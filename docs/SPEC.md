# Racing-Dashboard – Spec

The specification of the engine that all games share. Game notes: [ACE/NOTES.md](ACE/NOTES.md). Driving assists of all planned games: [ASSISTS.md](ASSISTS.md).

## 1. Purpose and principles

A self-made dashboard for PC racing games on a phone and a tablet. It shows the live car data (gear, RPM and shift lights first) and replaces keyboard shortcuts with touch buttons. It is an open-source hobby project; the sister project for DCS World is DCS-Dashboard, whose structure it follows.

Principles:

- **Universal.** The UI looks the same for every game. A game is a connector that translates its data into one universal model ([section 3](#3-the-universal-telemetry-model)) and maps the universal buttons ([section 4](#4-buttons)) to its keys. The game is chosen in the settings.
- **Keep it simple.** Python standard library only, plain HTML, CSS and JavaScript (no framework, no build step, no external files).
- **Adaptable pages.** Pages are small HTML files that use shared building blocks; each page can have several styles, one CSS file each, cycled on the device.
- **Not every edge case is handled:** a lost packet or a crash is fine, a restart fixes it. A connector error never stops the bridge.
- Public repo: no personal data in code, docs, logs or commits; everything machine-specific lives in the ignored `config/config.toml`.

### Fixed decisions

| Topic | Decision |
| --- | --- |
| First game | Assetto Corsa EVO on PC (shared memory) |
| Platform | Windows PC with the game, Python 3.12 or newer; devices in the same local network, no login |
| Pages | GEAR + REV (phone: 14-segment gear and 8 rev lights), DASH (tablet); every device can open every page |
| Live data | Server-Sent Events, rate chosen per device: 10, 20, 30 or 60 Hz (default 60) |
| Buttons | Keypresses with scan codes (SendInput); tap or hold |
| Shift lights | The game's own shift signal; the lights are scaled to the learned shift point and flash at the signal |
| Units | km/h by default, mph per device |
| Code | Public GitHub repo `Racing-Dashboard`, main branch |

## 2. Architecture

```
Game (e.g. Assetto Corsa EVO)
 └─ shared memory / UDP / ...           ▲ keypresses (SendInput, scan codes)
        │                               │
        ▼                               │
Python bridge (core/server.py)
 ├─ Connector (games/<game>/connector.py) ... read() at [telemetry] read_hz -> universal model
 ├─ State .................................. the latest frame, with a sequence number
 ├─ Web server ............................. the pages (ui/), /stream, /state, /api/*
 ├─ Buttons ................................ the connector, or a keypress to the game window
 └─ Rolling log ............................ logs/racing-dashboard.log
        ▲▼ HTTP: SSE /stream?hz=N, POST /api/command
Phone / tablet pages (ui/)
```

- **Threads.** One reader thread calls the connector at `read_hz` (60) and stores the frame; the web server answers each request in its own thread; each open page holds one `/stream` connection that sends the latest frame at the rate the page asked for (only when it changed, plus a heartbeat every second). A watchdog thread releases held keys whose release never arrived.
- **Game switch.** The GAME setting closes the old connector and loads the new one; held keys are released first. The choice is saved in `config/settings.json`.
- **Local network only.** The server listens on `[dashboard] host` / `port` (default `0.0.0.0:8080`) and prints the address at start.

## 3. The universal telemetry model

`core/telemetry.py` (`FIELDS`) is the contract between connectors and pages. A connector returns a dict with these names from `read()`, or `None` while the game is not running; missing names keep their defaults. Units are fixed:

| Field | Meaning |
| --- | --- |
| `connected`, `status` | fresh data from the game; `off` / `live` / `pause` / `replay` |
| `car`, `track` | names as the game reports them |
| `gear`, `max_gears` | −1 = R, 0 = N, 1.. forward; number of forward gears |
| `gear_mode` | selector of an automatic gearbox or an electric car: `None` (manual or unknown), `P` park, `D` drive, `S` sport, `B` regen, `L` low, `M` manual mode |
| `rpm`, `rpm_max`, `rpm_pct` | engine speed, redline, rpm as a share of the redline (0..1) |
| `shift_up`, `shift_down`, `limiter` | the game's shift signals and the rev limiter |
| `speed_kmh`, `gas`, `brake`, `clutch` | km/h; pedals 0..1 |
| `tc_level`, `tc_cut_level`, `abs_level`, `esc_level`, `engine_map`, `diff_power`, `diff_coast` | driver settings, `None` if the car has none |
| `limits` | range per stepped setting for this car, e.g. `{"tc_level": [0, 11]}` (missing = unknown) |
| `launch`, `auto_clutch` | launch control active, auto clutch assist on (`None` = not available) |
| `esc_active` | stability control working right now |
| `warn_brake`, `warn_engine`, `warn_oil`, `warn_coolant` | warning lamps as a state, no value: `None` (not reported), `off`, `cold`, `warn` (yellow), `alert` (red) |
| `tc_active`, `abs_active` | the aid is working right now |
| `brake_bias` | front share 0..1 |
| `pit_limiter`, `ignition`, `engine_running`, `lights`, `wipers` | car systems (lights / wipers are stages, 0 = off) |
| `fuel_l`, `fuel_max_l`, `fuel_per_lap_l` | litres |
| `lap`, `position`, `cars` | completed laps, position, number of cars |
| `lap_ms`, `last_ms`, `best_ms`, `delta_ms`, `lap_valid` | lap times in ms (`None` = no time), delta to best (negative = faster) |
| `flag` | `none`, `blue`, `yellow`, ... (not filled for ACE yet) |
| `error`, `error_text` | set by the core, not by a connector: `None` or an error code, and a short text for the pages ([Errors](#errors)) |

Each frame also carries `game` (the active game id).

### Errors

The pages show **E** instead of the gear when the data cannot be trusted, and a chip names the reason ("E · GAME NOT RUNNING"). The core checks every frame (`telemetry.with_error`, the same for every game) and logs each change (`data | error | ...`):

| Code | Text | When |
| --- | --- | --- |
| `no_game` | GAME NOT RUNNING | the connector finds no game (`read()` returns `None`) |
| `read_error` | CANNOT READ THE GAME | the connector raised an error |
| `bad_value` | UNEXPECTED DATA: <field> <value> | `gear`, `rpm` or `rpm_pct` missing or not a number; a value outside its possible range (`RANGES`: gear −1..20, rpm 0..25000, rpm_pct 0..1.5, speed 0..600 km/h, pedals 0..1, brake bias 0..1, fuel 0..1000 l, lap times up to 24 h); a gear that is not a whole number; NaN or infinity; rpm more than 30 % above `rpm_max`. Typical causes: a game update changed the shared memory layout, the wrong game is selected, a connector bug |
| `no_data` | NO NEW DATA FROM THE GAME | the game is running but its data does not change for `stale_s` (pause, menu, loading, setup screen) |
| `not_driving` | NOT ON TRACK | the game reports no live session (`status` `off`) |

The page adds what only it can see (`RD.errorOf` in `js/rd.js`): NO CONNECTION TO THE PC (no message for 2.5 s: Wi-Fi, PC asleep, bridge closed) and DATA FROM THE PC NOT READABLE. While there is an error the rev lights stay off. `RD.checks` takes further page checks; `RD.notices` only fill the chip: on GEAR + REV a gear above 9 shows E with "GEAR 10: THE DISPLAY SHOWS ONE DIGIT" while the rev lights keep working (the data itself is fine). The ACE connector logs the game and shared memory version when it attaches, so a layout change after a game update shows in the log.

## 4. Buttons

`core/actions.py` (`GROUPS`) is the universal button set, the same for every game:

| Group | Buttons |
| --- | --- |
| AIDS | TC − / +, ABS − / +, BB REAR / FRONT, MAP − / + |
| CAR | PIT LIMITER, LIGHTS, FLASH (hold), WIPERS, IGNITION, STARTER (hold), IND LEFT / RIGHT, HAZARDS, HORN (hold) |
| VIEW | CAMERA, HUD, MIRROR, DISPLAY PAGE, LOOK LEFT / BACK / RIGHT (hold), LEADERBOARD |
| PIT | PAUSE / ESC, AUTO SHIFT, SHIFT − / +, NEUTRAL, SAVE REPLAY |

- A **tap** button sends one keypress per touch (held `[input] tap_ms`, default 80 ms). A **hold** button presses the key on touch and releases it when the finger lifts; the watchdog releases it after `hold_max_s` (10 s) if the release never arrives.
- A button with a telemetry `field` shows its live value (TC level, brake bias, ON / OFF) and lights up while the state is on.
- A game maps an action to a key in `[keys]` of its `game.toml`; `[games.<id>.keys]` in `config/config.toml` overrides single keys. An action without a key is greyed out ("NO KEY"). Invalid keys are logged at start and their button is greyed out.
- A connector can carry out actions itself (`HANDLES` plus `handle()`); the demo game does this for all buttons.
- Keys are sent with `SendInput` and `KEYEVENTF_SCANCODE`, because games read scan codes. Input goes to the foreground window: if the game window (`[window] process` or `title`) is not in front, the bridge taps LShift (Windows lets a program change the active window only right after input), brings it to the front and waits 0.3 s. If it is not found, the button is refused with "game window not found".
- Key names: modifiers `LCtrl RCtrl LShift RShift LAlt RAlt`; `A`–`Z`, `0`–`9`, `F1`–`F12`, `Num0`–`Num9`, `NumPlus NumMinus NumMultiply NumDivide NumEnter NumDecimal`, `Esc Tab Space Enter Backspace Home End PageUp PageDown Insert Delete Up Down Left Right`, `Minus Equals LBracket RBracket Semicolon Apostrophe Grave Backslash Comma Period Slash`.

## 5. Requests

| Request | Reply |
| --- | --- |
| `GET /`, `/gear`, `/dash`, any file in `ui/` | the page or file (a path without extension gets `.html`; nothing outside `ui/`) |
| `GET /stream?hz=N` | Server-Sent Events, one `data: {frame}` per tick at N Hz (capped at `read_hz`), `retry: 1000` |
| `GET /state` | the latest frame as JSON (for polling clients, e.g. an ESP32 display) |
| `GET /api/info` | `{"game", "game_name", "games": [{"id", "name"}], "groups": [...buttons with "enabled"], "address", "hz_choices", "keys_available"}` |
| `POST /api/command` | `{"action": "tc_up"}` (tap) or `{"action": "horn", "state": "down" / "up"}` → `{"ok": true}` or HTTP 409 `{"error": ...}` |
| `POST /api/settings` | `{"game": "demo"}` → the new `/api/info`; HTTP 400 for an unknown game |

The command errors are `unknown action`, `state '...' not valid for a ... button`, `no key set for ...`, `keypresses work on Windows only` and `game window not found`; the page shows them briefly.

## 6. The pages

`ui/` holds the pages and their building blocks. Every page loads `css/base.css` and `js/rd.js` and calls `RD.start()`.

- **Binding.** An element with `data-rd="field"` shows that field, formatted by `data-fmt` (`gear`, `rpm`, `speed`, `speedunit`, `level`, `bias`, `fuel`, `onoff`, `lap`, `delta`, `position`, `fuellaps`, `pct`, `int`, `text`; more in `RD.formats`). `data-rd-on="field"` toggles the class `on` while the field is true. Rendering runs once per animation frame with the latest frame and only touches elements whose text changed.
- **Body classes** for styles: `rd-stale` (no data for 2.5 s or not connected; a "NO DATA" chip shows), `rd-shift`, `rd-limiter`, `rd-pit`, `rd-tc`, `rd-abs`.
- **Widgets.** `.rd-revlights` (`data-colors` one letter per field: `b` blue, `g` green, `y` yellow, `r` red; `data-fill` `outside` or `left`; `data-range`): rev light fields. They light over the last `range` (0.25) of the rpm share below the shift point, in pairs from the outside in (or from the left); unlit fields stay dim. At the game's `shift_up` all fields flash, on the `limiter` faster. `.rd-seg` (`data-field`, `data-fmt`) and `.rd-seg-text` (`data-text`), from `js/seg14.js`: a field or fixed text drawn as a 14-segment display in SVG (segments a–f, g1, g2, i, l and the diagonals h, j, k, m; each diagonal fills its quadrant with the same gap as on a real display); digits use the outer segments and the split middle bar, `R` = a b f e g1 g2 m, `N` = f e b c h m, `E` = a f e d g1 g2; gearbox letters `P` = a b f e g1 g2, `D` = a b c d i l, `S` = a f g1 g2 c d (the standard S, like a 5), `B` = a b c d g2 i l, `L` = f e d, `M` = f e b c h j. Format `gear`: E on errors; P when `gear_mode` is P; the letter when `gear_mode` is D, S, B or L and the car is in a forward gear (unless the device setting AUTOMATIC GEARBOX is SHOW GEAR NUMBER); else R, N or the number. Format `gearseg` also shows E for a number above 9. Widgets register in `RD.widgetInits`. `.rd-leds` (`data-count`, `data-range`): the LED shift strip. It lights over the last `range` (0.25) of the rpm share below the shift point, green, yellow, red, and flashes blue at the game's shift signal and red on the limiter. The shift point is learned per car and gear as the rpm share at which the game first signals `shift_up` (until then 0.95). `.rd-rpmbar` (with `<i class="fill">` and `<i class="mark">`): the RPM bar with the shift mark, driven by the CSS variables `--rpm` and `--shift`.
- **Styles.** `<body data-page="gear" data-styles="classic,bar">` and `<link id="rd-style">`: the style is `styles/<page>/<style>.css`. The half-moon button cycles the styles; the choice is stored per page on the device. All styles of a page share the page's markup and only arrange, show or hide its elements. Adding a style is one CSS file plus its name in `data-styles`.
- **Toolbar and settings.** Bottom right: the style button (if the page has more than one style) and the settings gear (44 px, the accepted exception to the 56 px touch size). The settings are listed in the [README](../README.md#settings).
- **Buttons** (`js/buttons.js`, DASH): built from `/api/info`, one tab per group, the chosen tab is stored on the device; pointer events, so a hold works with the finger resting on it.
- **Design rules.** Dark background, white bold labels, touch targets at least 56 px, no emoji code points (icons are inline SVG), page locked for home-screen use (no zoom, no selection, no scroll bounce). GEAR + REV works in portrait and landscape on phones; DASH is designed for 1180 × 820 landscape and fits 1024 × 768 and portrait.

### GEAR + REV

One style, **SEGMENT** (`styles/gear/segment.css`): 8 rev lights on top (blue, green, yellow, red, red, yellow, green, blue; filling from the outside in, flashing at the shift point); below, a light grey frame that runs close to the screen edges with GEAR (in segments) set into its top line, and the gear as a yellow 14-segment display at 92 % of the frame height (landscape) or width (portrait). No rpm or speed numbers. On an error the gear shows E and the chip sits in the bottom frame line ([Errors](#errors)). The settings button sits faintly inside the bottom right corner of the frame.

### DASH (dash box)

The tablet page (`dash.html`, `js/dashbox.js`, style **CARDS** `styles/dash/cards.css`): one card per setting, built from the active game's **dash map** `games/<id>/dash.toml`. The page looks the same for every car of a game and can differ between games. Header: game, car, the gear in segments, LIVE (or a red E), the settings button. Cards fill a 4 × 2 grid in landscape and 2 × 4 in portrait.

| Card type | Shows | Buttons | Map keys |
| --- | --- | --- | --- |
| `stepper` | big value (segments), range from the game (`limits`), level dots | − / + (disabled at the ends of the range) | `field`, `down`, `up` |
| `bias` | brake bias % front (segments) and a front / rear bar | ◀ FRONT / REAR ▶, holding repeats (after 0.4 s, every 0.16 s) | `field`, `front`, `rear` |
| `toggle` | a lamp with the state text (`on` / `off`), `style` `amber` (lights up) or `green` | the whole lamp, if the card has an `action`; else display only | `field`, `action`?, `on`, `off`, `style` |
| `pair` | two values side by side (e.g. differential power / coast) | none | `fields`, `labels` |
| `fuel` | litres (segments), a tank bar (yellow below 15 %, red below 7 %), laps left (or "OF n L") | none | `field`, `max`?, `per_lap`? |
| `cycle` | a stage setting (lights, wipers): a lamp with the stage (`names`, else OFF / the number), lit amber above 0 | the lamp steps to the next stage; optional second button `extra` (e.g. FLASH) | `field`, `action`, `names`?, `extra`?, `extra_label`? |
| `ignition` | OFF / ON (amber) / RUNNING (green) | the lamp toggles the ignition; START is held like a starter (disabled while the engine runs) | `field`, `running`, `action`, `starter` |
| `lamps` | warning lamps as icons, state only: grey off, blue cold, yellow warning, red alert (icons `brake`, `engine`, `oil`, `coolant`) | none | `fields`, `icons`, `labels` |

Every card has `label` and an optional `hint` (small text at the bottom, e.g. "Set in the game's assist menu"). A stepper may name an `active` field (`tc_active`, `abs_active`, `esc_active`): while it is true the digits, dots and frame turn amber. Every value is read back from the game, so the card shows what the game applied. A card **lights up** (yellow outline) after a press until the new value arrives (at most 1.2 s), and for 0.7 s whenever its value changes in the game, so a change made in the car looks the same as one made on the tablet (fuel and lamps do not light up). A card whose value is `None` (the car does not have it) is greyed out with "NOT ON THIS CAR" and takes no presses; a button whose action has no key for the game is disabled. While there is an error ([Errors](#errors)) all cards show "-" and take no presses, and the chip sits in a strip above the cards. The bridge checks the map at start (`check_dash`: known type, action and field names; a bad card is logged and left out) and serves it in `/api/info` as `dash`, with `enabled` per action.

Actions of type `hold` (`actions.py`, e.g. FLASH, START) are pressed while the finger is on the button (`/api/info` sends `kinds` per action). Landscape: 4 columns, 5 for more than 8 cards (15 cards: 5 × 3); portrait: 2 columns, 3 for more than 8 cards. Tappable lamps stay at least 56 px high.

Assetto Corsa EVO: TC, TC CUT, ABS, STABILITY, ENGINE MAP (steppers; TC, TC CUT, ABS and STABILITY amber while active), BRAKE BIAS, FUEL, DIFF (pair, shown only: ACE has no key binding for it), PIT LIMITER (toggle), LAUNCH (shown only: activated in the car by holding brake and throttle), LIGHTS (cycle + FLASH), WIPERS (cycle), IGNITION (+ START), AUTO CLUTCH (shown only: set in the game's assist menu), WARNINGS (brake, engine, oil, coolant). The demo game has the same map; its car has no stability control, warms up from cold and overheats with engine map 5.

The former tablet page with the telemetry strip and the four button tabs is now **BUTTONS** (`buttons.html`, `styles/buttons/standard.css`).

## 7. Adding a game

1. Make a folder `games/<id>/` with `game.toml` (`[game] name`, `[window] process` / `title`, `[keys]`), `connector.py` with `class Connector(telemetry.Connector)` and, for the tablet, `dash.toml` (the dash box cards, see [DASH](#dash-dash-box)).
2. `read()` returns the universal fields the game provides (or `None` while the game is not running); `open()` / `close()` attach and detach; `handle()` optional.
3. The bridge loads every folder with a `game.toml`; the game appears in the GAME setting.

Known data sources for later games: AC and ACC (shared memory `Local\acpmf_*`, ACC also UDP broadcasting), iRacing (irsdk shared memory), rFactor 2 and Le Mans Ultimate (shared memory plugin / native), Automobilista 2 and Project CARS 2 (shared memory `$pcars2$`, UDP), F1 (UDP), BeamNG (OutGauge UDP), Forza (Data Out UDP), Dirt Rally / EA WRC (UDP). `core/winmem.py` reads any Windows shared memory block.

## 8. Installation

`install.bat` runs `tools/install.ps1` (Windows PowerShell 5.1, plain ASCII, no `exit` so it can also run as `irm <raw url> | iex`). Steps: find Python 3.12+ (`py -3`, `python`, the usual install folders) or install Python 3.13 with winget (`--scope user`); use the copy the script is in, or download `main.zip` from GitHub to `%LOCALAPPDATA%\RacingDashboard` (an update removes the code folders `core ui games docs tools tests` and merges the rest with robocopy, so `config\config.toml` stays; a marker file `.installed-by-script` allows the uninstall to delete the folder); run `core/server.py --check`; add the inbound firewall rule "Racing Dashboard" (TCP `[dashboard] port`, profiles Private and Domain) with one elevated PowerShell; warn about networks set to Public and offer to switch them to Private; create Start menu entries (start, uninstall, folder) and an optional desktop shortcut. The start shortcut runs the found `python.exe` with `core\server.py` directly. `-Uninstall` removes shortcuts, the rule and (for a downloaded copy) the folder. Every change is asked first; `-Yes` accepts the defaults.

`server.py --check` loads the config and all games without starting the server and prints Python version, games, start game, port, address and `Result OK`.

## 9. Configuration

`config/config.toml` is optional; sections are merged key by key over the defaults in `core/config.py`. See `config/config.example.toml` for every key: `[dashboard]` host, port, start game; `[telemetry]` read_hz, stale_s; `[input]` tap_ms, hold_max_s; `[log]`; `[games.<id>.keys]` key overrides.

## 10. Tests

`python -m unittest discover tests`: the ACE struct layout and translation against synthetic shared memory, and a bridge smoke test with the demo game (pages, path safety, state, info, commands, stream rate). On Windows with ACE running, `python tools/ace_probe.py` prints the live values.

## 11. Future development and out of scope

Ideas: more games; more pages and styles (e.g. a round rev counter, a timing page); flags and tyre data; external displays such as an ESP32 reading `/state`; a virtual joystick (vJoy) as an alternative to keypresses, for buttons that should work while the game is not the active window.

Out of scope: multiplayer cheating aids, security beyond the local network, hardware.
