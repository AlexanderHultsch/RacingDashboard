"""DiRT Rally 2.0 connector: reads the game's UDP telemetry (Codemasters "extradata=3" format).

Enable it once in
    Documents\\My Games\\DiRT Rally 2.0\\hardware_settings\\hardware_settings_config.xml
    <udp enabled="true" extradata="3" ip="127.0.0.1" port="20777" delay="1" />
The connector checks this file at start and logs what is missing.

The packet is a row of little-endian 32-bit floats; byte offsets below. Offsets up to 252 follow the
cm-telemetry parser (rally2.rs); max rpm, idle rpm and the gear count (bytes 252-264) follow the common
66-float layout. The game only sends while driving. Only reading is possible: buttons are keypresses.
Field notes and what is not verified yet: docs/DR2/NOTES.md.
"""
import os
import re
import socket
import struct
import time
from pathlib import Path

import log
import telemetry

FLOAT = struct.Struct("<f")
MIN_SIZE = 256                 # extradata=3; smaller packets miss gear and rpm
GONE_S = 10.0                  # no packet for this long: report "game not running / not driving"
SHIFT_PCT = 0.94               # DiRT Rally 2.0 sends no shift signal: shift light from this rpm share
LIMITER_PCT = 0.99
CONFIG = Path("My Games") / "DiRT Rally 2.0" / "hardware_settings" / "hardware_settings_config.xml"

# byte offsets of the fields the dashboard reads (the whole layout: docs/DR2/NOTES.md)
LAP_TIME, LAP_DISTANCE, POS_X, POS_Z, SPEED = 4, 8, 16, 24, 28
THROTTLE, STEER, BRAKE, CLUTCH, GEAR = 116, 120, 124, 128, 132
LAP, RPM, POSITION = 144, 148, 156
TRACK_LENGTH, LAST_LAP = 244, 248
MAX_RPM, IDLE_RPM, MAX_GEARS = 252, 256, 260


def f32(data: bytes, offset: int) -> float | None:
    if offset + 4 > len(data):
        return None
    value = FLOAT.unpack_from(data, offset)[0]
    return value if value == value else None        # NaN -> None


def names(length: float, rpm_max: float, idle: float, gears: int) -> tuple[str, str]:
    """(track, car) for the analysis page. The packet carries no names, so the stage is named by its length
    and the car by its gearbox and engine: different stages and different cars keep apart in the laps and
    best times. Two cars with the same gear count, redline and idle share one name (rare)."""
    track = f"Stage {length / 1000:.2f} km" if length > 0 else ""
    car = f"{gears}-speed, {round(rpm_max)} rpm, idle {round(idle)}" if rpm_max > 0 and gears > 0 else ""
    return track, car


def parse(data: bytes) -> dict:
    """One telemetry packet -> universal telemetry (core/telemetry.py)."""
    raw_rpm, raw_max = f32(data, RPM) or 0.0, f32(data, MAX_RPM) or 0.0
    # Some builds send the engine rate as rpm / 10: a redline below 2000 cannot be real.
    scale = 10.0 if 0 < raw_max < 2000 else 1.0
    rpm, rpm_max = raw_rpm * scale, raw_max * scale
    max_gears = int(f32(data, MAX_GEARS) or 0)
    gear_raw = f32(data, GEAR)
    if gear_raw is None:
        gear = None
    elif gear_raw < 0 or (gear_raw >= 10 and 0 < max_gears < 10):   # reverse: negative (or 10 on some builds)
        gear = -1
    else:
        gear = int(gear_raw)
    length = f32(data, TRACK_LENGTH) or 0.0
    distance = f32(data, LAP_DISTANCE) or 0.0
    lap_time, last = f32(data, LAP_TIME), f32(data, LAST_LAP)
    rpm_pct = min(1.2, max(0.0, rpm / rpm_max)) if rpm_max > 0 else 0.0
    track, car = names(length, rpm_max, (f32(data, IDLE_RPM) or 0.0) * scale, max_gears if 0 < max_gears <= 20 else 0)
    return {
        "status": "live",
        "track": track,
        "car": car,
        "gear": gear,
        "max_gears": max_gears if 0 < max_gears <= 20 else 0,
        "rpm": round(max(0.0, rpm)),
        "rpm_max": round(rpm_max) if rpm_max > 0 else 0,
        "rpm_pct": round(rpm_pct, 4),
        "shift_up": rpm_pct >= SHIFT_PCT and gear is not None and 0 < gear < (max_gears or 99),
        "limiter": rpm_pct >= LIMITER_PCT,
        "speed_kmh": round(max(0.0, (f32(data, SPEED) or 0.0) * 3.6), 1),
        "gas": round(f32(data, THROTTLE) or 0.0, 3),
        "brake": round(f32(data, BRAKE) or 0.0, 3),
        "clutch": round(f32(data, CLUTCH) or 0.0, 3),
        "lap": int(f32(data, LAP) or 0),
        "position": int(f32(data, POSITION) or 0),
        "lap_ms": int(lap_time * 1000) if lap_time and lap_time > 0 else None,
        "last_ms": int(last * 1000) if last and last > 0 else None,
        "lap_progress": round(min(1.0, max(0.0, distance / length)), 4) if length > 0 else None,
        # analysis page: one stage = one lap; a new stage (length) or car = a new run
        "lap_pos": round(min(1.0, max(0.0, distance / length)), 6) if length > 0 else None,
        "track_length_m": round(length, 1) if length > 0 else None,
        "pos_x": round(f32(data, POS_X) or 0.0, 2),
        "pos_y": round(f32(data, POS_Z) or 0.0, 2),
        "steer": round(max(-1.0, min(1.0, f32(data, STEER) or 0.0)), 3),
        "session_id": f"stage-{round(length)}",
    }


def config_paths() -> list[Path]:
    """Where hardware_settings_config.xml can be: Documents, also when OneDrive moves it."""
    roots = [Path.home() / "Documents"]
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(name):
            roots.append(Path(os.environ[name]) / "Documents")
    return [root / CONFIG for root in roots]


def check_config(text: str, port: int) -> str | None:
    """Problem with the game's UDP setting, or None if it sends extradata=3 to our port."""
    match = re.search(r"<udp\b([^>]*)>", text)
    if not match:
        return "no <udp ...> line in hardware_settings_config.xml"
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
    if attrs.get("enabled", "").lower() != "true":
        return 'UDP telemetry is off: set enabled="true"'
    if attrs.get("extradata") != "3":
        return f'extradata="{attrs.get("extradata")}": set extradata="3"'
    if attrs.get("port") != str(port):
        return f'the game sends to port {attrs.get("port")}, the dashboard listens on {port}'
    return None


class Connector(telemetry.Connector):
    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.port = int(game.get("udp", {}).get("port", 20777))
        self.sock = None
        self.last_packet = None
        self.last_time = 0.0
        self.short_logged = False
        self.stale_s = cfg["telemetry"]["stale_s"]

    def open(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", self.port))
        self.sock.setblocking(False)
        log.line("dr2", "udp", f"listening on port {self.port}")
        for path in config_paths():
            if path.exists():
                problem = check_config(path.read_text(encoding="utf-8", errors="replace"), self.port)
                log.line("dr2", "config", problem or "UDP telemetry on (extradata 3)")
                break
        else:
            log.line("dr2", "config", "hardware_settings_config.xml not found (start the game once)")

    def read(self) -> dict | None:
        while True:                       # take the newest packet, drop older ones
            try:
                data = self.sock.recv(2048)
            except (BlockingIOError, InterruptedError):
                break
            if len(data) < MIN_SIZE:
                if not self.short_logged:
                    log.line("dr2", "packet", f"{len(data)} bytes: set extradata=\"3\" in hardware_settings_config.xml")
                    self.short_logged = True
                continue
            self.last_packet, self.last_time = data, time.monotonic()
        if self.last_packet is None:
            return None
        idle = time.monotonic() - self.last_time
        if idle > GONE_S:
            return None
        values = parse(self.last_packet)
        values["connected"] = idle < self.stale_s
        return values

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None
