# Analysis page – agreed strategy

The analysis page as agreed with the owner (interview, November 2026). **Built** (November 2026): `core/recorder.py`, `ui/analysis.html`, `ui/js/analysis.js`; technical details in [SPEC.md](SPEC.md#analysis). Verified with Assetto Corsa EVO at Brands Hatch (lap and section times against the game's own, map, deltas, REVIEW / SAVE, graphs); DiRT Rally 2.0 not yet. The page itself only shows data; tips come only from the **AI trainer**, on a tap ([TRAINER.md](TRAINER.md)). This replaces the earlier rule "no coaching, no tips".

## The page (one page; iPad landscape; right side: REVIEW and GRAPHS tabs)

- **Left: the circuit map** with the track cut into sections. Overview of the whole track; tapping a section zooms into it, **BACK** (top left of the map) returns to the overview. **Dragging a finger along the track** (overview or section) moves a yellow ring on the map and a yellow cursor line through all graphs at the same place (no value readouts); the part of the lines after the cursor is faded. The best / last / now lines are slightly see-through (owner, November 2026).
- **Race lines** drawn on the map in high quality: **green** = the best (baseline) section, **blue** = the last lap, **red** = the current lap (after the session: the lap being looked at). No braking markers.
- **Right: graphs for the selected section**, each with the same three lines (green best, blue last, red current), over the position in the section: speed, throttle, brake, steering, gear (throttle / brake and steering / gear as separate small graphs, so the colours keep meaning best / last / current), and the time delta building up inside the section. **4 graphs per page**, scrolled up / down (owner, November 2026): page 1 speed, throttle, brake, delta; page 2 steering, gear, TC, ABS; page 3 stability, engine map.
- **Driving aids** (owner, November 2026): when TC, ABS and stability work, and at which level TC (with TC cut), ABS, stability and the engine map were set, per line, to see how much assistance is good and where it costs time. Levels rarely change, so these graphs sit on the later pages. The AI trainer gets the same facts.
- **Always visible:** delta per section against best ever and against last lap, and delta per lap against best ever and against last lap.
- **Section strip** under the map: the delta of every section against best and against last (two rows), horizontally scrollable with a slider for long tracks; in LIVE it scrolls along with the current section. Tapping a cell opens that section.
- **LIVE** is the start view: the current section is selected and the graphs update while driving. Any section can be tapped and analysed **while driving** as well as after the session; the page stays there until LIVE is tapped, while recording, the top deltas and the strip keep updating.
- The right side has two tabs: **REVIEW** (start view) with the pending save offers (SAVE / SKIP, SAVE ALL, SKIP ALL, UNDO), because especially at the beginning many new bests come in; **GRAPHS** for the deep dive. Tapping an offer or a section opens GRAPHS. And the **end-of-run menu** (below).

## Sections

- Equal sections of **250 m along the track**, from the track length and the car's position on the lap (the game's normalised lap position), **not** the driven distance, so borders stay in the same place whatever line is driven. The last piece joins the previous section if it is shorter than 125 m.
- Section times are interpolated at the borders, so they do not depend on the sample rate.

## Repeating a section (practice)

In practice you may turn around and drive a section again. The rule:

- Entering section **N−1** (driving forward) means a repeat may follow; the new attempt replaces section **N** from the moment the car drives into N. A section's attempt is only ever replaced when it is entered **from the section before it**.
- So a spin at a border does not overwrite anything: spinning at the N / N+1 border and rolling back into N leaves N untouched (it was not entered from N−1); entering N+1 again only restarts the N+1 attempt.
- Driving backwards (lap position decreasing) is never recorded.
- All attempts are kept in the run's files (numbered); the page shows the latest as the red line.
- A faster repeat is offered in REVIEW like any best section; the lap it belongs to never counts as a lap.

## Recording

- **By time, 30 samples per second** while driving (live session, fresh data). Each sample: time since lap start, lap position, x / y position on the map, speed, throttle, brake, steering, gear, and the driving aids (TC / ABS / stability working, the set levels of TC, TC cut, ABS, stability, engine map). The lap position is stored with every sample so laps line up section by section.
- Samples are kept in memory and written when the lap ends (no disk writes while driving). About 165 KB per 1:30 lap.
- **Ambient data once per lap**: air and track temperature, grip, weather, time of day, fuel, tyre compound (what the game reports).
- **DiRT Rally 2.0**: one stage = one lap; sections along the stage.

## Baselines

- Kept per **game, track and car**: the best lap, and the best version of **every section** separately.
- **Automatic, ask first**: every new best section and every new best lap is offered on the page (SAVE / SKIP). Unanswered offers stay pending in a list and wait; nothing becomes a baseline without a tap. The end-of-run menu shows what is still open.
- **One backup** of the previous baseline is always kept, so a mis-tap can be undone.
- **Invalid laps** (the game's flag): never a best lap; their sections may still be offered (the game does not say where the cut was).

## Runs and files

- One **run** = one game session; it ends when the session, car or track changes, or the game closes.
- All laps of a run are kept. After the run, the end-of-run menu can delete the run's laps and keep only the baselines.
- Strict log form: **JSON Lines** (one JSON object per line); every file starts with a header line (format name and version, game, car, track, track length, section length, sample rate, lap, valid) followed by sample lines, one ambient line and a summary line (lap time, section times, valid).
- Planned layout (under a `data/` folder, ignored by git):
  - `data/runs/<game>/<track>/<car>/<date-time>/lap-007.jsonl` and `run.jsonl` (laps, offers, saves); open offers in `data/pending.jsonl`
  - `data/baselines/<game>/<track>/<car>/lap.jsonl`, `lap.prev.jsonl`, `sections/section-07.jsonl`, `section-07.prev.jsonl`

## Data the connectors must add

Universal fields: lap position (0..1), track length, x / y position, steering (−1..1), session identity (to detect a new run), ambient values. Assetto Corsa EVO: `npos`, `track_length_m`, the player's entry in `car_coordinates`, `steerAngle`, air / road temperature, grip, time of day, tyre compound (checked at Brands Hatch, [ACE/NOTES.md](ACE/NOTES.md)). DiRT Rally 2.0: lap distance / track length, position x / z from the packet (bytes 16 and 24), steering (byte 120).

## Performance

The bridge records at 30 Hz from the frame it already reads and writes only at lap end. The page fetches the samples of one section at a time (a 250 m section is a few seconds: about 100–200 samples per line), and in LIVE refreshes the current section a few times per second; the always-visible deltas come with the normal live stream.

## Next steps

1. PNG mockup of the page (map left, graphs right, deltas, offers, end-of-run menu) - done; feedback taken over above.
2. Build: recorder and files in the bridge, API, page; tests with the demo car - done.
3. Verify the new ACE / DR2 fields on the PC (lap position, position, steering, session id; whether the map is mirrored).
4. Later, if wanted: choose any lap of the run as the red line after the session (now: the last lap, blue the one before). The AI coach is defined in [TRAINER.md](TRAINER.md).
