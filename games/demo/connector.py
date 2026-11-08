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
RPM_IDLE = 1100
SHIFT_PCT = 0.94                         # the "game's" shift point
# gearbox modes, cycled with the AUTO SHIFT button: (name, the demo driver shifts, gear_mode, upshift share)
GEARBOXES = [("sequential", True, None, SHIFT_PCT), ("automatic D", True, "D", 0.80),
             ("automatic S", True, "S", 0.97), ("manual", False, None, SHIFT_PCT)]
RATIOS = [0, 3.3, 2.3, 1.75, 1.4, 1.15, 0.97]   # km/h -> rpm factor per gear, scaled below
SPEED_RPM = 30.0                         # rpm per km/h at ratio 1.0
LAP_M = 4200.0
FUEL_MAX = 60.0
PIT_LIMIT_KMH = 60.0
GEARS = len(RATIOS) - 1


def target_speed(pos: float) -> float:
    """Wanted speed in km/h at a track position 0..1: a few straights and corners."""
    corners = (0.12, 0.31, 0.38, 0.55, 0.72, 0.9)
    speed = 285.0
    for corner in corners:
        distance = min(abs(pos - corner), 1 - abs(pos - corner))
        speed = min(speed, 85 + 2600 * distance)
    return speed


class Connector(telemetry.Connector):
    HANDLES = tuple(actions.BY_NAME)

    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.last = time.monotonic()
        self.pos = 0.0
        self.speed = 0.0
        self.gear = 1
        self.shift_until = 0.0
        self.lap_start = self.last
        self.lap = 0
        self.last_ms = None
        self.best_ms = None
        self.fuel = 42.0
        self.coolant = 35.0                      # starts cold: blue lamp until about 50 C
        self.state = {"tc_level": 3, "tc_cut_level": 2, "abs_level": 2, "brake_bias": 0.565, "engine_map": 1, "pit_limiter": False,
                      "lights": 0, "wipers": 0, "ignition": True, "engine_running": True, "auto_shifter": True}
        self.gearbox = 0

    def handle(self, action: str, state: str) -> bool:
        s = self.state
        if state == "up":
            return True
        steps = {"tc_up": ("tc_level", 1, 0, 11), "tc_down": ("tc_level", -1, 0, 11),
                 "tc_cut_up": ("tc_cut_level", 1, 0, 8), "tc_cut_down": ("tc_cut_level", -1, 0, 8),
                 "abs_up": ("abs_level", 1, 0, 12), "abs_down": ("abs_level", -1, 0, 12),
                 "map_up": ("engine_map", 1, 1, 5), "map_down": ("engine_map", -1, 1, 5),
                 "bias_front": ("brake_bias", 0.005, 0.45, 0.7), "bias_rear": ("brake_bias", -0.005, 0.45, 0.7)}
        if action in steps and s.get(steps[action][0]) is not None:
            name, step, low, high = steps[action]
            s[name] = round(min(high, max(low, s[name] + step)), 3)
        elif action == "auto_shifter":
            self.gearbox = (self.gearbox + 1) % len(GEARBOXES)
            s["auto_shifter"] = GEARBOXES[self.gearbox][1]
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
        want = target_speed(self.pos)
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
            if self.gear < GEARS and rpm >= RPM_MAX * GEARBOXES[self.gearbox][3] and gas > 0:
                self.shift(self.gear + 1)
            elif self.gear > 1 and self.rpm_for(self.gear - 1) < RPM_MAX * 0.7 and brake > 0:
                self.shift(self.gear - 1)
            elif self.gear <= 0:
                self.shift(1)
        self.pos += self.speed / 3.6 * dt / LAP_M
        if self.pos >= 1.0:
            self.pos -= 1.0
            lap_ms = int((now - self.lap_start) * 1000)
            self.lap += 1
            self.last_ms = lap_ms
            self.best_ms = min(self.best_ms or lap_ms, lap_ms)
            self.lap_start = now
        if running:
            self.fuel = max(0.0, self.fuel - dt * (0.002 + 0.0009 * gas * self.speed / 100))
        lap_ms = int((now - self.lap_start) * 1000)
        rpm_pct = rpm / RPM_MAX
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
            "launch": running and self.gear == 1 and self.speed < 8 and gas > 0.5,
            "auto_clutch": s["auto_shifter"],
            "gear_mode": GEARBOXES[self.gearbox][2],
            **self.warnings(running),
            "limits": {"tc_level": [0, 11], "tc_cut_level": [0, 8], "abs_level": [0, 12], "engine_map": [1, 5], "diff_power": [1, 10], "diff_coast": [1, 10]},
            "ignition": s["ignition"], "engine_running": running, "lights": s["lights"], "wipers": s["wipers"],
            "fuel_l": round(self.fuel, 2), "fuel_max_l": FUEL_MAX, "fuel_per_lap_l": 2.6,
            "lap": self.lap, "position": 3, "cars": 18,
            "lap_ms": lap_ms, "last_ms": self.last_ms, "best_ms": self.best_ms, "delta_ms": delta, "lap_valid": True,
        }
