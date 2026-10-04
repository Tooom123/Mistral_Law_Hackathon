// NullityBench-FR — measured, not promised. Numbers come from /benchmark only.
import { api } from "./api.js";
import { $, h, toast } from "./ui.js";

let polling = null;

export async function renderBench() {
  const { results: r, state: st } = await api.bench();
  $("#bench-run").onclick = async () => {
    await api.benchRun(10);
    toast("NullityBench-FR : 10 dossiers synthétiques en cours de génération et d'analyse…");
    poll();
  };
  $("#bench-state").textContent = st.running ? `en cours ${st.done}/${st.total}` : st.error ? `erreur : ${st.error}` : "";
  if (st.running) poll();
  const box = $("#bench");
  if (!r) { box.replaceChildren(h("div", { class: "honesty" }, h("b", {}, "Pas encore de mesure. "), "Lancez le banc : chaque dossier est généré, analysé puis comparé à sa vérité terrain.")); return; }
  const cb = r.casebreak, o = cb.overall, pct = v => v === null || v === undefined ? "—" : `${Math.round(v * 100)}`;
  box.replaceChildren(
    h("div", { class: "kpis" },
      kpi(pct(o.recall), "rappel (%) · nullités injectées", true),
      kpi(pct(o.precision), "précision (%) · alertes « nullité possible »"),
      kpi(`${o.decoy_fp}/${o.decoys}`, "leurres signalés à tort"),
      kpi(pct(cb.page_accuracy), "page exacte (%)"),
      kpi(`${r.seconds_per_1000_pages ?? "—"}`, "secondes / 1 000 pages")),
    h("table", { class: "dense bars" },
      h("thead", {}, h("tr", {}, ["Nullité", "Trouvées", "Manquées", "Fausses alertes", "Leurres", "Rappel", "", "Précision", ""].map(x => h("th", {}, x)))),
      h("tbody", {}, cb.per_nullity.map(x => h("tr", {},
        h("td", {}, h("b", {}, x.nullity_id)), h("td", { class: "mono" }, x.tp), h("td", { class: "mono" }, x.fn), h("td", { class: "mono" }, x.fp),
        h("td", { class: "mono" }, `${x.decoy_fp}/${x.decoys}`),
        h("td", { class: "bar__v" }, pct(x.recall)), h("td", { class: "bar" }, bar(x.recall)),
        h("td", { class: "bar__v" }, pct(x.precision)), h("td", { class: "bar" }, bar(x.precision, true)))))),
    h("div", { class: "vs" },
      h("div", {}, h("h3", {}, "Par niveau de certitude"),
        h("table", { class: "attrs" }, Object.entries(cb.per_certainty).map(([k, v]) => h("tr", {},
          h("td", {}, { documented: "documenté", inferred: "déduit", needs_reading: "à lire" }[k] ?? k),
          h("td", {}, h("span", { class: "v" }, `${v.tp} justes · ${v.fp} fausses`), h("span", { class: "q" }, `précision ${pct(v.precision)} %`)))))),
      h("div", {}, h("h3", {}, "Comparaison : LLM seul"),
        r.baseline.status === "ok"
          ? h("table", { class: "attrs" },
              h("tr", {}, h("td", {}, "Modèle"), h("td", {}, h("span", { class: "v" }, r.baseline.model))),
              h("tr", {}, h("td", {}, "Rappel"), h("td", {}, h("span", { class: "v" }, `${pct(r.baseline.recall)} %`), h("span", { class: "q" }, `BREACH : ${pct(o.recall)} %`))),
              h("tr", {}, h("td", {}, "Précision"), h("td", {}, h("span", { class: "v" }, `${pct(r.baseline.precision)} %`), h("span", { class: "q" }, `BREACH : ${pct(o.precision)} %`))),
              h("tr", {}, h("td", {}, "Page exacte"), h("td", {}, h("span", { class: "v" }, `${pct(r.baseline.page_accuracy)} %`))))
          : h("p", { class: "muted" }, `Non exécutée — ${r.baseline.reason}`))),
    h("div", { class: "honesty" }, h("b", {}, "À dire honnêtement. "), r.honesty,
      h("div", { class: "mono", style: { marginTop: "8px", color: "var(--ink-3)" } }, `${r.n_dossiers} dossiers · ${r.pages} pages · généré le ${r.generated_at}`)));
}

const kpi = (v, l, hot = false) => h("div", { class: `kpi ${hot ? "hot" : ""}` }, h("b", {}, v), h("span", {}, l));
const bar = (v, p = false) => h("div", { class: "bar__track" }, h("div", { class: `bar__fill ${p ? "p" : ""}`, style: { width: `${(v ?? 0) * 100}%` } }));

function poll() {
  clearInterval(polling);
  polling = setInterval(async () => {
    const { state: st } = await api.bench();
    $("#bench-state").textContent = st.running ? `en cours ${st.done}/${st.total}` : "";
    if (!st.running) { clearInterval(polling); renderBench(); }
  }, 1500);
}
