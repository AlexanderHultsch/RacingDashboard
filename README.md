# Racing Dashboard

A universal dashboard for PC racing games on your phone and tablet. A small Python bridge on the gaming PC reads the game's live data and serves web pages on the local network. Open them on an iPhone, iPad or any device with a browser. The pages look the same for every game; the game (the "connector") is chosen in the settings.

- **GEAR + REV** (`/gear`), for a phone, portrait or landscape: the gear as a big yellow 14-segment display in a frame, with 8 rev lights above it and the speed small in a second frame below (blue, green, yellow from the outside, two red in the middle). The lights fill from the outside in, the two red ones at the game's shift point; then the screen inside the frame turns red, and at the rev limit it flashes bright red (the lights never flash). Always the gear number, also with an automatic gearbox or electric drive (P only for park). When the data cannot be trusted the gear shows **E** and a small chip says why, for example *GAME NOT RUNNING*, *NO NEW DATA FROM THE GAME* (pause, menu), *NO CONNECTION TO THE PC* or *UNEXPECTED DATA: RPM -5*.
- **DASH** (`/dash`), for a tablet: the dash box. One big card per setting (TC, TC cut, ABS, stability, engine map, brake bias, fuel, differential, pit limiter, lights with flash, wipers, ignition with starter, warning lamps, tyres and brakes, performance / drive mode) that shows the value the game applied and changes it while driving with large − / + buttons. TC, ABS and stability turn amber while they work; a card lights up when its setting changes, on the tablet or in the car. The warning lamps (brake, engine, oil, coolant) show only a state: grey, blue, yellow or red. Settings a car does not have are greyed out. The cards come from a map per game (`games/<game>/dash.toml`), so the page looks the same for every car of a game.
- **ANALYSIS** (`/analysis`), for a tablet in landscape: where the time goes. The bridge records every lap; the page shows the track map cut into 250 m sections on the left and graphs of one section on the right (speed, throttle, brake, steering, gear, time delta), each with three lines: **green** your best, **blue** the last lap, **red** the lap now. Always visible: the delta of the lap and of the section against your best ever and the last lap, and a strip with the delta of every section. Tap any section, while driving or afterwards. New best laps and sections wait in the REVIEW tab to SAVE or SKIP, one by one or all at once (nothing is saved without a tap, one backup kept for UNDO); the GRAPHS tab is for the deep dive. Details: [docs/ANALYSIS.md](docs/ANALYSIS.md).
  - **AI trainer**: an AI TRAINER button on the map sends the facts of the whole lap (overview) or of the zoomed section to an AI of your choice (Claude, ChatGPT, Gemini or a local Ollama model, set up in the settings with your own API key, kept on the PC) and shows up to 9 tips in a TRAINER tab: what to change, where, and how much time it is worth. The tips judge the driving against the fundamentals of fast driving (braking, brake release, apex, throttle, line, gear) and against your own best. Only on a tap; greyed out without a working connection. Details: [docs/TRAINER.md](docs/TRAINER.md).
- **BOOST** (`/boost`), for a phone, portrait or landscape: the turbo boost as a round gauge in a frame like GEAR + REV's, a red needle, a yellow arc up to the value, BAR under the hub and the value with one decimal below it in yellow 14-segment digits (like the speed on GEAR + REV); the gauge ends at the car's maximum boost. **NO TURBO** for a car without a turbo (ACE, ACR); in iRacing the manifold pressure, so below 0 the arc turns blue and the page says **VACUUM** (every car shows something); **NO DATA** in DiRT Rally 2.0, which sends no boost.
- **BUTTONS** (`/buttons`), for a tablet: a telemetry strip and four tabs of buttons sent to the game as keypresses: **AIDS**, **CAR**, **VIEW** and **PIT**.

Every device can open every page. The live data streams at up to 60 updates per second; the rate is chosen per device in the settings.

**Games:** Assetto Corsa EVO, Assetto Corsa Rally, iRacing and DiRT Rally 2.0 (all PC), and a **Demo** game, a simulated car for trying the pages without a game. Every game gets every page: gear and rev lights, its own dash box, the analysis page with the AI trainer, and the buttons. More games can be added as one folder each, see [docs/SPEC.md](docs/SPEC.md).

**Status:** in daily use with Assetto Corsa EVO (0.9.1) on an iPad and an iPhone: bridge, all pages, the dash box, the analysis page and the AI trainer. ACE has no keyboard defaults for the car controls, so bind the keys once in the game, see [ACE keys](#ace-keys). DiRT Rally 2.0, Assetto Corsa Rally and iRacing are built from their telemetry documentation and the code of other tools that read them, and tested with simulated data only (November 2026): see their notes in `docs/` for what to check on the first drive.

## Requirements

- Windows PC with the game; Python 3.12 or newer (standard library only, no packages)
- Phone or tablet in the same network as the PC (iOS 16 or newer, or a current Chrome)

## Install

Choose one of the two ways. Both are run on the gaming PC and are safe to run again: that updates or repairs the installation and keeps your settings.

**A: one line (downloads the latest version).** Press Start, type `PowerShell`, open it and paste:

```powershell
irm https://raw.githubusercontent.com/AlexanderHultsch/RacingDashboard/main/tools/install.ps1 | iex
```

**B: from the ZIP.** On GitHub click **Code → Download ZIP**, unzip it where you want to keep it, and double-click **`install.bat`**. If Windows warns about a file from the internet, choose **More info → Run anyway**.

The installer walks you through five steps and asks before it changes anything:

1. **Python.** Finds Python 3.12 or newer, or installs Python 3.13 for your user (with winget).
2. **Program files.** Way A installs to `%LOCALAPPDATA%\RacingDashboard`; way B uses the unzipped folder.
3. **Check.** Starts the dashboard once in test mode to see that everything loads.
4. **Network.** Adds a Windows firewall rule so phones and tablets can connect (one admin prompt). It warns you if your network is set to *Public*, which blocks them, and offers to switch it to *Private*.
5. **Shortcuts.** Adds Start menu entries (start, uninstall, open the folder) and, if you like, a desktop shortcut.

At the end it shows the address to open on your phone and offers to start the dashboard.

**Remove:** Start menu → Racing Dashboard → **Uninstall Racing Dashboard**. It removes the shortcuts and the firewall rule, and the program folder if way A installed it. Python stays.

Unattended options for `tools\install.ps1`: `-Yes` (accept all defaults), `-InstallDir <folder>`, `-NoShortcuts`, `-NoFirewall`, `-Uninstall`.

## Use

1. **Start** Racing Dashboard from the Start menu or the desktop (or double-click `start_dashboard.bat`). The window shows the address, for example `http://192.168.1.20:8080/Racing_Dashboard`. Keep the window open while you drive.
2. **Phone / tablet** (same Wi-Fi as the PC): open the address in the browser and choose a page, or open `/gear` or `/dash` directly. Save **`/Racing_Dashboard`** (the home page) on the tablet: Share → **Add to Home Screen** runs it full screen under the name Racing_Dashboard. The name keeps it apart from other dashboards (e.g. flight simulator ones) on the same address and port; `/` opens the same home page.
3. **Game.** Start the game and drive; the pages follow as soon as the car is on track. Assetto Corsa EVO needs no set-up: it publishes its shared memory by itself. Assetto Corsa Rally and iRacing need no set-up either. DiRT Rally 2.0 needs its UDP telemetry switched on once, see [docs/DR2/NOTES.md](docs/DR2/NOTES.md). Most games have no keyboard defaults for the car controls: bind the proposed keys once in the game (ACE: [docs/ACE/KEYS.md](docs/ACE/KEYS.md), the others in their notes).

No game at hand? Open the settings (gear button, top right) and choose **DEMO** under GAME.

**Phone cannot connect?** Check that phone and PC are in the same network, that the PC's network is *Private* (Settings → Network & internet), and run the installer again to repair the firewall rule.

Manual set-up without the installer: install Python 3.12 or newer from [python.org](https://www.python.org/downloads/) (tick **Add python.exe to PATH**) and run `python core\server.py`.

## Settings

The gear button at the top right of every page (same size and place on every page) opens the settings:

| Setting | Applies to | Meaning |
| --- | --- | --- |
| PAGE | this device | HOME, GEAR + REV, DASH, ANALYSIS, BUTTONS or BOOST |
| GAME | all devices | the connector: Assetto Corsa EVO, Assetto Corsa Rally, DiRT Rally 2.0, iRacing or Demo; remembered on the PC |
| UPDATE RATE | this device | 10, 20, 30 or 60 updates per second |
| SPEED | this device | KM/H or MPH |
| STYLE OF THIS PAGE | this device | shown when a page has more than one style (the half-moon button cycles them) |
| KEEP SCREEN ON | this device | uses the browser's wake lock where allowed. iOS allows it only on HTTPS, so for a phone used as a display set **Settings → Display & Brightness → Auto-Lock → Never** |
| AI TRAINER | all devices, kept on the PC | OFF, CLAUDE, CHATGPT, GEMINI or LOCAL (OLLAMA); the API key (stored on the PC in `config\trainer.json`, never shown again); FAST or BEST (the exact model is shown); the connection status with TEST. See [docs/TRAINER.md](docs/TRAINER.md) |
| INFO | | game, data state, car, track, frames per second, the address for other devices |

## ACE keys

The buttons are keypresses (scan codes, like a real keyboard). ACE has to be the active window on the PC; the bridge brings it to the front if needed.

ACE has no keyboard defaults for the car controls, so bind the keys once in ACE under **Options → Controls → Car**. [docs/ACE/KEYS.md](docs/ACE/KEYS.md) lists every ACE control by its exact name with the proposed key (numpad for TC / ABS / ESC / map / brake bias and lights, PageUp / PageDown for flash and starter, letters P / U / I for pit limiter, wipers and ignition; Insert, Home, Delete and End do not work in ACE), what is not needed, and what to check after binding. The same keys are set in `games/ace/game.toml`. If you bind other keys, put yours in `config/config.toml`:

```toml
[games.ace.keys]
tc_up = "Num6"
pit_limiter = "J"
```

A button without a key is greyed out. `tools/ace_probe.py` prints the live values the bridge reads from ACE, which is useful for checking the connector in the game.

## Repository

```
install.bat               the installer (runs tools/install.ps1)
start_dashboard.bat       starts the bridge
core/                     the bridge, the same for every game
  server.py               entry point: reads the connector, web server, live stream, buttons
  telemetry.py            the universal data model every connector fills, and the Connector base class
  actions.py              the universal button set (groups AIDS, CAR, VIEW, PIT)
  keys.py                 keypresses (SendInput, scan codes), brings the game window to the front
  winmem.py               Windows shared memory reader for shared-memory games
  kunos.py                the physics page shared by Kunos' games (ACE, Assetto Corsa Rally)
  recorder.py             lap recording for the analysis page: sections, attempts, files, baselines, offers
  trainer.py              the AI trainer: facts, prompt, providers (Claude, ChatGPT, Gemini, Ollama), answer checks
  config.py, log.py       configuration and rolling log
games/                    one folder per game
  ace/                    Assetto Corsa EVO: connector.py (shared memory), game.toml (window, keys), dash.toml (dash box)
  acr/                    Assetto Corsa Rally: connector.py (shared memory, ACC layout), game.toml, dash.toml
  dr2/                    DiRT Rally 2.0: connector.py (UDP telemetry), game.toml (window, keys, port), dash.toml
  iracing/                iRacing: connector.py (irsdk shared memory, session YAML), game.toml, dash.toml
  demo/                   simulated car: connector.py, game.toml
ui/                       the web pages
  index.html, gear.html, dash.html, analysis.html, buttons.html, boost.html    the pages
  icon.ico, racing-dashboard-icon.png icons for the Windows shortcut and the home screen (own name: other dashboards on the same address keep their icon)
  js/rd.js, js/buttons.js             live data, widgets, styles, settings, buttons
  js/seg14.js                         14-segment display drawn as SVG (the gear and its label)
  js/dashbox.js                       the dash box cards, built from the game's dash map
  js/analysis.js                      the analysis page: map, section strip, graphs, offers, AI trainer tab
  js/boost.js                         the boost gauge
  css/base.css                        colours and shared widgets
  styles/<page>/<style>.css           the styles of each page
config/                   config.example.toml (config.toml, settings.json and trainer.json are local and ignored)
data/                     recorded laps and baselines (JSON Lines; local, ignored by git)
docs/                     SPEC.md (the engine), ANALYSIS.md, TRAINER.md, ASSISTS.md, HANDOVER.md, notes per game (ACE/, ACR/, DR2/, IRACING/)
tests/                    python -m unittest discover tests
tools/install.ps1         installer: Python, files, check, firewall, shortcuts; -Uninstall removes it
tools/ace_probe.py        prints the live ACE values (Windows, game running); --analysis for the analysis fields
tools/analysis_check.py   checks the recorded laps and baselines in data/ (rate, gaps, lap / section times, ranges)
```
