/* Startup page (startup.html): an IGN button and an ENGINE START STOP button. Load after rd.js.
 *
 *   <div class="rd-startup"> with a button data-role="ignition" and a button data-role="starter" </div>
 *
 * The buttons send the same actions as the DASH ignition card, taken from the game's dash map (/api/info):
 * the card with the ignition action (ACE, demo: type "ignition" with its starter; ACR, iRacing: push cards
 * "ignition" and "starter"). A "hold" action is pressed while the finger is on the button and released after,
 * a "tap" action is one keypress. A button without a key (or a game without the action) does nothing.
 * State, by light only (owner): the ignition field of that card (else "ignition") lights IGN amber, START
 * red (ready); the running field (else "engine_running") lights START green. While the engine runs START does
 * nothing (as on the DASH); on an error both rings are dark and the buttons take no presses.
 */
(function () {
  "use strict";

  RD.widgetInits.push([".rd-startup", (el) => {
    const buttons = { ignition: el.querySelector('[data-role="ignition"]'), starter: el.querySelector('[data-role="starter"]') };
    const action = { ignition: null, starter: null };   // name, kind and whether a key is set, from the dash map
    let fields = { on: "ignition", running: "engine_running" };
    let usable = false, running = false;

    RD.loadInfo().then((info) => {
      const cards = info.dash || [];
      const find = (name) => cards.find((c) => c.action === name || c.starter === name);
      for (const role of ["ignition", "starter"]) {
        const card = find(role);
        if (card) action[role] = { name: role, kind: (card.kinds || {})[role] || "tap", enabled: !!(card.enabled || {})[role] };
      }
      const ign = cards.find((c) => c.type === "ignition");
      if (ign) fields = { on: ign.field || "ignition", running: ign.running || "engine_running" };
      refresh();
    }).catch(() => {});

    function refresh() {
      for (const role of ["ignition", "starter"]) {
        const a = action[role];
        const blocked = !usable || !a || !a.enabled || (role === "starter" && running);
        buttons[role].classList.toggle("na", !a || !a.enabled);
        buttons[role].dataset.blocked = blocked ? "1" : "";
      }
    }

    for (const role of ["ignition", "starter"]) {
      const b = buttons[role];
      let held = false;
      const stop = () => {
        b.classList.remove("pressed");
        if (held) { held = false; RD.command(action[role].name, "up"); }
      };
      b.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        b.classList.add("pressed");
        try { b.setPointerCapture(e.pointerId); } catch (err) { /* pointer already gone */ }
        const a = action[role];
        if (held || b.dataset.blocked || !a) return;
        if (a.kind === "hold") { held = true; RD.command(a.name, "down"); } else RD.command(a.name, "tap");
      });
      ["pointerup", "pointercancel", "lostpointercapture"].forEach((n) => b.addEventListener(n, stop));
      b.addEventListener("contextmenu", (e) => e.preventDefault());
    }

    let last = null;
    function update(f) {
      const error = RD.errorOf(f);
      usable = !error;
      running = !error && f[fields.running] === true;
      const on = !error && (f[fields.on] === true || running);
      const state = running ? "run" : on ? "on" : "off";
      if (state !== last) {
        el.classList.remove("s-" + last);
        el.classList.add("s-" + state);
        last = state;
      }
      refresh();
    }

    update({});
    RD.listeners.push(update);
  }]);
})();
