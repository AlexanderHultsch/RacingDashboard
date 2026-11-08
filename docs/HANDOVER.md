# Handover – local session on the Windows PC

For the next Claude session running on the owner's Windows PC, with Assetto Corsa EVO (ACE) and DiRT Rally 2.0 (DR2) installed. Written at the end of the cloud session that built the **analysis page** and fixed it after the owner's first drive with it (November 2026). Read this first, then [ANALYSIS.md](ANALYSIS.md) (what the owner wants from the analysis page), [README.md](../README.md) and [SPEC.md](SPEC.md) (how it all works).

**The job for this session:** check the analysis page and **the data it records** with the real games, and fix what the games deliver differently from what the code assumes. Everything else already works in ACE.

## Start

```
git pull
python -m unittest discover tests
python core\server.py --check
python core\server.py
```

The tests must pass (42 tests) and `--check` must print `Result OK`. The bridge prints the address for the iPad. Log: `logs\racing-dashboard.log`. The repository moved to `github.com/AlexanderHultsch/RacingDashboard` (the old name redirects); if `git pull` complains, ask the owner before changing the remote.

## Where things stand

| Part | Where | State |
| --- | --- | --- |
| Bridge, GEAR + REV (phone), DASH (iPad), BUTTONS | `core/`, `ui/` | in use in ACE; the owner said it works very well |
| ACE connector (shared memory) | `games/ace/connector.py` | dash values verified in the game (BMW M4 CSL, Mazda RX-7, Toyota GR86). Lights / wipers are not published by ACE 0.9.1 ([ACE/NOTES.md](ACE/NOTES.md)) |
| ACE keys | `games/ace/game.toml`, [ACE/KEYS.md](ACE/KEYS.md) | bound by the owner, keys reach the game |
| DR2 connector (UDP) | `games/dr2/connector.py` | only tested with simulated packets |
| Demo game | `games/demo/` | a 4.9 km track whose laps differ a little; use it to tell page problems from game problems |
| **Analysis page** (iPad, landscape) | `core/recorder.py`, `ui/analysis.html`, `ui/js/analysis.js`, `ui/styles/analysis/standard.css` | **first drive in ACE** (Toyota GR86, Brands Hatch, 6 laps): the map with the track and 16 sections was drawn, laps and section times were recorded, section bests saved. See below for what was fixed after it and what is still open |
| Analysis fields in the connectors | `lap_pos`, `track_length_m`, `pos_x`, `pos_y`, `steer`, `session_id`, ambient values | ACE, checked with the recorded laps (Brands Hatch, GR86): lap position, track length and position work (driven distance 99 % of the track length), 29 Hz on clean laps, section times add up to the lap time, steering about ±0.95, `lap_valid` true on the clean laps and false on the laps with a pause or a return to the pits, `session_id` (`0-0-0-Practice`) stable within the session; lap times match the game's (`game_time`) within 0.006 s; the first lap after leaving the pits is invalid in ACE too (correct). **Not checked yet:** map mirrored or not, a lap with a pause (should count now), `session_id` across sessions. DR2: never seen |
| **AI trainer** | `core/trainer.py`, button and TRAINER tab in `ui/js/analysis.js`, settings in `ui/js/rd.js`, [TRAINER.md](TRAINER.md) | built and tested with a simulated AI; **not yet with a real answer**: set a provider and key in the settings, TEST, then ask on the analysis page and check `logs\racing-dashboard.log` (`trainer | ...`) and `data\trainer.jsonl` |
| Tools | `tools/ace_probe.py --analysis`, **`tools/analysis_check.py`** (new) | see the plan |
| Installer | `install.bat`, `tools/install.ps1` | ask the owner whether it was ever run |

### What the owner saw on the first drive, and what was done

| Owner's finding | Cause | Now |
| --- | --- | --- |
| Section strip and the four deltas at the top empty | they compared against the lap just started (lap 6, which had reached no section yet) | sections the new lap has not reached show the last lap's values (dimmed); between laps the page shows the last complete lap (while paused it keeps the lap in progress, owner's wish, November 2026); the delta to the last lap no longer needs a valid last lap |
| "NOT RECORDING" without a reason | the game sent no error; the recorder stopped for its own reason (most likely the game was paused) | the header says why (GAME PAUSED, REPLAY, NOT ON TRACK, no lap position, track length unknown, STAGE FINISHED) and shows the last lap time with OUT LAP / INVALID / INTERRUPTED / REPEATED |
| Graph titles covered by the lines on the iPad | the plot started at the panel top | titles in their own band |
| Page too close to the top edge (the iPad fades there) | | 26 px lower in landscape, as DASH |
| "Store the analysis even when I am in another tab" | the recording runs in the bridge on the PC, whatever page or tab the iPad shows; the page only *looked* empty (first finding) | no change needed; confirm it with the owner on the next drive |
| Wanted: REVIEW and GRAPHS tabs, REVIEW as start view (many new bests at the beginning), SKIP ALL | | built: REVIEW (SAVE / SKIP, SAVE ALL, SKIP ALL with a second tap, UNDO; tap an offer to see its section), GRAPHS for the deep dive |

**Still open from the screenshot:** no green best-lap line on the map. The recorded data says the best lap *was* offered and saved (lap 4 at 21:51, lap 5 2:05.759 at 21:53, `run.jsonl`), so if the line is still missing with a saved best lap, the problem is in the page, not the data. The header now shows why the last lap did not count; if it says INVALID on clean laps, ACE's `is_valid_lap` is wrong or inverted (check it, see the table below). If it says INTERRUPTED, the recorder saw a pause or a jump (check `status` and the gaps in step 2).

## Test plan

Do it in this order, one step at a time, and tell the owner what you see after each step.

### 1. Demo first

Settings (gear button) → GAME → DEMO. Open `http://localhost:8080/analysis` on the PC and on the iPad. After the first lap (about 1:30) the map, the strip and the REVIEW tab fill. If the demo works but a game does not, the problem is in that game's connector.

### 2. Check the real data already recorded (and after every drive)

The owner's drives are on the PC in `data\` (ignored by git): `data\runs\ace\<track>\<car>\<date_time>\lap-NNN.jsonl` plus `run.jsonl`, the baselines in `data\baselines\...`, open offers in `data\pending.jsonl`. Run:

```
python tools\analysis_check.py
python tools\analysis_check.py --last 1
python tools\analysis_check.py --game ace
```

Per run it prints the session id, the track length, the section count and the log (laps, offers, saves, skips); per lap the time, whether it counts (and why not), the sample rate, gaps, the lap position range, steering and map ranges, the distance driven on the map against the track length, the sum of the section times against the lap time and the ambient values. Problems are marked `!!`. What to look for:

- **Many runs for one session** (a new folder every few seconds or laps): `session_id` changes while driving → simplify it in `parse()` of `games/ace/connector.py`.
- **Laps that do not count:** `invalid` on clean laps → `is_valid_lap` (the check prints where the game invalidated the lap, `invalid_at`); `broken` (interrupted) → a jump (back to the pits, a reset) or turning around, no longer a pause; `out_lap` only for the first lap.
- **Sample rate** well below 30 Hz or long gaps → the frames had errors (`data | error` in the log) or `status` was not `live`.
- **Lap time** against the game's lap time: the summary line stores the game's own time as `game_time` and `analysis_check.py` prints the difference (`!!` above 0.05 s on a lap that counts); a few hundredths at most.
- **Section times** add up to the lap time.
- **Steering** stuck at ±1 → wrong unit (degrees / radians), scale it in `parse()`; near 0 all the time → wrong field.
- **Driven distance / track length** far from 1 → `track_length_m` or the position scale is wrong.
- **Ambient** values plausible (air / road temperature, tyre compound, time of day).

Open one lap file as well and read a few lines: the header, some samples, the `section`, `ambient` and `summary` lines (formats in [SPEC.md](SPEC.md#analysis)).

### 3. ACE: the live values

GAME → ASSETTO CORSA EVO, drive, and in a second window run:

```
py tools\ace_probe.py --analysis
```

It prints the analysis values five times per second, and every occupied car slot (`[index] x,z id ...`) with `*` on the slot the connector uses as the player.

| Value | Expected | If not |
| --- | --- | --- |
| `status` | `live` while driving | the recorder only records `live`; check the `STATUS` mapping |
| `lap_pos` | grows from 0 to 1 and wraps to 0 at the start / finish line | laps end where it jumps from above 0.9 to below 0.1 (`_sample` in `recorder.py`) |
| `track_length_m` | the track length in metres (Brands Hatch GP about 3.9 km: the 16 sections fit) | |
| `pos_x`, `pos_y` | change smoothly; the `*` slot moves with your car | in a session with AI cars check that `*` is still your car; else fix `player_xy()` |
| `steer` | about −1 full left … +1 full right | scale in `parse()` |
| `session_id` | the same while driving; changes with a new session | build it from fewer fields |
| `lap_valid` | true on a clean lap, false after cutting | if always false (or inverted), every lap is INVALID and never a best lap: fix the mapping |

### 4. ACE: the page

Drive three clean laps, then on the iPad:

- **Map:** compare with the track map in the game. The page draws `pos_x` to the right and `pos_y` (the game's z) downwards. Mirrored → negate `pos_y` (or `pos_x`) in `parse()` and note it in [ACE/NOTES.md](ACE/NOTES.md).
- **Car dot** follows the car, the red line grows behind it; strip and the four deltas fill while driving.
- **REVIEW** (start view on the right): a best lap is offered after a clean lap; SAVE one, SKIP one, UNDO, SKIP ALL (tap twice). A saved best lap shows as the green line on the map. Files in `data\baselines\ace\<track>\<car>\`.
- **GRAPHS:** tap a section on the map, in the strip or in REVIEW; green best, blue last, red now; LIVE follows the car again.
- **Pause** (Esc) during a lap: the header says GAME PAUSED; the lap time stops (the recorder's clock stands still while paused) and the lap counts normally (owner's decision, November 2026). Compare `game_time` with `time` in `analysis_check.py`.
- **Another tab** (switch the iPad to DASH, drive, come back): the laps driven meanwhile are there.
- **END RUN** (tap twice): the end-of-run menu (KEEP ALL LAPS / KEEP BASELINES ONLY).
- **Practice repeat:** turn around into the previous section, then forward again: ↻ on that section in the strip, the lap does not count, a faster repeat is offered as a section best.

Then run `python tools\analysis_check.py --last 1` again.

### 5. DR2

Enable UDP ([DR2/NOTES.md](DR2/NOTES.md)), GAME → DIRT RALLY 2.0, drive a stage. One stage = one lap: timed from the moment the car moves to when it stops after the finish (`lap_pos` must reach 0.9995: check `/state` at the finish; the header says STAGE FINISHED). The run is named `stage-<length>`; DR2 sends no car or track name, so baselines go to `data\baselines\dr2\unknown\unknown\` – ask the owner whether to sort them by stage length. Check map orientation, steering and the data with `analysis_check.py`.

## How the analysis works (where to look)

- **Recorder** `core/recorder.py`, fed every frame by the reader thread in `core/server.py` (an exception is logged as `analysis | error` and never stops the bridge). Constants at the top (`BACKWARD_BREAK_M`, `RESTART_M`, `MIN_TRACK_M`, `STAGE_END_POS`, `STANDING_KMH`). `_why_not()` says why a frame is not recorded; `_sample()` holds the line crossing, restart, stage end and repeat rule; `_enter()` decides whether a section attempt starts; `_shown()` picks the red / blue laps; `_strip()` and `_deltas()` feed the page.
- **Config** `[analysis]` in `config\config.toml`: `enabled`, `data_dir`, `hz` (30), `section_m` (250).
- **API** (PC browser): `/api/analysis`, `/api/analysis/live` (deltas, strip, `why`, `last_lap`), `/api/analysis/section?n=3`. Full list in [SPEC.md](SPEC.md#5-requests).
- **Page** `ui/js/analysis.js`: polls `/live` 4 × per second, the selected section 2 × per second; map and graphs on canvas; the car dot from the normal stream; REVIEW / GRAPHS tabs (`setTab`).

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; no lap picker yet.
- UNDO restores the previous baseline but does not bring the offer back into REVIEW.
- KEEP BASELINES ONLY deletes the lap files; offers still open then live only in memory until the bridge restarts.
- A lap started standing on a circuit (race start) counts as a normal lap.
- If a game reports a different track length in another session, the section count can change and old section baselines no longer line up (not seen yet).

## Debugging tools

- Log `logs\racing-dashboard.log`: `analysis | run` (a run starts: length, sections), `analysis | run end`, `analysis | baseline`, `analysis | error`; `data | error` for bad frames; `ace | shared memory`, `ace | raw`.
- `http://localhost:8080/state`: the current frame with all fields.
- `py tools\ace_probe.py [--analysis]`, `python tools\analysis_check.py [--last N] [--game ID]`.
- Force a game: settings → GAME, or `config\settings.json` `{"game": "ace"}`. Key overrides: `[games.<id>.keys]` in `config\config.toml`.

## Decisions the owner made (keep them)

- Universal UI, one folder per game (`games/<id>/connector.py`, `game.toml`, `dash.toml`); UI in `ui/` (plain HTML / CSS / JS); Python standard library only.
- GEAR + REV: yellow 14-segment digit in a light grey frame close to the screen edges, GEAR in the top line, as large as possible; 8 rev lights blue-green-yellow-red-red-yellow-green-blue filling from the outside in, flashing at the shift point, unlit fields dim; no rpm / speed numbers; E for errors with a chip; always the gear number, also with an automatic gearbox or ACE auto-shift (no D / S letters and no setting for it since November 2026; P only for park); gears above 9 show E. **No** dimmed gear with the engine off, **no** flashing gear in the pit lane.
- Settings button: same size and place on every page, top right. Settings overlay: 16 px padding plus the landscape top gap. Home page `/Racing_Dashboard` (the link saved on the iPad; flight simulator dashboards share the address and port).
- DASH (iPad): cards, the same layout for every car of a game; greyed cards for what a car lacks; values read back from the game; a card lights up after a tap and when the value changes in the game; TC / ABS / ESC amber while active; warning lamps as colours only; no hints. ACE: IGNITION held, WIPERS as a latch, LIGHTS / WIPERS without state, diff locking in % for cars without diff steps, FIXED settings, no LAUNCH, no AUTO CLUTCH. Landscape starts 26 px lower.
- AI TRAINER ([TRAINER.md](TRAINER.md), agreed and built November 2026): button bottom right on the map (WHOLE TRACK in the overview, SECTION n when zoomed), answer in a third tab TRAINER, only on a tap; Claude / ChatGPT / Gemini / Ollama with the owner's key kept on the PC; FAST / BEST per provider; facts computed by the bridge, fixed prompt, JSON answer with up to 3 tips (summary 25 words, tip 35 words); English; last 5 answers in one rolling file; greyed out without a working connection.
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)): one page, tips only from the AI trainer; map left; right side two tabs, **REVIEW first** (offers, SAVE / SKIP, SAVE ALL, SKIP ALL, UNDO) and GRAPHS (4 per page, scrolled: speed, throttle, brake, delta / steering, gear, TC, ABS / stability, engine map; aids as lanes: working + set level); green best, blue last, red now; lap and section deltas vs best ever and vs last always visible; section strip with slider; no braking markers; LIVE start view and tapping sections while driving; 250 m sections by track position (last piece under 125 m joins the previous one); recording by time at 30 Hz, written at lap end; JSON Lines with a header line; baselines per game / track / car for the lap and every section; every new best **offered, never saved without a tap**; one backup per baseline for UNDO; invalid laps: sections may be offered, the lap never; a pause stops the lap time and the lap counts normally; a run is a game session, all its laps kept, end-of-run menu can keep baselines only; the repeat rule (entering N−1 then N replaces N; a spin at a border replaces nothing; backwards never recorded; all attempts kept, the latest shown). Landscape starts 26 px lower.

## Working with the owner

- The owner writes short messages (sometimes with typos); reply short and plain, in English.
- Branches: commit to `main`; the only other branch is one work-in-progress branch for a prototype the owner has not approved yet, merged into `main` once approved. No branch per feature.
- For visual changes: **show PNG mockups first** (HTML rendered with a headless browser), ask for feedback, then build. For bigger features the owner likes a short interview first.
- Keep README, SPEC, the game notes and tests in step with every change; no personal data in commits; no emoji in the UI.
- Ideas not built yet: lap picker after the session, the AI trainer (defined), tyre / brake temperature / damage cards, two-page dash box, names for light / wiper stages, flags, more games ([ASSISTS.md](ASSISTS.md)).
