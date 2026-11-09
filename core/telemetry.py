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
    "gear_mode": None,       # automatic gearbox / electric selector: None (manual or unknown), "P" park,
                             # "D" drive, "S" sport, "B" regen, "L" low, "M" manual mode. The pages show the
                             # gear number whatever the mode (owner's decision) and P only for park
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
    "tc_cut_level": None,    # TC cut (TC2, how much power is cut) setting, None = not on this car
    "abs_level": None,
    "abs_active": False,
    "brake_bias": None,      # front share 0..1
    "engine_map": None,
    "esc_level": None,       # stability control setting, None = not on this car
    "esc_active": False,     # stability control is working right now
    "diff_power": None,      # differential power (on throttle) setting, None = not adjustable
    "diff_coast": None,      # differential coast (off throttle) setting
    "diff_power_pct": None,  # differential locking on throttle as a share 0..1 (the value, not a setting step)
    "diff_coast_pct": None,
    "drive_mode": None,      # performance / drive mode as a step (ACE: active_performance_mode), None = not on this car
    "drive_mode_name": None, # the game's name of the active mode, e.g. "SPORT+"
    "tyre_temp_c": None,     # tyre temperatures [front left, front right, rear left, rear right] in C
    "tyre_psi": None,        # tyre pressures, same order, in psi
    "brake_temp_c": None,    # brake temperatures, same order, in C  # differential locking off throttle, 0..1
    # warning lamps, as a state (no value): None (not reported), "off", "cold" (blue), "warn" (yellow), "alert" (red)
    "warn_brake": None,      # brake warning (!): handbrake on, brake system
    "warn_engine": None,     # check engine: ignition on with the engine off, engine trouble
    "warn_oil": None,        # oil: no / low oil pressure, oil too hot
    "warn_coolant": None,    # coolant temperature: cold (blue), hot (yellow), overheating (red)
    # range of the stepped settings for this car: {"tc_level": [0, 11], ...}; missing = unknown
    "limits": {},
    # stepped settings this car has but the driver cannot change (e.g. ABS fixed at 1): ["abs_level"]
    "fixed": [],
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
    "lap_progress": None,    # share of the lap / stage driven, 0..1
    # analysis page (core/recorder.py)
    "lap_pos": None,         # position on the lap along the track, 0..1 (the game's normalised position)
    "track_length_m": None,  # length of the track / stage in metres
    "pos_x": None,           # car position on the map, metres (game world, seen from above)
    "pos_y": None,
    "steer": None,           # steering, -1 (full left) .. 1 (full right)
    "session_id": None,      # changes when a new game session starts (a new run)
    "air_c": None,           # ambient, written once per lap
    "road_c": None,
    "tyre_compound": None,
    "time_of_day": None,     # "hh:mm" in the game
    # set by the core, not by a connector (see check() below)
    "error": None,           # None, or a code from ERRORS
    "error_text": "",        # short text for the pages, e.g. "UNEXPECTED DATA: RPM -5"
    "latched": [],           # latch buttons whose key the bridge holds down right now, e.g. ["wipers"]
}

# Error codes the core sets in "error". The pages then show E instead of the gear.
ERRORS = {
    "no_game": "GAME NOT RUNNING",              # the connector finds no game
    "read_error": "CANNOT READ THE GAME",       # the connector raised an error
    "no_data": "NO NEW DATA FROM THE GAME",     # the game is running but its data does not change (pause, menu, loading)
    "not_driving": "NOT ON TRACK",              # the game reports no live session (menus)
    "bad_value": "UNEXPECTED DATA",             # a value is missing, not a number or out of its possible range
}

# Possible ranges of the numeric fields; a value outside means the data is not what we expect
# (a changed shared memory layout after a game update, a wrong game selected, a connector bug).
RANGES = {
    "gear": (-1, 20), "max_gears": (0, 20),
    "rpm": (0, 25000), "rpm_max": (0, 25000), "rpm_pct": (0.0, 1.5),
    "speed_kmh": (0.0, 600.0), "gas": (-0.05, 1.05), "brake": (-0.05, 1.05), "clutch": (-0.05, 1.05),
    "brake_bias": (0.0, 1.0), "fuel_l": (0.0, 1000.0), "fuel_max_l": (0.0, 1000.0),
    "diff_power_pct": (0.0, 1.0), "diff_coast_pct": (0.0, 1.0),
    "lap_progress": (0.0, 1.05), "lap_pos": (0.0, 1.0001), "steer": (-1.5, 1.5),
    "lap_ms": (0, 86_400_000), "last_ms": (0, 86_400_000), "best_ms": (0, 86_400_000),
}
REQUIRED = ("gear", "rpm", "rpm_pct")    # what the gear page needs; must be present and numeric
GEAR_MODES = (None, "P", "D", "S", "B", "L", "M")
# states of a warning lamp (fields warn_*): None = the game does not report it
LAMP_STATES = (None, "off", "cold", "warn", "alert")
LAMPS = ("warn_brake", "warn_engine", "warn_oil", "warn_coolant")


def check(values: dict) -> str | None:
    """Returns a short description of the first unexpected value, or None if the data looks right."""
    for name in REQUIRED:
        value = values.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{name.upper()} MISSING"
    for name, (low, high) in RANGES.items():
        value = values.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
            return f"{name.upper()} NOT A NUMBER"
        if not low <= value <= high:
            return f"{name.upper()} {value:g}"
    if not isinstance(values.get("gear"), int):
        return f"GEAR {values.get('gear')}"
    if values.get("gear_mode") not in GEAR_MODES:
        return f"GEAR MODE {values.get('gear_mode')}"
    for name in LAMPS:
        if values.get(name) not in LAMP_STATES:
            return f"{name.upper()} {str(values.get(name)).upper()}"
    rpm, rpm_max = values.get("rpm"), values.get("rpm_max")
    if rpm_max and rpm > rpm_max * 1.3:
        return f"RPM {rpm:g} ABOVE MAX {rpm_max:g}"
    return None


def with_error(values: dict | None, failed: bool) -> dict:
    """The frame for the pages: the connector values plus "error" and "error_text"."""
    frame = blank()
    if failed:
        code, detail = "read_error", ""
    elif values is None:
        code, detail = "no_game", ""
    else:
        frame.update(values)
        frame["error"], frame["error_text"] = None, ""
        problem = check(frame)
        if problem:
            code, detail = "bad_value", problem
        elif not frame["connected"]:
            code, detail = "no_data", ""
        elif frame["status"] == "off":
            code, detail = "not_driving", ""
        else:
            return frame
    frame["error"] = code
    frame["error_text"] = ERRORS[code] + (": " + detail if detail else "")
    return frame


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
