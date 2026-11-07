"""The universal telemetry model.

Every connector (one per game, in games/<game>/connector.py) translates its game's data into
this one flat dictionary. The UI only knows these names, so every page works with every game.
A connector fills what its game provides and leaves the rest at the default below.
"""

# name: default. Units are fixed so the UI never has to know which game is running.
FIELDS = {
    # session
    "connected": False,      # True while the game delivers fresh data
    "status": "off",         # "off", "live", "pause", "replay"
    "car": "",               # car name as the game reports it
    "track": "",             # track name as the game reports it
    # engine and gearbox
    "gear": 0,               # -1 = R, 0 = N, 1.. = forward gears
    "max_gears": 0,          # number of forward gears, 0 = unknown
    "rpm": 0,                # engine speed, 1/min
    "rpm_max": 0,            # redline / limiter, 1/min, 0 = unknown
    "rpm_pct": 0.0,          # rpm as share of rpm_max, 0..1
    "shift_up": False,       # the game says: shift up now
    "shift_down": False,     # the game says: shift down now
    "limiter": False,        # rev limiter hit
    # motion and pedals
    "speed_kmh": 0.0,
    "gas": 0.0,              # 0..1
    "brake": 0.0,            # 0..1
    "clutch": 0.0,           # 0..1
    # driving aids and car systems
    "tc_level": None,        # driver setting, None = not available
    "tc_active": False,      # TC is cutting right now
    "abs_level": None,
    "abs_active": False,
    "brake_bias": None,      # front share 0..1
    "engine_map": None,
    "pit_limiter": False,
    "ignition": None,        # True / False, None = not available
    "engine_running": None,
    "lights": None,          # headlight stage, 0 = off
    "wipers": None,          # wiper level, 0 = off
    # fuel
    "fuel_l": None,
    "fuel_max_l": None,
    "fuel_per_lap_l": None,
    # timing (milliseconds; None = no time yet)
    "lap": 0,                # completed laps
    "position": 0,
    "cars": 0,
    "lap_ms": None,
    "last_ms": None,
    "best_ms": None,
    "delta_ms": None,        # to best lap, negative = faster
    "lap_valid": True,
    "flag": "none",          # "none", "blue", "yellow", "black", "white", "checkered", "green", ...
}


def blank() -> dict:
    return dict(FIELDS)


class Connector:
    """Base class of a game connector. A game folder's connector.py defines `Connector(Connector)`.

    read() is called by the core at [telemetry] read_hz. It returns a dict with names from FIELDS
    (missing names keep their defaults), or None while the game is not running.
    """

    def __init__(self, game: dict, cfg: dict):
        self.game = game      # the parsed games/<game>/game.toml
        self.cfg = cfg        # the full config

    def open(self) -> None:
        pass

    def read(self) -> dict | None:
        return None

    def close(self) -> None:
        pass

    def handle(self, action: str, state: str) -> bool:
        """Return True if the connector carried out the action itself (no keypress needed)."""
        return False
