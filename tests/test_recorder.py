"""Tests of the analysis recorder (core/recorder.py) with a simulated car on a 1000 m track."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

import recorder  # noqa: E402

LENGTH = 1000.0
DT = 1 / 30


def frame(p, v=180.0, **extra):
    values = {"connected": True, "error": None, "status": "live", "lap_pos": p % 1.0, "track_length_m": LENGTH,
              "track": "Test Ring", "car": "Test Car", "session_id": "s1", "pos_x": p * 10, "pos_y": 0.0,
              "speed_kmh": v, "gas": 1.0, "brake": 0.0, "steer": 0.0, "gear": 4, "lap_valid": True, "air_c": 20}
    values.update(extra)
    return values


class Car:
    """Drives along the track; the lap position wraps at the line. ms = metres per second."""

    def __init__(self, rec, p=0.0, t=100.0):
        self.rec, self.p, self.t = rec, p, t

    def drive(self, metres, ms=50.0, **extra):
        step = ms * DT / LENGTH * (1 if metres >= 0 else -1)
        for _ in range(int(abs(metres) / (ms * DT))):
            self.p += step
            self.t += DT
            self.rec.feed(frame(self.p, v=ms * 3.6, **extra), "demo", self.t)

    def stand(self, seconds, **extra):
        for _ in range(int(seconds / DT)):
            self.t += DT
            self.rec.feed(frame(self.p, v=0.0, **extra), "demo", self.t)


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.rec = recorder.Recorder(self.dir, hz=30, section_m=250)

    def tearDown(self):
        self.tmp.cleanup()

    def offers(self, kind=None):
        return [o for o in self.rec.state()["offers"] if kind is None or o["kind"] == kind]

    def test_sections_along_the_track(self):
        for length, sections in ((1000, 4), (1100, 4), (1130, 5), (300, 1)):
            rec = recorder.Recorder(self.dir, section_m=250)
            rec.feed(dict(frame(0.1), track_length_m=length), "demo", 1.0)
            self.assertEqual(rec.sections, sections, length)
            self.assertEqual(rec._section(0.9999), sections - 1)

    def test_laps_sections_and_files(self):
        car = Car(self.rec, p=0.5)                     # out lap from half way
        car.drive(500 + 1000 + 1000 + 20)              # to the line, then two full laps
        state = self.rec.state()
        self.assertEqual(state["laps"], 3)
        lap = self.rec.last_lap
        self.assertTrue(lap.counts)
        self.assertAlmostEqual(lap.time, 20.0, delta=0.05)
        for n in range(4):
            self.assertAlmostEqual(lap.done(n).time, 5.0, delta=0.05)
        self.assertFalse(self.rec.prev_lap.out_lap)
        files = sorted(self.rec.run_dir.glob("lap-*.jsonl"))
        self.assertEqual([f.name for f in files], ["lap-001.jsonl", "lap-002.jsonl", "lap-003.jsonl"])
        lines = [json.loads(line) for line in files[1].read_text().splitlines()]
        self.assertEqual(lines[0]["type"], "header")
        self.assertEqual(lines[0]["format"], "racing-dashboard.lap")
        self.assertEqual(lines[-1]["type"], "summary")
        self.assertTrue(lines[-1]["counts"])
        self.assertEqual(sum(1 for l in lines if l["type"] == "ambient"), 1)
        samples = [l for l in lines if l["type"] == "s"]
        self.assertGreater(len(samples), 550)
        self.assertEqual(samples, sorted(samples, key=lambda s: s["t"]))
        # offers: the out lap's last section, then every section and the lap; equal times are not offered again
        self.assertEqual(len(self.offers("lap")), 1)
        self.assertEqual(sorted(o["sec"] for o in self.offers("section")), [0, 1, 2, 3])

    def test_save_skip_undo(self):
        car = Car(self.rec, p=0.0)
        car.drive(1020)
        lap_offer = self.offers("lap")[0]
        self.rec.save_all()
        folder = self.dir / "baselines" / "demo" / "test-ring" / "test-car"
        self.assertTrue((folder / "lap.jsonl").exists())
        self.assertEqual(len(list((folder / "sections").glob("section-0?.jsonl"))), 4)
        self.assertEqual(self.offers(), [])
        head = json.loads((folder / "lap.jsonl").read_text().splitlines()[0])
        self.assertEqual(head["format"], "racing-dashboard.lap-baseline")
        # a slower lap: nothing to offer
        car.drive(1000, ms=45)
        self.assertEqual(self.offers(), [])
        self.assertIsNotNone(self.rec.live()["deltas"]["lap_best"])
        # a faster lap: offered again; SAVE keeps a backup, UNDO brings the old one back
        car.drive(1000, ms=60)
        faster = self.offers("lap")[0]
        self.assertLess(faster["time"], lap_offer["time"])
        self.assertTrue(self.rec.decide(faster["id"], True))
        self.assertTrue((folder / "lap.prev.jsonl").exists())
        self.assertAlmostEqual(self.rec.base["lap"]["time"], faster["time"], delta=0.001)
        self.assertTrue(self.rec.undo())
        self.assertAlmostEqual(self.rec.base["lap"]["time"], lap_offer["time"], delta=0.001)
        # SKIP removes an offer without saving
        section = self.offers("section")[0]
        self.assertTrue(self.rec.decide(section["id"], False))
        self.assertNotIn(section["id"], [o["id"] for o in self.offers()])

    def test_repeat_a_section(self):
        car = Car(self.rec, p=0.0)
        car.drive(625)                                 # into the middle of section 3
        car.drive(-150, ms=10)                         # turned around: back into section 2
        car.drive(150)                                 # and forward into section 3 again
        lap = self.rec.lap
        self.assertEqual(len(lap.attempts[2]), 2)      # section 3 started again (entered from section 2)
        self.assertEqual(len(lap.attempts[1]), 1)      # section 2 was entered backwards: not replaced
        self.assertTrue(lap.repeated)
        self.assertEqual(self.rec.live()["strip"]["attempts"][2], 2)
        car.drive(400)                                 # finish the lap
        self.assertFalse(self.rec.last_lap.counts)     # a lap with a repeat never counts
        self.assertEqual(self.offers("lap"), [])
        self.assertTrue(any(o["sec"] == 2 and o["att"] == 2 for o in self.offers("section")))

    def test_spin_at_a_border_replaces_nothing_before(self):
        car = Car(self.rec, p=0.0)
        car.drive(510)                                 # just into section 3
        car.drive(-20, ms=5)                           # spin, roll back into section 2
        car.drive(40)
        lap = self.rec.lap
        self.assertEqual(len(lap.attempts[1]), 1)      # section 2 keeps its one attempt
        self.assertIsNotNone(lap.done(1))
        self.assertEqual(len(lap.attempts[2]), 2)      # section 3 restarts
        self.assertFalse(lap.broken)                   # 20 m back does not break the lap

    def test_backwards_is_not_recorded(self):
        car = Car(self.rec, p=0.0)
        car.drive(300)
        car.drive(-50, ms=10)
        car.drive(100)
        ps = [row[recorder.P] for row in self.rec.lap.line()]
        self.assertEqual(ps, sorted(ps))
        for attempts in self.rec.lap.attempts.values():
            for attempt in attempts:
                ps = [row[recorder.P] for row in attempt.samples]
                self.assertEqual(ps, sorted(ps))

    def test_invalid_lap_offers_sections_only(self):
        car = Car(self.rec, p=0.0)
        car.drive(400)
        car.drive(620, lap_valid=False)
        self.assertFalse(self.rec.last_lap.valid)
        self.assertEqual(self.offers("lap"), [])
        sections = self.offers("section")
        self.assertEqual(len(sections), 4)
        self.assertTrue(all(o["invalid"] for o in sections))

    def test_pause_breaks_the_lap(self):
        car = Car(self.rec, p=0.0)
        car.drive(300)
        self.rec.feed(frame(car.p, status="pause"), "demo", car.t + 1)
        car.t += 5
        car.drive(720)
        self.assertTrue(self.rec.last_lap.broken)
        self.assertFalse(self.rec.last_lap.counts)
        self.assertEqual(self.offers("lap"), [])
        self.assertNotIn(1, [o["sec"] for o in self.offers("section")])   # the paused section

    def test_stage_with_standing_start(self):
        car = Car(self.rec, p=0.0)
        car.stand(3)                                   # countdown at the start
        car.drive(999.8)
        car.p = 0.9999
        car.stand(2)                                   # stopped after the finish
        lap = self.rec.last_lap
        self.assertIsNotNone(lap)
        self.assertTrue(lap.counts)
        self.assertAlmostEqual(lap.time, 20.0, delta=0.1)
        self.assertIsNone(self.rec.lap)
        self.assertEqual(len(self.offers("lap")), 1)

    def test_new_session_ends_the_run(self):
        car = Car(self.rec, p=0.0)
        car.drive(1100)
        first = self.rec.run_dir
        self.rec.feed(frame(0.1, session_id="s2"), "demo", car.t + 1)
        ended = self.rec.state()["ended"]
        self.assertEqual(ended["laps"], 2)
        self.assertEqual(ended["dir"], str(first))
        self.assertTrue(self.rec.finish_run("baselines"))
        self.assertFalse(first.exists())
        self.assertIsNone(self.rec.state()["ended"])

    def test_pending_offers_survive_a_restart(self):
        car = Car(self.rec, p=0.0)
        car.drive(1020)
        count = len(self.offers())
        again = recorder.Recorder(self.dir, hz=30, section_m=250)
        self.assertEqual(len(again.state()["offers"]), count)
        section = next(o for o in again.state()["offers"] if o["kind"] == "section")
        self.assertTrue(again.decide(section["id"], True))
        path = self.dir / "baselines" / "demo" / "test-ring" / "test-car" / "sections" / f"section-{section['sec'] + 1:02d}.jsonl"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(lines[0]["format"], "racing-dashboard.section-baseline")
        samples = [l for l in lines if l["type"] == "s"]
        self.assertGreater(len(samples), 100)
        self.assertLess(samples[0]["t"], 0.1)
        self.assertLess(samples[0]["d"], 3)

    def test_section_api(self):
        car = Car(self.rec, p=0.0)
        car.drive(1020)
        self.rec.save_all()
        car.drive(1000, ms=48)
        car.drive(300, ms=48)                          # into section 2 of the next lap
        data = self.rec.section(1)
        self.assertTrue(data["best"] and data["last"] and data["now"])
        self.assertEqual(len(data["best"][0]), 9)
        self.assertEqual(data["to_m"], 500.0)
        live = self.rec.live()
        self.assertEqual(live["strip"]["best"][0] > 0, True)   # slower than the baseline
        state = self.rec.state()
        self.assertEqual(len(state["borders"]), 4)
        self.assertTrue(state["outline"])

    def test_strip_shows_the_last_lap_until_the_new_one_gets_there(self):
        car = Car(self.rec, p=0.0)
        car.drive(1020)
        self.rec.save_all()
        car.drive(1000, ms=48)                         # lap 2 done (slower than the baseline)
        car.drive(300, ms=48)                          # lap 3: only section 1 done
        strip = self.rec.live()["strip"]
        self.assertFalse(strip["old"][0])              # section 1: from the lap in progress
        self.assertTrue(all(strip["old"][1:]))         # the rest: from lap 2
        self.assertTrue(all(v is not None and v > 0 for v in strip["best"]))
        self.assertIsNotNone(self.rec.live()["deltas"]["lap_last"])

    def test_paused_shows_the_last_lap_and_why(self):
        car = Car(self.rec, p=0.0)
        car.drive(1020)
        car.drive(200)
        self.rec.feed(frame(car.p, status="pause"), "demo", car.t + 0.1)
        live = self.rec.live()
        self.assertFalse(live["recording"])
        self.assertEqual(live["why"], "GAME PAUSED")
        self.assertEqual(live["red_lap"], 1)          # the last complete lap, not the started one
        self.assertIsNotNone(live["deltas"]["lap_time"])
        self.assertTrue(all(v is not None for v in live["strip"]["times"]))
        self.assertEqual(live["last_lap"]["lap"], 1)
        self.rec.feed(frame(car.p, lap_pos=None), "demo", car.t + 0.2)
        self.assertEqual(self.rec.live()["why"], "THE GAME SENDS NO LAP POSITION")

    def test_invalid_last_lap_still_gives_the_delta_to_last(self):
        car = Car(self.rec, p=0.0)
        car.drive(1020, lap_valid=False)
        car.drive(300)
        self.assertFalse(self.rec.last_lap.counts)
        self.assertIsNotNone(self.rec.live()["deltas"]["lap_last"])


if __name__ == "__main__":
    unittest.main()
