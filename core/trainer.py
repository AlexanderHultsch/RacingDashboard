"""AI trainer for the analysis page (docs/TRAINER.md).

On a tap the page asks for the WHOLE TRACK (map overview) or one SECTION (map zoomed in). The trainer
computes facts from the recorded lines (best, last, now) with core/recorder.py, sends them in a fixed
prompt to the AI the owner set up (Claude, ChatGPT, Gemini or a local Ollama model), checks the JSON
answer and keeps the last 5 questions and answers in data/trainer.jsonl.

Settings (provider, FAST / BEST, the API keys) are kept on the PC in config/trainer.json (ignored by
git). An API key is never sent back to a page and never written to the log. Standard library only.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROVIDERS = ("off", "claude", "chatgpt", "gemini", "ollama")
NAMES = {"off": "OFF", "claude": "CLAUDE", "chatgpt": "CHATGPT", "gemini": "GEMINI", "ollama": "LOCAL (OLLAMA)"}
LEVELS = ("fast", "best")
HISTORY = 5                     # questions and answers kept in data/trainer.jsonl
MAX_TIPS = 3
WORDS = {"title": 4, "text": 35, "note": 30}
STOP = {"IN", "AT", "ON", "INTO", "OF", "THE", "AND", "TO", "FOR", "A", "SECTION"}   # not left dangling in a cut title
ANTHROPIC_VERSION = "2026-10-21"
# Claude models that get the server-side fallback on a refusal (docs/TRAINER.md)
CLAUDE_FALLBACK = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1")

SYSTEM_PROMPT = """You are a race driving coach for a sim racer. You get measured facts about one section or one lap of a
circuit, for up to three laps: BEST (the driver's best), LAST (the previous lap) and NOW (the lap being
analysed). Find where NOW loses time against BEST and tell the driver what to do differently next lap.

How to read DATA:
- Metres count from the section start and grow along the section: a larger value is later. To brake or
  lift "later" means a larger metre value, "earlier" a smaller one.
- coast_m is the total distance without throttle or brake in the section, not a position.
- entry_kmh comes from the section before: a slower entry is lost in the section before, so say so and
  point there instead of inventing a fix in this section.
- gears is the sequence of gears used; gear_at_min is the gear at the slowest point.

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
9. If NOW is not slower than BEST anywhere that matters, say so in "note" and give no tips.
10. If a line is missing (no BEST yet, or NOW has not reached a section), compare with what exists and
    say so in "note"; otherwise "note" is an empty string.

Answer with JSON only, no markdown, exactly this shape:
{"tips": [{"title": string, "section": integer, "from_m": integer, "to_m": integer, "text": string,
"gain_s": number}], "note": string}

Limits: title at most 4 words, an instruction in capitals ("BRAKE LATER"), the action only, without the
place (the place is shown next to it). The title must say the same as the text (later stays later).
text at most 35 words. No more than 3 tips. Plain English, metres, km/h and seconds."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tips", "note"],
    "properties": {
        "tips": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "section", "from_m", "to_m", "text", "gain_s"],
                "properties": {
                    "title": {"type": "string"}, "section": {"type": "integer"},
                    "from_m": {"type": "integer"}, "to_m": {"type": "integer"},
                    "text": {"type": "string"}, "gain_s": {"type": "number"},
                },
            },
        },
        "note": {"type": "string"},
    },
}

# FAST / BEST = a fixed model + effort pair per provider; overridable in config.toml [trainer.models]
MODELS = {
    "claude": {"fast": {"model": "claude-haiku-5-5", "effort": "medium"},
               "best": {"model": "claude-opus-5-5", "effort": "high"}},
    "chatgpt": {"fast": {"model": "gpt-6-luna", "effort": "low"},
                "best": {"model": "gpt-6-astra", "effort": "high"}},
    "gemini": {"fast": {"model": "gemini-3.8-flash", "effort": "LOW"},
               "best": {"model": "gemini-4-argon", "effort": "HIGH"}},
    # empty model: the smallest (FAST) or largest (BEST) model pulled in Ollama
    "ollama": {"fast": {"model": "", "effort": ""}, "best": {"model": "", "effort": ""}},
}


class TrainerError(Exception):
    """code: shown on the page (NO KEY, KEY REJECTED, MODEL NOT FOUND, NO INTERNET, ...)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


# ------------------------------------------------------------------ facts


def _interp(xs, ys, x):
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for i in range(1, len(xs)):
        if xs[i] >= x:
            a, b = xs[i - 1], xs[i]
            return ys[i] if b == a else ys[i - 1] + (ys[i] - ys[i - 1]) * (x - a) / (b - a)
    return ys[-1]


def facts(rows: list, time_s, best_rows: list | None = None, length: float = 250.0) -> dict | None:
    """Facts of one line in one section. rows: [d, t, v, thr, brk, str, g, ...] (recorder.section),
    d metres and t seconds from the section start. best_rows: the best line, for delta_by_50m."""
    if not rows or len(rows) < 2:
        return None
    d = [r[0] for r in rows]
    v = [r[2] for r in rows]
    thr = [r[3] for r in rows]
    brk = [r[4] for r in rows]
    out = {"time_s": None if time_s is None else round(time_s, 3), "complete": time_s is not None,
           "entry_kmh": round(v[0]), "exit_kmh": round(v[-1])}
    lift = None
    seen_full = False
    for i, value in enumerate(thr):
        if value >= 0.9:
            seen_full = True
        elif seen_full and value < 0.5:
            lift = i
            break
    out["lift_m"] = None if lift is None else round(d[lift])
    on = next((i for i, value in enumerate(brk) if value > 0.10), None)
    out["brake_on_m"] = None if on is None else round(d[on])
    out["brake_peak_pct"] = round(max(brk) * 100)
    off = None if on is None else next((i for i in range(on, len(brk)) if brk[i] < 0.05), None)
    out["brake_off_m"] = None if off is None else round(d[off])
    coast = sum(d[i] - d[i - 1] for i in range(1, len(rows)) if thr[i] <= 0.1 and brk[i] <= 0.1)
    out["coast_m"] = round(coast)
    low = min(range(len(v)), key=lambda i: v[i])
    out["min_kmh"], out["min_at_m"], out["gear_at_min"] = round(v[low]), round(d[low]), rows[low][6]
    gears = []                                    # neutral (0) during a shift is not a gear used
    for r in rows:
        if r[6] != 0 and (not gears or gears[-1] != r[6]):
            gears.append(r[6])
    out["gears"] = "-".join(str(g) for g in gears)
    full = None                                   # back above 95 % after the slowest point, held 30 m
    for i in range(low, len(rows)):
        if thr[i] < 0.95:
            continue
        j, held = i, True
        while j < len(rows) and d[j] - d[i] < 30:
            if thr[j] < 0.95:
                held = False
                break
            j += 1
        if held:
            full = i
            break
    out["full_throttle_m"] = None if full is None else round(d[full])
    out["steer_max"] = round(max(abs(r[5]) for r in rows), 2)
    aids = aid_facts(rows, d)
    if aids:
        out["aids"] = aids
    if best_rows and len(best_rows) > 1:
        bd, bt = [r[0] for r in best_rows], [r[1] for r in best_rows]
        t = [r[1] for r in rows]
        deltas = {}
        mark = 50
        marks = []
        while mark < length - 5:
            marks.append(mark)
            mark += 50
        marks.append(round(length))                   # always the section end
        for mark in marks:
            at = min(mark, d[-1], bd[-1]) if mark - min(d[-1], bd[-1]) <= 5 else mark   # the last sample may be a little short
            tm, tb = _interp(d, t, at), _interp(bd, bt, at)
            if tm is not None and tb is not None:
                deltas[str(mark)] = round(tm - tb, 3)
        out["delta_by_50m"] = deltas
    return out


AIDS = (("tc", 9), ("abs", 10), ("esc", 11))
LEVEL_NAMES = ("tc", "tc_cut", "abs", "esc", "engine_map")      # rows[12:17]


def aid_facts(rows: list, d: list) -> dict | None:
    """Where TC / ABS / stability worked and the set levels (rows from recorder.section, columns 9-16)."""
    if len(rows[0]) < 17:
        return None
    out = {}
    total = (d[-1] - d[0]) or 1.0
    for name, i in AIDS:
        if all(r[i] is None for r in rows):
            continue
        on = sum(d[k + 1] - d[k] for k in range(len(rows) - 1) if rows[k][i])
        first = next((r[0] for r in rows if r[i]), None)
        out[f"{name}_working_m"] = round(on)
        out[f"{name}_working_pct"] = round(on / total * 100)
        out[f"{name}_first_m"] = None if first is None else round(first)
    start = {n: rows[0][12 + k] for k, n in enumerate(LEVEL_NAMES) if rows[0][12 + k] is not None}
    if start:
        out["levels"] = start
    changes = []
    for k in range(1, len(rows)):
        for j, n in enumerate(LEVEL_NAMES):
            if rows[k][12 + j] != rows[k - 1][12 + j]:
                changes.append({"at_m": round(rows[k][0]), "setting": n, "to": rows[k][12 + j]})
    if changes:
        out["level_changes"] = changes[:10]
    return out or None


def section_data(sec: dict) -> dict:
    """The three lines of one section (recorder.section) as facts."""
    length = (sec.get("to_m") or 0) - (sec.get("from_m") or 0) or 250.0
    best = facts(sec["best"], sec.get("best_time"), None, length)
    return {
        "best": best,
        "last": facts(sec["last"], sec.get("last_time"), sec["best"], length),
        "now": facts(sec["now"], sec.get("now_time"), sec["best"], length),
    }


def build_request(rec, mode: str, n: int | None, game_name: str = "") -> tuple[str, dict, dict]:
    """(task line, DATA, view) for the recorder's current lines. view: what the page shows as title."""
    state = rec.state()
    if not state.get("active"):
        raise TrainerError("NO DATA", "no run yet")
    meta = {"game": game_name or state["game"], "car": state["car"], "track": state["track"],
            "track_length_m": round(state["track_length_m"]), "section_m": state["section_m"]}
    from_game = meta["game"]
    laps = {"now": state.get("red_lap"), "last": state.get("blue_lap")}
    head = f"of {state['track']}, {state['car']}, {from_game}. NOW is lap {laps['now']}, LAST is lap {laps['last']}"
    if mode == "section":
        if n is None or not 0 <= n < state["sections"]:
            raise TrainerError("NO DATA", "no such section")
        sec = rec.section(n)
        lines = section_data(sec)
        if not any(lines.values()):
            raise TrainerError("NO DATA", "nothing recorded in this section yet")
        length = round(sec["to_m"] - sec["from_m"])
        data = {"mode": "section", **meta, "section": n + 1, "section_length_m": length,
                "laps": dict(laps, best="saved section best"), "lines": lines}
        task = f"TASK: Analyse SECTION {n + 1} ({length} m) {head}, BEST is the saved section best."
        if lines["now"] and not lines["now"]["complete"]:
            task += " NOW has not finished this section yet."
        times = [("NOW LAP " + str(laps["now"]) + " ", sec.get("now_time")), ("BEST ", sec.get("best_time")),
                 ("LAST ", sec.get("last_time"))]
        view = {"mode": "section", "section": n + 1, "title": f"SECTION {n + 1}",
                "times": " · ".join(f"{k}{v:.3f}" for k, v in times if v is not None)}
        return task, data, view
    # whole track: the lap in progress only once it is complete, else the last complete lap
    now_lap, last_lap = rec.complete_laps()
    laps = {"now": now_lap.no if now_lap else None, "last": last_lap.no if last_lap else None}
    head = f"of {state['track']}, {state['car']}, {from_game}. NOW is lap {laps['now']}, LAST is lap {laps['last']}"
    rows, secs = [], {}
    for k in range(state["sections"]):
        sec = rec.section(k, (now_lap, last_lap))
        secs[k] = sec
        b, last, now = sec.get("best_time"), sec.get("last_time"), sec.get("now_time")
        rows.append({"section": k + 1, "best_s": b, "last_s": last, "now_s": now,
                     "now_vs_best": None if now is None or b is None else round(now - b, 3),
                     "now_vs_last": None if now is None or last is None else round(now - last, 3)})
    if not any(r["now_s"] or r["last_s"] or r["best_s"] for r in rows):
        raise TrainerError("NO DATA", "no section recorded yet")
    losing = sorted((r for r in rows if r["now_vs_best"] is not None and r["now_vs_best"] > 0.05),
                    key=lambda r: -r["now_vs_best"])[:3]
    focus = [{"section": r["section"], "lines": section_data(secs[r["section"] - 1])} for r in losing]
    driven = [r["section"] for r in rows if r["now_s"] is not None]
    lap_times = {"best_lap_s": state.get("base_lap"),
                 "last_lap_s": None if not last_lap or last_lap.time is None else round(last_lap.time, 3),
                 "now_lap_s": None if not now_lap or now_lap.time is None else round(now_lap.time, 3)}
    data = {"mode": "track", **meta, "sections_count": state["sections"],
            "laps": dict(laps, best="saved best lap and section bests"), "lap_times": lap_times,
            "now_sections_driven": driven, "sections": rows, "focus": focus}
    task = f"TASK: Analyse the WHOLE LAP {head}, BEST is the saved best (lap and section bests)."
    if driven and len(driven) < state["sections"]:
        task += f" NOW has driven sections {driven[0]}-{driven[-1]} so far."
    loss = sum(r["now_vs_best"] for r in rows if r["now_vs_best"] is not None)
    view = {"mode": "track", "section": None, "title": "WHOLE TRACK",
            "times": f"NOW LAP {laps['now']} · {len(driven)} OF {state['sections']} SECTIONS · "
                     f"{'+' if loss >= 0 else '−'}{abs(loss):.3f} VS BEST"}
    return task, data, view


# ------------------------------------------------------------------ answer


def _cut(text, limit: int) -> str:
    words = str(text or "").split()
    return " ".join(words) if len(words) <= limit else " ".join(words[:limit]) + "…"


def _title(text) -> str:
    """A tip title in capitals, at most 4 words, without a dangling "IN SECTION" or trailing punctuation."""
    words = str(text or "").upper().replace(",", " ").split()
    words = words[:WORDS["title"]]
    while len(words) > 1 and (words[-1] in STOP or words[-1].isdigit()):
        words.pop()
    return " ".join(words)


def check_answer(text: str, data: dict) -> dict:
    """The AI's JSON answer, checked: at most 3 tips, places that exist in DATA, word limits."""
    raw = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.S)
    if fence:
        raw = fence.group(1)
    try:
        answer = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        try:
            answer = json.loads(raw[start:end + 1]) if start >= 0 < end else None
        except ValueError:
            answer = None
    if not isinstance(answer, dict) or not isinstance(answer.get("tips", []), list) or not ("tips" in answer or "note" in answer):
        raise TrainerError("ANSWER NOT READABLE", raw[:120])
    if data["mode"] == "section":
        allowed = {data["section"]: data["section_length_m"]}
    else:
        allowed = {r["section"]: data["section_m"] for r in data["sections"]}
    tips = []
    for tip in answer.get("tips") or []:
        if not isinstance(tip, dict):
            continue
        try:
            sec, a, b = int(tip["section"]), int(tip["from_m"]), int(tip["to_m"])
            gain = round(float(tip["gain_s"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        if sec not in allowed or a < 0 or b < a or a > allowed[sec] + 5:
            continue
        tips.append({"title": _title(tip.get("title")), "section": sec,
                     "from_m": a, "to_m": min(b, round(allowed[sec])), "text": _cut(tip.get("text"), WORDS["text"]),
                     "gain_s": max(0.0, gain)})
        if len(tips) == MAX_TIPS:
            break
    return {"tips": tips, "note": _cut(answer.get("note") or "", WORDS["note"])}


# ------------------------------------------------------------------ providers


def _http(url: str, body: dict | None, headers: dict, timeout: float) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=dict(headers, **({"content-type": "application/json"} if data else {})),
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8", "replace")[:300]
        except OSError:
            detail = ""
        if error.code in (401, 403):
            raise TrainerError("KEY REJECTED", f"HTTP {error.code}") from None
        if error.code == 404:
            raise TrainerError("MODEL NOT FOUND", f"HTTP 404 {detail[:120]}") from None
        if error.code == 429:
            raise TrainerError("RATE LIMITED", "HTTP 429") from None
        raise TrainerError("AI ERROR", f"HTTP {error.code} {detail[:160]}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            raise TrainerError("NO ANSWER IN TIME", str(reason)) from None
        raise TrainerError("NO CONNECTION", str(reason)) from None


class Provider:
    def __init__(self, key: str, model: str, effort: str, timeout: float, base: str = ""):
        self.key, self.model, self.effort, self.timeout, self.base = key, model, effort, timeout, base

    def check(self) -> str:
        """Confirms key and model (no cost); returns the model name in use."""
        raise NotImplementedError

    def ask(self, system: str, user: str) -> tuple[str, dict]:
        """(answer text, {"in": tokens, "out": tokens})"""
        raise NotImplementedError


class Claude(Provider):
    URL = "https://api.anthropic.com/v1"

    def headers(self, beta: bool = False) -> dict:
        h = {"x-api-key": self.key, "anthropic-version": ANTHROPIC_VERSION}
        if beta:
            h["anthropic-beta"] = "server-side-fallback-2026-07-01"
        return h

    def check(self) -> str:
        _http(f"{self.URL}/models/{self.model}", None, self.headers(), self.timeout)
        return self.model

    def ask(self, system, user):
        fallback = self.model in CLAUDE_FALLBACK
        body = {"model": self.model, "max_tokens": 16000, "system": system,
                "messages": [{"role": "user", "content": user}],
                "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}}}
        if fallback:                       # a refusal is retried on a fallback model by the API
            body["fallbacks"] = "default"
        reply = _http(f"{self.URL}/messages", body, self.headers(fallback), self.timeout)
        if reply.get("stop_reason") == "refusal":
            raise TrainerError("AI REFUSED", str((reply.get("stop_details") or {}).get("category") or ""))
        text = "".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text")
        usage = reply.get("usage") or {}
        return text, {"in": usage.get("input_tokens"), "out": usage.get("output_tokens")}


class ChatGPT(Provider):
    URL = "https://api.openai.com/v1"

    def headers(self) -> dict:
        return {"authorization": f"Bearer {self.key}"}

    def check(self) -> str:
        models = _http(f"{self.URL}/models", None, self.headers(), self.timeout).get("data") or []
        if self.model not in {m.get("id") for m in models}:
            raise TrainerError("MODEL NOT FOUND", self.model)
        return self.model

    def ask(self, system, user):
        body = {"model": self.model, "max_completion_tokens": 16000, "reasoning_effort": self.effort,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "trainer_answer", "schema": SCHEMA, "strict": True}}}
        reply = _http(f"{self.URL}/chat/completions", body, self.headers(), self.timeout)
        message = ((reply.get("choices") or [{}])[0]).get("message") or {}
        if message.get("refusal"):
            raise TrainerError("AI REFUSED", str(message["refusal"])[:120])
        usage = reply.get("usage") or {}
        return message.get("content") or "", {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}


class Gemini(Provider):
    URL = "https://generativelanguage.googleapis.com/v1beta"

    def headers(self) -> dict:
        return {"x-goog-api-key": self.key}

    def check(self) -> str:
        _http(f"{self.URL}/models/{self.model}", None, self.headers(), self.timeout)
        return self.model

    def ask(self, system, user):
        config = {"responseMimeType": "application/json", "responseJsonSchema": SCHEMA}
        if self.effort:
            config["thinkingConfig"] = {"thinkingLevel": self.effort}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": config}
        reply = _http(f"{self.URL}/models/{self.model}:generateContent", body, self.headers(), self.timeout)
        parts = (((reply.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        usage = reply.get("usageMetadata") or {}
        return text, {"in": usage.get("promptTokenCount"), "out": usage.get("candidatesTokenCount")}


class Ollama(Provider):
    def __init__(self, key, model, effort, timeout, base="", level="fast"):
        super().__init__(key, model, effort, timeout, base or "http://localhost:11434")
        self.level = level

    def check(self) -> str:
        try:
            tags = _http(f"{self.base}/api/tags", None, {}, min(self.timeout, 5)).get("models") or []
        except TrainerError as error:
            if error.code == "NO CONNECTION":
                raise TrainerError("OLLAMA NOT RUNNING", error.detail) from None
            raise
        if not tags:
            raise TrainerError("MODEL NOT FOUND", "no model pulled in Ollama")
        names = [t.get("name") for t in tags]
        if self.model:
            if self.model not in names:
                raise TrainerError("MODEL NOT FOUND", self.model)
            return self.model
        ordered = sorted(tags, key=lambda t: t.get("size") or 0)
        self.model = (ordered[0] if self.level == "fast" else ordered[-1]).get("name")
        return self.model

    def ask(self, system, user):
        if not self.model:
            self.check()
        body = {"model": self.model, "stream": False, "format": SCHEMA,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        reply = _http(f"{self.base}/api/chat", body, {}, self.timeout)
        return (reply.get("message") or {}).get("content") or "", {"in": reply.get("prompt_eval_count"),
                                                                   "out": reply.get("eval_count")}


CLASSES = {"claude": Claude, "chatgpt": ChatGPT, "gemini": Gemini, "ollama": Ollama}


# ------------------------------------------------------------------ the trainer


def hint(key: str) -> str:
    """What a page may see of a key: the start and the last 4 characters."""
    if not key:
        return ""
    head = key[:7] if len(key) > 16 else key[:3]
    return f"{head}…{key[-4:]}"


class Trainer:
    def __init__(self, cfg: dict, settings_file, data_dir, log=None):
        self.cfg = cfg.get("trainer", {})
        self.settings_file = Path(settings_file)
        self.history_file = Path(data_dir) / "trainer.jsonl"
        self.log = log or (lambda *args: None)
        self.lock = threading.RLock()
        self.busy = False
        self.settings = self._load_settings()
        self.status = {"state": "unchecked", "error": None, "detail": "", "checked": None, "ms": None, "model": None}
        self.history = self._load_history()

    # ---------------------------------------------------------- settings

    def _load_settings(self) -> dict:
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("provider", "off")
        data.setdefault("level", "fast")
        data.setdefault("keys", {})
        if data["provider"] not in PROVIDERS:
            data["provider"] = "off"
        if data["level"] not in LEVELS:
            data["level"] = "fast"
        return data

    def _save_settings(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def model_for(self, provider: str, level: str) -> dict:
        entry = dict(MODELS.get(provider, {}).get(level, {}))
        entry.update((self.cfg.get("models", {}).get(provider, {}) or {}).get(level, {}) or {})
        return entry

    def provider(self) -> Provider:
        name, level = self.settings["provider"], self.settings["level"]
        if name == "off":
            raise TrainerError("OFF")
        key = self.settings["keys"].get(name, "")
        if name != "ollama" and not key:
            raise TrainerError("NO KEY")
        entry = self.model_for(name, level)
        timeout = float(self.cfg.get("timeout_s", 90))
        if name == "ollama":
            return Ollama(key, entry.get("model", ""), entry.get("effort", ""), timeout,
                          self.cfg.get("ollama_url", ""), level)
        return CLASSES[name](key, entry.get("model", ""), entry.get("effort", ""), timeout)

    def update(self, changes: dict) -> dict:
        """Settings from a page: provider, level, key (for the provider given or the current one)."""
        with self.lock:
            if changes.get("provider") in PROVIDERS:
                self.settings["provider"] = changes["provider"]
            if changes.get("level") in LEVELS:
                self.settings["level"] = changes["level"]
            if isinstance(changes.get("key"), str):
                target = changes.get("key_for") if changes.get("key_for") in CLASSES else self.settings["provider"]
                key = changes["key"].strip()
                if key:
                    self.settings["keys"][target] = key
                else:
                    self.settings["keys"].pop(target, None)
            self._save_settings()
            self.log("trainer", "settings", f"{self.settings['provider']} {self.settings['level']}")
        return self.test()

    # ---------------------------------------------------------- connection

    def test(self) -> dict:
        """Checks key and model without cost; the result greys the page's button in or out."""
        started = time.monotonic()
        status = {"state": "error", "error": None, "detail": "", "model": None}
        try:
            provider = self.provider()
            status["model"] = provider.check()
            status["state"] = "ok"
        except TrainerError as error:
            status["state"] = "off" if error.code == "OFF" else "error"
            status["error"], status["detail"] = error.code, error.detail
            if status["model"] is None and self.settings["provider"] not in ("off",):
                status["model"] = self.model_for(self.settings["provider"], self.settings["level"]).get("model") or None
        status["checked"] = time.strftime("%H:%M")
        status["ms"] = round((time.monotonic() - started) * 1000)
        with self.lock:
            self.status = status
        if status["state"] != "off":
            self.log("trainer", "connection", f"{self.settings['provider']} {status['model'] or '-'}: "
                     + ("ok" if status["state"] == "ok" else f"{status['error']} {status['detail']}"[:160]))
        return self.public()

    def test_later(self) -> None:
        threading.Thread(target=self.test, daemon=True).start()

    # ---------------------------------------------------------- asking

    def ask(self, rec, mode: str, section, game_name: str = "") -> dict:
        with self.lock:
            if self.busy:
                raise TrainerError("BUSY", "a question is already on its way")
            self.busy = True
        try:
            if mode not in ("track", "section"):
                raise TrainerError("NO DATA", "mode")
            task, data, view = build_request(rec, mode, None if section is None else int(section), game_name)
            provider = self.provider()
            if not provider.model and isinstance(provider, Ollama):
                provider.check()
            user = task + "\nDATA:\n" + json.dumps(data, separators=(",", ":"))
            started = time.monotonic()
            try:
                text, usage = provider.ask(SYSTEM_PROMPT, user)
            except TrainerError as error:
                if error.code in ("KEY REJECTED", "MODEL NOT FOUND", "NO CONNECTION", "OLLAMA NOT RUNNING"):
                    with self.lock:
                        self.status.update(state="error", error=error.code, detail=error.detail)
                raise
            seconds = round(time.monotonic() - started, 1)
            answer = check_answer(text, data)
            entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **view, "game": data["game"], "car": data["car"],
                     "track": data["track"], "laps": data["laps"], "provider": self.settings["provider"],
                     "level": self.settings["level"], "model": provider.model, "effort": provider.effort,
                     "seconds": seconds, "tokens": usage, "answer": answer, "task": task, "data": data}
            self._add_history(entry)
            self.log("trainer", "answer", f"{view['title']} · {provider.model} · {seconds} s · "
                     f"{len(answer['tips'])} tips · tokens {usage.get('in')}/{usage.get('out')}")
            return self._public_entry(entry)
        finally:
            with self.lock:
                self.busy = False

    # ---------------------------------------------------------- history

    def _load_history(self) -> list:
        try:
            lines = self.history_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("answer"):
                out.append(item)
        return out[-HISTORY:]

    def _add_history(self, entry: dict) -> None:
        with self.lock:
            self.history = (self.history + [entry])[-HISTORY:]
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.history_file.with_name(self.history_file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for item in self.history:
                    f.write(json.dumps(item, separators=(",", ":")) + "\n")
            tmp.replace(self.history_file)

    @staticmethod
    def _public_entry(entry: dict) -> dict:
        return {k: entry.get(k) for k in ("at", "mode", "section", "title", "times", "car", "track", "provider",
                                          "level", "model", "seconds", "answer")}

    # ---------------------------------------------------------- for the pages

    def public(self) -> dict:
        """Status and history for the pages: never a key, only whether one is set and its hint."""
        with self.lock:
            name, level = self.settings["provider"], self.settings["level"]
            models = {p: {lv: self.model_for(p, lv).get("model") or "smallest / largest pulled model"
                          for lv in LEVELS} for p in CLASSES}
            return {
                "provider": name, "provider_name": NAMES[name], "level": level,
                "providers": [[p, NAMES[p]] for p in PROVIDERS], "models": models,
                "model": self.status.get("model") or (models.get(name, {}).get(level) if name != "off" else None),
                "keys": {p: hint(self.settings["keys"].get(p, "")) for p in CLASSES if p != "ollama"},
                "ok": self.status.get("state") == "ok", "state": self.status.get("state"),
                "error": self.status.get("error"), "detail": self.status.get("detail", ""),
                "checked": self.status.get("checked"), "ms": self.status.get("ms"), "busy": self.busy,
                "history": [self._public_entry(e) for e in reversed(self.history)],
            }
