# Racing-Dashboard

A universal dashboard for PC racing games on your phone and tablet. A small Python bridge on the gaming PC reads the game's live data and serves web pages on the local network. Open them on an iPhone, iPad or any device with a browser. The pages look the same for every game; the game (the "connector") is chosen in the settings.

- **GEAR + REV** (`/gear`), for a phone, portrait or landscape: a huge gear and the shift lights. Two styles, **CLASSIC** (LED strip and big gear) and **BAR** (gear box and RPM bar), switched with the small style button.
- **DASH** (`/dash`), for a tablet: gear, RPM, speed, TC, ABS, brake bias, engine map, fuel, position and lap times, plus four tabs of buttons that are sent to the game as keypresses: **AIDS**, **CAR**, **VIEW** and **PIT**.

Every device can open every page. The live data streams at up to 60 updates per second; the rate is chosen per device in the settings.

**Games:** Assetto Corsa EVO (PC) and a **Demo** game, a simulated car for trying the pages without a game. More games can be added as one folder each, see [docs/SPEC.md](docs/SPEC.md).

**Status:** the bridge, the pages and the demo game are built and tested. The ACE connector is built from Kunos' shared memory documentation and tested against a simulated shared memory, not yet in the game. The ACE keyboard defaults could not be confirmed, so check the keys once in the game, see [ACE keys](#ace-keys).

## Requirements

- Windows PC with the game; Python 3.12 or newer (standard library only, no packages)
- Phone or tablet in the same network as the PC (iOS 16 or newer, or a current Chrome)

## Getting started

1. **Python.** Run `python --version` in a command prompt; it must show 3.12 or newer. Otherwise install Python from [python.org](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. **This repo.** Download it with **Code → Download ZIP** and unzip it, or clone it with git.
3. **Run.** Double-click `start_dashboard.bat` (or run `python core\server.py`). It prints the address, for example `http://<PC address>:8080`. If Windows asks to allow Python on the network, allow it for private networks.
4. **Phone / tablet.** Open the address in the browser and choose a page, or open `/gear` or `/dash` directly. To run it full screen: Share → **Add to Home Screen**.
5. **Game.** Start Assetto Corsa EVO and drive; the pages follow as soon as the car is on track. No game set-up is needed: ACE publishes its shared memory by itself.

To try it without the game, open the settings (gear button, bottom right) and choose **DEMO** under GAME.

Stop the bridge with Ctrl+C or close the window.

## Settings

The gear button at the bottom right of every page opens the settings:

| Setting | Applies to | Meaning |
| --- | --- | --- |
| PAGE | this device | HOME, GEAR + REV or DASH |
| GAME | all devices | the connector: Assetto Corsa EVO or Demo; remembered on the PC |
| UPDATE RATE | this device | 10, 20, 30 or 60 updates per second |
| SPEED | this device | KM/H or MPH |
| STYLE OF THIS PAGE | this device | e.g. CLASSIC or BAR on GEAR + REV (the half-moon button cycles them) |
| KEEP SCREEN ON | this device | uses the browser's wake lock where allowed. iOS allows it only on HTTPS, so for a phone used as a display set **Settings → Display & Brightness → Auto-Lock → Never** |
| INFO | | game, data state, car, track, frames per second, the address for other devices |

## ACE keys

The buttons are keypresses (scan codes, like a real keyboard). ACE has to be the active window on the PC; the bridge brings it to the front if needed.

The keys are in `games/ace/game.toml`. Keys marked `AC` there are defaults of the original Assetto Corsa and are probably the same in ACE. Keys marked `set` are a proposal: bind them once in ACE under **Options → Controls**. Check both and, if your ACE keys differ, put your own in `config/config.toml`:

```toml
[games.ace.keys]
tc_up = "LCtrl+T"
pit_limiter = "LCtrl+LShift+P"
```

A button without a key is greyed out. `tools/ace_probe.py` prints the live values the bridge reads from ACE, which is useful for checking the connector in the game.

## Repository

```
start_dashboard.bat       starts the bridge
core/                     the bridge, the same for every game
  server.py               entry point: reads the connector, web server, live stream, buttons
  telemetry.py            the universal data model every connector fills, and the Connector base class
  actions.py              the universal button set (groups AIDS, CAR, VIEW, PIT)
  keys.py                 keypresses (SendInput, scan codes), brings the game window to the front
  winmem.py               Windows shared memory reader for shared-memory games
  config.py, log.py       configuration and rolling log
games/                    one folder per game
  ace/                    Assetto Corsa EVO: connector.py (shared memory), game.toml (window, keys)
  demo/                   simulated car: connector.py, game.toml
ui/                       the web pages
  index.html, gear.html, dash.html    the pages
  js/rd.js, js/buttons.js             live data, widgets, styles, settings, buttons
  css/base.css                        colours and shared widgets
  styles/<page>/<style>.css           the styles of each page
config/                   config.example.toml (config.toml and settings.json are local and ignored)
docs/                     SPEC.md (the engine), ACE/NOTES.md (ACE shared memory and keys)
tests/                    python -m unittest discover tests
tools/ace_probe.py        prints the live ACE values (Windows, game running)
```
