/* Map page (map.html): the whole track fitted to the screen and a red dot for the car. Load after rd.js.
 *
 *   <div class="rd-map"></div>
 *
 * The page draws the track itself from the live position: the lap is cut into BINS pieces by lap_pos and each
 * piece keeps the car's pos_x / pos_y there, so after one lap the whole track is known. It is kept per game and
 * track in the browser (localStorage) and seeded from the analysis recorder's outline (GET /api/analysis: the best
 * lap, else the last lap or the lap so far), so a track with a saved best lap is complete at once. A jump (reset,
 * back to the pits) leaves no line across the map: pieces further apart than JUMP_M are not joined.
 * Scale: once FULL of the lap is known the track is fitted to the screen exactly and stays put; before that the
 * view is at least the size a track of that length needs (track_length_m / 3.2), so a straight does not fill the
 * screen, and it only grows when the car drives out of it. Same orientation as the analysis map. The start /
 * finish line is drawn where lap_pos is 0.
 */
(function () {
  "use strict";

  const BINS = 1000, FULL = 0.95, JUMP_M = 80, GAP_BINS = 6, SAVE_MS = 5000, OUTLINE_MS = 10000;
  const NS = "http://www.w3.org/2000/svg";
  let notice = null;
  RD.notices.push(() => notice);

  const store = {
    get: (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode: not kept */ } },
  };

  RD.widgetInits.push([".rd-map", (el) => {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "map-svg");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.innerHTML = `<path class="edge"/><path class="track"/><line class="start"/><circle class="glow"/><circle class="dot"/>`;
    el.appendChild(svg);
    const [edge, track, start, glow, dot] = svg.children;

    let key = null, bins = new Array(BINS).fill(null), length = 0, view = null, full = false;
    let dirty = false, lastSave = 0, lastDraw = 0, lastOutline = 0;

    function reset(newKey, trackLength) {
      key = newKey;
      length = trackLength || 0;
      const saved = store.get("rd-map:" + key);
      bins = Array.isArray(saved) && saved.length === BINS ? saved : new Array(BINS).fill(null);
      view = null;
      dirty = true;
      lastOutline = 0;
    }

    const filled = () => bins.reduce((n, b) => n + (b ? 1 : 0), 0);
    // how much of the lap is known: a piece counts when it or a neighbour within 2 pieces (~8 m) is known
    const covered = () => bins.reduce((n, b, i) => n + ([-2, -1, 0, 1, 2].some((o) => bins[(i + o + BINS) % BINS]) ? 1 : 0), 0) / BINS;

    function seed() {                                   // the recorder's outline fills pieces the page has not seen
      lastOutline = performance.now();
      fetch("/api/analysis").then((r) => (r.ok ? r.json() : null)).then((st) => {
        if (!st || !st.outline || st.track !== key.split("|")[1]) return;
        for (const [x, y, p] of st.outline) {
          if (x === null || y === null || p === null) continue;
          const i = Math.min(BINS - 1, Math.max(0, Math.floor(p * BINS)));
          if (!bins[i]) { bins[i] = [x, y]; dirty = true; }
        }
      }).catch(() => {});
    }

    // the track as path pieces: consecutive known bins, not joined across gaps or jumps (and round the line)
    function pathData() {
      let d = "", prev = null, prevI = -99;
      const order = [...Array(BINS).keys()];
      for (const i of order.concat(order.slice(0, GAP_BINS))) {
        const b = bins[i % BINS];
        if (!b) continue;
        const near = prev && i - prevI <= GAP_BINS && Math.hypot(b[0] - prev[0], b[1] - prev[1]) < JUMP_M;
        d += (near ? " L" : " M") + b[0].toFixed(1) + " " + b[1].toFixed(1);
        prev = b; prevI = i;
      }
      return d;
    }

    function fit(carX, carY) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      const add = (x, y) => { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); };
      bins.forEach((b) => b && add(b[0], b[1]));
      if (typeof carX === "number") add(carX, carY);
      if (!isFinite(x0)) return;
      full = covered() >= FULL;
      // until the lap is known: at least the size a track of this length needs, so it does not zoom in on a straight
      const least = full ? 0 : Math.max(length / 3.2, 200);
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      let w = Math.max(x1 - x0, least), h = Math.max(y1 - y0, least);
      const pad = Math.max(w, h) * 0.06;
      w += 2 * pad; h += 2 * pad;
      view = { x: cx - w / 2, y: cy - h / 2, w, h, full };
      svg.setAttribute("viewBox", `${view.x} ${view.y} ${w} ${h}`);
      const scale = Math.min(r.width / w, r.height / h);                 // screen px per metre
      const tw = Math.max(5, Math.min(14, 0.012 * Math.min(r.width, r.height))) / scale;
      edge.style.strokeWidth = tw + 3 / scale;
      track.style.strokeWidth = tw;
      start.style.strokeWidth = 3 / scale;
      start.dataset.half = tw * 1.1;
      dot.setAttribute("r", 7 / scale);
      glow.setAttribute("r", 14 / scale);
    }

    const inside = (x, y) => view && x > view.x && x < view.x + view.w && y > view.y && y < view.y + view.h;

    function draw(carX, carY) {
      const d = pathData();
      edge.setAttribute("d", d);
      track.setAttribute("d", d);
      const a = bins[0] || bins[1], b = bins[4] || bins[5];
      start.style.display = a && b ? "" : "none";
      if (a && b) {
        const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = -(b[1] - a[1]) / len, ny = (b[0] - a[0]) / len;
        const half = Number(start.dataset.half || 6);
        start.setAttribute("x1", a[0] + nx * half); start.setAttribute("y1", a[1] + ny * half);
        start.setAttribute("x2", a[0] - nx * half); start.setAttribute("y2", a[1] - ny * half);
      }
      notice = filled() < 2 ? "DRIVE A LITTLE: THE MAP IS DRAWN AS YOU DRIVE" : null;
    }

    window.addEventListener("resize", () => { view = null; dirty = true; });

    function update(f) {
      const error = RD.errorOf(f);
      el.classList.toggle("off", !!error);
      if (f.game && f.track) {
        const k = f.game + "|" + f.track;
        if (k !== key) reset(k, f.track_length_m);
        if (!length && f.track_length_m) length = f.track_length_m;
      }
      const ok = !error && key && typeof f.pos_x === "number" && typeof f.pos_y === "number";
      const now = performance.now();
      if (ok && typeof f.lap_pos === "number" && (f.speed_kmh || 0) > 5) {
        const i = Math.min(BINS - 1, Math.max(0, Math.floor(f.lap_pos * BINS)));
        const b = bins[i];
        if (!b || Math.hypot(b[0] - f.pos_x, b[1] - f.pos_y) > 2) { bins[i] = [+f.pos_x.toFixed(1), +f.pos_y.toFixed(1)]; dirty = true; }
      }
      if (key && now - lastOutline > OUTLINE_MS && (!view || !view.full)) seed();
      if (dirty && now - lastDraw > 500) {
        lastDraw = now;
        if (!view || (!view.full && covered() >= FULL) || (ok && !inside(f.pos_x, f.pos_y))) fit(f.pos_x, f.pos_y);
        draw();
        dirty = false;
        if (now - lastSave > SAVE_MS) { lastSave = now; store.set("rd-map:" + key, bins); }
      }
      dot.style.display = glow.style.display = ok && view ? "" : "none";
      if (ok) {
        if (view && !inside(f.pos_x, f.pos_y)) dirty = true;
        dot.setAttribute("cx", f.pos_x); dot.setAttribute("cy", f.pos_y);
        glow.setAttribute("cx", f.pos_x); glow.setAttribute("cy", f.pos_y);
      }
    }
    update({});
    RD.listeners.push(update);
  }]);
})();
