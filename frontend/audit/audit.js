import { Flow } from "../app/flow.js";

/* BREACH — conflict-of-interest audit.
   Data: GET /api/coi/cases/{case} (falls back to the snapshot in audit/data/ when the API is not running).
   Timeline = the case graph collage (app/flow.js): one paper tile per document, a row per category, in time order;
   the selected flag's documents are joined in pen, its first line to read is the taped red tile.
   Click a tile → the document, with the exact lines highlighted and annotated in the margin. Flags → chain, evidence, comparable past cases, next steps. */

const API = window.BREACH_API ?? "";
const params = new URLSearchParams(location.search);
const CASE = params.get("case") || "mckinsey";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const parse = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const fmtDay = x => `${String(x.getDate()).padStart(2, "0")} ${MONTHS[x.getMonth()]} ${x.getFullYear()}`;
const fmtMonth = x => `${MONTHS[x.getMonth()]} ${x.getFullYear()}`;
const dmy = x => `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}/${x.getFullYear()}`;
const STICKER = { dual_role: "dual role", undeclared_interest: "false decl.", missing_declaration: "missing", revolving_door: "revolving", family_tie: "relative", false_statement: "under oath" };
// the document a flag sends you to first
const PRIMARY = ["declared", "statement", "signature", "private engagement", "missing", "declared tie"];
const primary = f => f.evidence.find(e => PRIMARY.includes(e.role)) ?? f.evidence[0];
const CERT = { documented: "Documented", inferred: "Inferred", needs_reading: "Needs reading" };
const KIND_LABEL = { person: "person", company: "company", public: "public order", doc: "document" };

const S = { data: null, flag: null, doc: null, focus: null, live: false, precedents: null, precFilter: { pattern: null, prov: null } };

/* ================================================================ data */

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

async function load() {
  try {
    S.data = await getJSON(`${API}/api/coi/cases/${CASE}`);
    S.live = true;
  } catch {
    S.data = await getJSON(`audit/data/${CASE}.json`);
  }
  S.byDoc = Object.fromEntries(S.data.documents.map(d => [d.id, d]));
  S.byFlag = Object.fromEntries(S.data.flags.map(f => [f.id, f]));
  S.docOrder = [...S.data.documents].sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id)).map(d => d.id);
  if (S.live && !S.data.flags.some(f => f.note)) {
    // reviewer notes (Mistral) arrive after the first paint
    getJSON(`${API}/api/coi/cases/${CASE}?llm=true`).then(full => {
      for (const f of full.flags) if (f.note && S.byFlag[f.id]) S.byFlag[f.id].note = f.note;
      S.data.engine = full.engine;
      renderEngine();
      if (S.flag) renderDetail(S.flag, false);
    }).catch(() => {});
  }
}

/* ================================================================ header + strip */

function renderHeader() {
  const { case: c, stats: st, flags } = S.data;
  $("#case-title").textContent = `${c.title} — ${c.subtitle}`;
  document.title = `BREACH — ${c.title}`;
  $("#tab-flags").textContent = flags.length;
  $("#tab-prec").textContent = "";
  const cells = [
    [st.documents, "documents read"], [st.flags, "potential conflicts", "alert"],
    [st.cross_references, "lines to read"], [st.cleared, "checks cleared", "ok"],
  ];
  $("#strip").innerHTML = cells.map(([n, l, k]) => `<div class="stat ${k ? "stat--" + k : ""}"><b>${n}</b><span>${l}</span></div>`).join("");
  renderEngine();
}

function renderEngine() {
  const e = S.data.engine || {};
  $("#engine").innerHTML = `<i></i>${S.live ? "live" : "offline"}${e.notes === "mistral" ? " · Mistral" : ""}`;
  $("#engine").title = `${e.extraction || ""} · ${e.precedents || ""}`;
}

/* ================================================================ timeline (paper collage) */

let flow = null;

function flowData() {
  const all = $("#tl-all").checked;
  const f = S.flag && S.byFlag[S.flag];
  const lane = Object.fromEntries(S.data.lanes.map(l => [l.id, l.label]));
  const docs = S.docOrder.map(id => S.byDoc[id]).filter(d => all || d.flags.length);
  const nodes = docs.map(d => ({
    id: d.id, type: "ACT", category: lane[d.lane], label: d.short, start: `${d.date}T00:00:00`, doc_ids: [d.id],
    dateLabel: d.precision === "month" ? fmtMonth(parse(d.date)) : dmy(parse(d.date)),
  }));
  const shown = new Set(docs.map(d => d.id));
  const edges = [], alerts = [];
  if (f) {
    const chain = S.docOrder.filter(id => f.docs.includes(id) && shown.has(id));
    for (let i = 1; i < chain.length; i++) edges.push({ kind: "SUPPORTS", src: chain[i - 1], dst: chain[i] });
    const main = primary(f).doc;
    for (const id of chain) {
      alerts.push(id === main
        ? { node: { id }, status: "possible_nullity", key: f.id, sticker: { big: f.id, small: STICKER[f.pattern] ?? "" } }
        : { node: { id }, status: "needs_reading", key: f.id, noSticker: true });
    }
  }
  return { graph: { lanes: S.data.lanes.map(l => l.label), nodes, edges }, alerts };
}

function renderTimeline() {
  flow ??= new Flow($("#flow"), {
    padBottom: 40,
    onSelect: n => openDoc(n.id, S.flag && S.byFlag[S.flag].docs.includes(n.id) ? { flag: S.flag } : null),
    onAlert: key => { const e = primary(S.byFlag[key]); openDoc(e.doc, { flag: key, span: e }); },
  });
  const { graph, alerts } = flowData();
  flow.setData(graph, alerts);
  if (S.doc) flow.select(S.doc);
}

const TL = { redraw: () => flow && renderTimeline() };

/* ================================================================ tooltip */

const tip = $("#tip");
function showTip(ev, html) { tip.innerHTML = html; tip.hidden = false; moveTip(ev); }
function moveTip(ev) {
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(innerWidth - w - 10, ev.clientX + 14) + "px";
  tip.style.top = (ev.clientY + h + 24 > innerHeight ? ev.clientY - h - 12 : ev.clientY + 16) + "px";
}
function hideTip() { tip.hidden = true; }

/* ================================================================ flags */

function renderFlags() {
  $("#flag-list").innerHTML = S.data.flags.map(f => `
    <li class="fl sev-${f.severity}" data-flag="${f.id}" tabindex="0">
      <span class="fl__id">${f.id}</span>
      <span class="fl__h">${esc(f.headline)}</span>
      <span class="fl__meta"><span class="chip">${esc(f.pattern_label)}</span></span>
    </li>`).join("");
  $$("#flag-list .fl").forEach(li => {
    li.addEventListener("click", e => {
      const chip = e.target.closest(".chip--doc");
      if (chip) { e.stopPropagation(); selectFlag(chip.dataset.flag, false); openDoc(chip.dataset.doc, { flag: chip.dataset.flag }); return; }
      selectFlag(li.dataset.flag);
    });
    li.addEventListener("keydown", e => { if (e.key === "Enter") selectFlag(li.dataset.flag); });
  });
  $("#cleared-n").textContent = S.data.cleared.length;
  $("#cleared-list").innerHTML = S.data.cleared.map((c, i) =>
    `<li>${esc(c.text)}<button data-i="${i}" type="button">${c.src.doc} p.${c.src.page}</button></li>`).join("");
  $$("#cleared-list button").forEach(b => b.addEventListener("click", () => {
    const c = S.data.cleared[+b.dataset.i];
    openDoc(c.src.doc, { span: c.src, ok: true });
  }));
}

function selectFlag(id, scroll = true) {
  S.flag = S.flag === id && scroll ? null : id;
  $$("#flag-list .fl").forEach(li => li.classList.toggle("is-on", li.dataset.flag === S.flag));
  renderDetail(S.flag, scroll);
  renderTimeline();
  if (S.flag) history.replaceState(null, "", `#flag=${S.flag}`);
}

function renderDetail(id, scroll) {
  const el = $("#detail");
  if (!id) {
    el.innerHTML = `<div class="empty"><p class="mono">Select a flag</p><p class="muted">The chain, the exact lines, comparable past cases and what to check next.</p></div>`;
    return;
  }
  const f = S.byFlag[id];
  const ev = f.evidence.map((e, i) => `
    <li class="ev" data-i="${i}">
      <div class="ev__top"><span class="ev__ref">${e.doc} · p.${e.page} — ${esc(S.byDoc[e.doc].title.split(" — ")[0])}</span><span class="ev__role">${esc(e.role)}</span></div>
      <div class="ev__label">${esc(e.label)}</div>
      <p class="ev__q">${esc(e.quote)}</p>
    </li>`).join("");
  const evShort = f.evidence.slice(0, 5).map((e, i) => `
    <li class="ev" data-i="${i}">
      <div class="ev__top"><span class="ev__label">${esc(e.label)}</span><span class="ev__ref">${e.doc} p.${e.page}</span></div>
      <p class="ev__q">${esc(e.quote)}</p>
    </li>`).join("");
  const more = f.evidence.length > 5 ? `<details class="more"><summary>${f.evidence.length - 5} more lines</summary><ol class="evs">${ev.split('<li class="ev"').slice(6).map(x => '<li class="ev"' + x).join("")}</ol></details>` : "";
  el.innerHTML = `
    <div class="sev-${f.severity}">
      <div class="d__top">
        <span class="fl__id">${f.id}</span>
        <span class="chip">${esc(f.pattern_label)}</span>
        <span class="cert cert--${f.certainty}">${CERT[f.certainty]}</span>
      </div>
      <h3 class="d__h">${esc(f.headline)}</h3>
      <p class="d__sum">${esc(f.summary)}</p>
      <div class="d__grid">
        <div>
          <div class="d__sec">${chainSVG(f)}</div>
          <div class="d__sec"><h4>Where to look</h4><ol class="evs">${evShort}</ol>${more}</div>
        </div>
        <div>
          <div class="d__sec"><h4>Similar past cases</h4><ol class="pcs">${[f.precedents[0], f.precedents.find(p => p.provenance === "public_record" && p !== f.precedents[0]) ?? f.precedents[1]].filter(Boolean).map(p => precCard(p, true)).join("")}</ol></div>
          <div class="d__sec"><h4>Next steps</h4><ul class="next">${f.next.map((n, i) => `<li><input type="checkbox" id="nx-${f.id}-${i}"><label for="nx-${f.id}-${i}">${esc(n)}</label></li>`).join("")}</ul></div>
          ${f.note ? `<details class="more"><summary>✦ Mistral reviewer note</summary><div class="note">${md(f.note.text)}</div></details>` : ""}
          <details class="more"><summary>Legal framework</summary><ul class="legal">${f.legal.map(l => `<li><b>${esc(l.ref)}</b>${esc(l.text)}</li>`).join("")}</ul></details>
        </div>
      </div>
      <div class="d__actions">
        <button class="btn btn--primary" type="button" id="d-open">Open the document →</button>
        <button class="btn" type="button" id="d-memo">Export memo</button>
        <span class="disclaimer">To review — the lawyer decides.</span>
      </div>
    </div>`;
  $$(".ev", el).forEach(li => li.addEventListener("click", () => {
    const e = f.evidence[+li.dataset.i];
    openDoc(e.doc, { flag: f.id, span: e });
  }));
  $$(".chain .l.is-doc", el).forEach(g => g.addEventListener("click", () => openDoc(g.dataset.doc, { flag: f.id })));
  $("#d-open").onclick = () => { const e = primary(f); openDoc(e.doc, { flag: f.id, span: e }); };
  $("#d-memo").onclick = () => download(`${CASE}-${f.id}.md`, memo(f));
  if (scroll) $("#view-flags").scrollIntoView({ behavior: "smooth", block: "start" });
}

function md(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>").replace(/«\s*(.+?)\s*»/g, "« <i>$1</i> »");
}

function chainSVG(f) {
  const { nodes, links } = f.chain;
  const W = 560, bw = 150, bh = 46, gap = (W - 20 - bw * nodes.length) / Math.max(1, nodes.length - 1);
  const pos = Object.fromEntries(nodes.map((n, i) => [n.id, { x: 10 + i * (bw + gap), y: 70 }]));
  const H = 190;
  const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const idx = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  const ls = links.map((l, k) => {
    const a = pos[l.s], b = pos[l.t];
    const adj = Math.abs(idx[l.s] - idx[l.t]) === 1;
    const [x1, x2] = idx[l.s] < idx[l.t] ? [a.x + bw / 2, b.x + bw / 2] : [a.x + bw / 2, b.x + bw / 2];
    const up = adj;
    const y = up ? a.y : a.y + bh;
    const cy = up ? y - 52 : y + 52;
    const mx = (x1 + x2) / 2, my = up ? y - 39 : y + 39;
    const label = trunc(l.label, 30);
    const lw = label.length * 5.7 + 10;
    return `<g class="l ${l.doc ? "is-doc" : ""}" ${l.doc ? `data-doc="${l.doc}"` : ""}>
      <path d="M${x1},${y} Q${mx},${cy} ${x2},${y}" marker-end="url(#arr)"/>
      <rect class="lbg" x="${mx - lw / 2}" y="${my - 9}" width="${lw}" height="15" rx="4"/>
      <text x="${mx}" y="${my + 2}" text-anchor="middle">${esc(label)}${l.doc ? ` · ${l.doc}` : ""}</text></g>`;
  }).join("");
  const ns = nodes.map(n => `<g class="n k-${n.kind}" transform="translate(${pos[n.id].x},${pos[n.id].y})">
      <rect width="${bw}" height="${bh}" rx="9"/>
      <text class="k" x="12" y="17">${KIND_LABEL[n.kind] || n.kind}</text>
      <text x="12" y="34">${esc(trunc(n.id, 22))}</text></g>`).join("");
  return `<svg class="chain" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chain of the flag">
    <defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8A8A96"/></marker></defs>
    ${ls}${ns}</svg>`;
}

function precCard(p, compact) {
  const prov = p.provenance === "public_record" ? `<span class="chip chip--public">public record</span>` : `<span class="chip chip--syn">simulated scenario</span>`;
  const why = p.why ? [...(p.why.patterns || []).map(x => `<span class="chip">${esc(x)}</span>`),
    ...(p.why.signals || []).slice(0, 3).map(x => `<span class="chip chip--ok">${esc(x)}</span>`)].join("") : "";
  const score = p.score != null ? `<span class="score" title="similarity">${Math.round(p.score * 100)}<i style="--w:${Math.round(Math.min(1, p.score) * 100)}%"></i></span>` : "";
  return `<li class="pc">
    <div class="pc__top">${prov}<span class="chip">${esc(p.jurisdiction)} · ${p.year}</span>${compact ? "" : `<span class="chip">${esc(p.kind)}</span>`}${score}</div>
    <div class="pc__t">${esc(p.title)}</div>
    <div class="pc__c">${esc(p.citation)}</div>
    ${compact ? "" : `<p class="pc__f">${esc(p.facts)}</p><p class="pc__o"><b>Outcome.</b> ${esc(p.outcome)}</p>`}
    <p class="pc__l">${compact ? "" : "<b>Lesson.</b> "}${esc(p.lesson)}</p>
    ${why && !compact ? `<div class="pc__why">${why}</div>` : ""}
  </li>`;
}

function memo(f) {
  const t = d => S.byDoc[d].title;
  return [`# ${f.id} — ${f.title}`, "", `**${f.headline}**  `,
    `Severity: ${f.severity} · certainty: ${CERT[f.certainty]} · pattern: ${f.pattern_label}`, "", f.summary, "",
    ...(f.aggravating.length ? ["## Aggravating elements", ...f.aggravating.map(a => `- ${a}`), ""] : []),
    "## Where to look", "", ...f.evidence.map(e => `- **${e.doc} p.${e.page}** — ${t(e.doc)} · _${e.role}_  \n  > ${e.quote}`), "",
    "## Framework", ...f.legal.map(l => `- **${l.ref}** — ${l.text}`), "",
    "## Comparable cases", ...f.precedents.map(p => `- **${p.citation}** (${p.jurisdiction}, ${p.year}${p.provenance === "synthetic" ? ", simulated" : ""}) — ${p.lesson}`), "",
    "## Next steps", ...f.next.map(n => `- [ ] ${n}`), "",
    "_Potential conflict of interest, to review. The legal qualification belongs to the reviewing lawyer._"].join("\n");
}

function download(name, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ================================================================ document drawer */

function openDoc(id, opts = null) {
  const d = S.byDoc[id];
  if (!d) return;
  S.doc = id;
  S.focus = opts;
  const drawer = $("#drawer");
  drawer.hidden = false;
  $("#doc-ref").textContent = `${d.id} · ${d.precision === "month" ? fmtMonth(parse(d.date)) : fmtDay(parse(d.date))} · ${S.data.lanes.find(l => l.id === d.lane)?.label ?? ""}`;
  $("#doc-title").textContent = d.title;
  $("#doc-sub").textContent = `${d.issuer} · ${d.pages.length} page${d.pages.length > 1 ? "s" : ""}`;
  $("#doc-flags").innerHTML = d.flags.map(fid => {
    const f = S.byFlag[fid];
    return `<span class="chip chip--${f.severity}" data-flag="${fid}" title="${esc(f.headline)}">${fid} · ${esc(f.pattern_label)}</span>`;
  }).join("");
  $$("#doc-flags .chip").forEach(c => c.addEventListener("click", () => selectFlag(c.dataset.flag)));
  $("#doc-body").innerHTML = d.pages.map(p => pageHTML(d, p)).join("");
  flow?.select(id);
  requestAnimationFrame(() => {
    $$(".sheet").forEach(placeNotes);
    $$(".sheet__text mark").forEach(m => m.addEventListener("click", () => selectFlag(m.dataset.flags.split(" ")[0], false)));
    $$(".mnote").forEach(n => n.addEventListener("click", () => selectFlag(n.dataset.flag, false)));
    focusSpan(d);
  });
}

function pageHTML(d, p) {
  const text = p.text;
  // split the text at every mark boundary, so overlapping marks from several flags stay readable
  const cuts = new Set([0, text.length]);
  p.marks.forEach(m => { cuts.add(m.start); cuts.add(m.end); });
  const pts = [...cuts].sort((a, b) => a - b);
  let html = "";
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    const seg = esc(text.slice(a, b));
    const cover = p.marks.filter(m => m.start <= a && m.end >= b);
    if (!cover.length) { html += seg; continue; }
    const flags = [...new Set(cover.map(m => m.flag))];
    const sev = cover.some(m => m.severity === "high") ? "high" : "medium";
    const title = cover.map(m => `${m.flag} · ${m.label}`).join("\n");
    html += `<mark class="sev-${sev}" data-flags="${flags.join(" ")}" data-start="${a}" title="${esc(title)}">${seg}</mark>`;
  }
  // one margin note per distinct span start
  const byStart = new Map();
  p.marks.forEach(m => byStart.set(m.start, [...(byStart.get(m.start) ?? []), m]));
  const groups = [...byStart].map(([start, ms]) => ({ start, ms }));
  const notes = groups.map(g => {
    const sev = g.ms.some(m => m.severity === "high") ? "high" : "medium";
    const fl = [...new Set(g.ms.map(m => m.flag))];
    return `<div class="mnote sev-${sev}" data-anchor="${g.start}" data-flag="${fl[0]}"><b>${fl.join(" ")}</b> ${esc(g.ms[0].role)}</div>`;
  }).join("");
  return `<div class="sheet" data-page="${p.n}">
    <span class="sheet__stamp">${d.id} · p.${p.n}/${d.pages.length}</span>
    <div class="sheet__text">${html}</div>
    <div class="sheet__margin">${notes}</div>
    <div class="sheet__foot"><span>${esc(d.notice)}</span><span>${d.id} — page ${p.n}</span></div>
  </div>`;
}

function placeNotes(sheet) {
  const text = $(".sheet__text", sheet);
  const base = text.getBoundingClientRect().top;
  let last = -1e9;
  $$(".mnote", sheet).forEach(n => {
    const mark = $(`mark[data-start="${n.dataset.anchor}"]`, text) || $$("mark", text).find(m => +m.dataset.start >= +n.dataset.anchor);
    if (!mark) return;
    let top = mark.getBoundingClientRect().top - base;
    top = Math.max(top, last + 4);
    n.style.top = top + "px";
    last = top + n.offsetHeight;
  });
}

function focusSpan(d) {
  const o = S.focus || {};
  let target = null;
  if (o.span) {
    const sheet = $(`.sheet[data-page="${o.span.page}"]`);
    if (sheet) {
      target = $$("mark", sheet).find(m => +m.dataset.start >= o.span.start && +m.dataset.start < o.span.end);
      if (!target && o.ok) {
        // cleared check: show the line without a flag colour
        target = sheet;
      }
    }
  } else if (o.flag) {
    target = $$(".sheet__text mark").find(m => m.dataset.flags.split(" ").includes(o.flag));
  }
  target = target || $(".sheet__text mark");
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    if (target.tagName === "MARK") {
      const flagged = o.flag ? $$(".sheet__text mark").filter(m => m.dataset.flags.split(" ").includes(o.flag)) : [target];
      (o.span ? [target] : flagged).forEach(m => { m.classList.remove("is-focus"); void m.offsetWidth; m.classList.add("is-focus"); });
    }
  } else $("#doc-body").scrollTop = 0;
}

function stepDoc(dir) {
  const i = S.docOrder.indexOf(S.doc);
  const j = Math.max(0, Math.min(S.docOrder.length - 1, i + dir));
  if (j !== i) openDoc(S.docOrder[j], S.flag ? { flag: S.flag } : null);
}

function closeDoc() {
  $("#drawer").hidden = true;
  S.doc = null;
  flow?.select(null);
}

/* ================================================================ precedents */

async function loadPrecedents() {
  if (S.precedents) return;
  try {
    const r = await getJSON(`${API}/api/coi/precedents?k=100`);
    S.precedents = r.results; S.precStats = r.stats; S.patterns = r.patterns; S.precLive = true;
  } catch {
    const r = await getJSON(`audit/data/precedents.json`);
    S.precedents = r.results; S.precStats = r.stats; S.patterns = r.patterns; S.precLive = false;
  }
  $("#tab-prec").textContent = "";
  const st = S.precStats;
  $("#prec-sub").textContent = `${st.total} past conflict-of-interest cases — court decisions, settlements, parliamentary reports, statutes and simulated scenarios. Each flag is compared against them.`;
  $("#prec-stats").innerHTML = [
    `<span><b>${st.total}</b> entries</span>`,
    `<span><b>${st.by_provenance.public_record || 0}</b> public record</span>`,
    `<span><b>${st.by_provenance.synthetic || 0}</b> simulated scenarios</span>`,
    `<span><b>${Object.keys(st.by_jurisdiction).length}</b> jurisdictions</span>`,
    `<span>retrieval: ${esc(st.engine)}</span>`].join("");
  const pats = Object.entries(S.patterns);
  $("#prec-filters").innerHTML = [`<button data-prov="" class="is-on">All</button>`, `<button data-prov="public_record">Public record</button>`, `<button data-prov="synthetic">Simulated</button>`, `<span style="width:12px"></span>`,
    ...pats.map(([k, v]) => `<button data-pattern="${k}">${esc(v)} <span class="mono">${st.by_pattern[k] || 0}</span></button>`)].join("");
  $$("#prec-filters button").forEach(b => b.addEventListener("click", () => {
    if ("prov" in b.dataset) {
      S.precFilter.prov = b.dataset.prov || null;
      $$("#prec-filters [data-prov]").forEach(x => x.classList.toggle("is-on", x === b));
    } else {
      S.precFilter.pattern = S.precFilter.pattern === b.dataset.pattern ? null : b.dataset.pattern;
      $$("#prec-filters [data-pattern]").forEach(x => x.classList.toggle("is-on", x.dataset.pattern === S.precFilter.pattern));
    }
    searchPrecedents();
  }));
  searchPrecedents();
}

let precTimer = 0;
async function searchPrecedents() {
  const q = $("#prec-q").value.trim();
  const { pattern, prov } = S.precFilter;
  let list;
  if ((q || pattern) && S.precLive) {
    const u = new URLSearchParams({ q, k: 50 });
    if (pattern) u.append("pattern", pattern);
    if (prov) u.set("provenance", prov);
    list = (await getJSON(`${API}/api/coi/precedents?${u}`)).results;
    if (pattern) list = list.filter(p => p.patterns.includes(pattern));
  } else {
    const words = q.toLowerCase().split(/\W+/).filter(w => w.length > 2);
    list = S.precedents.filter(p => (!prov || p.provenance === prov) && (!pattern || p.patterns.includes(pattern)))
      .map(p => ({ p, s: words.reduce((acc, w) => acc + (JSON.stringify(p).toLowerCase().includes(w) ? 1 : 0), 0) }))
      .filter(x => !words.length || x.s > 0).sort((a, b) => b.s - a.s).map(x => x.p);
  }
  $("#prec-list").innerHTML = list.length ? list.map(p => precCard(p, false)).join("") : `<li class="muted">No match.</li>`;
}

/* ================================================================ views + intro */

function setView(v) {
  const prec = v === "precedents";
  $("#view-timeline").hidden = prec;
  $("#view-flags").hidden = prec;
  $("#view-precedents").hidden = !prec;
  $$(".tab").forEach(t => t.classList.toggle("is-on", t.dataset.view === v));
  if (prec) loadPrecedents();
  else if (v === "flags") $("#view-flags").scrollIntoView({ behavior: "smooth" });
  else window.scrollTo({ top: 0, behavior: "smooth" });
}

async function intro() {
  const st = S.data.stats;
  const steps = [
    ["Reading the case file", `${st.documents} documents · ${st.pages} pages`],
    ["Extracting facts with their page", `${st.facts} facts`],
    ["Linking people and companies", `${st.people} people · ${st.companies} companies`],
    ["Cross-referencing documents", `${st.rules} rules · ${st.cross_references} links`],
    ["Comparing with past cases", `${st.precedents} precedents`],
    ["Points to review", `${st.flags} flags · ${st.cleared} cleared`],
  ];
  const box = $("#intro");
  box.hidden = false;
  $("#intro-steps").innerHTML = steps.map(([l]) => `<li><i></i><span>${l}</span><b></b></li>`).join("");
  let skip = false;
  $("#intro-skip").onclick = () => { skip = true; };
  const lis = $$("#intro-steps li");
  for (let i = 0; i < steps.length && !skip; i++) {
    lis[i].className = "is-run";
    $("#intro-title").textContent = steps[i][0] + "…";
    await new Promise(r => setTimeout(r, i === 0 ? 650 : 480));
    lis[i].className = "is-done" + (i === steps.length - 1 ? " is-alert" : "");
    $("b", lis[i]).textContent = steps[i][1];
  }
  if (!skip) {
    $("#intro-title").textContent = `${st.flags} potential conflicts to review`;
    await new Promise(r => setTimeout(r, 900));
  }
  box.hidden = true;
  try { sessionStorage.setItem("breach-intro", "1"); } catch { /* private mode */ }
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3200);
}

/* ================================================================ boot */

async function boot() {
  try { await load(); } catch (e) {
    toast("Could not load the case file. Run `uv run casebreak serve`.");
    throw e;
  }
  renderHeader();
  renderFlags();
  renderTimeline();

  let seen = false;
  try { seen = sessionStorage.getItem("breach-intro") === "1"; } catch { /* ignore */ }
  if (params.has("intro") || !seen) await intro();

  const hash = location.hash.match(/flag=(F\d+)/);
  if (hash && S.byFlag[hash[1]]) selectFlag(hash[1], false);
  else if (location.hash === "#precedents") setView("precedents");
  else selectFlag(S.data.flags[0].id, false);

  $$(".tab").forEach(t => t.addEventListener("click", e => { e.preventDefault(); setView(t.dataset.view); }));
  $("#tl-all").addEventListener("change", renderTimeline);
  $("#doc-close").onclick = closeDoc;
  $("#doc-prev").onclick = () => stepDoc(-1);
  $("#doc-next").onclick = () => stepDoc(1);
  $("#prec-q").addEventListener("input", () => { clearTimeout(precTimer); precTimer = setTimeout(searchPrecedents, 180); });
  addEventListener("keydown", e => {
    if (e.target.matches("input")) return;
    if (e.key === "Escape") closeDoc();
    if (!$("#drawer").hidden && e.key === "ArrowRight") stepDoc(1);
    if (!$("#drawer").hidden && e.key === "ArrowLeft") stepDoc(-1);
  });
}

boot();
