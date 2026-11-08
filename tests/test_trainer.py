"""Tests of the AI trainer (core/trainer.py, docs/TRAINER.md) without a real AI: facts, the prompt
container, answer checks, the history, settings and keys. Providers are simulated."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

import recorder  # noqa: E402
import trainer  # noqa: E402

LENGTH = 1000.0
DT = 1 / 30


def frame(p, v, **extra):
    values = {"connected": True, "error": None, "status": "live", "lap_pos": p % 1.0, "track_length_m": LENGTH,
              "track": "Test Ring", "car": "Test Car", "session_id": "s1", "pos_x": p * 10, "pos_y": 0.0,
              "speed_kmh": v, "gas": 1.0, "brake": 0.0, "steer": 0.0, "gear": 4, "lap_valid": True}
    values.update(extra)
    return values


def drive_lap(rec, t, brake_at=100.0, brake_m=40.0):
    """One lap of the 1000 m ring: full throttle, braking in each section from brake_at for brake_m metres."""
    p, ms = 0.0, 50.0
    while p < 1.0:
        d = (p * LENGTH) % 250
        braking = brake_at <= d < brake_at + brake_m
        rec.feed(frame(p, (30.0 if braking else ms) * 3.6, gas=0.0 if braking else 1.0, brake=0.8 if braking else 0.0,
                       gear=3 if braking else 4), "demo", t)
        step = (30.0 if braking else ms) * DT / LENGTH
        p += step
        t += DT
    return t


def rows(brake_on=100, brake_off=140, low=60.0):
    """A synthetic 250 m section: [d, t, v, thr, brk, str, g]."""
    out, t = [], 0.0
    for d in range(0, 251, 5):
        braking = brake_on <= d < brake_off
        v = low if braking else 150.0
        thr = 0.0 if braking else 1.0
        out.append([float(d), round(t, 3), v, thr, 0.9 if braking else 0.0, 0.3 if braking else 0.0, 3 if braking else 4])
        t += 5 / (v / 3.6)
    return out


class Facts(unittest.TestCase):
    def test_section_facts(self):
        best, now = rows(110, 140, 70.0), rows(95, 140, 60.0)
        f = trainer.facts(now, now[-1][1], best)
        self.assertEqual((f["lift_m"], f["brake_on_m"], f["brake_off_m"]), (95, 95, 140))
        self.assertEqual((f["min_kmh"], f["gear_at_min"], f["gears"]), (60, 3, "4-3-4"))
        self.assertEqual(f["full_throttle_m"], 140)
        self.assertEqual(f["brake_peak_pct"], 90)
        self.assertGreater(f["delta_by_50m"]["250"], 0)            # now is slower than best at the end
        self.assertNotIn("delta_by_50m", trainer.facts(best, best[-1][1]))
        shifting = [r[:6] + [0 if r[0] == 145 else r[6]] for r in now]   # neutral for a moment while shifting
        self.assertEqual(trainer.facts(shifting, None)["gears"], "4-3-4")
        short = now[:-1] + [[249.2] + now[-1][1:]]                       # the last sample a little short of 250 m
        self.assertIn("250", trainer.facts(short, None, best)["delta_by_50m"])
        self.assertIsNone(trainer.facts([], None))


class Aids(unittest.TestCase):
    def test_aid_facts(self):
        base = rows(110, 140, 70.0)
        now = [r + [0.0, 0.0] + [1 if 150 <= r[0] < 180 else 0, 1 if 110 <= r[0] < 120 else 0, 0,
                    3 if r[0] < 200 else 4, 2, 2, None, 1] for r in base]
        f = trainer.facts(now, now[-1][1])
        self.assertEqual((f["aids"]["tc_working_m"], f["aids"]["tc_first_m"]), (30, 150))
        self.assertEqual(f["aids"]["abs_working_pct"], 4)
        self.assertEqual(f["aids"]["levels"], {"tc": 3, "tc_cut": 2, "abs": 2, "engine_map": 1})
        self.assertEqual(f["aids"]["level_changes"], [{"at_m": 200, "setting": "tc", "to": 4}])
        old = [r + [0.0, 0.0] + [None] * 8 for r in base]                          # laps from before the aids were recorded
        self.assertNotIn("aids", trainer.facts(old, old[-1][1]))
        self.assertIn("Driving aids", trainer.SYSTEM_PROMPT)


class Requests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = recorder.Recorder(self.tmp.name, hz=30, section_m=250)
        t = drive_lap(self.rec, 100.0, brake_at=120)        # lap 1 from the line
        self.rec.save_all()
        t = drive_lap(self.rec, t, brake_at=120)            # lap 2
        self.t = drive_lap(self.rec, t, brake_at=100)       # lap 3: brakes earlier
        self.rec.feed(frame(0.05, 180.0), "demo", self.t)   # lap 4 started

    def tearDown(self):
        self.tmp.cleanup()

    def test_section_request(self):
        task, data, view = trainer.build_request(self.rec, "section", 1, "Demo")
        self.assertIn("SECTION 2 (250 m)", task)
        self.assertEqual(data["mode"], "section")
        self.assertEqual(data["game"], "Demo")
        self.assertEqual(set(data["lines"]), {"best", "last", "now"})
        self.assertEqual(view["title"], "SECTION 2")
        json.dumps(data)                                     # sendable

    def test_track_request(self):
        # between laps: the last complete lap is NOW
        rec = recorder.Recorder(self.tmp.name + "/b", hz=30, section_m=250)
        t = drive_lap(rec, 100.0, brake_at=120)
        rec.save_all()
        t = drive_lap(rec, t, brake_at=100, brake_m=60)  # brakes earlier and longer: slower
        rec.feed(frame(0.01, 180.0), "demo", t)            # lap 3 has just started
        task, data, view = trainer.build_request(rec, "track", None)
        self.assertIn("WHOLE LAP", task)
        self.assertEqual(data["laps"]["now"], 2)            # the last complete lap, not the 10 m of lap 3
        self.assertEqual(data["laps"]["last"], 1)
        self.assertEqual(len(data["sections"]), 4)
        self.assertTrue(data["focus"])                       # the sections that lose time, with facts
        self.assertEqual(view["title"], "WHOLE TRACK")

    def test_no_run(self):
        rec = recorder.Recorder(self.tmp.name + "/c")
        with self.assertRaises(trainer.TrainerError):
            trainer.build_request(rec, "track", None)


class Answers(unittest.TestCase):
    data = {"mode": "section", "section": 5, "section_length_m": 250}

    def answer(self, **extra):
        a = {"note": "",
             "tips": [{"title": "Brake later", "section": 5, "from_m": 95, "to_m": 115, "text": "Brake at 115 m.", "gain_s": 0.2}]}
        a.update(extra)
        return json.dumps(a)

    def test_good_answer(self):
        a = trainer.check_answer(self.answer(), self.data)
        self.assertEqual(a["tips"][0]["title"], "BRAKE LATER")
        self.assertEqual(a["tips"][0]["gain_s"], 0.2)

    def test_fenced_and_limits(self):
        long = " ".join(["word"] * 60)
        tips = [{"title": "A B C D E F", "section": 5, "from_m": 10, "to_m": 20, "text": long, "gain_s": 0.1}] * 5
        a = trainer.check_answer("```json\n" + self.answer(tips=tips, note=long) + "\n```", self.data)
        self.assertEqual(len(a["tips"]), 3)
        self.assertTrue(a["note"].endswith("…"))
        self.assertEqual(len(a["note"].split()), 30)
        self.assertEqual(a["tips"][0]["title"], "A B C D")
        self.assertTrue(a["tips"][0]["text"].endswith("…"))

    def test_titles_are_cut_cleanly(self):
        for title, expected in (("Brake later in section 2", "BRAKE LATER"),
                                ("Lift earlier, brake softer", "LIFT EARLIER BRAKE SOFTER"),
                                ("carry speed into the", "CARRY SPEED")):
            tips = [{"title": title, "section": 5, "from_m": 10, "to_m": 20, "text": "t", "gain_s": 0.1}]
            self.assertEqual(trainer.check_answer(self.answer(tips=tips), self.data)["tips"][0]["title"], expected)

    def test_wrong_places_dropped(self):
        tips = [{"title": "X", "section": 9, "from_m": 10, "to_m": 20, "text": "t", "gain_s": 0.1},
                {"title": "Y", "section": 5, "from_m": 400, "to_m": 420, "text": "t", "gain_s": 0.1},
                {"title": "Z", "section": 5, "from_m": "a", "to_m": 20, "text": "t", "gain_s": 0.1}]
        self.assertEqual(trainer.check_answer(self.answer(tips=tips), self.data)["tips"], [])

    def test_not_json(self):
        with self.assertRaises(trainer.TrainerError) as caught:
            trainer.check_answer("Sorry, I cannot help.", self.data)
        self.assertEqual(caught.exception.code, "ANSWER NOT READABLE")


class FakeProvider(trainer.Provider):
    calls = []

    def check(self):
        if self.key == "bad":
            raise trainer.TrainerError("KEY REJECTED", "HTTP 401")
        return self.model

    def ask(self, system, user):
        FakeProvider.calls.append((system, user))
        data = json.loads(user.split("DATA:\n", 1)[1])
        sec = data.get("section", 1)
        return json.dumps({"summary": "ok", "note": "", "tips": [
            {"title": "Brake later", "section": sec, "from_m": 100, "to_m": 120, "text": "Brake later.", "gain_s": 0.15}]}), {"in": 100, "out": 50}


class TrainerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.old = trainer.CLASSES["claude"]
        trainer.CLASSES["claude"] = FakeProvider
        self.tr = trainer.Trainer({"trainer": {"models": {"claude": {"fast": {"model": "claude-test"}}}}},
                                  self.dir / "trainer.json", self.dir / "data")
        self.rec = recorder.Recorder(self.dir / "rec", hz=30, section_m=250)
        t = drive_lap(self.rec, 100.0)
        self.rec.save_all()
        drive_lap(self.rec, t, brake_at=90)

    def tearDown(self):
        trainer.CLASSES["claude"] = self.old
        self.tmp.cleanup()

    def test_off_and_no_key(self):
        self.assertEqual(self.tr.test()["state"], "off")
        status = self.tr.update({"provider": "claude"})
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"], "NO KEY")

    def test_key_stays_on_the_pc(self):
        secret = "sk-ant-api03-SECRETSECRETSECRET-7Q2f"
        status = self.tr.update({"provider": "claude", "key": secret})
        self.assertTrue(status["ok"])
        self.assertEqual(status["model"], "claude-test")             # the config override
        self.assertEqual(status["keys"]["claude"], "sk-ant-…7Q2f")
        self.assertNotIn("SECRET", json.dumps(status))
        saved = json.loads((self.dir / "trainer.json").read_text())
        self.assertEqual(saved["keys"]["claude"], secret)
        self.assertEqual(self.tr.update({"key": "bad"})["error"], "KEY REJECTED")

    def test_ask_and_rolling_history(self):
        self.tr.update({"provider": "claude", "key": "sk-ant-key-0000000000001234"})
        for n in range(7):
            out = self.tr.ask(self.rec, "section", n % 4, "Demo")
        self.assertEqual(out["answer"]["tips"][0]["section"], 3)         # the last ask: section index 2
        system, user = FakeProvider.calls[-1]
        self.assertEqual(system, trainer.SYSTEM_PROMPT)
        self.assertTrue(user.startswith("TASK: Analyse SECTION 3"))
        lines = (self.dir / "data" / "trainer.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 5)                                  # only the last 5 kept
        again = trainer.Trainer({}, self.dir / "trainer.json", self.dir / "data")
        self.assertEqual(len(again.public()["history"]), 5)              # kept over a restart
        self.assertNotIn("data", again.public()["history"][0])           # the page gets the answer only
        track = self.tr.ask(self.rec, "track", None, "Demo")
        self.assertEqual(track["title"], "WHOLE TRACK")


if __name__ == "__main__":
    unittest.main()
