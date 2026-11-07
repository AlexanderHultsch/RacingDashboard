/* Racing Dashboard client library: one file every page loads.
 *
 * - RD.connect()       live telemetry from the bridge (Server-Sent Events at the chosen rate)
 * - data-rd="field"    any element with this attribute shows that telemetry field,
 *   data-fmt="name"    formatted with RD.formats[name] (gear, speed, rpm, lap, delta, ...)
 * - data-rd-on="field" toggles the class "on" while the field is truthy
 * - RD.widgets         LED shift strip (.rd-leds) and RPM bar (.rd-rpmbar)
 * - RD.styles          the visual styles of a page, cycled with the style button
 * - RD.settings        the settings overlay (game, update rate, units, screen, info)
 * - RD.command()       sends a button to the game
 *
 * A page needs: <body data-page="gear" data-styles="classic,bar"> and
 * <link id="rd-style" rel="stylesheet">. Everything else is optional.
 * Body classes set while driving: rd-stale (no data), rd-shift, rd-limiter, rd-pit, rd-tc, rd-abs.
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
    gear: (v) => (v === undefined || v === null ? "-" : v < 0 ? "R" : v === 0 ? "N" : String(v)),
    int: (v) => (v === null || v === undefined ? "-" : String(Math.round(v))),
    rpm: (v) => (v ? String(Math.round(v)) : "0"),
    speed: (v) => String(Math.round((v || 0) * (RD.units() === "mph" ? 0.621371 : 1))),
    speedunit: () => (RD.units() === "mph" ? "MPH" : "KM/H"),
    level: (v) => (v === null || v === undefined ? "-" : String(v)),
    bias: (v) => (v === null || v === undefined ? "-" : (v * 100).toFixed(1)),
    fuel: (v) => (v === null || v === undefined ? "-" : v.toFixed(1)),
    onoff: (v) => (v ? "ON" : "OFF"),
    pct: (v) => (v === null || v === undefined ? "-" : Math.round(v * 100) + "%"),
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

  RD.connect = function () {
    if (source) source.close();
    source = new EventSource("/stream?hz=" + RD.rate());
    source.onmessage = (event) => {
      lastMessage = performance.now();
      frames += 1;
      RD.frame = JSON.parse(event.data);
      if (!pending) { pending = true; requestAnimationFrame(render); }
    };
  };

  setInterval(() => { RD.fps = frames; frames = 0; }, 1000);
  setInterval(() => {   // no message for 2.5 s: show "no data" (the stream sends a heartbeat every second)
    if (performance.now() - lastMessage > 2500) document.body.classList.add("rd-stale");
  }, 500);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) RD.connect(); });

  /* ------------------------------------------------------------ rendering */

  const bound = [];

  RD.bind = function (root) {
    (root || document).querySelectorAll("[data-rd], [data-rd-on]").forEach((el) => {
      bound.push({ el, field: el.dataset.rd, on: el.dataset.rdOn, fmt: RD.formats[el.dataset.fmt || "text"] || RD.formats.text, last: undefined, lastOn: undefined });
    });
  };

  function render() {
    pending = false;
    const f = RD.frame;
    const body = document.body.classList;
    body.toggle("rd-stale", !f.connected);
    body.toggle("rd-shift", !!f.shift_up);
    body.toggle("rd-limiter", !!f.limiter);
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
      const lit = f.connected ? Math.round(share * count) : 0;
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
    home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3 2 12h3v8h5v-5h4v5h5v-8h3z"/></svg>',
  };

  /* ------------------------------------------------------------ toolbar and settings */

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
      const pages = [["index", "HOME"], ["gear", "GEAR + REV"], ["dash", "DASH"]];
      body.appendChild(choice("PAGE", pages, document.body.dataset.page, (p) => { location.href = p === "index" ? "/" : "/" + p; }));
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
      const infoRow = document.createElement("section");
      infoRow.className = "rd-set-row rd-info";
      infoRow.innerHTML = "<h3>INFO</h3><dl></dl>";
      const dl = infoRow.querySelector("dl");
      const f = RD.frame;
      const lines = [
        ["GAME", info ? info.game_name : "-"],
        ["DATA", !f.connected ? "WAITING FOR THE GAME" : f.status && f.status !== "live" ? "LIVE (" + f.status.toUpperCase() + ")" : "LIVE"],
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
    document.querySelectorAll(".rd-leds").forEach(RD.widgets.leds);
    document.querySelectorAll(".rd-rpmbar").forEach(RD.widgets.rpmbar);
    RD.bind();
    if (options.toolbar !== false) RD.toolbar();
    document.body.classList.add("rd-stale");
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
