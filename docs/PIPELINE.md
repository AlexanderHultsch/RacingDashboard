# Analysis pipeline

A background worker in the bridge that analyses **every telemetry sample** and saves it all, so that the whole dataset, already pre-analysed, can later go to an AI for coaching. Focus: driving skill, not setup or weather. Built 18 November 2026 from the owner's proposal; tested with the demo car and synthetic laps, **not yet in a game**.

Code: `core/pipeline.py` (the worker, the sessions, the files), `core/pipeline_rules.py` (derived values, envelope, phases, rules). Thresholds: `config/analysis.default.toml`. Tests: `tests/test_pipeline.py`.

## When it runs

Only while the **AI DETAIL LOG** is on (settings; off by default) and the game delivers live data with a lap position. Then the bridge hands every frame to the worker (`Pipeline.put`): a queue of `[pipeline] queue_size` frames in front of one thread. It **never blocks** the bridge or the pages: when the worker falls behind, the oldest frame is dropped and counted (`dropped_frames`). The connector fills a `detail` block with the extra raw values only while the detail log is on; the bridge strips it from what it streams to the pages.

## Two passes

1. **Live**, at the end of every lap: derived values, phase, corner, label and reasons, with the grip envelope, the reference lap and the corner map **of the session so far**. The rows are appended to `samples.csv` at once (`label_pass` = `live`): a crash loses at most the lap in progress.
2. **Final**, at the end of the session (another game, track, car or session id; no live data for `session_idle_s`; the bridge closing) or **on demand** (`python tools/live.py --finalize`, `POST /api/pipeline/finalize`): the envelope, the reference (the best valid lap) and the corner map over the whole session, every sample relabelled (`label_pass` = `final`), `laps.json`, `corners.json`, `session.json` and `README.md` written. On demand the lap in progress goes on. A session the bridge left open (the window closed) is finalized at the next start.

## Per sample

**Inputs** (from the universal telemetry frame and the connector's `detail` block; ACE fills all of them): throttle, brake, clutch, steering (and steering-wheel degrees), gear, rpm, torque, speed, body slip (from the local velocity), lateral / longitudinal g, yaw rate, pitch, roll, ride height, slip ratio / slip angle / wheel load / fx / fy / suspension travel per wheel, kerb vibration, brake bias, engine brake, TC / ABS settings and strength, TC / ABS working, shift signal, rev limiter, tyre temperatures / pressures / wear, brake temperatures, lap position and track length, map position, the game's lap time and delta, wheels out, lap valid. Weather and ambient values, ERS and DRS are left out.

**Derived** (after smoothing over `[smoothing] window_s`, ~50 ms):

| Value | How |
| --- | --- |
| `lap_dist_m` | lap position × track length |
| `g_combined_g` | √(a_lat² + a_long²) |
| grip envelope `g_max(v)` | the `percentile` (98 %) of combined g in speed bins of `bin_kmh` (10 km/h), separately for braking, cornering and traction (histograms; a thin bin borrows from its neighbours) |
| `grip_use` U | √((a_lat / g_lat_max)² + (a_long / g_long_max)²) |
| `mu_tyre_*` | √(fx² + fy²) / wheel load, where the game sends the forces |
| `balance_deg` | mean \|slip angle front\| − mean \|slip angle rear\| (> 0 understeer, < 0 oversteer) |
| `body_slip_deg` | atan2(v_lat, v_long), from the connector |
| `steer_rate_dps`, `steer_reversal` | steering-wheel speed; a reversal is a change of direction after a swing of more than 2° within 0.5 s |
| `ref_speed_kmh`, `dv_kmh`, `dt_s`, `cost_s` | against the reference lap at the same `lap_dist_m`; cost = dt(i) − dt(i−1): where the time goes |

**Phase** (first match wins, then held for `[phase] min_s`): braking (brake > 0.05, steering < 5°) → entry (brake > 0.05 with steering ≥ 5°, or throttle < 0.2 while slowing to the next speed minimum) → apex (lateral g > 0.7 × cornering envelope, throttle < 0.3, brake < 0.05) → exit (after the speed minimum, throttle rising) → straight (throttle > 0.95, steering < 3°) → transition (anything else).

**Corners** come from the reference lap (before there is one, from each lap itself): where lateral g is above `[corners] lat_share` of the cornering envelope, short gaps joined, each corner starting where the braking / entry before it starts. Track and car independent.

## Rules and labels

Every rule looks at a whole phase (one braking, one entry ...) or at a stretch of samples (a lock-up), and a condition counts only once it held for its minimum time. A sample's **label** is the worst rule that covers it: bad > potential > good (`none` when no rule applied). **reasons** lists them, worst first: `RULE level measured_value (operator threshold)`, e.g. `BRK_LOCKUP bad -0.4 (< -0.15)`. The rules with their starting thresholds (all in the config):

| Phase | Good | Potential | Bad |
| --- | --- | --- | --- |
| Braking | pressure to 90 % of its peak in < 0.15 s (`BRK_BUILDUP`); deceleration ≥ 0.95 of the envelope (`BRK_ENVELOPE`); ABS working ≤ 30 % (`BRK_ABS`) | slower build-up; 0.85–0.95 of the envelope; ABS > 70 %; braking point > 5 m off the reference (`BRK_POINT`) | lock-up: slip ratio < −0.15 for > 0.1 s (`BRK_LOCKUP`); < 0.85 of the envelope; pedal overlap (`BRK_OVERLAP`); double braking (`BRK_DOUBLE`); > 10 m earlier than the reference without a higher minimum speed (`BRK_EARLY`) |
| Entry | trail braking with U 0.95–1.03 and \|balance\| ≤ 0.5° (`ENT_TRAIL`) | no pedal 0.1–0.3 s (`ENT_DEAD_ZONE`); U < 0.95 (`ENT_GRIP_USE`); \|balance\| 0.5–1.5° (`ENT_BALANCE`) | coasting > 0.3 s (`ENT_COAST`); \|balance\| > 1.5°; ≥ 2 steering reversals (`ENT_REVERSALS`) |
| Apex | minimum speed ≥ reference − 1 km/h (`APX_VMIN`); U ≥ 0.95 (`APX_GRIP_USE`); steering rate < 20°/s (`APX_STEER_RATE`) | minimum 1–3 km/h below; U below 0.95 | minimum > 3 km/h below with U < 0.88; a second speed minimum in one corner after a rise of 2 km/h (`APX_TWO_MINIMA`) |
| Exit | throttle rising without a lift while the steering unwinds (`EXT_THROTTLE`); rear slip 0.03–0.08 (`EXT_REAR_SLIP`) | rear slip 0.08–0.12; one throttle dip (`EXT_DIP`); TC > 0.2 s (`EXT_TC`); full throttle > 5 m later than the reference (`EXT_FULL_LATE`); unused traction (`EXT_UNUSED_TRACTION`) | wheelspin: rear slip > 0.12 for > 0.1 s (`EXT_WHEELSPIN`); a lift of 0.3 (`EXT_LIFT`); counter-steer with oversteer (`EXT_COUNTERSTEER`); TC > 0.5 s; steering added on the throttle (`EXT_STEER_ADDED`) |
| Straight | throttle ≥ 0.98 (`STR_THROTTLE`); upshift within 150 rpm of the game's shift signal in that gear (`STR_SHIFT`) | shift more than 150 rpm off | partial throttle with straight steering for 0.5 s, no braking after (`STR_PARTIAL`); rev limiter > 0.1 s (`STR_LIMITER`) |
| Transition | no pedal < 0.1 s (`TRN_COAST`) | 0.1–0.3 s | > 0.3 s |
| All | | | more than 2 wheels out (`ALL_OFFTRACK`); the moment the lap was invalidated (`ALL_INVALID`) |

Rules that compare with the reference lap (`BRK_POINT`, `BRK_EARLY`, `APX_VMIN`, `EXT_FULL_LATE`) wait for a valid reference lap. The proposal's "optimum shift point from the torque curve" is not built: the shift rule uses the game's shift signal.

**Fallbacks.** A field group that stays 0 for the whole session (ACE is Early Access; other games send less) switches off every rule that needs it (`NEEDS` in `core/pipeline_rules.py`); `session.json` lists `missing_fields` and `disabled_rules`, and the log says so (`pipeline | missing | ...`). Without steering-wheel degrees from the game, the steering share × `steer_deg_per_unit` is used (`steer_deg_source` in `session.json`).

## Output, per session folder

`data/sessions/<game>/<track>/<car>/<date_time>/`:

- `samples.csv`: one row per sample (about 30 a second), the raw values and the derived ones; units in the column names (`speed_kmh`, `lap_dist_m`, `slip_angle_fl_deg` ...); empty = not sent. CSV rather than Parquet because the project uses Python's standard library only; any tool and AI reads it.
- `laps.json`: per lap the lap time, complete / gap / valid, label shares, findings; `reference_lap`.
- `corners.json`: the corners of the reference lap and, per lap and corner, braking point, minimum speed and where, full-throttle point, time lost against the reference, rule counts.
- `session.json`: car, track, the thresholds used and their version, missing fields, disabled rules, the grip envelope per speed bin, label counts.
- `README.md`: the schema, so another AI can read the folder without context.

About 5 MB of `samples.csv` per 7 minutes of driving with the demo car (99 columns); the live pass costs about 2 s of CPU per 400 s of driving, the final pass about 1.5 s for that.

## Calibrating

The thresholds are starting values. Copy the lines you change from `config/analysis.default.toml` into `config/analysis.toml` (local, ignored by git) and restart the bridge; `session.json` records the thresholds each session used. `python tools/live.py --pipeline` shows the status, `--finalize` relabels the session now with the current thresholds.

## Not yet

- The AI trainer does not read these files yet: the next step is to send a session's summary (laps, corners, the worst stretches with their reasons) to the AI.
- Not checked in a game: ACE's `detail` values (units, which of them ACE fills), the phases and rules against real driving, the thresholds.
