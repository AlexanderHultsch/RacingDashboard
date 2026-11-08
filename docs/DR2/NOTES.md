# DiRT Rally 2.0 – Notes

How the dashboard reads DiRT Rally 2.0 and what is still to be checked in the game. Connector: `games/dr2/connector.py`; keys, window and UDP port: `games/dr2/game.toml`; dash box: `games/dr2/dash.toml`.

## Turn the telemetry on (once)

Edit `Documents\My Games\DiRT Rally 2.0\hardware_settings\hardware_settings_config.xml` (start the game once so the file exists) and set the `udp` line to:

```xml
<udp enabled="true" extradata="3" ip="127.0.0.1" port="20777" delay="1" />
```

At start the connector looks for this file (also in a OneDrive "Documents" folder) and logs `dr2 | config | ...`: "UDP telemetry on (extradata 3)", or what is wrong (off, wrong extradata, other port). Another tool on port 20777 (SimHub, a motion rig) and the dashboard cannot both receive the packets: forward them, or give the dashboard another port in `[games.dr2.udp]` of `config/config.toml` and in the XML.

## Reading: UDP telemetry

The game sends a packet of little-endian 32-bit floats per frame while driving (nothing in the menus). `extradata="3"` gives 264 bytes; the connector needs at least 256 and logs once when shorter packets arrive. Byte offsets up to 252 follow the cm-telemetry parser ([rally2.rs](https://docs.rs/cm-telemetry/latest/src/cm_telemetry/dirt/rally2.rs.html)); max rpm (252), idle rpm (256) and the gear count (260) follow the common 66-float layout.

| Universal | Byte | Note |
| --- | --- | --- |
| `gear` | 132 | float; negative = R, 0 = N, 1.. forward. 10 is also taken as R when the car has fewer than 10 gears (reported for some builds) |
| `rpm`, `rpm_max`, `rpm_pct` | 148, 252 | some builds send the rate as rpm / 10: a max below 2000 is scaled by 10 |
| `shift_up`, `limiter` | – | the game sends no shift signal: shift light from 94 % of max rpm (not in top gear), limiter from 99 % |
| `speed_kmh` | 28 | m/s × 3.6 |
| `gas`, `brake`, `clutch` | 116, 124, 128 | 0..1 |
| `lap_ms`, `last_ms` | 4, 248 | stage time, seconds |
| `lap_progress` | 8 / 244 | distance driven / stage length |
| `lap`, `position` | 144, 156 | |
| `max_gears` | 260 | |
| `lap_pos`, `track_length_m` | 8 / 244, 244 | analysis: one stage = one lap; the stage starts standing and ends when the car stays at the end |
| `pos_x`, `pos_y` | 16, 24 | world x and z, metres (the map may come out mirrored) |
| `steer` | 120 | −1..1 |
| `session_id` | – | `stage-<length>`: a new stage length starts a new analysis run |

Not in the packet (or always 0 in DiRT Rally 2.0): car and track name, fuel, ABS / TC level, light and wiper state, warning lamps. After 2 s without packets the pages show "NO NEW DATA FROM THE GAME", after 10 s "GAME NOT RUNNING" (the game sends nothing in the menus either).

### To check in the game

- [ ] Gear values in reverse and neutral.
- [ ] RPM: scaled by 10 or not (the log and `/state` show the values).
- [ ] Stage progress reaches 100 % at the finish (the analysis needs ≥ 99.95 % to end the stage lap).
- [ ] Analysis: position x / z gives the right map (not mirrored), steering sign, a restart jumps the distance back to 0.

## Controlling: keypresses

ABS, TC and stability control can only be changed in the assist menu (see [ASSISTS.md](../ASSISTS.md)). While driving the dashboard sends: LIGHTS (`H`), WIPERS (`W`), RECOVER (`F2`, back on the road, costs time), PAUSE (`Esc`). These are commonly listed keyboard defaults and not verified: check them under Options > Controls > Keyboard and change them in `[games.dr2.keys]` of `config/config.toml`.

## Dash box

STAGE TIME, STAGE (progress in % with a bar) and SPEED (value cards), LIGHTS and WIPERS (push buttons: the game does not report their state), RECOVER (push button that fires only after being held for 1 s, so it cannot be hit by accident).
