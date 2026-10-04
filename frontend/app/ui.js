// DOM + formatting helpers.
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}

export const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const JOURS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
export const d = iso => iso ? new Date(iso) : null;
export const hm = iso => { const x = d(iso); return x ? `${String(x.getHours()).padStart(2, "0")}h${String(x.getMinutes()).padStart(2, "0")}` : "?"; };
export const dmy = iso => { const x = d(iso); return x ? `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}/${x.getFullYear()}` : "?"; };
export const dm = iso => { const x = d(iso); return x ? `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}` : "?"; };
export const dayLabel = x => `${JOURS[x.getDay()]} ${x.getDate()} ${MOIS[x.getMonth()]}`;
export const longDate = iso => { const x = d(iso); return x ? `${x.getDate()} ${MOIS[x.getMonth()]} ${x.getFullYear()}` : "?"; };

export const CAT_FR = {
  INTERPELLATION: ["Interpellation", "arrestation"],
  GARDE_A_VUE: ["Garde à vue", "placement · droits · fin"],
  AUDITION: ["Auditions", "gardés à vue · témoins"],
  PERQUISITION_SAISIE: ["Perquisitions", "saisies · scellés · photos"],
  EXPERTISE: ["Expertises", "scellés exploités"],
  GEOLOCALISATION: ["Géolocalisation", "balises"],
  INTERCEPTIONS: ["Interceptions", "écoutes"],
  INSTRUCTION: ["Instruction", "juge · mise en examen"],
  AUTRE: ["Autres pièces", "plaintes · annexes"],
};
export const CERT = { documented: ["documenté", "pill--doc"], inferred: ["déduit", "pill--inf"], needs_reading: ["à lire", "pill--read"] };
export const VERDICT = {
  survit: ["Survit", ""], survit_sous_reserve: ["Survit ?", ""], fragilise: ["Fragilisé", "stamp--fragile"],
  a_instruire: ["À instruire", "stamp--instruire"],
};
export const ATTR_FR = {
  custody_start: "Début de garde à vue", custody_end: "Fin de garde à vue", custody_start_stated: "Placement (déclaré)",
  placed_at_stated: "Placement (déclaré)", notified_at: "Droits notifiés", arrest_time: "Interpellation",
  prosecutor_informed_at: "Avis au procureur", understands_french: "Comprend le français", language: "Langue",
  objectives_text: "Motivation", interpreter_present: "Interprète", delay_justification: "Justification du délai",
  lawyer_requested: "Avocat demandé", doctor_requested: "Médecin demandé", family_requested: "Proche à prévenir",
  signed: "Signé", lawyer_notified_at: "Avocat avisé", family_notified_at: "Proche avisé", exam_at: "Examen médical",
  authorized_at: "Autorisation", extension_authorized: "Prolongation", extension_from: "Prolongation à compter de",
  extension_authorized_at: "Prolongation autorisée à", end_time: "Fin", end_date: "Date de fin", start: "Début", end: "Fin",
  in_custody: "En garde à vue", lawyer_present: "Avocat présent", lawyer_waiver: "Renonciation à l'avocat",
  prosecutor_authorization: "Autorisation du procureur", lawyer_notified_at_stated: "Avocat avisé (déclaré)",
  place: "Lieu", is_home: "Domicile", occupant_present: "Occupant présent", witnesses_present: "Deux témoins",
  consent: "Assentiment", jld_authorization: "Autorisation JLD", item: "Objet", seal_number: "Scellé",
  seals_analysed: "Scellés analysés", authorization_ref: "Autorisation visée", authorization_date: "Date d'autorisation",
  date: "Date", person_name: "Personne", exif_time: "Horodatage EXIF", seal_label: "Étiquette", orphan_seals: "Scellé sans saisie",
  custody_start_conflict: "Heures divergentes", exif_conflict: "Incohérence EXIF", special_regime: "Régime dérogatoire",
  cited_missing: "PV cité absent", geoloc_used: "Géolocalisation utilisée", custody_id: "Garde à vue", custody_end_date: "Date de fin",
  start_date_only: "Date (heure illisible)", seized: "Saisi",
};

export function fmtVal(k, v) {
  if (v === true) return "oui";
  if (v === false) return "non";
  if (v === null || v === undefined) return "—";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(v)) return `${dmy(v)} ${hm(v)}`;
  if (k === "consent") return { handwritten: "écrit de la main", verbal: "verbal" }[v] ?? v;
  return String(v);
}

export function toast(msg, ms = 3800) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));
export const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// count-up in small jumps (stop-motion), never interpolated decimals
export function countTo(el, to, ms = 500) {
  const from = Number(el.dataset.v ?? 0);
  if (from === to) return;
  el.dataset.v = to;
  if (REDUCED) { el.textContent = to; return; }
  const steps = 6;
  let i = 0;
  clearInterval(el._t);
  el._t = setInterval(() => {
    i++;
    el.textContent = Math.round(from + (to - from) * (i / steps));
    if (i >= steps) clearInterval(el._t);
  }, ms / steps);
  const box = el.closest(".counter");
  if (box) { box.classList.remove("bump"); void box.offsetWidth; box.classList.add("bump"); }
}
