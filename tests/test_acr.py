"""Assetto Corsa Rally connector: the ACC layout and the translation, without the game.

Run: python -m unittest discover tests
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import telemetry  # noqa: E402
from kunos import Physics  # noqa: E402

spec = importlib.util.spec_from_file_location("acr_connector", ROOT / "games" / "acr" / "connector.py")
acr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acr)


def put(field, value: str):
    for i, ch in enumerate(value):
        field[i] = ord(ch)


def build():
    ph, gr, st = Physics(), acr.Graphics(), acr.Static()
    ph.packetId, ph.gear, ph.rpms, ph.speedKmh, ph.gas, ph.clutch = 9, 4, 6200, 112.3, 0.8, 1.0
    ph.steerAngle, ph.brakeBias, ph.airTemp, ph.roadTemp, ph.fuel, ph.tc = -0.5, 0.58, 291.15, 300.15, 40.0, 1.0
    ph.currentMaxRpm = 7800
    put(gr.currentTime, "01:02.345")
    gr.distanceTraveled, gr.TC, gr.ABS = 2500.0, 3, 0
    gr.carCoordinates[0][0], gr.carCoordinates[0][2] = 120.5, -340.25
    put(st.carModel, "Lancia Delta HF Integrale")
    put(st.track, "Afon Bidno")
    st.trackSplineLength = 10000.0
    return ph, gr, st


class Layout(unittest.TestCase):
    def test_acc_offsets(self):
        # ACC SPageFileGraphic / SPageFileStatic offsets (sequential reading, UTF-16 strings, 4-byte alignment)
        self.assertEqual(acr.Graphics.completedLaps.offset, 132)
        self.assertEqual(acr.Graphics.distanceTraveled.offset, 156)
        self.assertEqual(acr.Graphics.carCoordinates.offset, 256)
        self.assertEqual(acr.Static.track.offset, 134)
        self.assertEqual(acr.Static.maxRpm.offset, 412)
        self.assertEqual(acr.Static.trackSplineLength.offset, 520)


class Parse(unittest.TestCase):
    def test_values(self):
        ph, gr, st = build()
        v = acr.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((v["gear"], v["rpm"], v["rpm_max"]), (3, 6200, 7800))     # ACC 4 = 3rd; max from physics
        self.assertEqual(v["speed_kmh"], 112.3)
        self.assertEqual(v["clutch"], 0.0)                     # ACR 1.0 = pedal up
        self.assertEqual((v["car"], v["track"]), ("Lancia Delta HF Integrale", "Afon Bidno"))
        self.assertEqual(v["lap_ms"], 62345)
        self.assertEqual((v["lap_pos"], v["track_length_m"]), (0.25, 10000.0))
        self.assertEqual((v["pos_x"], v["pos_y"]), (120.5, -340.25))
        self.assertEqual((v["tc_level"], v["abs_level"], v["brake_bias"]), (3, 0, 0.58))
        self.assertTrue(v["tc_active"])
        self.assertEqual((v["air_c"], v["road_c"]), (18.0, 27.0))        # Kelvin -> Celsius
        self.assertEqual(v["steer"], -0.5)
        self.assertEqual(v["status"], "live")
        self.assertTrue(set(v) <= set(telemetry.FIELDS), set(v) - set(telemetry.FIELDS))
        self.assertIsNone(telemetry.check(dict(telemetry.blank(), **v, connected=True)))

    def test_paused_and_clock(self):
        ph, gr, st = build()
        ph.rpms = ph.gear = 0
        ph.speedKmh = ph.gas = ph.brake = 0.0
        self.assertEqual(acr.parse(bytes(ph), bytes(gr), bytes(st))["status"], "pause")
        for raw, ms in (("00:11.596", 11596), ("1:02:03.004", 3723004), ("00:00.000", None), ("", None), ("--:--", None)):
            field = acr.Graphics().currentTime
            put(field, raw)
            self.assertEqual(acr.clock_ms(field), ms, raw)

    def test_boost(self):
        ph, gr, st = build()
        self.assertEqual(acr.parse(bytes(ph), bytes(gr), bytes(st))["boost_bar"], 0.0)  # Lancia: no turbo, just 0
        ph.turboBoost, st.maxTurboBoost = 0.9, 1.4
        values = acr.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["boost_bar"], values["boost_max_bar"]), (0.9, 1.4))

    def test_wheel_slip(self):
        ph, gr, st = build()
        self.assertIsNone(acr.parse(bytes(ph), bytes(gr), bytes(st))["wheel_slip"])
        ph.slipRatio[2], ph.slipRatio[3] = 0.4, 9.0                         # far too fast: capped at 3
        values = acr.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["wheel_slip"], [0.0, 0.0, 0.4, 3.0])
        self.assertNotIn("wheel_lock", values)                              # ACR has no lock flag

    def test_static_rpm_wins(self):
        ph, gr, st = build()
        st.maxRpm = 8000
        self.assertEqual(acr.parse(bytes(ph), bytes(gr), bytes(st))["rpm_max"], 8000)


if __name__ == "__main__":
    unittest.main()
