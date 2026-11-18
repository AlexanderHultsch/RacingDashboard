# AI coach – data and corner knowledge

The per-sample analysis pipeline (every sample labelled with phase and Good / Potential / Bad, saved per session for an AI) is in [PIPELINE.md](PIPELINE.md).

How the AI trainer ([TRAINER.md](TRAINER.md)) gets what it needs to coach on any track, car and game. **Owner's decision (18 November 2026): no fixed phases, scenarios or thresholds in the code.** The bridge records the car's motion and sends clean measurements, each relative to the car's own limits; the AI judges with its racing knowledge. The prompt and the analysis are then fine-tuned with real answers.

Built 18 November 2026: the new values in the games, the recorder and the trainer (sections 1 and 2). Sections 3–7 are the knowledge behind it (section 7: what value combinations usually mean): a reference for tuning the prompt and for judging the answers.

## 1. What the games offer and what is recorded

Every value below was looked at in the four games' data (ACE graphics and physics pages, the Kunos physics page of Assetto Corsa Rally, iRacing's live variables, the DiRT Rally 2.0 UDP packet). Selected are the values that show how the driver uses the car's grip.

### Selected and recorded

| Value (field) | Why it matters | ACE | ACR | iRacing | DR2 | In the lap files |
| --- | --- | --- | --- | --- | --- | --- |
| speed, throttle, brake, steering, gear, rpm | the driver's inputs and the result | yes | yes | yes | yes | `v`, `thr`, `brk`, `str`, `g`, `rpm` (before) |
| position x / y, lap position | the line, the corner shape | yes | yes | dead-reckoned | yes | `x`, `y`, `p` (before) |
| TC / ABS / stability working, their levels | aids at work | yes | partly | ABS only | – | `a`, `lv` (before) |
| **lateral and longitudinal g** (`g_lat`, `g_long`) | grip use: braking, cornering and accelerating force | physics `accG` | physics `accG` | `LatAccel`, `LongAccel` | bytes 136, 140 | `ga`, `gl` |
| **yaw rate** (`yaw_rate`) | how fast the car rotates | physics `localAngularVel` | the same | `YawRate` | – | `yaw` |
| **body slip** (`body_slip`) | how sideways the car is | physics `localVelocity` | the same | `VelocityX` / `VelocityY` | – | `bs` |
| **slip angle per wheel** (`slip_angle`) | cornering slip: front against rear = understeer / oversteer | physics `slipAngle` | the same | – | – | `sa` (4 wheels) |
| **slip ratio per wheel** (`wheel_slip`) | braking and traction slip: lock-ups, wheelspin | physics `slipRatio` | the same | – | from the wheel speeds | `sr` (4 wheels) |
| **wheels off the track** (`wheels_out`) | the only hint about the track edges | physics `numberOfTyresOut` | the same | `PlayerTrackSurface` (off = 4) | – | `out` |

**Recorded only with the AI DETAIL LOG switched on** (settings, all devices; off by default, owner: keep the lap files small and the work light when the detail is not needed): off, a lap file keeps only what the pages show (position, speed, pedals, steering, gear, aids) and is about 40 % smaller, and rpm is left out too; the AI trainer then works with the pedal and line checks only. Laps recorded before 18 November 2026 have none of the new values; a game that does not send one leaves it out. **Signs and units are not yet checked in any game**: `python tools/live.py --record 60` checks the signs of the g forces and the yaw rate against braking, throttle and steering, and the slip angle unit (radians assumed for the Kunos games, `SLIP_ANGLE_RAD` in `core/kunos.py`).

### Looked at and left out

| Value | Why not |
| --- | --- |
| wheel load, tyre forces (`fx`, `fy`, `mz`) | the g forces show the same for the driver; the forces are not documented or checked in ACE |
| suspension travel, ride height, camber, tyre contact points | car setup, not driving technique (owner: no setup) |
| tyre and brake temperatures per sample | they change slowly; the TYRES page shows them; the lap's `ambient` line keeps the conditions |
| tyre wear | ACE does not send it |
| wheel angular speed | the slip ratio already says it |
| steering in degrees (`steer_degrees`) | the steering ratio differs per car; the share of full lock is enough |
| ACE's tyre lock flag | never set in the game; a locked wheel shows as slip ratio −100 % |
| kerb / slip / ABS vibrations | force feedback effects, no information beyond the slip values |
| heading, pitch, roll | the map position covers the heading |
| fuel, ERS, DRS, electronics, damage, flags, timing | not driving technique, or already on other pages |

## 2. What the AI gets

Per section and line (details in [TRAINER.md](TRAINER.md#what-is-sent-the-facts)):

- **trace**, every 10 m: metres, km/h, throttle %, brake %, steering, offset from the best line, and from the motion values **grip %** (combined g as % of the car's peak in this run), **balance** (front minus rear slip angle, degrees), **front slip %** and **rear slip %** (the axle's most slipping wheel; negative braking, positive wheelspin).
- **body_slip_max_deg** and where, **wheels_out_m**.
- Per request: **car_limits_g**, the car's peak lateral, braking, accelerating and combined g in this run (held for 5 samples, so a kerb strike or a crash does not count; the saved best lap counts too).
- Everything that was there before: braking point and release, coasting, minimum speed, apex, full throttle, gears, aids, the corner's shape, deltas against the best.

The yaw rate is recorded but not sent: the balance and the body slip say what matters for coaching more directly. Size: about 3,300 characters per section, so a whole-lap request with 4 focus sections stays small.

The prompt has one fundamental for this (the grip budget, smooth hand-over between braking, cornering and accelerating, the balance, judging by the car's own numbers) and two new tip categories, GRIP and BALANCE. Everything else is the AI's own knowledge.

## 3. The physics behind it, in five points

1. **The grip budget (friction circle).** A tyre has one budget of grip shared by braking, cornering and accelerating. A fast driver uses close to all of it all the time and hands it over smoothly: from braking to cornering on entry (trail braking), from cornering to accelerating on exit (throttle as the steering opens). Every moment with less than the full budget in use (coasting, a gap between brake and steering, a hesitant throttle) is lost time. Measure: combined g, √(lateral² + longitudinal²), against the highest the car has shown.
2. **Load transfer steers the car.** Braking moves weight to the front: more front grip, a lighter rear, the car rotates (and can oversteer). Throttle moves weight to the rear: a lighter front, the car pushes wide (understeer), and a rear-wheel-drive car can spin its wheels. Brake and throttle are steering tools, not only speed tools.
3. **Slip.** A tyre grips best at a small slip: a slip ratio of about 6–10 % when braking or accelerating (ACE: ABS and TC start at 6–7 %, measured on the owner's BMW M4 GT3 Evo) and a slip angle of a few degrees when cornering. More slip means sliding: less grip, more heat, lost time.
4. **Exit speed is worth more than entry speed** before a long straight: every km/h more at the exit is carried down the whole straight. Into a slow corner after a straight, the late braking point is worth more. The **minimum speed** decides what the corner costs.
5. **The corner type decides the trade-off.** Slow corners are won on braking and exit (a V-shaped speed trace); fast corners on minimum speed (a U-shaped trace). The apex moves with that.

## 4. What a fast corner looks like, phase by phase

A reference for reading answers and tuning the prompt: the AI is not given these as fixed phases or thresholds (owner: it must work on any track and car), but every row can be seen in the data it gets.

```
   A braking zone       B turn-in / entry      C mid-corner / apex      D exit
 ───────────────────┬──────────────────────┬────────────────────────┬──────────────────
  brake, straight    brake off as steering  minimum speed,           throttle on as steering
  line, downshifts   comes on (trail brake) car rotated, balanced    opens, track-out, upshift
```

### A. Braking zone (entry part 1)

| # | Parameter | Fast looks like | How it shows in the data |
| --- | --- | --- | --- |
| A1 | **Braking point** | As late as still lets the car reach the right minimum speed at the right place | `brake_on_m`; against BEST; and against the distance the car really needs: from entry speed to minimum speed at the car's best measured deceleration |
| A2 | **Brake ramp-up** | Full pressure within about 0.1–0.2 s; no slow squeeze at the start | time from brake on to 90 % of its peak |
| A3 | **Peak deceleration** | Close to the most the car has shown anywhere (the same car, the same session) | dv/dt from speed and time; directly as longitudinal g |
| A4 | **Brake pressure profile** | Aero cars (GT3, formula): highest at high speed, bled off as the speed and downforce fall. Road cars: nearly flat, then the release | brake % over distance: falling or flat |
| A5 | **Straight-line braking** | Hard braking with the wheels straight; steering only once the pressure comes down | steering while brake > 70 % |
| A6 | **Lock-ups / ABS** | ABS on: pressure right at the threshold, ABS working briefly. ABS off: no wheel slower than about −12 %, never locked | wheel slip front / rear, ABS working % of the braking distance |
| A7 | **Lift to brake** | Straight from full throttle to the brake, no gap | gap between `lift_m` and `brake_on_m`; `coast_m` |
| A8 | **Downshifts** | During braking, one per gear as the revs allow; no rear-wheel lock from engine braking | `shifts` against brake; rear slip spike at a downshift |

### B. Turn-in and entry (entry part 2)

| # | Parameter | Fast looks like | How it shows in the data |
| --- | --- | --- | --- |
| B1 | **Turn-in point** | One clear turn-in, placed for the apex; not early (forces a second steering input) and not late (too much steering at once) | where the steering passes 5 %; against `tightest_at_m` and against BEST |
| B2 | **Turn-in rate** | One smooth, quick input; as fast as the car takes it. Too fast: the front saturates (understeer) or the rear snaps (oversteer) | steering %/s at turn-in |
| B3 | **Trail braking** | Brake pressure comes down as the steering goes up: the two add to the grip budget. Longer and deeper in slow corners, short or none in fast ones | metres with brake > 5 % and steering > 10 %; how evenly brake falls as steering rises |
| B4 | **Brake release point** | Close to the minimum-speed point in slow corners; earlier in fast ones | `brake_off_m` against `min_at_m` |
| B5 | **Release smoothness** | A smooth taper to zero. A sudden release unloads the front and the car pushes wide | brake drop per 10 m in the last part of the release |
| B6 | **No coasting** | No metres without a pedal, except a deliberate lift in a fast corner | `coast_m` |
| B7 | **Speed trace shape** | Slow corner: V (a short moment at minimum speed). Fast corner: U (the minimum held). A long flat bottom in a slow corner means braked too early or too much | metres within 2 km/h of the minimum speed |
| B8 | **Entry line** | Outside of the track at turn-in | `off` against BEST (no track edges are known, see section 6) |
| B9 | **Entry speed against what the corner allows** | Overslowing: minimum speed far below what the car showed in similar corners. Overdriving: entry too fast, then understeer and a late apex | minimum speed against the car's grip (C1); entry understeer signs (section 3) |

### C. Mid-corner and apex

| # | Parameter | Fast looks like | How it shows in the data |
| --- | --- | --- | --- |
| C1 | **Grip use at minimum speed** | Lateral g near the most the car has shown at that speed. Corner speed limit ≈ √(lateral grip × radius) | lateral g = v² / driven radius (from x / y), or measured |
| C2 | **Apex place** | At or after the geometric apex before a straight (exit first), earlier in a fast corner (carry speed) | `min_at_m` against `tightest_at_m` |
| C3 | **Driven radius** | Larger than the corner's own radius: the full track width used | curvature of the driven path against the corner outline |
| C4 | **Lateral g plateau** | Steady lateral g through the corner, no dip in the middle (a dip means hesitation or a lift) | lateral g over distance |
| C5 | **Steering at the apex** | The least steering the radius needs. More steering for the same radius and speed than the car's normal means understeer (scrubbing speed) | steering per curvature against the car's own low-g value (section 3) |
| C6 | **Rotation** | The car points at the exit early, so the throttle can come on | yaw rate against speed / radius; steering already opening |
| C7 | **Maintenance throttle** | In a long corner a light, steady throttle settles the car | throttle 10–40 % held in the middle of a long corner |

### D. Exit

| # | Parameter | Fast looks like | How it shows in the data |
| --- | --- | --- | --- |
| D1 | **Throttle pick-up** | First throttle at or just before the apex, once the car is rotated | first throttle > 10 % after the brake release, against `min_at_m` |
| D2 | **Throttle ramp** | Progressive to full, in step with the steering opening: throttle up as steering comes down | time from 10 % to 95 %; throttle % + steering % roughly constant |
| D3 | **Full throttle point** | As early as the car's traction allows | `full_throttle_m` |
| D4 | **No lift after pick-up** | Once on the throttle, it stays on. A lift means too early, too much, or the car got loose / ran wide | throttle drops > 20 % after the pick-up |
| D5 | **Steering unwinding** | Steering opens from the apex to the exit. Steering that grows while the throttle grows means power understeer (running wide) | steering trend after the apex against throttle |
| D6 | **Wheelspin and TC** | A small slip at the traction limit, TC working little | rear wheel slip on exit; `aids` TC working |
| D7 | **Track-out** | To the outside of the track at the exit | `off` against BEST |
| D8 | **Exit speed** | Measured where it pays: 100 m after the exit, not only at the section end | speed at the exit and 100 m into the next section |
| D9 | **Upshifts** | At the shift light; earlier (short shift) only when traction-limited | `shifts`, `rpm` |

### Across all phases: input quality

| # | Parameter | Fast looks like | How it shows in the data |
| --- | --- | --- | --- |
| X1 | **Steering corrections** | One input in, one out. Several small reversals (sawing) mean the car is not settled or the driver is unsure | sign changes of the steering rate inside the corner |
| X2 | **Counter-steer** | None. Steering against the corner direction is catching oversteer | steering sign opposite to the corner's turn |
| X3 | **Pedal overlap** | Only on purpose (left-foot braking, rally) | brake and throttle both > 10 % |
| X4 | **Consistency** | The same braking point and minimum speed lap after lap | spread of `brake_on_m` and `min_kmh` over the laps of a run |

## 5. The car's limits: understeer and oversteer

**Understeer:** the front tyres slide more than the rear; the car turns less than the steering asks and runs wide. **Oversteer:** the rear slides more than the front; the car turns more than asked and the rear steps out. A small amount of either at the limit is normal and fast; too much costs time.

### How to see it in the data (best signal first)

| Signal | Understeer | Oversteer |
| --- | --- | --- |
| Front against rear slip angle (ACE, ACR: per wheel) | front clearly larger | rear clearly larger |
| Body slip angle (sideways speed against forward speed) | small | large, growing |
| Yaw rate against speed / driven radius | car turns less than its path needs | car turns more |
| Steering against the corner's radius and speed | more steering than the car needs elsewhere for the same radius and speed | less steering, or steering falling while the radius stays tight |
| Counter-steer | – | steering against the corner direction |
| Speed scrub | speed falling without brake while steering is high | – |
| Running wide | driven radius grows on exit while throttle and steering both rise | – |
| Throttle lift after pick-up | sometimes (to regain the front) | often (to catch the rear) |

The AI sees the balance directly (front minus rear slip angle, in the trace) where the game sends slip angles (ACE, Assetto Corsa Rally); elsewhere it reads it from steering, speed and grip in the trace.

### Six kinds, their cause and the fix

| Phase | Kind | Typical driver causes | What to change |
| --- | --- | --- | --- |
| Entry | **Understeer** | too fast into the corner; brake released too early (front unloaded); steering too fast or too much; braking too hard while steering (fronts lock or ABS works) | brake slightly earlier or less; keep a little brake into the turn-in (trail) so the front stays loaded; slower, smaller steering input |
| Entry | **Oversteer** | too much brake while steering (rear light); a downshift too early or too many (engine braking locks the rear); a sudden lift in a fast corner | release the brake as the steering builds; downshift later, one gear at a time; lift progressively; in-car: brake bias forward |
| Mid | **Understeer** | minimum speed too high; too much steering (scrubbing); no balance throttle | lower the minimum speed a little; open the steering slightly; a light, steady throttle |
| Mid | **Oversteer** | a lift mid-corner; too much rotation from the entry; kerbs or bumps | steady maintenance throttle; less trail brake on entry |
| Exit | **Power understeer** | throttle too early or too much with lock still on (front-wheel drive, aero cars at low speed) | rotate the car first (later apex), open the steering, then add throttle progressively |
| Exit | **Power oversteer** | too much throttle too early with steering on (rear-wheel drive, high torque, TC low or off) | progressive throttle as the steering opens; a gear higher; in-car: more TC |

In-car settings the coach may suggest (they are on the DASH, not the setup): brake bias, TC, TC cut, ABS, engine map. Car setup stays out (owner's rule).

## 6. Where the knowledge changes: corner, car, aids, surface

Knowledge for the AI and for tuning the prompt, not tags or rules in the code: the AI recognises the corner from `corner`, `next_section` and the trace, and the car from its name and `car_limits_g`.

### By corner

| Scenario | How it shows in the data | What matters most | What changes |
| --- | --- | --- | --- |
| **S1 Slow corner before a straight** (hairpin) | radius < 50 m or minimum < 80 km/h; a long straight follows (`next_section`) | exit: rotation on entry, early full throttle, speed 100 m after the exit | late apex; V-shaped speed trace; deep trail braking; a short time at minimum speed |
| **S2 Medium corner** | radius 50–120 m | balance between braking and minimum speed | apex near the geometric one; moderate trail braking |
| **S3 Fast corner** | radius > 120 m or minimum > 150 km/h | minimum speed, grip use, smooth inputs | earlier apex; U-shaped trace; a lift or a short brake only; mid-corner understeer is the main enemy |
| **S4 Chicane / esses** | left and right turns (`corner.type` chicane) | speed through the change of direction; line set for the last part | sacrifice the first part for the second; one quick, clean steering reversal; settle before the second turn |
| **S5 Corner before a slow corner** | a slow corner follows soon | entry of the next corner | exit speed counts less: set up the line for the next braking zone |
| **S6 Heavy braking zone** | a long straight before | braking point, peak deceleration, downshifts | A1–A8 weigh most |
| **S7 Lift-only or flat corner** | no brake on the best lap | commitment, minimum speed | no braking tips; coach the lift (short, early, smooth) or flat out |
| **S8 Decreasing radius** | the outline gets tighter after the turn-in | patience | later turn-in, later apex, brake longer into the corner |
| **S9 Increasing radius** | the outline opens after the tightest point | early throttle | earlier apex, throttle earlier and harder |

### By car

| Scenario | How it shows in the data | Coaching focus |
| --- | --- | --- |
| **High downforce** (GT3, formula) | grip in fast corners well above slow ones (`car_limits_g` reached at high speed) | brake very hard at high speed and bleed off; carry speed in fast corners; slow corners lose aero grip: patience on throttle, mid-corner understeer |
| **Low downforce road car** (GR86, Camaro) | about the same grip at all speeds | weight transfer: trail braking for rotation; longer braking distances; smooth hands |
| **Rear-wheel drive, high power, little TC** | rear slip and TC on exit | progressive throttle, short-shift if needed, power oversteer |
| **Front-wheel drive** | the car name (the coach knows the car) | power understeer on exit; lift-off rotation on entry is a tool |
| **All-wheel drive** (rally) | the car name, the game | throttle earlier, pull the car out of the corner |

The coach gets the car name; a model that knows the car can add what is commonly known about it.

### By driving aids

| Scenario | Coaching focus |
| --- | --- |
| **ABS on** | brake at the threshold and lean on the ABS briefly; ABS working through the whole zone means too much pressure into the corner (entry understeer) |
| **ABS off** | modulation: peak pressure without locking; any front lock is a tip |
| **TC on / off** | TC working long on exit means the throttle is too early or too fast; with TC off, wheelspin from the slip data |

### By surface (rally: Assetto Corsa Rally, DiRT Rally 2.0)

Loose surfaces follow different rules: a large slip angle is fast on gravel, left-foot braking and weight-transfer techniques (the Scandinavian flick) rotate the car, and the line follows the pace notes. The circuit thresholds above do not apply; the rally scenarios need their own rules (a later step).

## 7. Value combinations: what they usually mean

The logic for reading the data the AI gets (section 2). No single value says much; **combinations** do, read at the same place in the corner and compared with BEST there.

**Python evaluates them, not the AI** (owner, 18 November 2026): `core/coach.py` checks every section the lap has driven through and reports each code as `yes`, `partly` (good checks only), `no` or `n/a` (no braking here, a straight, a game without slip values, a lap recorded before the motion values). A found room-to-improve check also says how clearly (`slight` / `clear`), where (the longest stretch, metres from the section start), what it saw and a rough time. The AI gets these per section (`checks`) and for the whole lap (`lap_checks`) and only turns them into tips; `python tools/live.py --coach` (or `GET /api/coach`) prints the same report without any AI. **Gentle by design** (owner: estimates, not too harsh): every limit is relative to the car (its grip at that speed in this run, its own steering, its own best line), the margins are wide, a pattern must last a few metres, a short lift in a fast corner is not coasting, small throttle wobbles are not lifts, and a time estimate is at most half of what the lap lost against BEST in that stretch, never more than 0.3 s, and none without BEST. The limits are constants at the top of `core/coach.py`, to be tuned after real drives. Computed: G1–G6, B1–B5, E1–E4, M1–M4, X1–X5, L1, L2, L5, L6; L3 and L4 stay knowledge for the AI (the car's peak includes the lap itself, so grip above 100 % cannot happen, and "low all lap" shows in `lap_checks`).

Words used below, always relative to **this car in this run**, never fixed numbers:

| Word | Meaning |
| --- | --- |
| high grip | grip % close to the car's peak (about 90–100 %) |
| low grip | grip % clearly below what the car showed in similar corners (below about 75–80 %) |
| at the slip limit | slip near where this car's ABS / TC start to work (ACE M4 GT3 Evo: about 6–7 %) |
| balance + / − | front minus rear slip angle: + the front slides more (understeer), − the rear slides more (oversteer); a small + is normal and safe |
| hand-over | one input falling while the other rises: brake → steering on entry, steering → throttle on exit |

### Good: the car is used well

| # | Combination | Usually means |
| --- | --- | --- |
| G1 | brake high, steering near 0, grip high, front slip at the limit and steady, no lock, ABS working briefly or not at all | braking at the limit in a straight line |
| G2 | brake falling while steering rises, grip stays high through the change (no dip), balance small | trail braking: the grip is handed from braking to cornering without a gap |
| G3 | grip high and steady through the middle, balance near 0 or slightly +, steering steady with no corrections, body slip small | the car is at its limit and balanced in the corner |
| G4 | throttle rising while steering opens, grip stays high, rear slip small + without spikes, no lift, line out to the edge (a wheel out at the exit kerb is fine) | exit hand-over: full use of traction, the car pulled out of the corner |
| G5 | grip high in braking, corner and exit; low only on straights at full throttle | every part where grip limits the speed is used (on a straight the engine limits, not the grip) |
| G6 | the same pattern at the same places lap after lap | consistency: the basis for small, safe gains |

### Room to improve

**Braking**

| # | Combination | Usually means | What to try |
| --- | --- | --- | --- |
| B1 | brake on, but grip well below the car's peak, front slip small, ABS never works | not braking hard enough: the car could stop shorter | brake harder, then later |
| B2 | grip rises slowly after the brake comes on | hesitant first pressure | hit the brake hard at once, then ease off |
| B3 | front slip far beyond the limit or −100 % (locked), or ABS working through the whole zone; grip falls | overbraking: a locked or sliding tyre grips less | a little less pressure, a progressive release |
| B4 | neither pedal for metres between lift and brake or before turn-in (coast), grip low there | coasting: grip unused | brake straight from full throttle; turn in on the brake |
| B5 | brake fully off before the steering starts, grip dips between braking and turning | no trail braking: a gap in the grip budget | release more slowly, overlap brake and steering |

**Entry (turn-in to apex)**

| # | Combination | Usually means | What to try |
| --- | --- | --- | --- |
| E1 | steering rising while brake is still high, balance strongly +, front slip far negative | entry understeer: the fronts asked to brake and turn too much at once | ease the brake earlier as the steering builds |
| E2 | brake dropped abruptly at turn-in, balance jumps +, speed falls without brake, line goes outside | entry understeer: the front unloaded, or too fast into the corner | release slowly; or a little slower into the corner |
| E3 | balance strongly − with brake or a lift, body slip rising, counter-steer, rear slip negative at a downshift | entry oversteer: too much brake while turning, a sudden lift, or engine braking | release earlier as you turn; downshift later, one gear at a time; lift gently |
| E4 | steering bigger than BEST at the same place and speed, grip not higher | overdriving: more steering does not give more grip | less steering lock, a slower turn-in |

**Middle of the corner**

| # | Combination | Usually means | What to try |
| --- | --- | --- | --- |
| M1 | grip dips in the middle, speed below BEST, steering steady, balance near 0 | not committed: the car could go faster here | carry more speed: brake less or later |
| M2 | grip high, balance strongly +, steering growing, speed falling without brake | mid-corner understeer: scrubbing speed | a slightly slower entry; open the steering |
| M3 | steering reverses several times, balance flips between + and − | the car is unsettled, the driver corrects | one smooth input; a steady light throttle in long corners |
| M4 | a long flat minimum speed in a slow corner, grip low there | braked too early or too much, then waited | a later, harder brake and a short minimum (a V, not a U) |

**Exit**

| # | Combination | Usually means | What to try |
| --- | --- | --- | --- |
| X1 | steering already opening and grip falling, but the throttle not yet on | late throttle: time lost onto the straight | throttle on as the steering opens |
| X2 | throttle on early while steering stays large or grows, balance +, line goes outside, wheels out at the exit | power understeer: running wide | rotate the car first (later apex), then open the steering, then throttle |
| X3 | rear slip big + spikes, TC working long, body slip rising, counter-steer, a throttle lift after the pick-up | power oversteer: too much throttle too early | progressive throttle as the steering opens; a higher gear; more TC |
| X4 | throttle lifted again after the pick-up, balance and slip normal | too early or unsure | wait a moment, then one progressive pick-up |
| X5 | line stays inside at the exit (`off` +), no wheel near the edge, speed lower than BEST 50–100 m later | the exit is not used: too tight a line | let the car run out to the edge |

**Limits, line and aids**

| # | Combination | Usually means | What to try |
| --- | --- | --- | --- |
| L1 | wheels out at the same place every lap with time gained against BEST | using a kerb: fine if the game keeps the lap valid | keep it, if the lap stays valid |
| L2 | wheels out with body slip and time lost | an excursion: past the limit | a little less entry speed or throttle there |
| L3 | grip above 100 % | a new peak: the car can do more than it showed before | compare with the earlier corners: they had grip to spare |
| L4 | grip low everywhere on this lap | cold tyres (out lap, first laps), or general caution | judge after a few laps; then push corner by corner |
| L5 | TC working long while the rear slip stays small | TC cuts more than needed | try a lower TC |
| L6 | ABS working all the way to the apex with balance + at turn-in | leaning on ABS into the corner causes entry understeer | release earlier; or try a lower ABS |

### Read with care

- Cause and effect: a slow exit can come from the entry (E1–E4 make X1 or X2 likely). The first thing that goes wrong in a corner is the tip; the rest follows from it.
- Speed changes the numbers: a downforce car has less grip in slow corners than in fast ones, so compare grip % with similar corners, not with the lap's peak only.
- A small + balance, a little rear slip on exit and a few degrees of body slip are normal at the limit.
- Loose surfaces (rally) turn some of this round: more slip and body slip can be fast on gravel.
- Missing values: iRacing has no slip angles or slip ratio (no balance, no slip columns), DR2 no slip angles; old laps have none of the motion values. The AI then reads the same patterns from speed, pedals, steering and the line.

## 8. Next

1. **Check the new values in ACE** (local): `python tools/live.py motion` while driving, then `python tools/live.py --record 90` with hard braking, full throttle out of slow corners and both directions of corner: the check says whether each sign is right and whether the slip angles are in degrees. Then the same in ACR, iRacing, DR2.
2. **Fine-tune with real answers**: put the combinations of section 7 into the prompt in a short form (owner to agree), ask the AI TRAINER on laps recorded with the new values, read the facts sent with each answer (`data/trainer.jsonl`, field `data`) and adjust the prompt where the answers miss or misread something.
3. Later: rally knowledge for loose surfaces; the yaw rate in the facts if the answers need it.
