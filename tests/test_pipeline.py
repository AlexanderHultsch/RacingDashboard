"""The analysis pipeline (core/pipeline.py, core/pipeline_rules.py): derived values, envelope, phases, rules,
fallbacks for missing fields, the session files, the non-blocking queue and the recovery of an open session.

Run: python -m unittest discover tests
"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import pipeline  # noqa: E402
import pipeline_rules as rules  # noqa: E402

LENGTH = 1000.0
HZ = 30


def profile(d, lockup=False, spin=False):
    """A 1000 m lap with one right-hand corner: straight, braking 300-400 m, corner 400-500 m, exit 500-600 m."""
    if d < 300:
        return dict(v=200, thr=1.0, brk=0.0, steer=0.0, lat=0.0, lon=0.2)
    if d < 400:
        k = (d - 300) / 100
        return dict(v=200 - 100 * k, thr=0.0, brk=0.9, steer=0.0, lat=0.0, lon=-1.4,
                    ratio=-0.4 if lockup and 330 <= d < 345 else -0.06)
    if d < 500:
        k = (d - 400) / 100
        return dict(v=100, thr=0.0, brk=max(0.0, 0.3 - k), steer=0.3, lat=1.5, lon=-0.4 * (1 - k), sa=(3.0, 2.8))
    if d < 600:
        k = (d - 500) / 100
        return dict(v=100 + 40 * k, thr=min(1.0, 0.2 + k), brk=0.0, steer=0.3 * (1 - k), lat=1.5 * (1 - k), lon=0.5,
                    sa=(2.5, 2.4), rear=0.3 if spin and 520 <= d < 540 else 0.05)
    k = (d - 600) / 400
    return dict(v=140 + 60 * k, thr=1.0, brk=0.0, steer=0.0, lat=0.0, lon=0.3)


def frames(laps=3, start=0.0, options=None, slip=True):
    """Telemetry frames (core/telemetry.py names) at HZ for the given number of laps, with the time stamps."""
    options = options or {}
    t, d, lap, out = 1000.0, start, 1, []
    while lap <= laps:
        p = profile(d, **options.get(lap, {}))
        frame = {"connected": True, "error": None, "status": "live", "track": "Test Ring", "car": "Test Car",
                 "session_id": "s1", "track_length_m": LENGTH, "lap_pos": d / LENGTH, "speed_kmh": p["v"],
                 "gas": p["thr"], "brake": p["brk"], "steer": p["steer"], "gear": 3 if p["v"] < 150 else 5,
                 "rpm": 7000, "g_lat": p["lat"], "g_long": p["lon"], "lap_valid": True, "shift_up": False,
                 "abs_active": False, "tc_active": False, "wheels_out": 0, "pos_x": d, "pos_y": 0.0}
        if slip:
            ratio, rear = p.get("ratio", 0.0), p.get("rear", 0.0)
            frame["wheel_slip"] = [ratio, ratio, rear or ratio, rear or ratio]
            sa = p.get("sa", (0.5, 0.5))
            frame["slip_angle"] = [sa[0], sa[0], sa[1], sa[1]]
        out.append((frame, t))
        t += 1 / HZ
        d += p["v"] / 3.6 / HZ
        if d >= LENGTH:
            d -= LENGTH
            lap += 1
    return out


def config(tmp: Path, **override):
    local = tmp / "local.toml"
    local.write_text("\n".join(f"[{s}]\n" + "\n".join(f"{k} = {v}" for k, v in kv.items()) for s, kv in override.items()))
    return rules.load_config(rules.DEFAULTS_FILE, local)


class Rules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_config_override(self):
        cfg = config(self.dir, braking={"lockup_ratio": -0.2})
        self.assertEqual(cfg["braking"]["lockup_ratio"], -0.2)            # the local file wins ...
        self.assertEqual(cfg["braking"]["lockup_s"], 0.1)                 # ... key by key
        self.assertEqual(cfg["pipeline"]["hz"], 30)

    def test_envelope(self):
        env = rules.Envelope(rules.load_config())
        for g in [1.0] * 90 + [1.5] * 10:
            env.add({"a_lat_g": g, "a_long_g": 0.0, "speed_kmh": 105, "brake": 0})
        self.assertEqual(env.g_max("cornering", 104), 1.5)                # 98th percentile of the bin
        self.assertEqual(env.g_max("cornering", 140), 1.5)                # an empty bin borrows from its neighbours
        self.assertIsNone(env.g_max("braking", 100))

    def lap_rows(self, cfg, **opts):
        session = pipeline.Session(self.dir, ("test", "Test Ring", "Test Car", "s1"), {"track_length_m": LENGTH},
                                   cfg, lambda *a: None)
        for frame, t in frames(1, options={1: opts})[:-1]:
            session.add(frame, t)
        rows = session.rows
        for r in rows:
            session.envelope.add(r)
        session.note_fields(rows)
        found = rules.analyse_lap(rows, cfg, session.envelope, None, None, session.seen, {}, "live")
        return rows, found, session

    def test_phases_and_labels(self):
        cfg = rules.load_config()
        rows, found, _ = self.lap_rows(cfg)
        at = lambda d: min(rows, key=lambda r: abs(r["lap_dist_m"] - d))  # noqa: E731
        self.assertEqual(at(150)["phase"], "straight")
        self.assertEqual(at(350)["phase"], "braking")
        self.assertIn(at(450)["phase"], ("entry", "apex"))
        self.assertEqual(at(800)["phase"], "straight")
        self.assertEqual(at(450)["corner_id"], 1)
        self.assertIsNone(at(800)["corner_id"])
        self.assertTrue(all(r["label"] in ("good", "potential", "bad", "none") for r in rows))
        names = {f["rule"] for f in found}
        self.assertIn("BRK_BUILDUP", names)
        self.assertIn("STR_THROTTLE", names)
        self.assertNotIn("BRK_LOCKUP", names)
        self.assertAlmostEqual(at(450)["balance_deg"], 0.2, places=2)     # front 3.0 deg, rear 2.8 deg
        self.assertGreater(at(450)["grip_use"], 0.9)

    def test_lockup_and_wheelspin(self):
        cfg = rules.load_config()
        rows, found, _ = self.lap_rows(cfg, lockup=True, spin=True)
        lock = next(f for f in found if f["rule"] == "BRK_LOCKUP")
        self.assertEqual((lock["level"], lock["value"]), ("bad", -0.4))
        self.assertTrue(327 <= rows[lock["i0"]]["lap_dist_m"] <= 346)              # smoothing may start it a sample early
        self.assertEqual(rows[lock["i0"] + 1]["label"], "bad")
        self.assertIn("BRK_LOCKUP bad -0.4 (< -0.15)", rows[lock["i0"] + 1]["reasons"])
        self.assertIn("EXT_WHEELSPIN", {f["rule"] for f in found})

    def test_missing_fields_switch_rules_off(self):
        cfg = rules.load_config()
        session = pipeline.Session(self.dir, ("test", "T", "C", "s"), {"track_length_m": LENGTH}, cfg, lambda *a: None)
        for frame, t in frames(1, options={1: {"lockup": True}}, slip=False)[:-1]:
            session.add(frame, t)
        session.note_fields(session.rows)
        self.assertNotIn("slip_ratio", session.seen)
        found = rules.analyse_lap(session.rows, cfg, session.envelope, None, None, session.seen, {}, "live")
        self.assertNotIn("BRK_LOCKUP", {f["rule"] for f in found})           # no slip ratio: the rule is off


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def drive(self, pipe, laps=3, **kw):
        for frame, t in frames(laps, **kw):
            pipe.handle(frame, "test", t)

    def test_session_files(self):
        pipe = pipeline.Pipeline(self.dir, log=lambda *a: self.log.append(a))
        self.drive(pipe, 3, options={2: {"lockup": True}})
        self.assertEqual([l["lap"] for l in pipe.session.laps], [1, 2])     # lap 3 still in progress
        folder = pipe.session.folder
        live = list(csv.DictReader(open(folder / "samples.csv")))
        self.assertEqual(live[0]["label_pass"], "live")
        result = pipe.session.finalize(2000.0)
        self.assertEqual(result["laps"], 3)
        rows = list(csv.DictReader(open(folder / "samples.csv")))
        self.assertEqual(list(rows[0]), rules.COLUMNS)
        self.assertEqual({r["label_pass"] for r in rows}, {"final"})
        self.assertTrue(any("BRK_LOCKUP bad" in r["reasons"] for r in rows if r["lap"] == "2"))
        laps = json.loads((folder / "laps.json").read_text())
        self.assertEqual(laps["reference_lap"], 1)                            # the best valid lap (lap 2 locked: slower)
        self.assertTrue(laps["laps"][0]["valid"] and not laps["laps"][2]["complete"])
        corners = json.loads((folder / "corners.json").read_text())
        self.assertEqual(len(corners["corners"]), 1)
        first = corners["per_lap"][0]
        self.assertTrue(250 <= first["braking_point_m"] <= 320)
        self.assertEqual(first["v_min_kmh"], 100.0)
        session = json.loads((folder / "session.json").read_text())
        self.assertIn("wheel_load", session["missing_fields"])               # the test frames send no detail
        self.assertIn("cornering", session["envelope_g"])
        self.assertIsNotNone(session["finalized"])
        self.assertIn("## Columns", (folder / "README.md").read_text())
        self.assertTrue(any(a[1] == "missing" for a in self.log))

    def test_finalize_on_demand_keeps_the_lap(self):
        pipe = pipeline.Pipeline(self.dir)
        self.drive(pipe, 2)
        in_progress = len(pipe.session.rows)
        self.assertGreater(in_progress, 0)
        pipe.finish(1500.0, end=False)
        self.assertEqual(len(pipe.session.rows), in_progress)                 # the lap in progress goes on
        self.assertIsNotNone(pipe.session)

    def test_new_session_and_idle(self):
        pipe = pipeline.Pipeline(self.dir)
        self.drive(pipe, 2)
        first = pipe.session.folder
        other = dict(frames(1)[0][0], car="Other Car")
        pipe.handle(other, "test", 5000.0)                                    # another car: the old session ends
        self.assertNotEqual(pipe.session.folder, first)
        self.assertIsNotNone(json.loads((first / "session.json").read_text())["finalized"])
        pipe.idle(5000.0 + pipe.cfg["pipeline"]["session_idle_s"] + 1)
        self.assertIsNone(pipe.session)

    def test_queue_never_blocks(self):
        cfg = rules.load_config()
        cfg["pipeline"]["queue_size"] = 3
        pipe = pipeline.Pipeline(self.dir, cfg=cfg)                            # no worker started: nothing is taken out
        for k in range(10):
            pipe.put({"k": k}, "test", float(k))
        self.assertEqual(pipe.dropped, 7)
        self.assertEqual([pipe.queue.get_nowait()[1]["k"] for _ in range(3)], [7, 8, 9])   # the newest are kept

    def test_open_session_is_recovered(self):
        pipe = pipeline.Pipeline(self.dir)
        self.drive(pipe, 2)
        folder = pipe.session.folder
        pipe.session.close_file()                                             # the bridge was killed here
        again = pipeline.Pipeline(self.dir, log=lambda *a: self.log.append(a))
        again.start()
        again.stop()
        self.assertIsNotNone(json.loads((folder / "session.json").read_text())["finalized"])
        self.assertTrue((folder / "corners.json").exists())
        self.assertTrue(any(a[1] == "recover" for a in self.log))


if __name__ == "__main__":
    unittest.main()
