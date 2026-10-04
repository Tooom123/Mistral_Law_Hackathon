// Case graph — the case file as a collage of paper cut-outs (same language as the landing page):
// one pixel tile per act, cut out with a white edge, stuck on rows by category, in time order; pen lines = "depends on".
// The flagged act is the red tile, taped, with a yellow sticker; "Simulate impact" tips the dominoes.
// Everything comes from /graph and /alerts — nothing is drawn that the data does not say.
// Small cases only (the 3D graph stays for big ones). This module touches nothing else: no timeline code.
import { h, sleep, REDUCED, CAT_FR, dmy, hm } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  parent?.appendChild(e);
  return e;
};

// Mistral ramp: rows take yellow → orange, the breach is red, what falls goes grey.
const LANE_COLORS = ["#FFAF01", "#FF8204", "#FA500F", "#F5742B", "#FFC247"];
const PIXEL_RAMP = ["#FFE8D2", "#FFD3AA", "#FFAF01", "#FF8204", "#FA500F", "#E61300", "#C4001D"];
const RED = "#E61300";

// deterministic pseudo-random in [0,1) from a string — the same case always looks the same
function rnd(seed) {
  let n = 2166136261;
  for (let i = 0; i < seed.length; i++) n = Math.imul(n ^ seed.charCodeAt(i), 16777619);
  n = Math.imul(n ^ (n >>> 15), 2246822507);
  return ((n ^ (n >>> 13)) >>> 0) / 4294967295;
}
const jit = (seed, k, amp) => (rnd(seed + k) - 0.5) * 2 * amp;

const wrapLabel = (s, max = 17) => {
  const words = String(s).split(/\s+/), lines = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > max && cur) { lines.push(cur); cur = w; } else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 3);
};

const dayDiff = (a, b) => Math.round((Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) - Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) / 864e5);

// white paper edge that follows the tile, wobbling like a quick cut with scissors
function cutPath(seed, half) {
  const s = half + 6.5;                       // 6–7 px of white around the tile
  const pts = [];
  const side = (ax, ay, bx, by, k) => {         // 3 points per side, jittered
    for (let i = 0; i < 3; i++) {
      const t = i / 3;
      pts.push([ax + (bx - ax) * t + jit(seed, `${k}x${i}`, 2.2), ay + (by - ay) * t + jit(seed, `${k}y${i}`, 2.2)]);
    }
  };
  side(-s, -s, s, -s, "t"); side(s, -s, s, s, "r"); side(s, s, -s, s, "b"); side(-s, s, -s, -s, "l");
  return "M" + pts.map(p => p.map(v => v.toFixed(1)).join(",")).join(" L") + " Z";
}

export class Flow {
  constructor(root, { onSelect, onAlert, onSimulate } = {}) {
    this.root = root;
    this.onSelect = onSelect; this.onAlert = onAlert; this.onSimulate = onSimulate;
    this.svg = svgEl("svg", { class: "flow", role: "img", "aria-label": "Case graph: acts as paper tiles, by category and time" });
    this.ruler = h("div", { class: "ruler", hidden: true });
    this.stats = h("div", { class: "flow-stats" });
    this.replayBtn = h("button", { class: "flow-replay", title: "Replay", onclick: () => this.play() }, "↻");
    root.append(this.svg, this.stats, this.ruler, this.replayBtn);
    this.nodeEls = new Map();
    this.edgeEls = [];
    this.dominoOn = false;
    this.fx = { nodes: new Map(), edges: new Set() };
    this.ro = new ResizeObserver(() => { if (this.graph && root.clientWidth) this.layout({ animate: false }); });
    this.ro.observe(root);
    this.ready = true;
  }

  setData(graph, alerts) {
    const first = !this.graph;
    this.graph = graph; this.alerts = alerts;
    this.layout({ animate: first });
    this.renderStats();
    this.renderRuler();
  }

  resize() { if (this.graph && this.root.clientWidth) this.layout({ animate: false }); }
  play() { if (this.graph) { this.resetDomino(); this.layout({ animate: true }); this.renderRuler(); } }

  // ------------------------------------------------------------------ geometry
  layout({ animate }) {
    const g = this.graph;
    const W = this.root.clientWidth, H = this.root.clientHeight;
    if (!W || !H) return;
    const acts = g.nodes.filter(n => n.type === "ACT").sort((a, b) => (a.start ?? "9").localeCompare(b.start ?? "9"));
    const lanes = g.lanes.filter(l => acts.some(a => a.category === l));
    const small = W < 700;
    const padL = small ? 16 : 150, padR = small ? 16 : 56, padT = small ? 96 : 118, padB = small ? 170 : 196;
    const laneH = Math.min(172, (H - padT - padB) / Math.max(lanes.length, 1));
    const step = acts.length > 1 ? Math.min(176, (W - padL - padR - 60) / (acts.length - 1)) : 0;
    const t = Math.max(34, Math.min(66, step * 0.56 || 66, laneH * 0.48));
    const x0 = padL + (W - padL - padR - step * (acts.length - 1)) / 2;
    const pos = new Map(acts.map((a, i) => [a.id, { x: x0 + i * step, y: padT + lanes.indexOf(a.category) * laneH + laneH / 2 - 10 }]));
    this.geo = { W, H, t, lanes, laneH, padT, padL, small, acts, pos };

    const svg = this.svg;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.replaceChildren();
    this.nodeEls.clear(); this.edgeEls = [];
    const defs = svgEl("defs", {}, svg);
    // pen line: slightly wobbly, like the app's hand-drawn strokes
    const f = svgEl("filter", { id: "flow-rough", x: "-5%", y: "-5%", width: "110%", height: "110%" }, defs);
    svgEl("feTurbulence", { type: "fractalNoise", baseFrequency: "0.035", numOctaves: "2", result: "n" }, f);
    svgEl("feDisplacementMap", { in: "SourceGraphic", in2: "n", scale: "2.6" }, f);

    this.drawPixels(svg, W, H, padT, laneH * lanes.length);

    // rows: a soft band + a label tag stuck on the left
    lanes.forEach((l, i) => {
      const y = padT + i * laneH;
      svgEl("rect", { x: 0, y, width: W, height: laneH, class: `flow__band ${i % 2 ? "alt" : ""}` }, svg);
      if (!small) {
        const tag = svgEl("g", { transform: `translate(18,${y + laneH / 2 - 18}) rotate(${(i % 2 ? 1.6 : -1.6)})`, class: "flow__tag" }, svg);
        const name = CAT_FR[l]?.[0] ?? l;
        svgEl("rect", { x: 0, y: 0, width: name.length * 7.4 + 34, height: 26 }, tag);
        svgEl("rect", { x: 9, y: 9, width: 8, height: 8, fill: LANE_COLORS[i % LANE_COLORS.length] }, tag);
        svgEl("text", { x: 24, y: 17.5 }, tag).textContent = name;
      }
    });

    // pen lines (SUPPORTS), drawn in left to right
    const edgeLayer = svgEl("g", { filter: "url(#flow-rough)" }, svg);
    const idx = new Map(acts.map((a, i) => [a.id, i]));
    for (const e of g.edges.filter(e => e.kind === "SUPPORTS" && pos.has(e.src) && pos.has(e.dst))) {
      const a = pos.get(e.src), b = pos.get(e.dst);
      const x1 = a.x + t / 2 + 8, x2 = b.x - t / 2 - 8, mx = (x1 + x2) / 2;
      const p = svgEl("path", {
        d: `M${x1},${a.y} C${mx},${a.y + jit(e.src + e.dst, "a", 6)} ${mx},${b.y + jit(e.src + e.dst, "b", 6)} ${x2},${b.y}`,
        class: `flow__edge ${e.origin === "llm_inferred" ? "inferred" : ""}`, pathLength: 1, "data-src": e.src, "data-dst": e.dst,
      }, edgeLayer);
      if (animate && !REDUCED) { p.style.animationDelay = `${(idx.get(e.dst) ?? 0) * 130 + 300}ms`; p.classList.add("draw"); }
      this.edgeEls.push(p);
    }

    // tiles
    const alertByNode = new Map(this.alerts.map(a => [a.node.id, a]));
    const nodeLayer = svgEl("g", {}, svg);
    acts.forEach((n, i) => {
      const { x, y } = pos.get(n.id);
      const al = alertByNode.get(n.id);
      const flagged = al?.status === "possible_nullity", toRead = al?.status === "needs_reading";
      const color = flagged ? RED : LANE_COLORS[lanes.indexOf(n.category) % LANE_COLORS.length];
      const ts = flagged ? t * 1.14 : t;                                   // the breach is a little bigger
      const outer = svgEl("g", { transform: `translate(${x},${y})`, class: `fn ${flagged ? "is-alert" : ""} ${toRead ? "is-read" : ""}`, "data-id": n.id, tabindex: 0 }, nodeLayer);
      const rot = svgEl("g", { transform: `rotate(${(jit(n.id, "r", 3.2)).toFixed(2)})` }, outer);
      const inner = svgEl("g", { class: "fn__in" }, rot);
      if (animate && !REDUCED) inner.style.animationDelay = `${i * 140}ms`; else inner.style.animation = "none";
      svgEl("rect", { x: -ts / 2 - 12, y: -ts / 2 - 12, width: ts + 24, height: ts + 80, fill: "transparent" }, inner);
      const paper = svgEl("g", { class: "fn__paper" }, inner);
      if (flagged) {
        svgEl("rect", { x: -ts / 2, y: -ts / 2, width: ts, height: ts, class: "fn__pulse" }, inner);
        svgEl("rect", { x: -ts / 2, y: -ts / 2, width: ts, height: ts, class: "fn__pulse p2" }, inner);
      }
      svgEl("path", { d: cutPath(n.id, ts / 2), class: "fn__cut" }, paper);               // white cut-out edge
      svgEl("rect", { x: -ts / 2, y: -ts / 2, width: ts, height: ts, fill: color, class: "fn__tile" }, paper);
      // pixel texture: 3×3 cells, some lighter — the Mistral blocks
      const c3 = ts / 3;
      for (let r = 0; r < 3; r++) for (let q = 0; q < 3; q++) {
        const v = rnd(`${n.id}${r}${q}`);
        if (v < 0.34) svgEl("rect", { x: -ts / 2 + q * c3, y: -ts / 2 + r * c3, width: c3, height: c3, fill: "#fff", opacity: 0.16 + v * 0.3, class: "fn__px" }, paper);
        else if (v > 0.86) svgEl("rect", { x: -ts / 2 + q * c3, y: -ts / 2 + r * c3, width: c3, height: c3, fill: "#000", opacity: 0.12, class: "fn__px" }, paper);
      }
      if (flagged) {
        svgEl("path", { d: `M${-ts * .12},${-ts / 2} l${ts * .1},${ts * .22} l${-ts * .14},${ts * .16} l${ts * .2},${ts * .18} l${-ts * .08},${ts * .16}`, class: "fn__crack" }, paper);
        svgEl("path", { d: "M-34,-3 l7,-8 h5 l6,5 h54 l-4,8 l-6,-3 l-5,6 h-52 l-6,-6 Z", class: "fn__tape", transform: `translate(0,${-ts / 2 - 5}) rotate(-4)` }, inner);
      }
      if (toRead) svgEl("rect", { x: -ts / 2 - 9, y: -ts / 2 - 9, width: ts + 18, height: ts + 18, class: "fn__ring" }, inner);
      svgEl("rect", { x: -ts / 2 - 9, y: -ts / 2 - 9, width: ts + 18, height: ts + 18, class: "fn__sel" }, inner);
      // paper label stuck under the tile (on a phone only the flagged act keeps one)
      if (!(small && !flagged)) {
        const lines = wrapLabel(n.label, Math.max(11, Math.min(17, Math.floor((step - 26) / 6.5))));
        const w = Math.max(...lines.map(l => l.length)) * 6.5 + 18;
        const lh = 14, top = ts / 2 + 14;
        const lab = svgEl("g", { class: "fn__lab", transform: `rotate(${(jit(n.id, "l", 1.6)).toFixed(2)})` }, inner);
        svgEl("rect", { x: -w / 2, y: top, width: w, height: lines.length * lh + (n.start ? 17 : 8) + 6 }, lab);
        const tx = svgEl("text", { y: top + 15, class: "fn__label" }, lab);
        lines.forEach((ln, k) => { const sp = svgEl("tspan", { x: 0, dy: k ? lh : 0 }, tx); sp.textContent = ln; });
        if (n.start) {
          svgEl("text", { y: top + 15 + lines.length * lh + 1, class: "fn__date" }, lab).textContent =
            dmy(n.start).slice(0, 5) + (n.start.slice(11, 16) !== "00:00" ? ` ${hm(n.start)}` : "");
        }
      }
      if (al) this.drawSticker(outer, al, ts);
      outer.addEventListener("mouseenter", () => this.hover(n.id));
      outer.addEventListener("mouseleave", () => this.hover(null));
      outer.addEventListener("click", () => { this.select(n.id); this.onSelect?.(n); });
      outer.addEventListener("keydown", e => { if (e.key === "Enter") outer.dispatchEvent(new MouseEvent("click")); });
      this.nodeEls.set(n.id, outer);
    });
    if (this.sel) this.select(this.sel);
    this.applyFx();
  }

  // dithered clusters of orange pixels on both sides, like the landing hero (denser at the edges, clear in the middle)
  drawPixels(svg, W, H, top, bandH) {
    const size = W < 700 ? 14 : 28, cols = Math.ceil(W / size);
    const gp = svgEl("g", { class: "flow__pixels" }, svg);
    const band = W < 700 ? 1.2 : Math.max(2.5, Math.min(4.5, cols * 0.08));
    const y0 = Math.floor((top - 70) / size), y1 = Math.ceil((top + bandH + 150) / size);
    const bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
    for (let r = Math.max(0, y0); r < y1; r++) for (let c = 0; c < cols; c++) {
      const edge = Math.min(c + .5, cols - c - .5);
      let v = 1 - Math.min(1, edge / band);
      const along = 1 - Math.min(1, Math.abs(r - (y0 + y1) / 2) / ((y1 - y0) / 2));
      v *= (0.45 + 0.9 * rnd(`p${r}-${c}`)) * (0.35 + 0.8 * along);
      if (v < 0.17 || v <= (bayer[r & 3][c & 3] + .5) / 16 * 0.75) continue;
      const k = Math.min(PIXEL_RAMP.length - 1, Math.floor(v * PIXEL_RAMP.length + (c < cols / 2 ? -0.6 : 0.5)));
      svgEl("rect", { x: c * size, y: r * size, width: size, height: size, fill: PIXEL_RAMP[Math.max(0, k)] }, gp);
    }
  }

  // the yellow sticker (like the landing's "4 months") + the hard-shadow button
  drawSticker(outer, al, ts) {
    const d = al.details ?? {};
    let big = al.nullity_id, small = "";
    if (d.day_received != null && d.offence && d.limit) { big = `Day ${d.day_received}`; small = `limit ${dayDiff(new Date(d.offence), new Date(d.limit))}`; }
    const g = svgEl("g", { class: `fn__sticker ${al.status === "needs_reading" ? "read" : ""}`, transform: `translate(${ts / 2 + 12},${-ts / 2 - 6}) rotate(9)` }, outer);
    svgEl("circle", { r: 37, class: "st__ring" }, g);
    svgEl("circle", { r: 31, class: "st__disc" }, g);
    svgEl("text", { y: small ? -1 : 5, class: "st__big" }, g).textContent = big;
    if (small) svgEl("text", { y: 15, class: "st__small" }, g).textContent = small;
    g.addEventListener("click", ev => { ev.stopPropagation(); this.onAlert?.(al.key); });
    const sim = svgEl("g", { class: "fn__sim", transform: `translate(${ts / 2 + 18},${ts / 2 - 4})` }, outer);
    svgEl("rect", { x: 0, y: -13, width: 112, height: 28, class: "sim__sh" }, sim);
    svgEl("rect", { x: -2, y: -16, width: 112, height: 28, class: "sim__bt" }, sim);
    svgEl("text", { x: 54, y: 2, class: "sim__tx" }, sim).textContent = "Simulate impact ▸";
    sim.addEventListener("click", ev => { ev.stopPropagation(); this.onSimulate?.(al.node.id); });
  }

  // ------------------------------------------------------------------ overlays
  renderStats() {
    const g = this.graph, a = this.alerts;
    const docs = new Set(g.nodes.filter(n => n.type === "ACT").flatMap(n => n.doc_ids)).size;
    const flagged = a.filter(x => x.status === "possible_nullity").length;
    const risk = Math.max(0, ...a.map(x => x.why?.affected_count ?? 0));
    const cell = (n, l, cls = "") => h("div", { class: `fs ${cls}` }, h("b", {}, String(n)), h("span", {}, l));
    this.stats.replaceChildren(cell(docs, docs === 1 ? "document" : "documents"), cell(flagged, flagged === 1 ? "breach" : "breaches", flagged ? "red" : ""), cell(risk, "acts at risk", risk ? "red" : ""));
  }

  // the breach in one picture: days since the offence as pixel cells, the limit, the red one, a note in pen
  renderRuler() {
    const top = this.alerts.find(x => x.status === "possible_nullity" && x.details?.day_received != null && x.details.offence && x.details.limit);
    if (!top) { this.ruler.hidden = true; return; }
    const d = top.details;
    const limit = dayDiff(new Date(d.offence), new Date(d.limit)), posted = d.day_posted, recv = d.day_received;
    const n = Math.max(recv, limit) + 2;
    const cells = [];
    for (let i = 0; i <= n; i++) {
      const over = i > limit;
      const c = h("i", { class: `rl__c ${over ? "over" : ""} ${i === recv ? "recv" : ""}` });
      c.style.setProperty("--c", over ? RED : LANE_COLORS[Math.min(4, Math.floor(i / (limit + 1) * 3))]);
      cells.push(c);
    }
    const mark = (day, label, cls) => { const m = h("span", { class: `rl__m ${cls}` }, label); m.style.setProperty("--d", day); return m; };
    const lim = h("span", { class: "rl__lim" }, h("em", {}, `${limit}-day limit`));
    lim.style.setProperty("--d", limit + 1);
    const late = recv - limit;
    const note = late > 0 ? h("span", { class: "rl__note" }, `${late === 1 ? "one day" : late + " days"} late`,
      h("span", { class: "rl__arrow", html: '<svg viewBox="0 0 60 40"><path d="M4 4 C 22 2, 44 12, 52 32" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round"/><path d="M42 30 L53 35 L55 23" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>' })) : null;
    if (note) note.style.setProperty("--d", recv);
    this.ruler.replaceChildren(h("span", { class: "rl__tape" }),
      h("div", { class: "rl__row" }, ...cells, lim, note),
      h("div", { class: "rl__marks" }, mark(0, "offence", ""), mark(posted, "posted", ""), mark(recv, `received · day ${recv}`, "red")));
    this.ruler.style.setProperty("--n", n + 1);
    this.ruler.hidden = false;
    // cells land one after the other, then the red one flashes (timers, not CSS delays: robust and replayable)
    clearTimeout(this._rt);
    const els = [...this.ruler.querySelectorAll(".rl__c")];
    els.forEach(c => c.classList.toggle("on", REDUCED));
    if (!REDUCED) els.forEach((c, i) => { this._rt = setTimeout(() => c.classList.add("on"), 700 + i * 60); });
  }

  // ------------------------------------------------------------------ interaction
  hover(id) {
    if (this.dominoOn) return;
    const near = new Set();
    if (id) {
      near.add(id);
      for (const e of this.edgeEls) { if (e.dataset.src === id) near.add(e.dataset.dst); if (e.dataset.dst === id) near.add(e.dataset.src); }
    }
    this.svg.classList.toggle("has-hover", !!id);
    for (const [k, el] of this.nodeEls) el.classList.toggle("near", near.has(k));
    for (const e of this.edgeEls) e.classList.toggle("hot", !!id && (e.dataset.src === id || e.dataset.dst === id));
  }
  highlight(id) { this.hover(id); }
  select(id) {
    this.sel = id;
    for (const [k, el] of this.nodeEls) el.classList.toggle("sel", k === id);
  }
  focus(id) { this.select(id); }

  // ------------------------------------------------------------------ domino
  // the state of the simulation lives in `fx`, so a re-layout (window resize) keeps it
  applyFx() {
    this.svg.classList.toggle("tipping", this.dominoOn);
    for (const [id, el] of this.nodeEls) for (const c of ["origin", "fade", "fallen"]) el.classList.toggle(c, this.fx.nodes.get(id) === c);
    for (const e of this.edgeEls) e.classList.toggle("domino", this.fx.edges.has(`${e.dataset.src}|${e.dataset.dst}`));
  }

  async domino(sim, sticker, counterEl) {
    this.resetDomino();
    this.dominoOn = true;
    const hit = new Set(sim.affected.map(a => a.id));
    this.fx.nodes.set(sim.removed, "origin");
    for (const k of this.nodeEls.keys()) if (k !== sim.removed && !hit.has(k)) this.fx.nodes.set(k, "fade");
    this.applyFx();
    sticker.hidden = false;
    counterEl.textContent = "0";
    let count = 0;
    for (let d = 1; d <= Math.max(1, sim.waves); d++) {
      await sleep(REDUCED ? 0 : 640);
      if (!this.dominoOn) return;
      for (const a of sim.affected.filter(x => x.depth === d)) {
        this.fx.nodes.set(a.id, "fallen");
        this.fx.edges.add(`${a.parent}|${a.id}`);
        this.applyFx();
        counterEl.textContent = ++count;
        await sleep(REDUCED ? 0 : 160);
      }
    }
  }

  resetDomino() {
    this.dominoOn = false;
    this.fx = { nodes: new Map(), edges: new Set() };
    this.applyFx();
  }
}
