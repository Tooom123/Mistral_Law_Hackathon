// Salle des opérations — live counters while the pipeline reads the file. Every number comes from /status.
import { api } from "./api.js";
import { $, h, countTo, CAT_FR, REDUCED } from "./ui.js";

const COUNTERS = [
  ["pages", "pages lues", c => c.pages_ocr ? `${c.pages_ocr} OCR` : ""],
  ["pieces", "pièces classées", () => ""],
  ["acts", "actes reconstitués", () => ""],
  ["quotes_verified", "citations vérifiées", () => "sur la page"],
  ["supports", "liens de dépendance", c => c.contradictions ? `${c.contradictions} contradictions` : ""],
  ["possible_nullity", "nullités possibles", c => c.needs_reading ? `+${c.needs_reading} à lire` : ""],
];
const KIND_FR = { piece: "pièce", ocr: "ocr", act: "acte", alert: "alerte", contradiction: "contradiction", cascade: "domino",
  warn: "à lire", done: "prêt", error: "erreur", info: "info" };

export function startWarroom(caseId, onDone) {
  const root = $("#warroom");
  root.hidden = false;
  $("#war-case").textContent = caseId;
  $("#war-title").textContent = "Lecture du dossier";
  $("#war-open").disabled = true;
  const counters = $("#counters");
  counters.replaceChildren(...COUNTERS.map(([k, l], i) => h("div", { class: `counter ${i === 5 ? "counter--alert" : i === 3 ? "counter--hot" : ""}`, "data-k": k },
    h("div", { class: "counter__n", "data-v": 0 }, "0"), h("div", { class: "counter__l" }, l), h("span", { class: "counter__sub" }))));
  $("#war-log").replaceChildren();
  $("#pagestrip").replaceChildren();
  $("#stages").replaceChildren();
  $("#lanes-preview").replaceChildren();
  const pix = pixels($("#war-pixels"));
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
    // page strip: one sheet per page read (scans and photos marked)
    const ocr = c.pages_ocr ?? 0, imgs = c.images ?? 0;
    while (pagesShown < (c.pages ?? 0) && pagesShown < 400) {
      pagesShown++;
      const isImg = pagesShown > (c.pages - imgs);
      const kind = isImg ? "img" : (pagesShown % Math.max(2, Math.round((c.pages || 1) / Math.max(1, ocr - imgs))) === 0 && ocr ? "scan" : "");
      const strip = $("#pagestrip");
      strip.append(h("span", { class: kind }, h("em", {}, pagesShown)));
      if (strip.children.length > 40) strip.firstChild.remove();
    }
    // log stream
    const log = st.log ?? [];
    const ol = $("#war-log");
    for (const e of log.slice(seen)) {
      ol.prepend(h("li", { class: `k-${e.kind}` }, h("time", {}, `${e.t.toFixed(1)}s`), h("span", { class: "k" }, KIND_FR[e.kind] ?? e.kind), h("span", {}, e.msg)));
      if (e.kind === "alert") flagLastPage();
    }
    while (ol.children.length > 80) ol.lastChild.remove();
    seen = log.length;
    const done = Object.values(st.stages ?? {}).filter(s => s.state === "done").length;
    pix.heat(done / Math.max(1, Object.keys(st.stages ?? {}).length), (c.possible_nullity ?? 0) > 0);
    if (st.state === "done") {
      $("#war-title").textContent = `${c.possible_nullity} nullités possibles, ${c.needs_reading} points à lire`;
      $("#war-sub").textContent = `${c.pages} pages · ${c.pieces} pièces · ${c.acts} actes · ${c.supports} liens de dépendance — chaque alerte renvoie à sa page.`;
      $("#war-open").disabled = false;
      $("#war-open").focus();
      clearInterval(clock);
      stop = true;
      onDone?.(st);
      return;
    }
    if (st.state === "error") {
      $("#war-title").textContent = "Erreur pendant l'analyse";
      $("#war-sub").textContent = st.error ?? "";
      clearInterval(clock);
      return;
    }
    setTimeout(tick, 320);
  }
  tick();
  return () => { stop = true; clearInterval(clock); pix.stop(); root.hidden = true; };
}

function flagLastPage() {
  const last = $("#pagestrip").lastElementChild;
  if (last) last.classList.add("flag");
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
    li.querySelector(".st").textContent = { pending: "en attente", running: "en cours", done: "fait" }[s.state] ?? s.state;
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

// Ordered (Bayer) dithering in the Mistral ramp, rising from the bottom as the pipeline advances.
function pixels(canvas) {
  const ctx = canvas.getContext("2d");
  const B = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]].map(r => r.map(v => (v + .5) / 16));
  const RAMP = ["#2A1A10", "#5A2A0A", "#FFAF01", "#FF8204", "#FA500F", "#E61300", "#C4001D"];
  let cols = 0, rows = 0, level = 0, target = 0, hot = false, raf = 0, last = 0;
  const phase = [];
  function resize() {
    const r = canvas.getBoundingClientRect();
    const cell = r.width < 760 ? 12 : 22;
    cols = Math.ceil(r.width / cell); rows = Math.ceil(r.height / cell);
    canvas.width = cols; canvas.height = rows;
    phase.length = 0;
    for (let i = 0; i < cols * rows; i++) phase.push(Math.random() * 6.28);
  }
  function draw(t) {
    ctx.clearRect(0, 0, cols, rows);
    level += (target - level) * .2;
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const i = y * cols + x;
      const fromBottom = 1 - y / rows;
      const edge = Math.min(x, cols - 1 - x) / cols;
      let v = (level * .4 - fromBottom * 1.35 + .22) + edge * 0 + .06 * Math.sin(t * .0005 + phase[i]) - edge * .9;
      if (hot) v += .05 * Math.sin(t * .002 + x * .3);
      if (v < .12 || v <= B[y & 3][x & 3]) continue;
      ctx.fillStyle = RAMP[Math.min(RAMP.length - 1, Math.floor(v * RAMP.length * 1.2 + (hot ? 1 : 0)))];
      ctx.globalAlpha = .38;
      ctx.fillRect(x, y, 1, 1);
    }
  }
  function loop(t) { if (t - last > 140) { draw(t); last = t; } raf = requestAnimationFrame(loop); }
  resize();
  window.addEventListener("resize", resize);
  if (!REDUCED) raf = requestAnimationFrame(loop); else draw(0);
  return { heat(p, h) { target = p; hot = h; if (REDUCED) draw(0); }, stop() { cancelAnimationFrame(raf); } };
}
