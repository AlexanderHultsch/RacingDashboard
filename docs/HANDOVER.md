# Handover – local session on the Windows PC

For the next Claude session **on the owner's Windows PC** (ACE, Assetto Corsa Rally, iRacing, DiRT Rally 2.0, the iPad and iPhone at hand). Written at the end of the cloud session, 10 November 2026. Read this first, then [README.md](../README.md), [SPEC.md](SPEC.md), and as needed [ANALYSIS.md](ANALYSIS.md), [TRAINER.md](TRAINER.md) and the game notes ([ACE](ACE/NOTES.md), [ACR](ACR/NOTES.md), [IRACING](IRACING/NOTES.md), [DR2](DR2/NOTES.md)).

**The job for this session:** drive with the owner and check what the cloud session could only build against simulated data: the **GRIP** page and **BOOST** in a turbo car first, then the open items below. Pull the data live with `tools/live.py` (every game) and `tools/ace_probe.py --raw` (ACE raw values), fix what the games deliver differently, and write the findings into the game notes and this file.

## Start

```
git pull
python -m unittest discover tests
python core\server.py --check
python core\server.py
```

All 84 tests must pass and `--check` must list five games (ace, acr, demo, dr2, iracing) with `Result OK`. Pages: `/Racing_Dashboard` (home), `/gear`, `/dash`, `/analysis`, `/boost`, `/grip`, `/Startup`; `/state` is the live frame, `/api/info` the dash map. An open page reloads itself when files in `ui/` change, but **restart the bridge after a change to Python code**. Log: `logs\racing-dashboard.log`. The repository is `github.com/AlexanderHultsch/RacingDashboard` (the old name Racing-Dashboard redirects).

## Live debugging: pull the data while the owner drives

Keep the bridge running in one window and use a second one. Both tools only read; nothing is changed in the game.

| Command | What it shows |
| --- | --- |
| `python tools\live.py` | the basic values five times a second, from the bridge's `/state` (works for every game) |
| `python tools\live.py grip` | a preset: `basic`, `grip` (slip per wheel with the GRIP stage each tile shows, lock flags, ABS / TC), `boost`, `revs`, `aids`, `tyres`, `car`, `analysis` |
| `python tools\live.py car --changes` | a line only when a value changes: good for lights, wipers, levels, lamps |
| `python tools\live.py --fields rpm,boost_bar,gas` | any fields |
| `python tools\live.py --once` | the whole frame once as JSON |
| `python tools\live.py --record 90` | records every frame for 90 s (20 a second) to `logs\live-<game>-<date_time>.jsonl` and checks it |
| `python tools\live.py --check last` | the check again for the newest recording (or give a file) |
| `python tools\ace_probe.py --raw` | ACE only, straight from the shared memory: `slipRatio`, `wheelSlip`, the tyre `slip` / `lock`, `tcInAction` / `absInAction` and the graphics `tc_active` / `abs_active`, every turbo value (`turbo_boost`, `turbo_boost_level`, `turbo_boost_perc`, `electronics.turbo_level`, `max_turbo_boost`, physics `turboBoost`) |
| `python tools\analysis_check.py --last 1` | the laps the analysis recorder wrote |

The check after a recording prints per section, with "!!" for a problem:
- **GRIP**: the slip of the front wheels under hard braking and of the rear wheels on full throttle, with the sign (braking must be negative, wheelspin positive; "!! ... the sign is the other way round" means flip it in the connector), the slip at part throttle (must stay near 0), the share of each GRIP stage per wheel, and whether the lock flag was ever set.
- **ABS / TC**: the settings seen, how often each worked, and **the slip at the moment ABS / TC start to work**: that is the car's grip limit and the best guide for where GRIP stage 2 should start (`STAGES` in `ui/js/grip.js`; the tool reads the limits from there).
- **REVS**: the rpm of the shift signal per gear and where the limiter starts.
- **BOOST**: the boost range and the rpm of the highest boost.
- **Every field**: min .. max or the values seen.

Paste the output into the chat and the recording stays in `logs\` (not in git). Ask the owner to drive one thing per recording (for example "three hard stops with ABS off"), so each recording answers one question.

## Test plan, in the owner's order of interest

### 1. GRIP in ACE

1. iPhone on `/grip`, bridge running, `python tools\live.py grip` in a second window. Car with ABS and TC (Porsche 992 GT3 R).
2. `python tools\live.py --record 90`: the owner drives normally, then three hard stops with **ABS off** (DASH: ABS to 0), then full throttle out of slow corners with **TC off**.
3. Read the check:
   - Sign: braking negative, wheelspin positive. If it is the other way round, negate `slips()` in `core/kunos.py` (ACE and ACR share it) and the test values in `tests/test_ace.py` / `test_acr.py`.
   - Part throttle near 0 (if not: the value is not a slip ratio; try `wheelSlip` or the graphics tyre `slip`, compare with `ace_probe.py --raw`).
   - Lock flag: set during the ABS-off stops? If never, stage 4 comes from slip alone (50 %), which is fine.
   - Slip when ABS / TC start (record again with ABS and TC on): if it is far from 12 %, move the stage limits in `ui/js/grip.js` (`STAGES`), with the owner. Same limits for every car (owner's rule), unless the owner wants them learned per car.
4. Ask the owner whether the colours come too early or too late on the iPhone. Stage 4 must flash.

### 2. BOOST in an ACE turbo car

BMW M4 GT3, Ferrari 296 GT3 or McLaren 720S GT3 Evo. `python tools\ace_probe.py --raw` while accelerating in 2nd and 3rd: which value rises with boost and to what number (bar assumed; a value around 1–2.5 is bar, around 100–250 is kPa, 0..1 is a share). The connector reads graphics `turbo_boost` (physics `turboBoost` as a fallback) and `max_turbo_boost` (`games/ace/connector.py`, `kunos.boost`). Then `python tools\live.py boost` and the iPhone on `/boost`: the needle must follow, the gauge end must fit the car.

### 3. AI trainer with ACE

Three clean laps, save the bests, AI TRAINER for the whole track and one section (FAST, then BEST once). Read the facts sent with each answer (`data\trainer.jsonl`, field `data`) before changing the prompt (`core/trainer.py`, [TRAINER.md](TRAINER.md)).

### 4. First drives in Assetto Corsa Rally, iRacing, DiRT Rally 2.0

For each: `python tools\live.py` (values follow the car?), `python tools\live.py grip` (slip: ACR `slipRatio`, DR2 wheel speeds; iRacing has none and GRIP says so), `python tools\live.py --record 120` over one stage or a few laps, then `python tools\analysis_check.py --last 1`. The open questions per game are in its NOTES: ACR attaches only while `acr.exe` runs, stage start / end; iRacing process name, brake bias per car, map direction (`VelocityY` sign), steering sign; DR2 UDP switched on in the XML, wheel speeds in m/s (part throttle must leave GRIP grey).

### 5. TYRES / PERFORMANCE cards in ACE

`python tools\live.py tyres` and `aids`: pressure unit (a pressure below 6 is taken as bar), colour scales against the game's HUD, Num3 / Num6 for the performance mode.

## What the cloud session did (10 November 2026, newest first)

| Commit | What |
| --- | --- |
| this one | **Live debugging tools**: `tools/live.py` (watch presets, record, check: GRIP sign and stages, ABS / TC onset slip, shift rpm per gear, boost, every field) and `tools/ace_probe.py --raw` (raw slip, lock, TC / ABS flags and every turbo value); `tests/test_live.py`; this handover for the local session |
| `8e8cd1f` | **GRIP page** `/grip` (phone): four tyre tiles coloured by the slip of each wheel (braking yellow → orange → red → bright red flashing, wheelspin light blue → blue-violet → purple → magenta flashing, grey = grip; stages from 6 / 12 / 25 / 50 % slip or the game's lock flag), ABS / TC setting between the tyres (white, OFF, grey – without, hidden when the game has none). Fields `wheel_slip`, `wheel_lock` (ACE `slipRatio` + tyre `lock`, ACR `slipRatio`, DR2 wheel speeds, demo simulated; iRacing none). Home tile, settings, startup line |
| `7aafb12` | **BUTTONS page removed** (owner): page, script, styles, home tile, settings entry, the LED strip and RPM bar widgets, `groups` in `/api/info`; `core/actions.py` is a flat `ACTIONS` table of the 21 actions the dash boxes use (camera, view, indicators, hazards, horn, shifting, pause and replay actions and their keys are gone; the demo car always shifts itself) |

Before that, the local session of 10 November: BOOST page (`2a636cc`, `d9b43d7`), rev lights by the game's flags (`5d1d565`), SPEED box (`b651239`), pages reload themselves (`bdfcab0`), TYRES / PERFORMANCE / DRIVE MODE cards (`2bff8f3` … `deb1037`).

## Where things stand

| Part | State |
| --- | --- |
| Bridge, GEAR + REV, DASH, home | in daily use with ACE |
| GEAR + REV rev lights and red screen | verified in ACE (Porsche 992 GT3 R, Toyota GR86): shift signal and limiter flag come from the game |
| Analysis page | verified with ACE (lap times within 0.006 s of the game's) |
| AI trainer | works with Claude; answers with the rewritten prompt (up to 9 tips) not judged yet |
| GRIP page | **checked in ACE** (BMW M4 GT3 Evo, 9 November 2026): slip sign right, lock flag never set, stages moved to 4 / 7 / 15 / 40 % (ABS / TC start at 6–7 %). Open: the owner's feel on the iPhone, more ABS / TC-on stops |
| BOOST page | **checked in ACE** (M4 GT3 Evo): `turbo_boost` in bar, up to 1.69; `max_turbo_boost` 0. No turbo check any more: the gauge is always drawn, 0 without a value |
| TYRES / PERFORMANCE cards | built, **not checked in the game** (pressure unit, colour scales, Num3 / Num6) |
| Assetto Corsa Rally, iRacing, DiRT Rally 2.0 | **never run against the games** |

## Open, in the owner's order of interest

1. GRIP in ACE: the owner's feel for the new stages on the iPhone; a recording with ABS and TC on (only 5–6 starts seen so far).
2. BOOST: done in ACE. iRacing's `ManifoldPress` is taken as absolute bar (boost = value − 1.013): unconfirmed.
3. STARTUP page (`/Startup`, built 9 November 2026): checked with the live ACE state (engine running: IGN amber, START green) and with the demo (presses, blocked START while running); **not yet pressed in ACE from the iPhone** (IGN off / on, START with the ignition on).
4. AI trainer quality with the new facts and prompt (test plan 3).
5. First drives in ACR, iRacing, DR2 (test plan 4).
6. TYRES / PERFORMANCE cards in ACE (test plan 5).
7. Driving aids in the graphs: bests from before 9 November have no aid data (`NOT RECORDED`) until new bests are saved.
8. ChatGPT / Gemini / Ollama in the trainer: never called for real, **not planned to be confirmed** (the owner uses Claude only). Leave the code.
9. A LICENSE file for the public repository (the owner's decision; MIT suggested).
10. Ideas not built yet: lap picker after the session, damage card, two-page dash box, names for light / wiper stages, flags, a clearer "no API credits" message, GRIP limits learned per car, more games ([ASSISTS.md](ASSISTS.md)).

## Findings from the real data (ACE 0.9.1)

- Porsche 992 GT3 R: max rpm 9,400, shift signal (`is_change_up_rpm`) from ~9,000–9,040 rpm in every gear, limiter flag (`is_rpm_limiter_on`) from ~9,070–9,120. `gear_rpm_window` is always 1.0 (no shift-light range from the game).
- Toyota GR86: no turbo, all turbo values 0, `engine_type` 0.
- BMW M4 GT3 Evo (Brands Hatch, 9 November 2026): `turbo_boost` 0 .. 1.69 bar (bar, highest around 5,000 rpm), `max_turbo_boost` 0, `turbo_boost_level` 0 or 1 (no turbo flag). Chevrolet Camaro ZL1: `max_turbo_boost` 157.4 at 0.39 bar boost (blew up the gauge scale): ACE's maximum is not used, the gauge never goes past 5 bar. `slipRatio` negative braking, positive wheelspin, −1 locked; the tyre `lock` flag never set; ABS starts at ~6.4 % slip, TC at ~7.1 %. Shift signal ~6,740–7,190 rpm, limiter from ~6,660–6,710 (max 7,000).
- `tools/live.py` must read `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and costs ~2 s per frame (fixed 9 November).
- `lap_pos`, track length and position work; section times add up to the lap time; `is_valid_lap` false after cutting and on the out lap.
- Lights / wipers stages are not published by ACE 0.9.1. Not checked: whether the ACE map is mirrored; `session_id` across sessions.

## How it works (where to look)

- **Connectors** `games/<id>/connector.py` translate a game into `core/telemetry.py` `FIELDS`; `game.toml` (window, keys), `dash.toml` (dash box cards). Kunos' physics page and `boost()` in `core/kunos.py`.
- **Pages** `ui/*.html`, shared code `ui/js/rd.js` (stream, formats, widgets, rev lights, settings, styles), `ui/js/seg14.js` (14-segment SVG), `ui/js/dashbox.js`, `ui/js/analysis.js`, `ui/js/boost.js`, `ui/js/grip.js`, `ui/js/startup.js`; styles `ui/styles/<page>/<style>.css`.
- **Recorder** `core/recorder.py`, **AI trainer** `core/trainer.py`; file formats in [SPEC.md](SPEC.md#analysis).
- **Tools** `tools/live.py` (live values of every game, recordings, checks), `tools/ace_probe.py` (ACE values straight from the shared memory, `--analysis`, `--raw`), `tools/analysis_check.py` (recorded laps).

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; no lap picker. UNDO does not bring the offer back into REVIEW. KEEP BASELINES ONLY deletes the lap files.
- A different track length in another session changes the section count. DR2: two cars with the same gear count, redline and idle share one name.
- iRacing: the map is dead-reckoned (drift within a lap); ACR: stage start / end detection unproven.

## Decisions the owner made (keep them)

- Universal UI, one folder per game; UI in `ui/` (plain HTML / CSS / JS); Python standard library only. Every game gets every page; a page a game cannot fill says so in the chip (BOOST in DR2: the gauge stays at 0).
- GEAR + REV: yellow 14-segment gear in a light grey frame close to the screen edges, GEAR in the top line; 8 rev lights blue-green-yellow-red-red-yellow-green-blue from the outside in, from 88 % of the game's shift point up to it; the red pair and the dark red screen at the game's shift signal; **bright red flashing only on the game's limiter flag — a simple rule by flags, no rule per car**; the lights never flash; no rpm number; SPEED small in a second frame below (no unit); E for errors with a chip; always the gear number (P only for park); gears above 9 show E.
- BOOST (phone): a gauge, not a number or bar; BAR under the hub, the value with one decimal below the gauge in the SPEED number style; VACUUM in iRacing; own link `/boost`, listed in the startup window. **No check whether a car has a turbo**: the gauge is always fully drawn and stays at 0 without a value (owner, 9 November 2026: "don't make it too complicated").
- GRIP (phone): four tyre tiles, colour only (no text, no LEDs), braking yellow to red, wheelspin light blue to purple, stages from 4 / 7 / 15 / 40 % slip, the same for every car, **stage 4 flashes bright** and comes and goes at once, stages 1–3 fade in 0.15 s and stay at least 0.3 s before stepping down one stage (calm colours, owner, 9 November 2026); in portrait a compact frame, not stretched; ABS / TC show only the setting, no colour, no flashing, grey without, hidden when the game has none (owner, 10 November 2026).
- No BUTTONS page (removed by the owner, 10 November 2026). The DASH and STARTUP send keys.
- STARTUP (`/Startup`, phone): IGN and ENGINE START STOP buttons like a modern road car's, dark brushed metal, chrome bezels, glass caps, white text; state by light only (IGN amber, START red ready / green running), no label under IGN; same functions as the DASH ignition card (owner, 9 November 2026, from three rounds of PNG mockups).
- Page arrows on the phone pages only (GEAR, BOOST, GRIP, STARTUP, round again): faint chevrons in the bottom left and right corner; HOME, DASH and ANALYSIS are not in the cycle (owner, 9 November 2026).
- Settings button: same size and place on every page, top right. Home page `/Racing_Dashboard` (the PC also serves flight sim dashboards on the same address and port). On a tablet in landscape every page starts 26 px lower (`--top-gap`).
- DASH (iPad): cards, same layout for every car of a game; greyed cards for what a car lacks; values read back from the game; TC / ABS / ESC amber while active; warning lamps as colours only. TYRES like the ACE HUD (no legend, no compound, brake bar full height, colour only). ACE: IGNITION held, WIPERS as a latch, engine map from 1, PERFORMANCE (not DRIVE MODE), no key on Comma (voice chat mute).
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)): map left with BACK and the cursor; tabs REVIEW first, GRAPHS, TRAINER; green best, blue last, red now; every new best offered, never saved without a tap; a pause stops the lap time; no pro / reference laps.
- AI TRAINER ([TRAINER.md](TRAINER.md)): only on a tap; Claude / ChatGPT / Gemini / Ollama with the owner's key kept on the PC; FAST / BEST (Claude: Haiku 5.5 medium / Opus 5.5 high); facts computed by the bridge; up to 9 tips, category first, no summary; English; last 5 answers kept.

## Working with the owner

- Short messages, mostly English, sometimes German, often with typos; reply short and plain in their language.
- **Commit and push only when the owner says so**; commit to `main`, end commit messages with the Co-Authored-By line. The only other branch is one work-in-progress branch for a prototype the owner has not approved yet.
- For visual changes: **show PNG mockups first**, then build. For bigger features a short interview first (3–4 multiple-choice questions).
- Keep README, SPEC, the game notes, TRAINER and tests in step with every change; no personal data in commits; no emoji in the UI. **Never ask for or handle the owner's API key.**
- Check against the game with the tools above before changing code, and write what the game really sends into its NOTES (field table and "To check" list). Before the session ends, write a handover for the next session (cloud or local) in this file.
