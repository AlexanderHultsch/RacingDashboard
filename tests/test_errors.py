"""The data checks of the core (core/telemetry.py): which frames the pages show as E.

Run: python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

import telemetry  # noqa: E402

GOOD = {"connected": True, "status": "live", "gear": 3, "rpm": 6500, "rpm_max": 8000, "rpm_pct": 0.81, "speed_kmh": 150.0}


def frame(**changes):
    values = dict(GOOD)
    values.update(changes)
    return telemetry.with_error(values, failed=False)


class Errors(unittest.TestCase):
    def test_good_data_has_no_error(self):
        result = frame()
        self.assertIsNone(result["error"])
        self.assertEqual(result["error_text"], "")
        self.assertEqual(result["gear"], 3)

    def test_game_not_running_and_read_error(self):
        self.assertEqual(telemetry.with_error(None, failed=False)["error"], "no_game")
        self.assertEqual(telemetry.with_error(None, failed=True)["error"], "read_error")

    def test_no_new_data_and_not_driving(self):
        self.assertEqual(frame(connected=False)["error"], "no_data")
        self.assertEqual(frame(status="off")["error"], "not_driving")
        self.assertIsNone(frame(status="replay")["error"])

    def test_unexpected_values(self):
        cases = {
            "GEAR 25": dict(gear=25),
            "GEAR -2": dict(gear=-2),
            "GEAR 2.5": dict(gear=2.5),
            "GEAR MISSING": dict(gear=None),
            "RPM -5": dict(rpm=-5),
            "RPM NOT A NUMBER": dict(rpm=float("nan")),
            "RPM_PCT 3": dict(rpm_pct=3.0),
            "SPEED_KMH 900": dict(speed_kmh=900.0),
            "RPM 20000 ABOVE MAX 8000": dict(rpm=20000),
            "GEAR MODE X": dict(gear_mode="X"),
        }
        for text, changes in cases.items():
            result = frame(**changes)
            self.assertEqual(result["error"], "bad_value", text)
            self.assertEqual(result["error_text"], "UNEXPECTED DATA: " + text)

    def test_gear_modes(self):
        for mode in (None, "P", "D", "S", "B", "L", "M"):
            self.assertIsNone(frame(gear_mode=mode)["error"], mode)

    def test_gear_ten_is_valid_data(self):
        # a 10-speed gearbox is real; only the one-digit display shows E (a page notice, not a data error)
        self.assertIsNone(frame(gear=10)["error"])

    def test_bad_values_win_over_stale(self):
        self.assertEqual(frame(connected=False, rpm=-1)["error"], "bad_value")


if __name__ == "__main__":
    unittest.main()
