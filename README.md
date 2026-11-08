# Racing-Dashboard

A universal dashboard for PC racing games on your phone and tablet. A small Python bridge on the gaming PC reads the game's live data and serves web pages on the local network. Open them on an iPhone, iPad or any device with a browser. The pages look the same for every game; the game (the "connector") is chosen in the settings.

- **GEAR + REV** (`/gear`), for a phone, portrait or landscape: the gear as a big yellow 14-segment display in a frame, with 8 rev lights above it (blue, green, yellow from the outside, two red in the middle). The lights fill from the outside in and flash at the shift point. Cars with an automatic gearbox or electric drive show the selector letter (P, D, S, B, L) instead of the number; the settings can switch this to the gear number. When the data cannot be trusted the gear shows **E** and a small chip says why, for example *GAME NOT RUNNING*, *NO NEW DATA FROM THE GAME* (pause, menu), *NO CONNECTION TO THE PC* or *UNEXPECTED DATA: RPM -5*.
- **DASH** (`/dash`), for a tablet: the dash box. One big card per setting (TC, TC cut, ABS, stability, engine map, brake bias, fuel, differential, pit limiter, lights with flash, wipers, ignition with starter, warning lamps) that shows the value the game applied and changes it while driving with large − / + buttons. TC, ABS and stability turn amber while they work; a card lights up when its setting changes, on the tablet or in the car. The warning lamps (brake, engine, oil, coolant) show only a state: grey, blue, yellow or red. Settings a car does not have are greyed out. The cards come from a map per game (`games/<game>/dash.toml`), so the page looks the same for every car of a game.
- **BUTTONS** (`/buttons`), for a tablet: a telemetry strip and four tabs of buttons sent to the game as keypresses: **AIDS**, **CAR**, **VIEW** and **PIT**.

Every device can open every page. The live data streams at up to 60 updates per second; the rate is chosen per device in the settings.

**Games:** Assetto Corsa EVO (PC), DiRT Rally 2.0 (PC) and a **Demo** game, a simulated car for trying the pages without a game. More games can be added as one folder each, see [docs/SPEC.md](docs/SPEC.md).

**Status:** the bridge, the pages and the demo game are built and tested. The ACE connector is built from Kunos' shared memory documentation and tested against a simulated shared memory, not yet in the game. The ACE keyboard defaults could not be confirmed, so check the keys once in the game, see [ACE keys](#ace-keys).

## Requirements

- Windows PC with the game; Python 3.12 or newer (standard library only, no packages)
- Phone or tablet in the same network as the PC (iOS 16 or newer, or a current Chrome)

## Install

Choose one of the two ways. Both are run on the gaming PC and are safe to run again: that updates or repairs the installation and keeps your settings.

**A: one line (downloads the latest version).** Press Start, type `PowerShell`, open it and paste:

```powershell
irm https://raw.githubusercontent.com/AlexanderHultsch/Racing-Dashboard/main/tools/install.ps1 | iex
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

1. **Start** Racing Dashboard from the Start menu or the desktop (or double-click `start_dashboard.bat`). The window shows the address, for example `http://192.168.1.20:8080`. Keep the window open while you drive.
2. **Phone / tablet** (same Wi-Fi as the PC): open the address in the browser and choose a page, or open `/gear` or `/dash` directly. For full screen: Share → **Add to Home Screen**.
3. **Game.** Start Assetto Corsa EVO and drive; the pages follow as soon as the car is on track. ACE needs no set-up: it publishes its shared memory by itself.

No game at hand? Open the settings (gear button, bottom right) and choose **DEMO** under GAME.

**Phone cannot connect?** Check that phone and PC are in the same network, that the PC's network is *Private* (Settings → Network & internet), and run the installer again to repair the firewall rule.

Manual set-up without the installer: install Python 3.12 or newer from [python.org](https://www.python.org/downloads/) (tick **Add python.exe to PATH**) and run `python core\server.py`.

## Settings

The gear button at the bottom right of every page opens the settings:

| Setting | Applies to | Meaning |
| --- | --- | --- |
| PAGE | this device | HOME, GEAR + REV or DASH |
| GAME | all devices | the connector: Assetto Corsa EVO or Demo; remembered on the PC |
| UPDATE RATE | this device | 10, 20, 30 or 60 updates per second |
| AUTOMATIC GEARBOX | this device | SHOW D / S (the selector letter) or SHOW GEAR NUMBER, for cars with an automatic gearbox or electric drive |
| SPEED | this device | KM/H or MPH |
| STYLE OF THIS PAGE | this device | shown when a page has more than one style (the half-moon button cycles them) |
| KEEP SCREEN ON | this device | uses the browser's wake lock where allowed. iOS allows it only on HTTPS, so for a phone used as a display set **Settings → Display & Brightness → Auto-Lock → Never** |
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
  config.py, log.py       configuration and rolling log
games/                    one folder per game
  ace/                    Assetto Corsa EVO: connector.py (shared memory), game.toml (window, keys), dash.toml (dash box)
  dr2/                    DiRT Rally 2.0: connector.py (UDP telemetry), game.toml (window, keys, port), dash.toml
  demo/                   simulated car: connector.py, game.toml
ui/                       the web pages
  index.html, gear.html, dash.html, buttons.html    the pages
  icon.ico, apple-touch-icon.png      icons for the Windows shortcut and the home screen
  js/rd.js, js/buttons.js             live data, widgets, styles, settings, buttons
  js/seg14.js                         14-segment display drawn as SVG (the gear and its label)
  js/dashbox.js                       the dash box cards, built from the game's dash map
  css/base.css                        colours and shared widgets
  styles/<page>/<style>.css           the styles of each page
config/                   config.example.toml (config.toml and settings.json are local and ignored)
docs/                     SPEC.md (the engine), ACE/NOTES.md (ACE shared memory and keys)
tests/                    python -m unittest discover tests
tools/install.ps1         installer: Python, files, check, firewall, shortcuts; -Uninstall removes it
tools/ace_probe.py        prints the live ACE values (Windows, game running)
```
