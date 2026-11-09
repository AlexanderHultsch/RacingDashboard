/* Boost gauge (boost.html). Load after rd.js and seg14.js.
 *
 *   <div class="rd-boost"><svg class="boost-dial" viewBox="0 0 200 200"></svg><div class="boost-readout"></div></div>
 *
 * Fields (core/telemetry.py): boost_bar (bar above the air pressure, negative = vacuum, null = the game sends
 * none), turbo (false = the car has no turbo), boost_min_bar (iRacing -1), boost_max_bar (the car's maximum).
 * The dial runs over 270 degrees from boost_min_bar (else 0) to the car's maximum rounded up to 0.5 bar (2 bar
 * when unknown); it grows when the boost goes higher, until the car changes.
 * Shows: the needle, a yellow arc up to the value (blue below 0) and the value in segments with BAR, or VACUUM
 * below 0; NO TURBO (a car without a turbo), NO DATA (a game without a boost value, with a hint in the chip),
 * E (no usable data, the chip says why).
 */
(function () {
  "use strict";

  const C = 100, R = 82, A0 = -135, A1 = 135;
  const point = (a, r) => [C + r * Math.sin(a * Math.PI / 180), C - r * Math.cos(a * Math.PI / 180)];
  const fixed = (v) => +v.toFixed(2);
  function arc(a, b, r) {
    if (b - a < 0.01) return "";
    const [x0, y0] = point(a, r), [x1, y1] = point(b, r);
    return `M${fixed(x0)} ${fixed(y0)} A${r} ${r} 0 ${b - a > 180 ? 1 : 0} 1 ${fixed(x1)} ${fixed(y1)}`;
  }
  const up = (v) => Math.ceil(v * 2 - 1e-6) / 2;            // round up to 0.5 bar

  let gameName = "";
  RD.loadInfo().then((info) => { gameName = (info.game_name || "").toUpperCase(); }).catch(() => {});
  RD.notices.push((f) => (f.boost_bar == null && f.turbo !== false ? (gameName || "THIS GAME") + " SENDS NO BOOST" : null));

  RD.widgetInits.push([".rd-boost", (el) => {
    const dial = el.querySelector(".boost-dial");
    const readout = el.querySelector(".boost-readout");
    let scaleKey = null, lo = 0, hi = 2, fill = null, needle = null;
    let car = null, peak = 0, lastText = null;

    function scale(min, max) {
      const key = min + "|" + max;
      if (key === scaleKey) return;
      scaleKey = key; lo = min; hi = max;
      const angle = (v) => A0 + (A1 - A0) * (v - lo) / (hi - lo);
      const major = hi - lo <= 3 ? 0.5 : 1, minor = major / 5;
      let out = `<path class="track" d="${arc(A0, A1, R)}"/>`;
      if (lo < 0) out += `<path class="vac-zone" d="${arc(A0, angle(0), R)}"/>`;
      out += `<path class="fill"/>`;
      for (let i = 0, n = Math.round((hi - lo) / minor); i <= n; i++) {
        const v = lo + i * minor, a = angle(v), isMajor = Math.abs(v / major - Math.round(v / major)) < 1e-6;
        const [x0, y0] = point(a, R - 7), [x1, y1] = point(a, R - (isMajor ? 15 : 11));
        out += `<line class="tick${isMajor ? "" : " minor"}" x1="${fixed(x0)}" y1="${fixed(y0)}" x2="${fixed(x1)}" y2="${fixed(y1)}"/>`;
        if (isMajor) {
          const [tx, ty] = point(a, R - 24);
          out += `<text x="${fixed(tx)}" y="${fixed(ty)}">${fixed(v)}</text>`;
        }
      }
      out += `<g class="needle-group"><polygon class="needle" points="${C - 2.6},${C + 12} ${C - 0.9},${C - R + 5} ${C + 0.9},${C - R + 5} ${C + 2.6},${C + 12}"/>` +
             `<circle class="hub" cx="${C}" cy="${C}" r="7"/><circle class="hub-dot" cx="${C}" cy="${C}" r="3"/></g>`;
      dial.innerHTML = out;
      fill = dial.querySelector(".fill");
      needle = dial.querySelector(".needle-group");
    }

    function text(kind, value, unit) {
      const key = kind + value + (unit || "");
      if (key === lastText) return;
      lastText = key;
      readout.innerHTML = "";
      const add = (cls, t, font) => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", cls);
        Seg14.draw(svg, t, font);
        readout.appendChild(svg);
      };
      if (kind === "msg") add("msg", value, Seg14.LABEL);
      else { add("num", value, Seg14.DIGIT); add("unit", unit, Seg14.LABEL); }
    }

    function update(f) {
      if (f.car !== car) { car = f.car; peak = 0; }
      const value = f.boost_bar;
      const ok = !RD.errorOf(f) && typeof value === "number" && isFinite(value);
      const min = typeof f.boost_min_bar === "number" && f.boost_min_bar < 0 ? -1 : 0;
      if (ok) peak = Math.max(peak, value);
      scale(min, Math.max(1, f.boost_max_bar > 0 ? up(f.boost_max_bar) : 2, up(peak)));
      el.classList.toggle("off", !ok);
      if (!ok) {
        text("msg", RD.errorOf(f) ? "E" : f.turbo === false ? "NO TURBO" : "NO DATA");
        return;
      }
      const v = Math.max(lo, Math.min(hi, value));
      const angle = (x) => A0 + (A1 - A0) * (x - lo) / (hi - lo);
      fill.setAttribute("d", v >= 0 ? arc(angle(Math.max(0, lo)), angle(v), R) : arc(angle(v), angle(0), R));
      fill.classList.toggle("vac", v < 0);
      needle.setAttribute("transform", `rotate(${fixed(angle(v))} ${C} ${C})`);
      text("num", (Math.abs(value) < 0.005 ? 0 : value).toFixed(2), value < -0.005 ? "VACUUM" : "BAR");
    }

    update({});
    RD.listeners.push(update);
  }]);
})();
