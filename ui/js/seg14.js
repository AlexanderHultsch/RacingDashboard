/* 14-segment display, drawn as SVG (no font needed, sharp at any size).
 *
 * Segments as on a real display: outer a (top) b (upper right) c (lower right) d (bottom)
 * e (lower left) f (upper left), middle bar g1 g2, centre verticals i (upper) l (lower),
 * diagonals h (upper left) j (upper right) k (lower left) m (lower right). Every diagonal
 * fills its quadrant from the outer corner to the centre, with the same gap as the others.
 *
 * Seg14.draw(svg, "R", Seg14.DIGIT)   draws text into an <svg> (digits, R N E G A P D S B L M O T U C V, "-", "." decimal
 *                                      point, ":" colon)
 *
 * Widgets (registered with RD when rd.js is loaded first):
 *   <svg class="rd-seg" data-field="gear" data-fmt="gear"></svg>   a live field in segments
 *   <svg class="rd-seg-text" data-text="GEAR"></svg>                fixed text in segments
 * Lit segments have the class "on"; colour them with CSS (fill).
 */
(function () {
  "use strict";

  const GLYPHS = {
    "0": "a b c d e f", "1": "b c", "2": "a b g1 g2 e d", "3": "a b g1 g2 c d", "4": "f g1 g2 b c",
    "5": "a f g1 g2 c d", "6": "a f e d c g1 g2", "7": "a b c", "8": "a b c d e f g1 g2", "9": "a b c d f g1 g2",
    "R": "a b f e g1 g2 m", "N": "f e b c h m", "G": "a f e d c g2", "E": "a f e d g1 g2", "A": "a b c e f g1 g2",
    // gearbox letters: P park, D drive, S sport (the standard S, like a 5), B regen, L low, M manual
    "P": "a b f e g1 g2", "D": "a b c d i l", "S": "a f g1 g2 c d", "B": "a b c d g2 i l", "L": "f e d", "M": "f e b c h j",
    // for the boost page: BOOST, NO TURBO, VACUUM, NO DATA (O drawn like 0)
    "O": "a b c d e f", "T": "a i l", "U": "b c d e f", "C": "a f e d", "V": "f e k j",
    "-": "g1 g2", " ": "",
  };

  // W x H character box, t segment thickness, g gap between segments, gap between characters
  const DIGIT = { W: 150, H: 180, t: 21, g: 3.5, gap: 24 };
  const LABEL = { W: 150, H: 180, t: 28, g: 6, gap: 36 };

  function segments(W, H, t, g) {
    const m = H / 2, c = W / 2, tc = t;
    const P = (pts) => pts.map((p) => p.map((v) => +v.toFixed(2)).join(",")).join(" ");
    // a band from corner (x1,y1) to corner (x2,y2), thinner than the outer segments
    const quad = (x1, y1, x2, y2) => {
      const w = Math.abs(x2 - x1), h = Math.abs(y2 - y1), len = Math.hypot(w, h), T = t * 0.5;
      const dw = Math.min(w * 0.45, T * len / h) * Math.sign(x2 - x1);
      const dh = Math.min(h * 0.45, T * len / w) * Math.sign(y2 - y1);
      return P([[x1, y1], [x1 + dw, y1], [x2, y2 - dh], [x2, y2], [x2 - dw, y2], [x1, y1 + dh]]);
    };
    // quadrant limits: inside the outer segments, beside the centre verticals, above / below the middle bar
    const L = t + g, R = W - t - g, CL = c - tc / 2 - g, CR = c + tc / 2 + g;
    const T1 = t + g, M1 = m - t / 2 - g, M2 = m + t / 2 + g, B = H - t - g;
    return {
      a: P([[g, 0], [W - g, 0], [W - t - g, t], [t + g, t]]),
      d: P([[t + g, H - t], [W - t - g, H - t], [W - g, H], [g, H]]),
      f: P([[0, g], [t, t + g], [t, m - t / 2 - g], [t / 2, m - g], [0, m - t / 2 - g]]),
      e: P([[0, H - g], [t, H - t - g], [t, m + t / 2 + g], [t / 2, m + g], [0, m + t / 2 + g]]),
      b: P([[W, g], [W - t, t + g], [W - t, m - t / 2 - g], [W - t / 2, m - g], [W, m - t / 2 - g]]),
      c: P([[W, H - g], [W - t, H - t - g], [W - t, m + t / 2 + g], [W - t / 2, m + g], [W, m + t / 2 + g]]),
      g1: P([[t / 2 + g, m], [t + g, m - t / 2], [c - tc / 2 - g, m - t / 2], [c - g, m], [c - tc / 2 - g, m + t / 2], [t + g, m + t / 2]]),
      g2: P([[W - t / 2 - g, m], [W - t - g, m - t / 2], [c + tc / 2 + g, m - t / 2], [c + g, m], [c + tc / 2 + g, m + t / 2], [W - t - g, m + t / 2]]),
      i: P([[c - tc / 2, t + g], [c + tc / 2, t + g], [c + tc / 2, m - t / 2 - g], [c, m - g], [c - tc / 2, m - t / 2 - g]]),
      l: P([[c - tc / 2, H - t - g], [c + tc / 2, H - t - g], [c + tc / 2, m + t / 2 + g], [c, m + g], [c - tc / 2, m + t / 2 + g]]),
      h: quad(L, T1, CL, M1),
      j: quad(R, T1, CR, M1),
      k: quad(L, B, CL, M2),
      m: quad(R, B, CR, M2),
    };
  }

  const cache = {};
  function segmentsFor(o) {
    const key = [o.W, o.H, o.t, o.g].join();
    return cache[key] || (cache[key] = segments(o.W, o.H, o.t, o.g));
  }

  /* Draws `text` into `svg`; `ghost` also draws the unlit segments (class "off"). */
  function draw(svg, text, o, ghost) {
    const segs = segmentsFor(o);
    const chars = [...String(text).toUpperCase()];
    let out = "", x = 0;
    for (const ch of chars) {
      if (ch === ":") {          // colon: two small squares, narrow advance
        const d = o.t * 1.05;
        out += `<rect class="on" x="${x}" y="${o.H * 0.3 - d / 2}" width="${d}" height="${d}"/>`;
        out += `<rect class="on" x="${x}" y="${o.H * 0.7 - d / 2}" width="${d}" height="${d}"/>`;
        x += d + o.gap;
        continue;
      }
      if (ch === ".") {          // decimal point: a small square on the baseline, narrow advance
        const d = o.t * 1.15;
        out += `<rect class="on" x="${x - o.gap * 0.5}" y="${o.H - d}" width="${d}" height="${d}"/>`;
        x += d + o.gap * 0.2;
        continue;
      }
      const on = (GLYPHS[ch] || "").split(" ");
      out += `<g transform="translate(${x} 0)">`;
      for (const [name, pts] of Object.entries(segs)) {
        if (on.includes(name)) out += `<polygon class="on" points="${pts}"/>`;
        else if (ghost) out += `<polygon class="off" points="${pts}"/>`;
      }
      out += "</g>";
      x += o.W + o.gap;
    }
    const pad = 10, w = Math.max(o.W, x - o.gap) + 2 * pad, h = o.H + 2 * pad;
    svg.setAttribute("viewBox", `${-pad} ${-pad} ${w} ${h}`);
    svg.style.aspectRatio = `${w} / ${h}`;
    svg.innerHTML = out;
  }

  window.Seg14 = { GLYPHS, DIGIT, LABEL, segments, draw };

  if (window.RD) {
    RD.widgetInits.push([".rd-seg", (svg) => {
      const field = svg.dataset.field || "gear";
      const fmt = RD.formats[svg.dataset.fmt || "text"] || RD.formats.text;
      const ghost = svg.dataset.ghost === "1";
      let last = null;
      const update = (f) => {
        const text = fmt(f[field], f);
        if (text !== last) { draw(svg, text, DIGIT, ghost); last = text; }
      };
      update({});
      RD.listeners.push(update);
    }]);
    RD.widgetInits.push([".rd-seg-text", (svg) => draw(svg, svg.dataset.text || "", LABEL, false)]);
  }
})();
