/* Dash box: the cards of the iPad page, built from the active game's dash map (games/<id>/dash.toml,
 * served in /api/info as "dash"). Needs rd.js and seg14.js.
 *
 *   stepper  big value, level dots (range from the game: frame.limits), - / + buttons
 *   bias     brake bias % front with a front / rear bar; holding a button repeats
 *   toggle   a lamp that shows the state; a button when the card has an action
 *   pair     two values side by side, shown only
 *
 * Every value comes from the game, so the card shows what the game applied. After a press the card
 * is "pending" until the value changes (or 1.2 s pass). A card whose value the car does not have is
 * greyed out ("NOT ON THIS CAR"); while there is an error all cards show "-" and do not take presses.
 */
(function () {
  "use strict";

  const PENDING_MS = 1200;
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

  /* A button that sends an action; with repeat it keeps sending while held. */
  function actionButton(html, action, enabled, card, repeat) {
    const b = el("button", "btn", html);
    b.dataset.action = action;
    b._enabled = enabled;
    let timer = null;
    const stop = () => { clearTimeout(timer); clearInterval(timer); timer = null; b.classList.remove("pressed"); };
    b.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      if (b.disabled) return;
      b.classList.add("pressed");
      try { b.setPointerCapture(e.pointerId); } catch (err) { /* pointer already gone */ }
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
    card._pendingSince = 0;
    card._pendingValue = undefined;
    card.press = (action) => {
      card._pendingSince = performance.now();
      card._pendingValue = card._value;
      card.classList.add("pending");
      RD.command(action);
    };
    card.settle = (value) => {
      card._value = value;
      if (card._pendingSince && (value !== card._pendingValue || performance.now() - card._pendingSince > PENDING_MS)) {
        card._pendingSince = 0;
        card.classList.remove("pending");
      }
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
      card.settle(v);
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

  const TYPES = { stepper, bias, pair, toggle };

  RD.dashbox = function (grid) {
    RD.loadInfo().then((info) => {
      const cards = (info.dash || []).filter((def) => TYPES[def.type]).map((def) => TYPES[def.type](def));
      cards.forEach((card) => grid.appendChild(card));
      grid.dataset.count = cards.length;
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
