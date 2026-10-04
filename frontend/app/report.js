// Rapport — Markdown from the API rendered as a brief; PDF/MD downloads.
import { api } from "./api.js";
import { state } from "./state.js";
import { $, esc } from "./ui.js";

export async function renderReport() {
  const o = { mode: state.mode, as_of: state.asOf, pseudo: state.pseudo };
  $("#report-mode").textContent = state.mode === "parquet" ? "audit de régularité (parquet)" : "défense";
  $("#dl-md").href = api.reportUrl(state.caseId, { ...o, format: "md" });
  $("#dl-pdf").href = api.reportUrl(state.caseId, { ...o, format: "pdf" });
  $("#report").innerHTML = "<p class='muted'>Rédaction…</p>";
  const md = await api.report(state.caseId, { ...o, format: "md" });
  $("#report").innerHTML = markdown(md);
}

function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<em>$2</em>")
    .replace(/_(.+?)_/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
}

export function markdown(md) {
  const out = [];
  let list = null;
  const flush = () => { if (list) { out.push(`<${list.t}>${list.items.map(i => `<li>${i}</li>`).join("")}</${list.t}>`); list = null; } };
  for (const raw of md.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    let m;
    if ((m = line.match(/^(#{1,3}) (.*)/))) { flush(); out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`); }
    else if ((m = line.match(/^(\s*)- (.*)/))) { if (!list) list = { t: "ul", items: [] }; list.items.push(m[1].length ? `<span style="padding-left:18px;display:inline-block">${inline(m[2])}</span>` : inline(m[2])); }
    else if (line.startsWith("> ")) { flush(); out.push(`<blockquote>${inline(line.slice(2))}</blockquote>`); }
    else if (line === "---") { flush(); out.push("<hr>"); }
    else if (!line.trim()) { flush(); }
    else { flush(); out.push(`<p>${inline(line)}</p>`); }
  }
  flush();
  return out.join("\n");
}
