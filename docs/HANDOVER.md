# Handover – local session on the Windows PC

For the next Claude session **on the owner's Windows PC** (ACE, Assetto Corsa Rally, iRacing, DiRT Rally 2.0, the iPad and the iPhone at hand). Written at the end of the cloud cleanup session after the local session of 9 November 2026. Read this first, then [README.md](../README.md), [SPEC.md](SPEC.md), and as needed [ANALYSIS.md](ANALYSIS.md), [TRAINER.md](TRAINER.md) and the game notes ([ACE](ACE/NOTES.md), [ACR](ACR/NOTES.md), [IRACING](IRACING/NOTES.md), [DR2](DR2/NOTES.md)).

**The job for this session:** first make sure the cleanup changed nothing in the game (step 1 of the test plan, ten minutes with ACE), then work on the open items with the owner.

## Start

```
git pull
python -m unittest discover tests
python core\server.py --check
python core\server.py
```

All 85 tests must pass and `--check` must list five games (ace, acr, demo, dr2, iracing) with `Result OK`. Pages: `/Racing_Dashboard` (home), `/gear`, `/dash`, `/analysis`, `/boost`, `/grip`, `/tyres`, `/damage`, `/map`, `/Startup` (page names in any case); `/state` is the live frame, `/api/info` the dash map. An open page reloads itself when files in `ui/` change; **the bridge must be restarted after `git pull` and after every change to Python code** (the owner hit this twice: a bridge started before a commit serves the old fields). Log: `logs\racing-dashboard.log`.

`tools\ace_probe.py` is gone (see below): use `tools\live.py`. **Edit files with the Edit tool or Python (utf-8), never PowerShell Get-Content / Set-Content** (that broke the `°` in `rd.js` once; `tests/test_encoding.py` catches it).

## What the cloud cleanup session changed (`46c453a`)

Nothing the pages show should be different. It was tested with the unit tests and the demo car only, so the game has to confirm it.

| Removed | Why | What could show up in the game if it was wrong |
| --- | --- | --- |
| Eight telemetry fields: `max_gears`, `shift_down`, `clutch`, `lap`, `position`, `cars`, `best_ms`, `delta_ms` (model, all five connectors, tests, docs) | nothing read them since the BUTTONS page went | a page or card that shows "-" or nothing where it had a value; an error in `logs\racing-dashboard.log` |
| The ACE connector's `ace \| raw` change log (`watched`, `changes`) | a debug log; it parsed the graphics page a second time on every read; ACE does not publish the light / wiper stages it was written to find | nothing: the log just no longer has `ace \| raw` lines |
| `tools\ace_probe.py` | ACE only, its questions are answered; `tools\live.py` covers every game | – |
| In `ui/js/rd.js`: the body classes `rd-stale`, `rd-shift`, `rd-limiter`, `rd-pit`, `rd-tc`, `rd-abs`, the `data-rd-on` binding, `RD.checks`, the `bias` / `fuel` formats, the rev lights' `data-early` option and their `shift` / `limiter` classes, the `RD.start` options | no style or page used them | **rev lights**: they must still fill from 88 % of the shift point, the red pair at the game's shift signal, the screen dark red then, bright red flashing on the limiter |

Also: the dash map check now knows the tyre card's score keys (`core_score`, `surface_score`, `brake_score`); a misspelt field name there is logged and the card left out. The ACE notes have a "checked in the game" and a "still to check" list; `docs/ACE/KEYS.md` no longer points to the removed log lines.

## Live debugging: pull the data while the owner drives

Keep the bridge running in one window and use a second one. The tools only read.

| Command | What it shows |
| --- | --- |
| `python tools\live.py` | the basic values five times a second, from the bridge's `/state` (every game) |
| `python tools\live.py grip` | a preset: `basic`, `grip`, `boost`, `revs`, `aids`, `tyres`, `car`, `analysis` |
| `python tools\live.py car --changes` | a line only when a value changes (lights, wipers, levels, lamps) |
| `python tools\live.py --fields rpm,boost_bar,gas` | any fields |
| `python tools\live.py --once` | the whole frame once as JSON |
| `python tools\live.py --record 90` | records every frame for 90 s to `logs\live-<game>-<date_time>.jsonl` and checks it: slip sign and GRIP stages, the slip where ABS / TC start, shift rpm and limiter per gear, boost range, min .. max of every field; "!!" marks a problem |
| `python tools\live.py --check last` | the check again for the newest recording |
| `python tools\analysis_check.py --last 1` | the laps the analysis recorder wrote |

One question per recording ("three hard stops with ABS off"). To find an unknown game value, write a throw-away script that records the raw shared memory once a second while the owner does one thing (a burnout, a crash, a reset to the pits) and list the fields that change with it; that found the tyre scores and the damage and ruled out wear. Do not commit such scripts.

## Test plan, in this order

### 1. After the cleanup: ten minutes with ACE (do this first)

1. `git pull`, restart the bridge, reload nothing by hand (the pages reload themselves). The log must show `ace | shared memory | game ..., layout ...` and no `read error`.
2. **GEAR + REV** on the iPhone: the gear, the speed, the rev lights up to the shift point, the red screen at the shift signal, the flashing on the limiter. In the pause menu the gear shows E with the chip NO NEW DATA FROM THE GAME.
3. **DASH** on the iPad: every card has its value; TC − / + changes the car and the card; TC / ABS turn amber while they work; the TYRES card has colours; FUEL shows litres and laps left.
4. **The phone pages** with the arrows: BOOST, GRIP, TYRES, DAMAGE, MAP, STARTUP each show what they showed before.
5. **ANALYSIS**: drive two laps; the lap time appears and matches the game's; `python tools\analysis_check.py --last 1` has no "!!". The AI TRAINER button answers.
6. `python tools\live.py --record 60` during a lap: the check prints without "!!" (it lists every field: none of the eight removed ones should be missed by anything).

If something is off, compare with the commit before the cleanup (`git diff 06b1135 46c453a -- <file>`) and fix forward.

### 2. The open items with ACE

- **A new DASH card**: the owner said "introduce one completely new" card but never said what it should show. Ask; then mockups first.
- **MAP on a track the page has not seen yet**: first lap not zoomed and filling in; after a lap fitted and still.
- **DAMAGE on the iPhone after a crash** (front, rear, both sides; a suspension hit).
- **GRIP**: the owner's feel for the calm colours and the 4 / 7 / 15 / 40 % stages; one recording with ABS and TC on (only 5–6 starts were seen): `python tools\live.py --record 120`, read "slip when it starts" under ABS / TC.
- **AI trainer**: three clean laps, save the bests, ask for the whole track and one section; read the facts sent with each answer (`data\trainer.jsonl`, field `data`) before changing the prompt (`core/trainer.py`, [TRAINER.md](TRAINER.md)).
- **Still to check in ACE** ([ACE/NOTES.md](ACE/NOTES.md)): the `status` numbers for pause and replay, `session_id` across sessions, the player's slot with other cars on track, PERFORMANCE − / + (Num3 / Num6).

### 3. First drives in Assetto Corsa Rally, iRacing, DiRT Rally 2.0 (never run against the games)

For each: GAME → the game, then `python tools\live.py` (do the values follow the car?), `python tools\live.py grip` (slip: ACR `slipRatio`, DR2 wheel speeds; iRacing has none and GRIP says so), `python tools\live.py --record 120` over one stage or a few laps, then `python tools\analysis_check.py --last 1`. The questions per game are in its NOTES:

- **ACR**: attaches only while `acr.exe` runs (log `acr | shared memory | attached ...`); the stage start and end on the analysis page; the slip sign; pause detection; bind the proposed keys. ACR damage and tyre scores are not read yet (it uses the same Kunos physics page as ACE).
- **iRacing**: the process name `iRacingSim64DX11.exe` for the keys; brake bias and engine map per car; the map direction (`VelocityY` sign) and the steering sign; `ManifoldPress` taken as absolute bar (boost = value − 1.013): unconfirmed.
- **DR2**: switch UDP on in the XML once ([DR2/NOTES.md](DR2/NOTES.md)); wheel speeds in m/s (part throttle on a straight must leave GRIP grey); stage start and end.

## What the sessions before did (newest first)

| Commit | What |
| --- | --- |
| `46c453a` | the cloud cleanup (above) |
| `06b1135` | Encoding test fixed (it matched its own docstring once tracked), the handover |
| `89fdf10` | **Broken characters**: a PowerShell edit had put a stray A-circumflex before every `°` in `ui/js/rd.js` (tyre tiles showed it after the temperature); restored, byte-order marks removed from seven files, new `tests/test_encoding.py`. **Edit files with the Edit tool or Python (utf-8), never PowerShell Get-Content / Set-Content** |
| `156b6a6` | **MAP** draws the track itself from the live position (1000 pieces by `lap_pos`, kept per track in the browser, seeded from the analysis outline); first lap at least track length / 3.2 wide so a straight does not fill the screen; fitted once 95 % is known |
| `61455d0` | **DAMAGE** page (car from above like the ACE HUD: body = overall damage, bands for nose / flanks / tail with thin dividing lines, a small shock absorber per wheel) and **MAP** page; fields `damage_body`, `damage_suspension` (ACE `car_damage[9]`, checked with front, rear, left and right hits) |
| `f602b00` | **TYRES** page: the DASH tyres card on its own for the phone; the tyre view moved to `RD.tyreView` in `rd.js`, shared by both; Y in the segment font |
| `d283a2a`, `6d8026f` | **TYRES card like the ACE HUD**: tile coloured by ACE's core temperature score, a frame around it by the surface score, brake bars by the brake score (fields `tyre_core_score`, `tyre_surface_score`, `brake_score`). First built as a pressure frame: wrong, the HUD frame is green in the pits where the pressure score is 0.33 |
| `e26eff8` | **Page arrows** on the phone pages (bottom corners, round again); HOME, DASH, ANALYSIS have none |
| `90daaaa` | BOOST ignores ACE's `max_turbo_boost` (157 in the Camaro ZL1 blew up the scale); the gauge never passes 5 bar |
| `77a56d3` | GRIP: calm colours (stages 1–3 fade 0.15 s, hold 0.3 s per step down), stage 4 flashes and goes at once |
| `00a9054` | **STARTUP** page: IGN and ENGINE START STOP buttons like a modern road car's, same actions as the DASH ignition card |
| `1bce3d6` | GRIP stages 4 / 7 / 15 / 40 % from an ACE drive; BOOST without a turbo check; `tools/live.py` on 127.0.0.1 (localhost cost 2 s per frame on Windows) |

## Where things stand

| Part | State |
| --- | --- |
| Bridge, GEAR + REV, DASH, home | in daily use with ACE |
| GEAR + REV rev lights and red screen | verified in ACE: shift signal and limiter flag come from the game |
| Analysis page, AI trainer | verified with ACE; trainer answers with the rewritten prompt not judged yet |
| GRIP | **checked in ACE** (M4 GT3 Evo): slip sign, lock flag never set, ABS / TC start at 6–7 % slip; calm colours built, the owner's feel on the iPhone still open |
| BOOST | **checked in ACE** (M4 GT3 Evo: bar, up to 1.69; Camaro ZL1) |
| TYRES card and page | **checked in ACE** (Camaro ZL1): core / surface / brake scores like the HUD, the owner confirmed the frame works |
| DAMAGE | **checked in ACE** (Camaro ZL1, all four sides); the page itself seen by the owner in mockups, not yet after a crash on the iPhone |
| MAP | checked live at Brands Hatch after the fix; the first-lap behaviour (no zoom) only checked in code, not on a new track |
| STARTUP | works with ACE (owner: "that works well") |
| Assetto Corsa Rally, iRacing, DiRT Rally 2.0 | **never run against the games** |

## Open, in the owner's order of interest

1. The cleanup check in ACE (test plan 1).
2. A new DASH card: ask the owner what it should show.
3. MAP on a new track, DAMAGE after a crash, GRIP feel and a recording with ABS / TC on, AI trainer quality (test plan 2).
4. First drives in ACR, iRacing, DR2 (test plan 3).
5. ChatGPT / Gemini / Ollama in the trainer: never called for real, **not planned to be confirmed** (the owner uses Claude only). Leave the code.
6. A LICENSE file for the public repository (the owner's decision; MIT suggested).
7. Ideas: lap picker after the session, two-page dash box, names for light / wiper stages, flags, a clearer "no API credits" message, MAP turned 90° in portrait for wide tracks (offered, not asked for), more games ([ASSISTS.md](ASSISTS.md)).

## Mockups on the PC

Headless rendering that worked (Edge on Windows, the same idea with Chromium): put each page in an `<iframe>` inside one composite HTML file (844 × 390 landscape, 390 × 844 portrait, scaled with `transform`), and screenshot the composite with `--headless=new --virtual-time-budget=5000 --screenshot`. Loading a page directly hangs on its live stream (EventSource); inside an iframe it renders. CSS transitions are caught half way in such a render, so a mockup can show washed-out colours where the real page does not. A second bridge for mockups: start the demo game on its own port with `server.recorder = recorder.Recorder(<a scratch folder>, 30, 250.0, log=server.log.line)` so the analysis and map pages have data, and never write into `data/`.

## Findings from the real data (ACE 0.9.1)

- Porsche 992 GT3 R: shift signal ~9,000–9,040 rpm, limiter flag from ~9,070–9,120, `gear_rpm_window` always 1.0.
- BMW M4 GT3 Evo: `turbo_boost` 0 .. 1.69 bar; `max_turbo_boost` 0; `turbo_boost_level` 0 or 1 (no turbo flag). `slipRatio` negative braking, positive wheelspin, −1 locked; tyre `lock` never set; ABS starts at ~6.4 % slip, TC at ~7.1 %.
- Chevrolet Camaro ZL1: `max_turbo_boost` 157.4 at 0.39 bar boost (not used). Tyre scores: `tyre_normalized_temperature_core` 1.0 = fine .. 2.0 = too hot (goes with `tyre_temperature_c`), left / centre / right the surface (2.0 in burnouts), never below 1.0; `tyre_normalized_pressure` 0.33 at 26 psi, 1.0 from 28 psi (not used); `brake_normalized_temperature` 0 to 150 C, 1.0 at 400 C, still 1.0 at 515 C. **Tyre wear is not published** (physics `tyreWear` 0, nothing else found byte by byte). Damage: graphics `car_damage[9]` = front, rear, left, right, centre, suspension FL, FR, RL, RR (0 .. 1), physics `carDamage` the same unscaled.
- Toyota GR86: no turbo, all turbo values 0. Lights / wipers stages are not published.

## How it works (where to look)

- **Connectors** `games/<id>/connector.py` translate a game into `core/telemetry.py` `FIELDS`; `game.toml` (window, keys), `dash.toml` (dash box cards). Kunos' physics page and `boost()` in `core/kunos.py`.
- **Pages** `ui/*.html`, shared code `ui/js/rd.js` (stream, formats, widgets, rev lights, the tyre view `RD.tyreView`, page arrows `RD.CYCLE`, settings, styles), `ui/js/seg14.js` (14-segment SVG), one script per page (`dashbox.js`, `analysis.js`, `boost.js`, `grip.js`, `tyres.js`, `damage.js`, `map.js`, `startup.js`); styles `ui/styles/<page>/<style>.css`. A page that needs a game's action or field names takes them from its dash map in `/api/info` (STARTUP, TYRES, GRIP).
- **Recorder** `core/recorder.py`, **AI trainer** `core/trainer.py`; file formats in [SPEC.md](SPEC.md#analysis).
- **Tools** `tools/live.py` (watch, record, check any game from the running bridge) and `tools/analysis_check.py` (the recorded laps): see "Live debugging" above; both are still needed for the first drives in ACR, iRacing and DR2.

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; no lap picker. UNDO does not bring the offer back into REVIEW. KEEP BASELINES ONLY deletes the lap files.
- A different track length in another session changes the section count. DR2: two cars with the same gear count, redline and idle share one name.
- iRacing: the map is dead-reckoned (drift within a lap); ACR: stage start / end detection unproven.
- MAP keeps a track per browser: another phone draws it again (or takes the analysis outline).

## Decisions the owner made (keep them)

- Universal UI, one folder per game; UI in `ui/` (plain HTML / CSS / JS); Python standard library only. Every game gets every page; a page a game cannot fill says so in the chip.
- **Phone pages** (GEAR + REV, BOOST, GRIP, TYRES, DAMAGE, MAP, STARTUP) share one look: a light grey frame, the page name in yellow 14-segment letters in its top line, faint page arrows in the bottom corners (round again, in that order). HOME, DASH, ANALYSIS are not in the cycle.
- GEAR + REV: yellow 14-segment gear, 8 rev lights from 88 % of the game's shift point; red pair and dark red screen at the game's shift signal; **bright red flashing only on the game's limiter flag — a simple rule by flags, no rule per car**; SPEED small below; E for errors with a chip.
- BOOST: a gauge; BAR under the hub, the value with one decimal below; VACUUM in iRacing; **no check whether a car has a turbo** – the gauge is always drawn and stays at 0 ("don't make it too complicated"); ACE's maximum is not used.
- GRIP: four tiles, colour only; braking yellow → red, wheelspin light blue → purple; stages 4 / 7 / 15 / 40 % for every car; **stage 4 flashes** and comes and goes at once, stages 1–3 fade 0.15 s and hold 0.3 s per step down ("informed, not disturbed"); ABS / TC setting only.
- TYRES (card and page): like the ACE HUD – tile by the core temperature score, frame by the surface score, brake bar by the brake score; no wear bar (ACE does not send it).
- DAMAGE: the car from above like the ACE HUD (sports car, no wheels), body = overall damage, bands for nose / flanks / tail with thin dividing lines, a small shock absorber per wheel (not a zigzag); light grey none → yellow → orange → red.
- MAP: the whole track fitted to the screen, not zoomed, red dot, start / finish line.
- STARTUP (`/Startup`): IGN and ENGINE START STOP like a modern road car's (dark brushed metal, chrome bezels, glass caps, white text); state by light only (IGN amber, START red ready / green running); same actions as the DASH ignition card.
- No BUTTONS page; the DASH and STARTUP send keys.
- Settings button top right on every page; home page `/Racing_Dashboard` (flight sim dashboards share the address); on a tablet in landscape every page starts 26 px lower.
- DASH (iPad): cards, same layout for every car of a game; greyed cards for what a car lacks; values read back from the game; TC / ABS / ESC amber while active; ACE: IGNITION held, WIPERS as a latch, engine map from 1, PERFORMANCE, no key on Comma.
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)) and AI TRAINER ([TRAINER.md](TRAINER.md)) as described there; trainer only on a tap, FAST / BEST (Claude Haiku 5.5 medium / Opus 5.5 high), up to 9 tips, English.

## Working with the owner

- Short messages, mostly English, sometimes German, often with typos; reply short and plain in their language.
- **Commit and push only when the owner says so**; commit to `main`, end commit messages with the Co-Authored-By line. The only other branch is one work-in-progress branch for a prototype the owner has not approved yet.
- For visual changes: **show PNG mockups first**, then build; expect two or three rounds ("looks cheap", "darker", "like the game"). When the owner sends a game screenshot, copy its layout closely. For bigger features a short interview first (3–4 multiple-choice questions).
- Keep README, SPEC, the game notes and tests in step with every change; no personal data in commits; no emoji in the UI. **Never ask for or handle the owner's API key.**
- Check against the game with the tools above before changing code, and write what the game really sends into its NOTES (the field table and the checked / still-to-check lists). Before the session ends, rewrite this file for the next session (say whether it is for a cloud or a local one, what it can and cannot do, and which in-game checks are left).
