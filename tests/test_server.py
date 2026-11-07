"""Bridge smoke test with the demo game: pages, /state, /api/info, /api/command, /stream.

Run: python -m unittest discover tests
"""
import json
import sys
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
    server.activate("demo")
    threading.Thread(target=server.reader, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    time.sleep(0.3)


def tearDownModule():
    httpd.shutdown()


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
        for path in ("/", "/gear", "/dash", "/js/rd.js", "/css/base.css", "/styles/gear/bar.css", "/apple-touch-icon.png"):
            status, content_type, body = get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body, path)
        self.assertIn("text/html", get("/gear")[1])

    def test_no_files_outside_ui(self):
        for path in ("/../core/server.py", "/%2e%2e/core/server.py", "/nothing"):
            with self.assertRaises(urllib.error.HTTPError, msg=path):
                get(path)

    def test_state_and_info(self):
        state = json.loads(get("/state")[2])
        self.assertTrue(state["connected"])
        self.assertEqual(state["game"], "demo")
        info = json.loads(get("/api/info")[2])
        self.assertEqual([g["name"] for g in info["groups"]], ["AIDS", "CAR", "VIEW", "PIT"])
        self.assertIn("ace", [g["id"] for g in info["games"]])

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


if __name__ == "__main__":
    unittest.main()
