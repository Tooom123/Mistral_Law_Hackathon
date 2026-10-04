// BREACH — app shell: routing, war room → timeline, alerts, node drawer, time travel, modes, report, benchmark.
import { api } from "./api.js";
import { state, set } from "./state.js";
import { $, $$, h, CERT, VERDICT, ATTR_FR, CAT_FR, fmtVal, hm, dmy, toast, REDUCED } from "./ui.js";
import { startWarroom } from "./warroom.js";
import { Timeline } from "./timeline.js";
import { openAlert } from "./acard.js";
import { renderReport } from "./report.js";
import { renderBench } from "./bench.js";

const params = new URLSearchParams(location.search);
let timeline;
let stopWar = null;

// ------------------------------------------------------------------ boot
async function boot() {
  engines();
  const cid = params.get("case");
  if (params.get("demo") !== null) return launchDemo();
  if (!cid) return picker();
  set({ caseId: cid });
  const st = await api.status(cid).catch(() => null);
  if (!st) { toast("Case file not found."); return picker(); }
  $("#case-title").textContent = st.title ?? cid;
  if (st.state !== "done" || params.get("war") !== null) {
    stopWar = startWarroom(cid, () => {});
    $("#war-open").onclick = () => { stopWar?.(); history.replaceState(null, "", `?case=${cid}#graph`); openCase(); };
    if (st.state === "done") $("#war-open").disabled = false;
    return;
  }
  openCase();
}

async function launchDemo() {
  const { case_id, title } = await api.demo(1);
  history.replaceState(null, "", `?case=${case_id}`);
  set({ caseId: case_id });
  $("#case-title").textContent = title;
  stopWar = startWarroom(case_id, () => {});
  $("#war-open").onclick = () => { stopWar?.(); history.replaceState(null, "", `?case=${case_id}#graph`); openCase(); };
}

async function picker() {
  $("#picker").hidden = false;
  $("#picker-demo").onclick = () => { $("#picker").hidden = true; launchDemo(); };
  const list = await api.cases().catch(() => []);
  $("#picker-list").replaceChildren(...list.filter(c => c.state === "done").slice(0, 12).map(c =>
    h("li", {}, h("a", { href: `?case=${c.case_id}#graph` }, h("span", {}, c.title ?? c.case_id), h("small", {}, `${c.pages ?? "?"} pages`), h("small", {}, `${c.alerts ?? 0} alerts`)))));
}

async function engines() {
  const e = await api.engines().catch(() => ({}));
  const r = await api.reforms().catch(() => []);
  set({ engines: e, reforms: r });
  const dots = [["mistral", "Mistral"], ["tesseract", "OCR"], ["jev", "Jev"], ["judilibre", "Judilibre"], ["lean", "Lean"]];
  $("#engines-dots").replaceChildren(...dots.map(([k]) => h("i", { class: e[k] ? "on" : "" })));
  const rows = [
    ["mistral", "Mistral (OCR, extraction, judge, tribunal)", e.mistral ? "key present" : "offline"],
    ["tesseract", "Local OCR (Tesseract)", e.tesseract ? "installed" : "missing"],
    ["jev", "Jev — typed judge (TypeSafe AI)", e.jev ? "key present" : "offline"],
    ["judilibre", "Judilibre — precedents", e.judilibre ? "key present" : "offline"],
    ["lean", "Lean 4 — proof kernel", e.lean ? "installed" : "missing"],
    ["leanstral", "Leanstral — Mistral prover", e.leanstral ? "active" : "inactive"],
    ["pseudonymize", "Pseudonymisation before any external call", e.pseudonymize ? "on" : "off"],
  ];
  $("#engines-pop").replaceChildren(h("h4", {}, "Engines"), h("ul", {}, rows.map(([k, l, v]) => h("li", {}, h("i", { class: e[k] ? "on" : "" }), h("span", {}, l), h("small", {}, v)))),
    h("p", {}, "Everything works without keys. Mistral, Jev and Judilibre only switch on when their keys are in .env."));
  $("#engines-btn").onclick = ev => { ev.stopPropagation(); $("#engines-pop").hidden = !$("#engines-pop").hidden; };
  document.addEventListener("click", ev => { if (!ev.target.closest("#engines-pop")) $("#engines-pop").hidden = true; });
}

// ------------------------------------------------------------------ case
async function openCase() {
  $("#warroom").hidden = true;
  $("#main").hidden = false;
  timeline ??= new Timeline({
    svg: $("#timeline"), labels: $("#lane-labels"), scroll: $("#timeline-scroll"), tooltip: $("#tooltip"),
    onSelect: n => openNode(n),
  });
  await refresh({ first: true });
  route();
}

async function refresh({ first = false } = {}) {
  const o = { as_of: state.asOf, pseudo: state.pseudo };
  const [graph, al] = await Promise.all([api.graph(state.caseId, o), api.alerts(state.caseId, { ...o, mode: state.mode })]);
  const before = new Set(state.alerts.map(a => a.key));
  set({ graph, alerts: al.alerts, deadline: al.deadline, title: graph.title });
  $("#case-title").textContent = graph.title;
  document.title = `BREACH — ${graph.title}`;
  timeline.setData(graph, al.alerts);
  renderAlerts(first ? null : before);
  renderDeadline();
  renderDense();
  $("#tab-count").textContent = al.counts.possible_nullity || "";
  $("#alerts-hand").textContent = `${al.counts.possible_nullity} possible · ${al.counts.needs_reading} to read`;
  if (first) {
    setupTimeTravel();
    prefetchVerdicts();
    const top = al.alerts[0];
    if (top) setTimeout(() => timeline.select(top.node.id), 300);
  }
  if (location.hash === "#report") renderReport();
}

async function prefetchVerdicts() {
  for (const a of state.alerts) {
    if (state.verdicts[a.id]) continue;
    try {
      const t = await api.tribunal(state.caseId, a.key);
      state.verdicts[a.id] = t.presiding.verdict;
      const li = $(`.al[data-key="${CSS.escape(a.key)}"] .al__verdict`);
      if (li) li.replaceChildren(stamp(t.presiding.verdict));
    } catch { /* optional */ }
  }
}

const stamp = v => h("span", { class: `stamp ${VERDICT[v]?.[1] ?? ""}`, title: "Verdict of the simulated tribunal" }, VERDICT[v]?.[0] ?? v);

// ------------------------------------------------------------------ alerts list
function renderAlerts(before) {
  const ol = $("#alert-list");
  const f = state.filter;
  const list = state.alerts.filter(a => f === "all" || a.status === f || (f === "accepted" && a.review?.decision === "accepted"));
  ol.replaceChildren(...list.map((a, i) => {
    const [cl, cc] = CERT[a.certainty];
    const li = h("li", {
      class: `al ${a.status === "needs_reading" ? "nr" : ""} ${a.review?.decision === "rejected" ? "rejected" : ""}`, "data-key": a.key, tabindex: 0,
      style: { animationDelay: before && before.has(a.key) ? "0s" : `${Math.min(i, 12) * 40}ms` },
      onclick: () => { timeline.select(a.node.id); markSel(a.key); openAlert(a.key, { onSimulate: simulate, onReviewed: () => refresh() }); },
      onmouseenter: () => timeline.select(a.node.id, { scroll: false }),
      onkeydown: e => { if (e.key === "Enter") e.currentTarget.click(); },
    },
      h("div", { class: "al__rank" }, "#", h("b", {}, String(i + 1).padStart(2, "0"))),
      h("div", {},
        h("div", { class: "al__top" }, h("span", { class: "pill pill--id" }, a.nullity_id), h("span", { class: "al__title" }, a.title)),
        h("p", { class: "al__what" }, a.what),
        h("div", { class: "al__meta" },
          h("span", { class: `pill ${cc}` }, cl),
          a.why.affected_count ? h("span", { class: "pill pill--aff" }, `${a.why.affected_count} act${a.why.affected_count > 1 ? "s" : ""} ↘`) : null,
          ...[...new Set(a.where.map(s => s.page))].slice(0, 3).map(p => h("span", { class: "pill pill--page" }, `p. ${p}`)),
          a.review?.decision === "accepted" ? h("span", { class: "pill pill--acc" }, "accepted") : null,
          a.review?.decision === "rejected" ? h("span", { class: "pill pill--rej" }, "dismissed") : null)),
      h("span", { class: "al__verdict" }, state.verdicts[a.id] ? stamp(state.verdicts[a.id]) : null));
    if (before && !before.has(a.key)) li.style.outline = "2px solid var(--orange)";
    return li;
  }));
  if (!list.length) ol.append(h("li", { class: "muted", style: { padding: "20px 6px" } }, "No alert for this filter."));
}
const markSel = key => $$(".al").forEach(el => el.classList.toggle("sel", el.dataset.key === key));

$("#filters").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  $$("#filters button").forEach(x => x.classList.toggle("is-on", x === b));
  set({ filter: b.dataset.f });
  renderAlerts(new Set(state.alerts.map(a => a.key)));
});

// ------------------------------------------------------------------ deadline
function renderDeadline() {
  const dl = state.deadline, box = $("#deadline");
  if (!dl?.anchors?.length) {
    box.replaceChildren(h("div", { class: "deadline__top" }, h("span", { class: "deadline__label" }, "Nullity deadline"), h("span", { class: "deadline__stamp" }, "to verify")),
      h("p", { class: "deadline__note" }, "No formal charge in the file: no anchor for the deadline."));
    return;
  }
  const a = dl.anchors[0];
  const [r4, r6] = a.regimes;
  const total = (new Date(r4.deadline) - new Date(a.anchor)) / 864e5;
  const pct = Math.min(100, Math.max(0, (1 - r4.days_left / total) * 100));
  box.replaceChildren(
    h("div", { class: "deadline__top" }, h("span", { class: "deadline__label" }, `Nullity deadline · ${dl.article}`), h("span", { class: "deadline__stamp" }, "to verify")),
    h("div", { class: "deadline__row" },
      h("span", { class: "deadline__j" }, r4.days_left >= 0 ? `D-${r4.days_left}` : `D+${-r4.days_left}`),
      h("span", { class: "deadline__d" }, `${r4.months} months → ${dmy(r4.deadline)}`, h("small", {}, r4.label)),
      h("span", { class: "deadline__j alt" }, r6.days_left >= 0 ? `D-${r6.days_left}` : `D+${-r6.days_left}`),
      h("span", { class: "deadline__d" }, `${r6.months} months → ${dmy(r6.deadline)}`, h("small", {}, r6.label))),
    h("div", { class: "deadline__bar", title: `Today: ${dmy(dl.today)}` }, h("i", { style: { width: `${pct}%` } }), h("em", { style: { left: `${pct}%` } })),
    h("p", { class: "deadline__note" }, `${a.person} formally charged on ${dmy(a.anchor)}${dl.anchors.length > 1 ? ` (+${dl.anchors.length - 1} other)` : ""}. ${dl.note}`));
}

// ------------------------------------------------------------------ node drawer
function openNode(n) {
  timeline.select(n.id, { scroll: false });
  const box = $("#node-drawer");
  box.classList.remove("node-drawer--right");
  const attrs = Object.entries(n.attrs ?? {}).filter(([k]) => !["custody_id", "_conflict_sources"].includes(k));
  const checks = n.checks ?? [];
  const icon = { satisfied: "✓", possible_nullity: "!", needs_reading: "?", not_applicable: "–" };
  const cls = { satisfied: "ok", possible_nullity: "pn", needs_reading: "nr" };
  box.replaceChildren(
    h("div", { class: "nd__head" },
      h("div", {}, h("span", { class: "mono", style: { color: "var(--orange)" } }, `${CAT_FR[n.category]?.[0] ?? n.category} · ${n.framework}`),
        h("h3", {}, n.label), h("span", { class: "mono", style: { color: "var(--ink-3)" } }, `${n.start ? dmy(n.start) + " " + hm(n.start) : "heure ?"}${n.end ? " → " + dmy(n.end) + " " + hm(n.end) : ""} · ${n.doc_ids.join(", ")}`)),
      h("button", { class: "nd__close", onclick: () => { box.hidden = true; }, title: "Fermer" }, "×")),
    h("div", { class: "nd__body" },
      h("div", { class: "nd__sec" }, `Checklist — ${CAT_FR[n.category]?.[0] ?? ""}`),
      checks.length ? h("ul", { class: "checklist" }, checks.map(c => h("li", { class: cls[c.status] ?? "" },
        h("span", { class: "ic" }, icon[c.status] ?? "·"), h("b", {}, c.nullity_id),
        h("span", {}, c.statement, " ", c.alert ? h("a", { onclick: () => openAlert(c.alert, { onSimulate: simulate, onReviewed: () => refresh() }) }, "ouvrir →") : null)))) :
        h("p", { class: "muted" }, "No check applies to this type of act."),
      h("div", { class: "nd__sec" }, "Attributes — each with its page and quote"),
      h("table", { class: "attrs" }, attrs.map(([k, a]) => h("tr", {},
        h("td", {}, ATTR_FR[k] ?? k),
        h("td", {}, h("span", { class: "v" }, fmtVal(k, a.value)), a.status !== "explicit" ? h("span", { class: "st" }, ` · ${{ missing: "missing", unreadable: "unreadable", inferred: "inferred" }[a.status] ?? a.status}`) : null,
          a.src ? h("span", { class: "q" }, `“${a.src.quote}” — ${a.src.doc_id}, p. ${a.src.page}`) : null)))),
      h("div", { class: "nd__actions" },
        h("button", { class: "btn btn--primary btn--sm", onclick: () => simulate(n.id) }, "Simulate impact"),
        h("button", { class: "btn btn--sm", onclick: () => { box.hidden = true; timeline.resetDomino(); $("#domino-sticker").hidden = true; } }, "Restore"))));
  box.hidden = false;
}

async function simulate(nodeId) {
  location.hash = "#graph";
  route();
  const sim = await api.simulate(state.caseId, nodeId);
  if (!sim.count) { toast("No act depends on this one in the graph."); return; }
  $("#node-drawer").hidden = true;
  await timeline.domino(sim, $("#domino-sticker"), $("#domino-n"));
  const n = state.graph.nodes.find(x => x.id === nodeId);
  const box = $("#node-drawer");
  box.classList.add("node-drawer--right");
  box.replaceChildren(
    h("div", { class: "nd__head" }, h("div", {}, h("span", { class: "mono", style: { color: "var(--red)" } }, "Domino effect · art. 174 CPP (logic)"),
      h("h3", {}, `${sim.count} act(s) potentially affected`), h("span", { class: "mono", style: { color: "var(--ink-3)" } }, `if “${n?.label ?? nodeId}” falls — ${sim.waves} wave(s)`)),
      h("button", { class: "nd__close", onclick: resetSim }, "×")),
    h("div", { class: "nd__body" },
      h("div", { class: "nd__sec" }, "Acts to name in the request"),
      h("ol", { class: "casc" }, sim.affected.map(x => h("li", { class: x.origin === "llm_inferred" ? "llm" : "" },
        h("span", {}, h("span", { class: "depth", style: { "--d": x.depth - 1 } }), x.label, h("span", { class: "via" }, x.via || "dependency")),
        h("span", { class: "mono" }, x.doc_ids.join(", "))))),
      h("p", { class: "muted" }, "\"Potentially\": whether an act is a necessary support is for the judge. Structural and cited links are solid; links inferred by a model are dashed."),
      h("div", { class: "nd__actions" }, h("button", { class: "btn btn--sm", onclick: resetSim }, "Restore the case file"))));
  box.hidden = false;
}

function resetSim() {
  timeline.resetDomino();
  $("#domino-sticker").hidden = true;
  $("#node-drawer").hidden = true;
}

// ------------------------------------------------------------------ toggles: mode, pseudo, time travel, zoom
$("#mode-seg").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b || b.classList.contains("is-on")) return;
  $$("#mode-seg button").forEach(x => { x.classList.toggle("is-on", x === b); x.setAttribute("aria-checked", x === b); });
  $("#mode-seg").dataset.mode = b.dataset.mode;
  set({ mode: b.dataset.mode });
  toast(b.dataset.mode === "prosecution" ? "Prosecution mode: the same graph, read as a regularity audit before closing the investigation." : "Defence mode: grounds of nullity to examine.");
  await refresh();
  if (location.hash === "#report") renderReport();
});

$("#pseudo-toggle").addEventListener("click", async e => {
  const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
  e.currentTarget.setAttribute("aria-pressed", on);
  set({ pseudo: on });
  toast(on ? "Pseudonymisation: names, addresses and dates of birth hidden on screen — and before any external call." : "Showing names in clear.");
  await refresh();
});

function setupTimeTravel() {
  const range = $("#asof-range"), out = $("#asof-out"), tt = $("#timetravel");
  const min = new Date("2022-01-01").getTime();
  const max = new Date(state.deadline?.today ?? Date.now()).getTime();
  const toDate = v => new Date(min + (max - min) * v / 100);
  const toVal = d => ((new Date(d) - min) / (max - min)) * 100;
  $("#asof-marks").replaceChildren(...state.reforms.filter(r => new Date(r.date) > min && new Date(r.date) < max).map(r =>
    h("i", { style: { left: `${toVal(r.date)}%` }, title: `${dmy(r.date)} — ${r.rules.join(", ")}` }, h("span", {}, dmy(r.date).slice(3)))));
  const label = () => { out.textContent = state.asOf ? dmy(state.asOf) : "—"; };
  let t;
  range.oninput = () => {
    let d = toDate(+range.value);
    for (const r of state.reforms) if (Math.abs(new Date(r.date) - d) < 25 * 864e5) d = new Date(r.date); // snap to reforms
    set({ asOf: d.toISOString().slice(0, 10) });
    label();
    clearTimeout(t);
    t = setTimeout(async () => {
      const n0 = state.alerts.filter(a => a.status === "possible_nullity").length;
      await refresh();
      const n1 = state.alerts.filter(a => a.status === "possible_nullity").length;
      if (n0 !== n1) toast(`Law as of ${dmy(state.asOf)}: ${n1} possible nullit${n1 === 1 ? "y" : "ies"} (${n1 - n0 > 0 ? "+" : ""}${n1 - n0}).`);
    }, 220);
  };
  $("#asof-seg").onclick = async e => {
    const b = e.target.closest("button");
    if (!b) return;
    $$("#asof-seg button").forEach(x => x.classList.toggle("is-on", x === b));
    if (b.dataset.asof === "auto") { tt.setAttribute("aria-disabled", "true"); set({ asOf: null }); label(); await refresh(); }
    else { tt.setAttribute("aria-disabled", "false"); range.value = toVal("2023-06-01"); range.oninput(); }
  };
  label();
}

let zoom = 1;
const zooms = [.5, .75, 1, 1.5, 2, 3];
$("#zoom-in").onclick = () => { zoom = zooms[Math.min(zooms.length - 1, zooms.indexOf(zoom) + 1)]; $("#zoom-label").textContent = `${zoom}×`; timeline.setZoom(zoom); };
$("#zoom-out").onclick = () => { zoom = zooms[Math.max(0, zooms.indexOf(zoom) - 1)]; $("#zoom-label").textContent = `${zoom}×`; timeline.setZoom(zoom); };
$("#timeline-scroll").addEventListener("wheel", e => {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  (e.deltaY < 0 ? $("#zoom-in") : $("#zoom-out")).click();
}, { passive: false });

// ------------------------------------------------------------------ dense list
function renderDense() {
  const t = $("#dense");
  $("#alerts-eyebrow").textContent = state.mode === "prosecution" ? "Regularity audit" : "Grounds to examine";
  $("#alerts-h1").textContent = state.mode === "prosecution" ? "Regularity issues to fix" : "All alerts, ranked";
  t.replaceChildren(
    h("thead", {}, h("tr", {}, ["", "#", "Rule", "Finding", "Pages", "Certainty", "Affected", "Article", "Decision"].map(x => h("th", {}, x)))),
    h("tbody", {}, state.alerts.map((a, i) => h("tr", { onclick: () => openAlert(a.key, { onSimulate: simulate, onReviewed: () => refresh() }) },
      h("td", { class: `st ${a.status === "needs_reading" ? "nr" : "pn"}` }),
      h("td", { class: "mono" }, String(i + 1).padStart(2, "0")),
      h("td", {}, h("b", {}, a.nullity_id), h("div", { class: "muted" }, a.title)),
      h("td", {}, a.what),
      h("td", { class: "mono" }, [...new Set(a.where.map(s => s.page))].join(", ")),
      h("td", {}, h("span", { class: `pill ${CERT[a.certainty][1]}` }, CERT[a.certainty][0])),
      h("td", { class: "mono" }, a.why.affected_count || "—"),
      h("td", { class: "mono" }, a.why.article),
      h("td", {}, a.review?.decision === "accepted" ? "accepted" : a.review?.decision === "rejected" ? "dismissed" : "—")))));
}

// ------------------------------------------------------------------ routing
function route() {
  const v = (location.hash || "#graph").slice(1);
  const view = ["graph", "alerts", "report", "bench"].includes(v) ? v : "graph";
  $$(".view").forEach(s => { s.hidden = s.dataset.view !== view; });
  $$(".tab").forEach(t => t.classList.toggle("is-on", t.dataset.view === view));
  if (view === "report") renderReport();
  if (view === "bench") renderBench();
}
window.addEventListener("hashchange", () => { if (!$("#main").hidden) route(); });

boot().catch(e => { console.error(e); toast(`Error: ${e.message}`); });
void REDUCED;
