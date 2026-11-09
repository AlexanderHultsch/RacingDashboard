# Driving assists – matrix

Which driving assists and car electronics the games have, whether they are on/off or stepped, and – most important for the tablet buttons – whether they can be changed **while driving** (a key binding or an in-car menu) or only in a menu. Researched in November 2026 from official patch notes, manuals, support pages and community guides; see [Sources](#sources).

Game versions: Assetto Corsa EVO 0.9.1, Assetto Corsa Rally 0.6, BeamNG.drive 0.40, Project CARS 2, Forza Motorsport 6 (Xbox One; PC: "Apex"), DiRT Rally 2.0, iRacing 2026, Wreckfest 2 (Early Access, Content Update 9).

## Legend

| Mark | Meaning |
| --- | --- |
| **bold** | can be changed **while driving** (key binding or in-car menu): a tablet button can work |
| plain | only in a menu, the setup or the session settings: no tablet button |
| — | not in the game |
| on/off | two states |
| 3 steps, 1–12 | stepped, with the number of levels or the range |
| modes | named modes chosen by the car (e.g. sport / regular / off) |
| \* | only on cars that have it (real car electronics) |
| ? | not confirmed |

## Matrix

| Assist | AC EVO | AC Rally | BeamNG | Project CARS 2 | Forza M6 | DiRT Rally 2.0 | iRacing | Wreckfest 2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ABS | **steps\*** (about 1–10); menu aid ? | on/off + map 1–3 (setup) | 3 modes (realistic / arcade / off) | **steps\*** (ICM); menu aid levels ? | on/off (+ assisted braking) | on/off or steps ? | **1–12\*** (12 = off on GT3) | 3 steps (none / half / full) |
| Traction control | **steps\*** (about 0–10+) | on/off + map 1–3 (setup); in car ? | **modes\*** (ESC/TC mode) | **steps\*** (ICM, TC up/down ?); menu aid | on/off (combined with STM) | on/off or steps ? | **1–12\*** (+ toggle) | 3 steps |
| TC2 / TC cut | **steps\*** (up to 14) | — | — | ? | — | — | **steps\*** (TC2 on GTP, TCC/TCR on 911) | — |
| Stability control (ESC) | **steps\*** (about 3, road cars); menu aid 0–100 % | — | **modes\*** (with TC) | menu aid, levels ? | on/off (with TC) | on/off or steps ? | — | 3 steps |
| Launch control | **on/off\*** (procedure in car) | — | **on/off\*** (radial menu) | ? | — | on/off | **steps\*** (start RPM, F1) | — |
| Brake bias | **0.1 % steps** | setup; in car ? | setup | **steps** (ICM + key) | setup | setup | **steps\*** | setup ? |
| Brake migration / fine bias | **steps\*** (EBB, in-car menu) | — | — | — | — | — | **steps\*** (F1, GTP) | — |
| Engine map / power mode | **steps\*** + **3–4 performance modes\*** | setup | **modes\*** (drive modes) | **steps\*** | — | — | **steps\*** (map, mixture, throttle shape) | — |
| Engine braking | ? | — | — | — | — | — | **steps\*** (F1) | — |
| Differential | **steps\*** (in-car menu) | — | **modes\*** (diff, 4WD, low range) | setup | setup | setup | **steps\*** (F1: entry / mid / high speed) | setup |
| Anti-roll bar / weight jacker | setup | setup | setup | **steps** (key) | setup | setup | **steps\*** | setup |
| ERS / hybrid | **modes\*** | — | — | **on/off\*** (KERS) | — | — | **modes\*** (5 deploy modes) | — |
| DRS / push-to-pass | ? | — | — | **on/off\*** | — | — | **on/off\*** | — |
| Pit limiter | **on/off**; auto aid on/off | — | **on/off\*** (speed limiter) | **on/off** | — (automatic pits) | — | **on/off**; auto aid on/off | — |
| Ignition / starter | **on/off** | auto start (menu) | **on/off** | ? | — | — | **on/off**; auto start (menu) | — |
| Gearbox automatic / manual | on/off (+ key: H-shifter to sequential) | on/off | **on/off** (key Q) | on/off | 3 modes (+ manual with clutch) | modes (to H-pattern with clutch) | shift aid levels | 3 modes (+ manual with clutch) |
| Auto clutch | on/off (+ clutch on start) | on/off | on/off | on/off | in gearbox setting | on/off (clutch override) | in shift aid | in gearbox setting |
| Auto blip | on/off | — | on/off (rev match) | — | — | — | in shift aid | — |
| Anti-stall / start assist | on/off | — | through clutch assist | — | — | — | in shift aid | — |
| Steering assist | gamepad only (off / assisted + %) | gamepad only | understeer 0–100 %, oversteer 0–200 % | on/off | 3 modes ? | — | — | — |
| Braking / throttle assist | — | — | — | braking on/off | in ABS setting (assisted) | off-throttle braking on/off | braking on/off, throttle on/off | — |
| Racing line | on/off | — | — | on/off (levels ?) | 3 modes (full / braking / off) | — | on/off | — |
| Damage | rate (single player) | on/off | always on | steps ? | 3 modes ? | normal / hardcore ? | host setting | 2 modes (normal / realistic) |
| Rewind / reset | — | — | **in car** (repair / rewind) | — | on/off (rewind button) | — | — | **reset in car** |

## What this means for the tablet

- **Changeable while driving:** AC EVO (most complete, binding names known), iRacing (rich but per car), Project CARS 2 (in-car menu "ICM" plus keys; names not confirmed), BeamNG (mode toggles, differential / 4WD, gearbox mode).
- **Menu only:** Forza Motorsport 6, DiRT Rally 2.0, Wreckfest 2, and mostly AC Rally. A tablet cannot change their assists while driving; at most it can show them if the game reports them.
- **Relative buttons:** ranges differ per game and per car (iRacing GT3: TC 12 = off; AC EVO: up to 14 TC cut steps), so the universal buttons should send **+ / −** (and toggles), not absolute values.
- **Missing in the universal actions today** (`core/actions.py`): ERS mode, DRS / push-to-pass, launch control, differential, brake migration, engine braking, anti-roll bar, ESC/TC mode toggle and gearbox mode toggle (BeamNG).

## Not confirmed

- AC EVO: the options of the ABS / TC master switch in the assist menu; key names for EBB, differential, turbo, engine braking; DRS.
- AC Rally: the binding names are now known from the game's input settings (November 2026: IncreaseTc / DecreaseTc, IncreaseAbs / DecreaseAbs on newer cars, brake bias increments, CycleLights, CycleWipers, StartStopEngine, Respawn; see [ACR/NOTES.md](ACR/NOTES.md)); their default keys and the number of engine map levels are not documented.
- BeamNG: the ABS mode names (from players), whether the ESC/TC key also cycles drive modes, launch control activation.
- Project CARS 2: the exact binding names (TC up/down, engine mode up/down, ABS / TC / SC toggles), the levels of the menu aids, launch control, racing line levels, damage modes.
- Forza Motorsport 6: the full option lists of steering, braking and TC / STM; whether assists can be changed from the pause menu.
- DiRT Rally 2.0: whether ABS / TC / SC are on/off or stepped (sources disagree); whether they can be changed from the pause menu (true for DiRT Rally 1).
- iRacing: a headlight on/off binding (only "Headlight Flash" confirmed); ESC on any car; hybrid deploy on GTP cars (mostly automatic since 2025 Season 4, per one article).
- Wreckfest 2: assists in the pause menu; whether "anti-spin" is a separate assist; a brake balance slider in tuning.

## Related games (short notes)

- **Project CARS 1:** real-world assists toggle plus ABS / TC / SC on/off; fewer in-car electronics. **Project CARS 3:** arcade-leaning, adds rewind (both not fully confirmed).
- **Forza Motorsport (2023, PC):** more steps (TC off / sport / on, STM sport / off / on, partial / full braking, throttle and steering assists), still menu only. **Forza Horizon:** similar, menu only.
- **DiRT Rally (2015):** ABS / TC / SC, changeable in the pause menu (Feral FAQ).
- **Wreckfest (2018):** ABS / TC / SC and gearbox modes in the garage / pre-race menu only.

## Sources

- AC EVO: Steam patch notes (store.steampowered.com/news/app/3058630); assetto-corsa-evo.fandom.com/wiki/Keybinds and /wiki/Car_Features; coachdaveacademy.com/tutorials/ultimate-assetto-corsa-evo-controller-settings/; traxion.gg/nine-tips-to-get-the-best-out-of-assetto-corsa-evo/; Steam discussions 797842031905909442, 756142145462608776, 727997287883622313.
- AC Rally: Steam patch notes (store.steampowered.com/news/app/3917090); coachdaveacademy.com/tutorials/beginners-guide-to-ac-assetto-corsa-rally/; Steam discussions 685237458700609408, 685237458700573812, 568162889929717062.
- BeamNG.drive: documentation.beamng.com/modding/input/default-keyboard-bindings/; documentation.beamng.com/getting_started/beginner-guide/; beamng.com/game/news/patch/beamng-drive-v0-40/ and v0-39; Steam discussions (app 284160) 3108022489662680202, 2789318172123925279.
- Project CARS 2: thesixthaxis.com (Project CARS 2 on a controller, 2017); gtplanet.net/project-cars-2-preview/; player.one Project CARS 2 review; spottis.com/games/project-cars-2-controls/; Steam discussions (app 378860); solox.gg/project-cars-2-assists-ai-difficulty-settings/.
- Forza Motorsport 6: xona.com/2015/09/11.html; supercheats.com/forza-6/walkthrough/before-you-tune; shacknews.com (FM6 Apex wheel support); gamerant.com/forza-motorsport-best-racing-settings-beginners/.
- DiRT Rally 2.0: pushsquare.com (DiRT Rally 2.0 tips, 2020); gamepressure.com/dirt-rally-20/driving-basics-tips-and-controls/; simwiki.net/wiki/Dirt_Rally_2.0; feralinteractive.com DiRT Rally FAQ.
- iRacing: support.iracing.com articles 31000133499 (driving aids), 31000133517 (controls), 31000170165 (pit macros), 31000159166 (hosted sessions); iracing.com/keyboard-shortcuts/; iracing.com/resources/user-manuals/ (Mercedes-AMG GT3, BMW M4 GT3, BMW M Hybrid V8, W12, SF23, IR18, Porsche Cup 992.2, NASCAR Next Gen).
- Wreckfest 2: Steam patch notes (app 1203190); thqnordic.com/news/wreckfest-content-update-9-full-changelog; Steam discussion 603026099853596046.
