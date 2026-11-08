"""Lap recorder for the analysis page (docs/ANALYSIS.md).

The bridge feeds it every telemetry frame. While the game delivers live data with a lap position it
samples at [analysis] hz (30), cuts the track into sections of [analysis] section_m (250 m) along the
track (lap position x track length, not the driven distance) and keeps per lap:

- the samples (time, lap position, x / y, speed, throttle, brake, steering, gear), forward only;
- per section the attempts. An attempt starts when the car drives into the section from the section
  before it and ends when it drives into the next one. Entering N-1 and then N again (practice: turned
  around) starts a new attempt for N; a spin that rolls back over a border replaces nothing.

Laps are written as JSON Lines when they end (nothing is written while driving). New best sections and
laps become offers (SAVE / SKIP) that wait until answered; a saved baseline keeps one backup of the
previous one for UNDO. One run = one game session (game, track, car, session id), or until END RUN.

Times in memory are monotonic seconds; the files store seconds from the lap / section start.
"""
import json
import math
import re
import shutil
import threading
import time
from pathlib import Path

FORMAT_VERSION = 1
BACKWARD_BREAK_M = 100.0     # back more than this from the furthest point reached: the lap does not count
RESTART_M = 200.0            # a jump back to the start line from further than this: restart (new lap)
MIN_TRACK_M = 300.0
STAGE_END_POS = 0.9995       # a stage (no line to cross again) ends when the car stays at its end
STAGE_END_S = 1.0
STANDING_KMH = 3.0           # a lap that starts standing (stage start) is timed from the moment it moves
OUTLINE_STEP_M = 5.0
LINE_STEP = 2                # every 2nd sample for the full-lap race lines on the map
AMBIENT = ("air_c", "road_c", "tyre_compound", "time_of_day", "fuel_l")

# sample row: [now, p, x, y, v, thr, brk, str, g, sec, att, line]  line = 1: part of the lap's line
NOW, P, X, Y, V, THR, BRK, STR, G, SEC, ATT, LINE = range(12)


def slug(text) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text or "unknown")).strip("-").lower() or "unknown"


def interp(xs: list, ys: list, x: float):
    """Linear interpolation of y at x in increasing xs; None outside or empty."""
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    if xs[hi] == xs[lo]:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / (xs[hi] - xs[lo])


def r3(value):
    return None if value is None else round(value, 3)


class Attempt:
    __slots__ = ("sec", "no", "t_in", "t_out", "samples", "max_p", "broken")

    def __init__(self, sec: int, no: int, t_in: float):
        self.sec, self.no, self.t_in, self.t_out = sec, no, t_in, None
        self.samples, self.max_p, self.broken = [], -1.0, False

    @property
    def time(self):
        return None if self.t_out is None else self.t_out - self.t_in


class Lap:
    def __init__(self, no: int, t0: float, out_lap: bool, standing: bool):
        self.no, self.t0, self.out_lap, self.standing = no, t0, out_lap, standing
        self.rows, self.attempts = [], {}
        self.max_p, self.broken, self.repeated, self.valid = -1.0, False, False, True
        self.time, self.ambient, self.file = None, None, None

    def line(self) -> list:
        return [row for row in self.rows if row[LINE]]

    def done(self, sec: int):
        """The latest completed attempt of a section."""
        for attempt in reversed(self.attempts.get(sec, [])):
            if attempt.t_out is not None:
                return attempt
        return None

    def latest(self, sec: int):
        attempts = self.attempts.get(sec)
        return attempts[-1] if attempts else None

    @property
    def clean(self) -> bool:
        """Driven in one go from line to line: no out lap, no pause, no turning around, nothing repeated."""
        return self.time is not None and not (self.out_lap or self.broken or self.repeated)

    @property
    def counts(self) -> bool:
        """A lap time that counts: clean, and the game says valid."""
        return self.clean and self.valid

    def info(self) -> dict:
        return {"lap": self.no, "time": r3(self.time), "counts": self.counts, "valid": self.valid,
                "out_lap": self.out_lap, "broken": self.broken, "repeated": self.repeated}


class Recorder:
    def __init__(self, data_dir, hz: int = 30, section_m: float = 250.0, log=None):
        self.dir = Path(data_dir)
        self.hz, self.period, self.section_m = hz, 1.0 / hz, float(section_m)
        self.log = log or (lambda *args: None)
        self.lock = threading.RLock()
        self.offers, self.next_offer, self.undo_stack = [], 1, []
        self.ended = None                      # the run that ended last, for the end-of-run menu
        self.why = "NO DATA YET"               # why nothing is recorded right now (None while recording)
        self.version = 0                       # +1 whenever state() changes (a lap, an offer, a save)
        self._reset_run()
        self._load_pending()

    # ------------------------------------------------------------------ runs

    def _reset_run(self) -> None:
        self.key, self.meta, self.run_dir, self.run_started = None, {}, None, None
        self.length, self.sections = 0.0, 0
        self.lap, self.last_lap, self.prev_lap = None, None, None
        self.last, self.cur_sec, self.attempt, self.end_since = None, None, None, None
        self.base = {"lap": None, "sections": {}}
        self.lap_no, self.laps_written, self.run_best, self.paused = 0, 0, None, False
        self.version += 1

    def _start_run(self, key: tuple, frame: dict) -> None:
        self._reset_run()
        game, track, car, session = key
        self.key = key
        self.length = float(frame["track_length_m"])
        rest = self.length % self.section_m
        self.sections = max(1, int(self.length // self.section_m) + (1 if rest >= self.section_m / 2 else 0))
        self.meta = {"game": game, "track": track or "unknown", "car": car or "unknown", "session": session,
                     "track_length_m": round(self.length, 1), "section_m": self.section_m,
                     "sections": self.sections, "hz": self.hz}
        self.run_started = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.run_dir = self.dir / "runs" / slug(game) / slug(track) / slug(car) / self.run_started
        self._load_baselines()
        self.log("analysis", "run", f"{game} / {track or '?'} / {car or '?'}: {self.length:.0f} m, "
                 f"{self.sections} sections of {self.section_m:g} m")

    def _end_run(self, reason: str) -> None:
        if self.key is None:
            return
        if self.lap is not None and len(self.lap.rows) > 1:
            self._write_lap(self.lap, complete=False)
        if self.laps_written:
            self._run_log({"type": "end", "reason": reason})
            size = sum(f.stat().st_size for f in self.run_dir.glob("*.jsonl"))
            self.ended = {"run": self.run_started, "dir": str(self.run_dir), "game": self.meta["game"],
                          "track": self.meta["track"], "car": self.meta["car"], "laps": self.laps_written,
                          "best": r3(self.run_best), "reason": reason, "mb": round(size / 1e6, 2)}
            self._save_pending()
            self.log("analysis", "run end", f"{reason}: {self.laps_written} laps in {self.run_dir}")
        self._reset_run()

    def _baseline_dir(self, meta: dict = None) -> Path:
        meta = meta or self.meta
        return self.dir / "baselines" / slug(meta["game"]) / slug(meta["track"]) / slug(meta["car"])

    # ------------------------------------------------------------------ feeding

    def feed(self, frame: dict, game: str, now: float) -> None:
        with self.lock:
            self.why = self._why_not(frame)
            if self.why:
                if frame.get("error") == "no_game" and self.key is not None:
                    self._end_run("game closed")
                self._pause()
                return
            key = (game, frame.get("track") or "", frame.get("car") or "", str(frame.get("session_id") or ""))
            if key != self.key:
                self._end_run("new session")
                self._start_run(key, frame)
            if self.last is not None and not self.paused and now - self.last[NOW] < self.period * 0.95:
                return
            self._sample(frame, now)

    @staticmethod
    def _why_not(frame: dict):
        """Why this frame is not recorded (shown on the page), or None."""
        if frame.get("error"):
            return frame.get("error_text") or str(frame["error"]).upper()
        if not frame.get("connected"):
            return "NO DATA FROM THE GAME"
        status = frame.get("status")
        if status != "live":
            return {"pause": "GAME PAUSED", "replay": "REPLAY", "off": "NOT ON TRACK"}.get(status, f"STATUS {status}".upper())
        if frame.get("lap_pos") is None:
            return "THE GAME SENDS NO LAP POSITION"
        if (frame.get("track_length_m") or 0) < MIN_TRACK_M:
            return "TRACK LENGTH UNKNOWN"
        return None

    def _pause(self) -> None:
        """No live data (pause, menu, replay): the lap and the attempt in progress no longer count."""
        if self.lap is not None and not self.paused:
            self.lap.broken = True
            if self.attempt is not None:
                self.attempt.broken = True
        self.paused = True

    def _section(self, p: float) -> int:
        return max(0, min(self.sections - 1, int(min(p, 0.999999) * self.length // self.section_m)))

    def _border_p(self, sec: int) -> float:
        return min(1.0, sec * self.section_m / self.length)

    def _sample(self, frame: dict, now: float) -> None:
        p = min(max(float(frame["lap_pos"]), 0.0), 1.0)
        sec = self._section(p)
        row = [now, p, frame.get("pos_x"), frame.get("pos_y"), float(frame.get("speed_kmh") or 0.0),
               float(frame.get("gas") or 0.0), float(frame.get("brake") or 0.0), float(frame.get("steer") or 0.0),
               int(frame.get("gear") or 0), sec, 0, 0]
        last, resumed = self.last, self.paused
        self.paused = False
        self.last = row
        if last is None:                                           # first sample of the run
            self._start_lap(now, p, row)
            self._record(row, frame)
            return
        lp = last[P]
        if lp > 0.9 and p < 0.1:                                   # over the line, forward
            gap = (1 - lp) + p
            t_cross = last[NOW] + (1 - lp) / gap * (now - last[NOW]) if gap > 0 else now
            self._close_attempt(t_cross)
            self._finish_lap(t_cross)
            self._start_lap(t_cross, 0.0, row)
            if sec != 0:
                self._enter(sec, row, last)
        elif lp < 0.1 and p > 0.9:                                 # over the line, backwards
            if self.lap is not None:
                self.lap.broken = True
            self.attempt, self.cur_sec = None, sec
        elif p < 0.02 and (lp - p) * self.length > RESTART_M:      # back at the start: restart
            if self.lap is not None and len(self.lap.rows) > 1:
                self.lap.broken = True
                self._write_lap(self.lap, complete=False)
                self.prev_lap, self.last_lap = self.last_lap, self.lap
            self._start_lap(now, p, row)
        elif self.lap is None:                                     # after a stage end: wait for the start
            if p < 0.02:
                self._start_lap(now, p, row)
        else:
            if (self.lap.max_p - p) * self.length > BACKWARD_BREAK_M:
                self.lap.broken = True                             # turned around: not one lap any more
            if sec != self.cur_sec:
                self._enter(sec, row, last)
        lap = self.lap
        if lap is None:
            return
        if resumed and self.attempt is not None:
            self.attempt.broken = True
        if lap.standing:
            moved = (p - lap.rows[0][P]) * self.length if lap.rows else 0.0
            if row[V] < STANDING_KMH and moved < 2.0:              # still standing at the start: time from here
                lap.t0, lap.max_p = now, -1.0
                lap.rows.clear()
                if self.attempt is not None:
                    self.attempt.t_in, self.attempt.max_p = now, -1.0
                    self.attempt.samples.clear()
            else:
                lap.standing = False
        self._record(row, frame)
        if p >= STAGE_END_POS:                                     # a stage ends when the car stays at its end
            self.end_since = self.end_since or now
            if now - self.end_since >= STAGE_END_S:
                self._close_attempt(self.end_since)
                self._finish_lap(self.end_since)
                self.lap, self.attempt, self.end_since = None, None, None
        else:
            self.end_since = None

    def _enter(self, sec: int, row: list, last: list) -> None:
        if row[P] > last[P] and self.cur_sec is not None and sec == self.cur_sec + 1:
            pb = self._border_p(sec)
            t_border = last[NOW] + (pb - last[P]) / (row[P] - last[P]) * (row[NOW] - last[NOW])
            t_border = min(max(t_border, last[NOW]), row[NOW])
            self._close_attempt(t_border)
            self._open_attempt(sec, t_border)
        else:
            # backwards into the section before, or a jump (reset, teleport): the attempt we leave stays
            # incomplete, and nothing is replaced until a section is entered from the section before it
            if row[P] > last[P] and self.lap is not None:
                self.lap.broken = True
            self.attempt = None
        self.cur_sec = sec

    def _record(self, row: list, frame: dict) -> None:
        lap = self.lap
        if lap is None:
            return
        p = row[P]
        if lap.ambient is None:                                    # ambient once per lap
            lap.ambient = {name: frame.get(name) for name in AMBIENT}
        if p > 0.02 and frame.get("lap_valid") is False:
            lap.valid = False
        if self.attempt is not None and p > self.attempt.max_p:
            row[ATT] = self.attempt.no
            self.attempt.samples.append(row)
            self.attempt.max_p = p
        if p > lap.max_p:
            row[LINE] = 1
            lap.max_p = p
        if row[ATT] or row[LINE]:
            lap.rows.append(row)

    # ------------------------------------------------------------------ laps and attempts

    def _start_lap(self, t0: float, p: float, row: list) -> None:
        self.lap_no += 1
        out_lap = p > 0.02
        self.lap = Lap(self.lap_no, t0, out_lap, standing=row[V] < STANDING_KMH)
        self.attempt, self.cur_sec, self.end_since = None, self._section(p), None
        if not out_lap:
            self._open_attempt(0, t0)
        self.version += 1

    def _open_attempt(self, sec: int, t_in: float) -> None:
        if self.lap is None:
            return
        attempts = self.lap.attempts.setdefault(sec, [])
        if attempts:
            self.lap.repeated = True
        self.attempt = Attempt(sec, len(attempts) + 1, t_in)
        attempts.append(self.attempt)

    def _close_attempt(self, t_out: float) -> None:
        attempt, self.attempt = self.attempt, None
        if attempt is None or len(attempt.samples) < 2:
            return
        attempt.t_out = t_out
        self.version += 1
        if attempt.broken:
            return
        base = self.base["sections"].get(attempt.sec)
        if base is None or attempt.time < base["time"] - 0.0005:
            self._offer({"kind": "section", "sec": attempt.sec, "lap": self.lap.no, "att": attempt.no,
                         "time": r3(attempt.time), "base": base and base["time"]}, (self.lap, attempt))

    def _finish_lap(self, t_end: float) -> None:
        lap = self.lap
        if lap is None:
            return
        lap.time = t_end - lap.t0
        self._write_lap(lap, complete=True)
        for offer in self.offers:                                  # sections of an invalid lap: say so
            if offer.get("run") == self.run_started and offer["lap"] == lap.no:
                offer["invalid"] = not lap.valid
                offer["file"] = str(lap.file)
        if lap.counts:
            self.run_best = lap.time if self.run_best is None else min(self.run_best, lap.time)
            base = self.base["lap"]
            if base is None or lap.time < base["time"] - 0.0005:
                self._offer({"kind": "lap", "sec": None, "lap": lap.no, "att": None, "time": r3(lap.time),
                             "base": base and base["time"], "file": str(lap.file)}, (lap, None))
        self._save_pending()
        self.prev_lap, self.last_lap = self.last_lap, lap
        self.version += 1

    # ------------------------------------------------------------------ files

    def _header(self, fmt: str, meta: dict = None, **extra) -> dict:
        meta = meta or self.meta
        return {"type": "header", "format": fmt, "version": FORMAT_VERSION,
                **{k: meta[k] for k in ("game", "car", "track", "track_length_m", "section_m", "sections", "hz")}, **extra}

    @staticmethod
    def _sample_line(row, t0: float) -> dict:
        return {"type": "s", "t": round(row[NOW] - t0, 3), "p": round(row[P], 6), "x": row[X], "y": row[Y],
                "v": round(row[V], 1), "thr": round(row[THR], 3), "brk": round(row[BRK], 3), "str": round(row[STR], 3),
                "g": row[G], "sec": row[SEC] + 1, "att": row[ATT], "line": row[LINE]}

    @staticmethod
    def _write_jsonl(path: Path, lines: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, separators=(",", ":")) + "\n")
        tmp.replace(path)

    @staticmethod
    def _read_jsonl(path) -> list:
        try:
            return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError):
            return []

    def _run_log(self, event: dict) -> None:
        if self.run_dir is None:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / "run.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            if f.tell() == 0:
                f.write(json.dumps(self._header("racing-dashboard.run", run=self.run_started,
                                                session=self.meta["session"]), separators=(",", ":")) + "\n")
            kind = event.pop("type")
            f.write(json.dumps({"type": kind, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **event},
                               separators=(",", ":")) + "\n")

    def _write_lap(self, lap: Lap, complete: bool) -> None:
        lines = [self._header("racing-dashboard.lap", run=self.run_started, lap=lap.no, out_lap=lap.out_lap)]
        lines += [self._sample_line(row, lap.t0) for row in lap.rows]
        for sec in sorted(lap.attempts):
            for attempt in lap.attempts[sec]:
                lines.append({"type": "section", "sec": sec + 1, "att": attempt.no, "time": r3(attempt.time),
                              "t_in": round(attempt.t_in - lap.t0, 3), "complete": attempt.t_out is not None,
                              "broken": attempt.broken})
        lines.append({"type": "ambient", **(lap.ambient or {})})
        lines.append({"type": "summary", "time": r3(lap.time), "complete": complete, "valid": lap.valid,
                      "counts": lap.counts, "out_lap": lap.out_lap, "repeated": lap.repeated, "broken": lap.broken,
                      "sections": [r3(self._section_time(lap, n)) for n in range(self.sections)]})
        lap.file = self.run_dir / f"lap-{lap.no:03d}.jsonl"
        self._write_jsonl(lap.file, lines)
        self.laps_written += 1
        self._run_log({"type": "lap", "lap": lap.no, "time": r3(lap.time), "counts": lap.counts, "complete": complete})

    # ------------------------------------------------------------------ baselines

    def _read_baseline(self, path: Path):
        lines = self._read_jsonl(path)
        summary = next((l for l in reversed(lines) if l.get("type") == "summary"), None)
        samples = [l for l in lines if l.get("type") == "s"]
        if not summary or summary.get("time") is None or len(samples) < 2:
            return None
        return {"time": summary["time"], "samples": samples, "p": [s["p"] for s in samples],
                "t": [s["t"] for s in samples], "header": lines[0]}

    def _load_baselines(self) -> None:
        folder = self._baseline_dir()
        self.base = {"lap": self._read_baseline(folder / "lap.jsonl"), "sections": {}}
        for n in range(self.sections):
            entry = self._read_baseline(folder / "sections" / f"section-{n + 1:02d}.jsonl")
            if entry:
                self.base["sections"][n] = entry
        self.version += 1

    @staticmethod
    def _same_car(a: dict, b: dict) -> bool:
        return all(a.get(k) == b.get(k) for k in ("game", "track", "car", "track_length_m", "section_m"))

    def _offer(self, offer: dict, payload) -> None:
        offer.update({"id": self.next_offer, "run": self.run_started, "game": self.meta["game"],
                      "track": self.meta["track"], "car": self.meta["car"], "meta": dict(self.meta),
                      "invalid": offer.get("invalid", False)})
        # one pending offer per section / lap and car: a faster one replaces it, a slower one is dropped
        for old in list(self.offers):
            if old["kind"] == offer["kind"] and old["sec"] == offer["sec"] and self._same_car(old["meta"], offer["meta"]):
                if offer["time"] < old["time"]:
                    self.offers.remove(old)
                else:
                    return
        self.next_offer += 1
        offer["_payload"] = payload
        self.offers.append(offer)
        self.version += 1
        self._run_log({"type": "offer", **self._public(offer)})
        self._save_pending()

    @staticmethod
    def _public(offer: dict) -> dict:
        return {k: v for k, v in offer.items() if not k.startswith("_") and k not in ("meta", "file")}

    def _save_pending(self) -> None:
        """Pending offers survive a restart of the bridge once their lap file is written."""
        keep = [{k: v for k, v in o.items() if not k.startswith("_")} for o in self.offers if o.get("file")]
        try:
            self._write_jsonl(self.dir / "pending.jsonl", [{"type": "header", "format": "racing-dashboard.pending",
                                                             "version": FORMAT_VERSION}] + keep)
        except OSError as error:
            self.log("analysis", "pending", repr(error))

    def _load_pending(self) -> None:
        for line in self._read_jsonl(self.dir / "pending.jsonl")[1:]:
            if line.get("file") and Path(line["file"]).exists():
                self.offers.append(line)
                self.next_offer = max(self.next_offer, line["id"] + 1)

    def _baseline_lines(self, offer: dict) -> list:
        meta = offer["meta"]
        source = {"run": offer["run"], "lap": offer["lap"], "attempt": offer["att"]}
        if "_payload" in offer:
            lap, attempt = offer["_payload"]
            t0 = attempt.t_in if attempt else lap.t0
            body = [self._sample_line(r, t0) for r in (attempt.samples if attempt else lap.line())]
        else:                                                      # from the lap file (after a restart)
            lines = self._read_jsonl(offer["file"])
            if offer["kind"] == "lap":
                body = [l for l in lines if l.get("type") == "s" and l.get("line")]
            else:
                sec, att = offer["sec"] + 1, offer["att"]
                info = next(l for l in lines if l.get("type") == "section" and l["sec"] == sec and l["att"] == att)
                body = [dict(l, t=round(l["t"] - info["t_in"], 3)) for l in lines
                        if l.get("type") == "s" and l["sec"] == sec and l["att"] == att]
        if offer["kind"] == "lap":
            head = self._header("racing-dashboard.lap-baseline", meta, source=source)
        else:
            d0 = offer["sec"] * meta["section_m"]
            head = self._header("racing-dashboard.section-baseline", meta, source=source, section=offer["sec"] + 1,
                                from_m=round(d0, 1), to_m=round(min(meta["track_length_m"], d0 + meta["section_m"]), 1))
            for line in body:
                line["d"] = round(line["p"] * meta["track_length_m"] - d0, 2)
        head["saved"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        return [head] + body + [{"type": "summary", "time": offer["time"]}]

    @staticmethod
    def _baseline_path(folder: Path, offer: dict) -> Path:
        if offer["kind"] == "lap":
            return folder / "lap.jsonl"
        return folder / "sections" / f"section-{offer['sec'] + 1:02d}.jsonl"

    def decide(self, offer_id: int, save: bool) -> bool:
        """SAVE (save=True) or SKIP an offer."""
        with self.lock:
            offer = next((o for o in self.offers if o["id"] == offer_id), None)
            if offer is None:
                return False
            self.offers.remove(offer)
            if save:
                folder = self._baseline_dir(offer["meta"])
                path = self._baseline_path(folder, offer)
                current = self._read_baseline(path)
                if current is None or offer["time"] < current["time"]:
                    lines = self._baseline_lines(offer)
                    backup = path.with_name(path.stem + ".prev.jsonl")
                    if path.exists():
                        path.replace(backup)
                    elif backup.exists():
                        backup.unlink()
                    self._write_jsonl(path, lines)
                    self.undo_stack = (self.undo_stack + [{"path": str(path), "label": self.label(offer)}])[-20:]
                    self.log("analysis", "baseline", f"saved {self.label(offer)}: {offer['time']:.3f} s")
                if self.key and folder == self._baseline_dir():
                    self._load_baselines()
            self._run_log({"type": "save" if save else "skip", "offer": offer_id, "kind": offer["kind"],
                           "sec": offer["sec"], "time": offer["time"]})
            self._save_pending()
            self.version += 1
            return True

    def save_all(self) -> int:
        return self.decide_all(True)

    def decide_all(self, save: bool) -> int:
        """SAVE ALL or SKIP ALL open offers; returns how many."""
        with self.lock:
            ids = [o["id"] for o in self.offers]
            for offer_id in ids:
                self.decide(offer_id, save)
            return len(ids)

    def undo(self) -> bool:
        """Back to the baseline before the last save (its backup); no backup: the baseline is removed."""
        with self.lock:
            if not self.undo_stack:
                return False
            entry = self.undo_stack.pop()
            path = Path(entry["path"])
            backup = path.with_name(path.stem + ".prev.jsonl")
            if backup.exists():
                backup.replace(path)
            elif path.exists():
                path.unlink()
            if self.key:
                self._load_baselines()
            self._run_log({"type": "undo", "label": entry["label"]})
            self.log("analysis", "baseline", f"undo {entry['label']}")
            self.version += 1
            return True

    def end_run(self) -> None:
        with self.lock:
            self._end_run("END RUN")

    def finish_run(self, keep: str) -> bool:
        """End-of-run menu: keep "all" laps, or only the "baselines" (the run's lap files are deleted)."""
        with self.lock:
            if not self.ended:
                return False
            if keep == "baselines":
                for offer in self.offers:                          # their lap data now lives in memory only
                    if str(offer.get("file", "")).startswith(self.ended["dir"]):
                        offer.pop("file", None)
                shutil.rmtree(self.ended["dir"], ignore_errors=True)
                self._save_pending()
                self.log("analysis", "run", f"lap files deleted: {self.ended['dir']}")
            self.ended = None
            self.version += 1
            return True

    # ------------------------------------------------------------------ for the page

    @staticmethod
    def label(offer: dict) -> str:
        what = "Lap" if offer["kind"] == "lap" else f"Section {offer['sec'] + 1}"
        return f"{what} · lap {offer['lap']}" + (f" · attempt {offer['att']}" if (offer.get("att") or 1) > 1 else "")

    def _shown(self):
        """(red, blue): the lap in progress and the last lap; between laps and while nothing is recorded
        (pause, pits, after the run) the last lap and the one before."""
        if self.lap is not None and len(self.lap.rows) > 1 and not self.paused:
            return self.lap, self.last_lap
        return self.last_lap, self.prev_lap

    @staticmethod
    def _xy(rows, step: int = LINE_STEP) -> list:
        return [[row[X], row[Y]] for row in rows[::step] if row[X] is not None]

    def _outline(self) -> list:
        """The track drawn from the best lap, else the last lap, else the lap in progress: a point every 5 m."""
        if self.base["lap"]:
            rows = [(s["p"], s["x"], s["y"]) for s in self.base["lap"]["samples"]]
        else:
            lap = self.last_lap if self.last_lap is not None else self.lap
            rows = [(r[P], r[X], r[Y]) for r in (lap.line() if lap else [])]
        out, next_p = [], -1.0
        for p, x, y in rows:
            if x is not None and p >= next_p:
                out.append([x, y, round(p, 5)])
                next_p = p + OUTLINE_STEP_M / self.length
        return out

    def _borders(self, outline: list) -> list:
        """Per section start: [x, y, nx, ny] (point and normal of the track there), None if not known yet."""
        if len(outline) < 2:
            return []
        ps, xs, ys = [o[2] for o in outline], [o[0] for o in outline], [o[1] for o in outline]
        out = []
        for n in range(self.sections):
            pb = max(ps[0], self._border_p(n))
            pa = min(ps[-1], pb + 10 / self.length)
            x, y, x2, y2 = interp(ps, xs, pb), interp(ps, ys, pb), interp(ps, xs, pa), interp(ps, ys, pa)
            if None in (x, y, x2, y2) or (x, y) == (x2, y2):
                out.append(None)
                continue
            norm = math.hypot(x2 - x, y2 - y)
            out.append([round(x, 2), round(y, 2), round(-(y2 - y) / norm, 4), round((x2 - x) / norm, 4)])
        return out

    @staticmethod
    def _section_time(lap, n: int):
        attempt = lap.done(n) if lap is not None else None
        return attempt.time if attempt else None

    def _strip(self) -> dict:
        """Per section: delta of the red lap against the best section and the blue lap. Sections the lap in
        progress has not reached yet show the last lap's values instead (old = True, drawn dimmer)."""
        red, blue = self._shown()
        best, last, times, attempts, old = [], [], [], [], []
        for n in range(self.sections):
            lap, other, prev = red, blue, False
            if self._section_time(red, n) is None and red is self.lap and blue is not None:
                lap, other, prev = blue, self.prev_lap, True
            t = self._section_time(lap, n)
            base = self.base["sections"].get(n)
            tb = self._section_time(other, n)
            times.append(r3(t))
            best.append(None if t is None or base is None else r3(t - base["time"]))
            last.append(None if t is None or tb is None else r3(t - tb))
            attempts.append(len(lap.attempts.get(n, [])) if lap is not None else 0)
            old.append(prev and t is not None)
        return {"best": best, "last": last, "times": times, "attempts": attempts, "old": old,
                "base": [r3(self.base["sections"][n]["time"]) if n in self.base["sections"] else None
                         for n in range(self.sections)]}

    def _deltas(self) -> dict:
        red, blue = self._shown()
        out = {"lap_best": None, "lap_last": None, "sec_best": None, "sec_last": None, "lap_time": None, "sec": None}
        base_lap = self.base["lap"]
        if red is None:
            return out
        if red is not self.lap or self.last is None:               # between laps / after the run: the totals
            out["lap_time"] = r3(red.time)
            if red.time is not None and base_lap:
                out["lap_best"] = r3(red.time - base_lap["time"])
            if red.time is not None and blue is not None and blue.time is not None:
                out["lap_last"] = r3(red.time - blue.time)
            return out
        p, now = self.last[P], self.last[NOW]
        out["lap_time"] = r3(now - red.t0)
        if not (red.broken or red.repeated or red.out_lap):
            if base_lap:
                ref = interp(base_lap["p"], base_lap["t"], p)
                out["lap_best"] = None if ref is None else r3(now - red.t0 - ref)
            if blue is not None and blue.clean:                   # the last lap need not be valid
                line = blue.line()
                ref = interp([r[P] for r in line], [r[NOW] - blue.t0 for r in line], p)
                out["lap_last"] = None if ref is None else r3(now - red.t0 - ref)
        attempt = self.attempt
        if attempt is not None and attempt.samples:
            out["sec"] = attempt.sec
            ts = now - attempt.t_in
            base = self.base["sections"].get(attempt.sec)
            if base:
                ref = interp(base["p"], base["t"], p)
                out["sec_best"] = None if ref is None else r3(ts - ref)
            prev = blue.done(attempt.sec) if blue is not None else None
            if prev is not None:
                ref = interp([r[P] for r in prev.samples], [r[NOW] - prev.t_in for r in prev.samples], p)
                out["sec_last"] = None if ref is None else r3(ts - ref)
        return out

    def _offers(self) -> list:
        return [dict(self._public(o), label=self.label(o)) for o in self.offers]

    def state(self) -> dict:
        """Everything the page needs on load and after each change (see version): track, lines, offers."""
        with self.lock:
            red, blue = self._shown()
            outline = self._outline() if self.key else []
            base = self.base["lap"]
            return {
                "version": self.version, "active": self.key is not None,
                **({k: self.meta[k] for k in ("game", "car", "track", "track_length_m", "section_m", "sections")}
                   if self.key else {}),
                "lap": self.lap.no if self.lap else None, "laps": self.laps_written,
                "outline": outline, "borders": self._borders(outline) if self.key else [],
                "lines": {"best": [[s["x"], s["y"]] for s in base["samples"][::LINE_STEP] if s.get("x") is not None]
                          if base else [],
                          "last": self._xy(blue.line()) if blue else []},
                "red_lap": red.no if red else None, "blue_lap": blue.no if blue else None,
                "base_lap": base["time"] if base else None, "run_best": r3(self.run_best),
                "offers": self._offers(), "undo": self.undo_stack[-1]["label"] if self.undo_stack else None,
                "ended": self.ended,
            }

    def live(self, since: int = 0) -> dict:
        """Small and frequent: deltas, the strip, the current section, the red line from point `since`."""
        with self.lock:
            red, _ = self._shown()
            line = self._xy(red.line()) if red else []
            since = max(0, min(since, len(line)))
            why = self.why or (None if self.lap is not None or self.key is None else "STAGE FINISHED")
            return {"version": self.version, "active": self.key is not None,
                    "recording": self.lap is not None and not self.paused, "why": why,
                    "last_lap": self.last_lap.info() if self.last_lap else None,
                    "sec": self.cur_sec, "lap": self.lap.no if self.lap else None, "red_lap": red.no if red else None,
                    "deltas": self._deltas(), "strip": self._strip() if self.key else None,
                    "now_from": since, "now_line": line[since:], "offers": len(self.offers)}

    def section(self, n: int) -> dict:
        """One section's three lines: best (baseline), last, now. Rows: [d, t, v, thr, brk, str, g, x, y],
        d = metres from the section start, t = seconds from the section start."""
        with self.lock:
            if not self.key or not 0 <= n < self.sections:
                return {"n": n, "best": [], "last": [], "now": []}
            d0 = n * self.section_m
            red, blue = self._shown()

            def rows(attempt):
                if attempt is None:
                    return []
                return [[round(r[P] * self.length - d0, 2), round(r[NOW] - attempt.t_in, 3), round(r[V], 1),
                         round(r[THR], 3), round(r[BRK], 3), round(r[STR], 3), r[G], r[X], r[Y]] for r in attempt.samples]

            base = self.base["sections"].get(n)
            best = [[round(s["p"] * self.length - d0, 2), s["t"], s["v"], s["thr"], s["brk"], s["str"], s["g"],
                     s["x"], s["y"]] for s in base["samples"]] if base else []
            now_attempt = red.latest(n) if red else None
            last_attempt = blue.done(n) if blue else None
            return {"n": n, "from_m": round(d0, 1), "to_m": round(min(self.length, d0 + self.section_m), 1),
                    "best": best, "best_time": base["time"] if base else None,
                    "last": rows(last_attempt), "last_time": r3(last_attempt.time) if last_attempt else None,
                    "now": rows(now_attempt), "now_time": r3(now_attempt.time) if now_attempt else None,
                    "now_attempt": now_attempt.no if now_attempt else None,
                    "red_lap": red.no if red else None, "blue_lap": blue.no if blue else None}
