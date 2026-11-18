# AI coach – corner knowledge

**Proposal, 18 November 2026, waiting for the owner's feedback.** Nothing here is built yet.

Today the AI trainer ([TRAINER.md](TRAINER.md)) judges a lap against seven fundamentals and against the driver's own best lap. The owner wants a coach that knows how a fast corner is driven, so that it can help even when the best lap itself is slow. This file lists everything that makes a driver faster through a corner: the parameters, what good looks like, how each one shows in our data, and the scenarios in which the rules change. **Corner entry comes first** (owner); exit and balance follow.

Data column in the tables:

| Mark | Meaning |
| --- | --- |
| **have** | already in the trainer's facts |
| **derive** | can be computed from what the recorder already stores (distance, time, speed, throttle, brake, steering, gear, x / y, aids, rpm): works for laps already recorded |
| **record** | needs a new recorded channel (lateral / longitudinal g, yaw rate, slip angles, wheel slip); only laps recorded after the change have it |

## 1. The physics behind it, in five points

1. **The grip budget (friction circle).** A tyre has one budget of grip shared by braking, cornering and accelerating. A fast driver uses close to all of it all the time and hands it over smoothly: from braking to cornering on entry (trail braking), from cornering to accelerating on exit (throttle as the steering opens). Every moment with less than the full budget in use (coasting, a gap between brake and steering, a hesitant throttle) is lost time. Measure: combined g, √(lateral² + longitudinal²), against the highest the car has shown.
2. **Load transfer steers the car.** Braking moves weight to the front: more front grip, a lighter rear, the car rotates (and can oversteer). Throttle moves weight to the rear: a lighter front, the car pushes wide (understeer), and a rear-wheel-drive car can spin its wheels. Brake and throttle are steering tools, not only speed tools.
3. **Slip.** A tyre grips best at a small slip: a slip ratio of about 6–10 % when braking or accelerating (ACE: ABS and TC start at 6–7 %, measured on the owner's BMW M4 GT3 Evo) and a slip angle of a few degrees when cornering. More slip means sliding: less grip, more heat, lost time.
4. **Exit speed is worth more than entry speed** before a long straight: every km/h more at the exit is carried down the whole straight. Into a slow corner after a straight, the late braking point is worth more. The **minimum speed** decides what the corner costs.
5. **The corner type decides the trade-off.** Slow corners are won on braking and exit (a V-shaped speed trace); fast corners on minimum speed (a U-shaped trace). The apex moves with that.

## 2. The phases of a corner

A corner has four phases. Each gets its parameters below.

```
   A braking zone       B turn-in / entry      C mid-corner / apex      D exit
 ───────────────────┬──────────────────────┬────────────────────────┬──────────────────
  brake, straight    brake off as steering  minimum speed,           throttle on as steering
  line, downshifts   comes on (trail brake) car rotated, balanced    opens, track-out, upshift
```

### A. Braking zone (entry part 1)

| # | Parameter | Fast looks like | How it shows in the data | Data |
| --- | --- | --- | --- | --- |
| A1 | **Braking point** | As late as still lets the car reach the right minimum speed at the right place | `brake_on_m`; against BEST; and against the distance the car really needs: from entry speed to minimum speed at the car's best measured deceleration | have / derive |
| A2 | **Brake ramp-up** | Full pressure within about 0.1–0.2 s; no slow squeeze at the start | time from brake on to 90 % of its peak | derive |
| A3 | **Peak deceleration** | Close to the most the car has shown anywhere (the same car, the same session) | dv/dt from speed and time; directly as longitudinal g | derive / record |
| A4 | **Brake pressure profile** | Aero cars (GT3, formula): highest at high speed, bled off as the speed and downforce fall. Road cars: nearly flat, then the release | brake % over distance: falling or flat | derive |
| A5 | **Straight-line braking** | Hard braking with the wheels straight; steering only once the pressure comes down | steering while brake > 70 % | derive |
| A6 | **Lock-ups / ABS** | ABS on: pressure right at the threshold, ABS working briefly. ABS off: no wheel slower than about −12 %, never locked | wheel slip front / rear, ABS working % of the braking distance | record (slip) / have (ABS) |
| A7 | **Lift to brake** | Straight from full throttle to the brake, no gap | gap between `lift_m` and `brake_on_m`; `coast_m` | have |
| A8 | **Downshifts** | During braking, one per gear as the revs allow; no rear-wheel lock from engine braking | `shifts` against brake; rear slip spike at a downshift | have / record |

### B. Turn-in and entry (entry part 2)

| # | Parameter | Fast looks like | How it shows in the data | Data |
| --- | --- | --- | --- | --- |
| B1 | **Turn-in point** | One clear turn-in, placed for the apex; not early (forces a second steering input) and not late (too much steering at once) | where the steering passes 5 %; against `tightest_at_m` and against BEST | derive |
| B2 | **Turn-in rate** | One smooth, quick input; as fast as the car takes it. Too fast: the front saturates (understeer) or the rear snaps (oversteer) | steering %/s at turn-in | derive |
| B3 | **Trail braking** | Brake pressure comes down as the steering goes up: the two add to the grip budget. Longer and deeper in slow corners, short or none in fast ones | metres with brake > 5 % and steering > 10 %; how evenly brake falls as steering rises | derive |
| B4 | **Brake release point** | Close to the minimum-speed point in slow corners; earlier in fast ones | `brake_off_m` against `min_at_m` | have |
| B5 | **Release smoothness** | A smooth taper to zero. A sudden release unloads the front and the car pushes wide | brake drop per 10 m in the last part of the release | derive |
| B6 | **No coasting** | No metres without a pedal, except a deliberate lift in a fast corner | `coast_m` | have |
| B7 | **Speed trace shape** | Slow corner: V (a short moment at minimum speed). Fast corner: U (the minimum held). A long flat bottom in a slow corner means braked too early or too much | metres within 2 km/h of the minimum speed | derive |
| B8 | **Entry line** | Outside of the track at turn-in | `off` against BEST (no track edges are known, see section 6) | have |
| B9 | **Entry speed against what the corner allows** | Overslowing: minimum speed far below what the car showed in similar corners. Overdriving: entry too fast, then understeer and a late apex | minimum speed against the car's grip (C1); entry understeer signs (section 3) | derive |

### C. Mid-corner and apex

| # | Parameter | Fast looks like | How it shows in the data | Data |
| --- | --- | --- | --- | --- |
| C1 | **Grip use at minimum speed** | Lateral g near the most the car has shown at that speed. Corner speed limit ≈ √(lateral grip × radius) | lateral g = v² / driven radius (from x / y), or measured | derive / record |
| C2 | **Apex place** | At or after the geometric apex before a straight (exit first), earlier in a fast corner (carry speed) | `min_at_m` against `tightest_at_m` | have |
| C3 | **Driven radius** | Larger than the corner's own radius: the full track width used | curvature of the driven path against the corner outline | derive |
| C4 | **Lateral g plateau** | Steady lateral g through the corner, no dip in the middle (a dip means hesitation or a lift) | lateral g over distance | derive / record |
| C5 | **Steering at the apex** | The least steering the radius needs. More steering for the same radius and speed than the car's normal means understeer (scrubbing speed) | steering per curvature against the car's own low-g value (section 3) | derive |
| C6 | **Rotation** | The car points at the exit early, so the throttle can come on | yaw rate against speed / radius; steering already opening | record / derive |
| C7 | **Maintenance throttle** | In a long corner a light, steady throttle settles the car | throttle 10–40 % held in the middle of a long corner | derive |

### D. Exit

| # | Parameter | Fast looks like | How it shows in the data | Data |
| --- | --- | --- | --- | --- |
| D1 | **Throttle pick-up** | First throttle at or just before the apex, once the car is rotated | first throttle > 10 % after the brake release, against `min_at_m` | derive |
| D2 | **Throttle ramp** | Progressive to full, in step with the steering opening: throttle up as steering comes down | time from 10 % to 95 %; throttle % + steering % roughly constant | derive |
| D3 | **Full throttle point** | As early as the car's traction allows | `full_throttle_m` | have |
| D4 | **No lift after pick-up** | Once on the throttle, it stays on. A lift means too early, too much, or the car got loose / ran wide | throttle drops > 20 % after the pick-up | derive |
| D5 | **Steering unwinding** | Steering opens from the apex to the exit. Steering that grows while the throttle grows means power understeer (running wide) | steering trend after the apex against throttle | derive |
| D6 | **Wheelspin and TC** | A small slip at the traction limit, TC working little | rear wheel slip on exit; `aids` TC working | record / have |
| D7 | **Track-out** | To the outside of the track at the exit | `off` against BEST | have |
| D8 | **Exit speed** | Measured where it pays: 100 m after the exit, not only at the section end | speed at the exit and 100 m into the next section | have / derive |
| D9 | **Upshifts** | At the shift light; earlier (short shift) only when traction-limited | `shifts`, `rpm` | have |

### Across all phases: input quality

| # | Parameter | Fast looks like | How it shows in the data | Data |
| --- | --- | --- | --- | --- |
| X1 | **Steering corrections** | One input in, one out. Several small reversals (sawing) mean the car is not settled or the driver is unsure | sign changes of the steering rate inside the corner | derive |
| X2 | **Counter-steer** | None. Steering against the corner direction is catching oversteer | steering sign opposite to the corner's turn | derive |
| X3 | **Pedal overlap** | Only on purpose (left-foot braking, rally) | brake and throttle both > 10 % | derive |
| X4 | **Consistency** | The same braking point and minimum speed lap after lap | spread of `brake_on_m` and `min_kmh` over the laps of a run | derive |

## 3. The car's limits: understeer and oversteer

**Understeer:** the front tyres slide more than the rear; the car turns less than the steering asks and runs wide. **Oversteer:** the rear slides more than the front; the car turns more than asked and the rear steps out. A small amount of either at the limit is normal and fast; too much costs time.

### How to see it in the data (best signal first)

| Signal | Understeer | Oversteer | Data |
| --- | --- | --- | --- |
| Front against rear slip angle (ACE, ACR: per wheel) | front clearly larger | rear clearly larger | record |
| Body slip angle (sideways speed against forward speed) | small | large, growing | record (ACE, ACR, iRacing) |
| Yaw rate against speed / driven radius | car turns less than its path needs | car turns more | record |
| Steering per curvature against the car's own low-g value | more steering for the same radius: understeer index above 1 | less steering, or steering falling while the radius stays tight | derive |
| Counter-steer | – | steering against the corner direction | derive |
| Speed scrub | speed falling without brake while steering is high | – | derive |
| Running wide | driven radius grows on exit while throttle and steering both rise | – | derive |
| Throttle lift after pick-up | sometimes (to regain the front) | often (to catch the rear) | derive |

The steering-per-curvature method needs no new channel: at low lateral g every car needs a fixed steering for a given curvature (its neutral steering gain). The bridge can learn that per car and lap from the data, and then measure in each corner how much more (understeer) or less (oversteer) steering the driver needed.

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

## 4. Scenarios: where the rules change

The bridge tags every section with its scenario so that the coach applies the right rules. Most tags come from data we already have.

### By corner

| Scenario | How the bridge recognises it | What matters most | Rules that change |
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

| Scenario | How the bridge recognises it | Coaching focus |
| --- | --- | --- |
| **High downforce** (GT3, formula) | lateral g rises with speed (more grip in fast corners than slow ones) | brake very hard at high speed and bleed off; carry speed in fast corners; slow corners lose aero grip: patience on throttle, mid-corner understeer |
| **Low downforce road car** (GR86, Camaro) | lateral g about the same at all speeds | weight transfer: trail braking for rotation; longer braking distances; smooth hands |
| **Rear-wheel drive, high power, little TC** | rear slip and TC on exit | progressive throttle, short-shift if needed, power oversteer |
| **Front-wheel drive** | the car name (the coach knows the car) | power understeer on exit; lift-off rotation on entry is a tool |
| **All-wheel drive** (rally) | the car name, the game | throttle earlier, pull the car out of the corner |

The coach also gets the car name; a model that knows the car can add what is commonly known about it.

### By driving aids

| Scenario | Coaching focus |
| --- | --- |
| **ABS on** | brake at the threshold and lean on the ABS briefly; ABS working through the whole zone means too much pressure into the corner (entry understeer) |
| **ABS off** | modulation: peak pressure without locking; any front lock is a tip |
| **TC on / off** | TC working long on exit means the throttle is too early or too fast; with TC off, wheelspin from the slip data |

### By surface (rally: Assetto Corsa Rally, DiRT Rally 2.0)

Loose surfaces follow different rules: a large slip angle is fast on gravel, left-foot braking and weight-transfer techniques (the Scandinavian flick) rotate the car, and the line follows the pace notes. The circuit thresholds above do not apply; the rally scenarios need their own rules (a later step).

## 5. What the bridge would send to the AI

Per section, on top of today's facts:

- **Scenario tags**: corner class (S1–S9), car class (downforce, drive), aids.
- **Phase points**: turn-in, trail-brake length and shape, release smoothness, throttle pick-up, ramp time, throttle drops, steering corrections, counter-steer.
- **Limits**: the car's best deceleration and lateral g on this lap (the reference for "using the grip"), grip use at minimum speed, the understeer index per phase (entry, mid, exit), wheel slip and slip angles once recorded.

The prompt would get the knowledge of sections 1–4: the phases, the balance table, and the scenario rules, so that the AI judges each corner by its type. New title categories: TURN-IN, TRAIL, BALANCE, INPUTS (next to BRAKING, RELEASE, APEX, THROTTLE, LINE, GEAR, AIDS, TIME).

All thresholds are relative to what the car itself has shown (its best deceleration, its best lateral g, its neutral steering gain), so the rules work for every car and game without a table per car.

## 6. What our data cannot tell

- **Track edges**: no game sends the track width, so "use all the track" is judged against BEST and the corner outline, not against the real edges. An estimate is possible from the spread of all recorded laps.
- **Kerbs and bumps**: not in the data.
- **Steering in degrees**: the games send a share of full lock, and the steering ratio differs per car; the understeer index uses the car's own neutral value instead.
- **iRacing**: no slip per wheel; the map position is dead-reckoned (good enough for curvature). **DiRT Rally 2.0**: no slip angles or yaw rate.
- **Sample rate**: 30 per second; rates of change (ramp-up, turn-in rate) are smoothed over a few samples.

## 7. Proposed steps

1. **Entry first, from data we already have** (works for laps already recorded): A1–A8, B1–B9 and the entry rows of the balance table: turn-in point and rate, trail braking, release smoothness, peak deceleration, speed trace shape, steering-per-curvature understeer index, counter-steer. Prompt: the entry knowledge and the scenario tags. Test against recorded ACE laps.
2. **New recorded channels**: lateral and longitudinal g, yaw rate, slip angle front / rear, body slip, wheel slip ratio front / rear (ACE and ACR from the physics page; iRacing `LatAccel`, `LongAccel`, `YawRate`, `VelocityX` / `VelocityY`; DR2 lateral and longitudinal g). Older laps simply lack them, as they lack the aids.
3. **Mid-corner and exit** (C, D) and the full balance table.
4. **Car and surface scenarios**, rally rules.

Open questions for the owner:

1. Start with step 1 (entry, no new recording), or record the new channels at the same time?
2. May the coach suggest in-car settings (brake bias, TC, ABS, engine map) when the data shows the cause there?
3. How many tips: keep up to 9, or fewer but deeper per corner?
