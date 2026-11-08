# Handover – local session on the Windows PC

For the next Claude session running on the owner's Windows PC, with Assetto Corsa EVO (ACE) and DiRT Rally 2.0 (DR2) installed. Written at the end of the cloud session that built the **analysis page** (November 2026). Read this first, then [ANALYSIS.md](ANALYSIS.md) (what the owner wants from the analysis page), [README.md](../README.md) and [SPEC.md](SPEC.md) (how it all works).

**The job for this session: test the analysis page in the real games** and fix what the games deliver differently from what the code assumes. Everything else already works in ACE.

## Start

```
git pull
python -m unittest discover tests
python core\server.py --check
python core\server.py
```

The tests must pass (39 tests) and `--check` must print `Result OK` before anything else. The bridge prints the address for the iPad. Log: `logs\racing-dashboard.log`.

## Where things stand

| Part | Where | State |
| --- | --- | --- |
| Bridge: web server, live stream, keypresses, game switch, data checks | `core/server.py` and friends | works on the PC (first test, November 2026) |
| ACE connector (shared memory) | `games/ace/connector.py` | **reading works in the game**: gear, rpm, shift lights, dash box values (seen with BMW M4 CSL and Mazda RX-7). Lights / wipers are not published by ACE 0.9.1 ([ACE/NOTES.md](ACE/NOTES.md)) |
| ACE keys | `games/ace/game.toml`, [ACE/KEYS.md](ACE/KEYS.md) | the owner bound them; keys reach the game (window `AssettoCorsaEVO.exe` verified) |
| GEAR + REV (phone), DASH (iPad), BUTTONS | `ui/` | in use; the owner said it works very well |
| DR2 connector (UDP) | `games/dr2/connector.py` | only tested with simulated packets |
| Demo game | `games/demo/` | works; a 4.9 km track with laps that differ a little, so the analysis page has something to show |
| **Analysis page** (iPad, landscape) | `core/recorder.py`, `ui/analysis.html`, `ui/js/analysis.js`, `ui/styles/analysis/standard.css` | **new, never run against a game.** Tested with the demo car in Chromium and with simulated laps in `tests/test_recorder.py` |
| New telemetry fields for the analysis | `lap_pos`, `track_length_m`, `pos_x`, `pos_y`, `steer`, `session_id`, `air_c`, `road_c`, `tyre_compound`, `time_of_day` in all three connectors | **ACE and DR2 values are guesses from the documentation**; this is what must be checked first |
| Installer | `install.bat`, `tools/install.ps1` | ask the owner whether it was ever run |

## Test plan for the analysis page

Do it in this order, one step at a time, and tell the owner what you see after each step.

### 1. Demo first (separates page problems from game problems)

Settings (gear button) → GAME → DEMO. Open `http://localhost:8080/analysis` on the PC and `http://<PC address>:8080/analysis` on the iPad. After the first lap (about 1:30) the map, the section strip and the graphs fill; TO REVIEW counts the offers. If the demo works but a game does not, the problem is in that game's connector.

### 2. ACE: the raw values

GAME → ASSETTO CORSA EVO, drive a practice session, and in a second window run:

```
py tools\ace_probe.py --analysis
```

It prints the analysis values five times per second, and below them every occupied car slot (`[index] x,z id ...`), with `*` on the slot the connector uses as the player. Check:

| Value | Expected | If not |
| --- | --- | --- |
| `status` | `live` while driving | the recorder only records `live`; check the `STATUS` mapping in the connector |
| `lap_pos` | grows from 0 to 1 and **wraps to 0 at the start / finish line** | the lap only ends when the value jumps from above 0.9 to below 0.1 (`_sample` in `recorder.py`). If ACE's `npos` starts somewhere else, laps end at the wrong place |
| `track_length_m` | the track length in metres (compare with the track's published length) | 0 or missing = **nothing is recorded** (needs at least 300 m). Then find the length elsewhere in `Static` or work it out |
| `pos_x`, `pos_y` | change smoothly in metres while driving; the `*` slot is the one that moves with your car | wrong slot = the map shows another car. Fix `player_xy()` in `games/ace/connector.py` (it matches `car_ids` against `player_car_id_a/b`, else slot 0) |
| `steer` | about −1 full left … +1 full right | if it is in degrees or radians, scale it in `parse()` (it is clamped to −1..1, so wrong units show as a flat line at ±1) |
| `session_id` | **stays the same** while driving; changes with a new session | if it changes while driving, every change ends the run: the log fills with `analysis | run` lines. Then build it from fewer fields (`parse()`, `session_id`) |
| `lap_valid` | false after cutting the track | a lap that is not valid is never offered as best lap |

### 3. ACE: the page

Drive three laps, then look at the iPad:

- **Map:** is it the track as in the game, or mirrored / rotated? The map draws `pos_x` to the right and `pos_y` (the game's z) downwards. If it is mirrored, negate `pos_y` (or `pos_x`) in `parse()` of the connector and say so in [ACE/NOTES.md](ACE/NOTES.md).
- **Car dot** follows the car; the red line grows behind it.
- **Lap time:** after a lap, the strip and `data\runs\ace\...\lap-00N.jsonl` (last line, `summary`, `time`) against the game's lap time. Expect a difference of a few hundredths at most (the recorder interpolates at the line at 30 Hz).
- **Sections:** tap a section on the map and in the strip; the graphs show green (best), blue (last), red (now). LIVE returns to following the car.
- **Offers:** TO REVIEW → SAVE one, SKIP one, UNDO; files appear in `data\baselines\ace\<track>\<car>\` (`lap.jsonl`, `sections\section-NN.jsonl`, and `*.prev.jsonl` after a second save).
- **Pause** (Esc) during a lap: that lap must not count (no best lap offered for it).
- **END RUN** (tap twice): the end-of-run menu with KEEP ALL LAPS / KEEP BASELINES ONLY.
- **Practice repeat** (the owner asked for it): turn around, drive back into the previous section, then forward again: the strip shows ↻ on the repeated section, the lap no longer counts, a faster repeat is offered as a section best.

### 4. DR2

Enable UDP ([DR2/NOTES.md](DR2/NOTES.md)), GAME → DIRT RALLY 2.0, drive a stage. One stage = one lap: the time starts when the car moves off and ends when the car stops after the finish (`lap_pos` must reach 0.9995: check `/state` at the finish). The run is named after the stage length (`session_id` `stage-<length>`); car and track names are not in DR2's packet, so baselines go to `data\baselines\dr2\unknown\unknown\` – sort by stage length if the owner wants it better. Check the map orientation and steering sign as for ACE.

## How the analysis works (where to look)

- **Recorder** `core/recorder.py`, fed every frame by the reader thread in `core/server.py` (an exception is logged as `analysis | error` and never stops the bridge). Constants at the top: `BACKWARD_BREAK_M` (100 m back = lap does not count), `RESTART_M`, `MIN_TRACK_M`, `STAGE_END_POS`, `STANDING_KMH`. `_sample()` holds the line crossing, restart, stage end and the repeat rule; `_enter()` decides whether a section attempt starts (only forward from the section before).
- **Config** `[analysis]` in `config/config.toml`: `enabled`, `data_dir` (`data`), `hz` (30), `section_m` (250).
- **API for debugging** (open in the PC browser): `/api/analysis` (state, outline, offers), `/api/analysis/live` (deltas, strip, current section), `/api/analysis/section?n=3` (the three lines of section 4). Full list in [SPEC.md](SPEC.md#5-requests).
- **Files** (JSON Lines, header line first): `data\runs\<game>\<track>\<car>\<date_time>\lap-007.jsonl` and `run.jsonl`; `data\baselines\<game>\<track>\<car>\`; open offers in `data\pending.jsonl`. `data\` is ignored by git. Formats in [SPEC.md](SPEC.md#analysis).
- **Page** `ui/js/analysis.js`: polls `/live` 4 × per second, the selected section 2 × per second, draws map and graphs on canvas; the car dot comes from the normal stream.

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; there is no lap picker yet.
- UNDO restores the previous baseline but does not bring the offer back into TO REVIEW.
- KEEP BASELINES ONLY deletes the lap files; offers still open then live only in memory until the bridge restarts.
- A lap started standing on a circuit (race start) counts as a normal lap.
- Baselines are kept per game / track / car folder. If a game reports a slightly different track length in another session, the section count can change and old section baselines no longer line up (not seen yet).

## Debugging tools

- Log `logs\racing-dashboard.log`: `analysis | run` (a run starts: track length and section count), `analysis | run end`, `analysis | baseline` (saved / undo), `analysis | error`; `data | error` for bad frames; `ace | shared memory` (game and layout version); `ace | raw` (light / wiper raw values).
- `http://localhost:8080/state`: the current frame with all fields, including the analysis ones.
- `py tools\ace_probe.py` (dash values) and `py tools\ace_probe.py --analysis` (analysis values and car slots).
- Force a game: settings → GAME, or `config\settings.json` `{"game": "ace"}`.
- Key overrides: `[games.<id>.keys]` in `config\config.toml` (local, not committed).

## Decisions the owner made (keep them)

- Universal UI, one folder per game (`games/<id>/connector.py`, `game.toml`, `dash.toml`); UI in `ui/` (plain HTML / CSS / JS); Python standard library only; commit directly to `main`.
- GEAR + REV: yellow 14-segment digit in a light grey frame close to the screen edges, GEAR in the top line, as large as possible; 8 rev lights blue-green-yellow-red-red-yellow-green-blue filling from the outside in, flashing at the shift point, unlit fields dim; no rpm / speed numbers; E for errors with a chip; P D S B L M letters (S like a 5); gears above 9 show E; ACE auto-shift shows the gear number. **No** dimmed gear with the engine off, **no** flashing gear in the pit lane.
- DASH (iPad): cards, the same layout for every car of a game; greyed cards for what a car lacks; values read back from the game; a card lights up after a tap and when the value changes in the game; TC / ABS / ESC amber while active; warning lamps as colours only; no hints on the cards. ACE: IGNITION held, WIPERS as a latch, LIGHTS / WIPERS without state, diff locking in % for cars without diff steps, fixed settings shown as FIXED, no LAUNCH and no AUTO CLUTCH card. Landscape starts 26 px lower.
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)): one page, no tabs, no coaching or tips; map left, six graphs right (speed, throttle, brake, steering, gear, delta); green best, blue last, red now; deltas for lap and section vs best ever and vs last always visible; section strip with slider; no braking markers; LIVE start view and tapping sections while driving; sections of 250 m by track position (not driven distance), last piece under 125 m joins the previous one; recording by time at 30 Hz, written at lap end; JSON Lines with a header line; baselines per game / track / car for the lap and every section; every new best is **offered, never saved without a tap**; one backup per baseline for UNDO; invalid laps: sections may be offered, the lap never; a run is a game session, all its laps kept, the end-of-run menu can keep baselines only; the repeat rule (entering N−1 then N replaces N; a spin at a border replaces nothing; backwards never recorded; all attempts kept, the latest shown).

## Working with the owner

- The owner writes short messages (sometimes with typos); reply short and plain, in English.
- For visual changes: **show PNG mockups first** (HTML rendered with a headless browser), ask for feedback, then build. For bigger features the owner likes a short interview first.
- Keep README, SPEC, the game notes and tests in step with every change; no personal data in commits; no emoji in the UI.
- Ideas not built yet: lap picker after the session, AI coach (maybe later), tyre / brake temperature / damage cards, two-page dash box, names for light / wiper stages, flags, more games ([ASSISTS.md](ASSISTS.md)).
