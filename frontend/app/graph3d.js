// Case graph in 3D — every node and link comes from /graph and /alerts (no layout data is invented).
// Nodes: acts (colour = category), people, seals, alerts. Links: depends on (SUPPORTS), contradiction,
// involves, part of custody, alert → act. Hover = neighbourhood, click = details, slow rotation until touched.
import { CAT_FR, hm, dmy, esc, sleep, REDUCED } from "./ui.js";

export const CAT_COLOR = {
  TRAFFIC: "#EA580C", KEEPER: "#0D9488", COURT: "#475569",
  INTERPELLATION: "#A16207", GARDE_A_VUE: "#EA580C", AUDITION: "#D97706", PERQUISITION_SAISIE: "#2563EB",
  EXPERTISE: "#0D9488", GEOLOCALISATION: "#7C3AED", INTERCEPTIONS: "#DB2777", INSTRUCTION: "#475569", AUTRE: "#9CA3AF",
};
const C = { person: "#151524", seal: "#64748B", pn: "#E61300", nr: "#EAB308", dim: "#E7E5E4", fallen: "#9F1239", origin: "#151524" };
const LINK = { SUPPORTS: "#94A3B8", CONTRADICTS: "#E61300", INVOLVES: "#D6D3D1", PART_OF: "#E7E5E4", ALERT: "#FCA5A5" };

export class Graph3D {
  constructor(el, { onSelect }) {
    this.el = el;
    this.onSelect = onSelect;
    this.show = { PERSON: true, ITEM: true, ALERT: true, ISOLATED: false };
    this.fitted = false;
    this.hot = null;          // Set of ids highlighted (hover / selection)
    this.fallen = new Map();  // domino: id -> "fallen" | "origin"
    this.ready = typeof window.ForceGraph3D === "function";
    if (!this.ready) {
      el.innerHTML = `<div class="grid h-full place-items-center text-sm text-stone-500">3D view unavailable (could not load 3d-force-graph from the CDN). The timeline still works.</div>`;
      return;
    }
    this.g = window.ForceGraph3D({ controlType: "orbit" })(el)
      .backgroundColor("#ffffff")
      .showNavInfo(false)
      .nodeId("id")
      .nodeVal(n => n.val)
      .nodeRelSize(4)
      .nodeOpacity(0.95)
      .nodeResolution(16)
      .nodeColor(n => this.colorOf(n))
      .nodeLabel(n => this.tip(n))
      .linkColor(l => this.linkColor(l))
      .linkWidth(l => (this.hot && this.hot.has(l._s) && this.hot.has(l._t)) ? (l.kind === "SUPPORTS" ? 1.6 : 1) : l.kind === "CONTRADICTS" ? 1.2 : l.kind === "SUPPORTS" ? 0.6 : 0.25)
      .linkOpacity(0.55)
      .linkDirectionalArrowLength(l => l.kind === "SUPPORTS" ? 3 : 0)
      .linkDirectionalArrowRelPos(1)
      .linkDirectionalParticles(l => (l.kind === "SUPPORTS" && this.hot && this.hot.has(l._s) && this.hot.has(l._t)) || l._domino ? 3 : 0)
      .linkDirectionalParticleWidth(1.6)
      .linkDirectionalParticleColor(l => l._domino ? C.pn : "#151524")
      .onNodeHover(n => { el.style.cursor = n ? "pointer" : ""; if (!this.locked) this.highlight(n?.id ?? null); })
      .onNodeClick(n => { this.stopRotate(); this.focus(n.id); this.onSelect?.(n.raw ?? n); })
      .onBackgroundClick(() => { this.locked = false; this.highlight(null); });
    this.g.d3Force("charge").strength(-45);
    this.g.onEngineStop(() => { if (!this.fitted) { this.fitted = true; this.g.zoomToFit(600, 40); } });
    this.g.d3Force("link").distance(l => l.kind === "SUPPORTS" ? 34 : l.kind === "ALERT" ? 14 : 24);
    const ctl = this.g.controls();
    ctl.autoRotate = !REDUCED;
    ctl.autoRotateSpeed = 0.6;
    el.addEventListener("pointerdown", () => this.stopRotate());
    el.addEventListener("wheel", () => this.stopRotate(), { passive: true });
    new ResizeObserver(() => this.resize()).observe(el);
  }

  stopRotate() { if (this.g) this.g.controls().autoRotate = false; this.onRotate?.(false); }
  toggleRotate() { if (!this.g) return false; const c = this.g.controls(); c.autoRotate = !c.autoRotate; return c.autoRotate; }
  resize() { if (this.g && this.el.clientWidth) this.g.width(this.el.clientWidth).height(this.el.clientHeight); }

  setData(graph, alerts) {
    if (!this.ready) return;
    this.graph = graph;
    this.alerts = alerts;
    this.rebuild();
  }

  rebuild() {
    const { graph, alerts } = this;
    const alertsBy = new Map();
    for (const a of alerts) { const l = alertsBy.get(a.node.id) ?? []; l.push(a); alertsBy.set(a.node.id, l); }
    const nodes = [];
    for (const n of graph.nodes) {
      if (n.type !== "ACT" && !this.show[n.type]) continue;
      const al = alertsBy.get(n.id) ?? [];
      nodes.push({
        id: n.id, raw: n, kind: n.type, label: n.label, category: n.category,
        val: n.type === "PERSON" ? 9 : n.type === "ITEM" ? 1.6 : n.subtype === "garde_a_vue" ? 6 : 2.4 + Math.min(3, al.length),
        alerts: al,
      });
    }
    let ids = new Set(nodes.map(n => n.id));
    if (!this.show.ISOLATED) {  // acts with no link and no alert (annexes, complaints…) only add noise to the picture
      const linked = new Set(graph.edges.flatMap(e => [e.src, e.dst]));
      const keep = n => n.kind !== "ACT" || linked.has(n.id) || n.alerts.length;
      this.hidden = nodes.filter(n => !keep(n)).length;
      nodes.splice(0, nodes.length, ...nodes.filter(keep));
      ids = new Set(nodes.map(n => n.id));
    } else this.hidden = 0;
    if (this.show.ALERT) {
      for (const a of alerts) {
        if (!ids.has(a.node.id)) continue;
        const id = `alert:${a.key}`;
        nodes.push({ id, kind: "ALERT", alert: a, label: `${a.nullity_id} — ${a.title}`, val: a.status === "possible_nullity" ? 2.2 : 1.4 });
        ids.add(id);
      }
    }
    const links = [];
    for (const e of graph.edges) {
      if (!ids.has(e.src) || !ids.has(e.dst)) continue;
      links.push({ source: e.src, target: e.dst, _s: e.src, _t: e.dst, kind: e.kind, origin: e.origin, label: e.label });
    }
    if (this.show.ALERT) {
      for (const a of alerts) if (ids.has(a.node.id)) links.push({ source: `alert:${a.key}`, target: a.node.id, _s: `alert:${a.key}`, _t: a.node.id, kind: "ALERT" });
    }
    this.adj = new Map();
    for (const l of links) {
      if (!this.adj.has(l._s)) this.adj.set(l._s, new Set());
      if (!this.adj.has(l._t)) this.adj.set(l._t, new Set());
      this.adj.get(l._s).add(l._t); this.adj.get(l._t).add(l._s);
    }
    this.byId = new Map(nodes.map(n => [n.id, n]));
    this.links = links;
    this.g.graphData({ nodes, links });
    this.resize();
  }

  colorOf(n) {
    const f = this.fallen.get(n.id);
    if (f) return f === "origin" ? C.origin : C.fallen;
    if (this.fallen.size) return C.dim;
    if (this.hot && !this.hot.has(n.id)) return C.dim;
    if (n.kind === "PERSON") return C.person;
    if (n.kind === "ITEM") return C.seal;
    if (n.kind === "ALERT") return n.alert.status === "possible_nullity" ? C.pn : C.nr;
    return CAT_COLOR[n.category] ?? CAT_COLOR.AUTRE;
  }

  linkColor(l) {
    if (l._domino) return C.pn;
    const on = !this.hot || (this.hot.has(l._s) && this.hot.has(l._t));
    if (this.fallen.size && !l._domino) return "#F5F5F4";
    if (!on) return "#F5F5F4";
    return LINK[l.kind] ?? "#D6D3D1";
  }

  tip(n) {
    const box = (title, sub, extra = "") => `<div class="g3-tip"><b>${esc(title)}</b><small>${esc(sub)}</small>${extra}</div>`;
    if (n.kind === "ALERT") {
      const a = n.alert;
      return box(`${a.nullity_id} · ${a.title}`, `${a.status === "possible_nullity" ? "Possible nullity" : "To investigate"} · ${a.certainty_label}`, `<p>${esc(a.what)}</p>`);
    }
    const r = n.raw;
    if (n.kind === "PERSON") return box(r.label, `Person · ${(this.adj.get(n.id)?.size ?? 0)} linked acts`);
    if (n.kind === "ITEM") return box(r.label, `Seal · ${(this.adj.get(n.id)?.size ?? 0)} linked acts`);
    const when = r.start ? `${dmy(r.start)} ${hm(r.start)}` : "time unknown";
    const al = n.alerts.slice(0, 3).map(a => `<p class="${a.status === "possible_nullity" ? "pn" : "nr"}">⚠ ${esc(a.nullity_id)} — ${esc(a.title)}</p>`).join("");
    return box(r.label, `${CAT_FR[r.category]?.[0] ?? r.category} · ${when} · ${r.doc_ids.join(", ")}`, al);
  }

  highlight(id) {
    if (!this.g) return;
    if (!id || !this.byId?.has(id)) this.hot = null;
    else {
      this.hot = new Set([id, ...(this.adj.get(id) ?? [])]);
      // follow dependency chains (what this act supports / is supported by)
      const sup = this.links.filter(l => l.kind === "SUPPORTS");
      const walk = (start, dir) => {
        const st = [start];
        while (st.length) {
          const c = st.pop();
          for (const l of sup) {
            const [a, b] = dir ? [l._s, l._t] : [l._t, l._s];
            if (a === c && !this.hot.has(b)) { this.hot.add(b); st.push(b); }
          }
        }
      };
      walk(id, true); walk(id, false);
    }
    this.refresh();
  }

  refresh() { if (this.g) this.g.nodeColor(this.g.nodeColor()).linkColor(this.g.linkColor()).linkWidth(this.g.linkWidth()).linkDirectionalParticles(this.g.linkDirectionalParticles()); }

  focus(id, { lock = true } = {}) {
    const n = this.byId?.get(id);
    if (!n || n.x === undefined) return;
    this.locked = lock;
    this.highlight(id);
    const d = 110, r = 1 + d / Math.max(1, Math.hypot(n.x, n.y, n.z));
    this.g.cameraPosition({ x: n.x * r, y: n.y * r, z: n.z * r }, n, REDUCED ? 0 : 900);
  }

  async domino(sim, counterEl) {
    if (!this.g) return;
    this.resetDomino();
    this.stopRotate();
    this.fallen.set(sim.removed, "origin");
    this.focus(sim.removed, { lock: true });
    this.hot = null;
    this.refresh();
    let count = 0;
    for (let d = 1; d <= Math.max(1, sim.waves); d++) {
      await sleep(REDUCED ? 0 : 520);
      for (const a of sim.affected.filter(a => a.depth === d)) {
        this.fallen.set(a.id, "fallen");
        for (const l of this.links) if (l._s === a.parent && l._t === a.id) l._domino = true;
        count++;
        if (counterEl) counterEl.textContent = count;
      }
      this.refresh();
    }
  }

  resetDomino() {
    this.fallen.clear();
    for (const l of this.links ?? []) delete l._domino;
    this.refresh();
  }

  toggle(kind, on) { this.show[kind] = on; this.fitted = false; if (this.graph) this.rebuild(); }
}
