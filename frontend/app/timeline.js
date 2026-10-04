// Timeline by category — one swim lane per category, time on X (long gaps compressed), one mark per act.
// SUPPORTS edges = what depends on what; CONTRADICTS = zig-zag; custody = a bar with its acts on it.
import { $, h, CAT_FR, hm, dmy, dayLabel, sleep, REDUCED } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const s = (tag, attrs = {}, ...kids) => {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  for (const kid of kids) if (kid) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
};

const GAV_CHILDREN = new Set(["placement_gav", "rights_notification", "lawyer_notice", "family_notice", "medical_exam", "extension", "custody_end"]);
const SHORT = {
  placement_gav: "Placement", rights_notification: "Rights", lawyer_notice: "Lawyer notified", family_notice: "Relative informed",
  medical_exam: "Doctor", extension: "Extension", custody_end: "End", hearing: "Hearing", hearing_witness: "Witness",
  interpellation: "Arrest", search: "Search", seizure: "Seizure", seal_analysis: "Seal analysis",
  lab_report: "Expert report", geolocation: "Tracker", geolocation_authorization: "Authorisation", interception: "Wiretaps",
  interception_order: "Order", opening: "Opening", mise_en_examen: "Formal charge", expert_order: "Expert appointment",
  chamber_ruling: "Chamber ruling", photo: "Photo", other: "",
};
const ROW = 30, TOP = 46, LANE_PAD = 16, HOUR = 44, CAP_H = 4, BREAK_W = 54;

export class Timeline {
  constructor({ svg, labels, scroll, tooltip, onSelect, onHover }) {
    Object.assign(this, { svg, labels, scroll, tooltip, onSelect, onHover });
    this.zoom = 1;
    this.positions = new Map();
    this.nodeEls = new Map();
    this.edgeEls = [];
  }

  // ------------------------------------------------------------------ data → layout
  setData(graph, alerts) {
    this.graph = graph;
    this.alertsByNode = new Map();
    for (const a of alerts) {
      const lst = this.alertsByNode.get(a.node.id) ?? [];
      lst.push(a);
      this.alertsByNode.set(a.node.id, lst);
    }
    const acts = graph.nodes.filter(n => n.type === "ACT");
    for (const n of acts) n._t = this.timeOf(n);
    this.acts = acts.filter(n => n._t);
    this.byId = new Map(graph.nodes.map(n => [n.id, n]));
    this.render();
  }

  timeOf(n) {
    if (n.start) return new Date(n.start);
    if (n.end) return new Date(n.end);
    for (const k of ["start_date_only", "end_date", "custody_end_date", "date"]) {
      const v = n.attrs?.[k]?.value;
      if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) { const x = new Date(v.slice(0, 10) + "T12:00:00"); n._approx = true; return x; }
    }
    return null;
  }

  buildScale() {
    const ts = new Set();
    for (const n of this.acts) { ts.add(+n._t); if (n.end) ts.add(+new Date(n.end)); }
    const pts = [...ts].sort((a, b) => a - b);
    const px = HOUR * this.zoom;
    const segs = [];
    let x = 50;
    for (let i = 0; i < pts.length; i++) {
      if (i === 0) { segs.push({ t: pts[0], x }); continue; }
      const gapH = (pts[i] - pts[i - 1]) / 36e5;
      const brk = gapH > CAP_H;
      x += Math.min(gapH, CAP_H) * px + (brk ? BREAK_W : 0);
      segs.push({ t: pts[i], x, brk, gapH });
    }
    this.segs = segs;
    this.width = x + 220;
    this.xOf = t => {
      t = +t;
      if (t <= segs[0].t) return segs[0].x - (segs[0].t - t) / 36e5 * px;
      for (let i = 1; i < segs.length; i++) {
        if (t <= segs[i].t) {
          const a = segs[i - 1], b = segs[i];
          return a.x + (t - a.t) / Math.max(1, b.t - a.t) * (b.x - a.x);
        }
      }
      return segs.at(-1).x + (t - segs.at(-1).t) / 36e5 * px;
    };
  }

  layout() {
    const lanes = [];
    const present = new Set(this.acts.map(n => n.category));
    for (const cat of this.graph.lanes) if (present.has(cat)) lanes.push(cat);
    this.lanes = [];
    let y = TOP;
    for (const cat of lanes) {
      const nodes = this.acts.filter(n => n.category === cat);
      const rows = [];
      const place = new Map();
      if (cat === "GARDE_A_VUE") {
        const cont = nodes.filter(n => n.subtype === "garde_a_vue").sort((a, b) => a._t - b._t);
        cont.forEach((c, i) => { rows.push([]); place.set(c.id, i); });
        for (const n of nodes) {
          if (n.subtype === "garde_a_vue") continue;
          const c = cont.find(c => c.person === n.person);
          if (c && GAV_CHILDREN.has(n.subtype)) place.set(n.id, place.get(c.id));
        }
      }
      const rest = nodes.filter(n => !place.has(n.id)).sort((a, b) => a._t - b._t);
      const lastX = rows.map(() => -1e9);
      for (const n of rest) {
        const x = this.xOf(n._t);
        let r = lastX.findIndex(lx => x - lx > 26);
        if (r === -1 || (cat === "GARDE_A_VUE" && r < rows.length && rows[r].length === 0 && false)) { r = lastX.length; lastX.push(-1e9); rows.push([]); }
        lastX[r] = x + (this.labelFor(n) ? Math.min(150, this.labelFor(n).length * 6.2) : 0);
        place.set(n.id, r);
      }
      const nRows = Math.max(1, lastX.length, rows.length);
      const hgt = LANE_PAD * 2 + nRows * ROW;
      this.lanes.push({ cat, y, h: hgt, nodes, count: nodes.length });
      const lastOnRow = new Map();
      for (const n of [...nodes].sort((a, b) => a._t - b._t)) {
        const r = place.get(n.id) ?? 0;
        const x = this.xOf(n._t);
        let dy = 0;
        const prev = lastOnRow.get(r);
        if (prev && x - prev.x < 16 && n.subtype !== "garde_a_vue") dy = prev.dy === 0 ? (prev.flip ? -11 : 11) : 0;
        lastOnRow.set(r, { x, dy, flip: dy > 0 });
        this.positions.set(n.id, { x, y: y + LANE_PAD + r * ROW + ROW / 2 + dy, lane: cat });
      }
      y += hgt;
    }
    this.height = y + 30;
  }

  labelFor(n) {
    const al = this.alertsByNode.get(n.id);
    const z = this.zoom;
    if (n.subtype === "other" || n.subtype === "garde_a_vue") return "";
    if (!al && z < 1.4 && !["search", "mise_en_examen", "interpellation", "hearing", "lab_report", "seal_analysis", "geolocation"].includes(n.subtype)) return "";
    const base = SHORT[n.subtype] ?? n.label;
    const who = n.subtype === "seizure" ? (n.attrs?.seal_number?.value ?? "no seal") : "";
    return `${base}${who ? " " + who : ""} · ${n._approx ? "?" : hm(n._t.toISOString())}`;
  }

  // ------------------------------------------------------------------ render
  render() {
    this.positions.clear(); this.nodeEls.clear(); this.edgeEls = [];
    this.buildScale();
    this.layout();
    const svg = this.svg;
    svg.replaceChildren();
    svg.setAttribute("width", this.width);
    svg.setAttribute("height", this.height);
    svg.setAttribute("viewBox", `0 0 ${this.width} ${this.height}`);
    const defs = s("defs");
    defs.append(s("pattern", { id: "hatch-break", width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
      s("rect", { width: 8, height: 8, fill: "#F6F2EC" }), s("rect", { width: 2, height: 8, fill: "#E2DBD2" })));
    defs.append(s("marker", { id: "arrow", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
      s("path", { d: "M0 0 L8 4 L0 8 z", fill: "#4A4A5A" })));
    defs.append(s("marker", { id: "arrow-red", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
      s("path", { d: "M0 0 L8 4 L0 8 z", fill: "#E61300" })));
    svg.append(defs);

    // lane bands
    const gBands = s("g");
    this.lanes.forEach((l, i) => {
      gBands.append(s("rect", { class: `t-band ${i % 2 ? "t-band--alt" : ""}`, x: 0, y: l.y, width: this.width, height: l.h }));
      gBands.append(s("line", { class: "t-laneline", x1: 0, x2: this.width, y1: l.y + l.h, y2: l.y + l.h }));
    });
    svg.append(gBands);

    // breaks + time axis
    const gAxis = s("g");
    for (let i = 1; i < this.segs.length; i++) {
      const b = this.segs[i];
      if (!b.brk) continue;
      const x1 = this.segs[i - 1].x + CAP_H * HOUR * this.zoom / 2 - 2;
      const x0 = this.xOf(this.segs[i - 1].t + CAP_H / 2 * 36e5);
      const wx = this.xOf(b.t - CAP_H / 2 * 36e5) - x0;
      gAxis.append(s("rect", { class: "t-break", x: x0, y: TOP - 10, width: Math.max(8, wx), height: this.height - TOP }));
      const days = Math.floor(b.gapH / 24), hrs = Math.round(b.gapH % 24);
      gAxis.append(s("text", { class: "t-breaklabel", x: x0 + wx / 2, y: TOP - 14, "text-anchor": "middle" }, `+${days ? days + "d " : ""}${hrs}h`));
      void x1;
    }
    const t0 = new Date(this.segs[0].t), t1 = new Date(this.segs.at(-1).t);
    const day = new Date(t0); day.setHours(0, 0, 0, 0);
    let lastLabelX = -1e9;
    if (this.xOf(day) < 0) {
      gAxis.append(s("text", { class: "t-daylabel", x: 8, y: 22 }, dayLabel(t0).toUpperCase()));
      lastLabelX = 8;
    }
    for (let dd = new Date(day); dd <= t1; dd.setDate(dd.getDate() + 1)) {
      const x = this.xOf(dd);
      if (x < 0) continue;
      gAxis.append(s("line", { class: "t-day", x1: x, x2: x, y1: 14, y2: this.height }));
      if (x - lastLabelX > 70) {
        gAxis.append(s("text", { class: "t-daylabel", x: x + 5, y: 22 }, dayLabel(dd).toUpperCase()));
        lastLabelX = x;
      }
    }
    // hour ticks inside dense segments
    const pxh = HOUR * this.zoom;
    const step = pxh > 70 ? 1 : pxh > 30 ? 2 : 4;
    for (let i = 1; i < this.segs.length; i++) {
      const a = this.segs[i - 1], b = this.segs[i];
      const start = new Date(a.t); start.setMinutes(0, 0, 0); start.setHours(start.getHours() + 1);
      for (let t = +start; t < b.t; t += step * 36e5) {
        const tt = new Date(t);
        if (tt.getHours() % step || tt.getHours() === 0) continue;
        if ((t - a.t) / 36e5 > CAP_H / 2 && (b.t - t) / 36e5 > CAP_H / 2 && b.brk) continue;
        const x = this.xOf(t);
        gAxis.append(s("line", { class: "t-hour", x1: x, x2: x, y1: 28, y2: this.height }));
        gAxis.append(s("text", { class: "t-hourlabel", x: x + 3, y: 38 }, `${String(tt.getHours()).padStart(2, "0")}:00`));
      }
    }
    // legal hour band for home searches (21h–6h) — drawn faintly behind the PERQUISITION lane
    const pl = this.lanes.find(l => l.cat === "PERQUISITION_SAISIE");
    if (pl) {
      for (let dd = new Date(day); dd <= t1; dd.setDate(dd.getDate() + 1)) {
        const n21 = new Date(dd); n21.setHours(21, 0, 0, 0);
        const n6 = new Date(dd); n6.setDate(n6.getDate() + 1); n6.setHours(6, 0, 0, 0);
        const xa = this.xOf(n21), xb = this.xOf(n6);
        if (xb - xa > 4) {
          gAxis.append(s("rect", { x: xa, y: pl.y + 1, width: xb - xa, height: pl.h - 2, fill: "#151524", opacity: .05 }));
          gAxis.append(s("text", { x: xa + 4, y: pl.y + pl.h - 5, class: "t-hourlabel" }, "21:00–06:00"));
        }
      }
    }
    svg.append(gAxis);

    // custody bars
    const gBars = s("g");
    for (const n of this.acts.filter(n => n.subtype === "garde_a_vue")) {
      const p = this.positions.get(n.id);
      const x2 = n.end ? this.xOf(new Date(n.end)) : p.x + 60;
      const pn = (n.checks ?? []).some(c => c.status === "possible_nullity");
      const g = s("g", { class: `t-custody ${pn ? "pn" : ""}`, "data-id": n.id });
      g.append(s("rect", { class: "bar", x: p.x, y: p.y - 8, width: Math.max(10, x2 - p.x), height: 16 }));
      g.append(s("text", { x: p.x + 2, y: p.y - 12 }, (n.label.replace("Custody — ", "Custody · ") + (n.end ? "" : " · end?")).toUpperCase()));
      // 24h mark
      const lim = new Date(+new Date(n.start) + 24 * 36e5);
      if (n.end && new Date(n.end) > lim) {
        const lx = this.xOf(lim);
        g.append(s("line", { class: "limit", x1: lx, x2: lx, y1: p.y - 14, y2: p.y + 12 }));
        g.append(s("text", { class: "limit-label", x: lx + 3, y: p.y + 20 }, "24h"));
      }
      g.addEventListener("click", () => this.onSelect?.(n));
      g.style.cursor = "pointer";
      gBars.append(g);
      this.nodeEls.set(n.id, g);
    }
    svg.append(gBars);

    // edges
    const gEdges = s("g");
    for (const e of this.graph.edges) {
      if (e.kind !== "SUPPORTS" && e.kind !== "CONTRADICTS") continue;
      const a = this.positions.get(e.src), b = this.positions.get(e.dst);
      if (!a || !b) continue;
      let path;
      if (e.kind === "SUPPORTS") {
        const dx = Math.max(30, Math.abs(b.x - a.x) * .45);
        path = s("path", { class: `t-edge ${e.origin === "llm_inferred" ? "llm" : ""}`, d: `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x - 7},${b.y}`, "marker-end": "url(#arrow)" });
      } else {
        path = s("path", { class: "t-con", d: zigzag(a, b) });
      }
      path.dataset.src = e.src; path.dataset.dst = e.dst; path.dataset.kind = e.kind;
      if (e.label) path.append(s("title", {}, e.label));
      gEdges.append(path);
      this.edgeEls.push(path);
    }
    svg.append(gEdges);

    // nodes
    const gNodes = s("g");
    const rankOf = n => (this.alertsByNode.get(n.id)?.length ? 2 : (n.checks ?? []).length ? 1 : 0);
    for (const n of [...this.acts].sort((a, b) => rankOf(a) - rankOf(b))) {
      if (n.subtype === "garde_a_vue") continue;
      const p = this.positions.get(n.id);
      const al = this.alertsByNode.get(n.id) ?? [];
      const checks = n.checks ?? [];
      const st = al.some(a => a.status === "possible_nullity") || checks.some(c => c.status === "possible_nullity") ? "pn"
        : al.length || checks.some(c => c.status === "needs_reading") ? "nr" : checks.length ? "ok" : "";
      const g = s("g", { class: `t-node ${st}`, transform: `translate(${p.x},${p.y})`, "data-id": n.id, tabindex: 0 });
      const big = ["mise_en_examen", "search", "interpellation"].includes(n.subtype);
      const r = big ? 8 : 6.5;
      let shape;
      if (n.subtype === "seizure") shape = s("rect", { class: "shape", x: -5.5, y: -5.5, width: 11, height: 11, transform: "rotate(45)" });
      else if (n.subtype === "photo") shape = s("circle", { class: "shape", r: 6 });
      else if (n.subtype === "other") shape = s("rect", { class: "shape", x: -3.5, y: -3.5, width: 7, height: 7, style: "stroke:#C4C1BC" });
      else shape = s("rect", { class: "shape", x: -r, y: -r, width: r * 2, height: r * 2 });
      g.append(s("circle", { class: "ring", r: 9 }), shape);
      if (al.length > 1) g.append(s("text", { class: "cnt", x: 0, y: 3, "text-anchor": "middle" }, al.length));
      const lbl = this.labelFor(n);
      if (lbl) g.append(s("text", { class: `lbl ${al.length ? "" : "dim"}`, x: r + 5, y: 3.5 }, lbl));
      if (n._approx) g.append(s("text", { class: "lbl", x: -3, y: -10, fill: "#C4001D" }, "?"));
      g.addEventListener("mouseenter", ev => this.hover(n, ev));
      g.addEventListener("mousemove", ev => this.moveTip(ev));
      g.addEventListener("mouseleave", () => this.unhover());
      g.addEventListener("click", () => this.onSelect?.(n));
      g.addEventListener("keydown", ev => { if (ev.key === "Enter") this.onSelect?.(n); });
      gNodes.append(g);
      this.nodeEls.set(n.id, g);
    }
    svg.append(gNodes);

    // lane labels (left column)
    this.labels.replaceChildren(h("div", { style: { height: `${TOP}px`, borderBottom: "1px solid var(--line)" } }));
    for (const l of this.lanes) {
      const [name, sub] = CAT_FR[l.cat] ?? [l.cat, ""];
      const pns = l.nodes.flatMap(n => this.alertsByNode.get(n.id) ?? []);
      this.labels.append(h("div", { class: "lane-label", style: { height: `${l.h}px` } },
        h("b", {}, name.toUpperCase()), h("small", {}, `${l.count} act${l.count > 1 ? "s" : ""} · ${sub}`),
        pns.length ? h("span", { class: "lane-alerts" }, pns.slice(0, 12).map(a => h("i", { class: a.status === "needs_reading" ? "nr" : "" }))) : null));
    }
    this.scroll.onscroll = () => { this.labels.scrollTop = this.scroll.scrollTop; };
  }

  // ------------------------------------------------------------------ interactions
  chain(id) {
    const out = new Set([id]);
    const down = [id], up = [id];
    const sup = this.graph.edges.filter(e => e.kind === "SUPPORTS");
    while (down.length) { const c = down.pop(); for (const e of sup) if (e.src === c && !out.has(e.dst)) { out.add(e.dst); down.push(e.dst); } }
    while (up.length) { const c = up.pop(); for (const e of sup) if (e.dst === c && !out.has(e.src)) { out.add(e.src); up.push(e.src); } }
    return out;
  }

  hover(n, ev) {
    if (this.dominoOn) return;
    const ch = this.chain(n.id);
    for (const el of this.edgeEls) el.classList.toggle("hot", ch.has(el.dataset.src) && ch.has(el.dataset.dst));
    const al = this.alertsByNode.get(n.id) ?? [];
    this.tooltip.replaceChildren(
      h("b", {}, n.label),
      h("small", {}, `${n._approx ? "date only — time unreadable" : `${dmy(n._t.toISOString())} · ${hm(n._t.toISOString())}`}${n.end ? " → " + hm(n.end) : ""} · ${n.doc_ids.join(", ")} · p. ${n.pages.slice(0, 3).join(", ")}`),
      ...al.slice(0, 3).map(a => h("span", { class: "tt-st" }, `⚠ ${a.nullity_id} — ${a.title}`)),
      ch.size > 1 ? h("small", {}, `${ch.size - 1} act(s) linked by dependency`) : null);
    this.tooltip.hidden = false;
    this.moveTip(ev);
    this.onHover?.(n);
  }

  moveTip(ev) {
    const r = this.scroll.parentElement.getBoundingClientRect();
    let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
    if (x > r.width - 310) x -= 330;
    this.tooltip.style.left = `${x}px`;
    this.tooltip.style.top = `${y}px`;
  }

  unhover() {
    this.tooltip.hidden = true;
    if (!this.dominoOn) for (const el of this.edgeEls) el.classList.remove("hot");
  }

  select(id, { scroll = true, anchor = .5 } = {}) {
    for (const [k, el] of this.nodeEls) el.classList.toggle("sel", k === id);
    const p = this.positions.get(id);
    if (p && scroll) {
      this.scroll.scrollTo({ left: Math.max(0, p.x - this.scroll.clientWidth * anchor), top: Math.max(0, p.y - this.scroll.clientHeight / 2), behavior: REDUCED ? "auto" : "smooth" });
    }
    const ch = this.chain(id);
    for (const el of this.edgeEls) el.classList.toggle("hot", ch.has(el.dataset.src) && ch.has(el.dataset.dst));
  }

  setZoom(z) {
    const cx = (this.scroll.scrollLeft + this.scroll.clientWidth / 2) / this.width;
    this.zoom = z;
    this.render();
    this.scroll.scrollLeft = cx * this.width - this.scroll.clientWidth / 2;
  }

  // ------------------------------------------------------------------ domino (stop-motion)
  async domino(sim, sticker, counterEl) {
    this.resetDomino();
    this.dominoOn = true;
    const origin = this.nodeEls.get(sim.removed);
    origin?.classList.add("origin");
    this.select(sim.removed, { anchor: .12 });
    for (const el of this.nodeEls.values()) if (el !== origin) el.classList.add("fade");
    const affected = new Set(sim.affected.map(a => a.id));
    for (const id of affected) this.nodeEls.get(id)?.classList.remove("fade");
    sticker.hidden = false;
    counterEl.textContent = "0";
    let count = 0;
    const waves = Math.max(1, sim.waves);
    for (let d = 1; d <= waves; d++) {
      await sleep(REDUCED ? 0 : 560);
      if (!this.dominoOn) return;
      for (const a of sim.affected.filter(a => a.depth === d)) {
        this.nodeEls.get(a.id)?.classList.add("fallen");
        for (const el of this.edgeEls) if (el.dataset.dst === a.id && el.dataset.src === a.parent) { el.classList.add("domino"); el.setAttribute("marker-end", "url(#arrow-red)"); }
        count++;
        counterEl.textContent = count;
        await sleep(REDUCED ? 0 : 120);
      }
    }
  }

  resetDomino() {
    this.dominoOn = false;
    for (const el of this.nodeEls.values()) el.classList.remove("fallen", "fade", "origin");
    for (const el of this.edgeEls) { el.classList.remove("domino", "hot"); if (el.dataset.kind === "SUPPORTS") el.setAttribute("marker-end", "url(#arrow)"); }
  }
}

function zigzag(a, b) {
  const n = 8, pts = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t;
    const off = i === 0 || i === n ? 0 : (i % 2 ? 5 : -5);
    const dx = b.y - a.y, dy = -(b.x - a.x), len = Math.hypot(dx, dy) || 1;
    pts.push(`${x + dx / len * off},${y + dy / len * off}`);
  }
  return "M" + pts.join(" L");
}
