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
| `tc_level`, `tc_cut_level`, `abs_level`, `esc_level`, `engine_map`, `diff_power`, `diff_coast` | graphics `electronics.*_level` | adjustable when `electronics_is_modifiable` is set; a setting that is not modifiable but has a max limit above 0 with the value inside min..max is shown as fixed (`fixed`); otherwise `None` (not on this car). Seen in the BMW M4 CSL: ABS 1, min 1, max 1, not modifiable = fixed ABS; TC CUT, engine map and diff levels all 0 = not on this car. Mazda RX-7 FD Spirit R: only ABS (fixed 1) and brake bias; TC, TC CUT, ESC, engine map, diff levels and diff locking all 0. `performance_mode_name` keeps the previous car's name ("SPORT+") when the car has none (range 0..0). Unused fields (dampers) can hold garbage with limits 0. **Engine map counts from 0 in ACE but from 1 in the car** (Porsche 992 GT3 R: ACE 0..2, car 1..3, owner, November 2026): the connector adds 1 to the value and the range (`from_one`) |
| `diff_power_pct`, `diff_coast_pct` | graphics `diff_power_raw_value`, `diff_coast_raw_value` | locking share 0..1 (BMW M4 CSL: 0.25 / 0.55); the DIFF card shows it in % when the car has no diff steps |
| `limits` | graphics `electronics_min_limit` / `electronics_max_limit` | per adjustable setting |
| `fixed` | the same blocks | settings the car has but cannot change (see above) |
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
| `lap`, `position`, `cars`, `lap_valid` | graphics `total_lap_count`, `current_pos`, `total_drivers`, `is_valid_lap` | `is_valid_lap` checked on the analysis page (Brands Hatch, November 2026): true on clean laps; false on the first lap after leaving the pits (correct, the game shows it invalid too) |
| `car`, `track` | graphics `car_model`, static `track` | |
| `status` | graphics `status` | assumed as in AC / ACC: 0 off, 1 replay, 2 live, 3 pause |
| `lap_pos` | graphics `npos` | normalised position on the lap, 0..1 (analysis sections) |
| `track_length_m` | static `track_length_m` | |
| `pos_x`, `pos_y` | graphics `car_coordinates[i]` x and z | the player's slot: the entry of `car_ids` that matches `player_car_id`, else slot 0; seen from above (x right, z down on the map; the map may come out mirrored, check it) |
| `steer` | physics `steerAngle` | assumed −1..1 (clamped) |
| `boost_bar`, `boost_max_bar` | graphics `turbo_boost` (physics `turboBoost` as a fallback), `max_turbo_boost` | **Checked** in the BMW M4 GT3 Evo at Brands Hatch (9 November 2026): `turbo_boost` is the boost in bar, 0 off the throttle up to 1.69 bar on full throttle (highest around 5,000 rpm). `max_turbo_boost` stays 0 even in this turbo car, and is 157.4 in the Chevrolet Camaro ZL1 (supercharged; boost 0.39 bar at `turbo_boost_perc` 0.65, so its maximum is about 0.6 bar): no usable unit, so it is **not used**; the gauge ends at 2 bar or the highest boost seen. `turbo_boost_level` is 1 in pause but 0 at low rpm off the throttle: no use as a "has a turbo" flag. Toyota GR86 (no turbo): all turbo values 0. No check whether a car has a turbo (owner): a car without one shows 0 |
| `rpm_pct`, `shift_up`, `limiter` | graphics `rpm_percent` (= rpm / physics `currentMaxRpm`), `is_change_up_rpm`, `is_rpm_limiter_on` | recorded in the game (Porsche 992 GT3 R, November 2026): max rpm 9,400, the shift signal from ~9,000–9,040 rpm in every gear (the car's own lights: green 8.0k, yellow 8.5k, red 8.7k, flashing blue 9.1k), the limiter flag from ~9,070–9,120 rpm. `gear_rpm_window` stays 1.0 (no shift-light range from the game), so the rev lights run from 88 % of the learned shift point up to it (Porsche: blue ~7.95k, red at the shift signal ~9.03k); the screen flashes only on `is_rpm_limiter_on` |
| `tyre_temp_c`, `tyre_psi`, `brake_temp_c` | graphics `tyre_lf / rf / lr / rr` `tyre_temperature_c`, `tyre_pressure`, `brake_temperature_c` (else physics `tyreCoreTemperature`, `wheelsPressure`, `brakeTemp`) | **not checked in the game yet** (November 2026): a pressure below 6 is taken as bar and shown in psi; the colour scales on the card (tyres green 80–100, yellow 115, red from 130 C; brakes green 300–650, red from 900 C) are a first guess (the owner: 111 C was still yellowish in the game's HUD on the tyre they drove), the game's normalised temperatures (`tyre_normalized_temperature_*`) are not used yet |
| `tyre_core_score`, `tyre_surface_score` | graphics `tyre_lf / rf / lr / rr` `tyre_normalized_temperature_core`, the highest of `tyre_normalized_temperature_left / center / right` | **Checked** in the Chevrolet Camaro ZL1 (9 November 2026): 1.0 = fine, rising to 2.0 when too hot (never below 1.0, also cold in the pits). The core score goes with `tyre_temperature_c` (the number on the card: 1.13 at 72.6 C, 1.33 at 76.6, 1.81 at 86.2); the surface temperatures react at once (2.0 at 100–170 C during burnouts while the core score stays 1.0). The ACE HUD colours the tile by the core score and the frame around it by the surface score: both green in the pits, frame red after burnouts; the TYRES card does the same. The frame is **not the pressure**: `tyre_normalized_pressure` (0.33 at 26 psi, 1.0 from 28 psi) is 0.33 in the pits while the HUD frame is green. **Tyre wear is not published** in ACE 0.9.1: physics `tyreWear` stays 0, and a byte-by-byte recording of all three blocks during burnouts and two resets to the pits found no other wear value (the HUD's grey bar beside each tyre, which rises with burnouts and resets in the pits, cannot be shown). The normalised temperatures (+108 / +112 / +116 left / centre / right, +124 core) rise from 1.0 to 2.0 when the tyre overheats |
| `wheel_slip`, `wheel_lock` | physics `slipRatio[4]` (−1 locked .. +3 clipped), graphics `tyre_lf / rf / lr / rr` `lock` | GRIP page. **Checked** in the BMW M4 GT3 Evo at Brands Hatch (9 November 2026, 3,600 frames): negative under braking (339 samples, none positive), positive on wheelspin (1,617, none negative), near 0 at part throttle (rear wheelspin in 1st gear at 20 km/h is real). A locked wheel reads −1, but the `lock` flag was **never set**, not even then: stage 4 comes from the slip alone. ABS starts to work at about 6.4 % slip, TC at about 7.1 %, and while they work the slip stays at 5–7 %: so the stages are 4 / 7 / 15 / 40 % (owner), stage 2 at that limit. Only 5–6 ABS / TC starts were recorded (both mostly off) |
| `drive_mode`, `drive_mode_name` | graphics `electronics.active_performance_mode` with its min / max / is_modifiable, `performance_mode_name` | BMW M4 CSL read in the game: 0, range 0..2, modifiable, name `SPORT+`; the name stays from the last car on cars without modes, so it is only sent with a mode. − / + not checked in the game yet |
| `session_id` | static `event_id`, `session_id`, `session`, `session_name` | a change starts a new analysis run |
| `air_c`, `road_c`, `tyre_compound`, `time_of_day` | physics `airTemp`, `roadTemp`, graphics `tyre_lf.tyre_compound_front`, graphics time of day | ambient line once per lap |

### To check in the game

- [ ] Gear, RPM, shift lights (`is_change_up_rpm` lights at the right moment), limiter.
- [ ] `rpm_percent` range (0..1 expected).
- [x] GRIP: `slipRatio` sign and size, the `lock` flag (never set), the stage limits (4 / 7 / 15 / 40 %). Open: whether the colours feel right on the iPhone, and the ABS / TC start slip with more stops with them on.
- [x] BOOST: `turbo_boost` in bar (M4 GT3 Evo up to 1.69 bar); `max_turbo_boost` 0.
- [ ] `status` numbers (pause and replay).
- [ ] TC / ABS / MAP levels and brake bias follow the in-game changes.
- [ ] Lights and wiper stages (ACE menu: up to 3 light stages, 5 wiper stages; the `ace | raw` log lines show the numbers).
  BMW M4 CSL (ACE 0.9.1, Nov 2026): the limit blocks say lights 0..2, wipers 0..4, but the live `instrumentation` block stayed all 0 (also `are_headlights_visible`, `flashing_lights` and `session_state.lights_on`) while Light Cycle +, Wiper Cycle + and Flashing Lights were pressed. The wipers did move in the game while `wiper_level` stayed 0, and no other byte of the graphics block changed with them. So ACE 0.9.1 does not publish the light / wiper state in shared memory (the overlay live-telemetry-evo also treats `instrumentation` as opaque); only the limit blocks are filled. The dashboard cannot read lights or wipers back from ACE for now.
- [ ] Keys: bind them as in [KEYS.md](KEYS.md) (ACE has no keyboard defaults for the car tab), then check each DASH card.
- [ ] Lap times, delta, position.
- [ ] Analysis fields (not verified at all): `npos` runs 0..1 and wraps at the line; `track_length_m` is filled; the `car_ids` / `player_car_id` match finds the player (else the dot and lines show another car); `steerAngle` is −1..1; the map is not mirrored; `session_id` stays the same while driving and changes with a new session. `/state` shows `lap_pos`, `pos_x`, `pos_y`, `steer`, `session_id`.
- [ ] Not used yet: `flag` / `global_flag` (the enum numbers are not published), the normalised tyre and brake temperatures.

`python tools/ace_probe.py` prints these values live; `--analysis` prints the analysis fields and every occupied car slot with its driver id (the `*` slot is the one used as the player).

The bridge also writes an `ace | raw | ...` line to the log whenever one of the rarely changing raw values changes: every `instrumentation` field (light and wiper stages, indicators, flash, hazards, display), the min..max range of `main_light_stage` and `wiper_level` on this car, and the seven `assists_state` flags by name. The first line after attaching lists them all. Switch lights or wipers in the game and the log shows which number each stage is.

## Controlling: keypresses

ACE has no input API; the dash box buttons are keypresses (`core/keys.py`, scan codes) to the ACE window (`AssettoCorsaEVO.exe`, title "Assetto Corsa EVO").

ACE has no keyboard defaults for the car controls (checked in the game, Nov 2026: Options → Controls → Car is empty). [KEYS.md](KEYS.md) has the proposed key for each ACE control; `game.toml` uses the same keys.

- Car tab (TC, TC CUT, ABS, ESC, engine map, performance mode, brake bias, pit limiter, lights, flash, wipers, ignition, starter): plain keys from KEYS.md, bound once in ACE.

If ACE ignores the keys: raise `[input] tap_ms` (e.g. 150), and check that ACE is the active window (windowed or borderless helps). A virtual joystick (vJoy) is the fallback if keypresses do not work for some actions.
