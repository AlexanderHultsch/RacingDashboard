/* Dash box: the cards of the iPad page, built from the active game's dash map (games/<id>/dash.toml,
 * served in /api/info as "dash"). Needs rd.js and seg14.js.
 *
 *   stepper  big value, level dots (range from the game: frame.limits), - / + buttons
 *   bias     brake bias % front with a front / rear bar; holding a button repeats
 *   toggle   a lamp that shows the state; a button when the card has an action
 *   pair     two values side by side, shown only
 *   fuel     litres with a tank bar and laps left
 *   lamps    warning lamps as icons, state only: off (grey), cold (blue), warn (yellow), alert (red)
 *   cycle    a stage setting (lights, wipers): the lamp steps to the next stage, optional extra button
 *   ignition ignition lamp (OFF / ON / RUNNING) that toggles the ignition, and a START button (held)
 *   value    a value in segments (fmt lap / pct / speed / int), optional bar for a 0..1 share
 *   push     a big button without a state; confirm_ms: hold that long before it fires
 *
 * Every value comes from the game, so the card shows what the game applied. A card lights up ("lit")
 * when it is pressed (until the new value arrives) and whenever its value changes in the game, so a
 * change made in the car looks the same as one made on the tablet. A stepper with an "active" field
 * shows amber digits while the system works (TC cutting, ABS braking). A card whose value the car does
 * not have is greyed out ("NOT ON THIS CAR"); while there is an error all cards show "-" and take no presses.
 */
(function () {
  "use strict";

  const PENDING_MS = 1200;       // a press lights the card at most this long while waiting for the game
  const LIT_MS = 700;            // a changed value keeps the card lit this long
  const REPEAT_DELAY = 400;
  const REPEAT_EVERY = 160;

  const el = (tag, cls, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  };
  const isNone = (v) => v === null || v === undefined;

  function segSvg(cls) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "seg " + (cls || ""));
    return svg;
  }

  function drawSeg(svg, text) {
    if (svg._text === text) return;
    svg._text = text;
    Seg14.draw(svg, text, Seg14.DIGIT);
  }

  /* A button that sends an action. repeat: keeps sending taps while held (brake bias).
     A "hold" action (def.kinds) is pressed while the finger is on the button and released after. */
  function actionButton(html, action, enabled, card, repeat, def) {
    const b = el("button", "btn", html);
    b.dataset.action = action;
    b._enabled = enabled;
    const hold = !!def && (def.kinds || {})[action] === "hold";
    let timer = null, held = false;
    const stop = () => {
      clearTimeout(timer); clearInterval(timer); timer = null;
      b.classList.remove("pressed");
      if (held) { held = false; RD.command(action, "up"); }
    };
    b.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      if (b.disabled || held) return;
      b.classList.add("pressed");
      try { b.setPointerCapture(e.pointerId); } catch (err) { /* pointer already gone */ }
      if (hold) { held = true; card.press(action, "down"); return; }
      card.press(action);
      if (repeat) timer = setTimeout(() => { timer = setInterval(() => card.press(action), REPEAT_EVERY); }, REPEAT_DELAY);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach((n) => b.addEventListener(n, stop));
    b.addEventListener("contextmenu", (e) => e.preventDefault());
    return b;
  }

  function baseCard(def, kind) {
    const card = el("section", "card " + kind);
    card.appendChild(el("header", "top", `<span class="lab"></span><span class="rng"></span>`));
    card.querySelector(".lab").textContent = def.label;
    let litTimer = null, seen = false, last;
    const light = (ms) => {
      card.classList.add("lit");
      clearTimeout(litTimer);
      litTimer = setTimeout(() => card.classList.remove("lit"), ms);
    };
    card.press = (action, state) => {
      light(PENDING_MS);
      RD.command(action, state || "tap");
    };
    // called with the card's current value on every frame: a change lights the card
    card.settle = (value) => {
      const key = JSON.stringify(value === undefined ? null : value);
      if (seen && key !== last) light(LIT_MS);
      seen = true;
      last = key;
    };
    if (def.hint) card.appendChild(el("footer", "hint")).textContent = def.hint;
    return card;
  }

  function setState(card, error, missing) {
    card.classList.toggle("off", !!error);
    card.classList.toggle("na", !error && missing);
  }

  function setButtons(card, usable) {
    card.querySelectorAll(".btn").forEach((b) => { b.disabled = !usable || !b._enabled; });
  }

  /* ------------------------------------------------------------ card types */

  function stepper(def) {
    const card = baseCard(def, "stepper");
    const val = el("div", "val");
    const svg = segSvg();
    val.appendChild(svg);
    const pips = el("div", "pips");
    const btns = el("div", "btns");
    const down = actionButton("−", def.down, def.enabled[def.down], card, false);
    const up = actionButton("+", def.up, def.enabled[def.up], card, false);
    btns.append(down, up);
    card.insertBefore(btns, card.querySelector(".hint"));
    card.insertBefore(pips, btns);
    card.insertBefore(val, pips);
    let rangeKey = "";
    card.update = (f, error) => {
      const v = f[def.field];
      const missing = isNone(v);
      setState(card, error, missing);
      card.settle(v);
      drawSeg(svg, error || missing ? "-" : String(v));
      const range = (f.limits || {})[def.field];
      const key = range ? range.join("-") : "";
      if (key !== rangeKey) {
        rangeKey = key;
        card.querySelector(".rng").textContent = range ? `${range[0]}–${range[1]}` : "";
        pips.innerHTML = "";
        if (range && range[1] - range[0] <= 24) {
          const count = range[0] === 0 ? range[1] : range[1] - range[0] + 1;
          for (let i = 0; i < count; i++) pips.appendChild(el("i"));
        }
      }
      const lit = error || missing || !range ? 0 : range[0] === 0 ? v : v - range[0] + 1;
      [...pips.children].forEach((pip, i) => pip.classList.toggle("on", i < lit));
      card.classList.toggle("active", !!def.active && !error && !missing && !!f[def.active]);
      setButtons(card, !error && !missing);
      if (range && !error && !missing) {
        if (v <= range[0]) down.disabled = true;
        if (v >= range[1]) up.disabled = true;
      }
    };
    return card;
  }

  function bias(def) {
    const card = baseCard(def, "bias");
    card.querySelector(".rng").textContent = "% FRONT";
    const body = el("div", "bias-body");
    const svg = segSvg("bias-num");
    const bar = el("div", "split", "<b></b>");
    const ends = el("div", "ends", "<span>FRONT</span><span>REAR</span>");
    body.append(svg, bar, ends);
    const btns = el("div", "btns");
    btns.append(actionButton("<small>◀ FRONT</small>", def.front, def.enabled[def.front], card, true),
                actionButton("<small>REAR ▶</small>", def.rear, def.enabled[def.rear], card, true));
    card.insertBefore(btns, card.querySelector(".hint"));
    card.insertBefore(body, btns);
    card.update = (f, error) => {
      const v = f[def.field];
      const missing = isNone(v);
      setState(card, error, missing);
      card.settle(missing ? null : (v * 100).toFixed(1));      // compare what is shown, not float noise
      drawSeg(svg, error || missing ? "-" : (v * 100).toFixed(1));
      bar.firstChild.style.width = error || missing ? "0" : `${Math.max(0, Math.min(100, v * 100))}%`;
      setButtons(card, !error && !missing);
    };
    return card;
  }

  function pair(def) {
    const card = baseCard(def, "pair");
    const body = el("div", "two");
    const svgs = def.fields.map((field, i) => {
      const cell = el("div", "cell");
      const svg = segSvg();
      cell.appendChild(svg);
      cell.appendChild(el("small")).textContent = (def.labels || [])[i] || field;
      body.appendChild(cell);
      return svg;
    });
    card.insertBefore(body, card.querySelector(".hint"));
    card.update = (f, error) => {
      const values = def.fields.map((field) => f[field]);
      const missing = values.every(isNone);
      setState(card, error, missing);
      if (!error) card.settle(values);
      values.forEach((v, i) => drawSeg(svgs[i], error || isNone(v) ? "-" : String(v)));
    };
    return card;
  }

  function toggle(def) {
    const card = baseCard(def, "toggle " + (def.style || "amber"));
    let lamp;
    if (def.action) {
      lamp = actionButton("", def.action, def.enabled[def.action], card, false);
      lamp.classList.add("lamp");
    } else {
      lamp = el("div", "lamp");
    }
    card.insertBefore(lamp, card.querySelector(".hint"));
    card.update = (f, error) => {
      const v = f[def.field];
      const missing = isNone(v);
      setState(card, error, missing);
      card.settle(v);
      const on = !error && !missing && !!v;
      lamp.classList.toggle("on", on);
      const text = error || missing ? "–" : on ? def.on || "ON" : def.off || "OFF";
      if (lamp.textContent !== text) lamp.textContent = text;
      if (def.action) setButtons(card, !error && !missing);
    };
    return card;
  }

  function fuel(def) {
    const card = baseCard(def, "fuel");
    card.querySelector(".rng").textContent = "LITRES";
    const body = el("div", "fuel-body");
    const svg = segSvg("fuel-num");
    const tank = el("div", "tank", "<b></b>");
    const sub = el("div", "sub");
    body.append(svg, tank, sub);
    card.insertBefore(body, card.querySelector(".hint"));
    card.update = (f, error) => {
      const litres = f[def.field], max = def.max ? f[def.max] : null, perLap = def.per_lap ? f[def.per_lap] : null;
      const missing = isNone(litres);
      setState(card, error, missing);
      const ok = !error && !missing;
      drawSeg(svg, ok ? litres.toFixed(1) : "-");
      const share = ok && max ? Math.max(0, Math.min(1, litres / max)) : 0;
      tank.firstChild.style.width = `${share * 100}%`;
      tank.classList.toggle("low", ok && !!max && share < 0.15);
      tank.classList.toggle("empty", ok && !!max && share < 0.07);
      const text = !ok ? "" : perLap > 0 ? `\u2248 ${(litres / perLap).toFixed(1)} LAPS` : max ? `OF ${Math.round(max)} L` : "";
      if (sub.textContent !== text) sub.textContent = text;
    };
    return card;
  }

  /* warning lamp icons (inline SVG, 24 x 24, drawn in currentColor) */
  const ICONS = {
    brake: '<circle cx="12" cy="12" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8"/>' +
      '<path d="M12 8.4v4.6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="15.6" r="1.2" fill="currentColor"/>' +
      '<path d="M5.2 6.6a8.6 8.6 0 0 0 0 10.8M18.8 6.6a8.6 8.6 0 0 1 0 10.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    engine: '<path d="M3 11v5M3 13.5h2.2M5.2 10.2h2.3V8.4h3V6.8h4.6v1.6h2.1l2 2.3h1.6v6.8h-1.6l-2 2.1H9.3l-1.8-2.1H5.2z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>',
    oil: '<path d="M2.8 10.2l3 1.2 1.6-1.8h6.3l5.5-2.2 1 .9-6.2 6.9H7.4l-1.6-1.9H2.8z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>' +
      '<path d="M10 9.6V8.1M8.6 8.1h2.8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>' +
      '<path d="M20.4 14.6c.7 1 1.1 1.7 1.1 2.2a1.1 1.1 0 0 1-2.2 0c0-.5.4-1.2 1.1-2.2z" fill="currentColor"/>',
    coolant: '<path d="M12 3.2v9.6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="14.6" r="2.4" fill="currentColor"/>' +
      '<path d="M13.6 5.2h2.2M13.6 7.8h2.2M13.6 10.4h2.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
      '<path d="M3.5 19.4c1.4-1 2.8-1 4.2 0s2.8 1 4.3 0 2.8-1 4.2 0 2.8 1 4.3 0" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  };

  function lamps(def) {
    const card = baseCard(def, "lamps");
    const body = el("div", "lamp-grid");
    const cells = def.fields.map((field, i) => {
      const cell = el("div", "warn s-none", `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[def.icons[i]] || ""}</svg><small></small>`);
      cell.querySelector("small").textContent = (def.labels || [])[i] || "";
      body.appendChild(cell);
      return cell;
    });
    card.insertBefore(body, card.querySelector(".hint"));
    card.update = (f, error) => {
      def.fields.forEach((field, i) => {
        const state = error ? "none" : f[field] || "none";
        const cls = "warn s-" + state;
        if (cells[i].className !== cls) cells[i].className = cls;
      });
      card.classList.toggle("off", !!error);
    };
    return card;
  }

  function cycle(def) {
    const card = baseCard(def, "cycle amber");
    const lamp = actionButton("", def.action, def.enabled[def.action], card, false, def);
    lamp.classList.add("lamp");
    card.insertBefore(lamp, card.querySelector(".hint"));
    let extra = null;
    if (def.extra) {
      extra = actionButton(`<small>${def.extra_label || def.extra.toUpperCase()}</small>`, def.extra, def.enabled[def.extra], card, false, def);
      extra.classList.add("extra");
      card.insertBefore(extra, card.querySelector(".hint"));
    }
    card.update = (f, error) => {
      const v = f[def.field];
      const missing = isNone(v);
      setState(card, error, missing);
      card.settle(v);
      const ok = !error && !missing;
      lamp.classList.toggle("on", ok && v > 0);
      const names = def.names || [];
      const text = !ok ? "\u2013" : names[v] !== undefined ? names[v] : v === 0 ? "OFF" : String(v);
      if (lamp.textContent !== text) lamp.textContent = text;
      setButtons(card, ok);
    };
    return card;
  }

  function ignition(def) {
    const card = baseCard(def, "ignition");
    const lamp = actionButton("", def.action, def.enabled[def.action], card, false, def);
    lamp.classList.add("lamp");
    const start = actionButton("<small>START</small>", def.starter, def.enabled[def.starter], card, false, def);
    start.classList.add("extra");
    card.insertBefore(lamp, card.querySelector(".hint"));
    card.insertBefore(start, card.querySelector(".hint"));
    card.update = (f, error) => {
      const on = f[def.field], running = f[def.running];
      const missing = isNone(on);
      setState(card, error, missing);
      card.settle([on, running]);
      const ok = !error && !missing;
      const state = !ok ? "" : running ? "running" : on ? "on" : "off";
      lamp.classList.toggle("on", state === "on");
      lamp.classList.toggle("run", state === "running");
      const text = { "": "\u2013", off: "OFF", on: "ON", running: "RUNNING" }[state];
      if (lamp.textContent !== text) lamp.textContent = text;
      setButtons(card, ok);
      if (ok && running) start.disabled = true;      // the engine already runs
    };
    return card;
  }

  const VALUE_FORMATS = {
    lap: (v) => RD.formats.lap(v),
    pct: (v) => String(Math.round(v * 100)),
    speed: (v) => RD.formats.speed(v),
    int: (v) => String(Math.round(v)),
  };
  const VALUE_UNITS = { lap: () => "", pct: () => "%", speed: () => RD.formats.speedunit(), int: () => "" };

  function value(def) {
    const fmt = def.fmt || "int";
    const card = baseCard(def, "value");
    const body = el("div", "value-body");
    const svg = segSvg("value-num");
    body.appendChild(svg);
    const bar = def.bar ? el("div", "tank", "<b></b>") : null;
    if (bar) body.appendChild(bar);
    card.insertBefore(body, card.querySelector(".hint"));
    card.update = (f, error) => {
      const v = f[def.field];
      const missing = isNone(v);
      setState(card, error, false);
      card.classList.toggle("empty-value", !error && missing);
      card.querySelector(".rng").textContent = (VALUE_UNITS[fmt] || VALUE_UNITS.int)();
      drawSeg(svg, error || missing ? (fmt === "lap" ? "-:--.---" : "-") : (VALUE_FORMATS[fmt] || VALUE_FORMATS.int)(v));
      if (bar) bar.firstChild.style.width = error || missing ? "0" : `${Math.max(0, Math.min(100, v * 100))}%`;
    };
    return card;
  }

  function push(def) {
    const card = baseCard(def, "push");
    const b = el("button", "btn lamp push-btn", "<span></span><i class=\"fill\"></i>");
    b.querySelector("span").textContent = def.text || def.label;
    b.dataset.action = def.action;
    b._enabled = def.enabled[def.action];
    const confirm = Number(def.confirm_ms || 0);
    let timer = null;
    const cancel = () => { clearTimeout(timer); timer = null; b.classList.remove("pressed", "arming"); };
    b.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      if (b.disabled || timer) return;
      try { b.setPointerCapture(e.pointerId); } catch (err) { /* pointer already gone */ }
      b.classList.add("pressed");
      if (!confirm) { card.press(def.action); return; }
      b.style.setProperty("--confirm", `${confirm}ms`);
      b.classList.add("arming");                      // the fill grows while the finger stays on the button
      timer = setTimeout(() => { timer = null; b.classList.remove("arming"); card.press(def.action); }, confirm);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach((n) => b.addEventListener(n, cancel));
    b.addEventListener("contextmenu", (e) => e.preventDefault());
    card.insertBefore(b, card.querySelector(".hint"));
    card.update = (f, error) => {
      setState(card, error, false);
      b.disabled = !!error || !b._enabled;
    };
    return card;
  }

  const TYPES = { stepper, bias, pair, toggle, fuel, lamps, cycle, ignition, value, push };

  RD.dashbox = function (grid) {
    RD.loadInfo().then((info) => {
      const cards = (info.dash || []).filter((def) => TYPES[def.type]).map((def) => TYPES[def.type](def));
      cards.forEach((card) => grid.appendChild(card));
      grid.dataset.count = cards.length;
      grid.dataset.size = cards.length > 8 ? "large" : cards.length <= 6 ? "small" : "normal";   // 5 / 3 / 4 columns
      if (!cards.length) grid.appendChild(el("p", "empty", "No dash box for this game yet (games/&lt;game&gt;/dash.toml)."));
      const update = (f) => {
        const error = RD.errorOf(f);
        cards.forEach((card) => card.update(f, error));
      };
      update(RD.frame);
      RD.listeners.push(update);
    }).catch(() => RD.toast("no connection to the PC"));
  };
})();
