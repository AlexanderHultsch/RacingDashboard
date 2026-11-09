"""iRacing connector: reads the sim's live telemetry shared memory (irsdk, Windows).

iRacing publishes one named block, Local\\IRSDKMemMapFileName:
    a header (112 bytes) - version, status (bit 0 = connected), the variable table, the session info
        YAML and up to 4 rotating data buffers (each with a tickCount);
    the variable headers (144 bytes each: type, offset, count, name, description, unit);
    the session info, a YAML text (car, track, track length, shift lights, gears ...);
    the data buffers, one row of all variables per tick (60 Hz).
Layout from iRacing's irsdk_defines.h (SDK 1.19 / 1.20, BSD licence) and pyirsdk; the variable names are
iRacing's own. A variable exists only when the car has it (dcTractionControl, dcABS ...), so every
lookup is by name and a missing one is None ("not on this car").

There is no live X / Y position in iRacing's telemetry (Lat / Lon are only in .ibt files), so the map
position for the analysis page is dead-reckoned from the car's velocity and compass heading, and starts
again at the start / finish line every lap (the drift of one lap is small).
Field notes and what is not verified yet: docs/IRACING/NOTES.md.
"""
import math
import re
import struct
import time

import log
import telemetry
import winmem

MEMORY = "Local\\IRSDKMemMapFileName"
REOPEN_S = 1.0          # retry interval while iRacing is not running
STALE_REOPEN_S = 5.0    # reattach after this long without a new tick (detects a closed sim)
CONNECTED = 1           # header status bit irsdk_stConnected

HEADER = struct.Struct("<10i")          # ver, status, tickRate, sessionInfoUpdate, sessionInfoLen,
                                        # sessionInfoOffset, numVars, varHeaderOffset, numBuf, bufLen
VAR_BUF = struct.Struct("<4i")          # tickCount, bufOffset, tickCountBegin (SDK 1.20, else 0), pad
VAR_BUF_AT = 48
VAR_HEADER = struct.Struct("<3i?3x32s64s32s")   # type, offset, count, countAsTime, name, desc, unit
TYPES = {0: ("c", 1), 1: ("?", 1), 2: ("i", 4), 3: ("I", 4), 4: ("f", 4), 5: ("d", 8)}

# EngineWarnings bits (irsdk_EngineWarnings)
WATER_TEMP, OIL_PRESSURE, STALLED, PIT_LIMITER, REV_LIMITER, OIL_TEMP = 0x01, 0x04, 0x08, 0x10, 0x20, 0x40
OFF_TRACK = 0           # PlayerTrackSurface: -1 not in world, 0 off track, 1 pit stall, 2 approaching pits, 3 on track


# ------------------------------------------------------------------ session info (YAML)


def parse_session(text: str) -> dict:
    """The session info values the connector needs (see the module notes)."""
    data = parse_yaml(text)
    weekend, driver = data.get("WeekendInfo") or {}, data.get("DriverInfo") or {}
    me = _num(driver.get("DriverCarIdx"))
    car = ""
    for entry in driver.get("Drivers") or []:
        if _num(entry.get("CarIdx")) == me:
            car = entry.get("CarScreenName") or entry.get("CarScreenNameShort") or ""
            break
    track = weekend.get("TrackDisplayName") or weekend.get("TrackName") or ""
    config = weekend.get("TrackConfigName") or ""
    length = _num(weekend.get("TrackLengthOfficial")) or _num(weekend.get("TrackLength"))
    return {
        "car": car,
        "track": f"{track} - {config}" if config and config not in track else track,
        "track_length_m": round(length * 1000, 1) if length else None,     # "4.29 km"
        "redline": _num(driver.get("DriverCarRedLine")) or 0.0,
        "shift_rpm": _num(driver.get("DriverCarSLShiftRPM")) or 0.0,
        "gears": int(_num(driver.get("DriverCarGearNumForward")) or 0),
        "fuel_max": _num(driver.get("DriverCarFuelMaxLtr")),
        "session": f"{weekend.get('SessionID', '0')}-{weekend.get('SubSessionID', '0')}",
    }


def parse_yaml(text: str) -> dict:
    """The small part of YAML iRacing writes: maps by indentation, lists of maps ("- key: value") under a
    key on its own line, plain scalars. Enough for the session info; values stay strings ("4.29 km")."""
    root: dict = {}
    stack: list = [(-1, root)]               # (indent, container); a list item sits at its "- " indent + 1
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped in ("---", "..."):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        item = stripped.startswith("- ")
        body = stripped[2:] if item else stripped
        key, sep, value = body.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip().strip("'\"")
        if item:                                 # iRacing writes "- " at the indent of the list's key
            while len(stack) > 1 and stack[-1][0] > indent:
                stack.pop()
            owner = stack[-1][1]
            if not isinstance(owner, dict) or "__list__" not in owner:
                continue
            entry: dict = {}
            owner["__list__"].append(entry)
            stack.append((indent + 1, entry))
            container, level = entry, indent + 2
        else:
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()
            container, level = stack[-1][1], indent
        if value:
            container[key] = value
        else:
            child: dict = {"__list__": []}
            container[key] = child
            stack.append((level, child))
    return _clean(root)


def _clean(node):
    if isinstance(node, dict):
        if "__list__" in node:
            items = node.pop("__list__")
            if items:
                return [_clean(i) for i in items]
        return {k: _clean(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_clean(i) for i in node]
    return node


def _num(text):
    if text is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(text))
    return float(match.group()) if match else None


# ------------------------------------------------------------------ the memory image


class Image:
    """Reads the irsdk block: header, variables, the newest data row and the session info. `memory` has
    read_at(offset, length) -> bytes (winmem.SharedMemory, or bytes in the tests)."""

    def __init__(self, memory):
        self.memory = memory
        self.vars, self.vars_at = {}, None
        self.session, self.session_update = {}, None

    def header(self) -> dict:
        values = HEADER.unpack(self.memory.read_at(0, HEADER.size))
        names = ("ver", "status", "tick_rate", "session_update", "session_len", "session_offset",
                 "num_vars", "var_offset", "num_buf", "buf_len")
        return dict(zip(names, values))

    def load_vars(self, head: dict) -> None:
        key = (head["var_offset"], head["num_vars"])
        if key == self.vars_at:
            return
        table = self.memory.read_at(head["var_offset"], VAR_HEADER.size * head["num_vars"])
        out = {}
        for i in range(head["num_vars"]):
            kind, offset, count, _, name, _, _ = VAR_HEADER.unpack_from(table, i * VAR_HEADER.size)
            if kind in TYPES:
                out[name.split(b"\0", 1)[0].decode("latin-1")] = (kind, offset, count)
        self.vars, self.vars_at = out, key

    def load_session(self, head: dict) -> None:
        if head["session_update"] == self.session_update:
            return
        raw = self.memory.read_at(head["session_offset"], head["session_len"]).split(b"\0", 1)[0]
        utf8 = b"Encoding: UTF8" in raw[:200]
        self.session = parse_session(raw.decode("utf-8" if utf8 else "cp1252", errors="replace"))
        self.session_update = head["session_update"]

    def row(self, head: dict):
        """(tick, row bytes) of the newest complete buffer, or (None, None)."""
        bufs = [VAR_BUF.unpack(self.memory.read_at(VAR_BUF_AT + VAR_BUF.size * i, VAR_BUF.size))
                for i in range(max(0, min(head["num_buf"], 4)))]
        if not bufs:
            return None, None
        for _ in range(2):                                   # a buffer written while copied: try again
            tick, offset, begin, _ = max(bufs, key=lambda b: b[0])
            data = self.memory.read_at(offset, head["buf_len"])
            index = bufs.index((tick, offset, begin, _))
            after = VAR_BUF.unpack(self.memory.read_at(VAR_BUF_AT + VAR_BUF.size * index, VAR_BUF.size))
            if after[0] == tick and (after[2] == 0 or after[2] == tick):
                return tick, data
            bufs[index] = after
        return None, None

    def value(self, row: bytes, name: str, default=None):
        spec = self.vars.get(name)
        if spec is None:
            return default
        kind, offset, count = spec
        code, size = TYPES[kind]
        if count > 1:
            return list(struct.unpack_from(f"<{count}{code}", row, offset))
        return struct.unpack_from("<" + code, row, offset)[0]


# ------------------------------------------------------------------ frame


def level(value):
    """An in-car setting (dc...) as a whole number; None when the car does not have it."""
    return None if value is None else int(round(value))


def bias(value):
    """Brake bias as a front share 0..1; iRacing reports percent (e.g. 54.5) on most cars."""
    if value is None or value <= 0:
        return None
    share = value / 100 if value > 1.5 else value
    return round(share, 4) if 0.2 < share < 0.9 else None


def warnings(bits: int, running: bool) -> dict:
    """Warning lamps from iRacing's EngineWarnings bits."""
    return {
        "warn_brake": None,                                       # not reported by iRacing
        "warn_engine": "warn" if bits & STALLED or not running else "off",
        "warn_oil": "alert" if bits & OIL_PRESSURE else "warn" if bits & OIL_TEMP else "off",
        "warn_coolant": "warn" if bits & WATER_TEMP else "off",
    }


AIR_BAR = 1.013          # standard air pressure, bar: ManifoldPress minus this = boost (negative = vacuum)


def parse(image: Image, row: bytes) -> dict:
    """One data row -> universal telemetry (core/telemetry.py), without the map position."""
    v = lambda name, default=None: image.value(row, name, default)
    s = image.session
    rpm = float(v("RPM", 0.0) or 0.0)
    redline = s.get("redline") or 0.0
    gear = int(v("Gear", 0) or 0)
    gears = s.get("gears") or 0
    bits = int(v("EngineWarnings", 0) or 0)
    last, now = v("LapLastLapTime"), v("LapCurrentLapTime")
    steer, steer_max = v("SteeringWheelAngle"), v("SteeringWheelAngleMax")
    running = not bits & STALLED
    status = "replay" if v("IsReplayPlaying") else "live" if v("IsOnTrack") else "off"
    tod = v("SessionTimeOfDay")
    values = {
        "status": status,
        "car": s.get("car", ""),
        "track": s.get("track", ""),
        "gear": max(-1, min(gear, 20)),
        "rpm": round(max(0.0, rpm)),
        "rpm_max": round(redline),
        "rpm_pct": round(min(1.2, rpm / redline), 4) if redline else 0.0,
        "shift_up": bool(s.get("shift_rpm")) and rpm >= s["shift_rpm"] and 0 < gear < (gears or 99),
        "limiter": bool(bits & REV_LIMITER),
        "speed_kmh": round(max(0.0, float(v("Speed", 0.0) or 0.0) * 3.6), 1),
        "gas": round(float(v("Throttle", 0.0) or 0.0), 3),
        "brake": round(float(v("Brake", 0.0) or 0.0), 3),
        "tc_level": level(v("dcTractionControl")),
        "tc_cut_level": level(v("dcTractionControl2")),
        "abs_level": level(v("dcABS")),
        "abs_active": bool(v("BrakeABSactive", False)),
        "brake_bias": bias(v("dcBrakeBias")),
        "engine_map": level(v("dcThrottleShape", v("dcFuelMixture"))),
        "pit_limiter": bool(bits & PIT_LIMITER),
        # boost page: ManifoldPress (absolute, bar) minus the air pressure; below 0 = vacuum, so every car shows
        # something. iRacing does not send the car's maximum boost
        "boost_bar": round(v("ManifoldPress") - AIR_BAR, 3) if v("ManifoldPress") is not None else None,
        "boost_min_bar": -1.0,
        "engine_running": running,
        **warnings(bits, running),
        "fuel_l": round(v("FuelLevel"), 2) if v("FuelLevel") is not None else None,
        "fuel_max_l": s.get("fuel_max"),
        "lap_ms": int(now * 1000) if now and now > 0 else None,
        "last_ms": int(last * 1000) if last and last > 0 else None,
        # iRacing has no live "lap invalid" flag: four wheels off the track invalidates the lap
        "lap_valid": v("PlayerTrackSurface", 3) != OFF_TRACK,
        "lap_progress": None,
        # analysis page
        "lap_pos": None,
        "track_length_m": s.get("track_length_m"),
        "steer": round(max(-1.0, min(1.0, steer / steer_max)), 3) if steer is not None and steer_max else None,
        "session_id": f"{s.get('session', '0-0')}-{v('SessionNum', 0)}",
        "air_c": round(v("AirTemp"), 1) if v("AirTemp") is not None else None,
        "road_c": round(v("TrackTempCrew"), 1) if v("TrackTempCrew") is not None else None,
        "time_of_day": f"{int(tod // 3600) % 24:02d}:{int(tod % 3600 // 60):02d}" if tod is not None else None,
    }
    pct = v("LapDistPct")
    if pct is not None and 0 <= pct <= 1:
        values["lap_pos"] = values["lap_progress"] = round(pct, 6)
    return values


class Map:
    """Dead reckoning of the car's map position: velocity in the car frame (x forward, y to the left) turned
    by the compass heading (YawNorth, 0 = north, clockwise). Starts at 0 / 0 on every line crossing, so
    laps line up and the drift of one lap does not carry into the next. y on the map points south (the
    page draws y downwards), so north is up."""

    def __init__(self):
        self.east = self.north = 0.0
        self.time = self.pct = None

    def step(self, t, pct, vx, vy, yaw) -> tuple:
        if None in (t, vx, vy, yaw):
            return None, None
        if pct is not None and self.pct is not None and self.pct > 0.9 and pct < 0.1:
            self.east = self.north = 0.0                     # over the line: a new lap starts at the origin
        if self.time is not None and 0 < t - self.time <= 1.0:           # a longer gap: paused, no step
            dt = t - self.time
            self.east += (vx * math.sin(yaw) - vy * math.cos(yaw)) * dt
            self.north += (vx * math.cos(yaw) + vy * math.sin(yaw)) * dt
        self.time, self.pct = t, pct
        return round(self.east, 2), round(-self.north, 2)


class Connector(telemetry.Connector):
    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.memory = None
        self.image = None
        self.next_try = 0.0
        self.attached_at = 0.0
        self.last_tick, self.last_change = None, 0.0
        self.stale_s = cfg["telemetry"]["stale_s"]
        self.map = Map()
        self.version = None

    def attach(self) -> bool:
        now = time.monotonic()
        if now < self.next_try:
            return False
        self.next_try = now + REOPEN_S
        try:
            self.memory = winmem.SharedMemory(MEMORY)
        except FileNotFoundError:
            return False
        self.image, self.attached_at = Image(self.memory), now
        version = HEADER.unpack(self.memory.read_at(0, HEADER.size))[0]
        if version != self.version:
            self.version = version
            log.line("iracing", "shared memory", f"irsdk header version {version}")
        return True

    def read(self) -> dict | None:
        if self.memory is None and not self.attach():
            return None
        head = self.image.header()
        now = time.monotonic()
        if not head["status"] & CONNECTED:
            if now - self.attached_at > STALE_REOPEN_S:
                self.close()                                 # the sim may have closed: attach again later
            return None
        self.image.load_vars(head)
        self.image.load_session(head)
        tick, row = self.image.row(head)
        if row is None:
            return None
        values = parse(self.image, row)
        x, y = self.map.step(self.image.value(row, "SessionTime"), values["lap_pos"],
                             self.image.value(row, "VelocityX"), self.image.value(row, "VelocityY"),
                             self.image.value(row, "YawNorth"))
        values["pos_x"], values["pos_y"] = x, y
        if tick != self.last_tick:
            self.last_tick, self.last_change = tick, now
        values["connected"] = now - self.last_change < self.stale_s
        if not values["connected"] and now - self.attached_at > STALE_REOPEN_S:
            self.close()
            self.next_try = 0.0
        return values

    def close(self) -> None:
        if self.memory is not None:
            self.memory.close()
        self.memory, self.image = None, None
