"""Checks the laps the analysis recorder wrote (data/runs) and the saved baselines (data/baselines).

Per run: the session it belongs to, the number of laps, the log of offers / saves. Per lap: lap time,
whether it counts (and why not), samples and sample rate, gaps in the recording, the lap position
range and order, the sum of the section times against the lap time, steering and position ranges.
Problems are marked with "!!". Use it after driving to see whether the game's data is what the
recorder expects (docs/HANDOVER.md).

Run:  python tools/analysis_check.py                 every run, newest last
      python tools/analysis_check.py --last 1        only the newest run
      python tools/analysis_check.py --game ace      only one game
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import config  # noqa: E402


def read(path: Path) -> list:
    lines = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                lines.append(json.loads(line))
            except ValueError:
                lines.append({"type": "broken", "line": number})
    return lines


def fmt(t) -> str:
    if t is None:
        return "-"
    m = int(t // 60)
    return f"{m}:{t - m * 60:06.3f}" if m else f"{t:.3f}"


def check_lap(path: Path, hz: int) -> list[str]:
    lines = read(path)
    out, warn = [], []
    head = lines[0] if lines else {}
    summary = next((l for l in reversed(lines) if l.get("type") == "summary"), {})
    samples = [l for l in lines if l.get("type") == "s"]
    sections = [l for l in lines if l.get("type") == "section"]
    if any(l.get("type") == "broken" for l in lines):
        warn.append("lines that are not JSON")
    if head.get("type") != "header":
        warn.append("no header line")
    flags = [name for name in ("out_lap", "broken", "repeated") if summary.get(name)]
    if summary.get("valid") is False:
        flags.append("invalid")
    if not summary.get("complete", True):
        flags.append("incomplete")
    line = [s for s in samples if s.get("line")]
    out.append(f"  {path.name}: {fmt(summary.get('time'))}  "
               f"{'counts' if summary.get('counts') else 'does not count: ' + (', '.join(flags) or '?')}  "
               f"{len(samples)} samples")
    if len(line) > 2:
        span = line[-1]["t"] - line[0]["t"]
        rate = (len(line) - 1) / span if span > 0 else 0
        gaps = [(a["t"], b["t"] - a["t"]) for a, b in zip(line, line[1:]) if b["t"] - a["t"] > 3.0 / hz]
        ps = [s["p"] for s in line]
        out.append(f"      rate {rate:.1f} Hz, lap position {ps[0]:.4f} .. {ps[-1]:.4f}")
        if rate < hz * 0.8:
            warn.append(f"sample rate {rate:.1f} Hz, expected about {hz}")
        if gaps:
            worst = max(gaps, key=lambda g: g[1])
            warn.append(f"{len(gaps)} gaps in the recording, longest {worst[1]:.2f} s at {worst[0]:.1f} s")
        if any(b < a for a, b in zip(ps, ps[1:])):
            warn.append("lap position goes back inside the lap line")
        if summary.get("complete") and not summary.get("out_lap") and (ps[0] > 0.02 or ps[-1] < 0.98):
            warn.append("a complete lap should run from about 0 to about 1")
        steer = [s["str"] for s in line if s.get("str") is not None]
        xs = [s["x"] for s in line if s.get("x") is not None]
        ys = [s["y"] for s in line if s.get("y") is not None]
        if steer:
            out.append(f"      steering {min(steer):+.2f} .. {max(steer):+.2f}")
            if max(abs(v) for v in steer) >= 0.999:
                warn.append("steering reaches ±1: maybe not scaled to -1..1 (degrees / radians?)")
            if max(abs(v) for v in steer) < 0.02:
                warn.append("steering stays near 0")
        if xs:
            out.append(f"      map x {min(xs):.0f} .. {max(xs):.0f}, y {min(ys):.0f} .. {max(ys):.0f} "
                       f"({max(xs) - min(xs):.0f} x {max(ys) - min(ys):.0f} m)")
            if max(xs) - min(xs) < 50 and max(ys) - min(ys) < 50:
                warn.append("the car hardly moves on the map: wrong car slot or no position")
        else:
            warn.append("no map position")
        if head.get("track_length_m") and xs:
            dist = sum(((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5
                       for a, b in zip(line, line[1:]) if a.get("x") is not None and b.get("x") is not None)
            share = dist / head["track_length_m"] / max(1e-6, ps[-1] - ps[0])
            out.append(f"      driven on the map {dist:.0f} m for {ps[-1] - ps[0]:.0%} of a {head['track_length_m']:.0f} m track")
            if not 0.85 < share < 1.2:
                warn.append(f"driven distance / track length = {share:.2f}: track length or position scale wrong?")
    times = summary.get("sections") or []
    if summary.get("time") and times and all(t is not None for t in times):
        total = sum(times)
        out.append(f"      sections {len(times)}, sum {fmt(total)} (lap {fmt(summary['time'])})")
        if abs(total - summary["time"]) > 0.05:
            warn.append(f"section times add up to {total:.3f}, lap time {summary['time']:.3f}")
    repeats = [f"{s['sec']}" for s in sections if s.get("att", 1) > 1]
    if repeats:
        out.append(f"      repeated sections: {', '.join(repeats)}")
    ambient = next((l for l in lines if l.get("type") == "ambient"), None)
    if ambient:
        out.append("      ambient " + ", ".join(f"{k} {v}" for k, v in ambient.items() if k != "type"))
    out += [f"      !! {w}" for w in warn]
    return out


def main() -> None:
    cfg = config.load()
    data = Path(cfg["analysis"]["data_dir"])
    hz = int(cfg["analysis"]["hz"])
    game = sys.argv[sys.argv.index("--game") + 1] if "--game" in sys.argv else "*"
    runs = sorted((data / "runs").glob(f"{game}/*/*/*"), key=lambda p: p.name)
    if "--last" in sys.argv:
        runs = runs[-int(sys.argv[sys.argv.index("--last") + 1]):]
    if not runs:
        print(f"No runs in {data / 'runs'}")
    for run in runs:
        log = read(run / "run.jsonl") if (run / "run.jsonl").exists() else []
        head = log[0] if log else {}
        kinds = {}
        for event in log[1:]:
            kinds[event.get("type")] = kinds.get(event.get("type"), 0) + 1
        print(f"\nRUN {run.relative_to(data / 'runs')}")
        print(f"  session {head.get('session')!r}, track {head.get('track_length_m')} m, {head.get('sections')} sections; "
              + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
        for lap in sorted(run.glob("lap-*.jsonl")):
            print("\n".join(check_lap(lap, hz)))
    bases = sorted((data / "baselines").glob(f"{game}/*/*"))
    if bases:
        print("\nBASELINES")
    for folder in bases:
        lap = folder / "lap.jsonl"
        lap_time = next((l.get("time") for l in reversed(read(lap)) if l.get("type") == "summary"), None) if lap.exists() else None
        count = len(list((folder / "sections").glob("section-??.jsonl")))
        print(f"  {folder.relative_to(data / 'baselines')}: best lap {fmt(lap_time)}, {count} section bests")
    pending = data / "pending.jsonl"
    if pending.exists():
        print(f"\nOPEN OFFERS (kept over a restart): {max(0, len(read(pending)) - 1)}")


if __name__ == "__main__":
    main()
