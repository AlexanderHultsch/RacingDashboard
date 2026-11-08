# Analysis page – agreed strategy

The analysis page as agreed with the owner (interview, November 2026). Not built yet; this is the plan the build follows. No coaching and no tips: the page only shows data (an AI coach may come later).

## The page (one page, no tabs; iPad landscape)

- **Left: the circuit map** with the track cut into sections. Overview of the whole track; tapping a section zooms into it, tapping again returns to the overview.
- **Race lines** drawn on the map in high quality: **green** = the best (baseline) section, **blue** = the last lap, **red** = the current lap.
- **Right: graphs for the selected section**, each with the same three lines (green best, blue last, red current), over the position in the section: speed, throttle, brake, steering, gear (throttle / brake and steering / gear as separate small graphs, so the colours keep meaning best / last / current), and the time delta building up inside the section.
- **Always visible:** delta per section against best ever and against last lap, and delta per lap against best ever and against last lap.
- **LIVE** is the start view: the current section is selected and the graphs update while driving. Tapping any section leaves LIVE (after the session every section can be looked at); the LIVE button returns.
- A small list of **pending save offers** ("4 to review") and the **end-of-run menu** (below).

## Sections

- Equal sections of **250 m along the track**, from the track length and the car's position on the lap (the game's normalised lap position), **not** the driven distance, so borders stay in the same place whatever line is driven. The last piece joins the previous section if it is shorter than 125 m.
- Section times are interpolated at the borders, so they do not depend on the sample rate.

## Recording

- **By time, 30 samples per second** while driving (live session, fresh data). Each sample: time since lap start, lap position, x / y position on the map, speed, throttle, brake, steering, gear. The lap position is stored with every sample so laps line up section by section.
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
  - `data/runs/<game>/<track>/<car>/<date-time>/lap-007.jsonl` and the run's pending offers
  - `data/baselines/<game>/<track>/<car>/lap.jsonl`, `lap.prev.jsonl`, `sections/section-07.jsonl`, `section-07.prev.jsonl`

## Data the connectors must add

Universal fields: lap position (0..1), track length, x / y position, steering (−1..1), session identity (to detect a new run), ambient values. Assetto Corsa EVO: `npos`, `track_length_m`, the player's entry in `car_coordinates`, `steerAngle`, air / road temperature, grip, time of day, tyre compound; to verify on the PC first (`tools/ace_probe.py`). DiRT Rally 2.0: lap distance / track length, position x / z from the packet (bytes 16 and 24), steering (byte 120).

## Performance

The bridge records at 30 Hz from the frame it already reads and writes only at lap end. The page fetches the samples of one section at a time (a 250 m section is a few seconds: about 100–200 samples per line), and in LIVE refreshes the current section a few times per second; the always-visible deltas come with the normal live stream.

## Next steps

1. PNG mockup of the page (map left, graphs right, deltas, offers, end-of-run menu), feedback.
2. Verify the new ACE / DR2 fields on the PC.
3. Build: recorder and files in the bridge, API, page; tests with the demo car.
