"""iRacing connector: the irsdk memory image, the session info and the translation, without the sim.

Run: python -m unittest discover tests
"""
import importlib.util
import math
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import telemetry  # noqa: E402

spec = importlib.util.spec_from_file_location("iracing_connector", ROOT / "games" / "iracing" / "connector.py")
ir = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ir)

SESSION = """---
WeekendInfo:
 TrackName: oulton international
 TrackLength: 4.29 km
 TrackLengthOfficial: 4.33 km
 TrackDisplayName: Oulton Park Circuit
 TrackConfigName: International
 SessionID: 0
 SubSessionID: 0
SessionInfo:
 Sessions:
 - SessionNum: 0
   SessionType: Offline Testing
   ResultsPositions:
   ResultsFastestLap:
   - CarIdx: 255
     FastestLap: 0
DriverInfo:
 DriverCarIdx: 1
 DriverCarFuelMaxLtr: 120.000
 DriverCarRedLine: 9500.000
 DriverCarSLShiftRPM: 9250.000
 DriverCarGearNumForward: 6
 Drivers:
 - CarIdx: 0
   UserName: Pace Car
   CarScreenName: Safety Car
 - CarIdx: 1
   UserName: Driver
   CarScreenName: Porsche 911 GT3 R (992)
...
"""

# name: (type, value); types: 1 bool, 2 int, 3 bitField, 4 float, 5 double
VARS = {
    "SessionTime": (5, 100.0), "SessionNum": (2, 0), "Gear": (2, 4), "RPM": (4, 9300.0), "Speed": (4, 50.0),
    "Throttle": (4, 1.0), "Brake": (4, 0.0), "SteeringWheelAngle": (4, 1.0),
    "SteeringWheelAngleMax": (4, 4.0), "LapDistPct": (4, 0.25),
    "LapCurrentLapTime": (4, 23.5), "LapLastLapTime": (4, 92.25), "FuelLevel": (4, 41.5),
    "dcTractionControl": (4, 3.0), "dcABS": (4, 5.0), "dcBrakeBias": (4, 54.5), "BrakeABSactive": (1, True),
    "EngineWarnings": (3, 0x10 | 0x04), "IsOnTrack": (1, True), "IsReplayPlaying": (1, False),
    "PlayerTrackSurface": (2, 3), "AirTemp": (4, 21.0), "TrackTempCrew": (4, 30.0),
    "SessionTimeOfDay": (4, 50400.0), "ManifoldPress": (4, 0.4), "VelocityX": (4, 50.0), "VelocityY": (4, 0.0), "YawNorth": (4, 0.0),
}
CODES = {1: "?", 2: "i", 3: "I", 4: "f", 5: "d"}


class Memory:
    """A bytes image with read_at, like winmem.SharedMemory."""

    def __init__(self, data: bytearray):
        self.data = data

    def read_at(self, offset, length):
        return bytes(self.data[offset:offset + length]).ljust(length, b"\0")


def image(values=None, session=SESSION, tick=7, connected=True):
    """A complete irsdk block: header, variable headers, session info, 3 buffers (the newest is `tick`)."""
    values = dict(VARS, **(values or {}))
    var_offset, session_offset, buf_offset = 112, 16384, 65536
    row, layout, at = bytearray(1024), [], 0
    for name, (kind, value) in values.items():
        size = 8 if kind == 5 else 1 if kind == 1 else 4
        at = (at + size - 1) // size * size
        struct.pack_into("<" + CODES[kind], row, at, value)
        layout.append((kind, at, name))
        at += size
    data = bytearray(buf_offset + 3 * len(row))
    raw = session.encode("utf-8")
    struct.pack_into("<10i", data, 0, 2, 1 if connected else 0, 60, 5, 0x20000, session_offset,
                     len(layout), var_offset, 3, len(row))
    for i, (kind, offset, name) in enumerate(layout):
        struct.pack_into("<3i?3x32s64s32s", data, var_offset + 144 * i, kind, offset, 1, False, name.encode(), b"", b"")
    data[session_offset:session_offset + len(raw)] = raw
    for i in range(3):                                   # buffer 1 holds the newest tick
        struct.pack_into("<4i", data, 48 + 16 * i, tick - 1 if i != 1 else tick, buf_offset + len(row) * i, 0, 0)
    data[buf_offset + len(row):buf_offset + 2 * len(row)] = row
    return Memory(data)


def read(values=None, **kw):
    img = ir.Image(image(values, **kw))
    head = img.header()
    img.load_vars(head)
    img.load_session(head)
    tick, row = img.row(head)
    return img, tick, row


class Session(unittest.TestCase):
    def test_session_info(self):
        s = ir.parse_session(SESSION)
        self.assertEqual(s["car"], "Porsche 911 GT3 R (992)")          # the player's car, not car 0
        self.assertEqual(s["track"], "Oulton Park Circuit - International")
        self.assertEqual(s["track_length_m"], 4330.0)                  # the official length when given
        self.assertEqual((s["redline"], s["shift_rpm"], s["gears"], s["fuel_max"]), (9500.0, 9250.0, 6, 120.0))
        y = ir.parse_yaml(SESSION)
        self.assertEqual(y["SessionInfo"]["Sessions"][0]["ResultsFastestLap"][0]["CarIdx"], "255")
        self.assertEqual(y["SessionInfo"]["Sessions"][0]["ResultsPositions"], {})


class Parse(unittest.TestCase):
    def test_image_and_values(self):
        img, tick, row = read()
        self.assertEqual(tick, 7)
        v = ir.parse(img, row)
        self.assertEqual((v["gear"], v["rpm"], v["rpm_max"]), (4, 9300, 9500))
        self.assertTrue(v["shift_up"])                                 # above DriverCarSLShiftRPM
        self.assertEqual(v["speed_kmh"], 180.0)
        self.assertEqual((v["tc_level"], v["abs_level"], v["brake_bias"]), (3, 5, 0.545))
        self.assertIsNone(v["tc_cut_level"])                           # not on this car
        self.assertTrue(v["abs_active"] and v["pit_limiter"])
        self.assertEqual(v["warn_oil"], "alert")
        self.assertEqual(v["steer"], 0.25)
        self.assertEqual((v["lap_pos"], v["track_length_m"]), (0.25, 4330.0))
        self.assertEqual((v["lap_ms"], v["last_ms"]), (23500, 92250))
        self.assertEqual(v["time_of_day"], "14:00")
        self.assertEqual(v["status"], "live")
        self.assertTrue(v["lap_valid"])
        self.assertEqual(v["session_id"], "0-0-0")
        self.assertEqual((v["boost_bar"], v["boost_min_bar"]), (-0.613, -1.0))    # vacuum
        self.assertTrue(set(v) <= set(telemetry.FIELDS), set(v) - set(telemetry.FIELDS))
        self.assertIsNone(telemetry.check(dict(telemetry.blank(), **v, connected=True)))

    def test_states(self):
        img, _, row = read({"IsOnTrack": (1, False)})
        self.assertEqual(ir.parse(img, row)["status"], "off")          # garage, menus: NOT ON TRACK
        img, _, row = read({"IsReplayPlaying": (1, True)})
        self.assertEqual(ir.parse(img, row)["status"], "replay")
        img, _, row = read({"PlayerTrackSurface": (2, 0)})
        self.assertFalse(ir.parse(img, row)["lap_valid"])               # four wheels off
        img, _, row = read({"dcBrakeBias": (4, 0.0)})
        self.assertIsNone(ir.parse(img, row)["brake_bias"])

    def test_disconnected(self):
        img = ir.Image(image(connected=False))
        self.assertFalse(img.header()["status"] & ir.CONNECTED)


class MapPosition(unittest.TestCase):
    def test_dead_reckoning(self):
        m = ir.Map()
        self.assertEqual(m.step(10.0, 0.5, 50.0, 0.0, 0.0), (0.0, 0.0))
        self.assertEqual(m.step(11.0, 0.51, 50.0, 0.0, 0.0), (0.0, -50.0))       # north: up on the map
        self.assertEqual(m.step(12.0, 0.52, 10.0, 0.0, math.pi / 2), (10.0, -50.0))   # heading east
        self.assertEqual(m.step(13.0, 0.95, 0.0, 10.0, math.pi / 2), (10.0, -60.0))   # sliding left (north)
        self.assertEqual(m.step(13.1, 0.01, 50.0, 0.0, 0.0), (0.0, -5.0))         # over the line: from 0 / 0
        self.assertEqual(m.step(20.0, 0.02, 50.0, 0.0, 0.0), (0.0, -5.0))         # a gap (pause): no jump


if __name__ == "__main__":
    unittest.main()
