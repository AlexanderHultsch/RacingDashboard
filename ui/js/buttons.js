/* Button groups: tabs plus a grid of .rd-btn buttons, built from the bridge's /api/info.
 *
 * RD.buttons(tabsElement, gridElement)
 *   - one tab per group (AIDS, CAR, VIEW, PIT); the chosen tab is remembered on this device
 *   - "tap" buttons send one keypress per touch, "hold" buttons hold the key while touched,
 *     "latch" buttons (a per-game kind) press the key on one tap and let it go on the next
 *   - a button with a telemetry field shows its live value and lights up while it is on
 *   - a button without a key for the active game is greyed out
 */
(function () {
  "use strict";

  // telemetry field -> [format, is "on"]
  const FIELDS = {
    tc_level: ["level", () => false],
    abs_level: ["level", () => false],
    brake_bias: ["bias", () => false],
    engine_map: ["level", () => false],
    pit_limiter: ["onoff", (v) => !!v],
    lights: ["level", (v) => v > 0],
    wipers: ["level", (v) => v > 0],
    ignition: ["onoff", (v) => !!v],
    engine_running: ["running", (v) => !!v],
    gear: ["gear", () => false],
  };
  RD.formats.running = (v) => (v === null || v === undefined ? "-" : v ? "RUNNING" : "OFF");

  function makeButton(def) {
    const b = document.createElement("button");
    b.className = "rd-btn" + (def.type === "hold" ? " hold" : "");
    b.disabled = !def.enabled;
    b.innerHTML = "<span class='label'></span><span class='val'></span>";
    b.querySelector(".label").textContent = def.label;
    const val = b.querySelector(".val");
    // a "latch" button is on while the bridge holds its key down (frame.latched)
    const latch = def.type === "latch";
    if ((def.field && FIELDS[def.field]) || latch) {
      const [fmt, isOn] = FIELDS[def.field] || ["text", () => false];
      let last;
      RD.listeners.push((f) => {
        const held = latch && (f.latched || []).includes(def.action);
        const missing = f[def.field] === null || f[def.field] === undefined;
        const text = latch && missing ? (held ? "ON" : "OFF") : def.field ? RD.formats[fmt](f[def.field], f) : "";
        if (text !== last) { val.textContent = text; last = text; }
        b.classList.toggle("on", held || (!!def.field && isOn(f[def.field])));
      });
    }
    let down = false;
    const press = (e) => {
      e.preventDefault();
      if (b.disabled || down) return;
      down = true;
      b.classList.add("pressed");
      try { b.setPointerCapture(e.pointerId); } catch (err) { /* pointer already gone */ }
      RD.command(def.action, def.type === "hold" ? "down" : "tap");
    };
    const release = () => {
      if (!down) return;
      down = false;
      b.classList.remove("pressed");
      if (def.type === "hold") RD.command(def.action, "up");
    };
    b.addEventListener("pointerdown", press);
    b.addEventListener("pointerup", release);
    b.addEventListener("pointercancel", release);
    b.addEventListener("lostpointercapture", release);
    b.addEventListener("contextmenu", (e) => e.preventDefault());
    return b;
  }

  RD.buttons = function (tabs, grid) {
    RD.loadInfo().then((info) => {
      const groups = info.groups;
      let current = RD.store.get("tab", groups[0].name);
      if (!groups.some((g) => g.name === current)) current = groups[0].name;
      const panels = {};
      groups.forEach((group) => {
        const tab = document.createElement("button");
        tab.className = "tab";
        tab.textContent = group.name;
        tab.addEventListener("click", () => show(group.name));
        tabs.appendChild(tab);
        const panel = document.createElement("div");
        panel.className = "panel";
        panel.dataset.count = group.buttons.length;
        group.buttons.forEach((def) => panel.appendChild(makeButton(def)));
        grid.appendChild(panel);
        panels[group.name] = [tab, panel];
      });
      function show(name) {
        for (const [key, [tab, panel]] of Object.entries(panels)) {
          tab.classList.toggle("active", key === name);
          panel.hidden = key !== name;
        }
        RD.store.set("tab", name);
      }
      show(current);
    }).catch(() => RD.toast("no connection to the PC"));
  };
})();
