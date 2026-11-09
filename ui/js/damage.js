/* Damage page (damage.html): the car from above, coloured by damage. Load after rd.js.
 *
 *   <div class="rd-damage"></div>
 *
 * Fields (core/telemetry.py): damage_body [front, rear, left, right, centre] and damage_suspension [front left,
 * front right, rear left, rear right], 0 = none .. 1 = heavy; null = the game sends no damage (the chip says so).
 * Colours: grey without damage, then yellow (a scratch) - orange - red (1.0), mixed in between.
 */
(function () {
  "use strict";

  const STOPS = [[0, [184, 190, 198]], [0.04, [230, 198, 25]], [0.5, [240, 138, 28]], [1, [229, 65, 47]]];
  function colour(v) {
    if (typeof v !== "number" || !isFinite(v)) return "#2a313a";
    if (v <= 0) return `rgb(${STOPS[0][1].join(",")})`;
    for (let i = 1; i < STOPS.length; i++) {
      if (v <= STOPS[i][0]) {
        const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i], k = (v - a) / (b - a);
        return `rgb(${ca.map((c, j) => Math.round(c + (cb[j] - c) * k)).join(",")})`;
      }
    }
    return `rgb(${STOPS[STOPS.length - 1][1].join(",")})`;
  }

  // the car from above like the ACE HUD, 160 x 230: the body (centre) with the nose (front), the tail and rear
  // arches (rear) and the flanks (left / right) clipped to its outline, dark windows, and a small shock absorber
  // symbol beside each wheel (suspension)
  const BODY = "M80 10 C100 10 114 14 120 26 C124 34 126 42 126 52 L126 72 C126 80 121 88 120 96 L119 136 " +
               "C120 144 126 148 126 158 L126 184 C126 200 118 210 102 214 C94 216 88 216 80 216 C72 216 66 216 58 214 " +
               "C42 210 34 200 34 184 L34 158 C34 148 40 144 41 136 L40 96 C39 88 34 80 34 72 L34 52 C34 42 36 34 40 26 " +
               "C46 14 60 10 80 10 Z";
  const shock = (x, y, wheel) =>
    `<g class="shock" data-wheel="${wheel}" transform="translate(${x} ${y})">` +
    `<rect class="body" x="-4" y="0" width="8" height="26" rx="4"/>` +
    `<path class="coil" d="M-4 7 H4 M-4 11 H4 M-4 15 H4 M-4 19 H4"/></g>`;
  const SVG = `
    <svg class="damage-car" viewBox="0 0 160 230" aria-hidden="true">
      <defs>
        <clipPath id="dmg-body"><path d="${BODY}"/></clipPath>
        <clipPath id="dmg-front"><rect x="0" y="0" width="160" height="42"/></clipPath>
        <clipPath id="dmg-rear"><rect x="0" y="146" width="160" height="84"/></clipPath>
        <clipPath id="dmg-left"><rect x="0" y="42" width="80" height="104"/></clipPath>
        <clipPath id="dmg-right"><rect x="80" y="42" width="80" height="104"/></clipPath>
      </defs>
      <path class="zone fill" data-zone="4" d="${BODY}"/>
      <g clip-path="url(#dmg-body)">
        <path class="divide band" d="${BODY}"/>
        <g clip-path="url(#dmg-front)"><path class="zone edge" data-zone="0" d="${BODY}"/></g>
        <g clip-path="url(#dmg-rear)"><path class="zone edge" data-zone="1" d="${BODY}"/></g>
        <g clip-path="url(#dmg-left)"><path class="zone edge" data-zone="2" d="${BODY}"/></g>
        <g clip-path="url(#dmg-right)"><path class="zone edge" data-zone="3" d="${BODY}"/></g>
        <path class="divide" d="M28 42 H45 M115 42 H132 M28 146 H45.5 M114.5 146 H132"/>
      </g>
      <path class="glass" d="M50 66 C62 58 98 58 110 66 L102 98 C90 94 70 94 58 98 Z"/>
      <path class="glass" d="M45 104 L52 101 L52 152 L45 146 Z"/><path class="glass" d="M115 104 L108 101 L108 152 L115 146 Z"/>
      <path class="glass" d="M58 164 C70 168 90 168 102 164 L107 184 C92 189 68 189 53 184 Z"/>
      <path class="mirror" d="M34 80 L24 76 L24 84 Z"/><path class="mirror" d="M126 80 L136 76 L136 84 Z"/>
      <path class="outline" d="${BODY}"/>
      ${shock(12, 48, 0)}${shock(148, 48, 1)}${shock(12, 158, 2)}${shock(148, 158, 3)}
    </svg>`;

  let gameName = "", noDamage = false;
  RD.loadInfo().then((info) => { gameName = (info.game_name || "").toUpperCase(); }).catch(() => {});
  RD.notices.push((f) => (noDamage ? (gameName || "THIS GAME") + " SENDS NO DAMAGE" : null));

  RD.widgetInits.push([".rd-damage", (el) => {
    el.innerHTML = SVG;
    const zones = [...el.querySelectorAll(".zone")], springs = [...el.querySelectorAll(".shock .body")];
    const shown = new Map();
    const set = (node, prop, value) => { if (shown.get(node) !== value) { shown.set(node, value); node.style[prop] = value; } };
    function update(f) {
      const error = RD.errorOf(f);
      const body = Array.isArray(f.damage_body) ? f.damage_body : null;
      const susp = Array.isArray(f.damage_suspension) ? f.damage_suspension : null;
      noDamage = !error && !body && !susp;
      el.classList.toggle("off", !!error || noDamage);
      zones.forEach((z) => set(z, z.classList.contains("edge") ? "stroke" : "fill", colour(error || !body ? null : body[+z.dataset.zone])));
      springs.forEach((s) => set(s, "fill", colour(error || !susp ? null : susp[+s.parentNode.dataset.wheel])));
    }
    update({});
    RD.listeners.push(update);
  }]);
})();
