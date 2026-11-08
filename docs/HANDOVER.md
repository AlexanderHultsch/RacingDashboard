# Handover – first test on the Windows PC

State of the project at the end of the first (cloud) session, for the next Claude session that runs on the owner's Windows PC with the game installed. Read this first, then [README.md](../README.md) and [SPEC.md](SPEC.md).

## What exists

A universal racing dashboard: a Python bridge (standard library only) on the gaming PC reads the game and serves web pages to an iPhone / iPad on the local network.

| Part | Where | State |
| --- | --- | --- |
| Bridge: web server, 10–60 Hz live stream (SSE), keypresses, game switch, data checks | `core/` | tested in a Linux sandbox; keypresses (SendInput) and window focus never run on Windows |
| Assetto Corsa EVO connector (shared memory `Local\acevo_pmf_*`) | `games/ace/` | tested only against synthetic memory; never against the game |
| DiRT Rally 2.0 connector (UDP, extradata=3) | `games/dr2/` | tested only with simulated packets |
| Demo game (simulated car) | `games/demo/` | works; use it to separate page problems from game problems |
| GEAR + REV page (phone): 14-segment gear, 8 rev lights, E on errors | `ui/gear.html`, `ui/styles/gear/segment.css`, `ui/js/seg14.js` | browser-tested (Chromium), not on a real iPhone |
| DASH page (tablet): dash box cards built from a map per game | `ui/dash.html`, `ui/js/dashbox.js`, `ui/styles/dash/cards.css`, `games/*/dash.toml` | browser-tested, not on a real iPad |
| ANALYSIS page (tablet): map with 250 m sections, graphs per section, deltas, best laps / sections to save | `core/recorder.py`, `ui/analysis.html`, `ui/js/analysis.js`, `ui/styles/analysis/standard.css` | tested with the demo car and simulated laps; ACE / DR2 analysis fields never seen in the game |
| BUTTONS page (older tab page) | `ui/buttons.html` | works, secondary |
| Installer | `install.bat`, `tools/install.ps1` | **never run** (no PowerShell in the sandbox); Windows PowerShell 5.1, ASCII only |
| Tests | `tests/` | `python -m unittest discover tests` – all passing |

## First test plan (do it in this order, one thing at a time)

1. **Tests and check:** `python -m unittest discover tests` and `python core\server.py --check` (prints games, port, address, `Result OK`).
2. **Installer:** run `install.bat`; note every warning or error. Likely trouble spots: Python detection / winget install, the elevated firewall rule (`Start-Process -Verb RunAs -EncodedCommand`), shortcut creation (WScript.Shell), robocopy exit codes. The one-line `irm ... | iex` install only works if the GitHub repo is public.
3. **Bridge + demo:** start it (`python core\server.py` or the shortcut), open `http://localhost:8080`, settings → GAME → DEMO; check GEAR + REV and DASH.
4. **Phone / tablet:** open `http://<PC address>:8080/gear` and `/dash` on the same Wi-Fi. If nothing loads: network profile Private? firewall rule "Racing Dashboard" present? port 8080 free?
5. **Assetto Corsa EVO – reading:** GAME → ASSETTO CORSA EVO, drive, and run `py tools\ace_probe.py` in a second window. Compare every value with the game (list below).
6. **Assetto Corsa EVO – buttons:** bind the keys from `games/ace/game.toml` in ACE (Options → Controls → Car), try TC + / − on the iPad, watch `logs\racing-dashboard.log` (`command | ...` / `refused | ...` lines).
7. **DiRT Rally 2.0:** enable UDP (see [DR2/NOTES.md](DR2/NOTES.md)), GAME → DIRT RALLY 2.0, drive a stage.
8. **Analysis:** open `/analysis` on the iPad, drive three laps in ACE (a stage in DR2). Check in `/state` that `lap_pos` runs 0..1, `track_length_m`, `pos_x` / `pos_y` and `steer` are filled; that the map is the track (not mirrored, not another car) and the car dot follows; that a lap ends at the line and its time matches the game; then SAVE / SKIP / UNDO. Files: `data\runs\...`, `data\baselines\...`; log lines `analysis | ...`.

## Debugging tools

- Log: `logs\racing-dashboard.log` (also in the console window). Data errors are logged on change (`data | error | ...`); the ACE connector logs the game and shared memory version when it attaches (`ace | shared memory | ...`); DR2 logs its UDP / config state (`dr2 | config | ...`).
- Raw state: `http://localhost:8080/state` (the current frame as JSON), `http://localhost:8080/api/info` (games, buttons, dash map).
- `py tools\ace_probe.py`: live ACE values five times per second.
- Force a game: settings page GAME switch, or `config/settings.json` (`{"game": "ace"}`), or `[dashboard] game` in `config/config.toml`.
- Key overrides: `[games.<id>.keys]` in `config/config.toml` (local, not committed).

## Assumptions to verify in the real games

Assetto Corsa EVO (`games/ace/connector.py`, `docs/ACE/NOTES.md`):
- Window process name `AssettoCorsaEVO.exe` (keypresses refuse with "game window not found" if wrong; check Task Manager → Details).
- Graphics struct offsets (transcribed from Kunos' ACE_SharedFileOut_Documentation_v1; physics offsets are cross-checked, graphics are not).
- `status` numbers (0 off, 1 replay, 2 live, 3 pause assumed), `rpm_percent` range (0..1 assumed).
- `electronics_is_modifiable` / min / max limit blocks really populated (cards grey out "NOT ON THIS CAR" if not; ranges come from them).
- `esc_level`, `tc_cut_level`, `diff_power/coast`, `launch_active`, `assists_state` order (auto_gear = index 0, auto_clutch = index 2; the `ace | raw` log lines show all flags by name). The gear no longer shows D for auto_gear: it is an auto-shifter, the owner wants the gear number.
- Warning lamp thresholds (coolant 50 / 108 / 118 °C, oil 135 °C, oil pressure 0.5 bar, handbrake > 5 %) and that `oil_pressure_bar`, `water_temperature_c` are filled.
- Light and wiper stages (`main_light_stage`, `wiper_level`): what each number means → names in `games/ace/dash.toml` (`names = [...]`).
- Keys: ACE has no keyboard defaults for the car tab (verified). Insert, Home, Delete and End do not work in ACE bindings (moved to P, Num9, U, I). The proposed keys and the exact ACE control names are in [ACE/KEYS.md](ACE/KEYS.md); the owner binds them, then each DASH card is checked. "Starter" assumed to work while held. Window process `AssettoCorsaEVO.exe` verified (keys were sent, none refused).

DiRT Rally 2.0 (`games/dr2/connector.py`, `docs/DR2/NOTES.md`): rpm sent as tenths or not (auto-detected from max rpm < 2000), reverse encoding (negative, or 10), stage progress 0..100 %, keys `H` / `W` / `F2` / `Esc`, port 20777 free.

## Decisions the owner made (keep them)

- Universal UI, one folder per game (`games/<id>/connector.py`, `game.toml`, `dash.toml`); UI in `ui/`; Python standard library only; commit directly to `main`.
- GEAR + REV: design "A" – yellow 14-segment digit in a light grey frame close to the screen edges, GEAR in the top line, as large as possible; 8 rev lights blue-green-yellow-red-red-yellow-green-blue, filling from the outside in, flashing at the shift point, unlit fields dim; no rpm / speed numbers; E for errors with a chip naming the reason; letters P D S B L M for automatic / electric (standard shapes, S like 5); gears above 9 show E. **No** dimmed gear with the engine off, **no** flashing gear in the pit lane.
- DASH (iPad): concept "A – cards"; the same layout for every car of a game, different per game allowed; greyed cards for what a car lacks; values always read back from the game; a card lights up after a tap and when the value changes in the game; TC / ABS / ESC amber while active; warning lamps as colours only (grey / blue / yellow / red). ACE map: TC, TC CUT, ABS, STABILITY, ENGINE MAP, BRAKE BIAS, FUEL, DIFF (display only), PIT LIMITER, LIGHTS (+ FLASH), WIPERS, IGNITION (held; + START), WARNINGS. DR2 map: STAGE TIME, STAGE, SPEED, LIGHTS, WIPERS, RECOVER (hold 1 s). After the first test the owner removed the LAUNCH card and asked for IGNITION as a hold button (ACE switches the ignition only while the key is held, for a few seconds), WIPERS as an on / off latch (ACE wipes only while the key is held), the diff locking in % for cars without diff steps, fixed settings shown as FIXED, LIGHTS / WIPERS as buttons without a state (ACE 0.9.1 does not report them), and removed the AUTO CLUTCH card (not an option for the driver).
- Workflow for UI changes: show PNG mockups first (rendered from HTML with Playwright), get feedback, then build.

## Conventions

- Plain English docs; update README / SPEC / game notes with every behaviour change; keep tests passing and add tests for new logic.
- No personal data in code, docs, logs or commits; machine settings only in the ignored `config/config.toml`.
- No emoji in the UI (icons are inline SVG).
- Analysis page: agreed strategy in [ANALYSIS.md](ANALYSIS.md), built; the owner's rules there (sections by track position, repeat rule, ask before saving, one backup) are decisions to keep.
- Ideas not built yet: tyres / brake temperature / damage cards, two-page dash box (DRIVE / CAR), names for light / wiper stages, flags (ACE enum unpublished), electric single-speed detection (ACE `engine_type` numbers unpublished), more games (see [ASSISTS.md](ASSISTS.md)).
