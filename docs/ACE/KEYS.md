# Assetto Corsa EVO – key bindings for the dashboard

The iPad buttons are keypresses. ACE has **no keyboard defaults** for the car controls (first test, Nov 2026: every row on Options → Controls → Car was empty, only Horn had a controller button), so each key below has to be bound once in ACE. The keys are already set in `games/ace/game.toml`; bind the same ones in ACE.

The names in the first column are written exactly as ACE shows them. All proposals are plain keys without Ctrl / Shift, so it does not matter whether ACE accepts key combinations. They sit on the numpad, PageUp / PageDown and a few letters. Insert, Home, Delete and End are not used: ACE did not take them when binding (Home showed as `$`, Delete as `.`).

**How to bind:** in ACE open Options → Controls → Car, click the keyboard field (the dark box) next to the row and press the key. Or, with the bridge running, tap the matching iPad button while ACE waits for the key: the bridge then sends exactly the key it will use later.

## 1. Needed for the DASH page (bind these)

| ACE control (tab Car) | Dashboard button | Key |
| --- | --- | --- |
| Traction Control Cycle − | TC − | `Num7` |
| Traction Control Cycle + | TC + | `Num8` |
| Traction Control Cut Cycle − | TC CUT − | `Num4` |
| Traction Control Cut Cycle + | TC CUT + | `Num5` |
| ABS Cycle − | ABS − | `Num1` |
| ABS Cycle + | ABS + | `Num2` |
| ESC Cycle − | STABILITY − | `Num0` |
| ESC Cycle + | STABILITY + | `NumDecimal` |
| Engine Map Cycle − | ENGINE MAP − | `NumMinus` |
| Engine Map Cycle + | ENGINE MAP + | `NumPlus` |
| Brake Bias Rear | BRAKE BIAS REAR | `NumDivide` |
| Brake Bias Front | BRAKE BIAS FRONT | `NumMultiply` |
| Pit Limiter Toggle | PIT LIMITER | `P` |
| Light Cycle + | LIGHTS | `Num9` |
| Flashing Lights | FLASH (held) | `PageUp` |
| Wiper Cycle + | WIPERS (on / off) | `U` |
| Toggle Ignition | IGNITION | `I` |
| Starter | START (held) | `PageDown` |

ACE acts on Wiper Cycle + only while the key is held (a tap wipes once), so WIPERS is a latch: one tap holds `U` down until the next tap (`[kinds]` in `game.toml`). Toggle Ignition also works only while held: hold the IGNITION button a few seconds. If LIGHTS turns out to work the same way, try `lights = "latch"` under `[games.ace.kinds]` in `config/config.toml`.

On the numpad each setting is a pair, − on the left and + on the right: TC on 7 / 8, TC CUT on 4 / 5, ABS on 1 / 2, STABILITY on 0 / decimal point, ENGINE MAP on − / +, BRAKE BIAS on / (rear) and * (front), LIGHTS on 9. Letters: P pit limiter, U wipers, I ignition. Num Lock should be on.

## 2. Useful extras (BUTTONS page, bind if you want them)

| ACE control (tab Car) | Dashboard button | Key |
| --- | --- | --- |
| Left Direction Indicator | IND LEFT | `Comma` |
| Right Direction Indicator | IND RIGHT | `Period` |
| Hazard Lights | HAZARDS | `Slash` |
| Horn | HORN (held) | `Backslash` (keyboard field; your controller button RSB can stay) |
| Display Page Cycle + | DISPLAY PAGE | `NumEnter` |

## 3. Not needed

- Formula / hybrid controls: RS Deployment Map, MGU-Heat Mode, ERS Overtake, DRS Activate, Turbo Level Cycle.
- Damper Front / Rear Bump / Rebound Cycle, EBB Map Cycle, Performance Mode Cycle, Display Device Cycle, FFB Gain, Cycle / Pitch / Yaw / FOV Mirror, Optional Animation, Retractable Headlights Toggle, Rain Lights.
- Light Cycle −, Wiper Cycle −: only if Light Cycle + / Wiper Cycle + stop at the last stage instead of wrapping round to off (see section 5).
- The tab **Car Advanced** (one key per stage: Light Stage 1–3, Traction Control 1–15, Traction Control Cut 1–15, ABS Stage 1–8 or more, Engine Map Stage 1–10, ESC Stage 1–10, Performance Mode 1–10, Display Page 1–5, Wipers Stage 1–5). The dashboard steps with − / +, so these are not needed. They tell us the ranges, though (section 4).
- Differential Power / Coast Cycle − / +: the DIFF card only shows the values for now. ACE does have bindings for them, so the card could become two steppers later.

## 4. What the ACE menu tells us

- **The window is right.** The bridge sent every iPad press to the game window and refused none, so the process name `AssettoCorsaEVO.exe` is correct.
- **Stages per setting (the most any car can have):** lights 3, wipers 5, TC 15, TC CUT 15, ABS at least 8, engine map 10, ESC 10, performance mode 10, display pages 5. The real range per car comes from the game's limit blocks; the `ace | raw` log lines show the light and wiper range of the car you drive.
- **ACE has no keyboard defaults for the car tab.** The `AC` key defaults in `game.toml` (lights `L`, TC `LCtrl+T`, ABS `LCtrl+A`) were wrong for ACE and are replaced by the keys above.
- **Insert, Home, Delete and End do not work in ACE bindings** (Home showed as `$`, Delete as `.`), so pit limiter, lights, wipers and ignition use `P`, `Num9`, `U` and `I`.

## 5. What to check after binding (one drive)

Restart the bridge first, so the new keys and the `ace | raw` log lines are active.

1. **Each DASH card:** tap − / + and check that the car changes and the card shows the new value. A card that changes in the game but not on the iPad means a reading problem, so note which one.
2. **LIGHTS and WIPERS:** tap several times. Does it go round to off after the last stage, or stop there? Which stage is which (off, parking, low beam, high beam ...)? The log shows the number for each stage (`ace | raw | main_light_stage 0->1`).
3. **FLASH and START:** these are held as long as your finger is on the button. Does the starter crank while held, and does the engine start?
4. **IGNITION:** does one tap switch it on and the next off?
5. **ACE says a key is already used** (if it warns): pick another key and tell me, or put it in `config/config.toml` under `[games.ace.keys]`.
6. **Nothing happens at all:** ACE must be the active window (the bridge brings it to the front). If presses are too short for ACE, raise `[input] tap_ms` in `config/config.toml` (for example to 150).

The VIEW and PIT buttons (camera, HUD, mirror, look left / right, leaderboard, shift, auto shift) keep their old guesses. They live on other ACE tabs that have not been checked yet.
