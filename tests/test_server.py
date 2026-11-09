"""Bridge smoke test with the demo game: pages, /state, /api/info, /api/command, /stream.

Run: python -m unittest discover tests
"""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import config  # noqa: E402
import server  # noqa: E402


def setUpModule():
    global base, httpd
    server.cfg = config.load(Path("/nonexistent"))     # defaults only
    server.cfg["log"]["enabled"] = False
    server.log.setup(server.cfg["log"])
    server.games = config.load_games(server.cfg)
    for game in server.games.values():
        server.check_keys(game)
        server.check_dash(game)
    global data_dir
    data_dir = tempfile.TemporaryDirectory()
    server.recorder = server.recording.Recorder(data_dir.name)
    server.cfg["trainer"]["ollama_url"] = "http://127.0.0.1:9"     # nothing listens: no real AI in the tests
    server.trainer = server.training.Trainer(server.cfg, Path(data_dir.name) / "trainer.json", data_dir.name)
    server.activate("demo")
    threading.Thread(target=server.reader, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    time.sleep(0.3)


def tearDownModule():
    httpd.shutdown()
    server.recorder = None
    server.trainer = None
    time.sleep(0.05)
    data_dir.cleanup()


def get(path):
    with urllib.request.urlopen(base + path, timeout=3) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def post(path, body):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class Bridge(unittest.TestCase):
    def test_pages(self):
        for path in ("/", "/gear", "/dash", "/js/rd.js", "/css/base.css", "/styles/gear/segment.css", "/js/seg14.js", "/buttons", "/js/dashbox.js", "/styles/dash/cards.css", "/racing-dashboard-icon.png",
                     "/analysis", "/js/analysis.js", "/styles/analysis/standard.css"):
            status, content_type, body = get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body, path)
        self.assertIn("text/html", get("/gear")[1])

    def test_trainer_api_keeps_the_key(self):
        status, _, body = get("/api/trainer")
        self.assertEqual((status, json.loads(body)["state"]), (200, "unchecked"))
        code, reply = post("/api/trainer/settings", {"provider": "ollama", "key": "sk-ant-SECRET-abcd1234", "key_for": "claude"})
        self.assertEqual(code, 200)
        self.assertEqual(reply["error"], "OLLAMA NOT RUNNING")
        self.assertNotIn("SECRET", json.dumps(reply))
        self.assertNotIn("SECRET", get("/api/trainer")[2].decode())
        code, reply = post("/api/trainer/ask", {"mode": "track"})
        self.assertEqual(code, 409)                                  # no run recorded yet, or no AI

    def test_home_link(self):
        # the home page to save on the tablet: /Racing_Dashboard (other dashboards share the address)
        home = get("/")[2]
        for path in ("/Racing_Dashboard", "/racing_dashboard", "/Racing_Dashboard/"):
            status, _, body = get(path)
            self.assertEqual((status, body), (200, home), path)
        self.assertEqual(get("/Racing_Dashboard/gear")[2], get("/gear")[2])
        self.assertEqual(get("/Racing_Dashboard/css/base.css")[0], 200)

    def test_no_files_outside_ui(self):
        for path in ("/../core/server.py", "/%2e%2e/core/server.py", "/nothing"):
            with self.assertRaises(urllib.error.HTTPError, msg=path):
                get(path)

    def test_state_and_info(self):
        state = json.loads(get("/state")[2])
        self.assertTrue(state["connected"])
        self.assertEqual(state["game"], "demo")
        self.assertIsNone(state["error"])
        info = json.loads(get("/api/info")[2])
        self.assertEqual([g["name"] for g in info["groups"]], ["AIDS", "CAR", "VIEW", "PIT"])
        self.assertIn("ace", [g["id"] for g in info["games"]])
        self.assertEqual([c["label"] for c in info["dash"]],
                         ["TC", "TC CUT", "ABS", "STABILITY", "ENGINE MAP", "BRAKE BIAS", "FUEL", "DIFF", "PIT LIMITER",
                          "LIGHTS", "WIPERS", "IGNITION", "WARNINGS", "TYRES", "DRIVE MODE"])
        self.assertTrue(info["dash"][0]["enabled"]["tc_up"])
        lights = next(c for c in info["dash"] if c["label"] == "LIGHTS")
        self.assertEqual(lights["kinds"], {"lights": "tap", "flash": "hold"})
        ignition = next(c for c in info["dash"] if c["label"] == "IGNITION")
        self.assertEqual(ignition["kinds"], {"ignition": "hold", "starter": "hold"})

    def test_commands(self):
        before = json.loads(get("/state")[2])["tc_level"]
        self.assertEqual(post("/api/command", {"action": "tc_up"}), (200, {"ok": True}))
        time.sleep(0.1)
        self.assertEqual(json.loads(get("/state")[2])["tc_level"], before + 1)
        self.assertEqual(post("/api/command", {"action": "horn", "state": "down"})[0], 200)
        self.assertEqual(post("/api/command", {"action": "horn", "state": "up"})[0], 200)
        self.assertEqual(post("/api/command", {"action": "horn", "state": "tap"})[0], 409)
        self.assertEqual(post("/api/command", {"action": "self_destruct"})[0], 409)

    def test_stream(self):
        with urllib.request.urlopen(base + "/stream?hz=30", timeout=3) as r:
            self.assertIn("text/event-stream", r.headers.get("Content-Type"))
            frames, start = 0, time.monotonic()
            while frames < 15:
                line = r.readline()
                if line.startswith(b"data: "):
                    frame = json.loads(line[6:])
                    self.assertIn("rpm", frame)
                    frames += 1
            self.assertLess(time.monotonic() - start, 2.0)


class Latch(unittest.TestCase):
    """A per-game "latch" kind: one tap presses the key and keeps it down, the next lets it go.
    The keyboard and window are faked, so nothing is sent to the PC."""

    def test_latch(self):
        class Silent:                                   # a connector that handles no button itself
            def handle(self, action, state):
                return False
        sent = []
        saved = (server.active, server.connector, server.keys.available, server.keys.down, server.keys.up,
                 server.keys.focus, server.keys.tap)
        game = {"id": "fake", "game": {"name": "Fake"}, "window": {"process": "x.exe", "title": "X"},
                "keys": {"wipers": "U", "horn": "H"}, "kinds": {"wipers": "latch", "horn": "nonsense"}, "dash": []}
        try:
            server.check_keys(game)
            self.assertEqual(game["kinds"], {"wipers": "latch"})          # unknown kind dropped
            server.active, server.connector = game, Silent()
            server.keys.available = True
            server.keys.down = lambda combo: sent.append(("down", combo))
            server.keys.up = lambda combo: sent.append(("up", combo))
            server.keys.tap = lambda combo, s: sent.append(("tap", combo))
            server.keys.focus = lambda process, title: True
            self.assertEqual(server.command({"action": "wipers", "state": "down"})[0], False)   # taps only
            self.assertEqual(server.command({"action": "wipers"}), (True, ""))
            self.assertEqual(server.latched, {"wipers"})
            self.assertEqual(server.command({"action": "wipers"}), (True, ""))
            self.assertEqual(server.latched, set())
            server.command({"action": "wipers"})
            server.release_all()                                           # game switch / shutdown
            self.assertEqual(sent, [("down", "U"), ("up", "U"), ("down", "U"), ("up", "U")])
            self.assertEqual(server.latched, set())
            groups = server.actions.layout(game["keys"], set(), game["kinds"])
            wipers = next(b for g in groups for b in g["buttons"] if b["action"] == "wipers")
            self.assertEqual(wipers["type"], "latch")
        finally:
            (server.active, server.connector, server.keys.available, server.keys.down, server.keys.up,
             server.keys.focus, server.keys.tap) = saved
            server.latched.clear()



class Analysis(unittest.TestCase):
    def test_analysis_api(self):
        time.sleep(0.5)                                  # the demo car drives: a run starts
        status, _, body = get("/api/analysis")
        state = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(state["active"])
        self.assertEqual(state["game"], "demo")
        self.assertEqual(state["sections"], 20)
        _, _, body = get("/api/analysis/live?since=0")
        live = json.loads(body)
        self.assertTrue(live["recording"])
        self.assertEqual(len(live["strip"]["best"]), 20)
        _, _, body = get("/api/analysis/section?n=0")
        self.assertEqual(json.loads(body)["n"], 0)
        self.assertEqual(post("/api/analysis/offer", {"id": 999, "save": True})[0], 409)
        self.assertEqual(post("/api/analysis/undo", {})[0], 409)
        self.assertEqual(post("/api/analysis/skip-all", {})[0], 200)
        self.assertEqual(post("/api/analysis/finish", {"keep": "nonsense"})[0], 409)
        self.assertEqual(post("/api/analysis/nothing", {})[0], 404)
        status, state = post("/api/analysis/end", {})
        self.assertEqual(status, 200)

if __name__ == "__main__":
    unittest.main()
