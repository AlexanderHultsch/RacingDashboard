# Assetto Corsa EVO – Notes

How the dashboard reads ACE and what is still to be checked in the game. Connector: `games/ace/connector.py`; keys and window: `games/ace/game.toml`.

## Reading: shared memory

ACE publishes three named shared memory blocks (since v0.6, 15 April 2026; earlier Early Access builds used the AC / ACC names and an incomplete layout):

| Block | Content |
| --- | --- |
| `Local\acevo_pmf_physics` | 800 bytes. Same layout as ACC's physics page; the first 416 bytes as in AC. ACE additions include `brakeBias`, `currentMaxRpm`, `tcInAction` / `absInAction`, `ignitionOn`, `isEngineRunning` |
| `Local\acevo_pmf_graphics` | `SPageFileGraphicEvo`: HUD values in fixed-size sub-structs (tyres, damage, pit, electronics, instrumentation, session, timing, assists) |
| `Local\acevo_pmf_static` | session and track only; AC's `maxRpm`, `maxPower` and so on are gone |

The layouts follow Kunos' **ACE_SharedFileOut_Documentation_v1** (changelog 31 March / 1 April 2026), which is published with the game community, for example in the Race-Element discussion [#302](https://github.com/RiddleTime/Race-Element/discussions/302) and the Steam guide [3707421508](https://steamcommunity.com/sharedfiles/filedetails/?id=3707421508). The open-source overlay [live-telemetry-evo](https://github.com/albertowd/live-telemetry-evo) reads the same blocks and documents what the running game really writes; our physics offsets are checked against its offset table in `tests/test_ace.py`.

Reading uses `OpenFileMappingW` (`core/winmem.py`): unlike Python's `mmap` it fails when the block does not exist, which tells us the game is not running. Because our own handle keeps a block alive after the game closed, the connector reattaches when the data has not changed for 5 s; if the game is gone, that fails and the pages show NO DATA. Data that does not change for `stale_s` (2 s, e.g. in the pause menu) also shows NO DATA. ACE stops writing while the setup page is open.

### Field mapping

| Universal | ACE source | Note |
| --- | --- | --- |
| `gear` | physics `gear` − 1 | ACE: 0 = R, 1 = N, 2 = 1st |
| `rpm`, `rpm_max` | physics `rpms`, `currentMaxRpm` | `currentMaxRpm` is per tick |
| `rpm_pct` | graphics `rpm_percent` | 0..1; a value over 1.5 is taken as percent; 0 falls back to rpm / rpm_max |
| `shift_up`, `shift_down`, `limiter` | graphics `is_change_up_rpm`, `is_change_down_rpm`, `is_rpm_limiter_on` | the game's own per-car shift point |
| `speed_kmh`, `gas`, `brake`, `clutch` | physics | |
| `tc_level`, `tc_cut_level`, `abs_level`, `esc_level`, `engine_map`, `diff_power`, `diff_coast` | graphics `electronics.*_level` | adjustable when `electronics_is_modifiable` is set; a setting that is not modifiable but has a max limit above 0 with the value inside min..max is shown as fixed (`fixed`); otherwise `None` (not on this car). Seen in the BMW M4 CSL: ABS 1, min 1, max 1, not modifiable = fixed ABS; TC CUT, engine map and diff levels all 0 = not on this car. Mazda RX-7 FD Spirit R: only ABS (fixed 1) and brake bias; TC, TC CUT, ESC, engine map, diff levels and diff locking all 0. `performance_mode_name` keeps the previous car's name ("SPORT+") when the car has none (range 0..0). Unused fields (dampers) can hold garbage with limits 0 |
| `diff_power_pct`, `diff_coast_pct` | graphics `diff_power_raw_value`, `diff_coast_raw_value` | locking share 0..1 (BMW M4 CSL: 0.25 / 0.55); the DIFF card shows it in % when the car has no diff steps |
| `limits` | graphics `electronics_min_limit` / `electronics_max_limit` | per adjustable setting |
| `fixed` | the same blocks | settings the car has but cannot change (see above) |
| `launch`, `auto_clutch` | graphics `launch_active`, `assists_state.auto_clutch` | |
| `esc_active` | graphics `esc_active` | |
| `warn_brake` | graphics `handbrake_percent` | red while the handbrake is pulled (> 5 %) |
| `warn_engine` | graphics `is_ignition_on`, `is_engine_running` | yellow with ignition on and engine off; red when the coolant is overheating |
| `warn_oil` | graphics `oil_pressure_bar`, `oil_temperature_c` | red with the engine off (no pressure) or below 0.5 bar; yellow from 135 °C |
| `warn_coolant` | graphics `water_temperature_c` | blue below 50 °C, yellow from 108 °C, red from 118 °C; all lamps off with ignition off. Thresholds follow road-car dashes and are not verified in ACE |
| `gear_mode` | – | always `None`: ACE's `assists_state.auto_gear` is an auto-shifter on a manual gearbox, so the gear page shows the gear number (first test, Nov 2026: showing `D` for it was wrong). ACE reports no P / D / S selector, sport mode or electric drive yet (`engine_type` numbers unpublished) |
| `tc_active`, `abs_active` | graphics `tc_active` / `abs_active` or physics `tcInAction` / `absInAction` | |
| `brake_bias` | physics `brakeBias` | 0.56 = 56 % front |
| `pit_limiter` | physics `pitLimiterOn` or `electronics.is_pitlimiter_on` | |
| `ignition`, `engine_running` | graphics `is_ignition_on`, `is_engine_running` | |
| `lights`, `wipers` | graphics `instrumentation.main_light_stage`, `wiper_level` | ACE 0.9.1 leaves them at 0 even when lights / wipers work, so they are `None` (not reported: the cards show – and stay usable) until the game sends a stage above 0 once |
| `fuel_l`, `fuel_max_l`, `fuel_per_lap_l` | graphics `fuel_liter_current_quantity`, `max_fuel`, `fuel_liter_per_lap` (or `fuel_per_lap`) | |
| `lap_ms`, `last_ms`, `best_ms`, `delta_ms` | graphics `current_lap_time_ms`, `last_laptime_ms`, `best_laptime_ms`, `delta_time_ms` | 0 or `INT_MAX` = no time |
| `lap`, `position`, `cars`, `lap_valid` | graphics `total_lap_count`, `current_pos`, `total_drivers`, `is_valid_lap` | |
| `car`, `track` | graphics `car_model`, static `track` | |
| `status` | graphics `status` | assumed as in AC / ACC: 0 off, 1 replay, 2 live, 3 pause |
| `lap_pos` | graphics `npos` | normalised position on the lap, 0..1 (analysis sections) |
| `track_length_m` | static `track_length_m` | |
| `pos_x`, `pos_y` | graphics `car_coordinates[i]` x and z | the player's slot: the entry of `car_ids` that matches `player_car_id`, else slot 0; seen from above (x right, z down on the map; the map may come out mirrored, check it) |
| `steer` | physics `steerAngle` | assumed −1..1 (clamped) |
| `session_id` | static `event_id`, `session_id`, `session`, `session_name` | a change starts a new analysis run |
| `air_c`, `road_c`, `tyre_compound`, `time_of_day` | physics `airTemp`, `roadTemp`, graphics `tyre_lf.tyre_compound_front`, graphics time of day | ambient line once per lap |

### To check in the game

- [ ] Gear, RPM, shift lights (`is_change_up_rpm` lights at the right moment), limiter.
- [ ] `rpm_percent` range (0..1 expected).
- [ ] `status` numbers (pause and replay).
- [ ] TC / ABS / MAP levels and brake bias follow the in-game changes.
- [ ] Lights and wiper stages (ACE menu: up to 3 light stages, 5 wiper stages; the `ace | raw` log lines show the numbers).
  BMW M4 CSL (ACE 0.9.1, Nov 2026): the limit blocks say lights 0..2, wipers 0..4, but the live `instrumentation` block stayed all 0 (also `are_headlights_visible`, `flashing_lights` and `session_state.lights_on`) while Light Cycle +, Wiper Cycle + and Flashing Lights were pressed. The wipers did move in the game while `wiper_level` stayed 0, and no other byte of the graphics block changed with them. So ACE 0.9.1 does not publish the light / wiper state in shared memory (the overlay live-telemetry-evo also treats `instrumentation` as opaque); only the limit blocks are filled. The dashboard cannot read lights or wipers back from ACE for now.
- [ ] Keys: bind them as in [KEYS.md](KEYS.md) (ACE has no keyboard defaults for the car tab), then check each DASH card.
- [ ] Lap times, delta, position.
- [ ] Analysis fields (not verified at all): `npos` runs 0..1 and wraps at the line; `track_length_m` is filled; the `car_ids` / `player_car_id` match finds the player (else the dot and lines show another car); `steerAngle` is −1..1; the map is not mirrored; `session_id` stays the same while driving and changes with a new session. `/state` shows `lap_pos`, `pos_x`, `pos_y`, `steer`, `session_id`.
- [ ] Not used yet: `flag` / `global_flag` (the enum numbers are not published), tyre data.

`python tools/ace_probe.py` prints these values live.

The bridge also writes an `ace | raw | ...` line to the log whenever one of the rarely changing raw values changes: every `instrumentation` field (light and wiper stages, indicators, flash, hazards, display), the min..max range of `main_light_stage` and `wiper_level` on this car, and the seven `assists_state` flags by name. The first line after attaching lists them all. Switch lights or wipers in the game and the log shows which number each stage is.

## Controlling: keypresses

ACE has no input API; the buttons are keypresses (`core/keys.py`, scan codes) to the ACE window (`AssettoCorsaEVO.exe`, title "Assetto Corsa EVO").

ACE has no keyboard defaults for the car controls (checked in the game, Nov 2026: Options → Controls → Car is empty). [KEYS.md](KEYS.md) has the proposed key for each ACE control; `game.toml` uses the same keys.

- Car tab (TC, TC CUT, ABS, ESC, engine map, brake bias, pit limiter, lights, flash, wipers, ignition, starter, indicators, hazards, horn, display page): plain keys from KEYS.md, bound once in ACE.
- Other tabs, not checked yet: camera `F1`, mirror `F8`, leaderboard `F7`, look left / right `Q` / `W`, shift `Z` / `X`, auto shifter `LCtrl+L` (original AC defaults), HUD and look back as `LCtrl+LShift+<letter>` proposals.
- `NEUTRAL` and `SAVE REPLAY` have no key yet (greyed out).

If ACE ignores the keys: raise `[input] tap_ms` (e.g. 150), and check that ACE is the active window (windowed or borderless helps). A virtual joystick (vJoy) is the fallback if keypresses do not work for some actions.
