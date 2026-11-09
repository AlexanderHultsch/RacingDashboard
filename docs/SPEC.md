# Racing Dashboard – Spec

The specification of the engine that all games share. Game notes: Assetto Corsa EVO [ACE/NOTES.md](ACE/NOTES.md), Assetto Corsa Rally [ACR/NOTES.md](ACR/NOTES.md), DiRT Rally 2.0 [DR2/NOTES.md](DR2/NOTES.md), iRacing [IRACING/NOTES.md](IRACING/NOTES.md). Driving assists of all planned games: [ASSISTS.md](ASSISTS.md).

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
| Pages | GEAR + REV (phone: 14-segment gear and 8 rev lights), DASH and ANALYSIS (tablet), BOOST, GRIP and STARTUP (phone); every device can open every page |
| Live data | Server-Sent Events, rate chosen per device: 10, 20, 30 or 60 Hz (default 60) |
| Buttons | Keypresses with scan codes (SendInput); tap, hold or latch |
| Shift lights | The game's own shift signal; the lights are scaled to the learned shift point and flash at the signal |
| Units | km/h by default, mph per device |
| Code | Public GitHub repo `AlexanderHultsch/RacingDashboard`, main branch |

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
 ├─ Recorder (core/recorder.py) ............ laps, sections and baselines for the analysis page (data/)
 └─ Rolling log ............................ logs/racing-dashboard.log
        ▲▼ HTTP: SSE /stream?hz=N, POST /api/command
Phone / tablet pages (ui/)
```

- **Threads.** One reader thread calls the connector at `read_hz` (60) and stores the frame; the web server answers each request in its own thread; each open page holds one `/stream` connection that sends the latest frame at the rate the page asked for (only when it changed, plus a heartbeat every second). A watchdog thread releases held keys whose release never arrived.
- **Game switch.** The GAME setting closes the old connector and loads the new one; held keys are released first. The choice is saved in `config/settings.json`.
- **Local network only.** The server listens on `[dashboard] host` / `port` (default `0.0.0.0:8080`) and prints the address at start. The home page is `/Racing_Dashboard` (also `/`; any page or file can be reached under `/Racing_Dashboard/` too), the link to save on the tablet: the name keeps it apart from other dashboards on the same address and port. The home-screen icon is `ui/racing-dashboard-icon.png` (180 × 180, linked from every page), not the usual `/apple-touch-icon.png`, so a home-screen shortcut of another dashboard on the same address (e.g. a flight simulator one) keeps its own icon; the shortcut's name is `Racing_Dashboard` (`apple-mobile-web-app-title` of the home page).

## 3. The universal telemetry model

`core/telemetry.py` (`FIELDS`) is the contract between connectors and pages. A connector returns a dict with these names from `read()`, or `None` while the game is not running; missing names keep their defaults. Units are fixed:

| Field | Meaning |
| --- | --- |
| `connected`, `status` | fresh data from the game; `off` / `live` / `pause` / `replay` |
| `car`, `track` | names as the game reports them |
| `gear`, `max_gears` | −1 = R, 0 = N, 1.. forward; number of forward gears |
| `gear_mode` | selector of an automatic gearbox or an electric car: `None` (manual or unknown), `P` park, `D` drive, `S` sport, `B` regen, `L` low, `M` manual mode. The pages show the gear number whatever the mode and P only for park |
| `rpm`, `rpm_max`, `rpm_pct` | engine speed, redline, rpm as a share of the redline (0..1) |
| `shift_up`, `shift_down`, `limiter` | the game's shift signals and the rev limiter |
| `speed_kmh`, `gas`, `brake`, `clutch` | km/h; pedals 0..1 |
| `tc_level`, `tc_cut_level`, `abs_level`, `esc_level`, `engine_map`, `diff_power`, `diff_coast` | driver settings, `None` if the car has none |
| `diff_power_pct`, `diff_coast_pct` | differential locking on / off throttle as a share 0..1 (the value, not a setting step), `None` = not reported |
| `drive_mode`, `drive_mode_name` | drive / performance mode as a step (range in `limits`) and the game's name for it (e.g. `SPORT+`), `None` = not on this car |
| `tyre_temp_c`, `tyre_psi`, `brake_temp_c` | tyre temperatures (C), pressures (psi) and brake temperatures (C) as lists [front left, front right, rear left, rear right], `None` = not reported |
| `tyre_core_score`, `tyre_surface_score` | the game's own judgement of each tyre's temperature, same order, 1 = fine up to 2 = too hot: the core (goes with `tyre_temp_c`) and the tread surface (the hottest of inner / middle / outer); ACE `tyre_normalized_temperature_core` and `_left / _center / _right`; `None` = not reported |
| `limits` | range per stepped setting for this car, e.g. `{"tc_level": [0, 11]}` (missing = unknown) |
| `latched` | set by the bridge: latch actions whose key is held down right now, e.g. `["wipers"]` |
| `fixed` | stepped settings the car has but the driver cannot change, e.g. `["abs_level"]`: the card shows the value with FIXED and no − / + |
| `esc_active` | stability control working right now |
| `warn_brake`, `warn_engine`, `warn_oil`, `warn_coolant` | warning lamps as a state, no value: `None` (not reported), `off`, `cold`, `warn` (yellow), `alert` (red) |
| `tc_active`, `abs_active` | the aid is working right now |
| `brake_bias` | front share 0..1 |
| `pit_limiter`, `ignition`, `engine_running`, `lights`, `wipers` | car systems (lights / wipers are stages, 0 = off) |
| `fuel_l`, `fuel_max_l`, `fuel_per_lap_l` | litres |
| `lap`, `position`, `cars` | completed laps, position, number of cars |
| `lap_progress` | share of the lap / stage driven, 0..1 |
| `lap_pos`, `track_length_m` | position on the lap along the track, 0..1 (the game's normalised position, not the driven distance), and the track / stage length in metres: the analysis sections |
| `pos_x`, `pos_y` | car position on the map in metres (game world seen from above) |
| `steer` | steering −1 (full left) .. 1 (full right) |
| `session_id` | changes when a new game session starts (a new analysis run) |
| `air_c`, `road_c`, `tyre_compound`, `time_of_day` | ambient values, written once per lap |
| `lap_ms`, `last_ms`, `best_ms`, `delta_ms`, `lap_valid` | lap times in ms (`None` = no time), delta to best (negative = faster) |
| `boost_bar`, `boost_min_bar`, `boost_max_bar` | boost page: boost above the air pressure in bar (negative = vacuum, 0 for a car without a turbo: no check whether a car has one, `None` = the game sends none), the lowest value the game sends (iRacing −1, else 0) and the car's maximum boost (`None` = unknown). No range check: an odd boost value must not stop the other pages with E. ACE: graphics `turbo_boost` in bar (physics `turboBoost` as a fallback); `max_turbo_boost` is not used (0 in the M4 GT3 Evo, 157.4 in the Camaro ZL1), ACR: physics `turboBoost` and static `maxTurboBoost` (`kunos.boost`); iRacing: `ManifoldPress` − 1.013 bar; DR2: none |
| `wheel_slip`, `wheel_lock` | grip page: the slip ratio of each wheel [front left, front right, rear left, rear right] (0 = rolling with the car, negative = slower: braking, −1 = stopped; positive = faster: wheelspin; capped −1..3; `None` = the game sends none) and the game's own lock flag per wheel (`None` = the game has none). No range check. ACE: physics `slipRatio` (`kunos.slips`, `None` while all 0) and graphics `tyre_*.lock`; ACR: physics `slipRatio`, no lock flag; DR2: the wheel speeds against the car's speed (at least 3 m/s); iRacing: none (no slip per wheel in the live data); demo: simulated |
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

`core/actions.py` (`ACTIONS`) is the universal set of actions the dash box cards send, the same for every game, each with its usual type: TC − / +, TC CUT − / +, ABS − / +, ESC − / +, brake bias rear / front, engine map − / +, drive mode − / +, pit limiter, lights, flash (hold), wipers, ignition (hold), starter (hold), recover. The buttons are on the DASH page ([section 6](#dash-dash-box)); the former BUTTONS page (camera, view, indicators, horn, shifting, pause) was removed on 10 November 2026.

- A **tap** button sends one keypress per touch (held `[input] tap_ms`, default 80 ms). A **hold** button presses the key on touch and releases it when the finger lifts; the watchdog releases it after `hold_max_s` (10 s) if the release never arrives.
- A game can change how a button sends its key in `[kinds]` of its `game.toml` (`tap`, `hold`, or `latch`: one tap presses the key and keeps it down, the next tap lets it go, with no time limit; for games that act only while a key is held, e.g. ACE wipers). The bridge reports the latched actions in the frame (`latched`); the pages show such a button ON while its key is down. `[games.<id>.kinds]` in `config/config.toml` overrides single kinds; unknown actions or kinds are logged and ignored.
- A game maps an action to a key in `[keys]` of its `game.toml`; `[games.<id>.keys]` in `config/config.toml` overrides single keys. An action without a key is greyed out ("NO KEY"). Invalid keys are logged at start and their button is greyed out.
- A connector can carry out actions itself (`HANDLES` plus `handle()`); the demo game does this for all actions.
- Keys are sent with `SendInput` and `KEYEVENTF_SCANCODE`, because games read scan codes. Input goes to the foreground window: if the game window (`[window] process` or `title`) is not in front, the bridge taps LShift (Windows lets a program change the active window only right after input), brings it to the front and waits 0.3 s. If it is not found, the button is refused with "game window not found".
- Key names: modifiers `LCtrl RCtrl LShift RShift LAlt RAlt`; `A`–`Z`, `0`–`9`, `F1`–`F12`, `Num0`–`Num9`, `NumPlus NumMinus NumMultiply NumDivide NumEnter NumDecimal`, `Esc Tab Space Enter Backspace Home End PageUp PageDown Insert Delete Up Down Left Right`, `Minus Equals LBracket RBracket Semicolon Apostrophe Grave Backslash Comma Period Slash`.

## 5. Requests

| Request | Reply |
| --- | --- |
| `GET /`, `/gear`, `/dash`, `/analysis`, `/boost`, `/grip`, `/startup` (also `/Startup`), any file in `ui/` | the page or file (a path without extension gets `.html`, a page name in any case is found in lower case; nothing outside `ui/`) |
| `GET /stream?hz=N` | Server-Sent Events, one `data: {frame}` per tick at N Hz (capped at `read_hz`), `retry: 1000` |
| `GET /state` | the latest frame as JSON (for polling clients, e.g. an ESP32 display) |
| `GET /api/info` | `{"game", "game_name", "games": [{"id", "name"}], "dash": [...cards with "enabled" and "kinds" per action], "address", "hz_choices", "keys_available"}` |
| `POST /api/command` | `{"action": "tc_up"}` (tap) or `{"action": "starter", "state": "down" / "up"}` → `{"ok": true}` or HTTP 409 `{"error": ...}` |
| `POST /api/settings` | `{"game": "demo"}` → the new `/api/info`; HTTP 400 for an unknown game |
| `GET /api/analysis` | the analysis state: `version`, `active`, game / car / track, `track_length_m`, `section_m`, `sections`, `outline` ([x, y, p] every 5 m), `borders` ([x, y, nx, ny] per section start), `lines` (`best`, `last` as [x, y]), `red_lap`, `blue_lap`, `base_lap`, `offers`, `undo`, `ended` |
| `GET /api/analysis/live?since=k` | `version`, `recording`, `sec` (current section), `deltas` (`lap_best`, `lap_last`, `sec_best`, `sec_last`, `lap_time`), `strip` (per section `best`, `last`, `attempts`, `old`), `why` (why nothing is recorded), `last_lap`, the red line from point k (`now_from`, `now_line`), `offers` (count) |
| `GET /api/analysis/section?n=` | one section (0-based): `best`, `last`, `now` as rows [d, t, v, thr, brk, str, g, x, y, tc_on, abs_on, esc_on, tc, tc_cut, abs, esc, engine_map, rpm] (d metres and t seconds from the section start; aids and rpm null where not recorded), their times, `now_attempt` |
| `GET /api/trainer` | AI trainer status: `provider`, `level`, `model`, `models`, `keys` (hints only, never a key), `ok`, `state`, `error`, `detail`, `checked`, `ms`, `history` (the last 5 answers) |
| `POST /api/trainer/ask` | `{"mode": "track" / "section", "section": 4}` → `{"entry", "trainer"}` after the AI answered; HTTP 409 `{"error", "detail"}` when it failed; `/settings` `{"provider", "level", "key", "key_for"}` and `/test` → the status ([TRAINER.md](TRAINER.md)) |
| `POST /api/analysis/offer` | `{"id": 3, "save": true}` SAVE or SKIP one offer → the analysis state; `/save-all`, `/skip-all`, `/undo`, `/end` (END RUN), `/finish` `{"keep": "all" / "baselines"}` (end-of-run menu); HTTP 409 when not possible, 404 with `[analysis] enabled = false` |

The command errors are `unknown action`, `state '...' not valid for a ... button`, `no key set for ...`, `keypresses work on Windows only` and `game window not found`; the page shows them briefly.

## 6. The pages

`ui/` holds the pages and their building blocks. Every page loads `css/base.css` and `js/rd.js` and calls `RD.start()`.

- **Page updates.** Every frame carries `ui`, the newest change time of the files in `ui/`; an open page reloads itself when it changes (after an update and a restart of the bridge), so a phone or tablet left open always runs the current pages.
- **Binding.** An element with `data-rd="field"` shows that field, formatted by `data-fmt` (`gear`, `gearseg`, `speed`, `speedunit`, `bias`, `fuel`, `lap`, `text`; `RD.formats`). `data-rd-on="field"` toggles the class `on` while the field is true. Rendering runs once per animation frame with the latest frame and only touches elements whose text changed.
- **Body classes** for styles: `rd-stale` (no data for 2.5 s or not connected; a "NO DATA" chip shows), `rd-shift`, `rd-limiter`, `rd-pit`, `rd-tc`, `rd-abs`.
- **Widgets.** `.rd-revlights` (`data-colors` one letter per field: `b` blue, `g` green, `y` yellow, `r` red; `data-fill` `outside` or `left`; `data-range`): rev light fields. The scale ends at the game's shift point (learned from its shift signal per gear) and is `range` wide (0.12: from 88 % of it), in pairs from the outside in (or from the left); unlit fields stay dim. (A scale moved 3 % below the shift point was tried and dropped: it did not fit every car.) The innermost (red) pair lights only at the game's `shift_up` (or at the learned shift point); at the shift signal and on the `limiter` all fields are lit, **steady: the rev lights never flash** (owner, November 2026); the red fields lit set the body class `rd-redzone`. `.rd-seg` (`data-field`, `data-fmt`) and `.rd-seg-text` (`data-text`), from `js/seg14.js`: a field or fixed text drawn as a 14-segment display in SVG (segments a–f, g1, g2, i, l and the diagonals h, j, k, m; each diagonal fills its quadrant with the same gap as on a real display); digits use the outer segments and the split middle bar, `R` = a b f e g1 g2 m, `N` = f e b c h m, `E` = a f e d g1 g2; gearbox letters `P` = a b f e g1 g2, `D` = a b c d i l, `S` = a f g1 g2 c d (the standard S, like a 5), `B` = a b c d g2 i l, `L` = f e d, `M` = f e b c h j. Format `gear`: E on errors; P when `gear_mode` is P; else R, N or the number (always the number with an automatic gearbox or electric drive, the owner's decision; the other letters stay in the glyph table). Format `gearseg` also shows E for a number above 9. Widgets register in `RD.widgetInits`.
- **Styles.** `<body data-page="gear" data-styles="segment">` (one or more styles, comma-separated) and `<link id="rd-style">`: the style is `styles/<page>/<style>.css`. The half-moon button cycles the styles; the choice is stored per page on the device. All styles of a page share the page's markup and only arrange, show or hide its elements. Adding a style is one CSS file plus its name in `data-styles`.
- **Toolbar and settings.** Top right, the same size and place on every page (`base.css`: 6 px + the top gap from the top, 10 px from the right; DASH and ANALYSIS keep that corner of their header free, the GEAR + REV rev lights leave 54 px at both ends): the style button (if the page has more than one style) and the settings gear (44 px, the accepted exception to the 56 px touch size). `--top-gap` (`base.css`) is 26 px in landscape on a tablet (height 600 px or more: the iPad screen fades at its top edge) and 0 otherwise; pages and the settings overlay start that much lower. The settings overlay has 16 px padding on every side plus the top gap. The settings are listed in the [README](../README.md#settings).
- **Page arrows.** The phone pages cycle in the order GEAR + REV, BOOST, GRIP, STARTUP and round again (`RD.CYCLE` in `rd.js`, owner, 9 November 2026): a thin white chevron at 32 % opacity in the bottom left (previous) and bottom right (next) corner, a 56 × 80 px touch area, brighter while pressed (`.rd-arrow` in `base.css`). HOME, DASH and ANALYSIS have none.
- **Design rules.** Dark background, white bold labels, touch targets at least 56 px, no emoji code points (icons are inline SVG), page locked for home-screen use (no zoom, no selection, no scroll bounce). GEAR + REV works in portrait and landscape on phones; DASH is designed for 1180 × 820 landscape and fits 1024 × 768 and portrait.

### GEAR + REV

One style, **SEGMENT** (`styles/gear/segment.css`): 8 rev lights on top (blue, green, yellow, red, red, yellow, green, blue; filling from the outside in, the red pair at the shift point, never flashing); below, a light grey frame that runs close to the screen edges with GEAR (in segments) set into its top line, and the gear as a yellow 14-segment display at 92 % of the frame height (landscape) or width (portrait). Below it a second frame of the same width and style with SPEED (same label size as GEAR) in its top line and the speed in small segments (km/h or mph as set on the device, no unit shown; for info). In landscape on a phone the gear frame gives up height for it (the gear about 20 % smaller); in portrait the gear keeps its size. No rpm number. On an error the gear shows E and the chip sits in the bottom frame line ([Errors](#errors)). The screen inside the frame turns dark red while the red rev lights are lit (the game's shift point; body class `rd-redzone`, set by the rev lights) and bright red, flashing, on the game's rev limiter signal (`rd-maxrev`; an own estimate from the maximum rpm flashed too early in some cars and was dropped); the rev lights themselves are unchanged. The settings button sits faintly in the top right corner, beside the rev lights. The gear is always the number (also with an automatic gearbox or electric drive; P for park), as the owner decided.

### BOOST

One style, **GAUGE** (`styles/boost/gauge.css`, drawn by `js/boost.js`): a light grey frame like GEAR + REV's with BOOST (in segments) in its top line and a round gauge as large as the frame allows. The dial runs over 270 degrees from `boost_min_bar` (iRacing −1, else 0) to the car's `boost_max_bar` rounded up to 0.5 bar (2 bar when unknown, at least 1); it grows when the boost goes higher and resets when the car changes. It never goes past 5 bar: a larger maximum or boost value is taken as wrong and ignored (the ACE Camaro ZL1 sends a maximum of 157). Ticks every 0.5 bar (every 1 bar above a 3 bar range) with numbers, minor ticks between. A red needle, a yellow arc from 0 up to the value (blue from the value up to 0 when below 0, on a faint blue vacuum zone), below the hub BAR, or VACUUM below 0, and in the open bottom of the dial the value with one decimal in yellow segments, in the style of the SPEED number on GEAR + REV (same size, no glow; owner, 10 November 2026). The gauge is always fully drawn (owner, 9 November 2026): without a value (a car without a turbo sends 0, DR2 sends none, an error) the needle and the number stay at 0; the chip says "<GAME> SENDS NO BOOST" when the game sends none, or why the data is not usable. The segment font has O, T, U, C, V (BOOST, VACUUM).

### GRIP

One style, **TILES** (`styles/grip/tiles.css`, drawn by `js/grip.js`): a light grey frame like the gear and boost pages with GRIP (in segments) in its top line; in portrait a compact box in the middle of the screen (not stretched to the top and bottom), in landscape the whole screen. Inside, four tyre tiles laid out like the car (front on top), colour only, no text (owner, 10 November 2026). A tile's stage comes from the slip ratio of its wheel: 1 from 4 %, 2 from 7 %, 3 from 15 %, 4 from 40 % or when the game's lock flag is set (`STAGES` in `js/grip.js`, the same for every car; owner, 9 November 2026, after a drive in the ACE BMW M4 GT3 Evo, where ABS and TC start to work at 6–7 % slip: stage 2 is that limit). Braking (negative slip) runs yellow `#e6c619`, orange `#f08a1c`, red `#e5412f`, bright red `#ff1414`; wheelspin light blue `#8fa8ff`, blue-violet `#6f5cff`, purple `#a83cf0`, magenta `#e02ce6`; dark grey while the tyre grips. **Stage 4 flashes** bright (with a glow) and dark, 0.3 s each, and comes and goes at once. Calm colours for stages 1–3 (owner, 9 November 2026): a colour fades in over 0.15 s, up and down; a stage stays at least 0.3 s (counted from the last moment the slip was that high) before it steps down, one stage at a time; going up, or to the other side at the same stage, is at once (`RD.gripCalm` in `js/grip.js`). No colour below 10 km/h (the slip of a standing car means nothing) and none on an error (the tiles dim). Between the front tyres ABS and between the rear tyres TC: the selected setting only, white, no colour, no flashing; 0 shows OFF, `None` a grey –; hidden when the game reports no such setting (its dash map has no card with `abs_level` / `tc_level`, so DR2 shows none). A game without wheel slip (iRacing) leaves the tiles dim and the chip says "<GAME> SENDS NO WHEEL SLIP". The segment font has I for GRIP.

### STARTUP

One style, **METAL** (`styles/startup/metal.css`, driven by `js/startup.js`), chosen by the owner from PNG mockups (9 November 2026): the whole screen is a dark brushed metal plate with two round buttons like a modern road car's start button, side by side in landscape, IGN above START in portrait. Each button is built from layers: a cut-out in the plate with a shadow, a polished outer chamfer, a machined chrome face with turning grooves, a wall down to a smoked light ring lit from behind, and a domed black glass cap with a soft reflection. The text (IGN; ENGINE START STOP) is white; it glows when the ring is lit. No label under the buttons, no state text: the state is light only. IGN: amber ring with the ignition on (or the engine running). START: red ring with the ignition on (ready), green while the engine runs. A pressed cap goes in a little and darkens. The buttons send the same actions as the DASH ignition card, found in the game's dash map (`/api/info`): the card with the `ignition` action and the one with `starter` (ACE and demo: the ignition card; ACR, iRacing: push cards), with their kind (a hold action is pressed while the finger is on the button, a tap is one keypress) and whether a key is set (without one the button's text is grey and it does nothing). The state comes from that ignition card's `field` and `running` (else `ignition`, `engine_running`). While the engine runs START does nothing (as on the DASH); on an error both rings are dark and the buttons send nothing.

### DASH (dash box)

The tablet page (`dash.html`, `js/dashbox.js`, style **CARDS** `styles/dash/cards.css`): one card per setting, built from the active game's **dash map** `games/<id>/dash.toml`. The page looks the same for every car of a game and can differ between games. Header: game, car, the gear in segments, LIVE (or a red E), the settings button. Cards fill a 4 × 2 grid in landscape and 2 × 4 in portrait.

| Card type | Shows | Buttons | Map keys |
| --- | --- | --- | --- |
| `stepper` | big value (segments), range from the game (`limits`), level dots; FIXED instead of the range for a setting in `fixed` | − / + (disabled at the ends of the range, and for a fixed setting) | `field`, `down`, `up` |
| `mode` | a drive / performance mode: the game's name for it in big letters (else MODE n), one dot per mode, the range counted from 1 | − / + as a stepper | `field`, `name`, `down`, `up` |
| `tyres` | laid out like the car, as the ACE HUD (front left / right, rear left / right): a tile per tyre with its temperature; the pressure in psi above the fronts and below the rears; the brake as a full-height bar on the inner side of each tyre; with the game's scores (`core_score`, `surface_score`) the tile is coloured by the core score and a frame around it by the surface score, exactly like the ACE HUD (1.0 green, 1.5 yellow, 1.75 orange, 2.0 red; a thin dark gap between frame and tile; without the scores the tile follows `scale` and the frame stays dark grey); tile and bar coloured along a scale `[blue, green from, green to, red]`: blue, light blue, green (the window), yellow, orange, red, mixed in between (tyres `[50, 80, 100, 130]`, brakes `[100, 300, 650, 900]` C); dark digits on light colours; no legend | none | `field`, `pressure`, `core_score`, `surface_score`, `brakes`, `scale`, `brake_scale` |
| `bias` | brake bias % front (segments) and a front / rear bar | ◀ FRONT / REAR ▶, holding repeats (after 0.4 s, every 0.16 s) | `field`, `front`, `rear` |
| `toggle` | a lamp with the state text (`on` / `off`), `style` `amber` (lights up) or `green` | the whole lamp, if the card has an `action`; else display only | `field`, `action`?, `on`, `off`, `style` |
| `pair` | two values side by side (e.g. differential power / coast); with `alt` the alt fields are shown in % (labels `alt_labels`) when none of the main fields has a value | none | `fields`, `labels`, `alt`, `alt_labels` |
| `fuel` | litres (segments), a tank bar (yellow below 15 %, red below 7 %), laps left (or "OF n L") | none | `field`, `max`?, `per_lap`? |
| `cycle` | a stage setting (lights, wipers): a lamp with the stage (`names`, else OFF / the number), lit amber above 0. When the game does not report the stage but the action has a key, the card stays usable and shows – (for a `latch` action ON / OFF for the held key instead) | the lamp steps to the next stage; optional second button `extra` (e.g. FLASH) | `field`, `action`, `names`?, `extra`?, `extra_label`? |
| `ignition` | OFF / ON (amber) / RUNNING (green) | the lamp sends the ignition action as a hold (the key stays down while the finger is on it, so a short touch is a tap; ACE needs it held a few seconds); START is held like a starter (disabled while the engine runs) | `field`, `running`, `action`, `starter` |
| `value` | a value in segments (`fmt` `lap` time, `pct`, `speed` with the device's unit, `int`), optional bar for a 0..1 share | none | `field`, `fmt`, `bar`? |
| `push` | a big button without a state | the button; with `confirm_ms` it fires only after being held that long (a fill shows the progress); a `hold` action (e.g. a starter) is pressed as long as the finger is on it | `action`, `text`?, `confirm_ms`? |
| `lamps` | warning lamps as icons, state only: grey off, blue cold, yellow warning, red alert (icons `brake`, `engine`, `oil`, `coolant`) | none | `fields`, `icons`, `labels` |

Every card has `label` and an optional `hint` (small text at the bottom); the maps of ACE, DiRT Rally 2.0 and the demo use no hints (the owner removed them). A stepper may name an `active` field (`tc_active`, `abs_active`, `esc_active`): while it is true the digits, dots and frame turn amber. Every value is read back from the game, so the card shows what the game applied. A card **lights up** (yellow outline) after a press until the new value arrives (at most 1.2 s), and for 0.7 s whenever its value changes in the game, so a change made in the car looks the same as one made on the tablet (fuel and lamps do not light up). A card whose value is `None` (the car does not have it) is greyed out with "NOT ON THIS CAR" and takes no presses; a button whose action has no key for the game is disabled. While there is an error ([Errors](#errors)) all cards show "-" and take no presses, and the chip sits in a strip above the cards. The bridge checks the map at start (`check_dash`: known type, action and field names; a bad card is logged and left out) and serves it in `/api/info` as `dash`, with `enabled` per action.

Actions of type `hold` (`actions.py`, e.g. FLASH, START) are pressed while the finger is on the button (`/api/info` sends `kinds` per action). In landscape the page starts 26 px (about 5 mm on an iPad) lower, because the top edge of the iPad screen fades into its frame (`--top-gap` in `styles/dash/cards.css`). Landscape: 3 columns for up to 6 cards, 4 up to 8, 5 for more (15 cards: 5 × 3); portrait: 2 columns, 3 for more than 8 cards. Tappable lamps stay at least 56 px high.

Assetto Corsa EVO: TC, TC CUT, ABS, STABILITY, ENGINE MAP (steppers; TC, TC CUT, ABS and STABILITY amber while active), BRAKE BIAS, FUEL, DIFF (pair, shown only: the setting steps, or the locking in % for a car without steps, e.g. the BMW M4 CSL: POWER 25, COAST 55), PIT LIMITER (toggle), LIGHTS (cycle + FLASH), WIPERS (cycle), IGNITION (+ START), WARNINGS (brake, engine, oil, coolant). DiRT Rally 2.0 has its own map ([DR2/NOTES.md](DR2/NOTES.md)): STAGE TIME, STAGE, SPEED, LIGHTS, WIPERS, RECOVER (held 1 s). Assetto Corsa Rally ([ACR/NOTES.md](ACR/NOTES.md)): TC, ABS, BRAKE BIAS, STAGE TIME, STAGE, SPEED, LIGHTS, WIPERS, ENGINE (start / stop), RECOVER (held 1 s). iRacing ([IRACING/NOTES.md](IRACING/NOTES.md)): TC, TC 2, ABS, ENGINE MAP, BRAKE BIAS, FUEL, PIT LIMITER, IGNITION, STARTER (held), FLASH (held), WIPERS, WARNINGS. The demo game has the same map as Assetto Corsa EVO; its car has no stability control, warms up from cold and overheats with engine map 5.

### ANALYSIS

The tablet page for learning (`analysis.html`, `js/analysis.js`, style **STANDARD** `styles/analysis/standard.css`), agreed in [ANALYSIS.md](ANALYSIS.md). Header: game, car, track, lap, the last lap's time (with OUT LAP, INVALID, INTERRUPTED or REPEATED when it does not count), and while nothing is recorded the reason (GAME PAUSED, REPLAY, NOT ON TRACK, the game's error, STAGE FINISHED, ...); LIVE, END RUN (tap twice), settings. In landscape the page starts 26 px lower (the iPad screen fades at its top edge), as DASH. Below it four deltas, always visible: lap vs best ever, lap vs last, section vs best, section vs last (red = slower, green = faster). Left: the map (canvas) with the track outline from the best lap (else from the last lap or the lap in progress, whichever covers more of the track: a first lap from the pit box may be only a few metres), the section borders and numbers, the selected section highlighted, the full-lap lines (green best lap, blue last lap, red the lap now) and the car; tapping a section zooms into it with the three lines of that section, BACK (top left, only while zoomed) returns to the overview. Dragging along the track sets a cursor: a yellow ring on the map, a yellow line through all graphs with the metres in a chip on the axis; in the overview the graphs switch section as the finger crosses a border, in a section the cursor stays in it; the lines after the cursor are faded (28 %), all best / last / now lines are drawn at 80 % opacity; LIVE, the strip and the offers clear the cursor. Under the map the section strip (BEST and LAST row per section, horizontally scrollable with a slider; ↻ marks a repeated section); sections the lap in progress has not reached yet show the last lap's values, dimmed; tapping a cell opens that section. While the game is paused red stays the lap in progress and blue the last lap (the owner looks at the lap while paused); between laps and after the run red is the last complete lap and blue the one before. The delta to the last lap needs a clean last lap (not an out lap, not interrupted, nothing repeated); it need not be valid. Right: two tabs. **REVIEW** (the start view, because new best laps and sections come often, above all at the beginning): the open offers with SAVE / SKIP, SAVE ALL and SKIP ALL (tap twice: skipped offers cannot be brought back), UNDO for the last save, the number of open offers on the tab; tapping an offer opens its section in GRAPHS. **GRAPHS** (for a deep dive): graphs over the metres in the selected section, each with its title in a band above the plot, **4 per page**, scrolled vertically with a snap per page and dots on the right (tap a dot to jump): page 1 speed, throttle, brake, delta to the best section (or to the last lap when there is no best yet); page 2 steering, gear, **TC**, **ABS**; page 3 **stability**, **engine map**. A driving-aid graph has one lane per line (best / last / now): filled where the aid works, the set level on the left (TC as level / cut), a mark with `→ n` where the level changes, and `WORKING BEST x % · LAST y % · NOW z %` (share of the section) in the title band; `NOT RECORDED` for laps without aid data. Each page has its metres axis and the cursor line. LIVE (the start view) follows the current section; any section can be opened while driving and stays until LIVE is tapped. The page polls `/api/analysis/live` 4 times per second and the selected section twice per second; the car dot comes from the stream. Tapping a section on the map or in the strip opens GRAPHS. When a run ends the end-of-run menu shows laps, best lap, open offers and KEEP ALL LAPS / KEEP BASELINES ONLY.

**Recorder** (`core/recorder.py`, fed with every frame by the reader thread; an error in it is logged and never stops the bridge). It records while the frame is live, without error, with `lap_pos` and a track of at least 300 m, at `[analysis] hz` (30). Sections: `section_m` (250 m) along the track from `lap_pos × track_length_m`; the last piece joins the previous section if shorter than half a section. Section times are interpolated at the borders, lap times at the line. The repeat rule: an attempt of section N starts only when the car drives forward from N−1 into N and ends when it drives into N+1; moving back into a section never starts an attempt; samples are kept only while the position grows (driving backwards is not recorded); more than 100 m back from the furthest point, a jump (also one during a pause: back to the pits, a reset) or a backwards line crossing mark the lap as not counting. The recorder's clock stands still while nothing is recorded (game paused, menu, no data): a pause adds nothing to lap or section times, leaves no gap in the samples, and the lap counts normally, and a lap with a repeated section never counts. A lap that starts standing (a stage start) is timed from the moment the car moves; a stage ends when the car stays at its end (`lap_pos` ≥ 0.9995) for 1 s; a jump back to the start from further than 200 m is a restart. Offers: an attempt faster than the section baseline (or the first one), and a lap that counts and beats the lap baseline; one pending offer per section and lap (a faster one replaces it). SAVE moves the current baseline to `*.prev.jsonl` and writes the new one; UNDO puts the backup back (or removes a first baseline). Offers whose lap file exists survive a restart of the bridge (`data/pending.jsonl`). A run ends with a new session (game, track, car or `session_id` changes), when the game closes, or with END RUN.

Files (JSON Lines, every file starts with a header line `{"type": "header", "format": ..., "version": 1, game, car, track, track_length_m, section_m, sections, hz}`):

- `data/runs/<game>/<track>/<car>/<date_time>/lap-007.jsonl`: header (`racing-dashboard.lap`, run, lap, out_lap), sample lines `{"type": "s", "t", "p", "x", "y", "v", "thr", "brk", "str", "g", "sec", "att", "line", "rpm", "a", "lv"}` (`rpm` since November 2026; `a` = [TC, ABS, stability] working 1 / 0 and `lv` = the set [TC, TC cut, ABS, stability, engine map] levels, both left out when the game reports none, as in laps recorded before November 2026; t seconds from the lap start; `sec` 1-based; `att` the attempt the sample belongs to; `line` 1 = part of the lap's line), one `section` line per attempt (`sec`, `att`, `time`, `t_in`, `complete`, `broken`), one `ambient` line, one `summary` line (`time`, `game_time` (the game's own lap time in seconds, from `last_ms` once it changes after the line, within 5 s; null if the game sends none), `complete`, `valid`, `invalid_at` (lap position where the game first said invalid, or null), `counts`, `out_lap`, `repeated`, `broken`, `sections`). `run.jsonl` logs laps, offers, saves, skips, undos and the end.
- `data/baselines/<game>/<track>/<car>/lap.jsonl` (`racing-dashboard.lap-baseline`) and `sections/section-07.jsonl` (`racing-dashboard.section-baseline`, with `section`, `from_m`, `to_m`; samples with `d` metres and `t` seconds from the section start), each with a `source` (run, lap, attempt), and the backups `lap.prev.jsonl`, `section-07.prev.jsonl`.

**AI trainer** (`core/trainer.py`): an AI TRAINER button on the map and a TRAINER tab; the bridge computes the facts of the whole lap or the zoomed section, asks the AI the owner set up in the settings (Claude, ChatGPT, Gemini, Ollama; FAST / BEST = a fixed model + effort pair per provider) with a fixed prompt, checks the JSON answer and keeps the last 5 answers in `data/trainer.jsonl`. Full definition, prompt and answer format: [TRAINER.md](TRAINER.md).


## 7. Adding a game

1. Make a folder `games/<id>/` with `game.toml` (`[game] name`, `[window] process` / `title`, `[keys]`), `connector.py` with `class Connector(telemetry.Connector)` and, for the tablet, `dash.toml` (the dash box cards, see [DASH](#dash-dash-box)).
2. `read()` returns the universal fields the game provides (or `None` while the game is not running); `open()` / `close()` attach and detach; `handle()` optional.
3. The bridge loads every folder with a `game.toml`; the game appears in the GAME setting.

Known data sources for later games: AC and ACC (shared memory `Local\acpmf_*` with the ACC layout already read for Assetto Corsa Rally, ACC also UDP broadcasting), rFactor 2 and Le Mans Ultimate (shared memory plugin / native), Automobilista 2 and Project CARS 2 (shared memory `$pcars2$`, UDP), F1 (UDP), BeamNG (OutGauge UDP), Forza (Data Out UDP), Dirt Rally / EA WRC (UDP). `core/winmem.py` reads any Windows shared memory block (`read_at` for blocks without a fixed size, as iRacing's) and tells games with the same block names apart by their process (`process_running`); `core/kunos.py` holds the physics page Kunos' games share.

## 8. Installation

`install.bat` runs `tools/install.ps1` (Windows PowerShell 5.1, plain ASCII, no `exit` so it can also run as `irm <raw url> | iex`). Steps: find Python 3.12+ (`py -3`, `python`, the usual install folders) or install Python 3.13 with winget (`--scope user`); use the copy the script is in, or download `main.zip` from GitHub to `%LOCALAPPDATA%\RacingDashboard` (an update removes the code folders `core ui games docs tools tests` and merges the rest with robocopy, so `config\config.toml` stays; a marker file `.installed-by-script` allows the uninstall to delete the folder); run `core/server.py --check`; add the inbound firewall rule "Racing Dashboard" (TCP `[dashboard] port`, profiles Private and Domain) with one elevated PowerShell; warn about networks set to Public and offer to switch them to Private; create Start menu entries (start, uninstall, folder) and an optional desktop shortcut. The start shortcut runs the found `python.exe` with `core\server.py` directly. `-Uninstall` removes shortcuts, the rule and (for a downloaded copy) the folder. Every change is asked first; `-Yes` accepts the defaults.

`server.py --check` loads the config and all games without starting the server and prints Python version, games, start game, port, address and `Result OK`.

## 9. Configuration

`config/config.toml` is optional; sections are merged key by key over the defaults in `core/config.py`. See `config/config.example.toml` for every key: `[dashboard]` host, port, start game; `[telemetry]` read_hz, stale_s; `[input]` tap_ms, hold_max_s; `[analysis]` enabled, data_dir, hz, section_m; `[trainer]` timeout_s, ollama_url, models (FAST / BEST overrides); `[log]`; `[games.<id>.keys]` key overrides.

## 10. Tests

`python -m unittest discover tests` (84 tests): the data checks of the core; the ACE struct layout and translation against synthetic shared memory; the Assetto Corsa Rally ACC layout, clock text, Kelvin and pause detection; the boost values of ACE, ACR and iRacing; the wheel slip of ACE (with the lock flag), ACR and DR2; the iRacing memory image (header, variables, the newest buffer), the session YAML, the translation and the dead-reckoned map position; the DiRT Rally 2.0 packet translation, stage and car names and a UDP round trip; a bridge smoke test with the demo game (pages, the home link, path safety, state, info, commands, latch keys, stream rate, the analysis and trainer API, the API key never in a reply); the recorder with a simulated car (sections, lap and section times, the game's lap time, files, offers, SAVE / SKIP / UNDO, the repeat rule, a spin at a border, backwards driving, invalid and paused laps, a stage with a standing start, end of run, offers after a restart, the section data, driving aids); the AI trainer with simulated providers (facts, the request, answer checks, settings, keys, the rolling history); the live tool's GRIP stages and recording check. With the bridge running, `python tools/live.py` watches, records and checks the live values of any game (docs/HANDOVER.md); on Windows with ACE running, `python tools/ace_probe.py` prints the values straight from the shared memory (`--raw`: slip, lock, TC / ABS, turbo) and `python tools/analysis_check.py` checks the recorded laps.

## 11. Future development and out of scope

Ideas: more games; more pages and styles (e.g. a round rev counter, a timing page); flags; brake temperatures and damage; external displays such as an ESP32 reading `/state`; a virtual joystick (vJoy) as an alternative to keypresses, for buttons that should work while the game is not the active window.

Out of scope: multiplayer cheating aids, security beyond the local network, hardware.
