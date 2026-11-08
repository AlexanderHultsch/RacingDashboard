# Handover – cloud session

For the next Claude session **in the cloud** (no games, no Windows PC, no iPad). Written at the end of the local session on the owner's Windows PC (8–9 November 2026), which tested everything with Assetto Corsa EVO (ACE) on the PC and an iPad / iPhone. Read this first, then [README.md](../README.md), [SPEC.md](SPEC.md), [ANALYSIS.md](ANALYSIS.md) and [TRAINER.md](TRAINER.md).

## Start

```
git pull
python -m unittest discover tests
python core/server.py --check
```

All tests must pass (61 in November 2026) and `--check` must print `Result OK`. In the cloud the bridge runs with the **demo game** only (`python core/server.py`, settings → GAME → DEMO, or `config/settings.json` `{"game": "demo"}`); ACE needs Windows shared memory, keypresses need Windows. The owner's recorded laps (`data/`), the AI settings with the API key (`config/trainer.json`) and the local mockups (`mockups/`) are **not in git** and not in the cloud.

## What the cloud session can and cannot do

- **Can:** change code, docs and tests; run the tests and the demo game; render PNG mockups of pages with a headless browser (the owner wants mockups before every visual change); simulate laps (see `tests/test_recorder.py`, `tests/test_trainer.py`) and a simulated AI provider.
- **Cannot:** see the game, the owner's data or the log. Anything about real ACE / DR2 values comes from the owner: ask them to paste `python tools\analysis_check.py --last 1`, lines of `logs\racing-dashboard.log`, `http://localhost:8080/state`, or `data\trainer.jsonl` entries.
- **Never** ask for or handle the owner's API key. Real AI calls happen only on the owner's PC; the tests use simulated providers.

## Where things stand

| Part | Where | State |
| --- | --- | --- |
| Bridge, GEAR + REV (phone), DASH (iPad), BUTTONS | `core/`, `ui/` | in daily use with ACE; the owner says it works very well |
| Home page | `/Racing_Dashboard` (also `/`) | the link the owner saved on the iPad; flight simulator dashboards share the address and port |
| ACE connector | `games/ace/connector.py`, [ACE/NOTES.md](ACE/NOTES.md), keys in [ACE/KEYS.md](ACE/KEYS.md) | dash values verified in the game (BMW M4 CSL, Mazda RX-7, Toyota GR86, Porsche 992 GT3 R, Audi Sport quattro, VW Golf 8 R); lights / wipers are not published by ACE 0.9.1 |
| DR2 connector (UDP) | `games/dr2/connector.py` | only tested with simulated packets; the analysis never seen with DR2 |
| **Analysis page** | `core/recorder.py`, `ui/analysis.html`, `ui/js/analysis.js`, `ui/styles/analysis/standard.css` | **verified with ACE** at Brands Hatch (GR86, Golf, Audi, Porsche): lap and section times, lap times against the game's own (`game_time`, within 0.006 s), map, deltas, REVIEW / SAVE, graphs with the cursor, driving aids. Details below |
| **AI trainer** | `core/trainer.py`, [TRAINER.md](TRAINER.md) | works with Claude on the owner's PC (two real answers, Claude FAST); prompt and facts fixed after reading them, FAST now at effort medium; **not checked after those fixes**. ChatGPT, Gemini and Ollama never called for real |
| Tools | `tools/ace_probe.py [--analysis]`, `tools/analysis_check.py [--last N] [--game ID]` | for the owner on the PC |
| Installer | `install.bat`, `tools/install.ps1` | ask the owner whether it was ever run |

## Code review for the public release (cloud session, November 2026)

After the local session the owner asked for a full review and clean-up before making the repository public. Done: dead code removed (telemetry fields nothing read: `launch`, `auto_clutch`, `flag`; the demo's D / S gearbox modes; DiRT Rally 2.0 packet offsets the connector never read; `Recorder.save_all`; API payload fields no page used: `lap` / `laps` / `run_best` in `/api/analysis`, `times` / `base` in the strip, `busy` in `/api/trainer`; `RD.icons.home`, the `int` / `pct` formats; CSS of the removed TO REVIEW pop-up); the ACE connector derives `limits` and `fixed` from one pass over the settings; the trainer uses the recorder's interpolation; `log.setup` ignores a second call; the repository name (`AlexanderHultsch/RacingDashboard`) in the installer and the docs; README status and SPEC brought up to date. The owner's one open decision for the release: a **LICENSE** file (none yet).

## What the local session did (newest first)

| Commit | What |
| --- | --- |
| `1fafc7b` | AI trainer after the first real answers: no summary, tip titles on one line with the place below, prompt rules (metres grow = later, `coast_m` is a total, a slow entry comes from the section before, title = text), gears without the neutral of a shift, delta at the section end, WHOLE TRACK on the last complete lap, Claude FAST at effort medium |
| `29a54a9` | Driving aids recorded per sample (TC / ABS / stability working; TC, TC cut, ABS, stability, engine map levels); GRAPHS as 4 per page, scrolled (speed, throttle, brake, delta / steering, gear, TC, ABS / stability, engine map) with lanes per line; aid facts for the trainer |
| `6a5dbc3` | AI trainer: button on the map, TRAINER tab, settings (provider, key kept on the PC, FAST / BEST, TEST), `core/trainer.py`, last 5 answers in `data/trainer.jsonl` |
| `3133c74` | Map in the first lap of a new car (was drawn from a 10 m out lap); the paused view keeps the lap in progress |
| `4cf66e2` | Analysis cursor (drag along the track, yellow line in all graphs, faded ahead, BACK button, lines slightly see-through); settings button in one place top right on every page; gear numbers only (AUTOMATIC GEARBOX setting removed); home page `/Racing_Dashboard` |
| `cb2134c` | A pause stops the lap clock and the lap counts; the game's lap time and where a lap was invalidated stored in the lap file |
| earlier | ACE dash and key work (fixed ABS, diff locking %, wipers latch, ignition hold, keys off Insert / Home / Delete / End), see `git log` |

## Findings from the real data (ACE 0.9.1)

- `lap_pos`, track length and position work; driven distance 99 % of the track length; 29 Hz on clean laps; section times add up to the lap time; steering about ±0.95.
- `is_valid_lap`: true on clean laps, false after cutting and on the first lap from the pits (correct, the game shows it invalid too).
- `session_id` (`0-0-0-Practice`) stable within a session; **not checked across sessions** (it may be the same for every practice session).
- **Pause:** in one run (Golf, lap 4) the car stood 89 s after Paddock Hill while ACE kept reporting `live`, and ACE's own lap time included those 89 s. Either that was not the pause menu, or ACE practice does not pause. The owner never confirmed which; the dashboard follows the game there (the Golf's saved best lap is that 3:26 lap until a faster one is saved).
- In the pit box ACE reports a lap position near the line (0.997, or 0.37 on another start); an out lap from the pits is short and that is fine.
- **Not checked:** whether the map is mirrored compared with the game's track map (the page draws `pos_x` right and `pos_y` = game z down).

## Open, in the owner's order of interest

1. **AI trainer quality:** the next real answers after the fixes (titles agree with the text? does it mention gear / TC links, e.g. 1st gear with TC working where best used 2nd?). Ask the owner for the `data\trainer.jsonl` lines and read the facts sent with them (`data` field) before changing the prompt. Prompt and schema are in `core/trainer.py`; [TRAINER.md](TRAINER.md) shows them and the history of changes.
2. **Driving aids in the graphs:** saved bests from before 9 November have no aid data (`NOT RECORDED` in the best lane) until the owner saves new bests. Confirm with the owner that the lanes look right in a real session.
3. **ChatGPT / Gemini / Ollama** in the trainer: request shapes written from the providers' docs (models `gpt-6-luna` / `gpt-6-astra`, `gemini-3.8-flash` / `gemini-4-argon`, checked 2026-11-08); never called for real. Gemini's `x-goog-api-key` header and `GET /v1beta/models/<model>` were not confirmed for `generateContent` (the docs showed `?key=`): if TEST fails with Gemini, look there first.
4. **Two new DASH cards, paused by the owner:** TYRES (temperature and pressure per wheel, coloured cold / ok / hot) and DRIVE MODE (ACE performance mode name, − / + on new keys, proposed Num3 / Num6). A mockup was shown on the PC (`mockups/dash-tyres-drive-mode.png`, local only); the owner said "stop" before deciding. ACE data: graphics `tyre_*` (pressure, `tyre_temperature_c`, normalised values) and physics `wheelsPressure` / `tyreCoreTemperature`; performance mode in `electronics.active_performance_mode` with its limits and `performance_mode_name` (stale on cars without modes). Ask before picking it up again.
5. Map orientation, `session_id` across sessions, DR2 with the analysis (one stage = one lap, baselines under `dr2/unknown/unknown`, ask whether to sort by stage length).

## How the analysis works (where to look)

- **Recorder** `core/recorder.py`, fed every frame by the reader thread in `core/server.py`. Rows: `[now, p, x, y, v, thr, brk, str, g, sec, att, line, tc_on, abs_on, esc_on, levels]`; the recorder's clock stands still while nothing is recorded (pause, menu), so a pause adds no time. `_why_not()` says why a frame is not recorded; `_sample()` holds the line crossing, restart, stage end and repeat rule; `_shown()` picks red / blue (the lap in progress also while paused); `complete_laps()` gives the trainer's whole-track laps; `section(n, laps)` the three lines of a section with 17 columns.
- **Files** (formats in [SPEC.md](SPEC.md#analysis)): `data/runs/<game>/<track>/<car>/<date_time>/lap-NNN.jsonl` (samples with `a` and `lv` for the aids, `section`, `ambient`, `summary` with `game_time` and `invalid_at`), `run.jsonl`, `data/baselines/...`, `data/pending.jsonl`, `data/trainer.jsonl`.
- **Page** `ui/js/analysis.js`: map (tap a section to zoom, drag for the cursor, BACK), strip, REVIEW / GRAPHS / TRAINER tabs (`setTab`), graphs in pages of 4 (`renderGraphs`, `PER_PAGE`, aid lanes in `drawLanes`), trainer (`aiView`, `renderAi`, `renderTrainer`).
- **AI trainer** `core/trainer.py`: `facts()` / `aid_facts()` / `build_request()` from `recorder.section()`, `SYSTEM_PROMPT`, `SCHEMA`, one provider class each (`Claude`, `ChatGPT`, `Gemini`, `Ollama`), `check_answer()`, the history. FAST / BEST pairs in `MODELS`, overridable in `config.toml` `[trainer.models]`.

## Known limitations (tell the owner if they come up)

- After the session, red is always the last lap and blue the one before; no lap picker yet.
- UNDO restores the previous baseline but does not bring the offer back into REVIEW.
- KEEP BASELINES ONLY deletes the lap files; offers still open then live only in memory until the bridge restarts.
- A lap started standing on a circuit (race start) counts as a normal lap.
- If a game reports a different track length in another session, the section count can change and old section baselines no longer line up (not seen yet).
- Answers in the trainer history stay as they were checked; answers from before `1fafc7b` still carry a summary (not shown) and may have titles ending in `…`.

## Decisions the owner made (keep them)

- Universal UI, one folder per game (`games/<id>/connector.py`, `game.toml`, `dash.toml`); UI in `ui/` (plain HTML / CSS / JS); Python standard library only.
- GEAR + REV: yellow 14-segment digit in a light grey frame close to the screen edges, GEAR in the top line, as large as possible; 8 rev lights blue-green-yellow-red-red-yellow-green-blue filling from the outside in, flashing at the shift point, unlit fields dim (they leave 54 px at both ends for the settings button); no rpm / speed numbers; E for errors with a chip; always the gear number (P only for park); gears above 9 show E. **No** dimmed gear with the engine off, **no** flashing gear in the pit lane.
- Settings button: same size and place on every page, top right. Settings overlay: 16 px padding plus the landscape top gap. Home page `/Racing_Dashboard`. On a tablet in landscape every page starts 26 px lower (`--top-gap` in `base.css`; the iPad fades at its top edge); not on a phone.
- DASH (iPad): cards, the same layout for every car of a game; greyed cards for what a car lacks; values read back from the game; a card lights up after a tap and when the value changes in the game; TC / ABS / ESC amber while active; warning lamps as colours only; no hints. ACE: IGNITION held, WIPERS as a latch, LIGHTS / WIPERS without state, diff locking in % for cars without diff steps, FIXED settings, no LAUNCH, no AUTO CLUTCH.
- ANALYSIS ([ANALYSIS.md](ANALYSIS.md)): one page; map left with BACK (top left, while zoomed) and the cursor (drag along the track; yellow ring and a yellow line through all graphs; lines after it faded; no value readouts); best / last / now lines slightly see-through; right side tabs **REVIEW first**, GRAPHS (4 per page, scrolled), TRAINER; green best, blue last, red now; lap and section deltas vs best ever and vs last always visible; section strip with slider; no braking markers; LIVE start view and tapping sections while driving; 250 m sections by track position; recording at 30 Hz, written at lap end; baselines per game / track / car for the lap and every section; every new best **offered, never saved without a tap**; one backup per baseline for UNDO; invalid laps: sections may be offered, the lap never; a pause stops the lap time and the lap counts normally; while paused the page keeps the lap in progress; driving aids (working + set levels) recorded and shown as lanes; the repeat rule (entering N−1 then N replaces N; a spin at a border replaces nothing; backwards never recorded).
- AI TRAINER ([TRAINER.md](TRAINER.md)): button bottom right on the map, only `AI TRAINER` (the map decides: overview = whole track on the last complete lap, zoomed = that section), answer in the TRAINER tab, only on a tap; Claude / ChatGPT / Gemini / Ollama with the owner's key kept on the PC; FAST / BEST = fixed model + effort per provider (Claude: Haiku 5.5 medium / Opus 5.5 high); facts computed by the bridge, fixed prompt, JSON answer with up to 3 tips (title 4 words on one line, place below, text 35 words), **no summary**; English; tapping a tip opens its place in GRAPHS; last 5 answers in one rolling file, kept over restarts; greyed out with the reason when the connection does not work.

## Working with the owner

- The owner writes short messages, mostly English, sometimes German, often with typos; reply short and plain in the language they wrote.
- **Commit and push only when the owner says so** (they say "Commit and push"); commit to `main`, end commit messages with the Co-Authored-By line. The only other branch is one work-in-progress branch for a prototype the owner has not approved yet. No branch per feature.
- For visual changes: **show PNG mockups first** (HTML rendered with a headless browser), ask for feedback, then build. For bigger features the owner likes a short interview first (they answered well to 3–4 multiple-choice questions per round).
- Keep README, SPEC, the game notes, TRAINER and tests in step with every change; no personal data in commits; no emoji in the UI.
- The owner tests on the iPad (analysis, dash) and an iPhone (gear) while driving ACE with a controller; ask them to restart the bridge after a change.
- Ideas not built yet: lap picker after the session, tyre / brake temperature / damage cards (see open item 4), two-page dash box, names for light / wiper stages, flags, more games ([ASSISTS.md](ASSISTS.md)).
