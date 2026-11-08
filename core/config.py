import copy
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES = ROOT / "games"
UI = ROOT / "ui"
CONFIG_FILE = ROOT / "config" / "config.toml"
SETTINGS_FILE = ROOT / "config" / "settings.json"
TRAINER_FILE = ROOT / "config" / "trainer.json"    # AI trainer: provider, level, API keys (ignored by git)

DEFAULTS = {
    "dashboard": {"host": "0.0.0.0", "port": 8080, "game": "ace"},
    "telemetry": {"read_hz": 60, "stale_s": 2.0},
    "input": {"tap_ms": 80, "hold_max_s": 10.0},
    # Analysis page: lap recording (core/recorder.py); data_dir relative to the program folder
    "analysis": {"enabled": True, "data_dir": "data", "hz": 30, "section_m": 250},
    # AI trainer (core/trainer.py, docs/TRAINER.md): seconds to wait for an answer, the Ollama address,
    # and overrides of the FAST / BEST models, e.g. [trainer.models.claude.best] model = "claude-opus-5-5"
    "trainer": {"timeout_s": 90, "ollama_url": "http://localhost:11434", "models": {}},
    "log": {"enabled": True, "file": "logs/racing-dashboard.log", "max_mb": 5, "backups": 2},
    # Per game overrides of games/<game>/game.toml, e.g. [games.ace.keys] tc_up = "LCtrl+T"
    "games": {},
}


def merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def load(path: Path = CONFIG_FILE) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        with open(path, "rb") as f:
            merge(cfg, tomllib.load(f))
    cfg["log"]["file"] = str(ROOT / cfg["log"]["file"])
    cfg["analysis"]["data_dir"] = str(ROOT / cfg["analysis"]["data_dir"])
    return cfg


def load_games(cfg: dict) -> dict:
    """Every games/<id>/game.toml, with the [games.<id>] overrides of config.toml merged in."""
    games = {}
    for toml in sorted(GAMES.glob("*/game.toml")):
        with open(toml, "rb") as f:
            game = tomllib.load(f)
        game_id = toml.parent.name
        merge(game, copy.deepcopy(cfg["games"].get(game_id, {})))
        game.setdefault("game", {})
        game["game"].setdefault("name", game_id)
        game.setdefault("keys", {})
        game.setdefault("window", {})
        dash = toml.parent / "dash.toml"
        if dash.exists():
            with open(dash, "rb") as f:
                game["dash"] = tomllib.load(f).get("control", [])
        else:
            game["dash"] = []
        game["id"] = game_id
        game["dir"] = toml.parent
        games[game_id] = game
    return games


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
