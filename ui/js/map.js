/* Map page (map.html): the whole track fitted to the screen and a red dot for the car. Load after rd.js.
 *
 *   <div class="rd-map"></div>
 *
 * The track is the analysis recorder's outline (GET /api/analysis: a point every 5 m from the best lap, else the
 * last lap or the lap so far), fetched every OUTLINE_MS; the dot is pos_x / pos_y of every frame. Same orientation
 * as the analysis map. Until a track is recorded the page says so in the chip; it fills in as the car drives.
 */
(function () {
  "use strict";

  const OUTLINE_MS = 3000;
  const NS = "http://www.w3.org/2000/svg";
  let notice = null;
  RD.notices.push(() => notice);

  RD.widgetInits.push([".rd-map", (el) => {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "map-svg");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.innerHTML = `<polyline class="edge"/><polyline class="track"/><line class="start"/><circle class="glow"/><circle class="dot"/>`;
    el.appendChild(svg);
    const [edge, track, start, glow, dot] = svg.children;
    let key = "", scale = 1;

    function fit(points) {
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const [x, y] of points) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
      const pad = Math.max(x1 - x0, y1 - y0, 50) * 0.06;
      svg.setAttribute("viewBox", `${x0 - pad} ${y0 - pad} ${x1 - x0 + 2 * pad} ${y1 - y0 + 2 * pad}`);
      const r = el.getBoundingClientRect();
      scale = Math.min(r.width / (x1 - x0 + 2 * pad), r.height / (y1 - y0 + 2 * pad)) || 1;   // screen px per metre
      const line = points.map(([x, y]) => `${x},${y}`).join(" ");
      edge.setAttribute("points", line);
      track.setAttribute("points", line);
      const w = Math.max(5, Math.min(14, 0.012 * Math.min(r.width, r.height))) / scale;     // track width in metres
      edge.style.strokeWidth = w + 3 / scale;
      track.style.strokeWidth = w;
      // the start / finish line across the track at the first point
      const [ax, ay] = points[0], [bx, by] = points[Math.min(3, points.length - 1)];
      const len = Math.hypot(bx - ax, by - ay) || 1, nx = -(by - ay) / len, ny = (bx - ax) / len, half = w * 1.1;
      start.setAttribute("x1", ax + nx * half); start.setAttribute("y1", ay + ny * half);
      start.setAttribute("x2", ax - nx * half); start.setAttribute("y2", ay - ny * half);
      start.style.strokeWidth = 3 / scale;
      dot.setAttribute("r", 7 / scale);
      glow.setAttribute("r", 14 / scale);
    }

    function load() {
      fetch("/api/analysis").then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then((st) => {
        const points = (st.outline || []).filter((p) => p[0] !== null && p[1] !== null).map((p) => [p[0], p[1]]);
        notice = points.length < 2 ? "DRIVE A LITTLE: THE MAP IS DRAWN FROM THE LAP" : null;
        const k = points.length + ":" + (points[0] || "") + ":" + (points[points.length - 1] || "");
        if (points.length >= 2 && k !== key) { key = k; fit(points); }
      }).catch((status) => { notice = status === 404 ? "THE MAP NEEDS THE ANALYSIS (OFF IN THE CONFIG)" : null; });
    }
    load();
    setInterval(load, OUTLINE_MS);
    window.addEventListener("resize", () => { key = ""; load(); });

    function update(f) {
      const error = RD.errorOf(f);
      const ok = !error && typeof f.pos_x === "number" && typeof f.pos_y === "number";
      el.classList.toggle("off", !!error);
      dot.style.display = glow.style.display = ok && key ? "" : "none";
      if (ok) {
        dot.setAttribute("cx", f.pos_x); dot.setAttribute("cy", f.pos_y);
        glow.setAttribute("cx", f.pos_x); glow.setAttribute("cy", f.pos_y);
      }
    }
    update({});
    RD.listeners.push(update);
  }]);
})();
