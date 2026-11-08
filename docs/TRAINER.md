# AI trainer – agreed definition

Agreed with the owner in an interview (November 2026). **Built** (November 2026): `core/trainer.py`, `ui/js/analysis.js` (button, TRAINER tab), `ui/js/rd.js` (settings), tests in `tests/test_trainer.py`. Tested with a simulated AI only; **not yet with a real Claude / ChatGPT / Gemini / Ollama answer**. Mockups: `mockups/analysis-ai-trainer.png` and `mockups/settings-ai.png` (local, not in git). This replaces the earlier rule "no coaching, no tips" on the analysis page: tips come only from the trainer, and only when the driver taps it.

## What it does

The analysis page gets an **AI TRAINER** button. A tap sends what the page shows to an AI of the owner's choice and shows its answer: up to 3 tips on where the time goes and what to change.

| Mode | When | What is analysed |
| --- | --- | --- |
| **WHOLE TRACK** | the map shows the overview | the whole lap: every section's time for best, last and now, plus the full facts of the 3 sections where now loses the most against best |
| **SECTION n** | the map is zoomed into section n | that section only, with its full facts |

Lines, as everywhere on the page: **best** = the saved best (baseline lap, or the section bests), **last** = the last lap, **now** = the lap in progress (only the sections it has reached) or, between laps and after the run, the last complete lap.

## The page

- **Button:** bottom right of the map, `AI TRAINER` plus what it will analyse (`WHOLE TRACK` / `SECTION 5`). Greyed out when the AI connection does not work, when the trainer is OFF, or when there is nothing to compare (no best and no last line).
- **Answer:** a third tab **TRAINER** next to REVIEW and GRAPHS. The tap asks the AI and opens the tab; while waiting it says `ASKING CLAUDE · FAST · <model>`. Tapping a tip opens its section in GRAPHS with the cursor at the tip's place.
- **Tab content:** what was analysed and the times (`SECTION 5 · NOW LAP 3 8.059 · BEST 7.646 · LAST 7.819`), the summary line, the tips (number, title, place, text, time at stake), the provider / level / time / duration, `ASK AGAIN`, and the earlier answers as chips under `EARLIER` (tap one to show it).
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
| Claude | `claude-haiku-5-5`, effort `low` | `claude-opus-5-5`, effort `high` |
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
- Rough cost per question (about 3,000 tokens in, under 1,000 out): Claude FAST well under a cent, Claude BEST a few cents. Ollama is free.

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
| `gear_at_min` | gear at the slowest point |
| `gears` | gear sequence through the section, e.g. `"4-3-4"` |
| `full_throttle_m` | where the throttle is back above 95 % (held for 30 m) after the slowest point |
| `steer_max` | largest steering, 0–1 of full lock |
| `delta_by_50m` | time behind best (positive = slower) at every 50 m (`now` and `last` only) |
| `aids` | driving aids, when recorded: `tc_working_m`, `tc_working_pct`, `tc_first_m` (and the same for `abs`, `esc`), `levels` at the section start (`tc`, `tc_cut`, `abs`, `esc`, `engine_map`), `level_changes` (`at_m`, `setting`, `to`) |

Whole-track mode adds a `sections` table (per section: best / last / now time and the deltas) and the lap times; the full facts are sent for the 3 sections where now loses the most against best.

## The prompt

Always the same container: a fixed **system prompt** (identical for every request, so providers can cache it) and a **user message** with the task line and the data as JSON. Where the provider supports a JSON schema for the answer (Claude structured outputs, OpenAI, Gemini, Ollama `format`), the schema below is sent too; the bridge checks the answer anyway.

### System prompt

```text
You are a race driving coach for a sim racer. You get measured facts about one section or one lap of a
circuit, for up to three laps: BEST (the driver's best), LAST (the previous lap) and NOW (the lap being
analysed). Find where NOW loses time against BEST and tell the driver what to do differently next lap.

How to analyse:
1. Use only the numbers in DATA. Never invent a number. A time you give must come from time_s or
   delta_by_50m; a place must be a section and metres from DATA.
2. Compare NOW with BEST. Use LAST only to show what the driver already did better before
   ("your last lap braked at 112 m").
3. Look at these, in this order: braking point (brake_on_m, lift_m), brake release (brake_off_m), coasting
   (coast_m), minimum speed and where it is (min_kmh, min_at_m), throttle pickup (full_throttle_m),
   gear at the slowest point (gear_at_min, gears), exit speed (exit_kmh).
4. Find the place from delta_by_50m: where the delta grows is where the time goes.
   Driving aids ("aids"): where TC, ABS and stability worked (*_working_m, *_working_pct, *_first_m) and
   the set levels (levels, level_changes). If NOW differs from BEST in an aid level or in how much an aid
   worked, and that is where NOW loses or gains time, say whether a lower or higher setting may help.
   Only when the data shows it; never as a general rule.
5. Ignore differences smaller than 0.05 s, 5 m or 3 km/h.
6. Give one concrete action per tip that the driver can try on the next lap. Name the place as section
   and metres. Give the time at stake, rounded to 0.05 s.
7. Order the tips by time at stake, biggest first. At most 3 tips; fewer if fewer places matter.
8. Driving technique only: no car setup, no assists, no general safety advice, no praise, no filler.
9. If NOW is not slower than BEST anywhere that matters, say so in the summary and give no tips.
10. If a line is missing (no BEST yet, or NOW has not reached a section), compare with what exists and
    say so in "note"; otherwise "note" is an empty string.

Answer with JSON only, no markdown, exactly this shape:
{"summary": string, "tips": [{"title": string, "section": integer, "from_m": integer, "to_m": integer,
"text": string, "gain_s": number}], "note": string}

Limits: summary at most 25 words. title at most 4 words, an instruction in capitals ("BRAKE LATER").
text at most 35 words. No more than 3 tips. Plain English, metres, km/h and seconds.
```

### User message

```text
TASK: Analyse SECTION 5 (250 m) of Brands Hatch, Toyota GR86, Assetto Corsa EVO. NOW is lap 3, LAST is lap 2, BEST is the saved section best.
DATA:
{"mode": "section", "game": "Assetto Corsa EVO", "car": "Toyota GR86", "track": "Brands Hatch",
 "track_length_m": 3916, "section": 5, "section_m": 250, "laps": {"now": 3, "last": 2, "best": "baseline"},
 "lines": {"best": {...facts...}, "last": {...facts...}, "now": {...facts...}}}
```

Whole-track mode: `TASK: Analyse the WHOLE LAP of …`, and DATA has `"mode": "track"`, `"lap_times"`, `"sections"` (one row per section) and `"focus"` (the full facts of the 3 sections that lose the most).

### Answer schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["summary", "tips", "note"],
  "properties": {
    "summary": {"type": "string"},
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

### Checks by the bridge

The schema has no `maxItems` and no nullable fields, so every provider's JSON-schema mode accepts it; the bridge enforces the limits itself. The answer must parse as JSON in this shape (a ```json fence is removed); tips beyond 3 are dropped; a tip whose section is not in the data, or whose place lies outside the section, is dropped; texts over the word limits are cut at the limit with `…`. If the answer cannot be used, the tab says why (`The AI answer could not be read: ask again.`) and ASK AGAIN asks once more. Other errors shown in the tab: NO KEY, KEY REJECTED, MODEL NOT FOUND, NO CONNECTION, OLLAMA NOT RUNNING, RATE LIMITED, NO ANSWER IN TIME, AI REFUSED, NO DATA (nothing to compare yet), BUSY (one question at a time).

## How it is built

- Bridge: `core/trainer.py`: facts (`facts`, `section_data`, `build_request` from `recorder.section()`), the prompt (`SYSTEM_PROMPT`, `SCHEMA`), one HTTPS request per provider with `urllib` (standard library only, as the whole project; Claude `POST /v1/messages` with `output_config.effort` and `output_config.format`; ChatGPT `POST /v1/chat/completions` with `reasoning_effort` and `response_format` json_schema strict; Gemini `POST /v1beta/models/<model>:generateContent` with `responseJsonSchema` and `thinkingConfig.thinkingLevel`; Ollama `POST /api/chat` with `format`), `check_answer`, the history file. One question at a time.
- API: `GET /api/trainer` (status, settings without keys, models, history), `POST /api/trainer/ask {mode: "track" | "section", section: 0-based}` (waits for the answer; HTTP 409 with `error` / `detail` when it fails), `POST /api/trainer/settings {provider, level, key, key_for}`, `POST /api/trainer/test`.
- Log: `trainer | connection`, `trainer | settings`, `trainer | answer` (view, model, seconds, tips, tokens), `trainer | error`. Never the key.
- Page: the button on the map and the TRAINER tab in `ui/js/analysis.js`; the settings rows in `ui/js/rd.js`.
- Tests (`tests/test_trainer.py`, `tests/test_server.py`): facts from simulated rows and laps, the request container, answer checks (good, fenced, too long, wrong places, not JSON), the history rolling at 5 and kept over a restart, the key never in a reply; providers simulated, no real AI call in the tests.
