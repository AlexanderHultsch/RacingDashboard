# iRacing – Notes

How the dashboard reads iRacing and what is still to be checked in the sim. Connector: `games/iracing/connector.py`; keys and window: `games/iracing/game.toml`; dash box: `games/iracing/dash.toml`. Built in November 2026 from iRacing's SDK headers and open-source readers; **not run against the sim yet**.

## Reading: the irsdk shared memory

iRacing publishes one named block, `Local\IRSDKMemMapFileName` (opened with `OpenFileMappingW`, `core/winmem.py`, mapped whole). Layout from iRacing's BSD-licensed `irsdk_defines.h` (SDK 1.19 / 1.20, mirrored in open-source projects because the official download sits behind the members' forum) and [pyirsdk](https://github.com/kutu/pyirsdk):

| Part | Content |
| --- | --- |
| Header (112 bytes) | `ver`, `status` (bit 0 = connected), `tickRate`, `sessionInfoUpdate`, `sessionInfoLen`, `sessionInfoOffset`, `numVars`, `varHeaderOffset`, `numBuf`, `bufLen`, then (SDK 1.20) `curBufTickCount`, `curBuf`, and at byte 48 four buffer records (`tickCount`, `bufOffset`, `tickCountBegin`, pad) |
| Variable headers (144 bytes each) | `type` (0 char, 1 bool, 2 int, 3 bitfield, 4 float, 5 double), `offset` in a row, `count`, `countAsTime`, `name[32]`, `desc[64]`, `unit[32]` |
| Session info | YAML text (UTF-8 when `WeekendInfo: Encoding: UTF8`, else cp1252), re-read when `sessionInfoUpdate` changes |
| Data buffers | one row of all variables per tick (60 Hz), up to 4 rotating buffers |

The connector takes the buffer with the highest `tickCount`, copies it, and accepts the copy when `tickCount` is unchanged afterwards (and equals `tickCountBegin` where the sim writes it); two tries per read. The variable list is fixed for a session but differs per car, so every value is looked up by name; a missing variable is `None` (the dash card greys out: "not on this car"). The session YAML is read by a small parser (`parse_yaml`, standard library only) that understands what iRacing writes: maps by indentation and lists of maps with `- ` at the indent of their key.

### Field mapping

| Universal | iRacing source | Note |
| --- | --- | --- |
| `status` | `IsReplayPlaying`, `IsOnTrack` | replay; live while the player is in the car on track; else `off` (garage, menus: NOT ON TRACK). Header bit 0 off = GAME NOT RUNNING |
| `car`, `track` | YAML `DriverInfo:Drivers[CarIdx = DriverCarIdx]:CarScreenName`; `WeekendInfo:TrackDisplayName` (+ ` - TrackConfigName`) | |
| `gear`, `max_gears` | `Gear`; YAML `DriverCarGearNumForward` | −1 R, 0 N |
| `rpm`, `rpm_max`, `rpm_pct` | `RPM`; YAML `DriverCarRedLine` | |
| `shift_up` | YAML `DriverCarSLShiftRPM` | the car's own shift light point |
| `limiter`, `pit_limiter` | `EngineWarnings` bits 0x20, 0x10 | |
| `speed_kmh`, `gas`, `brake`, `clutch` | `Speed` (m/s), `Throttle`, `Brake`, `Clutch` | iRacing's clutch is 1 = engaged (pedal up): the dashboard shows `1 − Clutch` |
| `tc_level`, `tc_cut_level`, `abs_level` | `dcTractionControl`, `dcTractionControl2`, `dcABS` | only on cars that have them; ranges per car (not reported: no level dots) |
| `abs_active` | `BrakeABSactive` | iRacing reports no "TC is cutting now" flag |
| `wheel_slip` | – | iRacing's live data has no slip or speed per wheel: the GRIP page shows only the ABS / TC settings and says "IRACING SENDS NO WHEEL SLIP" |
| `brake_bias` | `dcBrakeBias` | percent on most cars (54.5 = 54.5 % front); values outside 20–90 % are shown as not reported. **To check per car** |
| `engine_map` | `dcThrottleShape`, else `dcFuelMixture` | iRacing has no `dcEngineMap`; which knob a car's MAP is differs per car. **To check** |
| `engine_running`, `warn_*` | `EngineWarnings` | 0x08 stalled → engine yellow; 0x04 oil pressure → oil red, 0x40 oil temperature → oil yellow; 0x01 water temperature → coolant yellow; brake not reported |
| `fuel_l`, `fuel_max_l` | `FuelLevel`; YAML `DriverCarFuelMaxLtr` | |
| `lap`, `position` | `LapCompleted`, `PlayerCarPosition` | |
| `lap_ms`, `last_ms`, `best_ms`, `delta_ms` | `LapCurrentLapTime`, `LapLastLapTime`, `LapBestLapTime`, `LapDeltaToBestLap` (when `LapDeltaToBestLap_OK`) | seconds → ms |
| `lap_valid` | `PlayerTrackSurface` | iRacing has no live "lap invalid" flag: off track (0, four wheels off) invalidates the lap for the analysis page |
| `lap_pos`, `lap_progress` | `LapDistPct` | |
| `track_length_m` | YAML `TrackLengthOfficial`, else `TrackLength` | "4.33 km" |
| `pos_x`, `pos_y` | dead reckoning from `VelocityX` / `VelocityY` (car frame) and `YawNorth` over `SessionTime` | iRacing's live telemetry has no position (`Lat` / `Lon` are only in `.ibt` files). The position starts at 0 / 0 at the line every lap, so laps line up and drift does not build up; north is up on the map. The sign of `VelocityY` (left positive, as MarvinsAIRA measured) is **to check**: a mirrored corner means it is the other way |
| `steer` | `SteeringWheelAngle / SteeringWheelAngleMax` | sign **to check** (−1 left, +1 right expected) |
| `session_id` | YAML `SessionID`, `SubSessionID`, live `SessionNum` | a new session starts a new analysis run |
| `air_c`, `road_c`, `time_of_day` | `AirTemp`, `TrackTempCrew`, `SessionTimeOfDay` | |

### To check in the sim

- [ ] Process name `iRacingSim64DX11.exe` and window title (keypresses refuse with "game window not found" if wrong).
- [ ] Gear, RPM, shift light point, limiter; TC / ABS / brake bias / engine map follow the in-car changes (and what `dcBrakeBias` reports on two or three cars).
- [ ] The map on the analysis page is the track, not mirrored (`VelocityY` sign) and the steering sign.
- [ ] `lap_valid`: is "four wheels off" the right rule for the owner's practice sessions?
- [ ] `session_id` stays the same while driving and changes with a new session.

## Controlling: keypresses

iRacing's keyboard defaults ([iracing.com/keyboard-shortcuts](https://www.iracing.com/keyboard-shortcuts/)): **S** starter, **I** ignition, **A** pit speed limiter, **=** / **−** brake bias increase / decrease. Traction control, ABS, engine map, headlight flash and wipers have **no default**: bind the proposed keys in iRacing (Options → Controls, in-car adjustments) or put your own in `[games.iracing.keys]` of `config/config.toml`.

| iRacing control | Dashboard button | Key |
| --- | --- | --- |
| Traction control − / + | TC − / + | `Num7` / `Num8` (proposal) |
| Traction control 2 − / + | TC 2 − / + | `Num4` / `Num5` (proposal) |
| ABS − / + | ABS − / + | `Num1` / `Num2` (proposal) |
| Throttle shape / engine map − / + | ENGINE MAP − / + | `NumMinus` / `NumPlus` (proposal) |
| Brake bias decrease / increase | BRAKE BIAS REAR / FRONT | `−` / `=` (default) |
| Pit speed limiter | PIT LIMITER | `A` (default) |
| Ignition | IGNITION (tap) | `I` (default) |
| Starter | STARTER (held) | `S` (default) |
| Headlight flash | FLASH (held) | `PageUp` (proposal) |
| Windshield wipers / tear-off | WIPERS | `U` (proposal) |

iRacing's broadcast messages (`IRSDK_BROADCASTMSG`) cover camera, replay, chat, pit service, telemetry recording and force feedback only: none changes TC, ABS, brake bias, the limiter or the starter, so the dashboard uses keypresses.

## Dash box

TC, TC 2, ABS (amber while ABS works), ENGINE MAP, BRAKE BIAS, FUEL, PIT LIMITER, IGNITION, STARTER (held), FLASH (held), WIPERS, WARNINGS (engine, oil, coolant; brake not reported). Cards for settings a car does not have are greyed out.
