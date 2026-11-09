"""tools/live.py: the GRIP stages (the same as the page's) and the check of a recording.

Run: python -m unittest discover tests
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("live", ROOT / "tools" / "live.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def frames(brake_slip: float) -> list:
    base = {"connected": True, "error": None, "game": "ace", "car": "Test", "track": "Test", "speed_kmh": 150.0,
            "gear": 3, "rpm": 7000, "abs_level": 3, "tc_level": 2}
    out = []
    for i in range(40):
        braking = i < 20
        out.append(dict(base, _t=i * 0.05, brake=1.0 if braking else 0.0, gas=0.0 if braking else 1.0,
                        abs_active=braking and i > 2,
                        wheel_slip=[brake_slip, brake_slip / 2, 0.0, 0.0] if braking else [0.0, 0.0, 0.15, 0.1],
                        wheel_lock=[False] * 4))
    return out


def check(rows: list) -> str:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "live-test.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            live.check(path)
        return out.getvalue()


class Live(unittest.TestCase):
    def test_stages_follow_the_page(self):
        self.assertEqual(live.STAGES, [0.04, 0.07, 0.15, 0.4])          # read from ui/js/grip.js
        self.assertEqual([live.stage(v) for v in (0.0, -0.05, -0.08, 0.2, 0.45, None)], ["", "l1", "l2", "s3", "s4", ""])
        self.assertEqual(live.stage(-0.01, True), "l4")                  # the game's lock flag

    def test_check(self):
        text = check(frames(-0.13))
        self.assertIn("sign OK", text)
        self.assertIn("ABS: setting 3; working in 17 frames; slip when it starts: median 0.130", text)
        self.assertNotIn("!!", text)
        self.assertIn("!! the slip is mostly POSITIVE under braking", check(frames(0.13)))


if __name__ == "__main__":
    unittest.main()
