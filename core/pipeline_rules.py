"""The per-sample analysis of the pipeline (core/pipeline.py, docs/PIPELINE.md): derived values, the grip envelope,
the driving phase and the rules that label every sample Good / Potential / Bad with reasons.

Pure functions on one lap at a time (a list of sample dicts with the COLUMNS names), so the live pass (after
every lap, with the envelope and reference of the session so far) and the final pass (the whole session again,
with the final envelope, reference lap and corner map) run the same code. Every threshold comes from the config
(config/analysis.default.toml); every rule names the fields it needs (NEEDS) and is skipped when the game never
sent them. Focus: driving skill, not setup or weather.
"""
import math
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_FILE = ROOT / "config" / "analysis.default.toml"
LOCAL_FILE = ROOT / "config" / "analysis.toml"

WHEELS = ("fl", "fr", "rl", "rr")
LEVELS = {"good": 1, "potential": 2, "bad": 3}

# the columns of samples.csv, in order: raw values (as the game sent them), then derived ones. Units in the names.
RAW = [
    "session_time_s", "lap", "lap_time_s", "lap_dist_m", "lap_pos", "speed_kmh", "throttle", "brake", "clutch",
    "steer", "steer_deg", "gear", "rpm", "torque_nm", "a_lat_g", "a_long_g", "yaw_rate_dps", "pitch_rad", "roll_rad",
    "ride_height_front_m", "ride_height_rear_m", "body_slip_deg",
    *[f"slip_ratio_{w}" for w in WHEELS], *[f"slip_angle_{w}_deg" for w in WHEELS],
    *[f"wheel_load_{w}_n" for w in WHEELS], *[f"fx_{w}_n" for w in WHEELS], *[f"fy_{w}_n" for w in WHEELS],
    *[f"suspension_travel_{w}_m" for w in WHEELS], "kerb_vibration", "brake_bias", "engine_brake",
    "tc_level", "abs_level", "tc_strength", "abs_strength", "tc_active", "abs_active", "shift_signal", "rev_limiter",
    *[f"tyre_temp_{w}_c" for w in WHEELS], *[f"tyre_pressure_{w}_psi" for w in WHEELS],
    *[f"tyre_wear_{w}" for w in WHEELS], *[f"brake_temp_{w}_c" for w in WHEELS],
    "pos_x_m", "pos_y_m", "game_lap_time_ms", "game_delta_ms", "wheels_out", "lap_valid",
]
DERIVED = [
    "g_combined_g", "g_lat_max_g", "g_long_max_g", "grip_use", *[f"mu_tyre_{w}" for w in WHEELS], "balance_deg",
    "steer_rate_dps", "steer_reversal", "ref_speed_kmh", "dv_kmh", "dt_s", "cost_s",
    "phase", "corner_id", "label", "reasons", "label_pass",
]
COLUMNS = RAW + DERIVED
BOOLS = {"tc_active", "abs_active", "shift_signal", "rev_limiter", "lap_valid", "steer_reversal"}
TEXT = {"phase", "label", "reasons", "label_pass"}

# fields whose absence switches rules off; a group counts as present once any of its columns is non-zero / true
FIELD_GROUPS = {
    "throttle": ["throttle"], "brake": ["brake"], "clutch": ["clutch"], "steer_deg": ["steer_deg"], "gear": ["gear"],
    "rpm": ["rpm"], "torque_nm": ["torque_nm"], "speed_kmh": ["speed_kmh"], "a_lat_g": ["a_lat_g"],
    "a_long_g": ["a_long_g"], "yaw_rate_dps": ["yaw_rate_dps"], "pitch_rad": ["pitch_rad"], "roll_rad": ["roll_rad"],
    "ride_height_m": ["ride_height_front_m", "ride_height_rear_m"], "body_slip_deg": ["body_slip_deg"],
    "slip_ratio": [f"slip_ratio_{w}" for w in WHEELS], "slip_angle": [f"slip_angle_{w}_deg" for w in WHEELS],
    "wheel_load": [f"wheel_load_{w}_n" for w in WHEELS], "fx": [f"fx_{w}_n" for w in WHEELS],
    "fy": [f"fy_{w}_n" for w in WHEELS], "suspension_travel": [f"suspension_travel_{w}_m" for w in WHEELS],
    "kerb_vibration": ["kerb_vibration"], "brake_bias": ["brake_bias"], "engine_brake": ["engine_brake"],
    "tc_strength": ["tc_strength"], "abs_strength": ["abs_strength"], "tc_active": ["tc_active"],
    "abs_active": ["abs_active"], "shift_signal": ["shift_signal"], "rev_limiter": ["rev_limiter"],
    "tyre_temp": [f"tyre_temp_{w}_c" for w in WHEELS], "tyre_pressure": [f"tyre_pressure_{w}_psi" for w in WHEELS],
    "tyre_wear": [f"tyre_wear_{w}" for w in WHEELS], "brake_temp": [f"brake_temp_{w}_c" for w in WHEELS],
    "position": ["pos_x_m", "pos_y_m"], "game_lap_time_ms": ["game_lap_time_ms"], "game_delta_ms": ["game_delta_ms"],
    "wheels_out": ["wheels_out"], "lap_valid": ["lap_valid"],
}
GRIP = ["a_lat_g", "a_long_g"]
NEEDS = {                                       # rule -> field groups it needs ("reference": a reference lap)
    "BRK_BUILDUP": ["brake"], "BRK_ENVELOPE": GRIP, "BRK_ABS": ["abs_active"], "BRK_POINT": ["reference"],
    "BRK_EARLY": ["reference"], "BRK_LOCKUP": ["slip_ratio"], "BRK_OVERLAP": ["throttle", "brake"],
    "BRK_DOUBLE": ["brake"],
    "ENT_TRAIL": GRIP + ["slip_angle"], "ENT_GRIP_USE": GRIP, "ENT_BALANCE": ["slip_angle"],
    "ENT_DEAD_ZONE": ["throttle", "brake"], "ENT_COAST": ["throttle", "brake"], "ENT_REVERSALS": ["steer_deg"],
    "APX_VMIN": ["reference"], "APX_GRIP_USE": GRIP, "APX_STEER_RATE": ["steer_deg"], "APX_TWO_MINIMA": ["speed_kmh"],
    "EXT_THROTTLE": ["throttle"], "EXT_REAR_SLIP": ["slip_ratio"], "EXT_WHEELSPIN": ["slip_ratio"],
    "EXT_UNUSED_TRACTION": ["slip_ratio"], "EXT_DIP": ["throttle"], "EXT_LIFT": ["throttle"], "EXT_TC": ["tc_active"],
    "EXT_FULL_LATE": ["reference"], "EXT_COUNTERSTEER": ["slip_angle", "steer_deg"], "EXT_STEER_ADDED": ["steer_deg"],
    "STR_THROTTLE": ["throttle"], "STR_SHIFT": ["shift_signal", "rpm", "gear"], "STR_PARTIAL": ["throttle"],
    "STR_LIMITER": ["rev_limiter"], "TRN_COAST": ["throttle", "brake"],
    "ALL_OFFTRACK": ["wheels_out"], "ALL_INVALID": ["lap_valid"],
}
PHASES = ("braking", "entry", "apex", "exit", "straight", "transition")
RULE_DOC = {
    "BRK_BUILDUP": "time from brake on to 90 % of its peak: good <= buildup_good_s, else potential",
    "BRK_ENVELOPE": "deceleration as a share of the braking envelope: good >= 0.95, potential 0.85-0.95, bad < 0.85",
    "BRK_ABS": "share of the braking phase with ABS working: good <= 30 %, potential > 70 %",
    "BRK_POINT": "braking point more than 5 m off the reference lap (m, - = earlier): potential",
    "BRK_EARLY": "braking more than 10 m earlier than the reference without a higher minimum speed: bad",
    "BRK_LOCKUP": "a wheel's slip ratio below -0.15 for more than 0.1 s: bad",
    "BRK_OVERLAP": "throttle and brake both above 10 % for 0.1 s: bad",
    "BRK_DOUBLE": "brake released and pressed again by 20 % within one braking: bad",
    "ENT_TRAIL": "trail braking with grip use 0.95-1.03 and |balance| <= 0.5 deg: good",
    "ENT_GRIP_USE": "grip use on entry below 0.95: potential",
    "ENT_BALANCE": "|balance| on entry: potential 0.5-1.5 deg, bad > 1.5 deg",
    "ENT_DEAD_ZONE": "no pedal for 0.1-0.3 s on entry: potential",
    "ENT_COAST": "no pedal for more than 0.3 s on entry: bad",
    "ENT_REVERSALS": "two or more steering reversals in one entry: bad",
    "APX_VMIN": "minimum speed against the reference (km/h): good >= -1, potential -1..-3, bad < -3 with grip use < 0.88",
    "APX_GRIP_USE": "grip use at the apex: good >= 0.95, else potential",
    "APX_STEER_RATE": "calm steering at the apex (< 20 deg/s): good",
    "APX_TWO_MINIMA": "two speed minima in one corner: bad",
    "EXT_THROTTLE": "throttle rising without a lift while the steering unwinds: good",
    "EXT_REAR_SLIP": "peak rear slip ratio on exit: good 0.03-0.08, potential 0.08-0.12",
    "EXT_WHEELSPIN": "rear slip ratio above 0.12 for more than 0.1 s: bad",
    "EXT_UNUSED_TRACTION": "rear slip below 0.03 with the throttle not full for 0.3 s: potential",
    "EXT_DIP": "one throttle dip of 10 % on exit: potential",
    "EXT_LIFT": "a throttle lift of 30 % on exit: bad",
    "EXT_TC": "TC working on exit: potential > 0.2 s, bad > 0.5 s",
    "EXT_FULL_LATE": "full throttle more than 5 m later than the reference (m): potential",
    "EXT_COUNTERSTEER": "counter-steering with oversteer (balance < -1 deg) for 0.1 s: bad",
    "EXT_STEER_ADDED": "steering added by 5 deg while on the throttle: bad",
    "STR_THROTTLE": "throttle at least 98 % on the straight: good",
    "STR_SHIFT": "upshift rpm against the game's shift signal in that gear: good within 150 rpm, else potential",
    "STR_PARTIAL": "straight steering with partial throttle for 0.5 s, no braking after: bad",
    "STR_LIMITER": "on the rev limiter for more than 0.1 s: bad",
    "TRN_COAST": "no pedal in a transition: good < 0.1 s, potential 0.1-0.3 s, bad > 0.3 s",
    "ALL_OFFTRACK": "more than two wheels off the track: bad",
    "ALL_INVALID": "the moment the game invalidated the lap (0.5 s around it): bad",
}


# ---------------------------------------------------------------- config

def merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(defaults: Path = DEFAULTS_FILE, local: Path = LOCAL_FILE) -> dict:
    """The thresholds: config/analysis.default.toml with config/analysis.toml (local, optional) merged over it."""
    with open(defaults, "rb") as f:
        cfg = tomllib.load(f)
    if local.exists():
        with open(local, "rb") as f:
            merge(cfg, tomllib.load(f))
    return cfg


# ---------------------------------------------------------------- small helpers

def num(value):
    return None if value is None or isinstance(value, str) or value != value else value


def median(values):
    values = sorted(v for v in values if v is not None)
    return values[len(values) // 2] if values else None


def interp(xs, ys, x):
    if not xs:
        return None
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    return ys[lo] if span <= 0 else ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / span


def present(seen: set, rule: str, has_reference: bool) -> bool:
    return all((g == "reference" and has_reference) or g in seen for g in NEEDS[rule])


def runs(rows, test, i0: int, i1: int):
    """[(start index, end index, seconds)] of the stretches between i0 and i1 where test(row) holds."""
    out, start = [], None
    for i in range(i0, i1 + 1):
        if test(rows[i]):
            start = i if start is None else start
        elif start is not None:
            out.append((start, i - 1, rows[i - 1]["_t"] - rows[start]["_t"] + rows[0]["_dt"]))
            start = None
    if start is not None:
        out.append((start, i1, rows[i1]["_t"] - rows[start]["_t"] + rows[0]["_dt"]))
    return out


def longest(found):
    return max(found, key=lambda r: r[2]) if found else None


# ---------------------------------------------------------------- the grip envelope

class Envelope:
    """g_max(v): the percentile of combined g per speed bin, separately for braking, cornering and traction, from
    histograms (cheap to update live, exact enough at resolution_g)."""

    MODES = ("braking", "cornering", "traction")

    def __init__(self, cfg: dict):
        e = cfg["envelope"]
        self.pct, self.bin, self.min_n, self.res = e["percentile"], e["bin_kmh"], e["min_samples"], e["resolution_g"]
        self.brake_on = cfg["phase"]["brake_on"]
        self.hist = {m: {} for m in self.MODES}
        self.cache = {}

    def mode(self, row) -> str | None:
        lat, lon = num(row.get("a_lat_g")), num(row.get("a_long_g"))
        if lat is None or lon is None:
            return None
        if (row.get("brake") or 0) > self.brake_on and lon < 0:
            return "braking"
        if abs(lat) >= abs(lon):
            return "cornering"
        return "traction" if lon > 0 else "braking"

    def add(self, row) -> None:
        mode = self.mode(row)
        v = num(row.get("speed_kmh"))
        if mode is None or v is None:
            return
        g = math.hypot(row["a_lat_g"], row["a_long_g"])
        bins = self.hist[mode].setdefault(int(v // self.bin), {})
        step = int(round(g / self.res))
        bins[step] = bins.get(step, 0) + 1
        self.cache = {}

    def g_max(self, mode: str, v) -> float | None:
        if v is None:
            return None
        b = int(v // self.bin)
        key = (mode, b)
        if key in self.cache:
            return self.cache[key]
        table = self.hist[mode]
        if not table:
            return None
        counts, reach = {}, 0
        while sum(counts.values()) < self.min_n and reach <= max(abs(k - b) for k in table):
            for k in {b - reach, b + reach}:
                for step, n in table.get(k, {}).items():
                    counts[step] = counts.get(step, 0) + n
            reach += 1
        total = sum(counts.values())
        if not total:
            return None
        need, acc = self.pct * total, 0
        for step in sorted(counts):
            acc += counts[step]
            if acc >= need:
                self.cache[key] = round(step * self.res, 3)
                return self.cache[key]
        return None

    def table(self) -> dict:
        out = {}
        for mode, bins in self.hist.items():
            out[mode] = {f"{b * self.bin}-{(b + 1) * self.bin}_kmh": self.g_max(mode, b * self.bin + self.bin / 2)
                         for b in sorted(bins)}
        return out


# ---------------------------------------------------------------- derived values and phases

def smooth(rows, keys, k: int) -> None:
    """Centred moving average over 2k+1 samples into row["_s"][key] (the raw values stay as they are)."""
    for r in rows:
        r["_s"] = {}
    for key in keys:
        vals = [num(r.get(key)) for r in rows]
        for i, r in enumerate(rows):
            window = [v for v in vals[max(0, i - k):i + k + 1] if v is not None]
            r["_s"][key] = sum(window) / len(window) if window else None


def speed_extrema(rows, rise: float):
    """Indices of speed minima / maxima where the speed falls and rises (or rises and falls) by at least rise."""
    v = [r["_s"]["speed_kmh"] or 0.0 for r in rows]
    mins, maxs = [], []
    direction, extreme = 0, 0
    for i in range(1, len(v)):
        if direction >= 0:                                   # rising (or unknown): look for a fall from the max
            if v[i] > v[extreme]:
                extreme = i
            elif v[extreme] - v[i] >= rise:
                if direction == 1 or extreme > 0:
                    maxs.append(extreme)
                direction, extreme = -1, i
        else:
            if v[i] < v[extreme]:
                extreme = i
            elif v[i] - v[extreme] >= rise:
                mins.append(extreme)
                direction, extreme = 1, i
    if direction == -1:
        mins.append(extreme)                                 # the lap ends while slowing down: the last minimum
    return mins, maxs


def derive(rows, cfg: dict, envelope: Envelope, reference: dict | None) -> None:
    """Fill the derived columns (except phase, corner, label) of one lap's rows."""
    hz = cfg["pipeline"]["hz"]
    k = max(1, round(cfg["smoothing"]["window_s"] * hz / 2))
    keys = ["throttle", "brake", "steer_deg", "speed_kmh", "a_lat_g", "a_long_g",
            *[f"slip_ratio_{w}" for w in WHEELS], *[f"slip_angle_{w}_deg" for w in WHEELS]]
    smooth(rows, keys, k)
    prev_dt = None
    for i, r in enumerate(rows):
        s = r["_s"]
        r["_t"] = r["session_time_s"]
        r["_dt"] = 1.0 / hz
        lat, lon = s["a_lat_g"], s["a_long_g"]
        r["g_combined_g"] = None if lat is None or lon is None else round(math.hypot(lat, lon), 3)
        glat = envelope.g_max("cornering", s["speed_kmh"])
        glong = envelope.g_max("braking" if (lon or 0) < 0 else "traction", s["speed_kmh"])
        r["g_lat_max_g"], r["g_long_max_g"] = glat, glong
        r["grip_use"] = (round(math.hypot(lat / glat, lon / glong), 3)
                         if None not in (lat, lon) and glat and glong else None)
        for w in WHEELS:
            fx, fy, load = (num(r.get(f"{c}_{w}_n")) for c in ("fx", "fy", "wheel_load"))
            r[f"mu_tyre_{w}"] = round(math.hypot(fx, fy) / load, 3) if None not in (fx, fy) and load and load > 0 else None
        front = [abs(s[f"slip_angle_{w}_deg"]) for w in ("fl", "fr") if s[f"slip_angle_{w}_deg"] is not None]
        rear = [abs(s[f"slip_angle_{w}_deg"]) for w in ("rl", "rr") if s[f"slip_angle_{w}_deg"] is not None]
        r["balance_deg"] = round(sum(front) / len(front) - sum(rear) / len(rear), 2) if front and rear else None
        if i == 0 or s["steer_deg"] is None or rows[i - 1]["_s"]["steer_deg"] is None:
            r["steer_rate_dps"] = 0.0
        else:
            span = max(1e-3, r["_t"] - rows[i - 1]["_t"])
            r["steer_rate_dps"] = round((s["steer_deg"] - rows[i - 1]["_s"]["steer_deg"]) / span, 1)
        if reference:
            d = r["lap_dist_m"]
            r["ref_speed_kmh"] = round(interp(reference["d"], reference["v"], d), 1)
            r["dv_kmh"] = round(r["speed_kmh"] - r["ref_speed_kmh"], 1)
            r["dt_s"] = round(r["lap_time_s"] - interp(reference["d"], reference["t"], d), 3)
            r["cost_s"] = 0.0 if prev_dt is None else round(r["dt_s"] - prev_dt, 4)
            prev_dt = r["dt_s"]
        else:
            r["ref_speed_kmh"] = r["dv_kmh"] = r["dt_s"] = r["cost_s"] = None
    reversals(rows, 2.0, 0.5)


def reversals(rows, min_deg: float, within_s: float) -> None:
    """steer_reversal = 1 where the steering changes direction after a swing of more than min_deg within within_s."""
    ext_i, direction = 0, 0
    for i, r in enumerate(rows):
        r["steer_reversal"] = False
        a = r["_s"]["steer_deg"]
        if a is None or rows[ext_i]["_s"]["steer_deg"] is None:
            ext_i = i
            continue
        step = a - rows[ext_i]["_s"]["steer_deg"]
        new = 1 if step > 0 else -1 if step < 0 else 0
        if direction == 0 or new == direction:
            if new:
                direction = new
            ext_i = i if (new == direction or direction == 0) else ext_i
        elif abs(step) > min_deg:
            if rows[i]["_t"] - rows[ext_i]["_t"] <= within_s:
                r["steer_reversal"] = True
            direction, ext_i = new, i


def phases(rows, cfg: dict, envelope: Envelope) -> None:
    """The driving phase of every sample, first match wins, then held for phase.min_s."""
    p = cfg["phase"]
    mins, maxs = speed_extrema(rows, p["min_rise_kmh"])
    ext = sorted([(i, "min") for i in mins] + [(i, "max") for i in maxs])
    nxt = [None] * len(rows)                                 # the next extremum ahead of each sample
    prv = [None] * len(rows)
    for i in range(len(rows)):
        nxt[i] = next((kind for j, kind in ext if j >= i), None)
        before = [kind for j, kind in ext if j < i]
        prv[i] = before[-1] if before else None
    raw = []
    for i, r in enumerate(rows):
        s = r["_s"]
        b, t = s["brake"] or 0.0, s["throttle"] or 0.0
        steer = abs(s["steer_deg"] or 0.0)
        glat = r["g_lat_max_g"]
        rising = i > 0 and t - (rows[max(0, i - 6)]["_s"]["throttle"] or 0.0) > 0.01
        if b > p["brake_on"] and steer < p["straight_steer_deg"]:
            phase = "braking"
        elif (b > p["brake_on"] and steer >= p["straight_steer_deg"]) or (t < p["entry_throttle_max"] and nxt[i] == "min"):
            phase = "entry"
        elif glat and s["a_lat_g"] is not None and abs(s["a_lat_g"]) > p["apex_lat_share"] * glat \
                and t < p["apex_throttle_max"] and b < p["apex_brake_max"]:
            phase = "apex"
        elif prv[i] == "min" and nxt[i] != "min" and rising:
            phase = "exit"
        elif t > p["full_throttle"] and steer < p["straight_steer_max_deg"]:
            phase = "straight"
        else:
            phase = "transition"
        raw.append(phase)
    hold = max(1, round(p["min_s"] * cfg["pipeline"]["hz"]))
    out, i = list(raw), 0
    while i < len(raw):
        j = i
        while j < len(raw) and raw[j] == raw[i]:
            j += 1
        if j - i < hold and i > 0:
            for k in range(i, j):
                out[k] = out[i - 1]
        i = j
    for r, phase in zip(rows, out):
        r["phase"] = phase
    for r in rows:
        r["_min"] = False
    for i in mins:
        rows[i]["_min"] = True


def segments(rows):
    """[(phase, first index, last index)] of the runs of one phase."""
    out, start = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i]["phase"] != rows[start]["phase"]:
            out.append((rows[start]["phase"], start, i - 1))
            start = i
    return out


# ---------------------------------------------------------------- corners and the reference lap

def corner_map(rows, cfg: dict | None = None) -> list:
    """Corners from a labelled lap (the reference): where the car corners for real, lateral g above lat_share of
    its cornering envelope (steering above the straight limit where the game sends no g), gaps under merge_m
    joined, at least min_m long, each starting where the braking / entry before it starts (at most lead_max_m
    earlier). Track and car independent. [{"corner_id", "start_m", "end_m"}]."""
    c = (cfg or {}).get("corners", {"lat_share": 0.4, "merge_m": 20.0, "min_m": 20.0, "lead_max_m": 200.0})
    straight = (cfg or {}).get("phase", {}).get("straight_steer_deg", 5.0)

    def cornering(r):
        lat, glat = r["_s"]["a_lat_g"], r.get("g_lat_max_g")
        if lat is not None and glat:
            return abs(lat) >= c["lat_share"] * glat
        return abs(r["_s"]["steer_deg"] or 0) >= straight

    spans, start = [], None
    for i, r in enumerate(rows):
        if cornering(r):
            start = i if start is None else start
        elif start is not None:
            spans.append([start, i - 1])
            start = None
    if start is not None:
        spans.append([start, len(rows) - 1])
    merged = []
    for a, b in spans:
        if merged and rows[a]["lap_dist_m"] - rows[merged[-1][1]]["lap_dist_m"] < c["merge_m"]:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        if rows[b]["lap_dist_m"] - rows[a]["lap_dist_m"] < c["min_m"]:
            continue
        lead = a
        while lead > 0 and rows[lead - 1]["phase"] in ("braking", "entry") \
                and rows[a]["lap_dist_m"] - rows[lead - 1]["lap_dist_m"] <= c["lead_max_m"]:
            lead -= 1
        if out and rows[lead]["lap_dist_m"] <= out[-1][1]:
            lead = next((k for k in range(lead, a + 1) if rows[k]["lap_dist_m"] > out[-1][1]), a)
        out.append([rows[lead]["lap_dist_m"], rows[b]["lap_dist_m"]])
    return [{"corner_id": k + 1, "start_m": round(a, 1), "end_m": round(b, 1)} for k, (a, b) in enumerate(out)]


def corner_of(corners, d):
    for c in corners:
        if c["start_m"] - 0.5 <= d <= c["end_m"] + 0.5:
            return c["corner_id"]
    return None


def corner_points(rows, corner, cfg) -> dict:
    """Braking point, minimum speed and full-throttle point of one lap in one corner (metres along the lap)."""
    p = cfg["phase"]
    a, b = corner["start_m"], corner["end_m"]
    inside = [r for r in rows if a - 150 <= r["lap_dist_m"] <= b + 200]
    core = [r for r in inside if a <= r["lap_dist_m"] <= b]
    if not core:
        return {}
    low = min(core, key=lambda r: r["speed_kmh"])
    vmin_d = low["lap_dist_m"]
    brake = None
    for r in inside:
        if r["lap_dist_m"] > vmin_d:
            break
        on = (r["brake"] or 0) > p["brake_on"]
        if on and brake is None:
            brake = r["lap_dist_m"]
        elif not on and brake is not None and r["lap_dist_m"] < a - 5:
            brake = None                                     # an earlier braking that ended before the corner
    full = next((r["lap_dist_m"] for r in inside if r["lap_dist_m"] > vmin_d and (r["throttle"] or 0) >= 0.98), None)
    lost = None
    if core[0].get("dt_s") is not None and core[-1].get("dt_s") is not None:
        lost = round(core[-1]["dt_s"] - core[0]["dt_s"], 3)
    return {"braking_point_m": None if brake is None else round(brake, 1), "v_min_kmh": round(low["speed_kmh"], 1),
            "v_min_at_m": round(vmin_d, 1), "full_throttle_m": None if full is None else round(full, 1),
            "time_lost_s": lost}


def reference_of(rows, corners, cfg) -> dict:
    """The reference lap's arrays for the comparisons (distance, lap time, speed) and its points per corner."""
    pts = sorted((r["lap_dist_m"], r["lap_time_s"], r["speed_kmh"]) for r in rows)
    clean = []
    for d, t, v in pts:
        if not clean or d > clean[-1][0]:
            clean.append((d, t, v))
    return {"lap": rows[0]["lap"], "d": [p[0] for p in clean], "t": [p[1] for p in clean], "v": [p[2] for p in clean],
            "corners": {c["corner_id"]: corner_points(rows, c, cfg) for c in corners}}


# ---------------------------------------------------------------- rules

def finding(rule, level, value, op, limit, i0, i1):
    return {"rule": rule, "level": level, "value": value, "op": op, "limit": limit, "i0": i0, "i1": i1}


def rules(rows, cfg: dict, seen: set, reference: dict | None, corners: list, shift_rpm: dict) -> list:
    """Every rule on one labelled lap: [finding]. A finding applies to the samples i0..i1."""
    out = []
    ref = reference is not None
    use = lambda rule: present(seen, rule, ref)  # noqa: E731
    segs = segments(rows)
    for n, (phase, i0, i1) in enumerate(segs):
        corner = rows[i0]["corner_id"]
        refc = (reference or {}).get("corners", {}).get(corner) if corner else None
        if phase == "braking":
            out += braking(rows, cfg, use, i0, i1, segs, n, refc, corners)
        elif phase == "entry":
            out += entry(rows, cfg, use, i0, i1)
        elif phase == "apex":
            out += apex(rows, cfg, use, i0, i1, refc)
        elif phase == "exit":
            out += exit_(rows, cfg, use, i0, i1, refc, corners)
        elif phase == "straight":
            out += straight(rows, cfg, use, i0, i1, shift_rpm)
        else:
            out += transition(rows, cfg, use, i0, i1)
    out += whole_lap(rows, cfg, use, corners, shift_rpm)
    return out


def braking(rows, cfg, use, i0, i1, segs, n, refc, corners):
    c, p, out = cfg["braking"], cfg["phase"], []
    s = lambda i, k: rows[i]["_s"][k]  # noqa: E731
    peak = max((s(i, "brake") or 0) for i in range(i0, i1 + 1))
    if use("BRK_BUILDUP") and peak > 0.3:
        on = next((i for i in range(i0, i1 + 1) if (s(i, "brake") or 0) > p["brake_on"]), i0)
        top = next((i for i in range(on, i1 + 1) if (s(i, "brake") or 0) >= 0.9 * peak), i1)
        took = round(rows[top]["_t"] - rows[on]["_t"], 3)
        out.append(finding("BRK_BUILDUP", "good" if took <= c["buildup_good_s"] else "potential", took, "<=",
                           c["buildup_good_s"], i0, i1))
    if use("BRK_ENVELOPE"):
        shares = [-s(i, "a_long_g") / rows[i]["g_long_max_g"] for i in range(i0, i1 + 1)
                  if (s(i, "brake") or 0) >= 0.5 * peak and s(i, "a_long_g") is not None and rows[i]["g_long_max_g"]]
        share = median(shares)
        if share is not None:
            level = "good" if share >= c["envelope_good"] else "potential" if share >= c["envelope_bad"] else "bad"
            out.append(finding("BRK_ENVELOPE", level, round(share, 3), ">=", c["envelope_good"], i0, i1))
    if use("BRK_ABS"):
        on = [bool(rows[i].get("abs_active")) for i in range(i0, i1 + 1)]
        share = sum(on) / len(on)
        if share <= c["abs_good_max"]:
            out.append(finding("BRK_ABS", "good", round(share, 2), "<=", c["abs_good_max"], i0, i1))
        elif share > c["abs_potential_min"]:
            out.append(finding("BRK_ABS", "potential", round(share, 2), ">", c["abs_potential_min"], i0, i1))
    if refc and refc.get("braking_point_m") is not None and (use("BRK_POINT") or use("BRK_EARLY")):
        start = rows[i0]["lap_dist_m"]
        diff = round(start - refc["braking_point_m"], 1)        # negative = earlier than the reference
        corner = rows[i0]["corner_id"]
        vmin = min((r["speed_kmh"] for r in rows if r["corner_id"] == corner), default=None)
        if diff < -c["early_bad_m"] and vmin is not None and vmin <= (refc.get("v_min_kmh") or 0) + 1:
            out.append(finding("BRK_EARLY", "bad", diff, "<", -c["early_bad_m"], i0, i1))
        elif abs(diff) > c["point_potential_m"]:
            out.append(finding("BRK_POINT", "potential", diff, "|x|>", c["point_potential_m"], i0, i1))
    end = segs[n + 1][2] if n + 1 < len(segs) and segs[n + 1][0] == "entry" else i1
    if use("BRK_LOCKUP"):
        for a, b, secs in runs(rows, lambda r: min((r["_s"][f"slip_ratio_{w}"] or 0) for w in WHEELS) < c["lockup_ratio"], i0, end):
            if secs >= c["lockup_s"]:
                worst = min(min((rows[i]["_s"][f"slip_ratio_{w}"] or 0) for w in WHEELS) for i in range(a, b + 1))
                out.append(finding("BRK_LOCKUP", "bad", round(worst, 3), "<", c["lockup_ratio"], a, b))
    if use("BRK_OVERLAP"):
        for a, b, secs in runs(rows, lambda r: (r["_s"]["throttle"] or 0) > c["overlap_throttle"]
                               and (r["_s"]["brake"] or 0) > c["overlap_brake"], i0, end):
            if secs >= c["overlap_s"]:
                out.append(finding("BRK_OVERLAP", "bad", round(secs, 2), ">=", c["overlap_s"], a, b))
    if use("BRK_DOUBLE"):
        top, dropped = 0.0, False
        for i in range(i0, end + 1):
            b = s(i, "brake") or 0
            if not dropped:
                top = max(top, b)
                dropped = top - b >= c["double_drop"] and b > p["brake_on"]
                low = b
            else:
                low = min(low, b)
                if b - low >= c["double_drop"]:
                    out.append(finding("BRK_DOUBLE", "bad", round(b - low, 2), ">=", c["double_drop"], i0, end))
                    break
    return out


def entry(rows, cfg, use, i0, i1):
    c, p, out = cfg["entry"], cfg["phase"], []
    trail = longest(runs(rows, lambda r: (r["_s"]["brake"] or 0) > p["brake_on"]
                         and abs(r["_s"]["steer_deg"] or 0) >= p["straight_steer_deg"], i0, i1))
    grip = median(rows[i]["grip_use"] for i in range(i0, i1 + 1))
    bal = median(abs(rows[i]["balance_deg"]) for i in range(i0, i1 + 1) if rows[i]["balance_deg"] is not None)
    if use("ENT_TRAIL") and trail and trail[2] >= c["trail_min_s"] and grip is not None and bal is not None \
            and c["grip_use_good_low"] <= grip <= c["grip_use_good_high"] and bal <= c["balance_good_deg"]:
        out.append(finding("ENT_TRAIL", "good", round(trail[2], 2), ">=", c["trail_min_s"], i0, i1))
    if use("ENT_GRIP_USE") and grip is not None and grip < c["grip_use_good_low"]:
        out.append(finding("ENT_GRIP_USE", "potential", grip, ">=", c["grip_use_good_low"], i0, i1))
    if use("ENT_BALANCE") and bal is not None:
        level = "good" if bal <= c["balance_good_deg"] else "potential" if bal <= c["balance_bad_deg"] else "bad"
        if level != "good":
            out.append(finding("ENT_BALANCE", level, bal, "<=", c["balance_good_deg"], i0, i1))
    coast = longest(runs(rows, lambda r: (r["_s"]["throttle"] or 0) < 0.05 and (r["_s"]["brake"] or 0) < 0.05, i0, i1))
    if coast and use("ENT_COAST") and coast[2] > c["coast_bad_s"]:
        out.append(finding("ENT_COAST", "bad", round(coast[2], 2), ">", c["coast_bad_s"], coast[0], coast[1]))
    elif coast and use("ENT_DEAD_ZONE") and coast[2] >= c["dead_zone_low_s"]:
        out.append(finding("ENT_DEAD_ZONE", "potential", round(coast[2], 2), ">=", c["dead_zone_low_s"], coast[0], coast[1]))
    count = sum(1 for i in range(i0, i1 + 1) if rows[i]["steer_reversal"])
    if use("ENT_REVERSALS") and count >= c["reversals_bad"]:
        out.append(finding("ENT_REVERSALS", "bad", count, ">=", c["reversals_bad"], i0, i1))
    return out


def apex(rows, cfg, use, i0, i1, refc):
    c, out = cfg["apex"], []
    vmin = min(rows[i]["speed_kmh"] for i in range(i0, i1 + 1))
    grip = median(rows[i]["grip_use"] for i in range(i0, i1 + 1))
    if use("APX_VMIN") and refc and refc.get("v_min_kmh") is not None:
        diff = round(vmin - refc["v_min_kmh"], 1)
        if diff >= -c["vmin_good_kmh"]:
            level = "good"
        elif diff < -c["vmin_bad_kmh"] and grip is not None and grip < c["grip_use_bad"]:
            level = "bad"
        else:
            level = "potential"
        out.append(finding("APX_VMIN", level, diff, ">=", -c["vmin_good_kmh"], i0, i1))
    if use("APX_GRIP_USE") and grip is not None:
        level = "good" if grip >= c["grip_use_good"] else "potential"
        out.append(finding("APX_GRIP_USE", level, grip, ">=", c["grip_use_good"], i0, i1))
    rate = median(abs(rows[i]["steer_rate_dps"]) for i in range(i0, i1 + 1))
    if use("APX_STEER_RATE") and rate is not None and rate < c["steer_rate_good_dps"]:
        out.append(finding("APX_STEER_RATE", "good", rate, "<", c["steer_rate_good_dps"], i0, i1))
    return out


def exit_(rows, cfg, use, i0, i1, refc, corners):
    c, out = cfg["exit"], []
    s = lambda i, k: rows[i]["_s"][k]  # noqa: E731
    thr = [s(i, "throttle") or 0 for i in range(i0, i1 + 1)]
    steer = [abs(s(i, "steer_deg") or 0) for i in range(i0, i1 + 1)]
    drops, peak, low, lifted = 0, thr[0], thr[0], 0.0
    for t in thr:
        if t > peak:
            if peak - low >= c["dip"]:
                drops += 1
            peak = low = t
        low = min(low, t)
        lifted = max(lifted, peak - low)
    if peak - low >= c["dip"]:
        drops += 1
    if use("EXT_THROTTLE") and lifted <= 0.05 and steer[-1] <= steer[0] + 0.5:
        out.append(finding("EXT_THROTTLE", "good", round(lifted, 2), "<=", 0.05, i0, i1))
    if use("EXT_LIFT") and lifted >= c["lift_bad"]:
        out.append(finding("EXT_LIFT", "bad", round(lifted, 2), ">=", c["lift_bad"], i0, i1))
    elif use("EXT_DIP") and drops == 1:
        out.append(finding("EXT_DIP", "potential", round(lifted, 2), ">=", c["dip"], i0, i1))
    rear = lambda r: max((r["_s"][f"slip_ratio_{w}"] or 0) for w in ("rl", "rr"))  # noqa: E731
    if use("EXT_REAR_SLIP"):
        top = max(rear(rows[i]) for i in range(i0, i1 + 1))
        spin = [x for x in runs(rows, lambda r: rear(r) > c["rear_slip_bad"], i0, i1) if x[2] >= c["wheelspin_s"]]
        if spin:
            a, b, _ = longest(spin)
            out.append(finding("EXT_WHEELSPIN", "bad", round(top, 3), ">", c["rear_slip_bad"], a, b))
        elif top > c["rear_slip_good_high"]:
            out.append(finding("EXT_REAR_SLIP", "potential", round(top, 3), "<=", c["rear_slip_good_high"], i0, i1))
        elif top >= c["rear_slip_good_low"]:
            out.append(finding("EXT_REAR_SLIP", "good", round(top, 3), "in", [c["rear_slip_good_low"], c["rear_slip_good_high"]], i0, i1))
        unused = longest(runs(rows, lambda r: rear(r) < c["rear_slip_good_low"] and (r["_s"]["throttle"] or 0) < 0.98, i0, i1))
        if unused and unused[2] >= c["unused_traction_s"] and use("EXT_UNUSED_TRACTION"):
            out.append(finding("EXT_UNUSED_TRACTION", "potential", round(unused[2], 2), ">=", c["unused_traction_s"], unused[0], unused[1]))
    if use("EXT_TC"):
        tc = longest(runs(rows, lambda r: bool(r.get("tc_active")), i0, i1))
        if tc and tc[2] > c["tc_bad_s"]:
            out.append(finding("EXT_TC", "bad", round(tc[2], 2), ">", c["tc_bad_s"], tc[0], tc[1]))
        elif tc and tc[2] > c["tc_potential_s"]:
            out.append(finding("EXT_TC", "potential", round(tc[2], 2), ">", c["tc_potential_s"], tc[0], tc[1]))
    if use("EXT_FULL_LATE") and refc and refc.get("full_throttle_m") is not None:
        corner = rows[i0]["corner_id"]
        mine = corner_points(rows, next(x for x in corners if x["corner_id"] == corner), cfg).get("full_throttle_m") if corner else None
        if mine is not None:
            late = round(mine - refc["full_throttle_m"], 1)
            if late > c["full_late_low_m"]:
                out.append(finding("EXT_FULL_LATE", "potential", late, "<=", c["full_late_low_m"], i0, i1))
    corner = rows[i0]["corner_id"]
    side = [s(i, "steer_deg") for i in range(len(rows)) if rows[i]["corner_id"] == corner and s(i, "steer_deg")]
    sign = 1 if sum(side) >= 0 else -1
    if use("EXT_COUNTERSTEER"):
        hit = longest(runs(rows, lambda r: (r["_s"]["steer_deg"] or 0) * sign < -1.0 and r["balance_deg"] is not None
                           and r["balance_deg"] < c["countersteer_balance_deg"], i0, i1))
        if hit and hit[2] >= 0.1:
            out.append(finding("EXT_COUNTERSTEER", "bad", round(hit[2], 2), ">=", 0.1, hit[0], hit[1]))
    if use("EXT_STEER_ADDED"):
        least = None
        for i in range(i0, i1 + 1):
            if (s(i, "throttle") or 0) <= c["steer_added_throttle"]:
                continue
            a = abs(s(i, "steer_deg") or 0)
            least = a if least is None else min(least, a)
            if a - least >= c["steer_added_deg"]:
                out.append(finding("EXT_STEER_ADDED", "bad", round(a - least, 1), ">=", c["steer_added_deg"], i, i1))
                break
    return out


def straight(rows, cfg, use, i0, i1, shift_rpm):
    c, out = cfg["straight"], []
    thr = median(rows[i]["_s"]["throttle"] for i in range(i0, i1 + 1))
    if use("STR_THROTTLE") and thr is not None and thr >= c["throttle_good"]:
        out.append(finding("STR_THROTTLE", "good", round(thr, 3), ">=", c["throttle_good"], i0, i1))
    return out


def transition(rows, cfg, use, i0, i1):
    c, s, out = cfg["transition"], cfg["straight"], []
    coast = longest(runs(rows, lambda r: (r["_s"]["throttle"] or 0) < 0.05 and (r["_s"]["brake"] or 0) < 0.05, i0, i1))
    if use("TRN_COAST"):
        secs = coast[2] if coast else 0.0
        level = "good" if secs < c["coast_good_s"] else "potential" if secs <= c["coast_bad_s"] else "bad"
        a, b = (coast[0], coast[1]) if coast and level != "good" else (i0, i1)
        out.append(finding("TRN_COAST", level, round(secs, 2), "<", c["coast_good_s"], a, b))
    if use("STR_PARTIAL"):
        straight_steer = cfg["phase"]["straight_steer_max_deg"]
        for a, b, secs in runs(rows, lambda r: s["partial_low"] <= (r["_s"]["throttle"] or 0) <= s["partial_high"]
                               and abs(r["_s"]["steer_deg"] or 0) < straight_steer, i0, i1):
            later = [r for r in rows[b:] if r["_t"] - rows[b]["_t"] <= 1.0]
            if secs >= s["partial_s"] and not any((r["_s"]["brake"] or 0) > cfg["phase"]["brake_on"] for r in later):
                out.append(finding("STR_PARTIAL", "bad", round(secs, 2), ">=", s["partial_s"], a, b))
    return out


def whole_lap(rows, cfg, use, corners, shift_rpm):
    """Rules that look across phases: shifts, the rev limiter, two minima in one corner, wheels out, invalid lap."""
    out, st, a = [], cfg["straight"], cfg["all"]
    if use("STR_SHIFT"):
        for i in range(1, len(rows)):
            g0, g1 = rows[i - 1]["gear"], rows[i]["gear"]
            if g0 is None or g1 is None or not (g1 == g0 + 1 and g0 >= 1):
                continue
            signal = shift_rpm.get(int(g0))
            rpm = rows[i - 1]["rpm"]
            if signal and rpm:
                off = round(rpm - signal)
                level = "good" if abs(off) <= st["shift_good_rpm"] else "potential"
                out.append(finding("STR_SHIFT", level, off, "|x|<=", st["shift_good_rpm"], max(0, i - 3), min(len(rows) - 1, i + 3)))
    if use("STR_LIMITER"):
        for x0, x1, secs in runs(rows, lambda r: bool(r.get("rev_limiter")), 0, len(rows) - 1):
            if secs > st["limiter_s"]:
                out.append(finding("STR_LIMITER", "bad", round(secs, 2), ">", st["limiter_s"], x0, x1))
    if use("APX_TWO_MINIMA"):
        rise = cfg["apex"]["two_minima_kmh"]
        half = max(1, round(0.5 * cfg["pipeline"]["hz"]))
        for c in corners:
            idx = [i for i, r in enumerate(rows) if r["_min"] and r["corner_id"] == c["corner_id"]]
            for a_i, b_i in zip(idx, idx[1:]):                # a real second slow-down: the speed rose in between
                between = max(rows[k]["_s"]["speed_kmh"] or 0 for k in range(a_i, b_i + 1))
                lift = round(between - max(rows[a_i]["_s"]["speed_kmh"] or 0, rows[b_i]["_s"]["speed_kmh"] or 0), 1)
                if lift >= rise:
                    out.append(finding("APX_TWO_MINIMA", "bad", lift, ">=", rise, max(0, b_i - half), min(len(rows) - 1, b_i + half)))
    if use("ALL_OFFTRACK"):
        for x0, x1, _ in runs(rows, lambda r: (r.get("wheels_out") or 0) > a["wheels_out_bad"], 0, len(rows) - 1):
            out.append(finding("ALL_OFFTRACK", "bad", max(rows[i]["wheels_out"] for i in range(x0, x1 + 1)), ">", a["wheels_out_bad"], x0, x1))
    if use("ALL_INVALID"):
        for i in range(1, len(rows)):
            if rows[i - 1].get("lap_valid") and rows[i].get("lap_valid") is False:
                t = rows[i]["_t"]
                near = [k for k, r in enumerate(rows) if abs(r["_t"] - t) <= a["invalid_window_s"]]
                out.append(finding("ALL_INVALID", "bad", 0, "==", 1, near[0], near[-1]))
    return out


def apply(rows, findings) -> None:
    """label = the worst level of the findings that cover a sample ("none" if none does); reasons lists them."""
    for r in rows:
        r["_found"] = []
    for f in findings:
        for i in range(f["i0"], f["i1"] + 1):
            rows[i]["_found"].append(f)
    for r in rows:
        found = r["_found"]
        if not found:
            r["label"], r["reasons"] = "none", ""
            continue
        worst = max(found, key=lambda f: LEVELS[f["level"]])
        r["label"] = worst["level"]
        r["reasons"] = "; ".join(f"{f['rule']} {f['level']} {f['value']} ({f['op']} {f['limit']})"
                                 for f in sorted(found, key=lambda f: -LEVELS[f["level"]]))


def analyse_lap(rows, cfg, envelope, reference, corners, seen, shift_rpm, label_pass: str) -> list:
    """The whole analysis of one lap; returns the findings (for corners.json). The rows get every derived column.
    corners None (no reference lap yet): the lap's own corners."""
    if not rows:
        return []
    derive(rows, cfg, envelope, reference)
    phases(rows, cfg, envelope)
    if corners is None:
        corners = corner_map(rows, cfg)
    for r in rows:
        r["corner_id"] = corner_of(corners, r["lap_dist_m"])
        r["label_pass"] = label_pass
    found = rules(rows, cfg, seen, reference, corners, shift_rpm)
    apply(rows, found)
    return found
