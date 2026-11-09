# Handover – local session on the Windows PC

For the next Claude session **on the owner's Windows PC**, with Assetto Corsa EVO (ACE), Assetto Corsa Rally (ACR), iRacing and DiRT Rally 2.0 (DR2) installed and the iPad / iPhone at hand. Written at the end of the cloud session of 9 November 2026. Read this first, then [README.md](../README.md), [SPEC.md](SPEC.md), [ANALYSIS.md](ANALYSIS.md), [TRAINER.md](TRAINER.md) and the notes of the game you test ([ACE](ACE/NOTES.md), [ACR](ACR/NOTES.md), [IRACING](IRACING/NOTES.md), [DR2](DR2/NOTES.md)).

**The job for this session:** the first real drive with everything the cloud session built: the **AI trainer's new facts and prompt** (with ACE), and the **new games** Assetto Corsa Rally and iRacing (and DR2, never driven yet). Fix what the games deliver differently from what the code assumes.

## Start

```
git pull
python -m unittest discover tests
python core\server.py --check
python core\server.py
```

All tests must pass (74 on 9 November 2026) and `--check` must list five games (ace, acr, demo, dr2, iracing) and print `Result OK`. **Restart the bridge after every change** and ask the owner to reload the page on the iPad. Log: `logs\racing-dashboard.log`. The owner's laps (`data\`), AI settings with the API key (`config\trainer.json`) and mockups (`mockups\`) are local and not in git.

The repository is `github.com/AlexanderHultsch/RacingDashboard` (renamed from Racing-Dashboard; the old name redirects). If `git pull` complains, ask the owner before changing the remote.

## What the cloud session did (9 November 2026, newest first)

| Commit | What |
| --- | --- |
| `91bcb56` | **Assetto Corsa Rally** (`games/acr`) and **iRacing** (`games/iracing`): connectors, keys, dash boxes; every page works for them, analysis and AI trainer included. `core/kunos.py` (the physics page ACE and ACR share), `winmem.read_at` / `winmem.process_running`; a push card whose action is `hold` is held while touched (iRacing STARTER) |
| `346a6b0` | DR2: the packet has no names, so the stage is named by its length (`Stage 10.01 km`) and the car by gears / redline / idle (`5-speed, 7500 rpm, idle 900`); laps and bests no longer all land in `dr2/unknown/unknown` |
| `277926d` | AI trainer prompt rewritten: fundamentals first, every tip linked to the numbers, **up to 9 tips** (was 3), title starts with the category (BRAKING, RELEASE, APEX, THROTTLE, LINE, GEAR, AIDS, TIME); whole track sends the full facts of the 4 worst sections (was 3) |
| `f09e649` | AI trainer facts: each section's shape from the recorded track (`corner`: type, turn, apex, radius), `next_section`, `lap_m`, a 10 m `trace` (speed, pedals, steering, line offset against BEST, inside / outside), **rpm recorded per sample** (`rpm_at_min`, `shifts`) |
| `3ae79df` | Code review for the public release: dead code out (`launch`, `auto_clutch`, `flag` fields, the demo's D / S modes, unused API fields), docs current. Open owner decision: a **LICENSE** file (none yet) |

Before that, the local session of 8–9 November (analysis cursor, aid lanes, AI trainer, pause handling, ...): see `git log` and the earlier entries in [TRAINER.md](TRAINER.md) and [ANALYSIS.md](ANALYSIS.md).

## Where things stand

| Part | Where | State |
| --- | --- | --- |
| Bridge, GEAR + REV, DASH, BUTTONS, home `/Racing_Dashboard` | `core/`, `ui/` | in daily use with ACE |
| ACE | `games/ace/`, [ACE/NOTES.md](ACE/NOTES.md), [ACE/KEYS.md](ACE/KEYS.md) | verified in the game (dash values, analysis at Brands Hatch); lights / wipers not published by ACE 0.9.1 |
| Analysis page | `core/recorder.py`, `ui/js/analysis.js` | verified with ACE (lap times within 0.006 s of the game's) |
| AI trainer | `core/trainer.py`, [TRAINER.md](TRAINER.md) | works with Claude; **the new facts and prompt have never produced a real answer** |
| **Assetto Corsa Rally** | `games/acr/`, [ACR/NOTES.md](ACR/NOTES.md) | **never run against the game.** Built from other tools' notes: ACR publishes the **ACC** layout under `Local\acpmf_*` (not ACE's), only partly filled; the connector attaches only while `acr.exe` runs (AC1 / ACC use the same names). Keys are proposals (no documented defaults) |
| **iRacing** | `games/iracing/`, [IRACING/NOTES.md](IRACING/NOTES.md) | **never run against the sim.** Built from iRacing's SDK headers; the map position is dead-reckoned (no live X / Y in iRacing), reset at the line each lap. Keys: iRacing defaults (S, I, A, = / −) plus proposals |
| DR2 | `games/dr2/`, [DR2/NOTES.md](DR2/NOTES.md) | **never run against the game** (simulated packets only); needs UDP switched on once in the game's XML |
| Tools | `tools\ace_probe.py [--analysis]`, `tools\analysis_check.py [--last N] [--game ID]` | `analysis_check` works for every game |
| Installer | `install.bat`, `tools\install.ps1` | ask the owner whether it was ever run |

## Test plan (ask the owner which game first)

### 1. AI trainer with ACE (the owner's first interest)

Drive three clean laps at a known track, save the bests, then ask AI TRAINER for the whole track and for one or two sections (FAST, then BEST once).

- Do the tips use the fundamentals with numbers (braking point, brake release against the apex, coasting, apex placement, throttle pickup, line, gear / rpm)? Is the category at the start of each title? Are 9 tips too many for FAST (padding)?
- Read the facts that were sent: the last lines of `data\trainer.jsonl` (`data` field). Check the **corner types** against the real corners (Brands Hatch: Paddock Hill fast, Druids slow / hairpin, Graham Hill medium) and the **line offset** (`off` in `trace`: positive = inside of the corner).
- Change the prompt only after reading the facts that went with an answer. Prompt, schema and facts are in `core/trainer.py`; keep [TRAINER.md](TRAINER.md) in step (the prompt block there is regenerated from the code).
- Laps saved before 9 November have no rpm: `rpm_at_min` is missing for those bests until new ones are saved.
- If the API credits are used up the trainer shows a generic AI ERROR (credits: the owner's Max plan includes monthly API credits once the Console organization is linked in claude.ai → Settings → Billing; the owner was told this, see the chat). Offering a clearer "no API credits left" message was proposed, not built.

### 2. Assetto Corsa Rally

1. GAME → ASSETTO CORSA RALLY, start a stage. Log: `acr | shared memory | attached to Local\acpmf_* (acr.exe runs)`. Not attached → check the process name in Task Manager (`acr.exe` expected, `PROCESSES` in the connector).
2. `http://localhost:8080/state` while driving: gear, rpm, speed, pedals, `steer`, `brake_bias`, `tc_level` / `abs_level`, `lap_ms` (from the clock text), `lap_pos` / `track_length_m`, `pos_x` / `pos_y`, car and stage name. Pause the game: `status` should become `pause` (blank physics page; the sources disagree whether ACR blanks or freezes it — frozen data shows NO DATA after 2 s, which is fine too).
3. Bind the proposed keys ([ACR/NOTES.md](ACR/NOTES.md)) and try each DASH card; RECOVER needs "Manual Respawn" in the session settings.
4. **Stage start and end on the analysis page** — the biggest open question: the distance along the stage may not line up with the start / finish lines, so the stage-end rule (`lap_pos` ≥ 0.9995 for 1 s, `STAGE_END_POS` in `core/recorder.py`) may not fire. After one full stage run `python tools\analysis_check.py --last 1`: one complete lap with a time close to the game's stage time is the goal.
5. The map: compare with the stage map in the game (mirrored?).

### 3. iRacing

1. GAME → IRACING, get in the car (test drive). Log: `iracing | shared memory | irsdk header version 2`. In the garage the pages show NOT ON TRACK (that is right: `IsOnTrack` false).
2. `/state`: gear, rpm, `rpm_max` (redline from the session info), `shift_up` at the car's shift light, `speed_kmh`, `clutch` (0 with the pedal up), `steer` (−1 left … +1 right?), `tc_level` / `abs_level` / `brake_bias` / `engine_map` on two or three cars (GT3, a road car), `fuel_l`, `lap_pos`, `track_length_m`, `car`, `track`.
3. `brake_bias`: iRacing's `dcBrakeBias` is percent on most cars; values outside 20–90 % are shown as not reported. Note what each car reports. `engine_map` reads `dcThrottleShape`, else `dcFuelMixture`: check it follows the car's MAP knob.
4. Keypresses: refused with "game window not found" → the process name `iRacingSim64DX11.exe` / title in `games/iracing/game.toml` is wrong (Task Manager → Details). Bind the proposals in iRacing for TC / ABS / map / flash / wipers ([IRACING/NOTES.md](IRACING/NOTES.md)).
5. **The map** (dead reckoning): drive a lap, look at the analysis page. Mirrored corners → the sign of `VelocityY` in `Map.step` (connector) is the other way; a track that does not close → heading convention (`YawNorth`). The drift within one lap should be small (MarvinsAIRA measured 0.3 %).
6. `lap_valid`: the analysis page counts a lap invalid after four wheels off (`PlayerTrackSurface` 0); ask the owner whether that matches iRacing's own judgement in their sessions.
7. `python tools\analysis_check.py --last 1` after a few laps: rate about 30 Hz, lap times against iRacing's (`game_time`), driven distance ≈ track length.

### 4. DiRT Rally 2.0

Enable UDP once ([DR2/NOTES.md](DR2/NOTES.md)), drive a stage: values, stage / car names, stage start and end on the analysis page, `analysis_check`.

## Findings from the real data (ACE 0.9.1)

- `lap_pos`, track length and position work; driven distance 99 % of the track length; 29 Hz on clean laps; section times add up to the lap time; steering about ±0.95.
- `is_valid_lap`: true on clean laps, false after cutting and on the first lap from the pits (correct).
- `session_id` stable within a session; **not checked across sessions**.
- Pause: in one run ACE kept reporting `live` while the car stood 89 s, and ACE's lap time included it; never confirmed whether that was the pause menu.
- In the pit box ACE reports a lap position near the line; a short out lap is fine.
- Not checked: whether the ACE map is mirrored.

## Open, in the owner's order of interest

1. AI trainer quality with the new facts and prompt (test plan 1).
2. First drives in ACR, iRacing, DR2 (test plan 2–4).
3. Driving aids in the graphs: bests from before 9 November have no aid data (`NOT RECORDED`) until new bests are saved.
4. ChatGPT / Gemini / Ollama in the trainer: written from the providers' docs, never called for real (Gemini's `x-goog-api-key` header and `GET /v1beta/models/<model>` unconfirmed). **Not planned to be confirmed**: the owner uses Claude only (owner, 10 November 2026). Leave the code; do not spend time on it unless the owner asks.
5. **TYRES and PERFORMANCE cards** (ACE; the demo calls it DRIVE MODE; the field is `drive_mode`, ACE's control is Performance Mode Cycle; built 10 November 2026 as in the mockup `mockups\dash-tyres-drive-mode.png`): **not checked in the game yet**. The TYRES card follows the ACE HUD (owner, 10 November 2026): pressures outside, tiles coloured by tyre temperature, the brake as a full bar beside each tyre coloured by brake temperature, no legend, no compound. Check in ACE: tyre and brake temperatures and pressures plausible (pressure unit: psi expected, a value below 6 is taken as bar), colours along a scale (tyres green 80–100 C, yellow 115, red from 130; brakes green 300–650 C, red from 900; first guesses, `scale` / `brake_scale` in `games/ace/dash.toml`), the mode name on a car with modes (BMW M4 CSL: SPORT+), NOT ON THIS CAR on one without; bind **Performance Mode Cycle − / +** to `Num3` / `Num6` in ACE and try − / +.
6. A LICENSE file for the public repository (the owner's decision; MIT suggested).

## How it works (where to look)

- **Connectors** `games/<id>/connector.py` translate a game into `core/telemetry.py` `FIELDS`; `games/<id>/game.toml` (window, keys, kinds), `dash.toml` (the dash box cards). Shared memory through `core/winmem.py` (`SharedMemory`, `read_at`, `process_running`); Kunos' physics page in `core/kunos.py`.
- **Recorder** `core/recorder.py`: rows `[now, p, x, y, v, thr, brk, str, g, sec, att, line, tc_on, abs_on, esc_on, levels, rpm]`; the clock stands still while nothing is recorded; `_why_not()`, `_sample()` (line crossing, restart, stage end, repeat rule), `_shown()`, `complete_laps()`, `section(n, laps)` (18 columns).
- **AI trainer** `core/trainer.py`: `corner_facts()`, `trace()`, `facts()`, `aid_facts()`, `section_data()`, `build_request()`, `SYSTEM_PROMPT`, `SCHEMA`, providers, `check_answer()` (`MAX_TIPS` 9, `FOCUS_SECTIONS` 4).
- **Files**: `data\runs\<game>\<track>\<car>\<date_time>\lap-NNN.jsonl` (samples with `rpm`, `a`, `lv`), `run.jsonl`, `data\baselines\...`, `data\pending.jsonl`, `data\trainer.jsonl`. Formats in [SPEC.md](SPEC.md#analysis).
- **Page** `ui/js/analysis.js`; dash box `ui/js/dashbox.js`.

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; no lap picker.
- UNDO restores the previous baseline but does not bring the offer back into REVIEW.
- KEEP BASELINES ONLY deletes the lap files; open offers then live only in memory until the bridge restarts.
- A lap started standing on a circuit (race start) counts as a normal lap.
- A different track length in another session changes the section count; old section baselines would no longer line up.
- DR2: two cars with the same gear count, redline and idle share one name (and one set of bests).
- iRacing: the map is dead-reckoned (drift within a lap); ACR: stage start / end detection unproven.

## Decisions the owner made (keep them)

- Universal UI, one folder per game (`games/<id>/connector.py`, `game.toml`, `dash.toml`); UI in `ui/` (plain HTML / CSS / JS); Python standard library only. Every game gets every page.
- GEAR + REV: yellow 14-segment digit in a light grey frame close to the screen edges, GEAR in the top line, as large as possible; 8 rev lights blue-green-yellow-red-red-yellow-green-blue filling from the outside in, the red pair lights at the game's shift point, the lights never flash, unlit fields dim (54 px free at both ends for the settings button); no rpm / speed numbers; E for errors with a chip; always the gear number (P only for park); gears above 9 show E. **No** dimmed gear with the engine off, **no** flashing gear in the pit lane. The screen inside the frame turns dark red when the two red rev lights are lit (the game's shift point) and flashes bright red only at max rev / on the limiter; the rev lights work as before (owner, 10 November 2026).
- Settings button: same size and place on every page, top right. Home page `/Racing_Dashboard`. On a tablet in landscape every page starts 26 px lower (`--top-gap`).
- DASH (iPad): cards, the same layout for every car of a game, different per game allowed; greyed cards for what a car lacks; values read back from the game; a card lights up after a tap and when the value changes in the game; TC / ABS / ESC amber while active; warning lamps as colours only; no hints. ACE: IGNITION held, WIPERS as a latch, LIGHTS / WIPERS without state, diff locking in % for cars without steps, FIXED settings, no LAUNCH, no AUTO CLUTCH. Buttons without a state for what a game does not report (ACR lights / wipers / engine, iRacing ignition / starter / flash / wipers, DR2 lights / wipers); RECOVER held 1 s.
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)): one page; map left with BACK and the cursor; right side tabs **REVIEW first**, GRAPHS (4 per page, scrolled), TRAINER; green best, blue last, red now; deltas always visible; section strip with slider; no braking markers; LIVE start view; 250 m sections by track position; 30 Hz, written at lap end; baselines per game / track / car for the lap and every section; every new best **offered, never saved without a tap**; one backup per baseline; invalid laps: sections may be offered, the lap never; a pause stops the lap time; driving aids recorded and shown as lanes; the repeat rule. No pro / reference laps (the owner decided to stay with the own best, 9 November 2026).
- AI TRAINER ([TRAINER.md](TRAINER.md)): button bottom right on the map, only on a tap; overview = whole track on the last complete lap, zoomed = that section; Claude / ChatGPT / Gemini / Ollama with the owner's key kept on the PC; FAST / BEST (Claude: Haiku 5.5 medium / Opus 5.5 high); facts computed by the bridge, fixed prompt; **fundamentals first, then the loss against BEST, every tip linked to the numbers; up to 9 tips; title starts with the category, no example in the prompt; no summary**; English; tapping a tip opens its place in GRAPHS; last 5 answers kept.

## Working with the owner

- Short messages, mostly English, sometimes German, often with typos; reply short and plain in the language they wrote.
- **Commit and push when the owner says so**; commit to `main`, end commit messages with the Co-Authored-By line. The only other branch is one work-in-progress branch for a prototype the owner has not approved yet. No branch per feature.
- For visual changes: **show PNG mockups first** (HTML rendered with a headless browser), ask for feedback, then build. For bigger features a short interview first (3–4 multiple-choice questions per round worked well).
- Keep README, SPEC, the game notes, TRAINER and tests in step with every change; no personal data in commits; no emoji in the UI. Never ask for or handle the owner's API key.
- The owner tests on the iPad (analysis, dash) and an iPhone (gear) while driving with a controller.
- Ideas not built yet: lap picker after the session, tyre / brake / damage cards, two-page dash box, names for light / wiper stages, flags, a clearer "no API credits" message, more games ([ASSISTS.md](ASSISTS.md)).
