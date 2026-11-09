"""Assetto Corsa Rally connector: reads the game's shared memory (Windows).

Assetto Corsa Rally (Early Access, Unreal Engine 5) publishes the classic Kunos blocks with the ACC layout,
not the Assetto Corsa EVO one:
    Local\\acpmf_physics    800 bytes, the ACC physics page (core/kunos.py)
    Local\\acpmf_graphics   the ACC graphics page; ACR fills only a few fields (the stage clock as text,
                            the distance along the stage, the car's world position)
    Local\\acpmf_static     the ACC static page: car, stage (in the game's language), stage length
AC1 and ACC publish the same block names, so the connector reads them only while acr.exe runs.

Kunos publishes no ACR documentation: the field notes come from tools that read ACR (SimHub, MarvinsAIRA,
acr-overlay, ZTMZ Pacenote, live-telemetry-evo, nobonobo/ac-telemetry). ACR leaves status, laps, damage,
lights and wipers empty; temperatures are in Kelvin; the clutch is 1 when the pedal is up. In the pause
menu the physics page is blanked (or frozen): the connector reports a pause.
Field notes and what is not verified yet: docs/ACR/NOTES.md.
"""
import re
import time
from ctypes import Structure, c_float, c_int32, c_uint16, sizeof

import log
import telemetry
import winmem
from kunos import Physics

PHYSICS_TAG = "Local\\acpmf_physics"
GRAPHICS_TAG = "Local\\acpmf_graphics"
STATIC_TAG = "Local\\acpmf_static"
PROCESSES = ("acr.exe", "acr-Win64-Shipping.exe")
REOPEN_S = 2.0          # retry interval while the game is not running (a process check each time)
STALE_REOPEN_S = 5.0
SHIFT_PCT = 0.94        # ACR sends no shift signal: shift light from this rpm share
LIMITER_PCT = 0.99
KELVIN = 273.15


def wchars(n):
    """A UTF-16 text field of n characters (2 bytes each on every system, unlike ctypes' c_wchar)."""
    return c_uint16 * n


class Graphics(Structure):            # ACC SPageFileGraphic, as far as the dashboard reads it
    _pack_ = 4
    _fields_ = [
        ("packetId", c_int32), ("status", c_int32), ("session", c_int32),
        ("currentTime", wchars(15)), ("lastTime", wchars(15)), ("bestTime", wchars(15)), ("split", wchars(15)),
        ("completedLaps", c_int32), ("position", c_int32), ("iCurrentTime", c_int32), ("iLastTime", c_int32),
        ("iBestTime", c_int32), ("sessionTimeLeft", c_float), ("distanceTraveled", c_float), ("isInPit", c_int32),
        ("currentSectorIndex", c_int32), ("lastSectorTime", c_int32), ("numberOfLaps", c_int32),
        ("tyreCompound", wchars(33)), ("replayTimeMultiplier", c_float), ("normalizedCarPosition", c_float),
        ("activeCars", c_int32), ("carCoordinates", (c_float * 3) * 60), ("carID", c_int32 * 60),
        ("playerCarID", c_int32), ("penaltyTime", c_float), ("flag", c_int32), ("penalty", c_int32),
        ("idealLineOn", c_int32), ("isInPitLane", c_int32), ("surfaceGrip", c_float), ("mandatoryPitDone", c_int32),
        ("windSpeed", c_float), ("windDirection", c_float), ("isSetupMenuVisible", c_int32),
        ("mainDisplayIndex", c_int32), ("secondaryDisplayIndex", c_int32), ("TC", c_int32), ("TCCut", c_int32),
        ("EngineMap", c_int32), ("ABS", c_int32), ("fuelXLap", c_float), ("rainLights", c_int32),
        ("flashingLights", c_int32), ("lightsStage", c_int32), ("exhaustTemperature", c_float), ("wiperLV", c_int32),
    ]


class Static(Structure):              # ACC SPageFileStatic, as far as the dashboard reads it
    _pack_ = 4
    _fields_ = [
        ("smVersion", wchars(15)), ("acVersion", wchars(15)), ("numberOfSessions", c_int32), ("numCars", c_int32),
        ("carModel", wchars(33)), ("track", wchars(33)), ("playerName", wchars(33)), ("playerSurname", wchars(33)),
        ("playerNick", wchars(33)), ("sectorCount", c_int32), ("maxTorque", c_float), ("maxPower", c_float),
        ("maxRpm", c_int32), ("maxFuel", c_float), ("suspensionMaxTravel", c_float * 4), ("tyreRadius", c_float * 4),
        ("maxTurboBoost", c_float), ("deprecated_1", c_float), ("deprecated_2", c_float),
        ("penaltiesEnabled", c_int32), ("aidFuelRate", c_float), ("aidTireRate", c_float),
        ("aidMechanicalDamage", c_float), ("aidAllowTyreBlankets", c_float), ("aidStability", c_float),
        ("aidAutoClutch", c_int32), ("aidAutoBlip", c_int32), ("hasDRS", c_int32), ("hasERS", c_int32),
        ("hasKERS", c_int32), ("kersMaxJ", c_float), ("engineBrakeSettingsCount", c_int32),
        ("ersPowerControllerCount", c_int32), ("trackSplineLength", c_float), ("trackConfiguration", wchars(33)),
    ]


def text(field) -> str:
    """A UTF-16 text field, up to its first NUL."""
    out = []
    for code in field:
        if code == 0:
            break
        out.append(code)
    return bytes(b for code in out for b in code.to_bytes(2, "little")).decode("utf-16-le", "replace").strip()


def clock_ms(field):
    """ACR writes the stage clock only as text ("00:11.596", "1:02:03.004"); None when empty or 0."""
    match = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)", text(field))
    if not match:
        return None
    h, m, s, frac = match.groups()
    ms = ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0")[:3])
    return ms or None


def celsius(kelvin: float):
    return round(kelvin - KELVIN, 1) if kelvin > 150 else None


def blank(ph) -> bool:
    """The pause menu (and the stop zone) blanks the physics page while its packet counter runs on."""
    return ph.rpms == 0 and ph.gear == 0 and ph.speedKmh == 0 and ph.gas == 0 and ph.brake == 0


def parse(physics: bytes, graphics: bytes, static: bytes) -> dict:
    """Raw shared memory bytes -> universal telemetry (core/telemetry.py)."""
    ph = Physics.from_buffer_copy(physics[:sizeof(Physics)])
    gr = Graphics.from_buffer_copy(graphics[:sizeof(Graphics)])
    st = Static.from_buffer_copy(static[:sizeof(Static)])
    rpm_max = st.maxRpm if st.maxRpm > 0 else max(0, ph.currentMaxRpm)
    rpm = max(0, ph.rpms)
    rpm_pct = min(1.2, rpm / rpm_max) if rpm_max else 0.0
    gear = ph.gear - 1                                   # ACC: 0 = R, 1 = N, 2 = 1st
    length = st.trackSplineLength
    x, _, z = gr.carCoordinates[0]                       # ACR writes only the player's car, in slot 0
    return {
        "status": "pause" if blank(ph) else "live",
        "car": text(st.carModel),
        "track": text(st.track),
        "gear": gear,
        "max_gears": 0,
        "rpm": rpm,
        "rpm_max": rpm_max,
        "rpm_pct": round(max(0.0, rpm_pct), 4),
        "shift_up": rpm_pct >= SHIFT_PCT and gear > 0,
        "limiter": rpm_pct >= LIMITER_PCT,
        "speed_kmh": round(max(0.0, ph.speedKmh), 1),
        "gas": round(ph.gas, 3),
        "brake": round(ph.brake, 3),
        "clutch": round(1.0 - ph.clutch, 3) if 0 <= ph.clutch <= 1 else 0.0,     # ACR: 1 = pedal up
        "tc_level": gr.TC if 0 <= gr.TC <= 20 else None,
        "tc_active": ph.tc > 0,
        "abs_level": gr.ABS if 0 <= gr.ABS <= 20 else None,
        "abs_active": ph.abs > 0,
        "brake_bias": round(ph.brakeBias, 4) if 0.2 < ph.brakeBias < 0.9 else None,
        "fuel_l": round(ph.fuel, 2) if ph.fuel > 0 else None,
        "fuel_max_l": round(st.maxFuel, 1) if st.maxFuel > 0 else None,
        "lap_ms": clock_ms(gr.currentTime),
        "last_ms": clock_ms(gr.lastTime),
        "lap_progress": round(min(1.0, max(0.0, gr.distanceTraveled / length)), 4) if length > 0 else None,
        # analysis page: one stage = one lap, progress from the distance along the stage
        "lap_pos": round(min(1.0, max(0.0, gr.distanceTraveled / length)), 6) if length > 0 else None,
        "track_length_m": round(length, 1) if length > 0 else None,
        "pos_x": round(x, 2) if (x or z) else None,
        "pos_y": round(z, 2) if (x or z) else None,
        "steer": round(max(-1.0, min(1.0, ph.steerAngle)), 3),
        "session_id": f"acr-{round(length)}",
        "air_c": celsius(ph.airTemp),
        "road_c": celsius(ph.roadTemp),
    }


class Connector(telemetry.Connector):
    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.blocks = None
        self.next_try = 0.0
        self.attached_at = 0.0
        self.last_packet, self.last_change = None, 0.0
        self.stale_s = cfg["telemetry"]["stale_s"]
        self.logged = False

    def attach(self) -> bool:
        now = time.monotonic()
        if now < self.next_try:
            return False
        self.next_try = now + REOPEN_S
        if not winmem.process_running(*PROCESSES):       # the same block names belong to AC1 / ACC too
            return False
        blocks = []
        try:
            for tag, struct in ((PHYSICS_TAG, Physics), (GRAPHICS_TAG, Graphics), (STATIC_TAG, Static)):
                blocks.append(winmem.SharedMemory(tag, sizeof(struct)))
        except FileNotFoundError:
            for block in blocks:
                block.close()
            return False
        self.blocks, self.attached_at = blocks, now
        if not self.logged:
            log.line("acr", "shared memory", "attached to Local\\acpmf_* (acr.exe runs)")
            self.logged = True
        return True

    def read(self) -> dict | None:
        if self.blocks is None and not self.attach():
            return None
        physics, graphics, static = (block.read() for block in self.blocks)
        values = parse(physics, graphics, static)
        now = time.monotonic()
        packet = physics[:4]
        if packet != self.last_packet:
            self.last_packet, self.last_change = packet, now
        values["connected"] = now - self.last_change < self.stale_s
        if not values["connected"] and now - self.attached_at > STALE_REOPEN_S:
            self.close()                                 # the game may have closed: check the process again
            self.next_try = 0.0
        return values

    def close(self) -> None:
        for block in self.blocks or ():
            block.close()
        self.blocks = None
