"""The coach's checks: value combinations that show good driving or room to improve (docs/COACHING.md, section 7).

Python decides, not the AI (owner, 18 November 2026): every check looks at one section of one lap and says
"yes", "no" or "n/a" (not enough data: no braking here, a straight, a game without slip values ...). A check of
the room-to-improve kind that says "yes" also says how clearly ("slight" or "clear"), where (metres from the
section start), what it saw, and roughly what it is worth.

Gentle on purpose (owner: estimates, not too harsh): every limit is relative to the car's own numbers in this
run (its peak grip at that speed, its own steering, its own best line), the margins are wide, a pattern must
last a few metres before it counts, and a time estimate is at most half of what the lap lost against BEST in
that stretch and never more than CAP_S. Without BEST there is no estimate at all.

Grip use is measured against grip_reference(): the car's combined-g peak in the same speed band (a downforce car
has less grip in slow corners), never below FLOOR of its overall peak (a band the car never pushed in would
otherwise count as "at the limit").

Input: the section rows of recorder.section ([d, t, v, thr, brk, str, g, x, y, tc_on, abs_on, esc_on, levels x5,
rpm, g_lat, g_long, yaw, body_slip, slip_angle_front, slip_angle_rear, slip_ratio_front, slip_ratio_rear,
wheels_out]); older laps have fewer columns, and missing values are None.
"""
import math

D, T, V, THR, BRK, STR = 0, 1, 2, 3, 4, 5
TC_ON, ABS_ON = 9, 10
GLAT, GLONG, BETA, SAF, SAR, SRF, SRR, OUT = 18, 19, 21, 22, 23, 24, 25, 26

CHECKS = {
    "G1": "braking at the limit in a straight line",
    "G2": "brake handed over to the steering (trail braking)",
    "G3": "at the limit and balanced in the middle",
    "G4": "throttle handed over from the steering on exit",
    "G5": "grip used wherever grip limits the speed",
    "G6": "consistent with the last lap",
    "B1": "not braking as hard as the car can",
    "B2": "slow first brake pressure",
    "B3": "overbraking: locking or ABS all the way",
    "B4": "coasting: no pedal",
    "B5": "brake off before turning in (no trail braking)",
    "E1": "entry understeer: braking hard while turning",
    "E2": "entry understeer: brake dropped at turn-in",
    "E3": "entry oversteer",
    "E4": "more steering than BEST, no more grip",
    "M1": "not committed in the middle",
    "M2": "mid-corner understeer: scrubbing speed",
    "M3": "car unsettled: steering corrections",
    "M4": "long minimum in a slow corner",
    "X1": "late throttle",
    "X2": "power understeer: running wide",
    "X3": "power oversteer",
    "X4": "throttle lifted again after the pick-up",
    "X5": "exit not used",
    "L1": "wheels out with time gained (a kerb)",
    "L2": "wheels out with time lost",
    "L5": "TC cutting more than needed",
    "L6": "leaning on ABS into the corner",
}
GOOD = ("G1", "G2", "G3", "G4", "G5", "G6")

# wide margins, all relative to the car where possible
HIGH_GRIP = 0.85          # share of the car's peak combined g that counts as "at the limit"
LOW_GRIP = 0.72           # below this, grip is clearly left unused
CLEAR_LOW_GRIP = 0.60
LOCK = -0.25              # front slip ratio well past any ABS / tyre peak (they start around -0.06 .. -0.12)
SPIN = 0.25               # rear slip ratio well past the traction peak
STRONG_BAL = 0.5          # the sliding end slides at least 50 % more than the other one ...
MIN_BAL_DEG = 1.5         # ... and by at least this many degrees
STEER_ON = 0.10           # steering that counts as turning (share of full lock)
MIN_M = 8.0               # a pattern must last this long to count
CAP_S = 0.3               # the most a single check may claim
STRAIGHT_DEG = 15.0
FLOOR = 0.6               # the grip reference never drops below this share of the car's overall peak
LIFT = 0.3                # a throttle drop of this much below its peak counts as a lift ...
LIFT_M = 5.0              # ... when it lasts this long


def grip_reference(limits: dict | None, kmh) -> float | None:
    """The car's combined g to measure grip use against at this speed (Peaks.public in core/recorder.py)."""
    if not limits or not limits.get("combined_g"):
        return None
    overall = limits["combined_g"]
    bands = {}
    for key, g in (limits.get("combined_by_speed") or {}).items():
        low, high = (float(x) for x in key.split("-"))
        bands[(low, high)] = g
    if not bands:
        return overall
    band = next((g for (low, high), g in bands.items() if kmh is not None and low <= kmh < high), None)
    if band is None and kmh is not None:                       # no peak at this speed: the nearest band below, else above
        below = [(low, g) for (low, _), g in bands.items() if low <= kmh]
        above = [(low, g) for (low, _), g in bands.items() if low > kmh]
        band = max(below)[1] if below else min(above)[1] if above else None
    return max(band or 0.0, FLOOR * overall)


def _v(row, i):
    return row[i] if len(row) > i else None


def _metres(rows, test) -> tuple[float, float | None, float | None]:
    """(metres where test(row) holds, start and end of its longest continuous stretch): the place to name."""
    total, best, start, length = 0.0, (None, None, 0.0), None, 0.0
    for a, b in zip(rows, rows[1:]):
        if test(a):
            total += b[D] - a[D]
            start = a[D] if start is None else start
            length += b[D] - a[D]
            if length > best[2]:
                best = (start, b[D], length)
        else:
            start, length = None, 0.0
    return total, best[0], best[1]


def _interp(rows, i, at):
    pts = [(r[D], r[i]) for r in rows if _v(r, i) is not None]
    if not pts:
        return None
    if at <= pts[0][0]:
        return pts[0][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= at <= d1:
            return v0 if d1 == d0 else v0 + (v1 - v0) * (at - d0) / (d1 - d0)
    return pts[-1][1]


def _median(values):
    values = sorted(v for v in values if v is not None)
    return values[len(values) // 2] if values else None


class Section:
    """One line through one section, with what the checks need worked out once."""

    def __init__(self, rows, best_rows, last_rows, turn, limits, trace, kind=None):
        self.rows, self.best, self.last = rows, best_rows or [], last_rows or []
        self.corner = abs(math.degrees(turn or 0.0)) >= STRAIGHT_DEG
        self.kind = kind
        self.limits = limits
        self.trace = trace or []
        steer = [abs(r[STR]) for r in rows]
        self.steer_max = max(steer) if steer else 0.0
        side = [r[STR] for r in rows if abs(r[STR]) > STEER_ON]
        self.sign = 1 if sum(side) >= 0 else -1               # the way this corner is steered (no sign convention needed)
        self.low = min(range(len(rows)), key=lambda k: rows[k][V])
        self.min_at = rows[self.low][D]
        self.brake_on = next((k for k, r in enumerate(rows) if r[BRK] > 0.1), None)
        self.has_grip = bool(limits) and any(_v(r, GLAT) is not None and _v(r, GLONG) is not None for r in rows)
        self.has_bal = any(_v(r, SAF) is not None and _v(r, SAR) is not None for r in rows)
        self.has_slip = any(_v(r, SRF) is not None for r in rows)

    def grip(self, r):
        if not self.has_grip or _v(r, GLAT) is None or _v(r, GLONG) is None:
            return None
        ref = grip_reference(self.limits, r[V])
        return math.hypot(r[GLAT], r[GLONG]) / ref if ref else None

    def bal(self, r):
        """+1 strong understeer, -1 strong oversteer, 0 balanced or unknown."""
        f, b = _v(r, SAF), _v(r, SAR)
        if f is None or b is None:
            return 0
        if f - b >= MIN_BAL_DEG and f >= b * (1 + STRONG_BAL):
            return 1
        if b - f >= MIN_BAL_DEG and b >= f * (1 + STRONG_BAL):
            return -1
        return 0

    def counter(self, r):
        """Steering against the way the corner is steered, with the car sliding: catching oversteer. Not in a
        chicane, where steering the other way is the corner itself."""
        if self.kind == "chicane" or r[STR] * self.sign >= -0.05:
            return False
        beta, rear = _v(r, BETA), _v(r, SRR)
        if beta is None and rear is None and _v(r, SAF) is None:
            return True                                       # nothing else to go by
        return self.bal(r) < 0 or (beta is not None and abs(beta) > 3) or (rear is not None and rear > 0.15)

    def loss(self, a, b):
        """Seconds lost against BEST between a and b metres, or None without BEST."""
        if len(self.best) < 2 or a is None or b is None:
            return None
        tn = [_interp(self.rows, T, x) for x in (a, b)]
        tb = [_interp(self.best, T, x) for x in (a, b)]
        if None in tn or None in tb:
            return None
        return (tn[1] - tb[1]) - (tn[0] - tb[0])

    def estimate(self, a, b):
        lost = self.loss(max(0.0, (a or 0) - 10), (b or 0) + 10)
        if lost is None or lost <= 0.02:
            return None
        return round(min(CAP_S, lost * 0.5) * 20) / 20 or None   # half of the loss, in 0.05 s steps


def _yes(sec, strength, a, b, note):
    end = sec.rows[-1][D]
    a = None if a is None else min(max(0.0, a), end)
    b = None if b is None else min(max(0.0, b), end)
    out = {"result": "yes", "strength": strength, "from_m": None if a is None else round(a),
           "to_m": None if b is None else round(b), "note": note}
    est = sec.estimate(a, b)
    if est:
        out["est_s"] = est
    return out


def _good(result, note=""):
    return {"result": result, "note": note} if note else {"result": result}


NO, NA = {"result": "no"}, {"result": "n/a"}


# ---------------------------------------------------------------- good driving

def g1(s):
    zone = [r for r in s.rows if r[BRK] > 0.5]
    if not s.has_grip or len(zone) < 3:
        return NA
    straight = [r for r in zone if abs(r[STR]) < STEER_ON] or zone
    level = _median(s.grip(r) for r in straight)
    locked = any(_v(r, SRF) is not None and r[SRF] < LOCK for r in zone)
    if level is None:
        return NA
    note = f"{level * 100:.0f} % grip under braking"
    if level >= HIGH_GRIP and not locked:
        return _good("yes", note)
    return _good("partly" if level >= LOW_GRIP and not locked else "no", note + (", a wheel locked" if locked else ""))


def g2(s):
    if not s.corner or s.brake_on is None:
        return NA
    overlap, a, b = _metres(s.rows, lambda r: r[BRK] > 0.05 and abs(r[STR]) > STEER_ON)
    if overlap < MIN_M:
        return _good("no", f"{overlap:.0f} m of brake and steering together")
    dip = min((s.grip(r) for r in s.rows if a <= r[D] <= b and s.grip(r) is not None), default=None)
    if dip is not None and dip < LOW_GRIP:
        return _good("partly", f"{overlap:.0f} m overlap, grip dips to {dip * 100:.0f} %")
    return _good("yes", f"{overlap:.0f} m overlap")


def _middle(s):
    return [r for r in s.rows if abs(r[D] - s.min_at) <= 30 and abs(r[STR]) > STEER_ON and r[BRK] < 0.05]


def g3(s):
    mid = _middle(s)
    if not s.corner or len(mid) < 3 or not s.has_grip:
        return NA
    level = _median(s.grip(r) for r in mid)
    strong = sum(1 for r in mid if s.bal(r)) / len(mid)
    if level is None:
        return NA
    note = f"{level * 100:.0f} % grip in the middle"
    if level >= HIGH_GRIP and strong < 0.3:
        return _good("yes", note)
    return _good("partly" if level >= LOW_GRIP else "no", note + (", balance off" if strong >= 0.3 else ""))


def _pickup(s):
    return next((k for k in range(s.low, len(s.rows)) if s.rows[k][THR] > 0.1), None)


def _lifts(s, start):
    """Places where the throttle fell clearly (LIFT) below its peak since the pick-up and stayed down LIFT_M."""
    peak, drops, down_at = 0.0, [], None
    for r in s.rows[start:]:
        if down_at is None:
            peak = max(peak, r[THR])
            if peak > 0.3 and r[THR] < peak - LIFT:
                down_at = r[D]
        elif r[THR] >= peak - LIFT / 3:                       # back up: one lift, if it lasted
            if r[D] - down_at >= LIFT_M:
                drops.append(down_at)
            down_at, peak = None, r[THR]
    if down_at is not None and s.rows[-1][D] - down_at >= LIFT_M:
        drops.append(down_at)
    return drops


def g4(s):
    k = _pickup(s)
    if not s.corner or k is None:
        return NA
    exit_rows = [r for r in s.rows[k:] if abs(r[STR]) > STEER_ON]
    if len(exit_rows) < 3:
        return _good("yes", "throttle on once the steering is straight")
    opening = exit_rows[-1][STR] * s.sign <= exit_rows[0][STR] * s.sign + 0.02
    lifts = _lifts(s, k)
    spin = any(_v(r, SRR) is not None and r[SRR] > SPIN for r in s.rows[k:])
    level = _median(s.grip(r) for r in exit_rows) if s.has_grip else None
    good = opening and not lifts and not spin and (level is None or level >= LOW_GRIP)
    note = "" if level is None else f"{level * 100:.0f} % grip on exit"
    return _good("yes" if good else "partly" if opening else "no", note)


def g5(s):
    limited = [s.grip(r) for r in s.rows if (r[BRK] > 0.1 or abs(r[STR]) > STEER_ON) and s.grip(r) is not None]
    if len(limited) < 5:
        return NA
    share = sum(1 for g in limited if g >= HIGH_GRIP) / len(limited)
    note = f"{share * 100:.0f} % of braking and cornering near the limit"
    return _good("yes" if share >= 0.6 else "partly" if share >= 0.35 else "no", note)


def g6(s):
    if len(s.last) < 2:
        return NA
    def key(rows):
        on = next((r[D] for r in rows if r[BRK] > 0.1), None)
        return on, min(r[V] for r in rows)
    (on_n, low_n), (on_l, low_l) = key(s.rows), key(s.last)
    same_brake = (on_n is None) == (on_l is None) and (on_n is None or abs(on_n - on_l) <= 8)
    if same_brake and abs(low_n - low_l) <= 4:
        return _good("yes")
    return _good("no", f"braking point {on_l if on_l is None else round(on_l)} -> {on_n if on_n is None else round(on_n)} m, "
                       f"minimum {low_l:.0f} -> {low_n:.0f} km/h")


# ---------------------------------------------------------------- braking

def b1(s):
    zone = [r for r in s.rows if r[BRK] > 0.2]
    if not s.has_grip or len(zone) < 5 or zone[-1][D] - zone[0][D] < 15:
        return NA
    level = _median(s.grip(r) for r in zone)
    abs_used = any(_v(r, ABS_ON) for r in zone)
    slip = min((r[SRF] for r in zone if _v(r, SRF) is not None), default=None)
    if level is None or level >= LOW_GRIP or abs_used or (slip is not None and slip < -0.08):
        return NO
    return _yes(s, "clear" if level < CLEAR_LOW_GRIP else "slight", zone[0][D], zone[-1][D],
                f"{level * 100:.0f} % grip while braking, ABS not used")


def b2(s):
    if s.brake_on is None:
        return NA
    peak = max(r[BRK] for r in s.rows)
    if peak < 0.5:
        return NA
    t0 = s.rows[s.brake_on][T]
    reach = next((r for r in s.rows[s.brake_on:] if r[BRK] >= 0.9 * peak), None)
    took = reach[T] - t0 if reach else 0.0
    if took <= 0.4:
        return NO
    return _yes(s, "clear" if took > 0.7 else "slight", s.rows[s.brake_on][D], reach[D],
                f"{took:.1f} s to full brake pressure")


def b3(s):
    if s.brake_on is None:
        return NA
    lock, a, b = _metres(s.rows, lambda r: _v(r, SRF) is not None and r[SRF] < LOCK)
    zone, za, zb = _metres(s.rows, lambda r: r[BRK] > 0.2)
    on, _, _ = _metres(s.rows, lambda r: r[BRK] > 0.2 and _v(r, ABS_ON))
    if lock >= 3:
        worst = min(r[SRF] for r in s.rows if _v(r, SRF) is not None)
        return _yes(s, "clear" if worst <= -0.9 else "slight", a, b, f"front slip down to {worst * 100:.0f} %")
    if zone >= 30 and on >= 0.9 * zone:
        return _yes(s, "slight", za, zb, "ABS working through the whole braking zone")
    return NO if (s.has_slip or any(_v(r, ABS_ON) is not None for r in s.rows)) else NA


def b4(s):
    if not s.corner and s.brake_on is None:
        return NA
    coast, a, b = _metres(s.rows, lambda r: r[THR] < 0.1 and r[BRK] < 0.1)
    fast = s.kind == "fast corner"                            # a short lift in a fast corner is a technique, not a fault
    if coast < (25 if fast else 10):
        return NO
    return _yes(s, "clear" if coast > 25 and not fast else "slight", a, b, f"{coast:.0f} m with no pedal")


def b5(s):
    if not s.corner or s.brake_on is None:
        return NA
    off = next((r[D] for r in s.rows[s.brake_on:] if r[BRK] < 0.05), None)
    turn = next((r[D] for r in s.rows[s.brake_on:] if abs(r[STR]) > STEER_ON), None)
    if off is None or turn is None or turn - off < 10:
        return NO
    return _yes(s, "clear" if turn - off > 25 else "slight", off, turn, f"brake off {turn - off:.0f} m before turning in")


# ---------------------------------------------------------------- entry

def _entry(s):
    return [r for r in s.rows if r[D] <= s.min_at]


def e1(s):
    if not s.corner or not s.has_bal:
        return NA
    m, a, b = _metres(_entry(s), lambda r: r[BRK] > 0.3 and abs(r[STR]) > 1.5 * STEER_ON and s.bal(r) > 0
                      and (_v(r, SRF) is None or r[SRF] < -0.12))
    if m < MIN_M:
        return NO
    return _yes(s, "clear" if m > 25 else "slight", a, b, f"front sliding for {m:.0f} m while braking and turning")


def e2(s):
    if not s.corner or s.brake_on is None or not s.has_bal:
        return NA
    rows = s.rows
    for k in range(s.brake_on, len(rows) - 1):
        if rows[k][BRK] >= 0.3:
            drop = next((j for j in range(k + 1, len(rows)) if rows[j][BRK] < 0.05), None)
            if drop is None or rows[drop][D] - rows[k][D] > 6:
                continue
            after = [r for r in rows[drop:] if r[D] - rows[drop][D] <= 30]
            turning = any(abs(r[STR]) > STEER_ON for r in after)
            push, a, b = _metres(after, lambda r: s.bal(r) > 0)
            if turning and push >= MIN_M:
                return _yes(s, "slight", rows[k][D], b, f"brake released within {rows[drop][D] - rows[k][D]:.0f} m, "
                                                         f"then the front slides for {push:.0f} m")
    return NO


def e3(s):
    if not s.corner:
        return NA
    entry = _entry(s)
    loose, a, b = _metres(entry, lambda r: (r[BRK] > 0.05 or r[THR] < 0.1) and
                          (s.bal(r) < 0 or s.counter(r) or (_v(r, BETA) is not None and abs(r[BETA]) > 5)))
    if loose < 4:
        return NO if (s.has_bal or any(_v(r, BETA) is not None for r in entry)) else NA
    return _yes(s, "clear" if loose > 15 else "slight", a, b, f"the rear steps out for {loose:.0f} m on entry")


def e4(s):
    if not s.corner or len(s.best) < 2:
        return NA
    at = s.min_at
    mine, theirs = abs(_interp(s.rows, STR, at) or 0), abs(_interp(s.best, STR, at) or 0)
    if theirs < STEER_ON or mine < theirs * 1.25:
        return NO
    gm = s.grip(min(s.rows, key=lambda r: abs(r[D] - at)))
    sb = Section(s.best, None, None, 0, s.limits, None)
    gb = sb.grip(min(s.best, key=lambda r: abs(r[D] - at)))
    if gm is not None and gb is not None and gm > gb + 0.03:
        return NO
    return _yes(s, "slight", at - 20, at + 20, f"{mine * 100:.0f} % steering at the apex, BEST {theirs * 100:.0f} %")


# ---------------------------------------------------------------- middle

def m1(s):
    mid = _middle(s)
    if not s.corner or len(mid) < 3 or not s.has_grip or len(s.best) < 2:
        return NA
    level = _median(s.grip(r) for r in mid)
    best_low = min(r[V] for r in s.best)
    slower = best_low - s.rows[s.low][V]
    if level is None or level >= LOW_GRIP or slower < 3 or any(s.bal(r) for r in mid):
        return NO
    return _yes(s, "clear" if level < CLEAR_LOW_GRIP else "slight", mid[0][D], mid[-1][D],
                f"{level * 100:.0f} % grip, minimum {slower:.0f} km/h below BEST")


def m2(s):
    if not s.corner or not s.has_bal:
        return NA
    rows = s.rows
    scrub, a, b = _metres(rows, lambda r: s.bal(r) > 0 and r[BRK] < 0.05 and r[THR] < 0.3 and abs(r[STR]) > STEER_ON)
    if scrub < MIN_M:
        return NO
    lost = (_interp(rows, V, a) or 0) - (_interp(rows, V, b) or 0)
    if lost < 2:
        return NO
    return _yes(s, "clear" if lost > 8 else "slight", a, b, f"front sliding for {scrub:.0f} m, {lost:.0f} km/h scrubbed off")


def m3(s):
    if not s.corner:
        return NA
    turning = [r for r in s.rows if abs(r[STR]) > STEER_ON]
    if len(turning) < 6:
        return NA
    flips, last_dir, ref = 0, 0, turning[0][STR]
    for r in turning[1:]:
        step = r[STR] - ref
        if abs(step) >= 0.04:
            direction = 1 if step > 0 else -1
            if last_dir and direction != last_dir:
                flips += 1
            last_dir, ref = direction, r[STR]
    if flips < 3:
        return NO
    return _yes(s, "clear" if flips >= 5 else "slight", turning[0][D], turning[-1][D], f"{flips} steering corrections")


def m4(s):
    if not s.corner:
        return NA
    low = s.rows[s.low][V]
    entry = s.rows[0][V]
    if low > 110 or entry - low < 30:                         # a slow corner after real braking
        return NA
    flat, a, b = _metres(s.rows, lambda r: r[V] - low <= 2)
    level = _median(s.grip(r) for r in s.rows if a is not None and a <= r[D] <= b) if s.has_grip else None
    if flat < 30 or (level is not None and level >= HIGH_GRIP):
        return NO
    return _yes(s, "slight", a, b, f"{flat:.0f} m within 2 km/h of the minimum")


# ---------------------------------------------------------------- exit

def x1(s):
    if not s.corner or s.steer_max < 2 * STEER_ON:
        return NA
    after = s.rows[s.low:]
    late, a, b = _metres(after, lambda r: abs(r[STR]) < 0.8 * s.steer_max and r[THR] < 0.2 and r[BRK] < 0.05)
    if late < 15:
        return NO
    return _yes(s, "clear" if late > 35 else "slight", a, b, f"steering opening, throttle under 20 % for {late:.0f} m")


def x2(s):
    if not s.corner:
        return NA
    after = s.rows[s.low:]
    wide, a, b = _metres(after, lambda r: r[THR] > 0.5 and abs(r[STR]) >= 0.8 * s.steer_max and s.bal(r) > 0)
    out_end = any(_v(r, OUT) for r in after[-max(1, len(after) // 3):])
    if not s.has_bal:
        return NA
    if wide < MIN_M:
        return NO
    return _yes(s, "clear" if out_end or wide > 25 else "slight", a, b,
                f"throttle with full steering and the front sliding for {wide:.0f} m" + (", wheels out at the exit" if out_end else ""))


def x3(s):
    if not s.corner:
        return NA
    after = s.rows[s.low:]
    spin, a, b = _metres(after, lambda r: (_v(r, SRR) is not None and r[SRR] > SPIN) or s.counter(r) or
                         (r[THR] > 0.3 and s.bal(r) < 0))
    tc, ta, tb = _metres(after, lambda r: _v(r, TC_ON))
    if spin >= 4:
        return _yes(s, "clear" if spin > 15 else "slight", a, b, f"the rear steps out or spins for {spin:.0f} m on exit")
    if tc >= 20 and any(s.counter(r) or (_v(r, BETA) is not None and abs(r[BETA]) > 4) for r in after):
        return _yes(s, "slight", ta, tb, f"TC working {tc:.0f} m with the car sideways")
    return NO if (s.has_slip or s.has_bal or any(_v(r, TC_ON) is not None for r in after)) else NA


def x4(s):
    k = _pickup(s)
    if k is None:
        return NA
    drops = _lifts(s, k)
    if not drops:
        return NO
    return _yes(s, "slight", drops[0] - 10, drops[-1] + 10, f"throttle lifted {len(drops)} time(s) after the pick-up")


def x5(s):
    if not s.corner or len(s.best) < 2:
        return NA
    offs = [p[5] for p in s.trace[-4:] if len(p) > 5 and p[5] is not None]
    if not offs:
        return NA
    inside = sum(offs) / len(offs)
    end = s.rows[-1][D]
    mine, theirs = _interp(s.rows, V, end - 20), _interp(s.best, V, end - 20)
    if inside < 1.5 or mine is None or theirs is None or theirs - mine < 3:
        return NO
    return _yes(s, "slight", end - 40, end, f"{inside:.1f} m inside the BEST line at the exit, {theirs - mine:.0f} km/h slower")


# ---------------------------------------------------------------- limits and aids

def _out(s):
    if not any(_v(r, OUT) is not None for r in s.rows):
        return None
    return _metres(s.rows, lambda r: _v(r, OUT))


def l1(s):
    got = _out(s)
    if got is None:
        return NA
    m, a, b = got
    lost = s.loss(a, b) if m >= 3 else None
    if m < 3 or lost is None or lost > -0.01:
        return NO
    return {"result": "yes", "from_m": round(a), "to_m": round(b), "note": f"{m:.0f} m with wheels out, {-lost:.2f} s gained"}


def l2(s):
    got = _out(s)
    if got is None:
        return NA
    m, a, b = got
    if m < 3:
        return NO
    lost = s.loss(a, b)
    sideways = any(_v(r, BETA) is not None and abs(r[BETA]) > 4 for r in s.rows if a <= r[D] <= b)
    if (lost is not None and lost > 0.03) or sideways:
        return _yes(s, "slight", a, b, f"{m:.0f} m with wheels out" + (", the car sideways" if sideways else ""))
    return NO


def l5(s):
    tc, a, b = _metres(s.rows, lambda r: _v(r, TC_ON))
    if tc == 0 and not any(_v(r, TC_ON) is not None for r in s.rows):
        return NA
    slip = max((r[SRR] for r in s.rows if _v(r, SRR) is not None and _v(r, TC_ON)), default=None)
    if tc < 20 or slip is None or slip > 0.08:
        return NO
    return _yes(s, "slight", a, b, f"TC working {tc:.0f} m with only {slip * 100:.0f} % rear slip")


def l6(s):
    if not s.corner or not any(_v(r, ABS_ON) is not None for r in s.rows):
        return NA
    turning = [r for r in _entry(s) if abs(r[STR]) > 1.5 * STEER_ON and r[BRK] > 0.2]
    on = [r for r in turning if _v(r, ABS_ON)]
    if len(on) < 4 or len(on) < 0.7 * len(turning) or not any(s.bal(r) > 0 for r in on):
        return NO
    return _yes(s, "slight", on[0][D], on[-1][D], "ABS working while turning in, the front sliding")


RULES = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "B1": b1, "B2": b2, "B3": b3, "B4": b4,
         "B5": b5, "E1": e1, "E2": e2, "E3": e3, "E4": e4, "M1": m1, "M2": m2, "M3": m3, "M4": m4, "X1": x1,
         "X2": x2, "X3": x3, "X4": x4, "X5": x5, "L1": l1, "L2": l2, "L5": l5, "L6": l6}


def evaluate(rows, best_rows=None, last_rows=None, corner: dict | None = None, limits: dict | None = None,
             trace: list | None = None) -> dict:
    """{code: result} for every check (CHECKS) on one line through one section. corner: the section's shape
    (trainer.corner_facts), limits: the car's grip (recorder Peaks.public), trace: the trainer's trace (for the
    line offset at the exit)."""
    if not rows or len(rows) < 4:
        return {}
    corner = corner or {}
    s = Section(rows, best_rows, last_rows, corner.get("turn", 0.0), limits, trace, corner.get("type"))
    return {code: rule(s) for code, rule in RULES.items()}


def brief(results: dict, found_only: bool = False) -> dict:
    """The results as short strings for the AI and the report: "yes", "no", "partly · 78 % grip ...",
    "yes · slight · 60-80 m · about 0.10 s · 18 m with no pedal". Checks that do not apply are left out;
    found_only (for the AI): of the room-to-improve checks only those that found something."""
    out = {}
    for code, r in results.items():
        if r["result"] == "n/a" or (found_only and code not in GOOD and r["result"] != "yes"):
            continue
        parts = [r["result"]]
        if r.get("strength"):
            parts.append(r["strength"])
        if r.get("from_m") is not None:
            parts.append(f"{r['from_m']}-{r['to_m']} m")
        if r.get("est_s"):
            parts.append(f"about {r['est_s']:.2f} s")
        if r.get("note") and (r["result"] != "no" or code in GOOD):
            parts.append(r["note"])
        out[code] = " · ".join(parts)
    return out
