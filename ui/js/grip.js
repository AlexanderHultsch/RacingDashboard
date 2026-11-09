/* Grip page (grip.html): the slip of each wheel as a coloured tile, and the ABS / TC settings. Load after rd.js.
 *
 *   <div class="rd-grip"> with four .grip-tyre (data-wheel 0..3: front left, front right, rear left, rear right)
 *   and two .grip-aid (data-field abs_level / tc_level, a .n name and a .v value) </div>
 *
 * Fields (core/telemetry.py): wheel_slip (slip ratio per wheel: negative braking, -1 locked; positive wheelspin;
 * null = the game sends none), wheel_lock (the game's own lock flag per wheel, or null), speed_kmh,
 * abs_level, tc_level.
 * A tyre gets stage 1..4 from its slip (STAGES: the share of the slip ratio from which each stage starts, the
 * same for every car; stage 4 also when the game says the wheel is locked) and the class l1..l4 (braking: the
 * wheel turns slower than the car) or s1..s4 (wheelspin); stage 4 flashes (the CSS). No colour below
 * MIN_KMH (a standing car's slip means nothing), none on an error.
 * ABS / TC show the setting (0 = OFF), a grey "–" when the car does not have it, and are hidden when the game
 * does not report the setting at all (its dash box has no card for it, /api/info).
 */
(function () {
  "use strict";

  const STAGES = [0.06, 0.12, 0.25, 0.5];   // to be checked in a test drive (docs/SPEC.md, GRIP)
  const MIN_KMH = 10;

  RD.gripStage = function (slip, locked) {
    if (typeof slip !== "number" || !isFinite(slip)) return "";
    const size = Math.abs(slip);
    const stage = STAGES.filter((limit) => size >= limit).length;
    if (locked) return "l4";
    return stage ? (slip < 0 ? "l" : "s") + stage : "";
  };

  let gameName = "";
  RD.notices.push((f) => (f.wheel_slip == null ? (gameName || "THIS GAME") + " SENDS NO WHEEL SLIP" : null));

  RD.widgetInits.push([".rd-grip", (el) => {
    const tyres = [...el.querySelectorAll(".grip-tyre")];
    const aids = [...el.querySelectorAll(".grip-aid")];
    const shown = new Set();
    RD.loadInfo().then((info) => {
      gameName = (info.game_name || "").toUpperCase();
      for (const card of info.dash || []) for (const key of ["field", "active"]) if (card[key]) shown.add(card[key]);
      aids.forEach((aid) => aid.classList.toggle("hide", !shown.has(aid.dataset.field)));
    }).catch(() => {});
    aids.forEach((aid) => aid.classList.add("hide"));      // until the game's dash map says it has the setting

    const last = ["", "", "", ""];
    function update(f) {
      const error = RD.errorOf(f);
      const slips = Array.isArray(f.wheel_slip) ? f.wheel_slip : null;
      const locks = Array.isArray(f.wheel_lock) ? f.wheel_lock : [];
      const moving = (f.speed_kmh || 0) >= MIN_KMH;
      el.classList.toggle("off", !!error || !slips);
      tyres.forEach((tyre, i) => {
        const cls = !error && slips && moving ? RD.gripStage(slips[i], locks[i] === true) : "";
        if (cls === last[i]) return;
        if (last[i]) tyre.classList.remove(last[i]);
        if (cls) tyre.classList.add(cls);
        last[i] = cls;
      });
      aids.forEach((aid) => {
        const v = error ? null : f[aid.dataset.field];
        const text = v === null || v === undefined ? "–" : v === 0 ? "OFF" : String(v);
        const value = aid.querySelector(".v");
        if (value.textContent !== text) value.textContent = text;
        aid.classList.toggle("na", text === "–");
      });
    }

    update({});
    RD.listeners.push(update);
  }]);
})();
