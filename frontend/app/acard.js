// Alert card — the four questions (What · Where · Why · What next), the page with the line highlighted,
// the simulated tribunal, the Lean proof, the judge's answers, Judilibre precedents and the review buttons.
import { api } from "./api.js";
import { state, set } from "./state.js";
import { $, h, esc, CERT, VERDICT, hm, dmy, toast, sleep, REDUCED, docType } from "./ui.js";

let current = null;

export async function openAlert(aid, { onSimulate, onReviewed } = {}) {
  const ov = $("#overlay"), card = $("#acard");
  ov.hidden = false;
  document.body.style.overflow = "hidden";
  card.replaceChildren(h("div", { class: "ac__head" }, h("p", { class: "mono" }, "Loading…")));
  const a = await api.alert(state.caseId, aid, { as_of: state.asOf, mode: state.mode, pseudo: state.pseudo });
  current = a;
  set({ selectedAlert: aid });
  const isPq = a.mode === "prosecution";
  const [certLabel, certCls] = CERT[a.certainty];

  // ---------- head
  const head = h("header", { class: "ac__head" },
    h("div", {},
      h("div", { class: "ac__sub" },
        h("span", { class: "pill pill--id" }, `${a.id} · ${a.nullity_id}`),
        h("span", { class: `ac__headline ${isPq ? "pq" : a.status === "needs_reading" ? "nr" : ""}` }, a.headline),
        h("span", { class: `pill ${certCls}` }, certLabel),
        a.confidence && a.confidence !== "n/a" ? h("span", { class: "pill pill--aff", title: "Confidence of the rule (catalogue)" }, `rule ${a.confidence}`) : null,
        a.why.validated_by ? h("span", { class: "pill pill--ok" }, `validated: ${a.why.validated_by}`) : h("span", { class: "pill pill--todo" }, "not validated by a lawyer")),
      h("h2", { id: "acard-title" }, a.title),
      h("p", { class: "mono", style: { color: "var(--ink-3)", margin: 0 } }, `${a.node.label} · ${a.node.start ? dmy(a.node.start) + " " + hm(a.node.start) : "date ?"}`)),
    h("div", { class: "ac__actions" },
      h("button", { class: "btn btn--primary", onclick: () => { close(); onSimulate?.(a.node.id); } }, "Simulate impact ⟶"),
      h("button", { class: "ac__close", onclick: close, title: "Close (Esc)" }, "×")));

  // ---------- left: the four questions
  const left = h("div", { class: "ac__left" });
  left.append(
    h("section", { class: "q4 q4--what" }, h("span", { class: "q4__tag" }, "1 · What"),
      h("p", { class: "q4__what" }, a.what),
      a.details?.threshold_note ? h("p", { class: "muted", style: { marginTop: "8px" } }, `Flagging threshold: ${Math.round(a.details.threshold_minutes)} min — ${a.details.threshold_note}.`) : null,
      a.details?.ocr_note ? h("p", { class: "muted" }, a.details.ocr_note) : null),
    h("section", { class: "q4 q4--where" }, h("span", { class: "q4__tag" }, "2 · Where"),
      ...a.where.map((s, i) => h("div", { class: `src ${i === 0 ? "is-on" : ""}`, "data-i": i, onclick: () => showPage(i) },
        h("span", { class: "src__p" }, `p. ${s.page}`),
        h("span", { class: "src__q" }, h("span", { class: "src__t" }, `“${s.quote}”`), h("span", { class: "src__m" }, `doc ${s.doc_id}${s.piece?.number ? " · report no. " + s.piece.number : ""}${s.piece ? " · " + docType(s.piece) : ""}`))))),
    whySection(a),
    h("section", { class: "q4 q4--next" }, h("span", { class: "q4__tag" }, "4 · What next"),
      h("ul", { class: "next" }, a.next.map(n => h("li", {}, h("span", {}, n)))),
      h("div", { id: "deadline-mini", style: { marginTop: "10px" } }),
      h("h4", {}, "Lawyer's decision"),
      reviewBlock(a, onReviewed)),
    h("section", { class: "q4 q4--court" }, h("span", { class: "q4__tag" }, "Simulated tribunal"), h("div", { id: "court" }, h("p", { class: "muted" }, "Deliberating…"))),
    a.has_proof ? h("section", { class: "q4 q4--proof" }, h("span", { class: "q4__tag" }, "Lean 4 proof"), h("div", { id: "proof" }, h("p", { class: "muted" }, "Checking with the Lean kernel…"))) : null,
    a.judge ? judgeSection(a.judge) : null,
    h("section", { class: "q4" }, h("span", { class: "q4__tag", style: { background: "var(--ink-3)" } }, "Precedents · Judilibre"), h("div", { id: "prec" }, h("p", { class: "muted" }, "Searching…"))),
  );

  // ---------- right: page viewer
  const tabs = h("div", { class: "pv__tabs" });
  const uniq = [...new Map(a.where.map((s, i) => [s.page, i])).entries()];
  for (const [page, i] of uniq) tabs.append(h("button", { "data-i": i, onclick: () => showPage(i) }, `p. ${page}`));
  const right = h("div", { class: "ac__right" },
    h("div", { class: "pv__bar" }, tabs, h("div", { class: "pv__meta", id: "pv-meta" })),
    h("div", { class: "pv__scroll", id: "pv-scroll" }),
    h("div", { class: "pv__foot" }, h("span", { id: "pv-foot" }), h("button", { id: "pv-text" }, "Text read")));

  card.replaceChildren(head, h("div", { class: "ac__body" }, left, right));
  if (a.where.length) showPage(0); else $("#pv-scroll").append(h("p", { class: "muted" }, "No source (document missing from the file)."));
  deadlineMini();
  loadCourt(a);
  if (a.has_proof) loadProof(a);
  loadPrecedents(a);
}

function whySection(a) {
  const w = a.why;
  return h("section", { class: "q4 q4--why" }, h("span", { class: "q4__tag" }, "3 · Why it matters"),
    h("div", { class: "law" }, h("span", { class: "law__art" }, w.article), h("div", { class: "law__ver" }, w.law_version,
      w.rights_at_stake?.length ? h("div", { class: "muted", style: { marginTop: "4px" } }, `Rights at stake: ${w.rights_at_stake.join(" · ")}`) : null)),
    ...(w.legal_todo ?? []).map(t => h("div", { class: "todo" }, `TODO(legal) — ${t}`)),
    h("h4", {}, w.affected_count ? `${w.affected_count} act(s) potentially affected — to name in the request` : "No dependent act in the graph"),
    w.affected_count ? h("ol", { class: "casc" }, w.affected.map(x => h("li", { class: x.origin === "llm_inferred" ? "llm" : "" },
      h("span", {}, h("span", { class: "depth", style: { "--d": x.depth - 1 } }), x.label, h("span", { class: "via" }, x.via || "dependency")),
      h("span", { class: "mono" }, x.pieces.map(p => p.cote).join(", "))))) : null,
    h("h4", {}, "What the prosecution will answer"),
    h("ul", { class: "counter-args", id: "counter-args" }),
    h("div", { class: "grief" }, w.grief_note));
}

function reviewBlock(a, onReviewed) {
  const note = h("textarea", { placeholder: "Note (optional) — e.g. prejudice to prove: self-incriminating statements p. 10" }, a.review?.note ?? "");
  const st = h("span", { class: "mono", style: { color: "var(--ink-3)" } }, a.review?.decision && a.review.decision !== "pending" ? `${a.review.decision === "accepted" ? "Accepted" : "Dismissed"} · ${a.review.at ?? ""}` : "Pending");
  const go = async decision => {
    await api.review(state.caseId, a.key, decision, note.value);
    st.textContent = decision === "accepted" ? "Accepted — moved to the top of the report" : decision === "rejected" ? "Dismissed — removed from the report" : "Pending";
    toast(decision === "accepted" ? "Ground accepted." : decision === "rejected" ? "Alert dismissed." : "Back to pending.");
    onReviewed?.();
  };
  return h("div", {}, note, h("div", { class: "review", style: { marginTop: "8px" } },
    h("button", { class: "btn btn--sm", onclick: () => go("accepted") }, "✓ Accept"),
    h("button", { class: "btn btn--sm btn--danger", onclick: () => go("rejected") }, "✕ Dismiss"),
    h("button", { class: "btn btn--sm", style: { boxShadow: "none" }, onclick: () => go("pending") }, "↺"), st));
}

function judgeSection(j) {
  const tier = { offline: "local heuristics (no key)", jev: "Jev (TypeSafe AI)", "mistral-small": "Mistral Small", "mistral-large": "Mistral Large" }[j.tier] ?? j.tier;
  return h("section", { class: "q4 q4--judge" }, h("span", { class: "q4__tag" }, "Judge · grey zone"),
    h("p", { class: "muted", style: { marginTop: 0 } }, `Judge: ${tier}${j.pseudonymized ? " · pseudonymised excerpt" : ""} · ${j.note}`),
    ...j.answers.map(q => h("div", { class: "judge-q" },
      h("b", {}, q.question || q.id),
      h("span", {}, `Answer: `, h("strong", {}, String(q.answer).replace("_", " ")), q.verified ? " · quote verified" : " · quote not verified"),
      q.quote ? h("q", {}, q.quote) : null)),
    j.unsure ? h("p", { class: "todo" }, "Judge unsure → certainty \"needs reading\".") : null);
}

// ------------------------------------------------------------------ page viewer
async function showPage(i) {
  const a = current, src = a.where[i];
  document.querySelectorAll(".src").forEach(el => el.classList.toggle("is-on", +el.dataset.i === i));
  document.querySelectorAll(".pv__tabs button").forEach(b => b.classList.toggle("is-on", a.where[+b.dataset.i].page === src.page));
  const box = $("#pv-scroll");
  box.replaceChildren(h("p", { class: "muted" }, "…"));
  const pg = await api.page(state.caseId, src.doc_id, src.page, { alert: a.key, pseudo: state.pseudo });
  const img = h("img", { src: api.imgUrl(pg.image), alt: `Page ${pg.page}` });
  const page = h("div", { class: "pv__page" }, img);
  box.replaceChildren(page);
  $("#pv-meta").textContent = `${pg.piece?.id ?? ""} · ${docType(pg.piece)} · ${pg.kind === "pdf_scan" ? "scan · " : pg.kind === "image" ? "photo · " : ""}${{ native: "native text", tesseract: "Tesseract OCR", mistral_ocr: "Mistral OCR", none: "unreadable" }[pg.ocr]}${state.pseudo ? " · original image (not masked)" : ""}`;
  $("#pv-foot").textContent = `page ${pg.page} / ${pg.total_pages}${pg.exif?.DateTimeOriginal ? " · EXIF " + pg.exif.DateTimeOriginal : ""}`;
  $("#pv-text").onclick = () => {
    const t = box.querySelector(".pv__text");
    if (t) t.remove(); else box.append(h("pre", { class: "pv__text" }, pg.text || "(aucun texte lu)"));
  };
  const place = () => {
    page.querySelectorAll(".pv__hl,.pv__note").forEach(e => e.remove());
    let first = null;
    for (const b of pg.highlights) {
      const el = h("div", { class: `pv__hl ${b.complete ? "" : "partial"}`, style: {
        left: `${b.x0 * 100 - .4}%`, top: `${b.y0 * 100 - .3}%`, width: `${(b.x1 - b.x0) * 100 + .8}%`, height: `${(b.y1 - b.y0) * 100 + .6}%` } });
      page.append(el);
      first ??= b;
    }
    if (first) {
      const note = annotation(a);
      if (note) page.append(h("div", { class: "pv__note", style: { left: `${Math.min(72, first.x1 * 100 + 2)}%`, top: `${first.y0 * 100 - 3.5}%` } }, note));
      const y = first.y0 * page.clientHeight - box.clientHeight / 3;
      box.scrollTo({ top: Math.max(0, y), behavior: REDUCED ? "auto" : "smooth" });
    } else if (pg.kind !== "image") {
      page.append(h("div", { class: "pv__note", style: { left: "8%", top: "4%" } }, "quote not located — read the page"));
    }
  };
  img.complete ? place() : img.addEventListener("load", place, { once: true });
}

function annotation(a) {
  const d = a.details ?? {};
  const fmt = m => { const hh = Math.floor(m / 60), mm = Math.round(m % 60); return hh ? `${hh}h${String(mm).padStart(2, "0")}` : `${mm} min`; };
  if (d.delay_minutes) return `${fmt(d.delay_minutes)} !`;
  if (d.duration_minutes && a.status === "possible_nullity") return `${fmt(d.duration_minutes)} > ${fmt(d.limit_minutes)}`;
  if (a.nullity_id === "PRQ-01" && d.start) return `${hm(d.start)} > 21:00`;
  return { "GAV-08": "no lawyer", "GAV-10": "no interpreter", "PRQ-03": "verbal ≠ written", "PRQ-04": "no seal",
    "GAV-13": "≠", "GEO-01": "missing document", "EXP-01": "origin?", "GAV-12": "time?", "GAV-06": "notice?", "MMC-01": "EXIF ≠ report" }[a.nullity_id] ?? "";
}

// ------------------------------------------------------------------ async sections
async function loadCourt(a) {
  const box = $("#court");
  let t;
  try { t = await api.tribunal(state.caseId, a.key, { as_of: state.asOf }); } catch (e) { box.replaceChildren(h("p", { class: "muted" }, String(e))); return; }
  state.verdicts[a.id] = t.presiding.verdict;
  const args = $("#counter-args");
  if (args) args.replaceChildren(...t.prosecution.objections.map(o => h("li", {}, o.text, " ", h("span", { class: `str str--${o.strength}` }, strengthFr(o.strength)))));
  const court = h("div", { class: "court" });
  box.replaceChildren(court, h("p", { class: "muted", style: { marginTop: "10px" } }, t.tier === "offline" ? "Deterministic agents over the graph (no API key). An objection only counts if a document in the file backs it." : "Mistral agents; objections only count if their quote is found on the page."));
  const bubbles = [
    h("div", { class: "bubble bubble--def" }, h("div", { class: "bubble__who" }, h("i"), "Defence"), h("div", {}, t.defense.text)),
    h("div", { class: "bubble bubble--pq" }, h("div", { class: "bubble__who" }, h("i"), `Prosecution · ${t.prosecution.objections.length} objection(s)`),
      ...t.prosecution.objections.map(o => h("div", { class: "obj" }, h("div", {}, o.text, o.source ? h("q", {}, `${o.source.quote} — p. ${o.source.page}`) : null, h("small", {}, o.why)),
        h("span", { class: `str str--${o.strength}` }, strengthFr(o.strength))))),
    h("div", { class: "bubble bubble--pres" }, h("div", { class: "bubble__who" }, h("i"), "Presiding judge"),
      h("span", { class: `stamp stamp--big ${VERDICT[t.presiding.verdict]?.[1] ?? ""}` }, t.presiding.label), h("div", {}, t.presiding.text),
      t.presiding.llm_text ? h("div", { class: "muted", style: { color: "#B9B6C4", marginTop: "8px" } }, t.presiding.llm_text) : null),
  ];
  for (const b of bubbles) { court.append(b); await sleep(REDUCED ? 0 : 380); }
}
const strengthFr = s => ({ supported: "backed by a document", to_verify: "to verify", no_evidence: "no document", principle: "principle — not decided" }[s] ?? s);

async function loadProof(a) {
  const box = $("#proof");
  let p;
  try { p = await api.proof(state.caseId, a.key, { as_of: state.asOf }); } catch (e) { box.replaceChildren(h("p", { class: "muted" }, String(e))); return; }
  if (p.status === "not_applicable") { box.replaceChildren(h("p", { class: "muted" }, p.reason)); return; }
  const ok = p.status === "proved";
  box.replaceChildren(
    h("div", { class: "proof-head" },
      h("span", { class: "proof-eq" }, p.human),
      h("span", { class: `proof-ok ${ok ? "" : "proof-ko"}` }, ok ? `✓ proved — ${String(p.lean ?? "Lean").split(",")[0]} kernel` : p.status === "unchecked" ? "not checked" : "✕ failed")),
    h("pre", { class: "proof", html: highlightLean(p.code) }),
    h("p", { class: "muted" }, `${p.scope} Prouveur : ${p.prover}${p.reason ? " · " + p.reason : ""}.`));
}

function highlightLean(code) {
  let inBlock = false;
  return code.split("\n").map(line => {
    if (inBlock || line.startsWith("/-")) {
      if (line.includes("-/")) inBlock = false; else inBlock = true;
      return `<span class="cm">${esc(line)}</span>`;
    }
    const i = line.indexOf("--");
    const codePart = i >= 0 ? line.slice(0, i) : line, cm = i >= 0 ? line.slice(i) : "";
    const hl = esc(codePart)
      .replace(/\b(def|theorem|by|decide|Nat|#eval)\b/g, '<span class="kw">$1</span>')
      .replace(/(?<![\w#])(\d+)(?![\w])/g, '<span class="num">$1</span>')
      .replace(/\b(gap_[a-z_]+|wait_[a-z_]+|outside_[a-z_]+)\b/g, '<span class="th">$1</span>');
    return hl + (cm ? `<span class="cm">${esc(cm)}</span>` : "");
  }).join("\n");
}

async function loadPrecedents(a) {
  const box = $("#prec");
  let p;
  try { p = await api.precedents(state.caseId, a.key); } catch (e) { box.replaceChildren(h("p", { class: "muted" }, String(e))); return; }
  if (p.status !== "ok") { box.replaceChildren(h("p", { class: "muted" }, `${p.reason ?? "Not available."} No decision is ever cited from memory.`), h("p", { class: "mono", style: { color: "var(--ink-3)" } }, `query ready: “${p.query ?? ""}” · criminal chamber`)); return; }
  box.replaceChildren(h("p", { class: "muted", style: { marginTop: 0 } }, `${p.corpus} · ${p.total ?? p.results.length} result(s) · retrieved, never generated.`),
    h("ul", { class: "prec" }, p.results.map(r => h("li", {}, h("a", { href: r.url, target: "_blank", rel: "noopener" }, `Crim., ${r.date} — no. ${r.number}`), r.solution ? ` · ${r.solution}` : "", h("div", { class: "muted" }, r.snippet)))));
}

function deadlineMini() {
  const box = $("#deadline-mini");
  const dl = state.deadline;
  if (!box || !dl?.anchors?.length) return;
  const a = dl.anchors[0];
  box.replaceChildren(h("div", { class: "grief" }, h("b", {}, "Deadline (to verify): "),
    a.regimes.map(r => `${r.months} months → ${dmy(r.deadline)} (D${r.days_left >= 0 ? "-" + r.days_left : "+" + (-r.days_left)})`).join(" · "),
    ` · from the formal charge of ${a.person} on ${dmy(a.anchor)}.`));
}

export function close() {
  $("#overlay").hidden = true;
  document.body.style.overflow = "";
  set({ selectedAlert: null });
}

document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#overlay").hidden) close(); });
document.addEventListener("click", e => { if (e.target.matches?.("[data-close]")) close(); });
