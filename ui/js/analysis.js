/* Analysis page (ui/analysis.html, docs/ANALYSIS.md).
 *
 * Data from the bridge (core/recorder.py):
 *   GET  /api/analysis              track outline, section borders, full-lap lines, offers, end of run
 *   GET  /api/analysis/live?since=  4 x per second: deltas, section strip, current section, red line
 *   GET  /api/analysis/section?n=   one section: best / last / now samples [d, t, v, thr, brk, str, g, x, y,
 *                                   tc_on, abs_on, esc_on, tc_level, tc_cut, abs_level, esc_level, engine_map]
 *   POST /api/analysis/offer {id, save}, /save-all, /skip-all, /undo, /end, /finish {keep: "all" | "baselines"}
 *   GET  /api/trainer, POST /api/trainer/ask {mode: "track" | "section", section}   AI trainer (docs/TRAINER.md)
 * The car dot on the map comes from the normal telemetry stream (pos_x, pos_y).
 */
(function () {
  "use strict";

  const COL = {
    best: "#22d36b", last: "#3f8cff", now: "#ff4545", sel: "#ffe93b", cur: "#ffe93b",
    grid: "#20272f", label: "#5f6974", title: "#7d8794", track: "#1b2128", edge: "#39424d", border: "#55606c",
  };
  const POLL_MS = 250;
  const LINE_ALPHA = 0.8;        // best / last / now lines: slightly see-through, so crossing lines stay readable
  const AHEAD_ALPHA = 0.28;      // the part after the cursor line: faded
  const $ = (id) => document.getElementById(id);

  const S = {
    state: null,          // /api/analysis
    live: null,           // /api/analysis/live
    version: -1,
    liveMode: true,       // LIVE: follow the current section
    sel: 0,               // selected section (0-based)
    zoom: false,          // map zoomed into the selected section
    cursor: null,         // metres into the selected section where the finger is on the map (null = none)
    sec: null,            // /api/analysis/section of the selected section
    nowLine: [],          // red full-lap line, filled incrementally
    nowLap: null,
    polls: 0,
    endArmed: 0,
    endDismissed: null,
    offline: false,
    tab: "review",        // right side: REVIEW (start), GRAPHS or TRAINER
    trainer: null,        // /api/trainer: connection, settings, last answers
    trEntry: null,        // the answer shown in TRAINER
    trAsking: null,       // what is being asked right now: {mode, section, title}
    trError: null,        // why the last question failed
  };

  /* ------------------------------------------------------------ helpers */

  function get(url) {
    return fetch(url, { cache: "no-store" }).then((r) => r.json());
  }
  function post(url, body) {
    return fetch(url, { method: "POST", body: JSON.stringify(body || {}) }).then((r) => r.json());
  }
  const sign = (x) => (x >= 0 ? "+" : "−");
  const fmtDelta = (x) => (x === null || x === undefined ? "-" : sign(x) + Math.abs(x).toFixed(3));
  const fmtCell = (x) => (x === null || x === undefined ? "" : Math.abs(x) < 0.005 ? "0.00" : sign(x) + Math.abs(x).toFixed(2).replace(/^0/, ""));
  const fmtLap = (s) => {
    if (s === null || s === undefined) return "-";
    const m = Math.floor(s / 60);
    return m + ":" + (s - m * 60).toFixed(3).padStart(6, "0");
  };
  const fmtSec = (s) => (s === null || s === undefined ? "-" : s < 60 ? s.toFixed(3) : fmtLap(s));
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function interp(xs, ys, x) {
    const n = xs.length;
    if (!n || x < xs[0] || x > xs[n - 1]) return null;
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (xs[mid] <= x) lo = mid; else hi = mid;
    }
    if (xs[hi] === xs[lo]) return ys[lo];
    return ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / (xs[hi] - xs[lo]);
  }

  function prep(canvas) {
    const r = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    return { ctx, w: r.width, h: r.height, dpr };
  }

  function sections() { return (S.state && S.state.sections) || 0; }
  function recording() { return !!(S.live && S.live.recording); }

  /* ------------------------------------------------------------ polling */

  async function poll() {
    try {
      const live = await get("/api/analysis/live?since=" + S.nowLine.length);
      S.offline = false;
      if (live.red_lap !== S.nowLap) {
        S.nowLap = live.red_lap;
        S.nowLine = live.now_from === 0 ? live.now_line : [];
      } else if (live.now_from <= S.nowLine.length) {
        S.nowLine.length = live.now_from;
        for (const p of live.now_line) S.nowLine.push(p);
      }
      S.live = live;
      if (live.version !== S.version) await loadState();
      let sectionDue = S.polls % 2 === 0 && (recording() && live.sec === S.sel);
      if (S.liveMode && live.sec !== null && live.sec !== undefined && live.sec !== S.sel) {
        S.sel = live.sec;
        sectionDue = true;
      }
      if (sectionDue || !S.sec || S.sec.n !== S.sel) await loadSection();
      S.polls += 1;
      mapDirty = true;
      renderAll();
    } catch (e) {
      if (!S.offline) { S.offline = true; renderHeader(); }
    }
    setTimeout(poll, S.offline ? 1000 : POLL_MS);
  }

  async function loadState() {
    const state = await get("/api/analysis");
    if (state.error) return;
    const changedTrack = !S.state || state.sections !== S.state.sections || state.track !== S.state.track;
    S.state = state;
    S.version = state.version;
    if (changedTrack) {
      buildStrip();
      if (S.sel >= sections()) S.sel = 0;
      S.sec = null;
    }
    if (!state.ended) S.endDismissed = null;
    renderOffers();
    renderModal();
    if (S.sec) await loadSection();
  }

  async function loadSection() {
    if (!sections()) { S.sec = null; return; }
    S.sec = await get("/api/analysis/section?n=" + S.sel);
  }

  function select(n, zoom) {
    setTab("graphs");
    S.liveMode = false;
    S.sel = Math.max(0, Math.min(sections() - 1, n));
    S.zoom = zoom;
    S.cursor = null;
    mapDirty = true;
    loadSection().then(renderAll);
    renderAll();
  }

  /* ------------------------------------------------------------ header and deltas */

  function renderHeader() {
    const st = S.state;
    const what = $("what");
    let text;
    if (S.offline) {
      text = "<b>NO CONNECTION TO THE PC</b>";
    } else if (!st || !st.active) {
      text = "NO RUN YET · DRIVE TO RECORD";
    } else {
      const game = RD.info && RD.info.game === st.game ? RD.info.game_name : st.game;
      const lap = S.live && S.live.lap ? " · LAP " + S.live.lap : "";
      text = esc([game, st.car, st.track].join(" · ").toUpperCase()) + lap;
      const last = S.live && S.live.last_lap;
      if (last && last.time) {
        const note = last.out_lap ? "OUT LAP" : last.repeated ? "REPEATED" : last.broken ? "INTERRUPTED" : !last.valid ? "INVALID" : "";
        text += " · LAST " + fmtLap(last.time) + (note ? " " + note : "");
      }
    }
    if (!S.offline && !recording()) {
      const why = (S.live && S.live.why) || RD.errorOf(RD.frame);
      text += " · <b>NOT RECORDING" + (why ? ": " + esc(why) : "") + "</b>";
    }
    if (what.innerHTML !== text) what.innerHTML = text;
    const live = $("live");
    live.classList.toggle("on", S.liveMode);
    live.classList.toggle("idle", !recording());
    const n = S.live ? S.live.offers : 0;
    const badge = $("tab-n");
    badge.textContent = n;
    badge.classList.toggle("zero", !n);
    const end = $("end");
    end.textContent = S.endArmed > performance.now() ? "TAP AGAIN TO END" : "END RUN";
  }

  function setDelta(id, x) {
    const el = $(id);
    el.textContent = fmtDelta(x);
    el.className = x === null || x === undefined ? "none" : x > 0.0005 ? "slower" : "faster";
  }

  function renderDeltas() {
    const d = (S.live && S.live.deltas) || {};
    setDelta("d-lap-best", d.lap_best);
    setDelta("d-lap-last", d.lap_last);
    const strip = S.live && S.live.strip;
    let n = S.sel, best = null, last = null;
    if (S.liveMode && recording() && d.sec !== null && d.sec !== undefined) {
      n = d.sec; best = d.sec_best; last = d.sec_last;
    } else if (strip) {
      best = strip.best[n]; last = strip.last[n];
    }
    $("d-sec-best-t").textContent = "SECTION " + (sections() ? n + 1 : "-") + " · VS BEST";
    $("d-sec-last-t").textContent = "SECTION " + (sections() ? n + 1 : "-") + " · VS LAST";
    setDelta("d-sec-best", best);
    setDelta("d-sec-last", last);
  }

  /* ------------------------------------------------------------ section strip */

  function buildStrip() {
    const cells = $("cells");
    cells.innerHTML = "";
    const add = (cls, text, n) => {
      const el = document.createElement("span");
      el.className = cls;
      el.textContent = text;
      if (n !== undefined) el.dataset.n = n;
      cells.appendChild(el);
      return el;
    };
    add("h", ""); add("h", "BEST"); add("h", "LAST");
    for (let n = 0; n < sections(); n++) {
      add("n", n + 1, n);
      add("c best", "", n);
      add("c last", "", n);
    }
    syncSlider();
  }

  function cellClass(v) {
    if (v === null || v === undefined) return "none";
    return v > 0.08 ? "pp" : v > 0.005 ? "p" : v < -0.06 ? "mm" : v < -0.005 ? "m" : "";
  }

  let lastFollow = -1;
  function renderStrip() {
    const strip = S.live && S.live.strip;
    const cells = $("cells");
    if (!strip) return;
    const d = S.live.deltas || {};
    const runningSec = recording() ? d.sec : null;
    cells.querySelectorAll("[data-n]").forEach((el) => {
      const n = +el.dataset.n;
      const sel = n === S.sel;
      if (el.classList.contains("n")) {
        el.className = "n" + (sel ? " sel" : "") + ((strip.attempts[n] || 0) > 1 ? " rep" : "");
        return;
      }
      const isBest = el.classList.contains("best");
      let v = isBest ? strip.best[n] : strip.last[n];
      if (n === runningSec) v = isBest ? d.sec_best : d.sec_last;
      const old = n !== runningSec && strip.old && strip.old[n];
      const cls = "c " + (isBest ? "best " : "last ") + cellClass(v) + (old ? " old" : "") + (sel ? " sel" : "");
      if (el.className !== cls) el.className = cls;
      const text = fmtCell(v);
      if (el.textContent !== text) el.textContent = text;
    });
    if (S.liveMode && S.sel !== lastFollow) {          // keep the current section in view
      const cell = cells.querySelector('.n[data-n="' + S.sel + '"]');
      if (cell) cells.scrollLeft = Math.max(0, cell.offsetLeft - cells.clientWidth / 2);
      lastFollow = S.sel;
    }
    syncSlider();
  }

  function syncSlider() {
    const cells = $("cells"), slider = $("slider");
    const max = Math.max(0, cells.scrollWidth - cells.clientWidth);
    slider.hidden = max < 4;
    slider.max = String(max);
    slider.value = String(cells.scrollLeft);
  }

  /* ------------------------------------------------------------ map */

  let mapDirty = true, mapView = null;
  const mapCache = document.createElement("canvas");

  function secRange(n) {
    const st = S.state;
    const a = (n * st.section_m) / st.track_length_m;
    const b = n === st.sections - 1 ? 1 : ((n + 1) * st.section_m) / st.track_length_m;
    return [a, b];
  }

  function mapPoints() {
    const st = S.state;
    if (!st) return [];
    if (st.outline.length) return st.outline;
    return S.nowLine.map((p) => [p[0], p[1], null]);
  }

  function view(w, h, pts) {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) {
      if (p[0] === null || p[0] === undefined) continue;
      if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0];
      if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1];
    }
    if (!isFinite(x0)) return null;
    const padTop = 34, pad = 22;
    let dx = Math.max(x1 - x0, 20), dy = Math.max(y1 - y0, 20);
    const aspect = (w - 2 * pad) / (h - pad - padTop);
    if (dx / dy > aspect * 2.2) dy = dx / (aspect * 2.2);       // a straight: do not zoom in sideways too far
    if (dy / dx > 2.2 / aspect) dx = dy * aspect / 2.2;
    const s = Math.min((w - 2 * pad) / dx, (h - pad - padTop) / dy);
    const ox = (w - dx * s) / 2 - (x0 - (dx - (x1 - x0)) / 2) * s;
    const oy = padTop + (h - pad - padTop - dy * s) / 2 - (y0 - (dy - (y1 - y0)) / 2) * s;
    return { s, ox, oy, w, h, X: (x) => ox + x * s, Y: (y) => oy + y * s };
  }

  function path(ctx, v, pts, close) {
    ctx.beginPath();
    let started = false;
    for (const p of pts) {
      if (p[0] === null || p[0] === undefined) continue;
      if (!started) { ctx.moveTo(v.X(p[0]), v.Y(p[1])); started = true; } else ctx.lineTo(v.X(p[0]), v.Y(p[1]));
    }
    if (close) ctx.closePath();
    return started;
  }

  function stroke(ctx, color, width, alpha) {
    ctx.globalAlpha = alpha === undefined ? 1 : alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function drawMapStatic() {
    const wrap = $("map");
    const r = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    mapCache.width = Math.max(1, Math.round(r.width * dpr));
    mapCache.height = Math.max(1, Math.round(r.height * dpr));
    const ctx = mapCache.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    mapView = null;
    const st = S.state;
    const outline = mapPoints();
    if (!st || !st.active || outline.length < 2) {
      ctx.fillStyle = COL.title;
      ctx.font = "700 14px " + getComputedStyle(document.body).fontFamily;
      ctx.textAlign = "center";
      ctx.fillText(st && st.active ? "THE TRACK APPEARS AFTER THE FIRST METRES" : "NO LAP RECORDED YET", r.width / 2, r.height / 2);
      return;
    }
    const zoom = S.zoom && S.sec && outline[0][2] !== null;
    let pts = outline;
    if (zoom) {
      const [a, b] = secRange(S.sel);
      pts = outline.filter((p) => p[2] >= a - 0.002 && p[2] <= b + 0.002);
      for (const key of ["best", "last", "now"]) for (const row of S.sec[key]) pts.push([row[7], row[8]]);
    }
    const v = view(r.width, r.height, pts);
    if (!v) return;
    mapView = v;
    const first = outline[0], lastPt = outline[outline.length - 1];
    const closed = Math.hypot(first[0] - lastPt[0], first[1] - lastPt[1]) < 60;
    const trackW = Math.max(zoom ? 14 : 7, Math.min(zoom ? 120 : 30, 13 * v.s));
    // the track surface
    if (path(ctx, v, outline, closed)) { stroke(ctx, COL.edge, trackW + 2); }
    path(ctx, v, outline, closed);
    stroke(ctx, COL.track, trackW);
    // the selected section (overview)
    const hasP = outline[0][2] !== null;
    if (!zoom && hasP && sections()) {
      const [a, b] = secRange(S.sel);
      if (path(ctx, v, outline.filter((p) => p[2] >= a && p[2] <= b))) stroke(ctx, COL.sel, trackW + 8, 0.22);
    }
    // section borders and numbers
    const font = getComputedStyle(document.body).fontFamily;
    const every = sections() > 40 ? 5 : sections() > 24 ? 2 : 1;
    (st.borders || []).forEach((b, n) => {
      if (!b) return;
      const cx = v.X(b[0]), cy = v.Y(b[1]), half = trackW / 2 + 4;
      ctx.beginPath();
      ctx.moveTo(cx + b[2] * half, cy + b[3] * half);
      ctx.lineTo(cx - b[2] * half, cy - b[3] * half);
      stroke(ctx, n === 0 ? "#f2f4f7" : COL.border, n === 0 ? 3 : 1.5);
      if (!zoom && hasP && n % every === 0) {
        const [a, bb] = secRange(n);
        const mid = (a + bb) / 2;
        const ps = outline.map((p) => p[2]);
        const mx = interp(ps, outline.map((p) => p[0]), mid), my = interp(ps, outline.map((p) => p[1]), mid);
        if (mx !== null) {
          ctx.fillStyle = n === S.sel ? COL.sel : "#6b7580";
          ctx.font = "800 10.5px " + font;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(n + 1), v.X(mx) + b[2] * (trackW / 2 + 11), v.Y(my) + b[3] * (trackW / 2 + 11));
        }
      }
    });
    // race lines
    if (zoom) {
      const cur = S.cursor;
      const xy = (rows) => rows.map((r) => [r[7], r[8]]);
      const line = (rows, color, width) => {
        const before = cur === null ? rows : rows.filter((r) => r[0] <= cur);
        const after = cur === null ? [] : rows.filter((r) => r[0] >= cur);
        if (path(ctx, v, xy(before))) stroke(ctx, color, width, LINE_ALPHA);
        if (path(ctx, v, xy(after))) stroke(ctx, color, width, AHEAD_ALPHA);
      };
      line(S.sec.best, COL.best, 3);
      line(S.sec.last, COL.last, 3);
      line(S.sec.now, COL.now, 3.2);
    } else {
      if (path(ctx, v, st.lines.best)) stroke(ctx, COL.best, 1.6, 0.85);
      if (path(ctx, v, st.lines.last)) stroke(ctx, COL.last, 1.6, 0.7);
      if (path(ctx, v, S.nowLine)) stroke(ctx, COL.now, 2.2);
    }
  }

  function drawMap() {
    if (mapDirty) { drawMapStatic(); mapDirty = false; }
    const { ctx, w, h } = prep($("map"));
    ctx.drawImage(mapCache, 0, 0, w, h);
    const f = RD.frame;
    if (mapView && recording() && typeof f.pos_x === "number" && typeof f.pos_y === "number") {
      ctx.beginPath();
      ctx.arc(mapView.X(f.pos_x), mapView.Y(f.pos_y), 7, 0, Math.PI * 2);
      ctx.fillStyle = COL.now;
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#fff";
      ctx.stroke();
    }
    const at = cursorPoint();
    if (mapView && at) {                               // where the cursor line in the graphs is
      const x = mapView.X(at[0]), y = mapView.Y(at[1]);
      ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2);
      ctx.lineWidth = 3; ctx.strokeStyle = COL.cur; ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = COL.cur; ctx.fill();
    }
    const tag = $("map-tag");
    const n = sections() ? S.sel + 1 : "-";
    const html = S.zoom ? "<b>SECTION " + n + "</b>" + (S.cursor !== null ? " · " + Math.round(S.cursor) + " M" : "")
      : "OVERVIEW · <b>SECTION " + n + "</b>" + (S.liveMode ? " LIVE" : "");
    if (tag.innerHTML !== html) tag.innerHTML = html;
    tag.classList.toggle("shift", S.zoom);
    $("back").hidden = !S.zoom;
  }

  function cursorPoint() {
    const st = S.state;
    if (S.cursor === null || !st || !st.outline.length || st.outline[0][2] === null) return null;
    const p = (S.sel * st.section_m + S.cursor) / st.track_length_m;
    const ps = st.outline.map((q) => q[2]);
    const x = interp(ps, st.outline.map((q) => q[0]), p), y = interp(ps, st.outline.map((q) => q[1]), p);
    return x === null ? null : [x, y];
  }

  // Map: tap a section in the overview to open it; drag along the track (overview or section) to move the
  // cursor line in the graphs. BACK returns to the overview.
  function nearest(e) {
    const st = S.state;
    const outline = st && st.outline;
    if (!mapView || !outline || !outline.length || outline[0][2] === null) return null;
    const r = $("map").getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    let pts = outline;
    if (S.zoom) {                                      // in a section the cursor stays in that section
      const [a, b] = secRange(S.sel);
      pts = outline.filter((p) => p[2] >= a && p[2] <= b);
    }
    let best = null, dist = S.zoom ? Infinity : 48;
    for (const p of pts) {
      const d = Math.hypot(mapView.X(p[0]) - x, mapView.Y(p[1]) - y);
      if (d < dist) { dist = d; best = p; }
    }
    return best;
  }

  function sectionOf(p) {
    return Math.min(sections() - 1, Math.floor((p * S.state.track_length_m) / S.state.section_m));
  }

  function scrub(p) {
    const st = S.state;
    const n = sectionOf(p[2]);
    setTab("graphs");
    S.liveMode = false;
    const load = n !== S.sel || !S.sec || S.sec.n !== n;
    S.sel = n;
    const [a, b] = secRange(n);
    S.cursor = Math.max(0, Math.min((b - a) * st.track_length_m, p[2] * st.track_length_m - n * st.section_m));
    mapDirty = true;
    if (load) loadSection().then(renderAll);
    renderAll();
  }

  let drag = null;
  function mapDown(e) {
    if (!S.state || !S.state.active) return;
    drag = { x: e.clientX, y: e.clientY, moved: false };
    try { $("map").setPointerCapture(e.pointerId); } catch (err) { /* pointer already gone */ }
    if (S.zoom) { const p = nearest(e); if (p) scrub(p); }
  }
  function mapMove(e) {
    if (!drag) return;
    if (!drag.moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 8) return;
    drag.moved = true;
    const p = nearest(e);
    if (p) scrub(p);
  }
  function mapUp(e) {
    if (!drag) return;
    const tap = !drag.moved;
    drag = null;
    if (tap && !S.zoom) {
      const p = nearest(e);
      if (p) select(sectionOf(p[2]), true);
    }
  }

  /* ------------------------------------------------------------ graphs */

  // Graphs: pages of 4 panels, scrolled vertically (snap per page). Page 1 speed, throttle, brake, delta;
  // page 2 steering, gear, TC, ABS; page 3 stability, engine map. Rows: [d, t, v, thr, brk, str, g, x, y,
  // tc_on, abs_on, esc_on, tc_level, tc_cut, abs_level, esc_level, engine_map] (assists null when not recorded).
  const PER_PAGE = 4;
  const A = { TC: 9, ABS: 10, ESC: 11, TCL: 12, CUT: 13, ABSL: 14, ESCL: 15, MAP: 16 };

  function renderGraphs() {
    const wrap = $("gwrap"), canvas = $("graphs");
    const sec = S.sec;
    const st = S.state;
    const n = sections() ? S.sel + 1 : "-";
    $("g-title").textContent = "SECTION " + n;
    if (!sec || !st || !st.active) {
      $("g-sub").textContent = "-";
      prep(canvas);
      return;
    }
    const len = Math.max(1, sec.to_m - sec.from_m);
    const parts = [Math.round(len) + " M"];
    if (S.liveMode && recording()) parts.push("LIVE");
    if (sec.red_lap) parts.push("NOW LAP " + sec.red_lap + (sec.now_attempt > 1 ? " · ATTEMPT " + sec.now_attempt : "") + (sec.now_time ? " " + fmtSec(sec.now_time) : ""));
    if (sec.best_time) parts.push("BEST " + fmtSec(sec.best_time));
    if (sec.blue_lap && sec.last_time) parts.push("LAST " + fmtSec(sec.last_time));
    $("g-sub").textContent = parts.join(" · ");

    const mph = RD.units() === "mph";
    const ref = sec.best.length > 1 ? sec.best : sec.last;
    const refName = sec.best.length > 1 ? "BEST" : "LAST";
    const refD = ref.map((r) => r[0]), refT = ref.map((r) => r[1]);
    const deltaRows = (rows) => rows.map((r) => {
      const t = interp(refD, refT, r[0]);
      return t === null ? null : [r[0], r[1] - t];
    }).filter(Boolean);
    const lines = { best: sec.best, last: sec.last, now: sec.now };
    const all = [...sec.best, ...sec.last, ...sec.now];
    const range = (i, pad, minSpan) => {
      let lo = Infinity, hi = -Infinity;
      for (const r of all) { if (r[i] < lo) lo = r[i]; if (r[i] > hi) hi = r[i]; }
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      if (hi - lo < minSpan) { const m = (hi + lo) / 2; lo = m - minSpan / 2; hi = m + minSpan / 2; }
      return [lo - pad, hi + pad];
    };
    const vScale = mph ? 0.621371 : 1;
    let [vLo, vHi] = range(2, 8, 30);
    vLo *= vScale; vHi *= vScale;
    const sMax = Math.max(0.15, ...all.map((r) => Math.abs(r[5]))) * 1.1;
    const gHi = Math.max(2, ...all.map((r) => r[6])) + 0.5;
    const deltas = { last: refName === "BEST" ? deltaRows(sec.last) : sec.last.map((r) => [r[0], 0]), now: deltaRows(sec.now) };
    const dVals = [...deltas.last, ...deltas.now].map((r) => r[1]);
    const dMax = Math.max(0.1, ...dVals.map(Math.abs)) * 1.15;
    const step = (lo, hi) => { const span = hi - lo, raw = span / 3, p = Math.pow(10, Math.floor(Math.log10(raw))); const m = raw / p; return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p; };
    const ticks = (lo, hi) => { const s = step(lo, hi), out = []; for (let v = Math.ceil(lo / s) * s; v <= hi; v += s) out.push(+v.toFixed(6)); return out; };

    const panels = [
      { title: mph ? "SPEED MPH" : "SPEED KM/H", lo: vLo, hi: vHi, val: (r) => r[2] * vScale, grid: ticks(vLo, vHi) },
      { title: "THROTTLE %", lo: -5, hi: 110, val: (r) => r[3] * 100, grid: [0, 50, 100] },
      { title: "BRAKE %", lo: -5, hi: 110, val: (r) => r[4] * 100, grid: [0, 50, 100] },
      { title: "DELTA S · VS " + refName, lo: -dMax, hi: dMax, delta: true, grid: ticks(-dMax, dMax),
        fmt: (g) => (g === 0 ? "0" : (g > 0 ? "+" : "−") + Math.abs(g).toFixed(Math.abs(g) < 0.1 ? 2 : 1)) },
      { title: "STEERING", lo: -sMax, hi: sMax, val: (r) => r[5], grid: [0], fmt: () => "0" },
      { title: "GEAR", lo: 0.5, hi: gHi, val: (r) => r[6], grid: [1, 2, 3, 4, 5, 6, 7, 8].filter((g) => g < gHi) },
      { title: "TC", lanes: true, on: A.TC, level: A.TCL, level2: A.CUT },
      { title: "ABS", lanes: true, on: A.ABS, level: A.ABSL },
      { title: "STABILITY", lanes: true, on: A.ESC, level: A.ESCL },
      { title: "ENGINE MAP", lanes: true, on: null, level: A.MAP },
    ];
    const pages = Math.ceil(panels.length / PER_PAGE);
    const viewH = Math.max(200, wrap.clientHeight);
    canvas.style.height = pages * viewH + "px";
    const snaps = $("gpages");
    if (snaps.childElementCount !== pages) snaps.innerHTML = "<div></div>".repeat(pages);
    snaps.querySelectorAll("div").forEach((d) => { d.style.height = viewH + "px"; });
    const dots = $("gdots");
    if (dots.childElementCount !== pages) {
      dots.innerHTML = "";
      for (let p = 0; p < pages; p++) {
        const b = document.createElement("button");
        b.setAttribute("aria-label", "Graphs page " + (p + 1));
        b.addEventListener("click", () => wrap.scrollTo({ top: p * viewH, behavior: "smooth" }));
        dots.appendChild(b);
      }
    }
    const page = Math.round(wrap.scrollTop / viewH);
    dots.querySelectorAll("button").forEach((b, i) => b.classList.toggle("on", i === page));

    const { ctx, w } = prep(canvas);
    const gap = 8, axisH = 18;
    const pl = 46, pr = 8;
    const W = w - pl - pr;
    const X = (d) => pl + (d / len) * W;
    const font = getComputedStyle(document.body).fontFamily;
    const nowEnd = sec.now.length ? sec.now[sec.now.length - 1][0] : null;
    const cx = S.cursor === null ? null : X(Math.min(S.cursor, len));
    const ph = (viewH - gap * (PER_PAGE - 1) - axisH - 4) / PER_PAGE;
    const band = 17;                                     // the title sits above the plot, never under a line

    // a line split at the cursor: full before it, faded after it
    const split = (top, height, paint) => {
      if (cx === null) { paint(LINE_ALPHA); return; }
      ctx.save(); ctx.beginPath(); ctx.rect(0, top, cx, height); ctx.clip(); paint(LINE_ALPHA); ctx.restore();
      ctx.save(); ctx.beginPath(); ctx.rect(cx, top, w - cx, height); ctx.clip(); paint(AHEAD_ALPHA); ctx.restore();
    };

    panels.forEach((panel, i) => {
      const p = Math.floor(i / PER_PAGE);
      const top = p * viewH + (i % PER_PAGE) * (ph + gap);
      ctx.font = "800 11.5px " + font;
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillStyle = COL.title;
      ctx.fillText(panel.title, pl + 2, top + 2);
      if (panel.lanes) return drawLanes(panel, top);
      const Y = (v) => top + band + 4 + (1 - (v - panel.lo) / (panel.hi - panel.lo)) * (ph - band - 8);
      ctx.font = "600 11px " + font;
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      for (const g of panel.grid) {
        if (g < panel.lo || g > panel.hi) continue;
        ctx.beginPath(); ctx.moveTo(pl, Y(g)); ctx.lineTo(w - pr, Y(g));
        ctx.strokeStyle = COL.grid; ctx.lineWidth = 1; ctx.stroke();
        ctx.fillStyle = COL.label;
        ctx.fillText(panel.fmt ? panel.fmt(g) : String(Math.round(g)), pl - 6, Y(g));
      }
      ctx.save();
      ctx.beginPath(); ctx.rect(pl, top + band, W, ph - band); ctx.clip();
      const draw = (rows, val, color, width) => {
        if (rows.length < 2) return;
        split(top, ph, (alpha) => {
          ctx.beginPath();
          rows.forEach((r, k) => { const x = X(r[0]), y = Y(val(r)); if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
          stroke(ctx, color, width, alpha);
        });
      };
      if (panel.delta) {
        if (sec.best.length > 1 || refName === "LAST") {
          ctx.beginPath(); ctx.moveTo(pl, Y(0)); ctx.lineTo(w - pr, Y(0));
          stroke(ctx, refName === "BEST" ? COL.best : COL.last, 2);
        }
        if (refName === "BEST") draw(deltas.last, (r) => r[1], COL.last, 2.2);
        draw(deltas.now, (r) => r[1], COL.now, 2.6);
      } else {
        draw(lines.best, panel.val, COL.best, 2.2);
        draw(lines.last, panel.val, COL.last, 2.2);
        draw(lines.now, panel.val, COL.now, 2.6);
      }
      if (recording() && S.live && S.live.sec === S.sel && nowEnd !== null) {
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(X(nowEnd), top + band); ctx.lineTo(X(nowEnd), top + ph);
        stroke(ctx, COL.now, 1, 0.5);
        ctx.setLineDash([]);
      }
      ctx.restore();
    });

    // assist panel: one lane per line (best / last / now); filled where the system works, the set level
    // on the left (and where it changes), the share of the section it worked in the title band
    function drawLanes(panel, top) {
      const names = [["best", COL.best], ["last", COL.last], ["now", COL.now]];
      const laneGap = 5;
      const laneH = (ph - band - 6 - laneGap * 2) / 3;
      const recorded = (rows) => rows.some((r) => r[panel.level] !== null && r[panel.level] !== undefined
        || (panel.on !== null && r[panel.on] !== null && r[panel.on] !== undefined));
      const shares = [];
      names.forEach(([key, color], k) => {
        const rows = lines[key];
        const y = top + band + 4 + k * (laneH + laneGap);
        ctx.fillStyle = "#1a2129";
        ctx.beginPath(); ctx.roundRect(pl, y, W, laneH, 4); ctx.fill();
        ctx.font = "700 11px " + font;
        ctx.textBaseline = "middle";
        if (rows.length < 2 || !recorded(rows)) {
          ctx.textAlign = "right"; ctx.fillStyle = "#3a424c";
          ctx.fillText("-", pl - 6, y + laneH / 2);
          if (rows.length >= 2) { ctx.textAlign = "left"; ctx.fillText("NOT RECORDED", pl + 8, y + laneH / 2); }
          shares.push(null);
          return;
        }
        if (panel.on !== null) {                          // where it works
          let on = 0, total = 0;
          split(y, laneH, (alpha) => {
            ctx.globalAlpha = alpha;
            ctx.fillStyle = color;
            for (let r = 0; r < rows.length - 1; r++) {
              if (rows[r][panel.on]) ctx.fillRect(X(rows[r][0]), y + 2, Math.max(1.5, X(rows[r + 1][0]) - X(rows[r][0])), laneH - 4);
            }
            ctx.globalAlpha = 1;
          });
          for (let r = 0; r < rows.length - 1; r++) {
            const dd = rows[r + 1][0] - rows[r][0];
            total += dd;
            if (rows[r][panel.on]) on += dd;
          }
          shares.push(total > 0 ? Math.round((on / total) * 100) : null);
        } else {
          shares.push(null);
        }
        const label = (r) => {
          const a = r[panel.level], b = panel.level2 ? r[panel.level2] : null;
          if (a === null || a === undefined) return "OFF";
          return b !== null && b !== undefined ? a + "/" + b : String(a);
        };
        ctx.textAlign = "right";                          // the level at the section start
        ctx.fillStyle = color;
        ctx.fillText(label(rows[0]), pl - 6, y + laneH / 2);
        ctx.textAlign = "left";
        for (let r = 1; r < rows.length; r++) {           // and where it changes
          const now = label(rows[r]);
          if (now === label(rows[r - 1])) continue;
          const x = X(rows[r][0]);
          ctx.fillStyle = "#e8edf2";
          ctx.fillRect(x - 1, y, 2, laneH);
          ctx.font = "800 11px " + font;
          ctx.fillText("→ " + now, x + 5, y + laneH / 2);
        }
        if (panel.on === null) {                          // engine map: the level written in the lane
          ctx.fillStyle = "#6b7580";
          ctx.font = "700 11px " + font;
          ctx.fillText(key.toUpperCase() + " · MAP " + label(rows[0]), pl + 8, y + laneH / 2);
        }
      });
      if (panel.on !== null) {
        ctx.font = "700 11px " + font;
        ctx.textAlign = "right";
        ctx.textBaseline = "top";
        const txt = shares.map((s, k) => (s === null ? "" : ["BEST ", "LAST ", "NOW "][k] + s + " %")).filter(Boolean).join(" · ");
        ctx.fillStyle = COL.label;
        ctx.fillText(txt ? "WORKING " + txt : "", w - pr, top + 3);
      }
    }

    // per page: metres along the section and the cursor
    for (let p = 0; p < pages; p++) {
      const base = p * viewH + viewH - 2;
      ctx.font = "600 11px " + font;
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillStyle = COL.label;
      const mStep = len > 400 ? 100 : 50;
      for (let m = 0; m <= len + 0.1; m += mStep) {
        if (cx !== null && Math.abs(X(m) - cx) < 28) continue;
        ctx.fillText(m + " m", Math.min(w - pr - 14, Math.max(pl + 8, X(m))), base);
      }
      if (cx !== null) {                               // the cursor: where the finger is on the map
        ctx.beginPath(); ctx.moveTo(cx, p * viewH + 15); ctx.lineTo(cx, base - axisH + 2);
        stroke(ctx, COL.cur, 1.6, 0.95);
        const label = Math.round(S.cursor) + " m";
        ctx.font = "800 11px " + font;
        const tw = ctx.measureText(label).width + 10;
        const lx = Math.max(pl, Math.min(w - pr - tw, cx - tw / 2));
        ctx.fillStyle = COL.cur;
        ctx.beginPath(); ctx.roundRect(lx, base - axisH + 3, tw, axisH - 2, 4); ctx.fill();
        ctx.fillStyle = "#1a1600";
        ctx.textAlign = "left";
        ctx.fillText(label, lx + 5, base);
      }
    }
  }

  /* ------------------------------------------------------------ offers and end of run */

  function offerRow(o) {
    const el = document.createElement("div");
    el.className = "offer";
    let em, small;
    if (o.kind === "lap") {
      em = fmtLap(o.time);
      small = o.base ? (o.base - o.time).toFixed(3) + " faster than your baseline " + fmtLap(o.base) : "first baseline lap for this car and track";
    } else {
      em = o.base ? fmtDelta(o.time - o.base) : fmtSec(o.time);
      small = o.base ? "new best section (" + fmtSec(o.time) + ", baseline " + fmtSec(o.base) + ")" : "first baseline for this section";
    }
    const current = S.state && S.state.active && o.game === S.state.game && o.car === S.state.car && o.track === S.state.track;
    if (!current) small += " · " + [o.car, o.track].join(" · ");
    el.innerHTML = "<div class='w'>" + esc(o.label) + " <em>" + esc(em) + "</em>" + (o.invalid ? "<span class='inv'>INVALID LAP</span>" : "")
      + "<small>" + esc(small) + (o.invalid ? " · the lap time does not count" : "") + "</small></div>"
      + "<button class='sbtn save'>SAVE</button><button class='sbtn'>SKIP</button>";
    if (o.kind === "section" && current) {             // look at the section before deciding
      el.querySelector(".w").addEventListener("click", () => select(o.sec, true));
    }
    const [save, skip] = el.querySelectorAll("button");
    save.addEventListener("click", () => decide(o.id, true));
    skip.addEventListener("click", () => decide(o.id, false));
    return el;
  }

  function decide(id, save) {
    post("/api/analysis/offer", { id, save }).then((state) => { if (!state.error) applyState(state); });
  }

  function applyState(state) {
    S.state = state;
    S.version = state.version;
    renderOffers();
    renderModal();
    mapDirty = true;
    loadSection().then(renderAll);
  }

  function renderOffers() {
    const st = S.state;
    const offers = (st && st.offers) || [];
    const box = $("offers");
    box.innerHTML = "";
    if (!offers.length) box.innerHTML = "<div class='none'>Nothing to review.<br>New best laps and sections appear here as you drive.</div>";
    offers.forEach((o) => box.appendChild(offerRow(o)));
    $("save-all").disabled = !offers.length;
    $("skip-all").disabled = !offers.length;
    $("undo").hidden = !(st && st.undo);
    $("undo-label").textContent = (st && st.undo) || "";
  }

  function setTab(tab) {
    S.tab = tab;
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    $("pane-review").hidden = tab !== "review";
    $("pane-graphs").hidden = tab !== "graphs";
    $("pane-trainer").hidden = tab !== "trainer";
    if (tab === "graphs") renderGraphs();
    if (tab === "trainer") renderTrainer();
  }

  /* ------------------------------------------------------------ AI trainer */

  function loadTrainer() {
    return get("/api/trainer").then((t) => { if (t.providers) { S.trainer = t; renderAi(); } }).catch(() => {});
  }

  function aiView() {                                  // what a tap on the button analyses: the map decides
    const n = S.sel + 1;
    return S.zoom ? { mode: "section", section: S.sel, title: "SECTION " + n } : { mode: "track", section: null, title: "WHOLE TRACK" };
  }

  function renderAi() {
    const btn = $("ai"), what = $("ai-what");
    const t = S.trainer;
    const usable = !!(t && t.ok && S.state && S.state.active && !S.trAsking);
    let text = "";
    if (S.trAsking) text = "ASKING…";
    else if (!t) text = "-";
    else if (t.provider === "off") text = "OFF";
    else if (!t.ok) text = t.error || "NOT CONNECTED";
    else if (!(S.state && S.state.active)) text = "NO RUN YET";
    if (what.textContent !== text) what.textContent = text;
    btn.disabled = !usable;
    btn.classList.toggle("off", !usable && !S.trAsking);
  }

  function ask(v) {
    if (S.trAsking) return;
    S.trAsking = v;
    S.trError = null;
    setTab("trainer");
    renderAi();
    post("/api/trainer/ask", { mode: v.mode, section: v.section }).then((r) => {
      if (r.trainer) S.trainer = r.trainer;
      if (r.entry) S.trEntry = r.entry;
      else S.trError = { code: r.error || "NO ANSWER", detail: r.detail || "" };
    }).catch(() => { S.trError = { code: "NO CONNECTION TO THE PC", detail: "" }; })
      .finally(() => { S.trAsking = null; renderAi(); renderTrainer(); });
  }

  const ERRORS = {
    "NO KEY": "No API key yet: add it in the settings (gear button) under AI TRAINER.",
    "KEY REJECTED": "The AI rejected the API key: check it in the settings.",
    "MODEL NOT FOUND": "The model is not available for this key: try the other level (FAST / BEST) in the settings.",
    "NO CONNECTION": "The PC cannot reach the AI: check the internet connection.",
    "OLLAMA NOT RUNNING": "Ollama is not running on the PC.",
    "RATE LIMITED": "Too many questions: wait a moment and ask again.",
    "NO ANSWER IN TIME": "The AI took too long: ask again, or use FAST.",
    "ANSWER NOT READABLE": "The AI answer could not be read: ask again.",
    "NO DATA": "Not enough laps recorded here yet to compare.",
    "BUSY": "A question is already on its way.",
    "AI REFUSED": "The AI declined to answer: ask again.",
  };

  function renderTrainer() {
    const pane = $("pane-trainer");
    const t = S.trainer;
    const history = (t && t.history) || [];
    const v = aiView();
    let entry = S.trEntry;
    if (!entry && !S.trAsking) entry = history.find((e) => e.title === v.title && S.state && e.car === S.state.car && e.track === S.state.track) || null;
    const level = t ? (t.level || "").toUpperCase() : "";
    let html;
    if (S.trAsking) {
      html = "<div class='tr-head'><div><b>" + esc(S.trAsking.title) + "</b><span>ASKING " + esc(t ? t.provider_name : "THE AI")
        + " · " + esc(level) + (t && t.model ? " · " + esc(t.model) : "") + "</span></div></div>"
        + "<div class='tr-sum'>Asking the AI… this takes a few seconds" + (t && t.level === "best" ? " (BEST thinks longer)" : "") + ".</div>";
    } else if (S.trError) {
      html = "<div class='tr-head'><div><b>" + esc(v.title) + "</b><span>NO ANSWER</span></div>"
        + "<button class='sbtn' id='tr-again'>ASK AGAIN</button></div>"
        + "<div class='tr-sum err'>" + esc(ERRORS[S.trError.code] || S.trError.code)
        + (S.trError.detail ? "<small>" + esc(S.trError.code + ": " + S.trError.detail) + "</small>" : "") + "</div>";
    } else if (entry) {
      const a = entry.answer || {};
      const tips = (a.tips || []).map((tip, i) => "<div class='tip' data-sec='" + tip.section + "' data-m='" + tip.from_m + "'><i>" + (i + 1)
        + "</i><div><h4>" + esc(tip.title) + "</h4><span class='where'>SECTION " + tip.section + " · " + tip.from_m + "–" + tip.to_m + " M</span><p>"
        + esc(tip.text) + "</p></div><em>≈ " + Number(tip.gain_s).toFixed(2) + " s</em></div>").join("");
      const at = (entry.at || "").slice(11, 16);
      const chips = history.filter((e) => e.at !== entry.at).map((e) => "<button data-at='" + esc(e.at) + "'>" + esc(e.title)
        + " " + esc((e.at || "").slice(11, 16)) + "</button>").join("");
      html = "<div class='tr-head'><div><b>" + esc(entry.title) + "</b><span>" + esc(entry.times || "") + "</span></div>"
        + "<button class='sbtn' id='tr-again'>ASK AGAIN</button></div>"
        + "<div class='tips'>" + (tips || "<div class='tr-none'>No tips: nothing worth changing here.</div>")
        + (a.note ? "<div class='tr-note'>" + esc(a.note) + "</div>" : "") + "</div>"
        + "<div class='tr-foot'><span>" + esc([(entry.provider || "").toUpperCase(), (entry.level || "").toUpperCase(), entry.model, at,
          entry.seconds + " s"].filter(Boolean).join(" · ")) + "</span>"
        + (chips ? "<span class='tr-hist'>EARLIER: " + chips + "</span>" : "") + "</div>";
    } else {
      const why = !t ? "" : t.provider === "off" ? "The AI trainer is OFF: choose an AI in the settings (gear button)."
        : !t.ok ? (ERRORS[t.error] || "The AI is not connected: check the settings.") : "";
      html = "<div class='tr-none'>Tap <b>AI TRAINER</b> on the map: in the overview it analyses the whole track, zoomed into a section only that section.<br>Best, last and now are compared; you get up to 3 tips."
        + (why ? "<br><br>" + esc(why) : "") + "</div>";
    }
    if (pane.innerHTML !== html) pane.innerHTML = html;
    const again = $("tr-again");
    if (again) again.onclick = () => ask(entry && !S.trError ? { mode: entry.mode, section: entry.section ? entry.section - 1 : null, title: entry.title } : aiView());
    pane.querySelectorAll(".tr-hist button").forEach((b) => { b.onclick = () => {
      S.trEntry = history.find((e) => e.at === b.dataset.at) || null; S.trError = null; renderTrainer();
    }; });
    pane.querySelectorAll(".tip").forEach((el) => { el.onclick = () => {   // look at the place in the graphs
      select(+el.dataset.sec - 1, true);
      S.cursor = +el.dataset.m;
      mapDirty = true;
      renderAll();
    }; });
  }

  function renderModal() {
    const st = S.state;
    const ended = st && st.ended;
    const show = !!ended && S.endDismissed !== ended.run;
    $("modal").hidden = !show;
    $("overlay").hidden = !show;
    if (!show) return;
    const offers = st.offers || [];
    const game = RD.info && RD.info.games ? (RD.info.games.find((g) => g.id === ended.game) || {}).name || ended.game : ended.game;
    $("m-sub").textContent = [game, ended.car, ended.track].join(" · ") + " · run " + ended.run.replace("_", " ").replace(/-(\d\d)-(\d\d)$/, ":$1:$2") + (ended.reason ? " · " + ended.reason : "");
    $("m-laps").textContent = ended.laps;
    $("m-best").textContent = fmtLap(ended.best);
    $("m-open").textContent = offers.length;
    $("m-mb").textContent = ended.mb + " MB";
    $("m-open-h").hidden = !offers.length;
    const box = $("m-offers");
    box.innerHTML = "";
    offers.forEach((o) => box.appendChild(offerRow(o)));
    $("keep-all-s").textContent = ended.laps + " lap files stay in this run";
    $("keep-base-s").textContent = "delete the " + ended.laps + " lap files of this run";
  }

  function finish(keep) {
    const run = S.state && S.state.ended && S.state.ended.run;
    post("/api/analysis/finish", { keep }).then((state) => {
      S.endDismissed = run;
      if (!state.error) applyState(state); else renderModal();
    });
  }

  /* ------------------------------------------------------------ start */

  function renderAll() {
    renderHeader();
    renderDeltas();
    renderStrip();
    drawMap();
    renderAi();
    if (S.tab === "graphs") renderGraphs();
  }

  RD.analysis = function () {
    $("live").addEventListener("click", () => {
      S.liveMode = true;
      S.zoom = false;
      S.cursor = null;
      lastFollow = -1;
      if (S.live && S.live.sec !== null && S.live.sec !== undefined) S.sel = S.live.sec;
      mapDirty = true;
      loadSection().then(renderAll);
    });
    document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
    $("m-save-all").addEventListener("click", () => post("/api/analysis/save-all").then((s) => { if (!s.error) applyState(s); }));
    $("save-all").addEventListener("click", () => post("/api/analysis/save-all").then((s) => { if (!s.error) applyState(s); }));
    // SKIP ALL cannot be undone: the first tap arms it for 3 s, the second skips
    for (const id of ["skip-all", "m-skip-all"]) {
      const btn = $(id);
      let armed = 0;
      btn.addEventListener("click", () => {
        if (armed > performance.now()) {
          armed = 0;
          btn.classList.remove("armed");
          btn.textContent = "SKIP ALL";
          post("/api/analysis/skip-all").then((s) => { if (!s.error) applyState(s); });
          return;
        }
        armed = performance.now() + 3000;
        btn.classList.add("armed");
        btn.textContent = "TAP AGAIN";
        setTimeout(() => { if (armed && armed <= performance.now()) { armed = 0; btn.classList.remove("armed"); btn.textContent = "SKIP ALL"; } }, 3050);
      });
    }
    $("undo-btn").addEventListener("click", () => post("/api/analysis/undo").then((s) => { if (!s.error) applyState(s); }));
    $("end").addEventListener("click", () => {
      if (S.endArmed > performance.now()) {
        S.endArmed = 0;
        post("/api/analysis/end").then((s) => { if (!s.error) applyState(s); });
      } else {
        S.endArmed = performance.now() + 3000;
        setTimeout(renderHeader, 3050);
      }
      renderHeader();
    });
    $("keep-all").addEventListener("click", () => finish("all"));
    $("keep-base").addEventListener("click", () => finish("baselines"));
    $("map").addEventListener("pointerdown", mapDown);
    $("map").addEventListener("pointermove", mapMove);
    $("map").addEventListener("pointerup", mapUp);
    $("map").addEventListener("pointercancel", () => { drag = null; });
    $("back").addEventListener("click", () => { S.zoom = false; mapDirty = true; renderAll(); });
    $("ai").addEventListener("click", () => ask(aiView()));
    loadTrainer();
    setInterval(loadTrainer, 15000);
    $("cells").addEventListener("click", (e) => {
      const el = e.target.closest("[data-n]");
      if (el) select(+el.dataset.n, true);
    });
    $("cells").addEventListener("scroll", () => { $("slider").value = String($("cells").scrollLeft); }, { passive: true });
    $("slider").addEventListener("input", () => {
      const cells = $("cells");
      cells.style.scrollBehavior = "auto";
      cells.scrollLeft = +$("slider").value;
      cells.style.scrollBehavior = "";
    });
    const ro = new ResizeObserver(() => { mapDirty = true; renderAll(); });
    ro.observe($("map"));
    ro.observe($("gwrap"));
    $("gwrap").addEventListener("scroll", () => { if (S.tab === "graphs") renderGraphs(); }, { passive: true });
    let dotPending = false;
    RD.listeners.push(() => {                            // the car dot follows the stream
      if (dotPending) return;
      dotPending = true;
      requestAnimationFrame(() => { dotPending = false; drawMap(); });
    });
    poll();
  };
})();
