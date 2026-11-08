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
| `tc_level`, `tc_cut_level`, `abs_level`, `esc_level`, `engine_map`, `diff_power`, `diff_coast` | graphics `electronics.*_level` | `None` when `electronics_is_modifiable` says the car has no setting |
| `limits` | graphics `electronics_min_limit` / `electronics_max_limit` | per setting the car has |
| `launch`, `auto_clutch` | graphics `launch_active`, `assists_state.auto_clutch` | |
| `esc_active` | graphics `esc_active` | |
| `warn_brake` | graphics `handbrake_percent` | red while the handbrake is pulled (> 5 %) |
| `warn_engine` | graphics `is_ignition_on`, `is_engine_running` | yellow with ignition on and engine off; red when the coolant is overheating |
| `warn_oil` | graphics `oil_pressure_bar`, `oil_temperature_c` | red with the engine off (no pressure) or below 0.5 bar; yellow from 135 °C |
| `warn_coolant` | graphics `water_temperature_c` | blue below 50 °C, yellow from 108 °C, red from 118 °C; all lamps off with ignition off. Thresholds follow road-car dashes and are not verified in ACE |
| `gear_mode` | graphics `assists_state.auto_gear` | `D` while the automatic gearbox assist is on; ACE reports no P / S selector, sport mode or electric drive yet (`engine_type` numbers unpublished) |
| `tc_active`, `abs_active` | graphics `tc_active` / `abs_active` or physics `tcInAction` / `absInAction` | |
| `brake_bias` | physics `brakeBias` | 0.56 = 56 % front |
| `pit_limiter` | physics `pitLimiterOn` or `electronics.is_pitlimiter_on` | |
| `ignition`, `engine_running` | graphics `is_ignition_on`, `is_engine_running` | |
| `lights`, `wipers` | graphics `instrumentation.main_light_stage`, `wiper_level` | |
| `fuel_l`, `fuel_max_l`, `fuel_per_lap_l` | graphics `fuel_liter_current_quantity`, `max_fuel`, `fuel_liter_per_lap` (or `fuel_per_lap`) | |
| `lap_ms`, `last_ms`, `best_ms`, `delta_ms` | graphics `current_lap_time_ms`, `last_laptime_ms`, `best_laptime_ms`, `delta_time_ms` | 0 or `INT_MAX` = no time |
| `lap`, `position`, `cars`, `lap_valid` | graphics `total_lap_count`, `current_pos`, `total_drivers`, `is_valid_lap` | |
| `car`, `track` | graphics `car_model`, static `track` | |
| `status` | graphics `status` | assumed as in AC / ACC: 0 off, 1 replay, 2 live, 3 pause |

### To check in the game

- [ ] Gear, RPM, shift lights (`is_change_up_rpm` lights at the right moment), limiter.
- [ ] `rpm_percent` range (0..1 expected).
- [ ] `status` numbers (pause and replay).
- [ ] TC / ABS / MAP levels and brake bias follow the in-game changes.
- [ ] Lights and wiper stages.
- [ ] Lap times, delta, position.
- [ ] Not used yet: `flag` / `global_flag` (the enum numbers are not published), tyre data.

`python tools/ace_probe.py` prints these values live.

## Controlling: keypresses

ACE has no input API; the buttons are keypresses (`core/keys.py`, scan codes) to the ACE window (`AssettoCorsaEVO.exe`, title "Assetto Corsa EVO").

ACE's keyboard defaults could not be confirmed from a public source (Nov 2026; the lists found online are for the original Assetto Corsa). So `game.toml` uses:

- `AC` keys: defaults of the original AC that ACE probably kept: lights `L`, horn `H`, look left / right `Q` / `W`, shift `Z` / `X`, camera `F1`, leaderboard `F7`, mirror `F8`, auto shifter `LCtrl+L`, TC `LCtrl+T`, ABS `LCtrl+A` (in AC these two cycle / toggle).
- `set` keys: `LCtrl+LShift+<letter>` proposals for actions without a known default (TC / ABS down, stability − / +, brake bias, engine map, pit limiter, flash, wipers, ignition, starter, indicators, hazards, HUD, look back, display page). Bind them in ACE under Options → Controls, or change them in `config/config.toml` to the keys you use.
- `NEUTRAL` and `SAVE REPLAY` have no key yet (greyed out).

If ACE ignores the keys: raise `[input] tap_ms` (e.g. 150), and check that ACE is the active window (windowed or borderless helps). A virtual joystick (vJoy) is the fallback if keypresses do not work for some actions.
