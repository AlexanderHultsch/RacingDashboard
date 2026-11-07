"""Prints the live ACE values the dashboard reads, five times per second (Windows, game running).

Use it to check the connector against the game: drive, shift, change TC / ABS / brake bias /
lights and see whether the values follow. Stop with Ctrl+C.

Run:  python tools/ace_probe.py
"""
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import config  # noqa: E402

spec = importlib.util.spec_from_file_location("ace_connector", ROOT / "games" / "ace" / "connector.py")
ace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ace)

SHOW = ("connected", "status", "gear", "rpm", "rpm_max", "rpm_pct", "shift_up", "limiter", "speed_kmh",
        "tc_level", "abs_level", "brake_bias", "engine_map", "pit_limiter", "lights", "wipers", "ignition",
        "fuel_l", "lap_ms", "last_ms", "best_ms", "car", "track")


def main() -> None:
    cfg = config.load()
    connector = ace.Connector({"id": "ace"}, cfg)
    print("Waiting for Assetto Corsa EVO ... (Ctrl+C to stop)")
    try:
        while True:
            values = connector.read()
            if values is None:
                print("\rgame not running" + " " * 60, end="", flush=True)
            else:
                print("\n" + "  ".join(f"{name}={values.get(name)}" for name in SHOW), flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        connector.close()


if __name__ == "__main__":
    main()
