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
        gr.status, gr.rpm_percent, gr.is_change_up_rpm = 2, 0.9, True
        gr.electronics.tc_level, gr.electronics_is_modifiable.tc_level = 3, 1
        gr.electronics.abs_level, gr.electronics_is_modifiable.abs_level = 2, 0
        gr.instrumentation.main_light_stage = 1
        gr.fuel_liter_current_quantity, gr.max_fuel, gr.fuel_liter_per_lap = 41.2, 100.0, 2.9
        gr.current_lap_time_ms, gr.last_laptime_ms = 65432, 101234
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

    def test_fixed_and_missing_settings(self):
        # BMW M4 CSL as read in the game: ABS fixed at 1, TC 0..10 adjustable, TC cut / engine map absent
        ph, gr, st = self.build()
        gr.electronics.tc_level, gr.electronics_max_limit.tc_level, gr.electronics_is_modifiable.tc_level = 3, 10, 1
        gr.electronics.abs_level, gr.electronics_min_limit.abs_level, gr.electronics_max_limit.abs_level = 1, 1, 1
        gr.electronics_is_modifiable.abs_level = 0
        gr.electronics.front_bump_damper_level = -108                 # garbage in an unused field stays unused
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["abs_level"], 1)
        self.assertEqual(values["fixed"], ["abs_level"])
        self.assertEqual(values["limits"], {"tc_level": [0, 10]})
        self.assertIsNone(values["tc_cut_level"])
        self.assertIsNone(values["engine_map"])
        self.assertIsNone(values["diff_power"])
        self.assertIsNone(values["diff_power_pct"])               # nothing sent
        gr.diff_power_raw_value, gr.diff_coast_raw_value = 0.25, 0.55
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["diff_power_pct"], values["diff_coast_pct"]), (0.25, 0.55))
        self.assertIsNone(telemetry.check(values))

    def test_engine_map_counts_from_one(self):
        # Porsche 992 GT3 R: ACE sends map 0..2, the car shows 1..3
        ph, gr, st = self.build()
        gr.electronics.engine_map_level, gr.electronics_max_limit.engine_map_level = 2, 2
        gr.electronics_is_modifiable.engine_map_level = 1
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["engine_map"], values["limits"]["engine_map"]), (3, [1, 3]))

    def test_tyres_and_drive_mode(self):
        ph, gr, st = self.build()
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertIsNone(values["tyre_temp_c"])                     # nothing sent: no tyre values
        self.assertIsNone(values["drive_mode"])
        for block, temp, pressure in ((gr.tyre_lf, 86.0, 27.4), (gr.tyre_rf, 104.0, 28.6),
                                      (gr.tyre_lr, 61.0, 25.9), (gr.tyre_rr, 79.0, 26.8)):
            block.tyre_temperature_c, block.tyre_pressure = temp, pressure
        # BMW M4 CSL as read in the game: performance mode 0, range 0..2, modifiable, named SPORT+
        gr.electronics.active_performance_mode, gr.electronics_max_limit.active_performance_mode = 0, 2
        gr.electronics_is_modifiable.active_performance_mode = 1
        gr.performance_mode_name = b"SPORT+"
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["tyre_temp_c"], [86.0, 104.0, 61.0, 79.0])
        self.assertEqual(values["tyre_psi"], [27.4, 28.6, 25.9, 26.8])
        self.assertIsNone(values["tyre_core_score"])                 # no scores sent: the card's own colours
        # Camaro ZL1 after burnouts: surface 2.0 (left / centre / right), core still 1.0 on the fronts
        for block, core, l, c, r in ((gr.tyre_lf, 1.0, 1.24, 1.21, 1.22), (gr.tyre_rf, 1.0, 1.0, 1.0, 1.0),
                                     (gr.tyre_lr, 1.81, 2.0, 2.0, 2.0), (gr.tyre_rr, 2.4, 1.97, 1.99, 2.0)):
            block.tyre_normalized_temperature_core = core
            block.tyre_normalized_temperature_left, block.tyre_normalized_temperature_center = l, c
            block.tyre_normalized_temperature_right = r
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["tyre_core_score"], [1.0, 1.0, 1.81, 2.0])
        self.assertEqual(values["tyre_surface_score"], [1.24, 1.0, 2.0, 2.0])
        self.assertIsNone(values["brake_temp_c"])                    # no brake temperatures sent yet
        gr.tyre_lf.brake_temperature_c, gr.tyre_rf.brake_temperature_c = 420.4, 415.0
        gr.tyre_lr.brake_temperature_c, gr.tyre_rr.brake_temperature_c = 180.0, 176.6
        self.assertEqual(ace.parse(bytes(ph), bytes(gr), bytes(st))["brake_temp_c"], [420, 415, 180, 177])
        self.assertEqual(ace.parse(bytes(ph), bytes(gr), bytes(st))["brake_score"], [0.0, 0.0, 0.0, 0.0])   # cold: a real 0
        gr.tyre_lf.brake_normalized_temperature, gr.tyre_lr.brake_normalized_temperature = 1.0, 0.117   # 420 C, 179 C
        self.assertEqual(ace.parse(bytes(ph), bytes(gr), bytes(st))["brake_score"], [1.0, 0.0, 0.12, 0.0])
        self.assertEqual((values["drive_mode"], values["drive_mode_name"]), (0, "SPORT+"))
        self.assertEqual(values["limits"]["drive_mode"], [0, 2])
        gr.tyre_lf.tyre_pressure = 1.89                              # bar: shown in psi
        self.assertEqual(ace.parse(bytes(ph), bytes(gr), bytes(st))["tyre_psi"][0], 27.4)
        gr.electronics_max_limit.active_performance_mode, gr.electronics_is_modifiable.active_performance_mode = 0, 0
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))         # a car without modes: the old name is ignored
        self.assertEqual((values["drive_mode"], values["drive_mode_name"]), (None, None))
        self.assertIsNone(telemetry.check(values))

    def test_boost(self):
        ph, gr, st = self.build()
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))      # no turbo or off the throttle: just 0
        self.assertEqual((values["boost_bar"], values["boost_max_bar"]), (0.0, None))
        gr.turbo_boost, gr.max_turbo_boost = 0.389, 157.434       # Camaro ZL1: max_turbo_boost in no usable unit
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["boost_bar"], values["boost_min_bar"], values["boost_max_bar"]), (0.389, 0.0, None))

    def test_damage(self):
        ph, gr, st = self.build()
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["damage_body"], values["damage_suspension"]), ([0.0] * 5, [0.0] * 4))
        # Camaro ZL1 after a front and a rear hit
        for i, v in enumerate((1.0, 1.0, 0.8796, 0.0, 1.0, 0.9132, 0.0, 0.5841, 0.0)):
            gr.car_damage.damage[i] = v
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["damage_body"], [1.0, 1.0, 0.88, 0.0, 1.0])
        self.assertEqual(values["damage_suspension"], [0.913, 0.0, 0.584, 0.0])

    def test_wheel_slip_and_lock(self):
        ph, gr, st = self.build()
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual((values["wheel_slip"], values["wheel_lock"]), (None, None))   # not filled: GRIP shows NO DATA
        ph.slipRatio[0], ph.slipRatio[1], ph.slipRatio[2], ph.slipRatio[3] = -1.0, -0.13, 0.0, 0.25
        gr.tyre_lf.lock = True
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertEqual(values["wheel_slip"], [-1.0, -0.13, 0.0, 0.25])
        self.assertEqual(values["wheel_lock"], [True, False, False, False])

    def test_lights_and_wipers_unreported_until_seen(self):
        reported = set()
        values = {"lights": 0, "wipers": 0}
        ace.unreported(values, reported)
        self.assertEqual(values, {"lights": None, "wipers": None})       # ACE 0.9.1 always sends 0
        values = {"lights": 2, "wipers": 0}
        ace.unreported(values, reported)
        self.assertEqual(values, {"lights": 2, "wipers": None})
        values = {"lights": 0, "wipers": 0}
        ace.unreported(values, reported)
        self.assertEqual(values["lights"], 0)                            # seen once: 0 is a real OFF now

    def test_auto_gear_assist_keeps_the_gear_number(self):
        ph, gr, st = self.build()
        gr.assists_state.flags[0] = 1                   # auto_gear assist: a manual gearbox shifted for the driver
        values = ace.parse(bytes(ph), bytes(gr), bytes(st))
        self.assertIsNone(values["gear_mode"])
        self.assertEqual(values["gear"], 3)

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
