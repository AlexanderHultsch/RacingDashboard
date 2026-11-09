"""Prints the live ACE values the dashboard reads, five times per second (Windows, game running).

Use it to check the connector against the game: drive, shift, change TC / ABS / brake bias /
lights and see whether the values follow. Stop with Ctrl+C.

Run:  python tools/ace_probe.py
      python tools/ace_probe.py --analysis   the analysis page's values (lap position, track length,
                                             map position, steering, session) and every occupied
                                             car_coordinates slot with its driver id, to see which
                                             slot is the player
      python tools/ace_probe.py --raw        the raw ACE values behind GRIP and BOOST: physics slipRatio and
                                             wheelSlip, the graphics tyre slip / lock, the TC / ABS flags of both
                                             pages, and every turbo value (which one is the boost, in what unit)
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


def raw(connector) -> str:
    """The raw values behind GRIP and BOOST, straight from the shared memory (not what the connector made of them)."""
    ph = ace.Physics.from_buffer_copy(connector.blocks[0].read()[:ace.sizeof(ace.Physics)])
    gr = ace.Graphics.from_buffer_copy(connector.blocks[1].read()[:ace.sizeof(ace.Graphics)])
    tyres = (gr.tyre_lf, gr.tyre_rf, gr.tyre_lr, gr.tyre_rr)
    four = lambda values: " ".join(f"{v:+.3f}" for v in values)  # noqa: E731
    return (f"    slipRatio {four(ph.slipRatio)} | wheelSlip {four(ph.wheelSlip)} | tyre slip {four(t.slip for t in tyres)}"
            f" | lock {' '.join(str(int(t.lock)) for t in tyres)}\n"
            f"    tcInAction {ph.tcInAction} absInAction {ph.absInAction} tc {ph.tc:.3f} abs {ph.abs:.3f}"
            f" | gr tc_active {int(gr.tc_active)} abs_active {int(gr.abs_active)}\n"
            f"    turbo_boost {gr.turbo_boost:.3f} turbo_boost_level {gr.turbo_boost_level:.3f} turbo_boost_perc {gr.turbo_boost_perc:.3f}"
            f" electronics.turbo_level {gr.electronics.turbo_level:.3f} max_turbo_boost {gr.max_turbo_boost:.3f} | physics turboBoost {ph.turboBoost:.3f}")


def main() -> None:
    analysis = "--analysis" in sys.argv
    raw_values = "--raw" in sys.argv
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
                if raw_values:
                    print(raw(connector), flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        connector.close()


if __name__ == "__main__":
    main()
