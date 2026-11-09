"""Demo connector: a simulated car, so the pages can be tried without a game (any OS).

The car drives laps on a made-up track (straights and corners), shifts by itself near the shift
point, uses fuel and sets lap times. The buttons act on the simulated car: TC, ABS, brake bias,
engine map, pit limiter, lights, wipers, ignition; with AUTO SHIFT off you shift with SHIFT + / -.
"""
import math
import random
import time

import actions
import telemetry

RPM_MAX = 8200
BOOST_MAX = 1.6          # the demo car has a turbo: bar at full throttle and high rpm
RPM_IDLE = 1100
SHIFT_PCT = 0.94                         # the "game's" shift point
RATIOS = [0, 3.3, 2.3, 1.75, 1.4, 1.15, 0.97]   # km/h -> rpm factor per gear, scaled below
SPEED_RPM = 30.0                         # rpm per km/h at ratio 1.0
FUEL_MAX = 60.0
PIT_LIMIT_KMH = 60.0
GEARS = len(RATIOS) - 1


# The demo track: a closed curve through these points (metres), about 4.9 km. Its corner speeds come
# from the curvature, braking zones from a backward pass, so the car brakes before the corners.
TRACK_POINTS = [(300, 560), (120, 520), (60, 400), (110, 280), (40, 140), (0, 0), (320, 0), (440, 30), (480, 130),
                (420, 230), (310, 250), (260, 320), (330, 410), (480, 430), (560, 370), (600, 250), (700, 190),
                (770, 250), (750, 420), (600, 540)]
TRACK_SCALE = 1.6
BRAKE_MS2 = 11.0
GRIP_MS2 = 17.0


def build_track(points, per_segment=60):
    """Centre line (x, y), cumulative distance, smoothed curvature, normals and a target speed profile."""
    pts = [(x * TRACK_SCALE, y * TRACK_SCALE) for x, y in points]
    m, line = len(pts), []
    for i in range(m):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % m], pts[(i + 2) % m]
        for k in range(per_segment):
            t = k / per_segment
            line.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                     + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    n = len(line)
    dist = [0.0]
    for i in range(1, n + 1):
        a, b = line[i - 1], line[i % n]
        dist.append(dist[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    heading = [math.atan2(line[(i + 1) % n][1] - line[i][1], line[(i + 1) % n][0] - line[i][0]) for i in range(n)]
    curv = []
    for i in range(n):
        da = heading[(i + 1) % n] - heading[i - 1]
        da = math.atan2(math.sin(da), math.cos(da))
        curv.append(da / max(1e-6, dist[i + 1] - dist[max(0, i - 1)]))
    for width in (12, 8):                                   # smooth twice
        curv = [sum(curv[(i + k) % n] for k in range(-width, width + 1)) / (2 * width + 1) for i in range(n)]
    normals = [(-math.sin(h), math.cos(h)) for h in heading]
    v = [min(78.0, math.sqrt(GRIP_MS2 / max(1e-5, abs(c)))) for c in curv]
    for _ in range(2):                                      # braking zones, around the loop twice
        for i in range(2 * n - 1, -1, -1):
            a, b = i % n, (i + 1) % n
            v[a] = min(v[a], math.sqrt(v[b] ** 2 + 2 * BRAKE_MS2 * (dist[a + 1] - dist[a])))
    return {"line": line, "dist": dist, "curv": curv, "normals": normals, "speed": [x * 3.6 for x in v], "n": n}


TRACK = build_track(TRACK_POINTS)
LAP_M = TRACK["dist"][-1]
KMAX = max(abs(c) for c in TRACK["curv"])


def track_index(pos: float) -> int:
    return min(TRACK["n"] - 1, int(pos * TRACK["n"]))


def target_speed(pos: float) -> float:
    """Wanted speed in km/h at a track position 0..1."""
    return min(285.0, TRACK["speed"][track_index(pos)])


def lap_form(nodes: int = 24) -> list[float]:
    """How well each part of a lap goes: speed factors (0.95..1.03) at evenly spaced points, new every lap,
    so the analysis page has faster and slower sections to show."""
    return [random.uniform(0.95, 1.03) for _ in range(nodes)]


def form_at(form: list[float], pos: float) -> float:
    x = pos * len(form)
    i = int(x) % len(form)
    f = x - int(x)
    f = f * f * (3 - 2 * f)                       # smooth between the points
    return form[i] + (form[(i + 1) % len(form)] - form[i]) * f


MODES = ("COMFORT", "SPORT", "SPORT+")     # the demo car's drive modes

class Connector(telemetry.Connector):
    HANDLES = tuple(actions.BY_NAME)

    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.last = time.monotonic()
        self.pos = 0.0
        self.session = f"demo-{int(time.time())}"
        self.line_phase = random.random()          # each lap takes a slightly different line
        self.form = lap_form()                     # and is a bit faster or slower in places
        self.speed = 0.0
        self.gear = 1
        self.shift_until = 0.0
        self.boost = 0.0
        self.lap_start = self.last
        self.lap = 0
        self.last_ms = None
        self.best_ms = None
        self.fuel = 42.0
        self.coolant = 35.0                      # starts cold: blue lamp until about 50 C
        self.state = {"tc_level": 3, "tc_cut_level": 2, "abs_level": 2, "brake_bias": 0.565, "engine_map": 1, "pit_limiter": False,
                      "drive_mode": 1,
                      "lights": 0, "wipers": 0, "ignition": True, "engine_running": True, "auto_shifter": True}

    def tyres(self, brake: float = 0.0) -> dict:
        """Tyres that warm up while driving: fronts hotter than rears, the left side a little more."""
        warm = min(1.0, self.speed / 180.0)
        base = [72 + 26 * warm, 70 + 22 * warm, 64 + 18 * warm, 62 + 16 * warm]
        temps = [round(t + random.uniform(-0.6, 0.6), 1) for t in base]
        psi = [round(26.0 + (t - 60) * 0.045, 1) for t in temps]
        self.brakes = getattr(self, "brakes", [80.0, 80.0, 70.0, 70.0])
        heat = [5.0 * brake, 5.0 * brake, 3.5 * brake, 3.5 * brake]          # brakes heat up when used, cool down slowly
        self.brakes = [max(60.0, b * 0.997 + h) for b, h in zip(self.brakes, heat)]
        return {"tyre_temp_c": temps, "tyre_psi": psi, "brake_temp_c": [round(b) for b in self.brakes]}

    def handle(self, action: str, state: str) -> bool:
        s = self.state
        if state == "up":
            return True
        steps = {"tc_up": ("tc_level", 1, 0, 11), "tc_down": ("tc_level", -1, 0, 11),
                 "tc_cut_up": ("tc_cut_level", 1, 0, 8), "tc_cut_down": ("tc_cut_level", -1, 0, 8),
                 "abs_up": ("abs_level", 1, 0, 12), "abs_down": ("abs_level", -1, 0, 12),
                 "map_up": ("engine_map", 1, 1, 5), "map_down": ("engine_map", -1, 1, 5),
                 "drive_mode_up": ("drive_mode", 1, 0, 2), "drive_mode_down": ("drive_mode", -1, 0, 2),
                 "bias_front": ("brake_bias", 0.005, 0.45, 0.7), "bias_rear": ("brake_bias", -0.005, 0.45, 0.7)}
        if action in steps and s.get(steps[action][0]) is not None:
            name, step, low, high = steps[action]
            s[name] = round(min(high, max(low, s[name] + step)), 3)
        elif action == "auto_shifter":
            s["auto_shifter"] = not s["auto_shifter"]      # off: SHIFT + / - shift the demo car
        elif action in ("pit_limiter", "ignition"):
            s[action] = not s[action]
            if action == "ignition" and not s["ignition"]:
                s["engine_running"] = False
        elif action == "starter" and s["ignition"]:
            s["engine_running"] = True
        elif action == "lights":
            s["lights"] = (s["lights"] + 1) % 3
        elif action == "wipers":
            s["wipers"] = (s["wipers"] + 1) % 4
        elif action == "shift_up" and not s["auto_shifter"]:
            self.shift(min(GEARS, self.gear + 1))
        elif action == "shift_down" and not s["auto_shifter"]:
            self.shift(max(-1, self.gear - 1))
        elif action == "neutral":
            self.shift(0)
        return True

    def shift(self, gear: int) -> None:
        self.gear = gear
        self.shift_until = time.monotonic() + 0.12

    def warnings(self, running: bool) -> dict:
        """Lamps of the demo car: it warms up from cold; engine map 5 makes it overheat (yellow, then red)."""
        s = self.state
        target = 35.0 if not running else 92.0 + (34.0 if s["engine_map"] >= 5 else 0.0)
        self.coolant += (target - self.coolant) * 0.0015
        if not s["ignition"]:
            return {"warn_brake": "off", "warn_engine": "off", "warn_oil": "off", "warn_coolant": "off"}
        coolant = "alert" if self.coolant >= 118 else "warn" if self.coolant >= 108 else "cold" if self.coolant < 50 else "off"
        return {"warn_brake": "off", "warn_engine": "off" if running else "warn",
                "warn_oil": "off" if running else "alert", "warn_coolant": coolant}

    def rpm_for(self, gear: int) -> float:
        if gear <= 0:
            return RPM_IDLE
        return max(RPM_IDLE, self.speed * SPEED_RPM * RATIOS[gear] * 1.0)

    def read(self) -> dict:
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        s = self.state
        running = s["engine_running"]
        drive = running and self.gear > 0 and now >= self.shift_until
        want = target_speed(self.pos) * form_at(self.form, self.pos)
        if s["pit_limiter"]:
            want = min(want, PIT_LIMIT_KMH)
        rpm = self.rpm_for(self.gear)
        limiter = rpm >= RPM_MAX
        gas = brake = 0.0
        if self.speed < want - 2 and drive and not limiter:
            gas = 1.0 if want - self.speed > 15 else 0.6
            power = 1.0 + 0.04 * (s["engine_map"] - 1)
            self.speed += dt * gas * power * max(4.0, 26 - self.speed / 13) * (1.3 if self.gear <= 2 else 1.0)
        elif self.speed > want + 2:
            brake = 1.0 if self.speed - want > 25 else 0.5
            self.speed -= dt * brake * 48
        else:
            self.speed -= dt * 1.5
        self.speed = max(0.0, self.speed)
        if running and self.gear > 0:
            rpm = min(RPM_MAX, self.rpm_for(self.gear))
        elif running:
            rpm = RPM_IDLE + random.uniform(-20, 20)
        else:
            rpm = 0
        if s["auto_shifter"] and running and now >= self.shift_until:
            if self.gear < GEARS and rpm >= RPM_MAX * SHIFT_PCT and gas > 0:
                self.shift(self.gear + 1)
            elif self.gear > 1 and self.rpm_for(self.gear - 1) < RPM_MAX * 0.7 and brake > 0:
                self.shift(self.gear - 1)
            elif self.gear <= 0:
                self.shift(1)
        self.pos += self.speed / 3.6 * dt / LAP_M
        if self.pos >= 1.0:
            self.pos -= 1.0
            self.line_phase = random.random()
            self.form = lap_form()
            lap_ms = int((now - self.lap_start) * 1000)
            self.lap += 1
            self.last_ms = lap_ms
            self.best_ms = min(self.best_ms or lap_ms, lap_ms)
            self.lap_start = now
        if running:
            self.fuel = max(0.0, self.fuel - dt * (0.002 + 0.0009 * gas * self.speed / 100))
        lap_ms = int((now - self.lap_start) * 1000)
        rpm_pct = rpm / RPM_MAX
        # the turbo builds up with throttle and rpm and needs a moment (lag)
        spool = BOOST_MAX * gas * min(1.0, max(0.0, (rpm_pct - 0.35) / 0.35)) if running else 0.0
        self.boost += (spool - self.boost) * min(1.0, dt * 3.0)
        delta = None
        if self.best_ms:
            delta = int(lap_ms - self.best_ms * self.pos)
        slip = gas > 0.9 and self.speed < 160 and s["tc_level"] > 0      # corner exits: TC cuts
        return {
            "connected": True, "status": "live", "car": "Demo GT", "track": "Demo Ring",
            "gear": self.gear, "max_gears": GEARS,
            "rpm": int(rpm), "rpm_max": RPM_MAX, "rpm_pct": round(rpm_pct, 4),
            "shift_up": self.gear < GEARS and self.gear > 0 and rpm_pct >= SHIFT_PCT - 0.02,
            "shift_down": False, "limiter": rpm >= RPM_MAX - 1,
            "speed_kmh": round(self.speed, 1), "gas": gas, "brake": brake, "clutch": 1.0 if now < self.shift_until else 0.0,
            "tc_level": s["tc_level"], "tc_cut_level": s["tc_cut_level"], "tc_active": slip and random.random() < 0.5,
            "abs_level": s["abs_level"], "abs_active": brake > 0.9 and s["abs_level"] > 0 and random.random() < 0.4,
            "brake_bias": s["brake_bias"], "engine_map": s["engine_map"], "pit_limiter": s["pit_limiter"],
            "esc_level": None,                                   # the demo car has no stability control
            "diff_power": 5, "diff_coast": 3,
            "drive_mode": s["drive_mode"], "drive_mode_name": MODES[s["drive_mode"]],
            "turbo": True, "boost_bar": round(self.boost, 3), "boost_min_bar": 0.0, "boost_max_bar": BOOST_MAX,
            **self.tyres(brake),
            **self.warnings(running),
            "limits": {"tc_level": [0, 11], "tc_cut_level": [0, 8], "abs_level": [0, 12], "engine_map": [1, 5], "diff_power": [1, 10], "diff_coast": [1, 10], "drive_mode": [0, 2]},
            "ignition": s["ignition"], "engine_running": running, "lights": s["lights"], "wipers": s["wipers"],
            "fuel_l": round(self.fuel, 2), "fuel_max_l": FUEL_MAX, "fuel_per_lap_l": 2.6,
            "lap": self.lap, "position": 3, "cars": 18,
            "lap_ms": lap_ms, "last_ms": self.last_ms, "best_ms": self.best_ms, "delta_ms": delta, "lap_valid": True,
            **self.where(),
        }

    def where(self) -> dict:
        """Analysis fields: position on the lap and on the map, steering, session, ambient."""
        i = track_index(self.pos)
        (x, y), (nx, ny), k = TRACK["line"][i], TRACK["normals"][i], TRACK["curv"][i]
        offset = max(-6.0, min(6.0, -k / KMAX * 5.0 + 1.2 * math.sin(2 * math.pi * (3 * self.pos + self.line_phase))))
        return {
            "lap_pos": round(self.pos, 6), "track_length_m": round(LAP_M, 1),
            "pos_x": round(x + nx * offset, 2), "pos_y": round(y + ny * offset, 2),
            "steer": round(max(-1.0, min(1.0, k * 40 + random.uniform(-0.02, 0.02))), 3),
            "session_id": self.session, "air_c": 22.0, "road_c": 31.0, "tyre_compound": "MEDIUM", "time_of_day": "14:00",
        }
