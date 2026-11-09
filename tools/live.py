"""Live debugging: watch, record and check the values the bridge serves, for every game.

Reads the running bridge (http://127.0.0.1:<port>/state, the same frame the pages get), so it works the same
for ACE, Assetto Corsa Rally, iRacing, DiRT Rally 2.0 and the demo. Start the bridge first, then in a second
window:

  python tools/live.py                         watch the basic values (5 lines a second)
  python tools/live.py grip                    watch a preset: basic grip boost revs aids tyres car analysis
  python tools/live.py grip --changes          print a line only when a shown value changes
  python tools/live.py --fields rpm,boost_bar  watch any fields
  python tools/live.py --once                  the whole frame once, as JSON
  python tools/live.py --record 60             record every frame for 60 s (20 a second) to
                                               logs/live-<game>-<date_time>.jsonl, then check it
  python tools/live.py --check last            check the newest recording again (or give a file)

The check prints what each open question needs (docs/HANDOVER.md): the sign of the wheel slip under braking
and on wheelspin, the GRIP stages per wheel, the slip where ABS / TC start to work, the rpm of the shift signal
and the limiter per gear, the boost range, and min / max / values of every field. Problems are marked "!!".
The recordings stay in logs/ (not in git); paste the check's output into the chat.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import config  # noqa: E402

PRESETS = {
    "basic": "status error_text gear rpm rpm_pct speed_kmh gas brake",
    "grip": "speed_kmh gas brake abs_level abs_active tc_level tc_active wheel_slip wheel_lock",
    "boost": "rpm rpm_pct gas boost_bar boost_min_bar boost_max_bar",
    "revs": "gear rpm rpm_max rpm_pct shift_up limiter",
    "aids": "tc_level tc_cut_level tc_active abs_level abs_active esc_level esc_active engine_map brake_bias "
            "drive_mode drive_mode_name fixed",
    "tyres": "tyre_temp_c tyre_psi brake_temp_c",
    "car": "pit_limiter lights wipers ignition engine_running latched warn_brake warn_engine warn_oil warn_coolant",
    "analysis": "lap_pos track_length_m pos_x pos_y steer lap_ms lap_valid session_id",
}
WHEELS = ("FL", "FR", "RL", "RR")
MIN_KMH = 10                       # as on the GRIP page: no stage below this speed


def grip_stages() -> list:
    """The GRIP page's stage limits, read from ui/js/grip.js so this tool always checks what the page shows."""
    text = (ROOT / "ui" / "js" / "grip.js").read_text(encoding="utf-8")
    match = re.search(r"const STAGES = \[([^\]]+)\]", text)
    return [float(v) for v in match.group(1).split(",")] if match else [0.04, 0.07, 0.15, 0.4]


STAGES = grip_stages()


def stage(slip, locked=False) -> str:
    """The GRIP page's class for one wheel: l1..l4 braking, s1..s4 wheelspin, "" grip (as RD.gripStage)."""
    if locked:
        return "l4"
    if not isinstance(slip, (int, float)):
        return ""
    n = sum(abs(slip) >= limit for limit in STAGES)
    return (("l" if slip < 0 else "s") + str(n)) if n else ""


def bridge_url(given: str | None) -> str:
    if given:
        return given.rstrip("/")
    port = config.load()["dashboard"]["port"]
    return f"http://127.0.0.1:{port}"     # not localhost: on Windows that tries IPv6 first, ~2 s per frame


def frame(url: str) -> dict:
    with urllib.request.urlopen(url + "/state", timeout=2) as reply:
        return json.loads(reply.read())


def show(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") if abs(value) < 100 else f"{value:.0f}"
    if isinstance(value, list):
        return "[" + " ".join(show(v) for v in value) + "]"
    if value is None:
        return "-"
    return str(value)


def line(f: dict, fields: list) -> str:
    parts = [f"{name}={show(f.get(name))}" for name in fields]
    if "wheel_slip" in fields and isinstance(f.get("wheel_slip"), list):
        locks = f.get("wheel_lock") or [False] * 4
        moving = (f.get("speed_kmh") or 0) >= MIN_KMH
        parts.append("stages=" + " ".join(f"{w}:{(stage(s, l is True) if moving else '') or '-'}"
                                          for w, s, l in zip(WHEELS, f["wheel_slip"], locks)))
    return " ".join(parts)


def watch(url: str, fields: list, hz: float, changes: bool) -> None:
    print(f"{url}/state  fields: {' '.join(fields)}  (Ctrl+C stops)")
    last = None
    while True:
        try:
            text = line(frame(url), fields)
        except OSError as error:
            text = f"!! bridge not reachable: {error}"
        if not changes or text != last:
            print(time.strftime("%H:%M:%S ") + text, flush=True)
            last = text
        time.sleep(1 / hz)


def record(url: str, seconds: float, hz: float) -> Path:
    first = frame(url)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = ROOT / "logs" / f"live-{first.get('game') or 'game'}-{stamp}.jsonl"
    path.parent.mkdir(exist_ok=True)
    print(f"recording {seconds:.0f} s at {hz:.0f} Hz to {path.relative_to(ROOT)}  (Ctrl+C stops early)")
    start = time.monotonic()
    count = 0
    with path.open("w", encoding="utf-8") as out:
        try:
            while time.monotonic() - start < seconds:
                try:
                    f = frame(url)
                except OSError as error:
                    print(f"!! bridge not reachable: {error}")
                    time.sleep(1)
                    continue
                f["_t"] = round(time.monotonic() - start, 3)
                out.write(json.dumps(f, separators=(",", ":")) + "\n")
                count += 1
                if count % int(hz * 5) == 0:
                    print(f"  {f['_t']:5.0f} s  {line(f, PRESETS['basic'].split())}", flush=True)
                time.sleep(max(0.0, start + count / hz - time.monotonic()))
        except KeyboardInterrupt:
            print("  stopped")
    print(f"{count} frames written")
    return path


# ---------------------------------------------------------------- the check

def numbers(values):
    return [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else None


def check(path: Path) -> None:
    frames = [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines() if text.strip()]
    if not frames:
        print(f"!! {path.name}: empty")
        return
    span = frames[-1].get("_t", 0) - frames[0].get("_t", 0)
    print(f"== {path.name}: {len(frames)} frames in {span:.0f} s ({len(frames) / span if span else 0:.1f} / s)")
    for key in ("game", "car", "track"):
        print(f"   {key}: {', '.join(sorted({str(f.get(key) or '-') for f in frames}))}")
    errors = {f.get("error_text") for f in frames if f.get("error")}
    if errors:
        print(f"   errors seen: {', '.join(sorted(errors))}")
    live = [f for f in frames if f.get("connected") and not f.get("error")]
    print(f"   frames with live data: {len(live)}")
    if not live:
        return
    check_grip(live)
    check_aids(live)
    check_revs(live)
    check_boost(live)
    check_fields(live)


def check_grip(frames: list) -> None:
    print("\n-- GRIP (wheel_slip, wheel_lock)")
    with_slip = [f for f in frames if isinstance(f.get("wheel_slip"), list)]
    if not with_slip:
        print("   no wheel_slip in this game / recording (iRacing sends none)")
        return
    moving = [f for f in with_slip if (f.get("speed_kmh") or 0) >= MIN_KMH]
    braking = [f for f in moving if (f.get("brake") or 0) > 0.5]
    power = [f for f in moving if (f.get("gas") or 0) > 0.9 and (f.get("brake") or 0) < 0.05]
    steady = [f for f in moving if 0.2 < (f.get("gas") or 0) < 0.9 and (f.get("brake") or 0) < 0.05]
    for name, group, wheels, want in (("hard braking (brake > 50 %)", braking, (0, 1), "negative"),
                                      ("full throttle", power, (2, 3), "positive"),
                                      ("part throttle (should be near 0)", steady, (0, 1, 2, 3), None)):
        if not group:
            print(f"   {name}: no frames")
            continue
        parts = []
        for w in wheels:
            slips = numbers(f["wheel_slip"][w] for f in group)
            parts.append(f"{WHEELS[w]} median {median(slips):+.3f} min {min(slips):+.3f} max {max(slips):+.3f}")
        print(f"   {name}, {len(group)} frames: " + "; ".join(parts))
        if want:
            values = numbers(f["wheel_slip"][w] for f in group for w in wheels)
            neg = sum(v < -0.02 for v in values)
            pos = sum(v > 0.02 for v in values)
            if want == "negative" and pos > neg:
                print("   !! the slip is mostly POSITIVE under braking: the sign is the other way round (flip it in the connector)")
            elif want == "positive" and neg > pos:
                print("   !! the slip is mostly NEGATIVE on full throttle: the sign is the other way round (flip it in the connector)")
            elif neg + pos == 0:
                print("   !! no slip at all here: the game may not fill the value")
            else:
                print(f"   sign OK ({neg} negative, {pos} positive samples)")
    if steady:
        worst = max(abs(v) for f in steady for v in numbers(f["wheel_slip"]))
        if worst > STAGES[1]:
            print(f"   !! up to {worst:.2f} slip at part throttle: wrong units or the stages start too early")
    print(f"   stages (limits {' / '.join(f'{v:g}' for v in STAGES)}), share of moving frames:")
    for w, name in enumerate(WHEELS):
        counts = {}
        for f in moving:
            locks = f.get("wheel_lock") or [False] * 4
            key = stage(f["wheel_slip"][w], locks[w] is True) or "grip"
            counts[key] = counts.get(key, 0) + 1
        order = ["grip", "l1", "l2", "l3", "l4", "s1", "s2", "s3", "s4"]
        print(f"     {name}: " + "  ".join(f"{k} {100 * counts[k] / len(moving):.0f}%" for k in order if k in counts))
    locks = [f for f in with_slip if isinstance(f.get("wheel_lock"), list)]
    if locks:
        set_ = [(w, f["wheel_slip"][w]) for f in locks for w in range(4) if f["wheel_lock"][w]]
        if set_:
            slips = numbers(s for _, s in set_)
            print(f"   lock flag set in {len(set_)} wheel samples (slip then: median {median(slips):+.3f}, max {max(slips):+.3f})")
        else:
            print("   lock flag never set (lock a wheel with ABS off to see whether the game uses it)")
    else:
        print("   no lock flag in this game")


def onset(frames: list, flag: str, wheels: tuple) -> list:
    """The largest |slip| of the given wheels in the frame where the flag turns on."""
    out, before = [], False
    for f in frames:
        on = bool(f.get(flag))
        if on and not before and isinstance(f.get("wheel_slip"), list):
            out.append(max(abs(f["wheel_slip"][w]) for w in wheels))
        before = on
    return numbers(out)


def check_aids(frames: list) -> None:
    print("\n-- ABS / TC")
    for name, level, flag, wheels in (("ABS", "abs_level", "abs_active", (0, 1)), ("TC", "tc_level", "tc_active", (2, 3))):
        levels = sorted({str(f.get(level)) for f in frames})
        active = sum(bool(f.get(flag)) for f in frames)
        line_ = f"   {name}: setting {', '.join(levels)}; working in {active} frames"
        starts = onset(frames, flag, wheels)
        if starts:
            line_ += f"; slip when it starts: median {median(starts):.3f} (min {min(starts):.3f}, max {max(starts):.3f}, {len(starts)} times)"
            line_ += f"  -> GRIP stage 2 starts at {STAGES[1]:g}"
        print(line_)


def check_revs(frames: list) -> None:
    print("\n-- REVS (shift signal and limiter per gear)")
    per_gear, before = {}, False
    for f in frames:
        on = bool(f.get("shift_up"))
        if on and not before:
            per_gear.setdefault(f.get("gear"), {"shift": [], "limiter": []})["shift"].append(f.get("rpm"))
        before = on
        if f.get("limiter"):
            per_gear.setdefault(f.get("gear"), {"shift": [], "limiter": []})["limiter"].append(f.get("rpm"))
    if not per_gear:
        print("   no shift signal or limiter in this recording")
    for gear in sorted(per_gear, key=lambda g: (g is None, g)):
        s, lim = numbers(per_gear[gear]["shift"]), numbers(per_gear[gear]["limiter"])
        print(f"   gear {gear}: shift signal at {', '.join(str(r) for r in s[:6]) or '-'} rpm; "
              f"limiter from {min(lim) if lim else '-'} rpm")
    print(f"   rpm_max: {', '.join(sorted({str(f.get('rpm_max')) for f in frames}))}")


def check_boost(frames: list) -> None:
    print("\n-- BOOST")
    boost = numbers(f.get("boost_bar") for f in frames)
    if not boost:
        print("   no boost value (the game sends none)")
        return
    top = max(frames, key=lambda f: f.get("boost_bar") if isinstance(f.get("boost_bar"), (int, float)) else -9)
    print(f"   boost {min(boost):.2f} .. {max(boost):.2f} bar (highest at {top.get('rpm')} rpm, "
          f"gas {top.get('gas')}); boost_max_bar {', '.join(sorted({str(f.get('boost_max_bar')) for f in frames}))}")


def check_fields(frames: list) -> None:
    print("\n-- every field (min .. max, or the values seen)")
    skip = {"_t", "limits", "error", "error_text", "ui"}
    for name in sorted({k for f in frames for k in f} - skip):
        values = [f.get(name) for f in frames]
        if all(v is None for v in values):
            continue
        if all(isinstance(v, list) or v is None for v in values):
            rows = [v for v in values if v]
            width = max((len(v) for v in rows), default=0)
            cols = [numbers(r[i] for r in rows if i < len(r)) for i in range(width)]
            if cols and all(cols):
                print(f"   {name}: " + "  ".join(f"{min(c):g}..{max(c):g}" for c in cols))
            else:
                print(f"   {name}: {', '.join(sorted({json.dumps(v) for v in values}))[:150]}")
        elif numbers(values) and len(numbers(values)) == len([v for v in values if v is not None]):
            n = numbers(values)
            print(f"   {name}: {min(n):g} .. {max(n):g}")
        else:
            seen = sorted({json.dumps(v) for v in values})
            print(f"   {name}: {', '.join(seen[:8])}{' ...' if len(seen) > 8 else ''}")


def newest() -> Path | None:
    files = sorted((ROOT / "logs").glob("live-*.jsonl"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch, record and check the bridge's live values.")
    parser.add_argument("preset", nargs="?", default="basic", choices=sorted(PRESETS), help="fields to watch")
    parser.add_argument("--fields", help="comma-separated fields to watch instead of a preset")
    parser.add_argument("--changes", action="store_true", help="print a line only when a value changes")
    parser.add_argument("--hz", type=float, help="lines (watch, default 5) or frames (record, default 20) per second")
    parser.add_argument("--once", action="store_true", help="print the whole frame once as JSON")
    parser.add_argument("--record", type=float, metavar="SECONDS", help="record every frame to logs/ and check it")
    parser.add_argument("--check", metavar="FILE", help="check a recording ('last' = the newest in logs/)")
    parser.add_argument("--url", help="the bridge, default http://127.0.0.1:<port from the config>")
    args = parser.parse_args()
    if args.check:
        path = newest() if args.check == "last" else Path(args.check)
        if not path or not path.exists():
            sys.exit("no recording found (python tools/live.py --record 60 makes one)")
        check(path)
        return
    url = bridge_url(args.url)
    try:
        if args.once:
            print(json.dumps(frame(url), indent=1, sort_keys=True))
        elif args.record:
            check(record(url, args.record, args.hz or 20))
        else:
            fields = args.fields.split(",") if args.fields else PRESETS[args.preset].split()
            watch(url, fields, args.hz or 5, args.changes)
    except KeyboardInterrupt:
        pass
    except OSError as error:
        sys.exit(f"bridge not reachable at {url}: {error}\nstart it first: python core\\server.py")


if __name__ == "__main__":
    main()
