"""ACE connector: struct layout and translation to the universal telemetry, without the game.

Run: python -m unittest discover tests
"""
import importlib.util
import sys
import unittest
from ctypes import sizeof
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import telemetry  # noqa: E402

spec = importlib.util.spec_from_file_location("ace_connector", ROOT / "games" / "ace" / "connector.py")
ace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ace)


class Layout(unittest.TestCase):
    def test_physics_offsets_match_the_documentation(self):
        # Offsets from the ACE / ACC shared memory documentation.
        expected = {"gear": 16, "rpms": 20, "speedKmh": 28, "tc": 204, "pitLimiterOn": 248, "clutch": 364,
                    "brakeBias": 564, "currentMaxRpm": 588, "tcInAction": 672, "ignitionOn": 772}
        for name, offset in expected.items():
            self.assertEqual(getattr(ace.Physics, name).offset, offset, name)
        self.assertEqual(sizeof(ace.Physics), 800)


class Parse(unittest.TestCase):
    def build(self):
        ph, gr, st = ace.Physics(), ace.Graphics(), ace.Static()
        ph.packetId, ph.gear, ph.rpms, ph.currentMaxRpm, ph.speedKmh = 7, 4, 7200, 8000, 187.46
        ph.gas, ph.brakeBias, ph.pitLimiterOn = 1.0, 0.565, 0
        gr.status, gr.rpm_percent, gr.is_change_up_rpm, gr.max_gears = 2, 0.9, True, 6
        gr.electronics.tc_level, gr.electronics_is_modifiable.tc_level = 3, 1
        gr.electronics.abs_level, gr.electronics_is_modifiable.abs_level = 2, 0
        gr.instrumentation.main_light_stage = 1
        gr.fuel_liter_current_quantity, gr.max_fuel, gr.fuel_liter_per_lap = 41.2, 100.0, 2.9
        gr.current_lap_time_ms, gr.last_laptime_ms, gr.best_laptime_ms = 65432, 101234, 0
        gr.total_lap_count, gr.current_pos, gr.total_drivers = 3, 5, 20
        gr.car_model = b"Porsche 992 GT3 R"
        st.track = b"Monza"
        return ph, gr, st

    def test_parse(self):
        ph, gr, st = self.build()
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["gear"], 3)               # ACE 4 = 3rd gear
        self.assertEqual(values["rpm"], 7200)
        self.assertEqual(values["rpm_max"], 8000)
        self.assertAlmostEqual(values["rpm_pct"], 0.9, places=4)
        self.assertTrue(values["shift_up"])
        self.assertEqual(values["speed_kmh"], 187.5)
        self.assertEqual(values["tc_level"], 3)
        self.assertIsNone(values["abs_level"])           # not adjustable in this car
        self.assertEqual(values["brake_bias"], 0.565)
        self.assertEqual(values["lights"], 1)
        self.assertEqual(values["fuel_l"], 41.2)
        self.assertEqual(values["last_ms"], 101234)
        self.assertIsNone(values["best_ms"])
        self.assertIsNone(values["delta_ms"])
        self.assertEqual(values["car"], "Porsche 992 GT3 R")
        self.assertEqual(values["track"], "Monza")
        self.assertEqual(values["status"], "live")
        self.assertTrue(set(values) <= set(telemetry.FIELDS), set(values) - set(telemetry.FIELDS))

    def test_warning_lamps(self):
        ph, gr, st = self.build()
        gr.is_ignition_on, gr.is_engine_running = True, False          # ignition on, engine not started
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["warn_engine"], values["warn_oil"]), ("warn", "alert"))
        gr.is_engine_running, gr.oil_pressure_bar, gr.water_temperature_c, gr.handbrake_percent = True, 4.0, 40, 1.0
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["warn_engine"], values["warn_oil"], values["warn_coolant"], values["warn_brake"]),
                         ("off", "off", "cold", "alert"))
        gr.water_temperature_c, gr.handbrake_percent = 120, 0.0
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["warn_coolant"], values["warn_engine"], values["warn_brake"]), ("alert", "alert", "off"))
        gr.is_ignition_on = False
        self.assertEqual(ace.parse(bytes(ph), bytes(gr), bytes(st))["warn_coolant"], "off")

    def test_reverse_neutral_and_percent_guard(self):
        ph, gr, st = self.build()
        ph.gear, gr.rpm_percent = 0, 45.0
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["gear"], -1)
        self.assertAlmostEqual(values["rpm_pct"], 0.45, places=4)
        ph.gear, gr.rpm_percent = 1, 0.0
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["gear"], 0)
        self.assertAlmostEqual(values["rpm_pct"], 0.9, places=4)   # falls back to rpm / rpm_max


if __name__ == "__main__":
    unittest.main()
