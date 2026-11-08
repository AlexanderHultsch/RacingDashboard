"""Racing Dashboard bridge: reads the game through its connector, serves the UI, sends keypresses.

Run:  python core/server.py   (or start_dashboard.bat)
"""
import sys

if sys.version_info < (3, 12):
    sys.exit(f"Racing Dashboard needs Python 3.12 or newer, this is {sys.version.split()[0]}. Run install.bat.")

import importlib.util
import json
import mimetypes
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import actions  # noqa: E402
import config  # noqa: E402
import keys  # noqa: E402
import log  # noqa: E402
import telemetry  # noqa: E402

HZ_CHOICES = (10, 20, 30, 60)
HEARTBEAT_S = 1.0

cfg: dict = {}
games: dict = {}
settings: dict = {}
active: dict | None = None        # the game.toml of the active game
connector = None
data = telemetry.blank()
seq = 0
data_lock = threading.Lock()
game_lock = threading.Lock()
key_lock = threading.Lock()
held: dict[str, float] = {}       # action -> time the key went down
address = ""


# ---------------------------------------------------------------- games and connectors

def load_connector(game: dict):
    path = game["dir"] / "connector.py"
    spec = importlib.util.spec_from_file_location(f"games.{game['id']}.connector", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Connector(game, cfg)


def check_keys(game: dict) -> None:
    """Drop invalid or unknown keys with a log line, so the rest of the game still works."""
    for action, combo in list(game["keys"].items()):
        if action not in actions.BY_NAME:
            log.line("keys", game["id"], f"unknown action '{action}' ignored")
            del game["keys"][action]
            continue
        if not combo:
            continue
        try:
            keys.parse(combo)
        except ValueError as error:
            log.line("keys", game["id"], f"{action} = '{combo}': {error}, button disabled")
            game["keys"][action] = ""


# dash box card types: the keys each type needs, which of them are actions, which are telemetry fields
DASH_TYPES = {
    "stepper": {"need": ("field", "down", "up"), "actions": ("down", "up")},
    "bias": {"need": ("field", "front", "rear"), "actions": ("front", "rear")},
    "toggle": {"need": ("field",), "actions": ("action",)},
    "pair": {"need": ("fields", "labels"), "actions": ()},
    "fuel": {"need": ("field",), "actions": ()},
    "lamps": {"need": ("fields", "icons"), "actions": ()},
    "cycle": {"need": ("field", "action"), "actions": ("action", "extra")},
    "value": {"need": ("field",), "actions": ()},
    "push": {"need": ("action",), "actions": ("action",)},
    "ignition": {"need": ("field", "running", "action"), "actions": ("action", "starter")},
}
DASH_FIELD_KEYS = ("field", "active", "max", "per_lap", "running")   # map keys that name one telemetry field
LAMP_ICONS = ("brake", "engine", "oil", "coolant")


def check_dash(game: dict) -> None:
    """Drop dash box cards with an unknown type, action or field (with a log line)."""
    good = []
    for number, control in enumerate(game["dash"], 1):
        kind = DASH_TYPES.get(control.get("type"))
        problem = None
        if kind is None:
            problem = f"unknown type '{control.get('type')}'"
        elif missing := [key for key in kind["need"] if not control.get(key)]:
            problem = f"missing {', '.join(missing)}"
        else:
            fields = list(control.get("fields", [])) + [control[key] for key in DASH_FIELD_KEYS if control.get(key)]
            unknown = [f for f in fields if f not in telemetry.FIELDS]
            unknown += [icon for icon in control.get("icons", []) if icon not in LAMP_ICONS]
            if control["type"] == "value" and control.get("fmt", "int") not in ("lap", "pct", "speed", "int"):
                unknown.append(f"fmt {control.get('fmt')}")
            unknown += [control[key] for key in kind["actions"] if control.get(key) and control[key] not in actions.BY_NAME]
            if unknown:
                problem = f"unknown {', '.join(unknown)}"
        if problem:
            log.line("dash", game["id"], f"card {number} ({control.get('label', '?')}) ignored: {problem}")
        else:
            good.append(control)
    game["dash"] = good


def dash_layout(game: dict, handled: set) -> list[dict]:
    """The dash box cards for the page, with "enabled" per action (a key is set or the game handles it)
    and "kinds" per action ("tap", or "hold": pressed while the finger is on the button)."""
    out = []
    for control in game["dash"]:
        card = dict(control)
        names = [control[key] for key in DASH_TYPES[control["type"]]["actions"] if control.get(key)]
        card["enabled"] = {name: bool(game["keys"].get(name)) or name in handled for name in names}
        card["kinds"] = {name: actions.BY_NAME[name]["type"] for name in names}
        out.append(card)
    return out


def activate(game_id: str) -> None:
    global active, connector, data
    with game_lock:
        with key_lock:
            release_all()
        if connector is not None:
            try:
                connector.close()
            except Exception as error:  # noqa: BLE001
                log.line("game", "close", repr(error))
        active = games[game_id]
        connector = load_connector(active)
        with data_lock:
            data = telemetry.blank()
        log.line("game", "active", f"{game_id} ({active['game']['name']})")


def reader() -> None:
    global data, seq
    period = 1.0 / max(1, cfg["telemetry"]["read_hz"])
    opened_for = None
    failed = None
    while True:
        start = time.monotonic()
        with game_lock:
            current = connector
            try:
                if opened_for is not current:
                    current.open()
                    opened_for = current
                values = current.read()
                if failed:
                    log.line("game", "read", "ok again")
                    failed = None
            except Exception as error:  # noqa: BLE001  a connector error must never stop the bridge
                values = None
                if repr(error) != failed:
                    failed = repr(error)
                    log.line("game", "read error", failed)
                try:
                    current.close()
                except Exception:  # noqa: BLE001
                    pass
                opened_for = None
        fresh = telemetry.with_error(values, bool(failed))
        with data_lock:
            if fresh["error_text"] != data.get("error_text"):
                log.line("data", "error" if fresh["error"] else "ok", fresh["error_text"] or "data as expected")
            if fresh != data:
                data = fresh
                seq += 1
        time.sleep(1.0 if failed else max(0.0, period - (time.monotonic() - start)))


def snapshot() -> tuple[int, dict]:
    with data_lock:
        return seq, dict(data, game=active["id"])


# ---------------------------------------------------------------- commands

def release_all() -> None:
    for action in list(held):
        combo = active["keys"].get(action) if active else None
        if combo:
            keys.up(combo)
        held.pop(action, None)


def hold_watchdog() -> None:
    """Releases a held key whose 'up' never arrived (tablet lost Wi-Fi, page closed)."""
    while True:
        time.sleep(0.5)
        limit = cfg["input"]["hold_max_s"]
        with key_lock:
            for action, since in list(held.items()):
                if time.monotonic() - since > limit:
                    keys.up(active["keys"][action])
                    held.pop(action, None)
                    log.line("command", action, f"released after {limit} s")


def command(body: dict) -> tuple[bool, str]:
    action = body.get("action")
    state = body.get("state", "tap")
    button = actions.BY_NAME.get(action)
    if button is None:
        return False, "unknown action"
    if state not in (("tap",) if button["type"] == "tap" else ("down", "up")):
        return False, f"state '{state}' not valid for a {button['type']} button"
    with game_lock:
        if connector.handle(action, state):
            log.line("command", action, f"{state} (handled by {active['id']})")
            return True, ""
    combo = active["keys"].get(action)
    if not combo:
        return False, f"no key set for {action}"
    if not keys.available:
        return False, "keypresses work on Windows only"
    window = active["window"]
    with key_lock:
        if state == "up":
            if action in held:
                keys.up(combo)
                held.pop(action, None)
            log.line("command", action, "up")
            return True, ""
        if not keys.focus(window.get("process", ""), window.get("title", "")):
            log.line("refused", action, "game window not found")
            return False, "game window not found"
        if state == "down":
            if action not in held:
                keys.down(combo)
                held[action] = time.monotonic()
        else:
            keys.tap(combo, cfg["input"]["tap_ms"] / 1000)
    log.line("command", action, f"{state} {combo}")
    return True, ""


# ---------------------------------------------------------------- web server

def info() -> dict:
    handled = set(getattr(connector, "HANDLES", ()))
    return {
        "game": active["id"],
        "game_name": active["game"]["name"],
        "games": [{"id": g["id"], "name": g["game"]["name"]} for g in games.values()],
        "groups": actions.layout(active["keys"], handled),
        "dash": dash_layout(active, handled),
        "address": address,
        "hz_choices": [hz for hz in HZ_CHOICES if hz <= cfg["telemetry"]["read_hz"]],
        "keys_available": keys.available,
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        pass

    def reply(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def reply_json(self, status: int, payload: dict) -> None:
        self.reply(status, "application/json", json.dumps(payload).encode())

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/stream":
            return self.stream(parse_qs(url.query))
        if url.path == "/state":
            return self.reply_json(200, snapshot()[1])
        if url.path == "/api/info":
            return self.reply_json(200, info())
        self.static(url.path)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.reply_json(400, {"error": "bad request"})
        path = urlparse(self.path).path
        if path == "/api/command":
            ok, error = command(body)
            return self.reply_json(200 if ok else 409, {"ok": True} if ok else {"error": error})
        if path == "/api/settings":
            game_id = body.get("game")
            if game_id not in games:
                return self.reply_json(400, {"error": "unknown game"})
            if game_id != active["id"]:
                activate(game_id)
                settings["game"] = game_id
                config.save_settings(settings)
            return self.reply_json(200, info())
        self.reply_json(404, {"error": "not found"})

    def static(self, path: str) -> None:
        name = path.strip("/") or "index"
        target = (config.UI / name).resolve()
        if not target.suffix:
            target = target.with_suffix(".html")
        if config.UI not in target.parents or not target.is_file():
            return self.reply(404, "text/plain", b"not found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self.reply(200, content_type, target.read_bytes())

    def stream(self, query: dict) -> None:
        """Server-Sent Events: one JSON telemetry frame per tick at the rate the page asks for."""
        try:
            hz = int(query.get("hz", ["30"])[0])
        except ValueError:
            hz = 30
        hz = min(max(1, hz), cfg["telemetry"]["read_hz"])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        last_seq, last_sent = -1, 0.0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            while True:
                tick = time.monotonic()
                current_seq, frame = snapshot()
                if current_seq != last_seq or tick - last_sent > HEARTBEAT_S:
                    self.wfile.write(b"data: " + json.dumps(frame, separators=(",", ":")).encode() + b"\n\n")
                    last_seq, last_sent = current_seq, tick
                time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - tick)))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def setup(file_log: bool = True) -> str:
    """Load config and games; returns the start game."""
    global cfg, games, settings
    cfg = config.load()
    cfg["log"]["enabled"] = cfg["log"]["enabled"] and file_log
    log.setup(cfg["log"])
    games = config.load_games(cfg)
    if not games:
        raise SystemExit("No game found in games/.")
    for game in games.values():
        check_keys(game)
        check_dash(game)
    settings = config.load_settings()
    wanted = settings.get("game") or cfg["dashboard"]["game"]
    if wanted not in games:
        log.line("game", "unknown", f"'{wanted}', using '{next(iter(games))}'")
        wanted = next(iter(games))
    return wanted


def check() -> None:
    """--check: load everything, print a summary, exit. Used by the installer."""
    wanted = setup(file_log=False)
    port = cfg["dashboard"]["port"]
    names = ", ".join(f"{game_id} ({game['game']['name']})" for game_id, game in games.items())
    print("Racing Dashboard check")
    print(f"  Python        {sys.version.split()[0]}")
    print(f"  Games         {names}")
    print(f"  Start game    {wanted}")
    print(f"  Web port      {port}")
    print(f"  Address       http://{lan_ip()}:{port}")
    print(f"  Keypresses    {'available' if keys.available else 'not available (Windows only)'}")
    print("  Result        OK")


def banner(port: int) -> None:
    line = "=" * 64
    print(f"\n{line}\n  Racing Dashboard is running  ({active['game']['name']})\n")
    print("  On your phone or tablet (same Wi-Fi), open in the browser:\n")
    print(f"      {address}\n")
    print(f"      Gear + Rev   {address}/gear")
    print(f"      Dash         {address}/dash\n")
    print("  Tip: Share > Add to Home Screen runs it full screen.")
    print(f"  Close this window (or press Ctrl+C) to stop.\n{line}\n", flush=True)


def main() -> None:
    global address
    if "--check" in sys.argv:
        return check()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("Racing Dashboard")
    wanted = setup()
    activate(wanted)
    if not keys.available:
        log.line("keys", "unavailable", "not on Windows: buttons are sent only to the demo game")
    host, port = cfg["dashboard"]["host"], cfg["dashboard"]["port"]
    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as error:
        log.line("server", "error", f"port {port}: {error}")
        raise SystemExit(f"\nPort {port} is in use: Racing Dashboard is probably running already in another window.\n"
                         f"Close it first, or set another [dashboard] port in config/config.toml.")
    server.daemon_threads = True
    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=hold_watchdog, daemon=True).start()
    address = f"http://{lan_ip()}:{port}"
    log.line("server", "open", address)
    banner(port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with key_lock:
            release_all()
        log.line("server", "stopped")


if __name__ == "__main__":
    main()
