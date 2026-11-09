/* Tyres page (tyres.html): the DASH TYRES card on its own. Load after rd.js.
 *
 *   <div class="rd-tyres"></div>
 *
 * The fields come from the game's tyres card in its dash map (/api/info), so every game shows what its DASH shows;
 * the view is RD.tyreView (rd.js), the same as on the DASH. A game without a tyres card leaves the tyres dim and
 * the chip says "<GAME> SENDS NO TYRE DATA".
 */
(function () {
  "use strict";

  let gameName = "", hasCard = true;
  RD.notices.push(() => (hasCard ? null : (gameName || "THIS GAME") + " SENDS NO TYRE DATA"));

  RD.widgetInits.push([".rd-tyres", (el) => {
    let view = null;
    RD.loadInfo().then((info) => {
      gameName = (info.game_name || "").toUpperCase();
      const def = (info.dash || []).find((c) => c.type === "tyres");
      hasCard = !!def;
      view = RD.tyreView(def || {});
      el.replaceChildren(view.body);
    }).catch(() => {});

    function update(f) {
      const error = RD.errorOf(f);
      const missing = view ? view.update(f, error) : true;
      el.classList.toggle("off", !!error || missing);
    }

    RD.listeners.push(update);
  }]);
})();
