/* Racing Dashboard client library: one file every page loads.
 *
 * - RD.connect()       live telemetry from the bridge (Server-Sent Events at the chosen rate)
 * - data-rd="field"    any element with this attribute shows that telemetry field,
 *   data-fmt="name"    formatted with RD.formats[name] (gear, speed, rpm, lap, delta, ...)
 * - data-rd-on="field" toggles the class "on" while the field is truthy
 * - RD.widgets         rev lights (.rd-revlights), LED shift strip (.rd-leds), RPM bar (.rd-rpmbar);
 *                      js/seg14.js adds 14-segment displays (.rd-seg, .rd-seg-text)
 * - RD.styles          the visual styles of a page, cycled with the style button
 * - RD.settings        the settings overlay (game, update rate, units, screen, AI trainer, info)
 * - RD.command()       sends a button to the game
 *
 * A page needs: <body data-page="gear" data-styles="segment"> (one or more styles, comma-separated) and
 * <link id="rd-style" rel="stylesheet">. Everything else is optional.
 * Body classes set while driving: rd-stale (no data), rd-error (any error), rd-shift, rd-limiter, rd-maxrev (the game's
 * limiter signal), rd-redzone (the red rev lights are lit), rd-pit, rd-tc, rd-abs.
 *
 * Errors: RD.errorOf(frame) returns the error text or null: no connection to the PC, data the page
 * cannot read, an error the bridge reports (frame.error: game not running, no new data, unexpected
 * values ...), or a page check (RD.checks, e.g. a gear above 9 on a one-digit display). While there is
 * an error the gear shows E, the rev lights stay off and the .rd-nodata chip shows "E · <text>".
 */
(function () {
  "use strict";

  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem("rd." + key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem("rd." + key, JSON.stringify(value)); } catch (e) { /* private mode */ }
    },
  };

  const RD = {
    frame: {},          // the latest telemetry frame
    info: null,         // /api/info: games, buttons, address
    listeners: [],      // functions called with each rendered frame
    store,
  };

  /* ------------------------------------------------------------ formats */

  const pad = (n, w) => String(n).padStart(w, "0");
  RD.formats = {
    text: (v) => (v === null || v === undefined || v === "" ? "-" : String(v)),
    /* the gear: E on errors, P for park, R, N, or the gear number (also with an automatic gearbox or an
       electric car: the owner wants the number, no D / S letters) */
    gear: (v, f) => {
      f = f || {};
      if (RD.errorOf(f) || !Number.isInteger(v)) return "E";
      const mode = f.gear_mode;
      if (mode === "P") return "P";
      return v < 0 ? "R" : v === 0 ? "N" : String(v);
    },
    // one-character gear display: E also for gears above 9 or below R
    gearseg: (v, f) => {
      const text = RD.formats.gear(v, f);
      return /^\d+$/.test(text) && Number(text) > 9 ? "E" : text;
    },
    rpm: (v) => (v ? String(Math.round(v)) : "0"),
    speed: (v) => String(Math.round((v || 0) * (RD.units() === "mph" ? 0.621371 : 1))),
    speedunit: () => (RD.units() === "mph" ? "MPH" : "KM/H"),
    level: (v) => (v === null || v === undefined ? "-" : String(v)),
    bias: (v) => (v === null || v === undefined ? "-" : (v * 100).toFixed(1)),
    fuel: (v) => (v === null || v === undefined ? "-" : v.toFixed(1)),
    onoff: (v) => (v ? "ON" : "OFF"),
    lap: (ms) => {
      if (!ms && ms !== 0) return "-:--.---";
      const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
      return m + ":" + pad(s, 2) + "." + pad(Math.floor(ms % 1000), 3);
    },
    delta: (ms) => (ms === null || ms === undefined ? "-.---" : (ms < 0 ? "-" : "+") + (Math.abs(ms) / 1000).toFixed(3)),
    position: (v, f) => (v ? "P" + v + (f.cars ? "/" + f.cars : "") : "P-"),
    fuellaps: (v, f) => (f.fuel_l && f.fuel_per_lap_l ? (f.fuel_l / f.fuel_per_lap_l).toFixed(1) : "-"),
  };

  RD.units = () => store.get("units", "kmh");

  /* ------------------------------------------------------------ connection */

  let source = null;
  let lastMessage = 0;
  let pending = false;
  let frames = 0;
  RD.fps = 0;

  RD.rate = () => store.get("hz", 60);

  RD.lost = true;          // no message from the PC for a while
  RD.badData = false;      // the last message could not be read

  function schedule() {
    if (!pending) { pending = true; requestAnimationFrame(render); }
  }

  RD.connect = function () {
    if (source) source.close();
    source = new EventSource("/stream?hz=" + RD.rate());
    source.onmessage = (event) => {
      lastMessage = performance.now();
      frames += 1;
      RD.lost = false;
      try {
        const frame = JSON.parse(event.data);
        if (!frame || typeof frame !== "object") throw new Error("not an object");
        // the bridge serves newer page files (an update, then a restart): load them
        if (frame.ui) {
          if (RD.uiVersion === undefined) RD.uiVersion = frame.ui;
          else if (frame.ui !== RD.uiVersion) { location.reload(); return; }
        }
        RD.frame = frame;
        RD.badData = false;
      } catch (e) {
        RD.badData = true;
      }
      schedule();
    };
  };

  setInterval(() => { RD.fps = frames; frames = 0; }, 1000);
  setInterval(() => {   // no message for 2.5 s (the stream sends a heartbeat every second): the PC is gone
    const lost = performance.now() - lastMessage > 2500;
    if (lost !== RD.lost) { RD.lost = lost; schedule(); }
  }, 500);

  /* Error text for a frame, or null. Pages add their own checks to RD.checks: (frame) => text | null.
     RD.notices are hints for the chip only (the data is fine, e.g. a gear the display cannot show). */
  RD.checks = [];
  RD.notices = [];
  RD.noticeOf = function (f) {
    for (const notice of RD.notices) {
      const text = notice(f);
      if (text) return text;
    }
    return null;
  };
  RD.errorOf = function (f) {
    if (RD.lost) return "NO CONNECTION TO THE PC";
    if (RD.badData) return "DATA FROM THE PC NOT READABLE";
    if (f.error) return f.error_text || String(f.error).toUpperCase();
    if (!f.connected) return "NO DATA FROM THE GAME";
    for (const check of RD.checks) {
      const text = check(f);
      if (text) return text;
    }
    return null;
  };
  document.addEventListener("visibilitychange", () => { if (!document.hidden) RD.connect(); });

  /* ------------------------------------------------------------ rendering */

  const bound = [];

  RD.bind = function (root) {
    (root || document).querySelectorAll("[data-rd], [data-rd-on]").forEach((el) => {
      bound.push({ el, field: el.dataset.rd, on: el.dataset.rdOn, fmt: RD.formats[el.dataset.fmt || "text"] || RD.formats.text, last: undefined, lastOn: undefined });
    });
  };

  let lastError;
  function render() {
    pending = false;
    const f = RD.frame;
    const body = document.body.classList;
    const error = RD.errorOf(f);
    const chipText = error || RD.noticeOf(f);
    body.toggle("rd-stale", RD.lost || !f.connected);
    body.toggle("rd-error", !!error);
    body.toggle("rd-notice", !!chipText);
    if (chipText !== lastError) {
      document.querySelectorAll(".rd-nodata").forEach((chip) => { chip.textContent = chipText ? "E \u00b7 " + chipText : ""; });
      lastError = chipText;
    }
    body.toggle("rd-shift", !!f.shift_up);
    body.toggle("rd-limiter", !!f.limiter);
    body.toggle("rd-maxrev", !error && !!f.limiter);             // the game's own rev limiter signal only
    body.toggle("rd-pit", !!f.pit_limiter);
    body.toggle("rd-tc", !!f.tc_active);
    body.toggle("rd-abs", !!f.abs_active);
    for (const b of bound) {
      if (b.field) {
        const text = b.fmt(f[b.field], f);
        if (text !== b.last) { b.el.textContent = text; b.last = text; }
      }
      if (b.on) {
        const on = !!f[b.on];
        if (on !== b.lastOn) { b.el.classList.toggle("on", on); b.lastOn = on; }
      }
    }
    for (const w of widgets) w(f);
    for (const fn of RD.listeners) fn(f);
  }

  /* ------------------------------------------------------------ widgets */

  const widgets = [];
  RD.widgets = {};

  // The game's shift point is learned per car and gear: the rpm share at which shift_up first lights.
  const shiftPoints = {};
  let shiftCar = null, lastShift = false;
  RD.shiftPoint = function (f) {
    if (f.car !== shiftCar) { shiftCar = f.car; for (const k in shiftPoints) delete shiftPoints[k]; }
    if (f.shift_up && !lastShift && f.rpm_pct > 0.5) shiftPoints[f.gear] = f.rpm_pct;
    lastShift = !!f.shift_up;
    return shiftPoints[f.gear] || Math.max(0, ...Object.values(shiftPoints)) || 0.95;
  };

  /* LED strip: <div class="rd-leds" data-count="15" data-range="0.25"></div>
     The LEDs light up over the last `range` of rpm before the shift point:
     green, then yellow, then red; at the shift point the strip flashes (class "shift"). */
  RD.widgets.leds = function (el) {
    const count = Number(el.dataset.count || 15);
    const range = Number(el.dataset.range || 0.25);
    const leds = [];
    for (let i = 0; i < count; i++) {
      const led = document.createElement("i");
      led.className = i < count * 0.4 ? "g" : i < count * 0.75 ? "y" : "r";
      el.appendChild(led);
      leds.push(led);
    }
    let lastLit = -1, lastState = "";
    widgets.push((f) => {
      const shift = RD.shiftPoint(f);
      const start = shift - range;
      const share = Math.min(1, Math.max(0, (f.rpm_pct - start) / range));
      const lit = RD.errorOf(f) ? 0 : Math.round(share * count);
      const state = f.limiter ? "limiter" : f.shift_up ? "shift" : "";
      if (lit !== lastLit) {
        leds.forEach((led, i) => led.classList.toggle("on", i < lit));
        lastLit = lit;
      }
      if (state !== lastState) {
        el.classList.toggle("shift", state === "shift");
        el.classList.toggle("limiter", state === "limiter");
        lastState = state;
      }
    });
  };

  /* RPM bar: <div class="rd-rpmbar"><i class="fill"></i><i class="mark"></i></div>
     Sets --rpm (0..1 of the redline) and --shift (the shift point) on the element; zone classes
     "high" and "shift" colour the fill. */
  RD.widgets.rpmbar = function (el) {
    let last = "";
    widgets.push((f) => {
      const shift = RD.shiftPoint(f);
      const pct = Math.min(1, Math.max(0, f.rpm_pct || 0));
      const key = pct.toFixed(3) + shift.toFixed(3) + f.shift_up + f.limiter;
      if (key === last) return;
      last = key;
      el.style.setProperty("--rpm", pct.toFixed(4));
      el.style.setProperty("--shift", shift.toFixed(4));
      el.classList.toggle("high", pct >= shift - 0.1);
      el.classList.toggle("shift", !!f.shift_up || !!f.limiter);
    });
  };

  /* Rev lights: <div class="rd-revlights" data-colors="b g y r r y g b" data-fill="outside" data-range="0.12"></div>
     One field per colour (b blue, g green, y yellow, r red). data-fill "outside": the fields light in pairs
     from the outside in; "left": one after another from the left. The scale ends at the game's shift point
     (learned from its shift signal) and is `range` wide (0.12: from 88 % of it); optional data-early moves the
     end below the shift point (not used: a fixed offset did not fit every car); the innermost pair (the red one) only at the game's shift signal
     (or at the learned shift point), so it means "shift now". The fields never flash: at the shift signal and
     on the limiter all are lit (classes "shift" / "limiter" for styles). Unlit fields stay dim (CSS). */
  RD.widgets.revlights = function (el) {
    const colors = (el.dataset.colors || "b g y r r y g b").trim().split(/\s+/);
    const outside = (el.dataset.fill || "outside") === "outside";
    const range = Number(el.dataset.range || 0.12);
    const early = Number(el.dataset.early || 0);
    const n = colors.length;
    const fields = colors.map((color) => {
      const field = document.createElement("i");
      field.className = color;
      el.appendChild(field);
      return field;
    });
    const step = fields.map((_, i) => (outside ? Math.min(i, n - 1 - i) : i));   // the step at which a field lights
    const steps = Math.max(...step) + 1;
    let lastLit = -1, lastState = "";
    widgets.push((f) => {
      const shift = RD.shiftPoint(f);
      const end = shift * (1 - early), start = end - shift * range;
      const share = ((f.rpm_pct || 0) - start) / (end - start || 1);
      const error = RD.errorOf(f);
      let lit = error ? 0 : Math.max(0, Math.min(steps, Math.ceil(share * steps - 1e-6)));
      const state = error ? "" : f.limiter ? "limiter" : f.shift_up ? "shift" : "";
      if (state) lit = steps;
      else if (lit === steps && share < 1) lit = steps - 1;          // the last pair waits for the end of the scale
      if (lit !== lastLit) {
        fields.forEach((field, i) => field.classList.toggle("on", step[i] < lit));
        // the red fields are lit (at the end of the scale or the game's shift signal): the gear page turns its screen red
        document.body.classList.toggle("rd-redzone", fields.some((field, i) => colors[i] === "r" && step[i] < lit));
        lastLit = lit;
      }
      if (state !== lastState) {
        el.classList.toggle("shift", state === "shift");
        el.classList.toggle("limiter", state === "limiter");
        lastState = state;
      }
    });
  };

  /* Widgets set up by RD.start: [selector, init]. Other scripts (js/seg14.js) add their own. */
  RD.widgetInits = [
    [".rd-revlights", RD.widgets.revlights],
    [".rd-leds", RD.widgets.leds],
    [".rd-rpmbar", RD.widgets.rpmbar],
  ];

  /* ------------------------------------------------------------ styles */

  RD.styles = {
    list: [],
    page: "",
    init() {
      const body = document.body;
      this.page = body.dataset.page || "page";
      this.list = (body.dataset.styles || "").split(",").map((s) => s.trim()).filter(Boolean);
      this.apply(store.get("style." + this.page, this.list[0]));
    },
    apply(name) {
      if (!this.list.includes(name)) name = this.list[0];
      if (!name) return;
      const link = document.getElementById("rd-style");
      if (link) link.href = "styles/" + this.page + "/" + name + ".css";
      document.body.dataset.style = name;
      store.set("style." + this.page, name);
    },
    next() {
      const i = this.list.indexOf(document.body.dataset.style);
      this.apply(this.list[(i + 1) % this.list.length]);
    },
  };

  /* ------------------------------------------------------------ commands */

  RD.command = function (action, state) {
    return fetch("/api/command", { method: "POST", body: JSON.stringify({ action, state: state || "tap" }) })
      .then((r) => r.json())
      .then((reply) => { if (reply.error) RD.toast(reply.error); return reply; })
      .catch(() => RD.toast("no connection to the PC"));
  };

  let toastTimer = null;
  RD.toast = function (text) {
    let el = document.getElementById("rd-toast");
    if (!el) { el = document.createElement("div"); el.id = "rd-toast"; document.body.appendChild(el); }
    el.textContent = text.toUpperCase();
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
  };

  RD.loadInfo = function () {
    return fetch("/api/info").then((r) => r.json()).then((info) => { RD.info = info; return info; });
  };

  /* ------------------------------------------------------------ screen wake lock */

  let wakeLock = null;
  RD.keepAwake = async function (on) {
    store.set("awake", on);
    try {
      if (on && "wakeLock" in navigator) {
        wakeLock = await navigator.wakeLock.request("screen");
      } else if (wakeLock) {
        await wakeLock.release();
        wakeLock = null;
      }
    } catch (e) { /* not allowed without a user gesture or on plain http */ }
  };
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && store.get("awake", false)) RD.keepAwake(true);
  });

  /* ------------------------------------------------------------ icons (inline SVG, no emoji) */

  RD.icons = {
    gear: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19.4 13a7.5 7.5 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.4 7.4 0 0 0-1.7-1L15 3h-4l-.4 2.9a7.4 7.4 0 0 0-1.7 1l-2.5-1-2 3.5L6.5 11a7.5 7.5 0 0 0 0 2l-2.1 1.6 2 3.5 2.5-1a7.4 7.4 0 0 0 1.7 1L11 21h4l.4-2.9a7.4 7.4 0 0 0 1.7-1l2.5 1 2-3.5zM13 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z" transform="translate(-1 0)"/></svg>',
    style: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3a9 9 0 1 0 0 18V3z"/><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
  };

  /* ------------------------------------------------------------ toolbar and settings */

  RD.HOME = "/Racing_Dashboard";    // the home page; the link to save on the tablet

  RD.toolbar = function () {
    const bar = document.createElement("div");
    bar.className = "rd-toolbar";
    if (RD.styles.list.length > 1) {
      const style = document.createElement("button");
      style.className = "rd-tool";
      style.innerHTML = RD.icons.style;
      style.setAttribute("aria-label", "Next style");
      style.addEventListener("click", () => { RD.styles.next(); RD.toast("style: " + document.body.dataset.style); });
      bar.appendChild(style);
    }
    const gear = document.createElement("button");
    gear.className = "rd-tool";
    gear.innerHTML = RD.icons.gear;
    gear.setAttribute("aria-label", "Settings");
    gear.addEventListener("click", () => RD.settings.open());
    bar.appendChild(gear);
    document.body.appendChild(bar);
  };

  function choice(title, options, current, onPick, note) {
    const row = document.createElement("section");
    row.className = "rd-set-row";
    row.innerHTML = "<h3></h3><div class='rd-choices'></div>" + (note ? "<p class='rd-note'></p>" : "");
    row.querySelector("h3").textContent = title;
    if (note) row.querySelector(".rd-note").textContent = note;
    const box = row.querySelector(".rd-choices");
    options.forEach(([value, label]) => {
      const b = document.createElement("button");
      b.className = "rd-choice" + (value === current ? " active" : "");
      b.textContent = label;
      b.addEventListener("click", () => {
        box.querySelectorAll(".rd-choice").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        onPick(value);
      });
      box.appendChild(b);
    });
    return row;
  }

  /* AI trainer rows (docs/TRAINER.md): provider, API key (kept on the PC, only a hint comes back),
     FAST / BEST, connection status with TEST */
  function aiRows(box, t) {
    const send = (url, body) => fetch(url, { method: "POST", body: JSON.stringify(body || {}) })
      .then((r) => r.json()).then((next) => { if (next.providers) aiRows(box, next); }).catch(() => {});
    box.innerHTML = "";
    const row = choice("AI TRAINER (ALL DEVICES, KEPT ON THE PC)", t.providers, t.provider, (p) => send("/api/trainer/settings", { provider: p }));
    if (t.provider !== "off") {
      const grid = document.createElement("div");
      grid.className = "rd-ai-grid";
      if (t.provider !== "ollama") {
        const k = document.createElement("span"); k.className = "k"; k.textContent = "API KEY";
        const keyBox = document.createElement("div"); keyBox.className = "rd-ai-key";
        const input = document.createElement("input");
        input.type = "password"; input.autocomplete = "off"; input.spellcheck = false;
        input.placeholder = t.keys[t.provider] ? "saved: " + t.keys[t.provider] + " (paste a new one to replace)" : "paste the API key";
        const save = document.createElement("button"); save.className = "rd-choice"; save.textContent = "SAVE";
        save.addEventListener("click", () => { if (input.value.trim()) send("/api/trainer/settings", { key: input.value.trim(), key_for: t.provider }); });
        keyBox.append(input, save);
        grid.append(k, keyBox);
      }
      const mk = document.createElement("span"); mk.className = "k"; mk.textContent = "MODEL";
      const levels = choice("", [["fast", "FAST"], ["best", "BEST"]], t.level, (lv) => send("/api/trainer/settings", { level: lv })).querySelector(".rd-choices");
      const name = document.createElement("span"); name.className = "rd-ai-model";
      name.textContent = t.model || (t.models[t.provider] || {})[t.level] || "";
      levels.appendChild(name);
      const ck = document.createElement("span"); ck.className = "k"; ck.textContent = "CONNECTION";
      const status = document.createElement("div");
      status.className = "rd-ai-status " + (t.ok ? "ok" : t.state === "unchecked" ? "" : "error");
      status.innerHTML = "<i></i><b></b><span></span>";
      status.querySelector("b").textContent = t.ok ? "CONNECTED" : t.state === "unchecked" ? "CHECKING…" : (t.error || "NOT CONNECTED");
      status.querySelector("span").textContent = (t.checked ? "checked " + t.checked + (t.ms !== null ? " · " + (t.ms / 1000).toFixed(1) + " s" : "") : "")
        + (!t.ok && t.detail ? " · " + t.detail : "");
      const test = document.createElement("button"); test.className = "rd-choice"; test.textContent = "TEST";
      test.addEventListener("click", () => { status.querySelector("b").textContent = "CHECKING…"; send("/api/trainer/test"); });
      status.appendChild(test);
      grid.append(mk, levels, ck, status);
      row.appendChild(grid);
    }
    const note = document.createElement("p");
    note.className = "rd-note";
    note.textContent = "The AI TRAINER button on the analysis page asks this AI. FAST answers in seconds for a fraction of a cent; "
      + "BEST thinks longer (a few cents per question with a cloud AI). The key is sent once to the PC and stored there (config\\trainer.json, "
      + "not in git); it is never shown again. Ollama runs on the PC and needs no key.";
    row.appendChild(note);
    box.appendChild(row);
  }

  RD.settings = {
    open() {
      RD.loadInfo().then((info) => this.draw(info)).catch(() => this.draw(null));
    },
    close() {
      const el = document.getElementById("rd-settings");
      if (el) el.remove();
    },
    draw(info) {
      this.close();
      const el = document.createElement("div");
      el.id = "rd-settings";
      el.innerHTML = "<header><h2>SETTINGS</h2><button class='rd-back'>BACK</button></header><div class='rd-set-body'></div>";
      el.querySelector(".rd-back").addEventListener("click", () => this.close());
      const body = el.querySelector(".rd-set-body");
      const pages = [["index", "HOME"], ["gear", "GEAR + REV"], ["dash", "DASH"], ["analysis", "ANALYSIS"], ["buttons", "BUTTONS"], ["boost", "BOOST"]];
      body.appendChild(choice("PAGE", pages, document.body.dataset.page, (p) => { location.href = p === "index" ? RD.HOME : "/" + p; }));
      if (info) {
        body.appendChild(choice("GAME (ALL DEVICES)", info.games.map((g) => [g.id, g.name.toUpperCase()]), info.game, (id) => {
          fetch("/api/settings", { method: "POST", body: JSON.stringify({ game: id }) })
            .then(() => location.reload());
        }));
        body.appendChild(choice("UPDATE RATE (THIS DEVICE)", info.hz_choices.map((hz) => [hz, hz + " HZ"]), RD.rate(), (hz) => {
          store.set("hz", hz); RD.connect();
        }));
      }
      body.appendChild(choice("SPEED (THIS DEVICE)", [["kmh", "KM/H"], ["mph", "MPH"]], RD.units(), (u) => {
        store.set("units", u); bound.forEach((b) => (b.last = undefined));
      }));
      if (RD.styles.list.length > 1) {
        body.appendChild(choice("STYLE OF THIS PAGE", RD.styles.list.map((s) => [s, s.toUpperCase()]), document.body.dataset.style, (s) => RD.styles.apply(s)));
      }
      const awakeNote = "wakeLock" in navigator ? "" : "Not available on this connection: set Auto-Lock to Never in the iPhone / iPad settings.";
      body.appendChild(choice("KEEP SCREEN ON (THIS DEVICE)", [[false, "OFF"], [true, "ON"]], store.get("awake", false), (on) => RD.keepAwake(on), awakeNote));
      const ai = document.createElement("div");
      body.appendChild(ai);
      fetch("/api/trainer", { cache: "no-store" }).then((r) => r.json()).then((t) => { if (t.providers) aiRows(ai, t); }).catch(() => {});
      const infoRow = document.createElement("section");
      infoRow.className = "rd-set-row rd-info";
      infoRow.innerHTML = "<h3>INFO</h3><dl></dl>";
      const dl = infoRow.querySelector("dl");
      const f = RD.frame;
      const lines = [
        ["GAME", info ? info.game_name : "-"],
        ["DATA", RD.errorOf(f) ? "E \u00b7 " + RD.errorOf(f) : "LIVE"],
        ["CAR", f.car || "-"],
        ["TRACK", f.track || "-"],
        ["FRAMES / S", String(RD.fps)],
        ["OPEN ON ANOTHER DEVICE", info ? info.address : "-"],
      ];
      if (info && !info.keys_available) lines.push(["BUTTONS", "keypresses need the bridge on Windows"]);
      for (const [k, v] of lines) {
        const dt = document.createElement("dt"); dt.textContent = k;
        const dd = document.createElement("dd"); dd.textContent = v;
        dl.append(dt, dd);
      }
      body.appendChild(infoRow);
      document.body.appendChild(el);
    },
  };

  /* ------------------------------------------------------------ start */

  RD.start = function (options) {
    options = options || {};
    RD.styles.init();
    for (const [selector, init] of RD.widgetInits) document.querySelectorAll(selector).forEach((el) => init(el));
    RD.bind();
    if (options.toolbar !== false) RD.toolbar();
    document.body.classList.add("rd-stale", "rd-error");
    render();
    RD.connect();
    if (store.get("awake", false)) {
      // A wake lock needs a user gesture on most browsers: ask on the first touch.
      document.addEventListener("pointerdown", () => RD.keepAwake(true), { once: true });
    }
    document.addEventListener("dblclick", (e) => e.preventDefault(), { passive: false });
    document.addEventListener("gesturestart", (e) => e.preventDefault());
  };

  window.RD = RD;
})();
