"use strict";
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
  const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
  const SCENARIO_NAMES = {
    clean: "Correct invoice (no error)", over_billed_qty: "Over-billed quantity", price_mismatch: "Price mismatch",
    unknown_item: "Item not on the PO", missing_po_ref: "Missing PO reference", wrong_po_ref: "Wrong PO reference",
    math_error: "Math / VAT error", not_received: "Billed before delivery", duplicate_invoice: "Duplicate invoice",
    "two errors": "Two errors at once",
  };
  const RENDER_NAMES = { pdf: "Clean PDF", scan: "Office scan", photo: "Phone photo" };

  let DATA = null;
  const state = { set: "holdout", outcome: "", render: "", scenario: "" };

  // ---------- small helpers ----------
  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }
  function text(parent, x, y, str, attrs = {}) {
    const t = el("text", { x, y, ...attrs }, parent);
    t.textContent = str;
    return t;
  }
  function h(tag, props = {}, kids = []) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else n.setAttribute(k, v);
    }
    for (const k of kids) n.appendChild(typeof k === "string" ? document.createTextNode(k) : k);
    return n;
  }
  // bar from a baseline: square at the base, 4px rounded data end
  function hbar(x, y, w, hgt, r = 4) {
    r = Math.min(r, w / 2, hgt / 2);
    if (w <= 0) return "";
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt - r}Q${x + w},${y + hgt} ${x + w - r},${y + hgt}H${x}Z`;
  }
  function vbar(x, base, wdt, hgt, r = 4) {
    r = Math.min(r, wdt / 2, hgt / 2);
    if (hgt <= 0) return "";
    const top = base - hgt;
    return `M${x},${base}V${top + r}Q${x},${top} ${x + r},${top}H${x + wdt - r}Q${x + wdt},${top} ${x + wdt},${top + r}V${base}Z`;
  }
  function legend(container, items, dot = false) {
    container.replaceChildren(...items.map(([name, color]) =>
      h("span", {}, [Object.assign(h("i", { class: dot ? "dotkey" : "" }), { style: `background:${color}` }), name])));
  }

  // ---------- tooltip ----------
  const tip = $("tip");
  function showTip(evt, rows) {
    tip.replaceChildren(...rows.map(([v, k, color]) => {
      const row = h("div");
      row.appendChild(h("div", { class: "v", text: v }));
      if (k) {
        const key = h("div", { class: "k" });
        if (color) key.appendChild(Object.assign(h("i"), { style: `background:${color}` }));
        key.appendChild(document.createTextNode(k));
        row.appendChild(key);
      }
      return row;
    }));
    let x, y;
    if (evt.clientX !== undefined && evt.type !== "focus") { x = evt.clientX; y = evt.clientY; }
    else { const r = evt.target.getBoundingClientRect(); x = r.left + r.width / 2; y = r.top; }
    tip.classList.add("show");
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(window.innerWidth - tw - 8, x + 14)) + "px";
    tip.style.top = Math.max(8, y - th - 12) + "px";
  }
  function hideTip() { tip.classList.remove("show"); }
  function hover(target, group, rows) {
    target.setAttribute("tabindex", "0");
    const on = (e) => { group?.classList.add("dim"); target.dataset.mark && group?.querySelectorAll(`[data-mark="${target.dataset.mark}"]`).forEach((m) => m.classList.add("on")); showTip(e, rows); };
    const off = () => { group?.classList.remove("dim"); group?.querySelectorAll(".on").forEach((m) => m.classList.remove("on")); hideTip(); };
    target.addEventListener("pointermove", on);
    target.addEventListener("pointerleave", off);
    target.addEventListener("focus", on);
    target.addEventListener("blur", off);
  }

  function table(container, head, rows, numCols = []) {
    const t = h("table", { class: "data" });
    t.appendChild(h("thead", {}, [h("tr", {}, head.map((c, i) => h("th", { class: numCols.includes(i) ? "num" : "", text: c })))]));
    t.appendChild(h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c, i) => h("td", { class: numCols.includes(i) ? "num" : "", text: String(c) }))))));
    container.replaceChildren(t);
  }

  // ---------- hero ----------
  function renderHero() {
    const held = DATA.matching.find((m) => m.set === "holdout").metrics;
    const heldInv = DATA.invoices.filter((i) => i.set === "holdout" && !i.api_error);
    const secs = heldInv.map((i) => i.seconds).sort((a, b) => a - b);
    const median = secs[Math.floor(secs.length / 2)];
    $("heroValue").textContent = `${held.review[0]} / ${held.review[1]}`;
    const tiles = [
      ["Planted errors caught", `${held.recall[0]} / ${held.recall[1]}`, "all 8 error types"],
      ["Correct final routing", `${pct(...held.status)}%`, `${held.status[0]} of ${held.status[1]}; the miss was an API timeout`],
      ["Median time per invoice", `${median.toFixed(1)} s`, "read, matched and filed"],
      ["Money decisions made by AI alone", "0", "every check is plain code"],
    ];
    $("tiles").replaceChildren(...tiles.map(([l, v, n]) =>
      h("div", { class: "tile" }, [h("div", { class: "label", text: l }), h("div", { class: "value", text: v }), h("div", { class: "note", text: n })])));
  }

  // ---------- chart 1: reading accuracy (grouped horizontal bars) ----------
  function renderReading() {
    const runs = DATA.extraction;
    const cats = [["All", "All forms"], ["pdf", "Clean PDF"], ["scan", "Office scan"], ["photo", "Phone photo"]];
    legend($("legReading"), runs.map((r, i) => [r.label + (r.set === "holdout" ? " (40)" : " (60)"), SERIES[i]]));
    const box = $("chartReading");
    const W = Math.max(300, box.clientWidth || 480);
    const left = 96, right = 44, barH = 12, gap = 2, groupGap = 18;
    const groupH = runs.length * barH + (runs.length - 1) * gap;
    const H = cats.length * groupH + (cats.length - 1) * groupGap + 30;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H });
    const x = (v) => left + (v / 100) * (W - left - right);
    const g = el("g", {}, svg);
    for (const t of [0, 25, 50, 75, 100]) {
      el("line", { x1: x(t), x2: x(t), y1: 0, y2: H - 22, class: "grid" }, g);
      text(g, x(t), H - 6, t + "%", { "text-anchor": "middle", class: "muted" });
    }
    el("line", { x1: left, x2: left, y1: 0, y2: H - 22, class: "axis" }, g);
    cats.forEach(([key, name], ci) => {
      const y0 = ci * (groupH + groupGap);
      text(g, left - 10, y0 + groupH / 2 + 4, name, { "text-anchor": "end" });
      runs.forEach((r, ri) => {
        const [a, b] = r[key];
        const v = pct(a, b), y = y0 + ri * (barH + gap);
        el("path", { d: hbar(left, y, x(v) - left, barH), fill: SERIES[ri], class: "mark", "data-mark": `${ci}-${ri}` }, g);
        if (key === "All") text(g, x(v) + 6, y + barH - 2, v + "%", { class: ri === runs.length - 1 ? "strong" : "" });
        const hit = el("rect", { x: left, y: y - 1, width: W - left - right + 40, height: barH + 2, class: "hit", "data-mark": `${ci}-${ri}`,
          "aria-label": `${name}, ${r.label}: ${v}%` }, g);
        hover(hit, g, [[`${v}%  (${a}/${b})`, `${r.label} · ${name}`, SERIES[ri]]]);
      });
    });
    box.replaceChildren(svg);
    table($("tableReading"), ["Form", ...runs.map((r) => r.label)],
      cats.map(([k, n]) => [n, ...runs.map((r) => `${pct(...r[k])}% (${r[k][0]}/${r[k][1]})`)]));
    const v1 = runs[0].All, v2 = runs[1].All;
    $("calloutReading").textContent = `Prompt v1 read 10/03/2026 (October 3) as March 10 on 9 invoices. One rule about Philippine dates took it from ${pct(...v1)}% to ${pct(...v2)}%.`;
  }

  // ---------- chart 2: matching (dot plot) ----------
  function renderMatching() {
    const runs = DATA.matching.filter((m) => m.label !== "First version");
    const names = { "After the PO fix": "Tuning, perfect data" };
    const label = (r) => names[r.label] || r.label;
    const metrics = [["review", "Problem invoices sent to review"], ["recall", "Planted errors caught"], ["precision", "Flags that were real"],
      ["clean", "Correct invoices passed"], ["po", "Correct PO found"], ["status", "Correct final routing"]];
    legend($("legMatching"), runs.map((r, i) => [label(r), SERIES[i]]), true);
    const box = $("chartMatching");
    const W = Math.max(300, box.clientWidth || 480);
    const narrow = W < 420;
    const left = narrow ? 130 : 186, right = 50, rowH = 38, lo = 85;
    const top = 20;
    const H = top + metrics.length * rowH + 26;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H });
    const x = (v) => left + ((Math.max(v, lo) - lo) / (100 - lo)) * (W - left - right);
    const g = el("g", {}, svg);
    for (const t of [85, 90, 95, 100]) {
      el("line", { x1: x(t), x2: x(t), y1: top, y2: H - 22, class: "grid" }, g);
      text(g, x(t), H - 6, t + "%", { "text-anchor": "middle", class: "muted" });
    }
    metrics.forEach(([k, name], mi) => {
      const cy = top + mi * rowH + rowH / 2;
      el("line", { x1: left, x2: W - right, y1: cy, y2: cy, class: "grid" }, g);
      const lbl = text(g, left - 10, cy + 4, narrow ? name.replace("Problem invoices sent to review", "Problems to review").replace("Planted errors caught", "Errors caught").replace("Correct invoices passed", "Correct passed").replace("Correct final routing", "Correct routing") : name, { "text-anchor": "end" });
      if (k === "review") lbl.setAttribute("class", "strong");
      runs.forEach((r, ri) => {
        const [a, b] = r.metrics[k], v = pct(a, b);
        const cyi = cy + (ri - 1) * 7;
        el("circle", { cx: x(v), cy: cyi, r: 5.5, fill: SERIES[ri], stroke: "var(--surface-1)", "stroke-width": 2, class: "mark", "data-mark": `${mi}-${ri}` }, g);
        const hit = el("circle", { cx: x(v), cy: cyi, r: 12, class: "hit", "data-mark": `${mi}-${ri}`, "aria-label": `${name}, ${label(r)}: ${v}%` }, g);
        hover(hit, g, [[`${v}%  (${a}/${b})`, `${label(r)} · ${name}`, SERIES[ri]]]);
      });
      // direct label: the held-out value, the one the story is about
      const held = runs[runs.length - 1].metrics[k];
      text(g, W - 4, cy + 4, pct(...held) + "%", { "text-anchor": "end", class: "strong" });
    });
    text(g, W - 4, 12, "held-out", { "text-anchor": "end", class: "muted" });
    box.replaceChildren(svg);
    table($("tableMatching"), ["Metric", ...runs.map(label)],
      metrics.map(([k, n]) => [n, ...runs.map((r) => `${pct(...r.metrics[k])}% (${r.metrics[k][0]}/${r.metrics[k][1]})`)]));
  }

  // ---------- filtered views ----------
  function inSet(i) { return state.set === "all" || i.set === state.set; }
  function filtered() {
    return DATA.invoices.filter((i) => inSet(i)
      && (!state.outcome || (state.outcome === "correct") === i.correct)
      && (!state.render || i.render === state.render)
      && (!state.scenario || i.scenario === state.scenario));
  }

  function renderTypes() {
    const runs = DATA.matching.filter((m) => m.data === "real" && (state.set === "all" || m.set === state.set));
    const types = Object.keys(runs[0].types);
    const sums = types.map((t) => runs.reduce((acc, r) => [acc[0] + r.types[t][0], acc[1] + r.types[t][1]], [0, 0]));
    const total = sums.reduce((a, s) => [a[0] + s[0], a[1] + s[1]], [0, 0]);
    $("typesSub").textContent = `${total[0]} of ${total[1]} caught · ${state.set === "all" ? "both sets" : state.set === "holdout" ? "held-out set" : "tuning set"}, full pipeline`;
    const order = types.map((t, i) => [t, sums[i]]).sort((a, b) => b[1][1] - a[1][1]);
    const box = $("chartTypes");
    const W = Math.max(300, box.clientWidth || 480);
    const left = 158, right = 52, barH = 14, rowH = 30;
    const H = order.length * rowH + 6;
    const max = Math.max(...order.map(([, s]) => s[1]));
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H });
    const x = (v) => left + (v / max) * (W - left - right);
    const g = el("g", {}, svg);
    el("line", { x1: left, x2: left, y1: 0, y2: H, class: "axis" }, g);
    order.forEach(([t, [c, p]], i) => {
      const y = i * rowH + (rowH - barH) / 2;
      const name = SCENARIO_NAMES[t];
      text(g, left - 10, y + barH - 3, name, { "text-anchor": "end" });
      el("path", { d: hbar(left, y, x(p) - left, barH), fill: "var(--track)", class: "mark", "data-mark": t }, g);
      if (c) el("path", { d: hbar(left, y, x(c) - left, barH, c === p ? 4 : 0), fill: "var(--series-1)", class: "mark", "data-mark": t }, g);
      text(g, x(p) + 6, y + barH - 3, `${c}/${p}`, { class: c < p ? "strong" : "" });
      const hit = el("rect", { x: 0, y: i * rowH, width: W, height: rowH, class: "hit", "data-mark": t, "aria-label": `${name}: ${c} of ${p} caught` }, g);
      hover(hit, g, [[`${c} of ${p} caught`, name, "var(--series-1)"]].concat(c < p ? [[`${p - c} missed`, "after an API timeout", null]] : []));
    });
    box.replaceChildren(svg);
    table($("tableTypes"), ["Error type", "Caught", "Planted"], order.map(([t, [c, p]]) => [SCENARIO_NAMES[t], c, p]), [1, 2]);
  }

  function renderLatency() {
    const inv = DATA.invoices.filter((i) => inSet(i) && !i.api_error);
    const bins = Array.from({ length: 10 }, (_, i) => ({ lo: i, hi: i + 1, n: 0 }));
    bins.push({ lo: 10, hi: Infinity, n: 0 });
    for (const i of inv) bins[Math.min(10, Math.floor(i.seconds))].n++;
    const secs = inv.map((i) => i.seconds).sort((a, b) => a - b);
    const median = secs[Math.floor(secs.length / 2)] || 0;
    const fails = DATA.invoices.filter((i) => inSet(i) && i.api_error).length;
    $("latSub").textContent = `Median ${median.toFixed(1)} s over ${inv.length} invoices${fails ? ` · ${fails} API timeout${fails > 1 ? "s" : ""} not shown` : ""}`;
    const box = $("chartLatency");
    const W = Math.max(300, box.clientWidth || 480);
    const left = 34, right = 8, top = 16, H = 200, base = H - 24;
    const max = Math.max(...bins.map((b) => b.n));
    const tickStep = max > 20 ? 10 : 5;
    const yMax = Math.ceil(max / tickStep) * tickStep;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H });
    const g = el("g", {}, svg);
    const y = (v) => base - (v / yMax) * (base - top);
    for (let t = 0; t <= yMax; t += tickStep) {
      el("line", { x1: left, x2: W - right, y1: y(t), y2: y(t), class: t ? "grid" : "axis" }, g);
      text(g, left - 6, y(t) + 4, t, { "text-anchor": "end", class: "muted" });
    }
    const slot = (W - left - right) / bins.length;
    const bw = Math.min(24, slot - 6);
    bins.forEach((b, i) => {
      const bx = left + i * slot + (slot - bw) / 2;
      el("path", { d: vbar(bx, base, bw, base - y(b.n)), fill: "var(--series-1)", class: "mark", "data-mark": i }, g);
      const lbl = b.hi === Infinity ? "10+" : String(b.lo);
      text(g, left + i * slot + slot / 2, H - 6, lbl, { "text-anchor": "middle", class: "muted" });
      const range = b.hi === Infinity ? "10 s or more" : `${b.lo}–${b.hi} s`;
      const hit = el("rect", { x: left + i * slot, y: top, width: slot, height: base - top, class: "hit", "data-mark": i, "aria-label": `${range}: ${b.n} invoices` }, g);
      hover(hit, g, [[`${b.n} invoice${b.n === 1 ? "" : "s"}`, range, "var(--series-1)"]]);
    });
    const mi = Math.min(10, Math.floor(median));
    text(g, left + mi * slot + slot / 2, top - 4, "median", { "text-anchor": "middle", class: "strong" });
    box.replaceChildren(svg);
    table($("tableLatency"), ["Seconds", "Invoices"], bins.map((b) => [b.hi === Infinity ? "10+" : `${b.lo}–${b.hi}`, b.n]), [1]);
  }

  function statusBadge(status, label) {
    const cls = status === "ready" ? "good" : "review";
    return h("span", { class: `status ${cls}` }, [h("span", { class: "dot" }), label || (status === "ready" ? "Ready" : "Needs review")]);
  }

  function renderGrid() {
    const list = filtered();
    $("count").textContent = `${list.length} invoice${list.length === 1 ? "" : "s"}`;
    $("invGrid").replaceChildren(...list.map((i) => {
      const card = h("button", { class: "inv", type: "button", "aria-label": `Open ${i.id}` });
      const thumb = h("div", { class: "thumb" });
      thumb.appendChild(h("img", { src: i.preview, alt: "", loading: "lazy", width: 760, height: 1075 }));
      const meta = h("div", { class: "meta" });
      meta.appendChild(h("b", { text: i.id }));
      meta.appendChild(h("div", { class: "scn", text: `${SCENARIO_NAMES[i.scenario]} · ${RENDER_NAMES[i.render]}` }));
      meta.appendChild(i.correct ? statusBadge(i.got, i.got === "ready" ? "Passed correctly" : "Flagged correctly")
        : h("span", { class: "status bad" }, [h("span", { class: "dot" }), i.api_error ? "API timeout → sent to a person" : "Missed something"]));
      card.append(thumb, meta);
      card.addEventListener("click", () => openInvoice(i));
      return card;
    }));
  }

  function openInvoice(i) {
    $("dlgImg").src = i.preview;
    $("dlgImg").alt = `${i.id}: ${RENDER_NAMES[i.render]} of an invoice from ${i.supplier}`;
    const info = $("dlgInfo");
    const close = h("button", { class: "toggle close", type: "button", text: "Close" });
    close.addEventListener("click", () => $("dlg").close());
    const kv = h("dl", { class: "kv" });
    for (const [k, v] of [["Supplier", i.supplier], ["Invoice no.", i.number], ["Total", `₱${i.total.toLocaleString("en-PH", { minimumFractionDigits: 2 })}`],
      ["Belongs to PO", i.true_po], ["Agent matched PO", i.matched_po || "none (couldn't read it)"], ["Form", RENDER_NAMES[i.render]],
      ["Read in", i.api_error ? "API timeout" : `${i.seconds.toFixed(1)} s`], ["Set", i.set === "holdout" ? "Held-out" : "Tuning"]]) {
      kv.append(h("dt", { text: k }), h("dd", { text: v }));
    }
    const planted = i.planted.length ? i.planted : ["Nothing: this invoice is correct."];
    const agent = i.agent.length ? i.agent : ["No issues found. Ready for approval."];
    info.replaceChildren(
      close,
      h("h3", { id: "dlgTitle", text: i.id }),
      h("div", { class: "sub" }, [`${SCENARIO_NAMES[i.scenario]} · expected `, statusBadge(i.expected), " · agent said ", statusBadge(i.got)]),
      kv,
      h("h4", { text: "Planted in this invoice" }), h("ul", {}, planted.map((p) => h("li", { text: p }))),
      h("h4", { text: "What the agent reported" }), h("ul", {}, agent.map((p) => h("li", { text: p }))),
    );
    $("dlg").showModal();
  }

  function renderFixes() {
    const ex = DATA.extraction, first = DATA.matching[0], fixed = DATA.matching[1];
    const items = [
      [`${pct(...ex[0].All)}% → ${pct(...ex[1].All)}%`, "invoices read fully correctly", "Day and month swapped",
        "Philippine invoices print 10/03/2026 for October 3; the model read March 10 on 9 of 60 invoices. One prompt rule fixed 8 of them, and a code check now flags any invoice dated before its own PO."],
      [`${first.types.unknown_item[0]}/${first.types.unknown_item[1]} → ${fixed.types.unknown_item[0]}/${fixed.types.unknown_item[1]}`, "unknown items caught",
        "False “wrong PO” accusations", `An extra item made the cited PO look like a bad fit, so the matcher picked another PO and invented over-billing. Rule: trust the printed PO unless another fits exactly. Flags that were real: ${pct(...first.metrics.precision)}% → ${pct(...fixed.metrics.precision)}%.`],
      ["Flash → Flash-Lite", "main model", "The main model went down",
        "Gemini Flash kept returning “high demand” and timing out. Flash-Lite answered in about 2–3 s with the accuracy above, so it became the main model with Flash as fallback. Timeouts still happen; every one goes to a person."],
      ["Recorded", "every invoice, even unreadable", "A duplicate slipped through",
        "Its original timed out, so no invoice number was on record. Every invoice now becomes a draft bill with the file attached and an “Enter manually” To-Do. Still open: duplicates of an unreadable original."],
    ];
    $("fixes").replaceChildren(...items.map(([d, ds, t, p]) =>
      h("div", { class: "fix" }, [h("div", { class: "delta" }, [d, h("small", { text: ds })]), h("div", {}, [h("h3", { text: t }), h("p", { text: p })])])));
  }

  function renderFiltered() { renderTypes(); renderLatency(); renderGrid(); }
  function renderAll() { renderHero(); renderReading(); renderMatching(); renderFiltered(); renderFixes(); }

  // ---------- controls ----------
  function wire() {
    $("segSet").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-set]");
      if (!b) return;
      state.set = b.dataset.set;
      $("segSet").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      renderFiltered();
    });
    for (const [id, key] of [["fOutcome", "outcome"], ["fRender", "render"], ["fScenario", "scenario"]]) {
      $(id).addEventListener("change", (e) => { state[key] = e.target.value; renderGrid(); });
    }
    const scen = [...new Set(DATA.invoices.map((i) => i.scenario))].sort((a, b) => SCENARIO_NAMES[a].localeCompare(SCENARIO_NAMES[b]));
    $("fScenario").append(...scen.map((s) => h("option", { value: s, text: SCENARIO_NAMES[s] })));

    document.querySelectorAll("button[data-table]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.table, cap = k[0].toUpperCase() + k.slice(1);
      const tbl = $("table" + cap), chart = $("chart" + cap);
      const showTable = tbl.hidden;
      tbl.hidden = !showTable;
      chart.hidden = showTable;
      b.textContent = showTable ? "Show chart" : "Show table";
    }));

    $("dlg").addEventListener("click", (e) => { if (e.target === $("dlg")) $("dlg").close(); });

    const themes = ["auto", "light", "dark"];
    let theme = "auto";
    try { theme = localStorage.getItem("theme") || "auto"; } catch (e) { /* storage unavailable */ }
    const apply = () => {
      if (theme === "auto") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", theme);
      $("themeBtn").textContent = `Theme: ${theme}`;
    };
    apply();
    $("themeBtn").addEventListener("click", () => {
      theme = themes[(themes.indexOf(theme) + 1) % themes.length];
      try { localStorage.setItem("theme", theme); } catch (e) { /* ignore */ }
      apply();
    });

    let raf = 0, lastW = 0;
    new ResizeObserver(() => {
      const w = document.body.clientWidth;
      if (w === lastW) return;
      lastW = w;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => { renderReading(); renderMatching(); renderTypes(); renderLatency(); });
    }).observe(document.body);
  }

  fetch("data.json").then((r) => r.json()).then((d) => { DATA = d; wire(); renderAll(); })
    .catch(() => { document.querySelector(".hero .lede").textContent = "Couldn't load the results data."; });
})();
