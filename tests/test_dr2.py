"""DiRT Rally 2.0 connector: packet decoding, the game's UDP setting, a real UDP round trip.

Run: python -m unittest discover tests
"""
import importlib.util
import socket
import struct
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import config  # noqa: E402
import log  # noqa: E402
import telemetry  # noqa: E402

spec = importlib.util.spec_from_file_location("dr2_connector", ROOT / "games" / "dr2" / "connector.py")
dr2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr2)


def packet(**values) -> bytes:
    """A 264-byte extradata=3 packet with the given fields (byte offset -> value)."""
    floats = [0.0] * 66
    fields = {"lap_time": 4, "lap_distance": 8, "speed": 28, "throttle": 116, "brake": 124, "gear": 132,
              "rpm": 148, "length": 244, "last": 248, "max_rpm": 252, "idle_rpm": 256, "max_gears": 260,
              "wheel_rl": 100, "wheel_rr": 104, "wheel_fl": 108, "wheel_fr": 112}
    for name, value in values.items():
        floats[fields[name] // 4] = value
    return struct.pack("<66f", *floats)


class Parse(unittest.TestCase):
    def test_values(self):
        v = dr2.parse(packet(lap_time=83.456, lap_distance=2500, length=10000, speed=25.0, throttle=0.8,
                             gear=3.0, rpm=6200, max_rpm=8000, max_gears=6, last=0))
        self.assertEqual(v["gear"], 3)
        self.assertEqual((v["rpm"], v["rpm_max"]), (6200, 8000))
        self.assertFalse(v["shift_up"])
        self.assertTrue(dr2.parse(packet(gear=3.0, rpm=7600, max_rpm=8000, max_gears=6))["shift_up"])
        self.assertFalse(dr2.parse(packet(gear=6.0, rpm=7600, max_rpm=8000, max_gears=6))["shift_up"])   # top gear
        self.assertAlmostEqual(v["rpm_pct"], 0.775, places=3)
        self.assertEqual(v["speed_kmh"], 90.0)
        self.assertEqual(v["lap_ms"], 83456)
        self.assertEqual(v["lap_progress"], 0.25)
        self.assertIsNone(v["last_ms"])
        self.assertTrue(set(v) <= set(telemetry.FIELDS))
        self.assertIsNone(telemetry.check(dict(telemetry.blank(), **v, connected=True)))

    def test_wheel_slip(self):
        v = dr2.parse(packet(speed=20.0, wheel_fl=0.0, wheel_fr=18.0, wheel_rl=20.0, wheel_rr=26.0))
        self.assertEqual(v["wheel_slip"], [-1.0, -0.1, 0.0, 0.3])          # front left locked, rear right spinning
        slow = dr2.parse(packet(speed=1.0, wheel_fl=1.0, wheel_fr=1.0, wheel_rl=4.0, wheel_rr=1.0))
        self.assertEqual(slow["wheel_slip"][2], 1.0)                        # below 3 m/s the car counts as 3 m/s
        self.assertIsNone(dr2.parse(packet(speed=20.0))["wheel_slip"])      # no wheel speeds

    def test_stage_and_car_names(self):
        v = dr2.parse(packet(length=10012.4, max_rpm=7500, idle_rpm=900, max_gears=5))
        self.assertEqual((v["track"], v["car"]), ("Stage 10.01 km", "5-speed, 7500 rpm, idle 900"))
        tenths = dr2.parse(packet(length=4800, max_rpm=750, idle_rpm=90, max_gears=6))     # rpm sent as tenths
        self.assertEqual(tenths["car"], "6-speed, 7500 rpm, idle 900")
        self.assertEqual((dr2.parse(packet())["track"], dr2.parse(packet())["car"]), ("", ""))   # menus / no data

    def test_rpm_sent_as_tenths(self):
        v = dr2.parse(packet(rpm=620, max_rpm=800, gear=2.0))
        self.assertEqual((v["rpm"], v["rpm_max"]), (6200, 8000))

    def test_reverse_and_neutral(self):
        self.assertEqual(dr2.parse(packet(gear=-1.0))["gear"], -1)
        self.assertEqual(dr2.parse(packet(gear=10.0, max_gears=6))["gear"], -1)
        self.assertEqual(dr2.parse(packet(gear=0.0))["gear"], 0)


class Config(unittest.TestCase):
    def test_check(self):
        good = '<config><motion_platform><udp enabled="true" extradata="3" ip="127.0.0.1" port="20777" delay="1" /></motion_platform></config>'
        self.assertIsNone(dr2.check_config(good, 20777))
        self.assertIn("enabled", dr2.check_config(good.replace('enabled="true"', 'enabled="false"'), 20777))
        self.assertIn("extradata", dr2.check_config(good.replace('extradata="3"', 'extradata="0"'), 20777))
        self.assertIn("port", dr2.check_config(good, 20888))
        self.assertIn("no <udp", dr2.check_config("<config/>", 20777))


class Udp(unittest.TestCase):
    def test_round_trip(self):
        cfg = config.load(Path("/nonexistent"))
        cfg["log"]["enabled"] = False
        log.setup(cfg["log"])
        connector = dr2.Connector({"id": "dr2", "udp": {"port": 0}}, cfg)
        connector.open()
        try:
            self.assertIsNone(connector.read())                      # nothing received yet
            port = connector.sock.getsockname()[1]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(b"short", ("127.0.0.1", port))               # too short: ignored
                s.sendto(packet(gear=4.0, rpm=5000, max_rpm=8000), ("127.0.0.1", port))
            time.sleep(0.1)
            values = connector.read()
            self.assertEqual(values["gear"], 4)
            self.assertTrue(values["connected"])
        finally:
            connector.close()


if __name__ == "__main__":
    unittest.main()
