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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const d = iso => iso ? new Date(iso) : null;
export const hm = iso => { const x = d(iso); return x ? `${String(x.getHours()).padStart(2, "0")}:${String(x.getMinutes()).padStart(2, "0")}` : "?"; };
export const dmy = iso => { const x = d(iso); return x ? `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}/${x.getFullYear()}` : "?"; };
export const dm = iso => { const x = d(iso); return x ? `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}` : "?"; };
export const dayLabel = x => `${DAYS[x.getDay()]} ${x.getDate()} ${MONTHS[x.getMonth()]}`;
export const longDate = iso => { const x = d(iso); return x ? `${x.getDate()} ${MONTHS[x.getMonth()]} ${x.getFullYear()}` : "?"; };

// category id -> [label, subtitle] (the ids stay the French procedural categories of the data model)
export const CAT_FR = {
  TRAFFIC: ["Enforcement", "offence · keeper · notice"],
  KEEPER: ["Registered keeper", "post room · statements · reply"],
  COURT: ["Court", "summons · hearings"],
  INTERPELLATION: ["Arrest", "arrests"],
  GARDE_A_VUE: ["Custody", "placement · rights · end"],
  AUDITION: ["Hearings", "custody · witnesses"],
  PERQUISITION_SAISIE: ["Searches", "seizures · seals · photos"],
  EXPERTISE: ["Forensics", "seal analyses"],
  GEOLOCALISATION: ["Geolocation", "trackers"],
  INTERCEPTIONS: ["Interceptions", "wiretaps"],
  INSTRUCTION: ["Judicial investigation", "judge · formal charge"],
  AUTRE: ["Other documents", "complaints · annexes"],
};
export const CERT = { documented: ["documented", "pill--doc"], inferred: ["inferred", "pill--inf"], needs_reading: ["needs reading", "pill--read"] };
export const VERDICT = {
  survives: ["Survives", ""], survives_with_caveats: ["Survives?", ""], weakened: ["Weakened", "stamp--fragile"],
  to_investigate: ["To investigate", "stamp--instruire"],
};
export const ATTR_FR = {
  custody_start: "Custody start", custody_end: "Custody end", custody_start_stated: "Placement (as stated)",
  placed_at_stated: "Placement (as stated)", notified_at: "Rights notified", arrest_time: "Arrest",
  prosecutor_informed_at: "Prosecutor informed", understands_french: "Understands French", language: "Language",
  objectives_text: "Grounds", interpreter_present: "Interpreter", delay_justification: "Delay justification",
  lawyer_requested: "Lawyer requested", doctor_requested: "Doctor requested", family_requested: "Relative to inform",
  signed: "Signed", lawyer_notified_at: "Lawyer notified", family_notified_at: "Relative informed", exam_at: "Medical examination",
  authorized_at: "Authorisation", extension_authorized: "Extension", extension_from: "Extension from",
  extension_authorized_at: "Extension authorised at", end_time: "End", end_date: "End date", start: "Start", end: "End",
  in_custody: "In custody", lawyer_present: "Lawyer present", lawyer_waiver: "Waiver of lawyer",
  prosecutor_authorization: "Prosecutor authorisation", lawyer_notified_at_stated: "Lawyer notified (as stated)",
  place: "Place", is_home: "Home", occupant_present: "Occupant present", witnesses_present: "Two witnesses",
  consent: "Consent", jld_authorization: "JLD authorisation", item: "Item", seal_number: "Seal",
  seals_analysed: "Seals analysed", authorization_ref: "Authorisation cited", authorization_date: "Authorisation date",
  date: "Date", person_name: "Person", exif_time: "EXIF timestamp", seal_label: "Label", orphan_seals: "Seal without seizure",
  custody_start_conflict: "Conflicting times", exif_conflict: "EXIF inconsistency", special_regime: "Special regime",
  cited_missing: "Cited report missing", geoloc_used: "Geolocation used", custody_id: "Custody", custody_end_date: "End date",
  start_date_only: "Date (time unreadable)", seized: "Seized",
  offence_at: "Offence", offence_place: "Place of offence", speed_recorded: "Recorded speed (mph)", speed_limit: "Speed limit (mph)",
  keeper_name: "Registered keeper", nip_posted_at: "Notice posted", nip_addressee: "Notice addressed to",
  nip_service_method: "Method of service", offence_stated_at: "Offence (as stated in the notice)",
  offence_place_stated: "Place (as stated in the notice)", offence_nature_stated: "Nature (as stated in the notice)",
  nip_received_at: "Notice received", nip_received_stated: "Notice received (as stated)", driver_name: "Driver identified",
  response_date: "Response", summons_date: "Summons", hearing_at: "Hearing", plea: "Plea", statement_date: "Statement",
  notice_date: "Notice date", enquiry_date: "Enquiry", court: "Court",
};

// document types of the case file (French police/court documents) -> English label
export const DOC_TYPE = {
  PV_INTERPELLATION: "Arrest report", PV_PLACEMENT_GAV: "Custody placement report", PV_NOTIFICATION_DROITS: "Rights notification report",
  PV_AVIS_AVOCAT: "Lawyer notice", PV_AVIS_FAMILLE: "Relative notice", PV_EXAMEN_MEDICAL: "Medical examination report",
  AUTORISATION_PROLONGATION: "Custody extension authorisation", PV_FIN_GAV: "End-of-custody report", PV_AUDITION_GAV: "Custody hearing report",
  SPEED_OFFENCE_REPORT: "Speed camera offence report", KEEPER_ENQUIRY: "Registered keeper enquiry", NIP: "Notice of intended prosecution",
  POST_ROOM_REGISTER: "Post room register", WITNESS_STATEMENT: "Witness statement", DRIVER_IDENTIFICATION: "Driver identification",
  SUMMONS: "Summons", COURT_HEARING_RECORD: "Court record",
  PV_AUDITION_TEMOIN: "Witness hearing report", PV_PERQUISITION: "Search and seizure report", PV_EXPLOITATION: "Seal analysis report",
  RAPPORT_EXPERTISE: "Expert report", ORDONNANCE_EXPERTISE: "Expert appointment order", AUTORISATION_GEOLOC: "Geolocation authorisation",
  PV_GEOLOCALISATION: "Geolocation report", ORDONNANCE_INTERCEPTION: "Interception order", PV_INTERCEPTION: "Interception transcript",
  REQUISITOIRE_INTRODUCTIF: "Opening of judicial investigation", PV_MISE_EN_EXAMEN: "First appearance / formal charge",
  ARRET_CHAMBRE_INSTRUCTION: "Investigating chamber ruling", PV_PLAINTE: "Complaint", PV_VIDEOPROTECTION: "CCTV review",
  PV_CONSTATATIONS: "Findings report", PV_REQUISITION: "Information request", PV_ANNEXE: "Annex", PHOTO: "Photograph", INCONNU: "Document",
};
export const docType = p => (p && (DOC_TYPE[p.type] ?? p.title)) || "";

export function fmtVal(k, v) {
  if (v === true) return "yes";
  if (v === false) return "no";
  if (v === null || v === undefined) return "—";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(v)) return `${dmy(v)} ${hm(v)}`;
  if (k === "consent") return { handwritten: "handwritten", verbal: "verbal" }[v] ?? v;
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
