// BREACH — API client. Same origin by default; override with window.BREACH_API.
const BASE = window.BREACH_API ?? "";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") ?? "";
  return ct.includes("json") ? res.json() : res.text();
}

const qs = o => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "" && v !== false) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  base: BASE,
  engines: () => req("/api/engines"),
  reforms: () => req("/api/law/reforms"),
  cases: () => req("/cases"),
  demo: (pace = 1) => req(`/cases/demo${qs({ pace })}`, { method: "POST" }),
  status: id => req(`/cases/${id}/status`),
  graph: (id, o = {}) => req(`/cases/${id}/graph${qs(o)}`),
  alerts: (id, o = {}) => req(`/cases/${id}/alerts${qs(o)}`),
  alert: (id, aid, o = {}) => req(`/cases/${id}/alerts/${encodeURIComponent(aid)}${qs(o)}`),
  simulate: (id, node_id) => req(`/cases/${id}/simulate`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id }) }),
  review: (id, aid, decision, note = "") => req(`/cases/${id}/alerts/${encodeURIComponent(aid)}/review`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, note }) }),
  tribunal: (id, aid, o = {}) => req(`/cases/${id}/alerts/${encodeURIComponent(aid)}/tribunal${qs(o)}`),
  proof: (id, aid, o = {}) => req(`/cases/${id}/alerts/${encodeURIComponent(aid)}/proof${qs(o)}`),
  precedents: (id, aid) => req(`/cases/${id}/alerts/${encodeURIComponent(aid)}/precedents`),
  page: (id, doc, page, o = {}) => req(`/cases/${id}/pages/${encodeURIComponent(doc)}/${page}${qs(o)}`),
  report: (id, o = {}) => req(`/cases/${id}/report${qs(o)}`),
  reportUrl: (id, o = {}) => `${BASE}/cases/${id}/report${qs(o)}`,
  imgUrl: path => BASE + path,
  bench: () => req("/benchmark"),
  benchRun: n => req(`/benchmark/run${qs({ n })}`, { method: "POST" }),
};
