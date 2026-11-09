# Assetto Corsa Rally – Notes

How the dashboard reads Assetto Corsa Rally (ACR, Early Access 0.6, Unreal Engine 5) and what is still to be checked in the game. Connector: `games/acr/connector.py`; keys and window: `games/acr/game.toml`; dash box: `games/acr/dash.toml`. Built in November 2026 from the notes and code of tools that read ACR; **not run against the game yet**.

## Reading: shared memory (ACC layout)

ACR does **not** use the Assetto Corsa EVO layout. It publishes the classic Kunos blocks with the **ACC** structs (UTF-16 strings, 4-byte alignment): `Local\acpmf_physics` (800 bytes, the physics page shared with ACE, `core/kunos.py`), `Local\acpmf_graphics`, `Local\acpmf_static`. Kunos has published no ACR documentation; the notes come from SimHub (ACR support since 9.10.9, November 2025), [live-telemetry-evo](https://github.com/albertowd/live-telemetry-evo), [acr-overlay](https://github.com/FlorentDChamps/acr-overlay), [MarvinsAIRA](https://github.com/mherbold/MarvinsAIRARefactored), [ZTMZ Pacenote](https://github.com/strawhatboy/ztmz_pacenote), [nobonobo/ac-telemetry](https://github.com/nobonobo/ac-telemetry), [acr_telemetry](https://github.com/decnet100/acr_telemetry) and [PacenotePal](https://github.com/Koenvh1/PacenotePal).

AC1 and ACC publish the **same block names**, so the connector attaches only while `acr.exe` runs (`winmem.process_running`); otherwise it would read another game's data with the wrong layout.

ACR fills only part of the pages: physics (pedals, gear, rpm, speed, steering, brake bias, fuel, temperatures in **Kelvin**, the clutch with 1 = pedal up, current max rpm at byte 588), graphics (the stage clock **as text** `mm:ss.fff`, the distance along the stage, the player's world position in slot 0, TC and ABS levels) and static (car, stage name in the game's language, stage length `trackSplineLength`). Status, session, laps, flags, damage, handbrake, lights and wipers stay empty. In the pause menu the physics page is blanked (or frozen) while its packet counter runs on; on the results screen the graphics page freezes.

### Field mapping

| Universal | ACR source | Note |
| --- | --- | --- |
| `status` | physics | `pause` when the physics page is blank (rpm, gear, speed and pedals all 0), else `live`; the graphics status is not used (ACR writes AC_OFF while driving) |
| `car`, `track` | static `carModel`, `track` | the stage name is in the game's language |
| `gear` | physics `gear` − 1 | ACC: 0 = R, 1 = N, 2 = 1st |
| `rpm`, `rpm_max`, `rpm_pct` | physics `rpms`; static `maxRpm`, else physics `currentMaxRpm` | |
| `shift_up`, `limiter` | – | ACR sends no shift signal: from 94 % / 99 % of max rpm |
| `speed_kmh`, `gas`, `brake`, `clutch` | physics | clutch shown as `1 − clutch` |
| `tc_level`, `abs_level` | graphics `TC`, `ABS` | adjustable on newer cars only |
| `tc_active`, `abs_active` | physics `tc`, `abs` (above 0) | **to check** (sources disagree) |
| `brake_bias` | physics `brakeBias` | front share |
| `fuel_l`, `fuel_max_l` | physics `fuel`, static `maxFuel` | ACR models no fuel use (0.2) |
| `lap_ms`, `last_ms` | graphics `currentTime`, `lastTime` (text) | the integer clocks are empty in ACR |
| `lap_pos`, `lap_progress`, `track_length_m` | graphics `distanceTraveled` / static `trackSplineLength` | one stage = one lap; the distance is re-projected every frame and may step back a little |
| `pos_x`, `pos_y` | graphics `carCoordinates[0]` x and z | |
| `steer` | physics `steerAngle` | −1 left … 1 right |
| `session_id` | `acr-<stage length>` | a new stage starts a new analysis run |
| `air_c`, `road_c` | physics `airTemp`, `roadTemp` | Kelvin → °C |

### To check in the game

- [ ] The connector attaches (log `acr | shared memory | attached ...`) and the values follow the car; the process name (`acr.exe`).
- [ ] Stage start and finish on the analysis page: the distance along the stage may not line up with the start and finish lines (ZTMZ found that), so the stage-end rule (progress ≥ 99.95 % for 1 s) may not fire. Check one complete stage with `python tools\analysis_check.py --last 1`.
- [ ] `tc_active` / `abs_active` and the TC / ABS levels on a car that has them.
- [ ] The pause detection (blank physics) and the map orientation.

## Controlling: keypresses

ACR's keyboard defaults are not documented, so every key is a proposal to bind once in the game (Options → Controls). The game's bindable actions (read from its input settings by d200x-button-box): IncreaseTc / DecreaseTc, IncreaseAbs / DecreaseAbs (newer cars), brake bias increments, CycleLights, CycleWipers, StartStopEngine (one action, no separate ignition and starter), Respawn (works only with Free Practice → Session Settings → "Manual Respawn" on), Pause.

| ACR action | Dashboard button | Key (proposal) |
| --- | --- | --- |
| DecreaseTc / IncreaseTc | TC − / + | `Num7` / `Num8` |
| DecreaseAbs / IncreaseAbs | ABS − / + | `Num1` / `Num2` |
| Brake bias rear / front | BRAKE BIAS | `NumDivide` / `NumMultiply` |
| CycleLights | LIGHTS | `Num9` |
| CycleWipers | WIPERS | `U` |
| StartStopEngine | ENGINE | `I` |
| Respawn | RECOVER (held 1 s) | `R` |
| Pause | PAUSE | `Esc` |

## Dash box

TC and ABS (amber while working; greyed on cars without them), BRAKE BIAS, STAGE TIME, STAGE (progress in % with a bar), SPEED, LIGHTS, WIPERS, ENGINE (start / stop), RECOVER (held 1 s so it cannot be hit by accident).
