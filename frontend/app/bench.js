// NullityBench-FR — measured, not promised. Numbers come from /benchmark only.
import { api } from "./api.js";
import { $, h, toast } from "./ui.js";

let polling = null;

export async function renderBench() {
  const { results: r, state: st } = await api.bench();
  $("#bench-run").onclick = async () => {
    await api.benchRun(10);
    toast("NullityBench-FR: generating and analysing 10 synthetic case files…");
    poll();
  };
  $("#bench-state").textContent = st.running ? `running ${st.done}/${st.total}` : st.error ? `error: ${st.error}` : "";
  if (st.running) poll();
  const box = $("#bench");
  if (!r) { box.replaceChildren(h("div", { class: "honesty" }, h("b", {}, "No measurement yet. "), "Run the benchmark: each case file is generated, analysed, then compared with its ground truth.")); return; }
  const cb = r.casebreak, o = cb.overall, pct = v => v === null || v === undefined ? "—" : `${Math.round(v * 100)}`;
  box.replaceChildren(
    h("div", { class: "kpis" },
      kpi(pct(o.recall), "recall (%) · injected nullities", true),
      kpi(pct(o.precision), "precision (%) · \"possible nullity\" alerts"),
      kpi(`${o.decoy_fp}/${o.decoys}`, "decoys wrongly flagged"),
      kpi(pct(cb.page_accuracy), "exact page (%)"),
      kpi(`${r.seconds_per_1000_pages ?? "—"}`, "seconds / 1,000 pages")),
    h("table", { class: "dense bars" },
      h("thead", {}, h("tr", {}, ["Nullity", "Found", "Missed", "False alerts", "Decoys", "Recall", "", "Precision", ""].map(x => h("th", {}, x)))),
      h("tbody", {}, cb.per_nullity.map(x => h("tr", {},
        h("td", {}, h("b", {}, x.nullity_id)), h("td", { class: "mono" }, x.tp), h("td", { class: "mono" }, x.fn), h("td", { class: "mono" }, x.fp),
        h("td", { class: "mono" }, `${x.decoy_fp}/${x.decoys}`),
        h("td", { class: "bar__v" }, pct(x.recall)), h("td", { class: "bar" }, bar(x.recall)),
        h("td", { class: "bar__v" }, pct(x.precision)), h("td", { class: "bar" }, bar(x.precision, true)))))),
    h("div", { class: "vs" },
      h("div", {}, h("h3", {}, "By certainty level"),
        h("table", { class: "attrs" }, Object.entries(cb.per_certainty).map(([k, v]) => h("tr", {},
          h("td", {}, { documented: "documented", inferred: "inferred", needs_reading: "needs reading" }[k] ?? k),
          h("td", {}, h("span", { class: "v" }, `${v.tp} correct · ${v.fp} wrong`), h("span", { class: "q" }, `precision ${pct(v.precision)}%`)))))),
      h("div", {}, h("h3", {}, "Comparison: LLM alone"),
        r.baseline.status === "ok"
          ? h("table", { class: "attrs" },
              h("tr", {}, h("td", {}, "Model"), h("td", {}, h("span", { class: "v" }, r.baseline.model))),
              h("tr", {}, h("td", {}, "Recall"), h("td", {}, h("span", { class: "v" }, `${pct(r.baseline.recall)}%`), h("span", { class: "q" }, `BREACH: ${pct(o.recall)}%`))),
              h("tr", {}, h("td", {}, "Precision"), h("td", {}, h("span", { class: "v" }, `${pct(r.baseline.precision)}%`), h("span", { class: "q" }, `BREACH: ${pct(o.precision)}%`))),
              h("tr", {}, h("td", {}, "Right rule, any page"), h("td", {}, h("span", { class: "v" }, `${pct(r.baseline.id_only_recall)}%`), h("span", { class: "q" }, r.baseline.matching ?? ""))))
          : h("p", { class: "muted" }, `Not run — ${r.baseline.reason}`))),
    h("div", { class: "honesty" }, h("b", {}, "To say honestly. "), r.honesty,
      h("div", { class: "mono", style: { marginTop: "8px", color: "var(--ink-3)" } }, `${r.n_dossiers} case files · ${r.pages} pages · generated ${r.generated_at}`)));
}

const kpi = (v, l, hot = false) => h("div", { class: `kpi ${hot ? "hot" : ""}` }, h("b", {}, v), h("span", {}, l));
const bar = (v, p = false) => h("div", { class: "bar__track" }, h("div", { class: `bar__fill ${p ? "p" : ""}`, style: { width: `${(v ?? 0) * 100}%` } }));

function poll() {
  clearInterval(polling);
  polling = setInterval(async () => {
    const { state: st } = await api.bench();
    $("#bench-state").textContent = st.running ? `running ${st.done}/${st.total}` : "";
    if (!st.running) { clearInterval(polling); renderBench(); }
  }, 1500);
}
