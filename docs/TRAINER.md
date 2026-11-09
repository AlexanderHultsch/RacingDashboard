# AI trainer – agreed definition

Agreed with the owner in an interview (November 2026). **Built** (November 2026): `core/trainer.py`, `ui/js/analysis.js` (button, TRAINER tab), `ui/js/rd.js` (settings), tests in `tests/test_trainer.py`. Works with Claude on the owner's PC (see [First real answers](#first-real-answers-november-2026)); ChatGPT, Gemini and Ollama are written from the providers' documentation and never called for real; the owner uses Claude only, so **testing them is not planned** (open point, November 2026). This replaces the earlier rule "no coaching, no tips" on the analysis page: tips come only from the trainer, and only when the driver taps it.

## What it does

The analysis page gets an **AI TRAINER** button. A tap sends what the page shows to an AI of the owner's choice and shows its answer: up to 9 tips (owner, November 2026; 3 at first) on where the driving breaks a fundamental of fast driving and where the time goes against the best, each linked to the measured numbers.

| Mode | When | What is analysed |
| --- | --- | --- |
| **WHOLE TRACK** | the map shows the overview | the whole lap: every section's time for best, last and now, plus the full facts of the 3 sections where now loses the most against best. NOW is the lap in progress only once it is complete; while a lap is being driven, NOW is the last complete lap and LAST the one before (owner's feedback on the first real answers, November 2026) |
| **SECTION n** | the map is zoomed into section n | that section only, with its full facts |

Lines, as everywhere on the page: **best** = the saved best (baseline lap, or the section bests), **last** = the last lap, **now** = the lap in progress (only the sections it has reached) or, between laps and after the run, the last complete lap.

## The page

- **Button:** bottom right of the map, `AI TRAINER` (the map decides what it analyses; no extra text). It shows `ASKING…` while waiting. Greyed out, with the reason next to it, when the AI connection does not work, when the trainer is OFF, or when there is nothing to compare (no best and no last line).
- **Answer:** a third tab **TRAINER** next to REVIEW and GRAPHS. The tap asks the AI and opens the tab; while waiting it says `ASKING CLAUDE · FAST · <model>`. Tapping a tip opens its section in GRAPHS with the cursor at the tip's place.
- **Tab content:** what was analysed and the times (`SECTION 5 · NOW LAP 3 8.059 · BEST 7.646 · LAST 7.819`), the tips (number, title on one line, the place below it, text, time at stake), the note, the provider / level / time / duration, `ASK AGAIN`, and the earlier answers as chips under `EARLIER` (tap one to show it).
- **Only on a tap.** Never automatically, never while driving unless the driver taps.
- **Language:** English.

## Settings (AI TRAINER, all devices, kept on the PC)

| Setting | Values |
| --- | --- |
| Provider | OFF, CLAUDE, CHATGPT, GEMINI, LOCAL (OLLAMA) |
| API key | typed or pasted once on any device (a password field and SAVE); sent to the PC and stored in `config\trainer.json` (ignored by git); never sent back to a page (the page only sees `sk-ant-…7Q2f`); never in the log. One key per provider. Not needed for Ollama. The page sends it once over the home network to the PC |
| Model | **FAST** or **BEST** (see [Models](#models-fast-and-best)); the exact model name is shown next to it |
| Connection | status with the reason (`CONNECTED`, `NO KEY`, `KEY REJECTED`, `MODEL NOT FOUND`, `NO INTERNET`, `OLLAMA NOT RUNNING`), the time of the last check, and a **TEST** button |

The connection is checked when the bridge starts (in the background), when the AI settings change, with TEST, and after a failed request. The check costs nothing: Claude `GET /v1/models/<model>`, ChatGPT `GET /v1/models` (the model must be listed), Gemini `GET /v1beta/models/<model>`, Ollama `GET /api/tags`. The page refreshes the status every 15 s.

## Models: FAST and BEST

FAST and BEST each stand for a fixed **model + effort** pair per provider. The table lives in the bridge (defaults below) and can be overridden in `config\config.toml` (`[trainer.models]`), so a newer model is a one-line change. The settings always show the exact model name in use.

| Provider | FAST | BEST |
| --- | --- | --- |
| Claude | `claude-haiku-5-5`, effort `medium` (was `low` until the first real answers: it mixed up earlier / later) | `claude-opus-5-5`, effort `high` |
| ChatGPT | `gpt-6-luna`, `reasoning_effort` `low` | `gpt-6-astra`, `reasoning_effort` `high` |
| Gemini | `gemini-3.8-flash`, `thinkingLevel` `LOW` | `gemini-4-argon`, `thinkingLevel` `HIGH` |
| Local (Ollama) | the smallest model pulled in Ollama | the largest model pulled in Ollama |

- The model and the effort are two separate settings in the API; the trainer sets both from the level. Effort (thinking depth) changes quality, time and cost within one model. Claude Haiku 5.5 and Opus 5.5 always think a little; `effort` is the only control.
- The ChatGPT and Gemini names were taken from the providers' model pages on 2026-11-08 (OpenAI: GPT-6 Luna "most efficient", GPT-6 Astra "flagship"; Google: Gemini 3.8 Flash, Gemini 4 Argon "flagship reasoning"). They change often: override them in `config\config.toml`, e.g.

  ```toml
  [trainer.models.chatgpt.fast]
  model = "gpt-6-luna"
  effort = "low"
  ```
- Ollama: set `model` for a level to use a specific pulled model; empty takes the smallest (FAST) or largest (BEST). The address is `[trainer] ollama_url` (default `http://localhost:11434`).
- `[trainer] timeout_s` (default 90) is how long the bridge waits for an answer.
- Claude BEST (`claude-opus-5-5`) is sent with the server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`): if the model declines, the API answers with a fallback model in the same call.
- Rough cost per question (about 1,000 tokens in for a section, 3,000–4,000 for the whole track, under 1,000 out): Claude FAST well under a cent, Claude BEST a few cents. Ollama is free.

## History

The last **5 questions and answers** are kept in one rolling file, `data\trainer.jsonl` (ignored by git). It survives a restart of the PC. Each line: time, mode, section, game / car / track, lap numbers, provider, model, effort, the task line and the data sent, the checked answer, the duration and the token counts. The TRAINER tab shows the latest answer for the view on the map (same section or WHOLE TRACK, same car and track) with its time; `ASK AGAIN` asks fresh; the other answers are chips under `EARLIER`.

## What is sent: the facts

The bridge computes the facts from the recorded laps (`core/recorder.py`); no raw graph data is sent. Distances are metres from the section start, speeds km/h, times seconds, pedals 0–100 %.

Per section and per line (`best`, `last`, `now`; a line that does not exist is `null`):

| Fact | Meaning |
| --- | --- |
| `time_s` | section time |
| `entry_kmh`, `exit_kmh` | speed at the section start and end |
| `lift_m` | where the throttle first drops below 50 % |
| `brake_on_m` | where the brake first goes above 10 % (`null` = no braking) |
| `brake_peak_pct` | highest brake pressure |
| `brake_off_m` | where the brake is back below 5 % |
| `coast_m` | metres with neither throttle above 10 % nor brake above 10 % |
| `min_kmh`, `min_at_m` | slowest point and where it is |
| `gear_at_min`, `rpm_at_min` | gear and engine speed at the slowest point (rpm since November 2026; older laps have none) |
| `gears`, `shifts` | gear sequence through the section, e.g. `"4-3-4"` (neutral while shifting left out), and where each change happened (`at_m`, `to`) |
| `full_throttle_m` | where the throttle is back above 95 % (held for 30 m) after the slowest point |
| `steer_max` | largest steering, 0–1 of full lock |
| `trace` | the line every 10 m: `[metres, km/h, throttle %, brake %, steering −100..100, off]`; `off` (`last` and `now` only, and only in a corner) is the distance in metres from the best line, positive towards the inside of the corner, negative towards the outside. This is what lets the AI judge the line and the shape of the inputs, not only a few points |
| `delta_by_50m` | time behind best (positive = slower) at every 50 m and at the section end (`now` and `last` only) |
| `aids` | driving aids, when recorded: `tc_working_m`, `tc_working_pct`, `tc_first_m` (and the same for `abs`, `esc`), `levels` at the section start (`tc`, `tc_cut`, `abs`, `esc`, `engine_map`), `level_changes` (`at_m`, `setting`, `to`) |

Per section, measured from the recorded track outline (`corner`, next to the three lines): `type` (straight, fast / medium / slow corner, chicane), `turn_deg` (how much the road turns), `tightest_at_m` and `radius_m` (the geometric apex). `next_section` says what follows (a straight after a slow corner makes the exit the priority) and `lap_m` where the section lies in the lap, so the AI can place the corner on the real circuit and use what it knows about it.

Whole-track mode adds a `sections` table (per section: type, best / last / now time and the deltas) and the lap times; the full facts are sent for the 4 sections where now loses the most against best.

Since November 2026 the prompt asks for judgement against the fundamentals as well (braking in a straight line and a progressive release towards the apex, no coasting, one apex placed for the exit or for speed, throttle as the steering opens, outside – inside – outside, the gear for the power band), because the driver's own best may be far from a good lap; and it allows the AI to name a corner of a real circuit it knows. Every number in a tip still has to come from DATA.

## The prompt

Always the same container: a fixed **system prompt** (identical for every request, so providers can cache it) and a **user message** with the task line and the data as JSON. Where the provider supports a JSON schema for the answer (Claude structured outputs, OpenAI, Gemini, Ollama `format`), the schema below is sent too; the bridge checks the answer anyway.

### System prompt

```text
You are a race driving coach for a sim racer. DATA holds measured facts about one section or one lap,
for up to three laps: BEST (the driver's own best, which may itself be far from a good lap), LAST (the
previous lap) and NOW (the lap being analysed). Your job: tell the driver what to do differently next
lap, in up to 9 tips. Two sources, in this order: first where NOW breaks a fundamental of fast driving,
then where NOW loses time against BEST. Every tip is linked to the data: it names the fundamental or the
loss, quotes the numbers that show it, and gives one concrete action. A fundamental that explains a loss
against BEST is one tip, not two.

Reading DATA (metres count from the section start; a larger value is later):
- corner: the section's shape from the recorded track. type (straight, fast / medium / slow corner,
  chicane), turn_deg, tightest_at_m and radius_m (the geometric apex). next_section: what follows.
  lap_m: where the section lies in the lap, metres from the start / finish line.
- trace: every 10 m [metres, km/h, throttle %, brake %, steering -100..100, off]. off (LAST and NOW,
  corners only) is the distance from the BEST line: positive = inside of the corner, negative = outside.
- lift_m, brake_on_m, brake_peak_pct, brake_off_m: where the throttle lifts, the brake comes on, how
  hard, where it is released. coast_m: total metres with neither pedal (a distance, not a place).
- min_kmh, min_at_m, gear_at_min, rpm_at_min: the slowest point. full_throttle_m: where the throttle is
  fully open again. exit_kmh: speed at the section end. entry_kmh: speed at the start, decided in the
  section before (a slow entry is that section's tip, not this one's).
- gears, shifts: the gears used and where they changed. aids: where TC / ABS / stability worked and the
  set levels.
- delta_by_50m (LAST and NOW): seconds behind BEST at every 50 m. Where it grows is where the time goes.

The fundamentals, each with the numbers that show it:
1. Braking point: brake hard and in a straight line. brake_peak_pct high early, brake_on_m before the
   steering builds up in trace.
2. Brake release: progressive, towards the apex. brake_off_m close to min_at_m, not far before it; no
   coasting (coast_m).
3. Apex: one, placed for what follows. At or after tightest_at_m when a straight or a faster section
   follows (exit speed first), earlier in a fast corner (carry speed). min_at_m against tightest_at_m.
4. Throttle: fully open as soon as the steering opens, no lift after the apex. full_throttle_m against
   the steering in trace.
5. Line: outside on entry, inside at the apex, outside on exit. off in trace against BEST.
6. Gear: the one that keeps the engine in its power band at the slowest point. gear_at_min, rpm_at_min,
   shifts.
7. Driving aids, only when the data shows it: if NOW differs from BEST in a level or in how much an aid
   worked, and that is where the time goes, say whether a higher or lower setting may help.

Rules:
- Every number in a tip comes from DATA; never invent one. The time at stake is measured (delta_by_50m,
  time_s) or, for a fundamental with nothing to measure against, estimated from the speeds in DATA with
  "about" in the text.
- Ignore differences under 0.05 s, 5 m or 3 km/h. Use LAST only to show what the driver already did
  better before ("your last lap braked at 112 m").
- If you know this real circuit (track, lap_m), name the corner and use what is commonly known about
  driving it; the numbers still come from DATA.
- Driving technique only: no car setup, no general advice, no praise, no filler.
- "note": say when a line is missing (no BEST yet, NOW not there yet) or when NOW is not slower than
  BEST anywhere; otherwise "". Give no tips when the driving is sound.

Answer with JSON only, no markdown, exactly this shape, tips ordered by gain_s, biggest first, at most 9:
{"tips": [{"title": string, "section": integer, "from_m": integer, "to_m": integer, "text": string,
"gain_s": number}], "note": string}

title: at most 4 words, an instruction in capitals, the action only (the place is shown next to it); it
must say the same as the text, and it starts with the category: BRAKING, RELEASE, APEX, THROTTLE, LINE,
GEAR, AIDS or TIME (a loss against BEST without a fundamental). text: at most 35 words, metres, km/h and
seconds, addressed to the driver, with the numbers from DATA.
```

### User message

```text
TASK: Analyse SECTION 5 (250 m) of Brands Hatch, Toyota GR86, Assetto Corsa EVO. NOW is lap 3, LAST is lap 2, BEST is the saved section best.
DATA:
{"mode": "section", "game": "Assetto Corsa EVO", "car": "Toyota GR86", "track": "Brands Hatch",
 "track_length_m": 3916, "section": 5, "section_length_m": 250, "lap_m": [1000, 1250],
 "laps": {"now": 3, "last": 2, "best": "saved section best"}, "next_section": {"section": 6, "type": "fast corner", "turn_deg": 18},
 "lines": {"best": {...facts...}, "last": {...facts...}, "now": {...facts...},
           "corner": {"type": "slow corner", "turn_deg": 109, "tightest_at_m": 184, "radius_m": 40}}}
```

Whole-track mode: `TASK: Analyse the WHOLE LAP of …`, and DATA has `"mode": "track"`, `"lap_times"`, `"sections"` (one row per section) and `"focus"` (the full facts of the 3 sections that lose the most).

### Answer schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["tips", "note"],
  "properties": {
    "tips": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["title", "section", "from_m", "to_m", "text", "gain_s"],
        "properties": {
          "title": {"type": "string"}, "section": {"type": "integer"},
          "from_m": {"type": "integer"}, "to_m": {"type": "integer"},
          "text": {"type": "string"}, "gain_s": {"type": "number"}
        }
      }
    },
    "note": {"type": "string"}
  }
}
```

No summary: the owner removed it from the tab after the first real answers (it was cut at the word limit and repeated the tips).

### Checks by the bridge

The schema has no `maxItems` and no nullable fields, so every provider's JSON-schema mode accepts it; the bridge enforces the limits itself. The answer must parse as JSON in this shape (a ```json fence is removed); tips beyond 9 are dropped; a tip whose section is not in the data, or whose place lies outside the section, is dropped; a title is cut to 4 words without a dangling `IN` / `SECTION` / number (the place is shown below it); texts over the word limits are cut at the limit with `…`. If the answer cannot be used, the tab says why (`The AI answer could not be read: ask again.`) and ASK AGAIN asks once more. Other errors shown in the tab: NO KEY, KEY REJECTED, MODEL NOT FOUND, NO CONNECTION, OLLAMA NOT RUNNING, RATE LIMITED, NO ANSWER IN TIME, AI REFUSED, NO DATA (nothing to compare yet), BUSY (one question at a time).

## First real answers (November 2026)

Two answers from Claude FAST (`claude-haiku-5-5`, effort low; Porsche 992 GT3 R, Brands Hatch), 8–9 s and about 2,500–4,200 tokens in, 1,500 out each. What they showed and what changed:

- The tab layout: titles wrapped before their last word and the summary was cut at 25 words → titles on one line with the place below, no summary.
- A title said LIFT EARLIER while the text (rightly) said to lift later: the prompt now says that metres grow along the section and that the title must say the same as the text.
- `coast_m` (total metres coasting) was read as a position ("coasting from 34 m"): explained in the prompt.
- A slower entry speed was blamed on this section: the prompt now says the entry comes from the section before.
- Gear sequences contained the neutral of each shift (`2-0-3-0-4`) and the delta stopped at 200 m of 250 m: both fixed in the facts.
- WHOLE TRACK on a lap with 2 of 16 sections driven compared only those 2: the whole track now uses the last complete lap while a lap is being driven.

## How it is built

- Bridge: `core/trainer.py`: facts (`facts`, `section_data`, `build_request` from `recorder.section()`), the prompt (`SYSTEM_PROMPT`, `SCHEMA`), one HTTPS request per provider with `urllib` (standard library only, as the whole project; Claude `POST /v1/messages` with `output_config.effort` and `output_config.format`; ChatGPT `POST /v1/chat/completions` with `reasoning_effort` and `response_format` json_schema strict; Gemini `POST /v1beta/models/<model>:generateContent` with `responseJsonSchema` and `thinkingConfig.thinkingLevel`; Ollama `POST /api/chat` with `format`), `check_answer`, the history file. One question at a time.
- API: `GET /api/trainer` (status, settings without keys, models, history), `POST /api/trainer/ask {mode: "track" | "section", section: 0-based}` (waits for the answer; HTTP 409 with `error` / `detail` when it fails), `POST /api/trainer/settings {provider, level, key, key_for}`, `POST /api/trainer/test`.
- Log: `trainer | connection`, `trainer | settings`, `trainer | answer` (view, model, seconds, tips, tokens), `trainer | error`. Never the key.
- Page: the button on the map and the TRAINER tab in `ui/js/analysis.js`; the settings rows in `ui/js/rd.js`.
- Tests (`tests/test_trainer.py`, `tests/test_server.py`): facts from simulated rows and laps, the request container, answer checks (good, fenced, too long, wrong places, not JSON), the history rolling at 5 and kept over a restart, the key never in a reply; providers simulated, no real AI call in the tests.
