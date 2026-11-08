"""Prints the live ACE values the dashboard reads, five times per second (Windows, game running).

Use it to check the connector against the game: drive, shift, change TC / ABS / brake bias /
lights and see whether the values follow. Stop with Ctrl+C.

Run:  python tools/ace_probe.py
      python tools/ace_probe.py --analysis   the analysis page's values (lap position, track length,
                                             map position, steering, session) and every occupied
                                             car_coordinates slot with its driver id, to see which
                                             slot is the player
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
ANALYSIS = ("status", "lap_pos", "track_length_m", "pos_x", "pos_y", "steer", "speed_kmh", "lap_valid",
            "session_id", "air_c", "road_c", "tyre_compound", "time_of_day")


def slots(connector) -> str:
    """Occupied car_coordinates slots: index, x / z, driver id; * = the slot the connector uses."""
    gr = ace.Graphics.from_buffer_copy(connector.blocks[1].read()[:ace.sizeof(ace.Graphics)])
    used = ace.player_xy(gr)
    out = [f"player id {gr.player_car_id_a}/{gr.player_car_id_b}"]
    for i in range(60):
        x, _, z = gr.car_coordinates[i]
        if x or z:
            mark = "*" if (round(x, 2), round(z, 2)) == used else " "
            out.append(f"{mark}[{i}] {x:.1f},{z:.1f} id {gr.car_ids[i][0]}/{gr.car_ids[i][1]}")
    return "  ".join(out)


def main() -> None:
    analysis = "--analysis" in sys.argv
    show = ANALYSIS if analysis else SHOW
    cfg = config.load()
    connector = ace.Connector({"id": "ace"}, cfg)
    print("Waiting for Assetto Corsa EVO ... (Ctrl+C to stop)")
    try:
        while True:
            values = connector.read()
            if values is None:
                print("\rgame not running" + " " * 60, end="", flush=True)
            else:
                print("\n" + "  ".join(f"{name}={values.get(name)}" for name in show), flush=True)
                if analysis:
                    print("    " + slots(connector), flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        connector.close()


if __name__ == "__main__":
    main()
