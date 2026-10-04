// War room — live counters while the pipeline reads the file. Every number comes from /status.
import { api } from "./api.js";
import { $, h, countTo, CAT_FR } from "./ui.js";

const COUNTERS = [
  ["pages", "pages read", c => c.pages_ocr ? `${c.pages_ocr} by OCR` : ""],
  ["pieces", "documents classified", () => ""],
  ["acts", "acts rebuilt", c => c.llm_filled ? `+${c.llm_filled} by Mistral` : ""],
  ["quotes_verified", "quotes verified", () => "on the page"],
  ["supports", "dependency links", c => c.contradictions ? `${c.contradictions} contradictions` : ""],
  ["possible_nullity", "possible nullities", c => c.needs_reading ? `+${c.needs_reading} to read` : ""],
];
const KIND_FR = { piece: "document", ocr: "ocr", act: "act", alert: "alert", contradiction: "contradiction", cascade: "domino",
  warn: "to read", done: "ready", error: "error", info: "info" };

export function startWarroom(caseId, onDone) {
  const root = $("#warroom");
  root.hidden = false;
  $("#war-case").textContent = caseId;
  $("#war-title").textContent = "Reading the case file";
  $("#war-open").disabled = true;
  const counters = $("#counters");
  counters.replaceChildren(...COUNTERS.map(([k, l], i) => h("div", { class: `counter ${i === 5 ? "counter--alert" : i === 3 ? "counter--hot" : ""}`, "data-k": k },
    h("div", { class: "counter__n", "data-v": 0 }, "0"), h("div", { class: "counter__l" }, l), h("span", { class: "counter__sub" }))));
  $("#war-log").replaceChildren();
  $("#stages").replaceChildren();
  $("#lanes-preview").replaceChildren();
  let seen = 0, pagesShown = 0, t0 = Date.now(), stop = false;
  const clock = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    $("#war-clock").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 250);

  async function tick() {
    if (stop) return;
    let st;
    try { st = await api.status(caseId); } catch { setTimeout(tick, 600); return; }
    const c = st.counters ?? {};
    for (const [k, , sub] of COUNTERS) {
      const box = counters.querySelector(`[data-k="${k}"]`);
      countTo(box.querySelector(".counter__n"), c[k] ?? 0, 300);
      box.querySelector(".counter__sub").textContent = sub(c);
    }
    renderStages(st);
    renderLanes(st.categories ?? {});
    // log stream
    const log = st.log ?? [];
    const ol = $("#war-log");
    for (const e of log.slice(seen)) {
      ol.prepend(h("li", { class: `k-${e.kind}` }, h("time", {}, `${e.t.toFixed(1)}s`), h("span", { class: "k" }, KIND_FR[e.kind] ?? e.kind), h("span", {}, e.msg)));
    }
    while (ol.children.length > 80) ol.lastChild.remove();
    seen = log.length;
    if (st.state === "done") {
      $("#war-title").textContent = `${c.possible_nullity} possible nullities, ${c.needs_reading} points to read`;
      $("#war-sub").textContent = `${c.pages} pages · ${c.pieces} documents · ${c.acts} acts · ${c.supports} dependency links — every alert points to its page.`;
      $("#war-open").disabled = false;
      $("#war-open").focus({ preventScroll: true });
      clearInterval(clock);
      stop = true;
      onDone?.(st);
      return;
    }
    if (st.state === "error") {
      $("#war-title").textContent = "Error during the analysis";
      $("#war-sub").textContent = st.error ?? "";
      clearInterval(clock);
      return;
    }
    setTimeout(tick, 320);
  }
  tick();
  return () => { stop = true; clearInterval(clock); root.hidden = true; };
}

function renderStages(st) {
  const ol = $("#stages");
  const entries = Object.entries(st.stages ?? {});
  if (ol.children.length !== entries.length) {
    ol.replaceChildren(...entries.map(([k, s]) => h("li", { "data-s": k }, h("span", { class: "dot" }),
      h("span", {}, h("b", {}, s.label), h("small", {}, s.detail)), h("span", { class: "st" }, ""))));
  }
  for (const [k, s] of entries) {
    const li = ol.querySelector(`[data-s="${k}"]`);
    li.className = `is-${s.state}`;
    li.querySelector(".st").textContent = { pending: "pending", running: "running", done: "done" }[s.state] ?? s.state;
  }
}

function renderLanes(cats) {
  const box = $("#lanes-preview");
  const max = Math.max(1, ...Object.values(cats));
  for (const k of Object.keys(CAT_FR)) {
    if (!(k in cats)) continue;
    let row = box.querySelector(`[data-c="${k}"]`);
    if (!row) {
      row = h("div", { class: "lp", "data-c": k }, h("span", {}, CAT_FR[k][0]), h("div", { class: "lp__bar" }, h("i")), h("b", {}, "0"));
      box.append(row);
    }
    row.querySelector("i").style.width = `${(cats[k] / max) * 100}%`;
    row.querySelector("b").textContent = cats[k];
  }
}
