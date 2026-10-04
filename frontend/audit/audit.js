/* BREACH — conflict-of-interest audit.
   Data: GET /api/coi/cases/{case} (falls back to the snapshot in audit/data/ when the API is not running).
   Timeline (d3, zoomable, long quiet periods compressed) → click a point → the document, with the exact lines
   highlighted and annotated in the margin. Flags → chain, evidence, comparable past cases, next steps. */

const API = window.BREACH_API ?? "";
const params = new URLSearchParams(location.search);
const CASE = params.get("case") || "mckinsey";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const parse = d3.timeParse("%Y-%m-%d");
const fmtDay = d3.timeFormat("%d %b %Y");
const fmtMonth = d3.timeFormat("%b %Y");
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
    [st.documents, "documents"], [st.pages, "pages read"], [st.facts, "facts extracted"],
    [`${st.people} · ${st.companies}`, "people · companies"], [st.cross_references, "cross-references"],
    [st.flags, `flags · ${st.high} high`, "alert"], [st.cleared, "checks cleared", "ok"],
  ];
  $("#strip").innerHTML = cells.map(([n, l, k]) => `<div class="stat ${k ? "stat--" + k : ""}"><b>${n}</b><span>${l}</span></div>`).join("");
  renderEngine();
}

function renderEngine() {
  const e = S.data.engine || {};
  $("#engine").innerHTML = `<i></i>${S.live ? "live" : "snapshot"} · ${esc(e.precedents || "")}${e.notes === "mistral" ? " · Mistral notes" : ""}`;
}

/* ================================================================ timeline */

const TL = { lane: 62, person: 46, gutter: 178, top: 34, bottom: 30, section: 26 };

function buildScale(width) {
  // piecewise time scale: quiet periods are compressed so the dense months stay readable
  const docs = S.data.documents.map(d => parse(d.date));
  const ctx = S.data.context.map(c => parse(c.date));
  const all = [...docs, ...ctx].sort((a, b) => a - b);
  // the axis follows the documents; older periods (e.g. a past employment) run in from the left edge
  const min = d3.timeMonth.offset(all[0], -3), max = d3.timeMonth.offset(all[all.length - 1], 3);
  // months with documents weigh 4, their neighbours 1.2, quiet months .15
  const months = d3.timeMonth.range(d3.timeMonth.floor(min), d3.timeMonth.offset(d3.timeMonth.ceil(max), 1));
  const count = d3.rollup(docs, v => v.length, d => +d3.timeMonth.floor(d));
  const near = m => count.has(+d3.timeMonth.offset(m, -1)) || count.has(+d3.timeMonth.offset(m, 1));
  const weights = months.map(m => (count.has(+m) ? 3 + Math.min(3, count.get(+m)) * 0.6 : near(m) ? 1.2 : 0.15));
  const total = d3.sum(weights);
  let acc = 0;
  const range = [0, ...weights.map(w => (acc += w) / total * width)];
  const domain = [...months, d3.timeMonth.offset(months[months.length - 1], 1)];
  return { x: d3.scaleTime().domain(domain).range(range).clamp(false) };
}

function renderTimeline() {
  const host = $("#tl-canvas");
  host.innerHTML = "";
  const flaggedOnly = $("#tl-flagged").checked;
  const showPeople = $("#tl-people").checked;
  const W = Math.max(host.clientWidth, 980);
  const innerW = W - TL.gutter - 24;
  const lanes = S.data.lanes;
  const people = showPeople ? [...new Set(S.data.periods.map(p => p.person))] : [];
  const lanesH = lanes.length * TL.lane;
  const peopleTop = TL.top + lanesH + (people.length ? TL.section : 0);
  const H = peopleTop + people.length * TL.person + TL.bottom;

  const { x: x0 } = buildScale(innerW);
  let x = x0;
  const svg = d3.select(host).append("svg").attr("width", W).attr("height", H);
  const defs = svg.append("defs");
  defs.append("pattern").attr("id", "hatch-high").attr("width", 6).attr("height", 6).attr("patternUnits", "userSpaceOnUse")
    .attr("patternTransform", "rotate(45)")
    .call(p => { p.append("rect").attr("width", 6).attr("height", 6).attr("fill", "rgba(230,19,0,.10)"); p.append("rect").attr("width", 2.2).attr("height", 6).attr("fill", "rgba(230,19,0,.55)"); });
  defs.append("clipPath").attr("id", "tl-clip").append("rect").attr("x", 0).attr("y", 0).attr("width", innerW).attr("height", H);

  // lane backgrounds + labels
  const bg = svg.append("g");
  lanes.forEach((l, i) => {
    const y = TL.top + i * TL.lane;
    bg.append("rect").attr("class", "tl-lane-bg" + (i % 2 ? " alt" : "")).attr("x", 0).attr("y", y).attr("width", W).attr("height", TL.lane);
    bg.append("line").attr("class", "tl-sep").attr("x1", 0).attr("x2", W).attr("y1", y).attr("y2", y);
    const n = S.data.documents.filter(d => d.lane === l.id).length;
    bg.append("text").attr("class", "tl-lane-label").attr("x", 18).attr("y", y + TL.lane / 2 - 2).text(l.label);
    bg.append("text").attr("class", "tl-lane-sub").attr("x", 18).attr("y", y + TL.lane / 2 + 13).text(`${n} document${n > 1 ? "s" : ""}`);
  });
  if (people.length) {
    bg.append("text").attr("class", "tl-section").attr("x", 18).attr("y", TL.top + lanesH + 17).text("People");
    bg.append("line").attr("class", "tl-sep").attr("x1", 0).attr("x2", W).attr("y1", TL.top + lanesH).attr("y2", TL.top + lanesH);
    people.forEach((p, i) => {
      const y = peopleTop + i * TL.person;
      bg.append("rect").attr("class", "tl-lane-bg" + (i % 2 ? "" : " alt")).attr("x", 0).attr("y", y).attr("width", W).attr("height", TL.person);
      bg.append("text").attr("class", "tl-lane-label").attr("x", 18).attr("y", y + TL.person / 2 + 4).text(p);
    });
  }
  bg.append("line").attr("class", "tl-sep").attr("x1", TL.gutter - 8).attr("x2", TL.gutter - 8).attr("y1", TL.top).attr("y2", H - TL.bottom);

  const plot = svg.append("g").attr("transform", `translate(${TL.gutter},0)`);
  const clip = plot.append("g").attr("clip-path", "url(#tl-clip)");
  const gGrid = clip.append("g").attr("class", "tl-grid");
  const gWin = clip.append("g");
  const gCtx = clip.append("g").attr("class", "tl-ctx");
  const gPer = clip.append("g");
  const gLinks = clip.append("g");
  const gDocs = clip.append("g");
  const gAxis = plot.append("g").attr("class", "tl-axis").attr("transform", `translate(0,${TL.top})`);
  const gAxisB = plot.append("g").attr("class", "tl-axis").attr("transform", `translate(0,${H - TL.bottom})`);

  const docs = S.data.documents.filter(d => !flaggedOnly || d.flags.length);
  const laneIdx = Object.fromEntries(lanes.map((l, i) => [l.id, i]));
  const personIdx = Object.fromEntries(people.map((p, i) => [p, i]));

  function draw() {
    // axis + grid
    // monthly candidates, kept when at least 56 px from the previous one (January wins its slot)
    const [d0, d1] = x.domain().length ? [x.domain()[0], x.domain()[x.domain().length - 1]] : [];
    const ticks = [];
    for (const m of d3.timeMonth.range(d3.timeMonth.ceil(d0), d1)) {
      const px = x(m);
      if (px < 0 || px > innerW) continue;
      const last = ticks[ticks.length - 1];
      if (!last || px - x(last) >= 56) ticks.push(m);
      else if (m.getMonth() === 0 && last.getMonth() !== 0 && (ticks.length < 2 || px - x(ticks[ticks.length - 2]) >= 56)) ticks[ticks.length - 1] = m;
    }
    const tf = d => (d.getMonth() === 0 ? d3.timeFormat("%Y")(d) : d3.timeFormat("%b")(d));
    gAxis.call(d3.axisTop(x).tickValues(ticks).tickFormat(tf).tickSize(4));
    gAxisB.call(d3.axisBottom(x).tickValues(ticks).tickFormat(d3.timeFormat("%b %Y")).tickSize(4));
    gGrid.call(d3.axisTop(x).tickValues(ticks).tickSize(-(H - TL.top - TL.bottom)).tickFormat(""))
      .attr("transform", `translate(0,${TL.top})`);

    // context events
    gCtx.selectAll("g").data(S.data.context).join(enter => {
      const g = enter.append("g");
      g.append("line"); g.append("text");
      return g;
    }).each(function (c) {
      const cx = x(parse(c.date));
      d3.select(this).select("line").attr("x1", cx).attr("x2", cx).attr("y1", TL.top).attr("y2", H - TL.bottom);
      d3.select(this).select("text").attr("x", cx - 4).attr("text-anchor", "end").attr("y", H - TL.bottom - 6).text(c.label);
    });

    // selected flag window
    gWin.selectAll("*").remove();
    const f = S.flag && S.byFlag[S.flag];
    if (f) {
      const a = x(parse(f.window[0])), b = x(parse(f.window[1]));
      gWin.append("rect").attr("class", "tl-window").attr("x", Math.min(a, b)).attr("y", TL.top).attr("width", Math.max(2, Math.abs(b - a))).attr("height", H - TL.top - TL.bottom);
      [a, b].forEach(v => gWin.append("line").attr("class", "tl-window-edge").attr("x1", v).attr("x2", v).attr("y1", TL.top).attr("y2", H - TL.bottom));
      gWin.append("text").attr("class", "tl-window-label").attr("x", Math.min(a, b) + 4).attr("y", TL.top + 12).text(`${f.id} · ${fmtDay(parse(f.window[0]))} → ${fmtDay(parse(f.window[1]))}`);
    }

    // people periods
    if (people.length) drawPeriods();

    // documents: stacked when they collide in the same lane
    const placed = [];
    const byLane = d3.group(docs, d => d.lane);
    for (const [lane, list] of byLane) {
      const sorted = [...list].sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
      let groupX = -1e9, stack = [];
      const flush = () => {
        stack.forEach((d, k) => placed.push({ d, cx: d._x, cy: TL.top + laneIdx[lane] * TL.lane + TL.lane / 2 + (k - (stack.length - 1) / 2) * 15, k, n: stack.length }));
        stack = [];
      };
      for (const d of sorted) {
        d._x = x(parse(d.date));
        if (d._x - groupX > 14) { flush(); groupX = d._x; }
        stack.push(d);
      }
      flush();
    }
    // labels: only when there is room before the next point of the same lane
    placed.sort((a, b) => a.cx - b.cx);
    const byLaneP = d3.group(placed, p => p.d.lane);
    for (const list of byLaneP.values()) {
      let free = -1e9;
      list.forEach((p, i) => {
        const nextX = list.slice(i + 1).find(q => q.cx - p.cx > 14)?.cx ?? 1e9;
        const full = p.d.title.split(" — ")[0];
        const text = p.n === 1 ? (full.length > 30 ? full.slice(0, 29) + "…" : full) : p.k === 0 ? `${p.n} documents` : "";
        const w = text.length * 5.6 + 16;
        p.label = text && p.cx > free && p.cx + w < nextX && p.cx + w < innerW + 10 ? text : "";
        if (p.label) free = p.cx + w;
      });
    }

    const sel = gDocs.selectAll("g.tl-doc").data(placed, p => p.d.id).join(enter => {
      const g = enter.append("g").attr("class", "tl-doc").attr("tabindex", 0).attr("role", "button");
      g.append("circle").attr("class", "halo").attr("r", 12);
      g.append("circle").attr("class", "dot").attr("r", 6.5);
      g.append("rect").attr("class", "badge-bg").attr("rx", 5).attr("height", 11);
      g.append("text").attr("class", "badge");
      g.append("text").attr("class", "lbl");
      g.on("click", (ev, p) => openDoc(p.d.id, S.flag ? { flag: S.flag } : null))
        .on("keydown", (ev, p) => { if (ev.key === "Enter") openDoc(p.d.id); })
        .on("mouseenter", (ev, p) => showTip(ev, docTip(p.d)))
        .on("mousemove", moveTip)
        .on("mouseleave", hideTip);
      return g;
    });
    sel.attr("transform", p => `translate(${p.cx},${p.cy})`)
      .attr("class", p => {
        const d = p.d, f = S.flag && S.byFlag[S.flag];
        return ["tl-doc", d.severity ? `sev-${d.severity}` : "", d.provenance === "public_record" ? "is-public" : "",
          S.doc === d.id ? "is-open" : "", f ? (f.docs.includes(d.id) ? "is-hit" : "is-dim") : ""].join(" ");
      });
    sel.select("text.lbl").attr("x", 11).attr("y", 4).text(p => p.label);
    sel.select("rect.badge-bg").attr("x", 3).attr("y", -15).attr("width", p => p.d.flags.length > 9 ? 16 : 11)
      .attr("display", p => p.d.flags.length ? null : "none");
    sel.select("text.badge").attr("x", 5.5).attr("y", -6.6).text(p => p.d.flags.length || "");

    // links through the evidence of the selected flag, in time order
    gLinks.selectAll("*").remove();
    if (f) {
      const pts = f.docs.map(id => placed.find(p => p.d.id === id)).filter(Boolean).sort((a, b) => a.cx - b.cx || a.cy - b.cy);
      const line = d3.line().curve(d3.curveCatmullRom.alpha(.6)).x(p => p.cx).y(p => p.cy);
      if (pts.length > 1) gLinks.append("path").attr("class", "tl-link").attr("d", line(pts));
    }
  }

  function drawPeriods() {
    const rows = S.data.periods;
    const track = p => (p.kind === "private" || p.kind === "employment" ? 0 : 1);
    const yOf = p => peopleTop + personIdx[p.person] * TL.person + 8 + track(p) * 16;
    const f = S.flag && S.byFlag[S.flag];
    const sel = gPer.selectAll("g.tl-period").data(rows, (p, i) => p.person + p.label + p.start + i).join(enter => {
      const g = enter.append("g").attr("class", p => `tl-period k-${p.kind}`);
      g.append("rect").attr("height", 13);
      g.append("text").attr("y", 10);
      g.on("click", (ev, p) => p.doc && openDoc(p.doc, p.flags[0] ? { flag: p.flags[0] } : null))
        .on("mouseenter", (ev, p) => showTip(ev, `<span class="mono">${esc(p.person)}</span><b>${esc(p.label)}</b><br>${fmtDay(parse(p.start))} → ${fmtDay(parse(p.end))}${p.doc ? `<br><span class="mono">source ${p.doc}</span>` : ""}`))
        .on("mousemove", moveTip).on("mouseleave", hideTip);
      return g;
    });
    sel.attr("transform", p => `translate(${x(parse(p.start))},${yOf(p)})`)
      .classed("is-dim", p => f && !p.flags.includes(f.id) && !f.persons.includes(p.person));
    sel.select("rect").attr("width", p => Math.max(3, x(parse(p.end)) - x(parse(p.start))));
    sel.select("text").attr("x", 6).text(p => (x(parse(p.end)) - x(parse(p.start)) > p.label.length * 5.4 + 12 ? p.label : ""));

    // overlap of a private and a public engagement for the same person
    const overlaps = [];
    for (const person of people) {
      const pr = rows.filter(r => r.person === person && r.kind === "private");
      const pu = rows.filter(r => r.person === person && r.kind === "public");
      for (const a of pr) for (const b of pu) {
        const s = a.start > b.start ? a.start : b.start, e = a.end < b.end ? a.end : b.end;
        if (s <= e) overlaps.push({ person, s, e });
      }
    }
    const ov = gPer.selectAll("g.tl-ov").data(overlaps, o => o.person + o.s).join(enter => {
      const g = enter.append("g").attr("class", "tl-ov");
      g.append("rect").attr("class", "tl-overlap").attr("rx", 4);
      g.append("text").attr("class", "tl-window-label");
      return g;
    });
    ov.select("rect").attr("x", o => x(parse(o.s))).attr("y", o => peopleTop + personIdx[o.person] * TL.person + 5)
      .attr("width", o => Math.max(2, x(parse(o.e)) - x(parse(o.s)))).attr("height", 35);
    ov.select("text").attr("x", o => x(parse(o.e)) + 4).attr("y", o => peopleTop + personIdx[o.person] * TL.person + 26)
      .text(o => (x(parse(o.e)) - x(parse(o.s)) > 6 ? "overlap" : ""));
  }

  const zoom = d3.zoom().scaleExtent([1, 30]).translateExtent([[0, 0], [innerW, H]]).extent([[0, 0], [innerW, H]])
    .filter(ev => (ev.type === "wheel" ? ev.ctrlKey || ev.metaKey || ev.shiftKey : !ev.button))
    .on("zoom", ev => { x = ev.transform.rescaleX(x0); draw(); });
  svg.call(zoom).on("dblclick.zoom", null);
  TL.zoomTo = (a, b) => {
    const xa = x0(a), xb = x0(b), k = Math.min(30, innerW / Math.max(1, xb - xa));
    svg.transition().duration(650).call(zoom.transform, d3.zoomIdentity.scale(k).translate(-xa, 0));
  };
  TL.fit = () => svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
  TL.by = k => svg.transition().duration(300).call(zoom.scaleBy, k);
  TL.redraw = draw;
  draw();
}

function docTip(d) {
  const fl = d.flags.map(id => `<span class="chip chip--${S.byFlag[id].severity}">${id}</span>`).join("");
  return `<span class="mono">${esc(d.id)} · ${d.precision === "month" ? fmtMonth(parse(d.date)) : fmtDay(parse(d.date))}</span>
    <b>${esc(d.title)}</b><br><span style="opacity:.7">${esc(d.issuer)}</span>
    ${fl ? `<div class="tip__flags">${fl}</div>` : ""}`;
}

function renderLegend() {
  $("#tl-legend").innerHTML = `
    <span><i class="lg-dot"></i>document</span>
    <span><i class="lg-dot lg-dot--high"></i>cited by a high flag</span>
    <span><i class="lg-dot lg-dot--medium"></i>cited by a medium flag</span>
    <span><i class="lg-dot lg-dot--public"></i>public record</span>
    <span><i class="lg-bar lg-bar--public"></i>public engagement</span>
    <span><i class="lg-bar lg-bar--private"></i>private engagement</span>
    <span><i class="lg-bar lg-bar--employment"></i>employment</span>
    <span><i class="lg-bar lg-bar--overlap"></i>overlap / window</span>
    <span>ctrl + scroll or ± to zoom · drag to pan</span>`;
}

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
      <span class="fl__meta">
        <span class="chip chip--${f.severity}">${f.severity}</span>
        <span class="chip">${esc(f.pattern_label)}</span>
        <span class="cert cert--${f.certainty}">${CERT[f.certainty]}</span>
      </span>
      <span class="fl__meta">${f.docs.map(id => `<span class="chip chip--doc" data-doc="${id}" data-flag="${f.id}">${id}</span>`).join("")}</span>
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
  TL.redraw?.();
  const bar = $("#tl-flagbar");
  if (S.flag) {
    const f = S.byFlag[S.flag];
    bar.hidden = false;
    bar.innerHTML = `<b>${f.id}</b><span>${esc(f.headline)}</span><span class="mono">${f.docs.length} documents · ${f.evidence.length} lines</span><button type="button" id="flag-clear">Clear</button>`;
    $("#flag-clear").onclick = () => selectFlag(S.flag);
  } else bar.hidden = true;
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
  const note = f.note ? `
    <div class="d__sec"><h4>Reviewer note</h4>
      <div class="note"><div class="note__h">✦ Mistral · ${esc(f.note.model || "")}${f.note.verified ? " · quotes verified on the page" : ""}</div>${md(f.note.text)}</div></div>` : "";
  const pcs = f.precedents.map(p => precCard(p, true)).join("");
  el.innerHTML = `
    <div class="sev-${f.severity}">
      <div class="d__top">
        <span class="fl__id">${f.id}</span>
        <span class="chip chip--${f.severity}">${f.severity} severity</span>
        <span class="chip">${esc(f.pattern_label)}</span>
        <span class="cert cert--${f.certainty}">${CERT[f.certainty]}</span>
        <span class="d__rule mono">${f.rule} · ${esc(f.title)}</span>
      </div>
      <h3 class="d__h">${esc(f.headline)}</h3>
      <p class="d__sum">${esc(f.summary)}</p>
      <div class="d__grid">
        <div>
          <div class="d__sec"><h4>The chain</h4>${chainSVG(f)}</div>
          <div class="d__sec"><h4>Where to look · ${f.evidence.length} lines in ${f.docs.length} documents</h4><ol class="evs">${ev}</ol></div>
          ${f.aggravating.length ? `<div class="d__sec"><h4>Aggravating</h4><ul class="agg">${f.aggravating.map(a => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}
        </div>
        <div>
          ${note}
          <div class="d__sec"><h4>Comparable past cases</h4><ol class="pcs">${pcs}</ol></div>
          <div class="d__sec"><h4>Framework</h4><ul class="legal">${f.legal.map(l => `<li><b>${esc(l.ref)}</b>${esc(l.text)}</li>`).join("")}</ul></div>
          <div class="d__sec"><h4>Next steps</h4><ul class="next">${f.next.map((n, i) => `<li><input type="checkbox" id="nx-${f.id}-${i}"><label for="nx-${f.id}-${i}">${esc(n)}</label></li>`).join("")}</ul></div>
        </div>
      </div>
      <div class="d__actions">
        <button class="btn btn--primary" type="button" id="d-open">Open the first line →</button>
        <button class="btn" type="button" id="d-time">Show on the timeline</button>
        <button class="btn" type="button" id="d-memo">Review memo (.md)</button>
        <span class="disclaimer">Potential conflict of interest — to review. The qualification is the lawyer's.</span>
      </div>
    </div>`;
  $$(".ev", el).forEach(li => li.addEventListener("click", () => {
    const e = f.evidence[+li.dataset.i];
    openDoc(e.doc, { flag: f.id, span: e });
  }));
  $$(".chain .l.is-doc", el).forEach(g => g.addEventListener("click", () => openDoc(g.dataset.doc, { flag: f.id })));
  $("#d-open").onclick = () => openDoc(f.evidence[0].doc, { flag: f.id, span: f.evidence[0] });
  $("#d-time").onclick = () => { $("#view-timeline").scrollIntoView({ behavior: "smooth" }); TL.zoomTo?.(d3.timeMonth.offset(parse(f.window[0]), -2), d3.timeMonth.offset(parse(f.window[1]), 2)); };
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
    <div class="pc__top">${prov}<span class="chip">${esc(p.jurisdiction)} · ${p.year}</span><span class="chip">${esc(p.kind)}</span>${score}</div>
    <div class="pc__t">${esc(p.title)}</div>
    <div class="pc__c">${esc(p.citation)}</div>
    ${compact ? "" : `<p class="pc__f">${esc(p.facts)}</p><p class="pc__o"><b>Outcome.</b> ${esc(p.outcome)}</p>`}
    <p class="pc__l">${compact ? "" : "<b>Lesson.</b> "}${esc(p.lesson)}</p>
    ${why ? `<div class="pc__why">${why}</div>` : ""}
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
  requestAnimationFrame(() => {
    $$(".sheet").forEach(placeNotes);
    $$(".sheet__text mark").forEach(m => m.addEventListener("click", () => selectFlag(m.dataset.flags.split(" ")[0], false)));
    $$(".mnote").forEach(n => n.addEventListener("click", () => selectFlag(n.dataset.flag, false)));
    focusSpan(d);
  });
  TL.redraw?.();
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
  const groups = d3.groups(p.marks, m => m.start).map(([start, ms]) => ({ start, ms }));
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
  TL.redraw?.();
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
  if (!prec) requestAnimationFrame(() => renderTimeline());
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
  renderLegend();
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
  $("#tl-flagged").addEventListener("change", renderTimeline);
  $("#tl-people").addEventListener("change", renderTimeline);
  $("#zoom-in").onclick = () => TL.by(1.6);
  $("#zoom-out").onclick = () => TL.by(1 / 1.6);
  $("#zoom-fit").onclick = () => TL.fit();
  $("#zoom-crisis").onclick = () => TL.zoomTo(new Date(2020, 9, 15), new Date(2021, 6, 15));
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
  let rt = 0;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderTimeline, 150); });
}

boot();
