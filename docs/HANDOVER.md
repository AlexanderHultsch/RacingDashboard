# Handover – for a cloud session

For the next Claude session **in the cloud** (no Windows, no games, no iPad / iPhone). Written at the end of the local session on the owner's Windows PC, 10 November 2026. Read this first, then [README.md](../README.md), [SPEC.md](SPEC.md), and as needed [ANALYSIS.md](ANALYSIS.md), [TRAINER.md](TRAINER.md) and the game notes ([ACE](ACE/NOTES.md), [ACR](ACR/NOTES.md), [IRACING](IRACING/NOTES.md), [DR2](DR2/NOTES.md)).

## What a cloud session can and cannot do

| Can | Cannot |
| --- | --- |
| Read and change all code and docs, run `python -m unittest discover tests` (79 tests, all pass) | Read a game: the connectors use Windows shared memory (`core/winmem.py`) or UDP from a running game |
| Run the bridge with the **demo game** (`python core/server.py`, GAME → DEMO): a simulated car with every field, a turbo (`boost_bar`) included, and laps for the analysis page | Send keypresses (`core/keys.py` is Windows only; the bridge reports "not available") |
| Render pages with a headless browser for **PNG mockups** (the owner wants them before every visual change) | Check anything against real game data: say so, and leave a test step for the local session in this file |
| Commit and push to `main` when the owner says so | See the owner's laps (`data/`), AI key (`config/trainer.json`) or mockups (`mockups/`): local, not in git |

Headless rendering tips: a page keeps its EventSource open, so a headless screenshot can hang; stub `window.EventSource` with a class that polls `/state` and calls `onmessage`, and replace `requestAnimationFrame` with `setTimeout` (rendering waits for an animation frame). For phone sizes render the page in iframes (844 × 390 landscape, 390 × 844 portrait) inside one composite page.

## Start

```
git pull
python -m unittest discover tests
python core/server.py --check
```

`--check` lists five games (ace, acr, demo, dr2, iracing) and prints `Result OK`. Pages: `/Racing_Dashboard` (home), `/gear`, `/dash`, `/analysis`, `/buttons`, `/boost`; `/state` is the live frame, `/api/info` the dash map and buttons. An open page reloads itself when files in `ui/` change (frame field `ui`).

## What the local session did (10 November 2026, newest first)

| Commit | What |
| --- | --- |
| `2a636cc` + this one | **BOOST page** `/boost` (phone): round gauge in the gear page's frame style, red needle, yellow arc, BAR under the hub and the value with one decimal below it in the SPEED number style. NO TURBO (ACE / ACR car without a turbo), VACUUM below 0 (iRacing manifold pressure), NO DATA + chip in DR2. Fields `turbo`, `boost_bar`, `boost_min_bar`, `boost_max_bar` (`kunos.boost`, iRacing `ManifoldPress`); demo car with a turbo; O T U C V in the segment font; home tile, settings entry, startup line |
| `5d1d565` | Rev lights: scale from 88 % of the game's shift point up to it; red pair and dark red screen at the game's shift signal; **bright red flashing only on the game's limiter flag** (owner: a simple rule by flags, nothing per car) |
| `b651239` | Gear page: SPEED box below the gear frame (same width and style, no unit) |
| `bdfcab0` | Pages reload themselves after an update; rev lights never flash |
| `deb1037` | Gear frame turns red at the shift point; tyre colours along a scale; ACE engine map counts from 1 |
| `4af985c`, `5f1f644` | TYRES card like the ACE HUD (pressures outside, tiles by tyre temperature, brake bar by brake temperature); ACE card PERFORMANCE |
| `2bff8f3`, `15bbf44` | TYRES and DRIVE MODE cards; left indicator off Comma (the owner's voice chat mute key); home link in the startup window, own home-screen icon name |

## Where things stand

| Part | State |
| --- | --- |
| Bridge, GEAR + REV, DASH, BUTTONS, home | in daily use with ACE |
| GEAR + REV rev lights and red screen | verified in ACE (Porsche 992 GT3 R, Toyota GR86): shift signal and limiter flag come from the game |
| Analysis page | verified with ACE (lap times within 0.006 s of the game's) |
| AI trainer | works with Claude; answers with the rewritten prompt (up to 9 tips) not judged yet |
| TYRES / PERFORMANCE cards | built, **not checked in the game** (pressure unit, colour scales, Num3 / Num6) |
| BOOST page | works with the demo car and shows NO TURBO in the GR86; **not checked in an ACE turbo car** |
| Assetto Corsa Rally, iRacing, DiRT Rally 2.0 | **never run against the games** |

## Open, in the owner's order of interest

1. **BOOST in an ACE turbo car** (local only): which of graphics `turbo_boost`, `turbo_boost_level`, `turbo_boost_perc` or physics `turboBoost` is the boost, its unit (bar assumed) and `max_turbo_boost`. Candidates: BMW M4 GT3, Ferrari 296 GT3, McLaren 720S GT3 Evo. iRacing's `ManifoldPress` is taken as absolute bar (boost = value − 1.013): unconfirmed.
2. AI trainer quality with the new facts and prompt (local, with ACE): read the facts in `data/trainer.jsonl` with each answer before changing the prompt.
3. First drives in ACR, iRacing, DR2 (local; the open questions are in each game's NOTES: ACR stage start / end, iRacing map direction, DR2 UDP).
4. TYRES / PERFORMANCE cards in ACE (local).
5. Driving aids in the graphs: bests from before 9 November have no aid data (`NOT RECORDED`) until new bests are saved.
6. ChatGPT / Gemini / Ollama in the trainer: never called for real, **not planned to be confirmed** (the owner uses Claude only). Leave the code.
7. A LICENSE file for the public repository (the owner's decision; MIT suggested).
8. Ideas not built yet: lap picker after the session, damage card, two-page dash box, names for light / wiper stages, flags, a clearer "no API credits" message, more games ([ASSISTS.md](ASSISTS.md)). Work that a cloud session can do fully: these, docs, tests, the demo car, pages and styles (with mockups).

## Findings from the real data (ACE 0.9.1)

- Porsche 992 GT3 R: max rpm 9,400, shift signal (`is_change_up_rpm`) from ~9,000–9,040 rpm in every gear, limiter flag (`is_rpm_limiter_on`) from ~9,070–9,120. `gear_rpm_window` is always 1.0 (no shift-light range from the game).
- Toyota GR86: no turbo, all turbo values 0, `engine_type` 0.
- `lap_pos`, track length and position work; section times add up to the lap time; `is_valid_lap` false after cutting and on the out lap.
- Lights / wipers stages are not published by ACE 0.9.1. Not checked: whether the ACE map is mirrored; `session_id` across sessions.

## How it works (where to look)

- **Connectors** `games/<id>/connector.py` translate a game into `core/telemetry.py` `FIELDS`; `game.toml` (window, keys), `dash.toml` (dash box cards). Kunos' physics page and `boost()` in `core/kunos.py`.
- **Pages** `ui/*.html`, shared code `ui/js/rd.js` (stream, formats, widgets, rev lights, settings, styles), `ui/js/seg14.js` (14-segment SVG), `ui/js/dashbox.js`, `ui/js/analysis.js`, `ui/js/boost.js`; styles `ui/styles/<page>/<style>.css`.
- **Recorder** `core/recorder.py`, **AI trainer** `core/trainer.py`; file formats in [SPEC.md](SPEC.md#analysis).

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; no lap picker. UNDO does not bring the offer back into REVIEW. KEEP BASELINES ONLY deletes the lap files.
- A different track length in another session changes the section count. DR2: two cars with the same gear count, redline and idle share one name.
- iRacing: the map is dead-reckoned (drift within a lap); ACR: stage start / end detection unproven.

## Decisions the owner made (keep them)

- Universal UI, one folder per game; UI in `ui/` (plain HTML / CSS / JS); Python standard library only. Every game gets every page; a page a game cannot fill says so (BOOST in DR2: NO DATA).
- GEAR + REV: yellow 14-segment gear in a light grey frame close to the screen edges, GEAR in the top line; 8 rev lights blue-green-yellow-red-red-yellow-green-blue from the outside in, from 88 % of the game's shift point up to it; the red pair and the dark red screen at the game's shift signal; **bright red flashing only on the game's limiter flag — a simple rule by flags, no rule per car**; the lights never flash; no rpm number; SPEED small in a second frame below (no unit); E for errors with a chip; always the gear number (P only for park); gears above 9 show E.
- BOOST (phone): a gauge, not a number or bar; BAR under the hub, the value with one decimal below the gauge in the SPEED number style; NO TURBO for ACE cars without a turbo, VACUUM in iRacing, DR2 NO DATA; own link `/boost`, listed in the startup window.
- Settings button: same size and place on every page, top right. Home page `/Racing_Dashboard` (the PC also serves flight sim dashboards on the same address and port). On a tablet in landscape every page starts 26 px lower (`--top-gap`).
- DASH (iPad): cards, same layout for every car of a game; greyed cards for what a car lacks; values read back from the game; TC / ABS / ESC amber while active; warning lamps as colours only. TYRES like the ACE HUD (no legend, no compound, brake bar full height, colour only). ACE: IGNITION held, WIPERS as a latch, engine map from 1, PERFORMANCE (not DRIVE MODE), no key on Comma (voice chat mute).
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)): map left with BACK and the cursor; tabs REVIEW first, GRAPHS, TRAINER; green best, blue last, red now; every new best offered, never saved without a tap; a pause stops the lap time; no pro / reference laps.
- AI TRAINER ([TRAINER.md](TRAINER.md)): only on a tap; Claude / ChatGPT / Gemini / Ollama with the owner's key kept on the PC; FAST / BEST (Claude: Haiku 5.5 medium / Opus 5.5 high); facts computed by the bridge; up to 9 tips, category first, no summary; English; last 5 answers kept.

## Working with the owner

- Short messages, mostly English, sometimes German, often with typos; reply short and plain in their language.
- **Commit and push only when the owner says so**; commit to `main`, end commit messages with the Co-Authored-By line. The only other branch is one work-in-progress branch for a prototype the owner has not approved yet.
- For visual changes: **show PNG mockups first**, then build. For bigger features a short interview first (3–4 multiple-choice questions).
- Keep README, SPEC, the game notes, TRAINER and tests in step with every change; no personal data in commits; no emoji in the UI. **Never ask for or handle the owner's API key.**
- When a change needs the game to verify, build it, test it with the demo car and unit tests, and add the in-game check to "Open" above for the local session.
