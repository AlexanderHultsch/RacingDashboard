"""The coach's checks (core/coach.py): value combinations evaluated by Python, gently, relative to the car.

Run: python -m unittest discover tests
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import coach  # noqa: E402

LIMITS = {"lat_g": 1.6, "brake_g": 1.5, "accel_g": 0.6, "combined_g": 1.6, "combined_by_speed": {"80-120": 1.4, "120-160": 1.6}}
CORNER = {"type": "medium corner", "turn": math.radians(90)}


def row(d, t, v, thr=0.0, brk=0.0, steer=0.0, g_lat=0.0, g_long=0.0, sa=(None, None), sr=(None, None), out=None,
        tc=None, abs_on=None, beta=None):
    """One section row as recorder.section sends it (27 columns)."""
    return [d, t, v, thr, brk, steer, 3, None, None, tc, abs_on, None, None, None, None, None, None, 6000,
            g_lat, g_long, None, beta, sa[0], sa[1], sr[0], sr[1], out]


def corner(brake_g=-1.45, coast_m=0, lock=False, lift=False, noise=False, trail=True):
    """A 250 m corner: full throttle, braking from 40 m, turn-in, apex at 130 m, exit on the throttle."""
    rows, t = [], 0.0
    for d in range(0, 251, 2):
        if d < 40:
            r = dict(v=150, thr=1.0)
        elif d < 40 + coast_m:
            r = dict(v=148, thr=0.0)
        elif d < 100:
            r = dict(v=150 - (d - 40) * 0.9, brk=0.9, g_long=brake_g, steer=0.25 if (trail and d >= 80) else 0.0,
                     g_lat=0.4 if d >= 80 else 0.0, sr=(-0.6 if lock and 60 <= d < 70 else -0.07, 0.0))
        elif d < 130:
            r = dict(v=95, brk=0.1 if trail and d < 110 else 0.0, thr=0.0 if trail and d < 110 else 0.15,
                     steer=0.5, g_lat=1.3, sa=(4.0, 3.6))                 # a light throttle at the apex
        else:
            thr = 0.3 + (d - 130) * 0.01
            if lift and 170 <= d < 180:
                thr = 0.1
            if noise and d % 4 == 0:
                thr -= 0.15                                   # a wobbling foot: not a lift
            r = dict(v=95 + (d - 130) * 0.4, thr=min(1.0, thr), steer=max(0.0, 0.5 - (d - 130) * 0.01),
                     g_lat=1.2, g_long=0.4, sa=(3.2, 3.0), sr=(0.0, 0.05))
        rows.append(row(d, round(t, 3), **r))
        t += 2 / (r["v"] / 3.6)
    return rows


class Reference(unittest.TestCase):
    def test_grip_reference(self):
        self.assertEqual(coach.grip_reference(LIMITS, 100), 1.4)            # the band of this speed
        self.assertEqual(coach.grip_reference(LIMITS, 200), 1.6)            # no band: the nearest below
        self.assertAlmostEqual(coach.grip_reference(LIMITS, 30), 1.4)       # nothing below: the nearest above
        weak = dict(LIMITS, combined_by_speed={"40-80": 0.5, "120-160": 1.6})
        self.assertAlmostEqual(coach.grip_reference(weak, 60), 0.96)        # never below 60 % of the peak
        self.assertEqual(coach.grip_reference({"combined_g": 1.6}, 60), 1.6)  # no bands: the overall peak
        self.assertIsNone(coach.grip_reference(None, 60))


class Checks(unittest.TestCase):
    def run_checks(self, rows, best=None, kind=None):
        return coach.evaluate(rows, best, None, dict(CORNER, type=kind or CORNER["type"]), LIMITS, None)

    def test_a_clean_corner(self):
        r = self.run_checks(corner())
        self.assertEqual(r["G1"]["result"], "yes")                          # 1.45 g of 1.6: braking at the limit
        self.assertEqual(r["G2"]["result"], "yes")                          # brake and steering overlap
        for code in ("B1", "B3", "B4", "B5", "X4"):
            self.assertEqual(r[code]["result"], "no", code)

    def test_soft_braking(self):
        r = self.run_checks(corner(brake_g=-0.8))
        self.assertEqual(r["G1"]["result"], "no")
        self.assertEqual(r["B1"]["result"], "yes")
        self.assertEqual(r["B1"]["strength"], "clear")                      # 0.8 of 1.6: half the car's grip

    def test_lock_and_coasting(self):
        r = self.run_checks(corner(lock=True, coast_m=16))
        self.assertEqual((r["B3"]["result"], r["B3"]["strength"]), ("yes", "slight"))
        self.assertEqual((r["B4"]["result"], r["B4"]["strength"]), ("yes", "slight"))
        self.assertEqual((r["B4"]["from_m"], r["B4"]["to_m"]), (40, 56))
        fast = self.run_checks(corner(coast_m=16), kind="fast corner")
        self.assertEqual(fast["B4"]["result"], "no")                        # a short lift in a fast corner is fine

    def test_no_trail_braking(self):
        r = self.run_checks(corner(trail=False))
        self.assertEqual(r["G2"]["result"], "no")

    def test_lift_and_noise(self):
        self.assertEqual(self.run_checks(corner(lift=True))["X4"]["result"], "yes")
        self.assertEqual(self.run_checks(corner(noise=True))["X4"]["result"], "no")   # wobbles are not lifts

    def test_estimate_is_gentle(self):
        slow = corner(coast_m=30)
        t = 0.0
        for a, b in zip(slow, slow[1:]):                          # and 10 % slower from the coasting on
            b[2] = b[2] * (0.9 if b[0] >= 40 else 1.0)
            t += (b[0] - a[0]) / (b[2] / 3.6)
            b[1] = round(t, 3)
        r = self.run_checks(slow, corner())
        lost = coach.Section(slow, corner(), None, 1.0, LIMITS, None).loss(30, 80)
        self.assertGreater(lost, 0)
        self.assertLessEqual(r["B4"]["est_s"], min(coach.CAP_S, lost * 0.5) + 0.05)
        self.assertNotIn("est_s", self.run_checks(slow)["B4"])              # no BEST: no estimate

    def test_not_applicable(self):
        plain = [r[:18] for r in corner()]                                  # a lap recorded without motion values
        r = coach.evaluate(plain, None, None, CORNER, None, None)
        self.assertEqual(r["G1"]["result"], "n/a")
        self.assertEqual(r["B4"]["result"], "no")                           # pedals alone still say this
        straight = coach.evaluate(corner(), None, None, {"type": "straight", "turn": 0.0}, LIMITS, None)
        self.assertEqual(straight["G3"]["result"], "n/a")
        self.assertEqual(coach.evaluate([], None), {})

    def test_brief(self):
        r = self.run_checks(corner(coast_m=16))
        full, found = coach.brief(r), coach.brief(r, found_only=True)
        self.assertEqual(full["G1"].split(" · ")[0], "yes")
        self.assertEqual(full["B1"], "no")
        self.assertTrue(found["B4"].startswith("yes · slight · 40-56 m"))
        self.assertNotIn("B1", found)                                       # only what was found
        self.assertIn("G1", found)                                          # the good checks always
        self.assertEqual(set(coach.RULES), set(coach.CHECKS))


if __name__ == "__main__":
    unittest.main()
