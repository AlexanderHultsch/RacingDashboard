"""The analysis pipeline: a background worker that analyses every telemetry sample and saves it all for the AI.

The bridge hands it every frame (Pipeline.put: never blocks; when the worker falls behind, the oldest frame is
dropped and counted). Only while the AI DETAIL LOG is on (the bridge decides) and the game delivers live data.
The worker samples at [pipeline] hz, cuts the session into laps (lap position wrapping at the line) and:

1. live pass, at the end of every lap: derived values, phase, corner, label and reasons with the grip envelope,
   reference lap and corner map of the session so far (core/pipeline_rules.py); the rows are appended to
   samples.csv at once, so a crash loses at most the lap in progress.
2. final pass, at the end of the session (another car, track or session, no live data for session_idle_s, the
   bridge closing) or on demand (POST /api/pipeline/finalize): the envelope, the reference (the best valid lap)
   and the corner map again over the whole session, every sample relabelled, and laps.json, corners.json,
   session.json and README.md written next to samples.csv.

Folder per session: data/sessions/<game>/<track>/<car>/<date_time>/. Thresholds: config/analysis.default.toml
(+ config/analysis.toml). Schema: docs/PIPELINE.md and the README.md in every session folder.
"""
import csv
import json
import queue
import re
import threading
import time
from pathlib import Path

import pipeline_rules as rules

FORMAT_VERSION = 1


def slug(text) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "unknown").lower()).strip("-") or "unknown"


def _wheel(values, k):
    return values[k] if isinstance(values, (list, tuple)) and len(values) == 4 else None


def sample(frame: dict, t: float, lap: int, lap_time: float, steer_unit: float) -> dict:
    """One row of samples.csv from a telemetry frame (core/telemetry.py) and its detail block (connector)."""
    x = frame.get("detail") or {}
    length = frame.get("track_length_m") or 0.0
    steer = frame.get("steer")
    steer_deg = x.get("steer_deg") if x.get("steer_deg") else (None if steer is None else steer * steer_unit)
    row = {
        "session_time_s": round(t, 3), "lap": lap, "lap_time_s": round(lap_time, 3),
        "lap_dist_m": round(frame["lap_pos"] * length, 2), "lap_pos": frame["lap_pos"],
        "speed_kmh": frame.get("speed_kmh"), "throttle": frame.get("gas"), "brake": frame.get("brake"),
        "clutch": x.get("clutch"), "steer": steer, "steer_deg": None if steer_deg is None else round(steer_deg, 1),
        "gear": frame.get("gear"), "rpm": frame.get("rpm"), "torque_nm": x.get("torque_nm"),
        "a_lat_g": frame.get("g_lat"), "a_long_g": frame.get("g_long"), "yaw_rate_dps": frame.get("yaw_rate"),
        "pitch_rad": x.get("pitch_rad"), "roll_rad": x.get("roll_rad"),
        "ride_height_front_m": (x.get("ride_height_m") or [None, None])[0],
        "ride_height_rear_m": (x.get("ride_height_m") or [None, None])[1],
        "body_slip_deg": frame.get("body_slip"),
        "kerb_vibration": x.get("kerb_vibration"), "brake_bias": frame.get("brake_bias"),
        "engine_brake": x.get("engine_brake"), "tc_level": frame.get("tc_level"), "abs_level": frame.get("abs_level"),
        "tc_strength": x.get("tc_strength"), "abs_strength": x.get("abs_strength"),
        "tc_active": frame.get("tc_active"), "abs_active": frame.get("abs_active"),
        "shift_signal": frame.get("shift_up"), "rev_limiter": frame.get("limiter"),
        "pos_x_m": frame.get("pos_x"), "pos_y_m": frame.get("pos_y"), "game_lap_time_ms": frame.get("lap_ms"),
        "game_delta_ms": x.get("delta_ms"), "wheels_out": frame.get("wheels_out"), "lap_valid": frame.get("lap_valid"),
    }
    sources = {"slip_ratio_{}": frame.get("wheel_slip"), "slip_angle_{}_deg": frame.get("slip_angle"),
               "wheel_load_{}_n": x.get("wheel_load_n"), "fx_{}_n": x.get("fx_n"), "fy_{}_n": x.get("fy_n"),
               "suspension_travel_{}_m": x.get("suspension_travel_m"), "tyre_temp_{}_c": frame.get("tyre_temp_c"),
               "tyre_pressure_{}_psi": frame.get("tyre_psi"), "tyre_wear_{}": x.get("tyre_wear"),
               "brake_temp_{}_c": frame.get("brake_temp_c")}
    for pattern, values in sources.items():
        for k, w in enumerate(rules.WHEELS):
            row[pattern.format(w)] = _wheel(values, k)
    return row


def to_csv(row: dict) -> list:
    out = []
    for col in rules.COLUMNS:
        v = row.get(col)
        if v is None:
            out.append("")
        elif isinstance(v, bool):
            out.append(1 if v else 0)
        elif isinstance(v, float):
            out.append(round(v, 4))
        else:
            out.append(v)
    return out


def from_csv(record: dict) -> dict:
    """A samples.csv row back to values (numbers as float, flags as bool, empty as None)."""
    row = {}
    for col in rules.RAW:
        text = record.get(col, "")
        if text == "":
            row[col] = None
        elif col in rules.BOOLS:
            row[col] = text in ("1", "True", "true")
        else:
            try:
                row[col] = float(text)
            except ValueError:
                row[col] = None
    if row.get("lap") is not None:
        row["lap"] = int(row["lap"])
    return row


class Session:
    """One game session (game, track, car, session id): its folder, the lap in progress, the live state."""

    def __init__(self, base: Path, key: tuple, frame: dict | None, cfg: dict, log, folder: Path | None = None,
                 meta: dict | None = None):
        self.key, self.cfg, self.log = key, cfg, log
        game, track, car, session_id = key
        self.meta = meta or {"game": game, "track": track or "unknown", "car": car or "unknown",
                             "session_id": session_id, "track_length_m": round(float(frame["track_length_m"]), 1)}
        self.started = folder.name if folder else time.strftime("%Y-%m-%d_%H-%M-%S")
        self.folder = folder or base / "sessions" / slug(game) / slug(track) / slug(car) / self.started
        self.folder.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.folder / "samples.csv"
        self.file = None
        self.writer = None
        self.envelope = rules.Envelope(cfg)
        self.seen = set()
        self.shift_rpm = {}
        self.reference, self.corners = None, []
        self.laps = []
        self.rows, self.lap_no, self.lap_t0, self.lap_start_p = [], 0, None, None
        self.lap_gap = False
        self.last_t = self.last_p = None
        self.samples = 0
        self.steer_from_game = False
        self.finalized = None
        if folder is None:                                         # an open session: its meta now, the laps after each lap,
            self.dump("session.json", {"format": "racing-dashboard.analysis-session", "version": FORMAT_VERSION,
                                       **self.meta, "started": self.started, "finalized": None,
                                       "hz": cfg["pipeline"]["hz"]})   # so a bridge killed mid-session can finish it later
            log("pipeline", "session", f"{game} / {track or '?'} / {car or '?'}: {self.folder}")

    @classmethod
    def restore(cls, folder: Path, cfg: dict, log) -> "Session":
        """An open session left behind (the bridge closed without finalizing): from its session.json and laps.json."""
        meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
        keep = {k: meta.get(k) for k in ("game", "track", "car", "session_id", "track_length_m")}
        s = cls(folder.parent, (keep["game"], keep["track"], keep["car"], keep["session_id"]), None, cfg, log, folder, keep)
        laps = folder / "laps.json"
        s.laps = json.loads(laps.read_text(encoding="utf-8")).get("laps", []) if laps.exists() else []
        return s

    # ------------------------------------------------------------ live

    def add(self, frame: dict, now: float) -> None:
        p = float(frame["lap_pos"])
        if self.rows and self.last_p is not None:
            if self.last_p > 0.9 and p < 0.1:
                self.close_lap(now, complete=True)
            elif p < self.last_p - 0.05:                           # back to the pits, a restart: the lap breaks
                self.close_lap(now, complete=False)
        if self.last_t is not None and now - self.last_t < 1.0 / self.cfg["pipeline"]["hz"] - 1e-4:
            self.last_p = p
            return
        if not self.rows:
            self.lap_no += 1
            self.lap_t0, self.lap_start_p, self.lap_gap = now, p, False
        elif now - self.last_t > self.cfg["pipeline"]["gap_s"]:
            self.lap_gap = True
        if (frame.get("detail") or {}).get("steer_deg"):
            self.steer_from_game = True
        self.rows.append(sample(frame, now, self.lap_no, now - self.lap_t0, self.cfg["pipeline"]["steer_deg_per_unit"]))
        self.last_t, self.last_p = now, p

    def note_fields(self, rows) -> None:
        for group, cols in rules.FIELD_GROUPS.items():
            if group not in self.seen and any(r.get(c) for r in rows for c in cols):
                self.seen.add(group)
        for r in rows:                                             # the rpm where the game first signals a shift, per gear
            if r.get("shift_signal") and r.get("gear") and r.get("rpm"):
                g = int(r["gear"])
                if g not in self.shift_rpm or r["rpm"] < self.shift_rpm[g]:
                    self.shift_rpm[g] = r["rpm"]

    def close_lap(self, now: float, complete: bool) -> None:
        rows, self.rows = self.rows, []
        if not rows:
            return
        complete = complete and self.lap_start_p is not None and self.lap_start_p < 0.03
        valid_flags = [r["lap_valid"] for r in rows if r.get("lap_valid") is not None]
        info = {"lap": rows[0]["lap"], "lap_time_s": round(now - self.lap_t0, 3) if complete else None,
                "complete": complete, "gap": self.lap_gap, "valid": complete and not self.lap_gap and all(valid_flags),
                "samples": len(rows)}
        for r in rows:
            self.envelope.add(r)
        self.note_fields(rows)
        found = rules.analyse_lap(rows, self.cfg, self.envelope, self.reference, self.corners or None, self.seen,
                                  self.shift_rpm, "live")
        info["labels"] = shares(rows)
        info["findings"] = len(found)
        self.write(rows)
        self.laps.append(info)
        best = self.reference_lap()
        if info["valid"] and best and best["lap"] == info["lap"]:
            self.corners = rules.corner_map(rows, self.cfg)
            self.reference = rules.reference_of(rows, self.corners, self.cfg)
        self.dump("laps.json", {"reference_lap": self.reference["lap"] if self.reference else None, "laps": self.laps})
        self.log("pipeline", "lap", f"lap {info['lap']}: {info['lap_time_s'] or '-'} s, "
                 f"{'valid' if info['valid'] else 'not valid'}, {info['labels']}")

    def reference_lap(self):
        valid = [l for l in self.laps if l["valid"] and l["lap_time_s"]]
        return min(valid, key=lambda l: l["lap_time_s"]) if valid else None

    def write(self, rows) -> None:
        if self.file is None:
            new = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
            self.file = open(self.csv_path, "a", newline="", encoding="utf-8")
            self.writer = csv.writer(self.file)
            if new:
                self.writer.writerow(rules.COLUMNS)
        for r in rows:
            self.writer.writerow(to_csv(r))
        self.file.flush()
        self.samples += len(rows)

    def close_file(self) -> None:
        if self.file is not None:
            self.file.close()
        self.file = self.writer = None

    # ------------------------------------------------------------ final pass

    def finalize(self, now: float, end: bool = True) -> dict:
        """Recompute envelope, reference and corner map over the whole session, relabel every sample, write the
        files. end: the session is over (the lap in progress is closed as incomplete); otherwise (on demand) the
        lap in progress goes on and later laps are appended with live labels again."""
        if self.rows and end:
            self.close_lap(now, complete=False)
        self.close_file()
        if not self.csv_path.exists():
            return {}
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            laps = {}
            for record in csv.DictReader(f):
                row = from_csv(record)
                laps.setdefault(row["lap"], []).append(row)
        cfg = self.cfg
        envelope, self.seen, self.shift_rpm = rules.Envelope(cfg), set(), {}
        for rows in laps.values():
            for r in rows:
                envelope.add(r)
            self.note_fields(rows)
        self.envelope = envelope
        best = self.reference_lap()
        self.reference, self.corners = None, []
        if best and best["lap"] in laps:
            ref_rows = laps[best["lap"]]
            rules.derive(ref_rows, cfg, envelope, None)
            rules.phases(ref_rows, cfg, envelope)
            self.corners = rules.corner_map(ref_rows, cfg)
            for r in ref_rows:
                r["corner_id"] = rules.corner_of(self.corners, r["lap_dist_m"])
            self.reference = rules.reference_of(ref_rows, self.corners, cfg)
        per_corner, counts = [], {"good": 0, "potential": 0, "bad": 0, "none": 0}
        tmp = self.csv_path.with_suffix(".csv.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(rules.COLUMNS)
            for lap, rows in sorted(laps.items()):
                found = rules.analyse_lap(rows, cfg, envelope, self.reference, self.corners or None,
                                          self.seen, self.shift_rpm, "final")
                for r in rows:
                    writer.writerow(to_csv(r))
                    counts[r["label"]] += 1
                info = next((l for l in self.laps if l["lap"] == lap), None)
                if info is not None:
                    info["labels"] = shares(rows)
                    info["findings"] = len(found)
                    if self.reference and info.get("lap_time_s"):
                        info["vs_reference_s"] = round(info["lap_time_s"] - self.reference["t"][-1], 3)
                for c in self.corners:
                    pts = rules.corner_points(rows, c, cfg)
                    if not pts:
                        continue
                    tally = {}
                    for fnd in found:
                        if rows[fnd["i0"]].get("corner_id") == c["corner_id"]:
                            name = f"{fnd['rule']} {fnd['level']}"
                            tally[name] = tally.get(name, 0) + 1
                    per_corner.append({"lap": lap, "corner_id": c["corner_id"], **pts, "rule_counts": tally})
        tmp.replace(self.csv_path)
        self.finalized = time.strftime("%Y-%m-%dT%H:%M:%S")
        ref_no = self.reference["lap"] if self.reference else None
        missing = [g for g in rules.FIELD_GROUPS if g not in self.seen]
        disabled = [r for r in rules.NEEDS if not rules.present(self.seen, r, self.reference is not None)]
        self.dump("laps.json", {"reference_lap": ref_no, "laps": self.laps})
        self.dump("corners.json", {"reference_lap": ref_no, "corners": self.corners, "per_lap": per_corner})
        self.dump("session.json", {
            "format": "racing-dashboard.analysis-session", "version": FORMAT_VERSION, **self.meta,
            "started": self.started, "finalized": self.finalized, "hz": cfg["pipeline"]["hz"],
            "config_version": cfg.get("config_version"), "config": cfg, "samples": sum(counts.values()),
            "laps": len(self.laps), "reference_lap": ref_no, "label_counts": counts,
            "missing_fields": missing, "present_fields": sorted(self.seen), "disabled_rules": disabled,
            "steer_deg_source": "game" if self.steer_from_game else
            f"estimated: steer x {cfg['pipeline']['steer_deg_per_unit']} deg",
            "envelope_g": envelope.table(),
        })
        (self.folder / "README.md").write_text(readme(), encoding="utf-8")
        if missing:
            self.log("pipeline", "missing", ", ".join(missing) + f" (rules off: {', '.join(disabled) or '-'})")
        self.log("pipeline", "finalized", f"{self.folder}: {len(self.laps)} laps, {sum(counts.values())} samples, "
                 f"reference lap {ref_no or '-'}")
        return {"folder": str(self.folder), "laps": len(self.laps), "samples": sum(counts.values()),
                "reference_lap": ref_no, "label_counts": counts, "missing_fields": missing}

    def dump(self, name: str, data: dict) -> None:
        path = self.folder / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        tmp.replace(path)


def shares(rows) -> dict:
    n = len(rows) or 1
    out = {}
    for level in ("good", "potential", "bad", "none"):
        out[level] = round(sum(1 for r in rows if r.get("label") == level) / n, 3)
    return out


class Pipeline:
    """The worker: a queue in front of one thread. put() never blocks the bridge."""

    def __init__(self, data_dir, log=None, cfg: dict | None = None):
        self.base = Path(data_dir)
        self.log = log or (lambda *_: None)
        self.cfg = cfg or rules.load_config()
        self.queue = queue.Queue(maxsize=self.cfg["pipeline"]["queue_size"])
        self.dropped = 0
        self.session: Session | None = None
        self.last_live = None
        self.thread = None
        self.status = {"active": False}
        self.last_result = None

    def start(self) -> None:
        if self.thread is None:
            for meta in sorted((self.base / "sessions").glob("*/*/*/*/session.json")):
                try:
                    if json.loads(meta.read_text(encoding="utf-8")).get("finalized") is None:
                        self.queue.put(("recover", meta.parent, None, time.monotonic()))   # finished by the worker
                except (OSError, ValueError):
                    pass
            self.thread = threading.Thread(target=self.run, name="pipeline", daemon=True)
            self.thread.start()

    def put(self, frame: dict, game: str, now: float) -> None:
        """Hand a frame to the worker; when it lags behind, the oldest frame is dropped (counted)."""
        item = ("frame", frame, game, now)
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(item)
            except queue.Full:
                self.dropped += 1

    def request_finalize(self) -> None:
        self.queue.put(("finalize", None, None, time.monotonic()))

    def stop(self, timeout: float = 30.0) -> None:
        """Finalize the open session and end the worker (the bridge closing)."""
        if self.thread is None:
            return
        self.queue.put(("stop", None, None, time.monotonic()))
        self.thread.join(timeout)

    def run(self) -> None:
        while True:
            try:
                kind, frame, game, now = self.queue.get(timeout=1.0)
            except queue.Empty:
                self.idle(time.monotonic())
                continue
            try:
                if kind == "frame":
                    self.handle(frame, game, now)
                elif kind == "finalize":
                    self.finish(now, end=False)
                elif kind == "recover":
                    self.log("pipeline", "recover", f"finalizing a session left open: {frame}")
                    self.last_result = Session.restore(frame, self.cfg, self.log).finalize(now)
                elif kind == "stop":
                    self.finish(now, end=True)
                    return
            except Exception as error:  # noqa: BLE001  the pipeline must never stop the bridge
                self.log("pipeline", "error", repr(error))
            self.update_status()

    def handle(self, frame: dict, game: str, now: float) -> None:
        if (frame.get("error") or not frame.get("connected") or frame.get("status") != "live"
                or frame.get("lap_pos") is None or not frame.get("track_length_m")):
            self.idle(now)
            return
        key = (game, frame.get("track"), frame.get("car"), frame.get("session_id"))
        if self.session is not None and self.session.key != key:
            self.finish(now, end=True)
        if self.session is None:
            self.session = Session(self.base, key, frame, self.cfg, self.log)
        self.session.add(frame, now)
        self.last_live = now

    def idle(self, now: float) -> None:
        if self.session is not None and self.last_live is not None and now - self.last_live > self.cfg["pipeline"]["session_idle_s"]:
            self.finish(now, end=True)
            self.update_status()

    def finish(self, now: float, end: bool) -> None:
        if self.session is None:
            return
        self.last_result = self.session.finalize(now, end)
        if end:
            self.session.close_file()
            self.session = None

    def update_status(self) -> None:
        s = self.session
        self.status = {
            "active": s is not None, "dropped_frames": self.dropped, "last_finalized": self.last_result,
            **({"folder": str(s.folder), "lap_in_progress": s.lap_no, "laps_done": len(s.laps),
                "samples_written": s.samples, "reference_lap": s.reference["lap"] if s.reference else None,
                "missing_fields": [g for g in rules.FIELD_GROUPS if g not in s.seen] if s.laps else None,
                "last_lap": s.laps[-1] if s.laps else None} if s else {}),
        }


# ---------------------------------------------------------------- the README of every session folder

COLUMN_DOC = {
    "session_time_s": "bridge clock in seconds (monotonic, not wall time)",
    "lap": "lap number in this session, from 1 (lap 1 usually starts somewhere on the track: an out lap)",
    "lap_time_s": "seconds since this lap started", "lap_dist_m": "distance along the lap, lap_pos x track length",
    "lap_pos": "the game's position on the lap, 0..1", "speed_kmh": "speed",
    "throttle": "throttle pedal 0..1", "brake": "brake pedal 0..1", "clutch": "clutch as the game sends it",
    "steer": "steering -1 (left) .. 1 (right)", "steer_deg": "steering-wheel angle in degrees (see session.json steer_deg_source)",
    "gear": "-1 R, 0 N, 1.. forward", "rpm": "engine speed", "torque_nm": "engine torque",
    "a_lat_g": "lateral acceleration in g, + = turning right", "a_long_g": "longitudinal acceleration in g, - = braking",
    "yaw_rate_dps": "rotation in degrees per second, + = right", "pitch_rad": "pitch", "roll_rad": "roll",
    "ride_height_front_m": "ride height front", "ride_height_rear_m": "ride height rear",
    "body_slip_deg": "angle between where the car points and where it travels",
    "slip_ratio_*": "slip ratio per wheel (fl fr rl rr): - = slower than the car (braking, -1 locked), + = wheelspin",
    "slip_angle_*_deg": "tyre slip angle per wheel", "wheel_load_*_n": "vertical load per wheel",
    "fx_*_n": "longitudinal tyre force per wheel", "fy_*_n": "lateral tyre force per wheel",
    "suspension_travel_*_m": "suspension travel per wheel", "kerb_vibration": "kerb vibration (force feedback effect)",
    "brake_bias": "front brake share 0..1", "engine_brake": "engine braking setting",
    "tc_level": "TC setting", "abs_level": "ABS setting", "tc_strength": "TC strength (game value)",
    "abs_strength": "ABS strength (game value)", "tc_active": "1 while TC cuts", "abs_active": "1 while ABS works",
    "shift_signal": "1 while the game's shift light says shift up", "rev_limiter": "1 on the rev limiter",
    "tyre_temp_*_c": "tyre temperature", "tyre_pressure_*_psi": "tyre pressure", "tyre_wear_*": "tyre wear (game value)",
    "brake_temp_*_c": "brake temperature", "pos_x_m": "map position x", "pos_y_m": "map position y",
    "game_lap_time_ms": "the game's lap time", "game_delta_ms": "the game's delta to its best lap",
    "wheels_out": "wheels off the track 0..4", "lap_valid": "1 while the game counts the lap as valid",
    "g_combined_g": "sqrt(a_lat^2 + a_long^2)", "g_lat_max_g": "the cornering envelope at this speed (session)",
    "g_long_max_g": "the braking or traction envelope at this speed (session)",
    "grip_use": "U = sqrt((a_lat/g_lat_max)^2 + (a_long/g_long_max)^2); 1 = at the car's limit seen in this session",
    "mu_tyre_*": "sqrt(fx^2 + fy^2) / wheel_load per wheel (only where the game sends the forces)",
    "balance_deg": "mean |slip angle| front - rear: > 0 understeer, < 0 oversteer",
    "steer_rate_dps": "steering-wheel speed", "steer_reversal": "1 where the steering changed direction (> 2 deg within 0.5 s)",
    "ref_speed_kmh": "the reference lap's speed at this lap_dist_m", "dv_kmh": "speed - reference speed",
    "dt_s": "time behind the reference lap at this point (+ = slower)", "cost_s": "dt_s minus the previous sample's dt_s: where time is lost",
    "phase": "braking, entry, apex, exit, straight or transition", "corner_id": "corner number from the reference lap (empty on straights)",
    "label": "good, potential or bad (the worst rule that fired here), none if no rule applied",
    "reasons": "the rules that fired here: RULE level measured_value (operator threshold); worst first",
    "label_pass": "live (labelled at lap end with the session so far) or final (relabelled at the end)",
}


def readme() -> str:
    lines = [
        "# Racing Dashboard analysis session",
        "",
        "Telemetry of one driving session, every sample pre-analysed: phase, corner, label and reasons. For a coach "
        "(human or AI) to analyse driving skill; setup and weather are out of scope.",
        "",
        "## Files",
        "",
        "- `samples.csv`: one row per sample (about 30 per second), raw values then derived values; units in the column "
        "names; empty = not sent by the game.",
        "- `laps.json`: per lap: lap time (s), complete (started at the line and crossed it again), gap (a pause inside), "
        "valid (complete, no gap, the game kept it valid), label shares, findings; `reference_lap` is the best valid lap.",
        "- `corners.json`: the corners of the reference lap (`start_m`, `end_m` along the lap) and per lap and corner: "
        "braking point, minimum speed and where, full-throttle point (m), time lost against the reference (s), rule counts.",
        "- `session.json`: car, track, the thresholds used (`config`), `missing_fields` (never sent by the game: the rules "
        "that need them were off, `disabled_rules`), the grip envelope per speed bin (`envelope_g`), label counts.",
        "",
        "## Labels",
        "",
        "Every sample gets the worst level of the rules that cover it: bad > potential > good; `none` if no rule applied. "
        "Rules look at a whole phase (e.g. one braking) or at a stretch of samples (e.g. a lock-up), always after smoothing "
        "(~50 ms) and only when a condition held for its minimum time. Thresholds are starting values (`config`).",
        "",
        "Phases (first match wins): braking (brake on, steering straight), entry (brake on while steering, or little "
        "throttle until the speed minimum), apex (lateral g near the envelope, little throttle, no brake), exit (after the "
        "minimum, throttle rising), straight (full throttle, steering straight), transition (anything else).",
        "",
        "## Rules",
        "",
    ]
    lines += [f"- `{r}`: {rules.RULE_DOC.get(r, '')}" for r in rules.NEEDS]
    lines += ["", "## Columns", ""]
    lines += [f"- `{c}`: {d}" for c, d in COLUMN_DOC.items()]
    return "\n".join(lines) + "\n"
