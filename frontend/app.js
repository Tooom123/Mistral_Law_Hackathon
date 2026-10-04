/* BREACH — landing: pixel background, case-file upload, pipeline start, scroll motion.
   No invented numbers: counters come from the dropped files
   (count, size, PDF pages read by pdf.js) or from the backend. */

(() => {
  "use strict";

  // Backend base URL. Override with: <script>window.BREACH_API = "http://localhost:8000"</script>
  const API_BASE = window.BREACH_API ?? "";
  const PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const $ = (sel, root = document) => root.querySelector(sel);

  /* ================================================================
     1. Pixel background — ordered (Bayer) dithering in the Mistral ramp
     ================================================================ */

  const BAYER = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
  ].map(row => row.map(v => (v + 0.5) / 16));

  // lightest to warmest
  const RAMP = ["#FFE8D2", "#FFD3AA", "#FFAF01", "#FF8204", "#FA500F", "#E61300", "#C4001D"];

  const smooth = (a, b, x) => {
    const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  };

  // low-frequency value noise: groups pixels into clusters rather than confetti
  const SEED = (Math.random() * 1e9) | 0;
  const hash = (x, y) => {
    let n = Math.imul(x, 374761393) + Math.imul(y, 668265263) + SEED;
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
  };
  const noise = (x, y) => {
    const xi = Math.floor(x), yi = Math.floor(y);
    const sx = smooth(0, 1, x - xi), sy = smooth(0, 1, y - yi);
    const top = hash(xi, yi) + (hash(xi + 1, yi) - hash(xi, yi)) * sx;
    const bot = hash(xi, yi + 1) + (hash(xi + 1, yi + 1) - hash(xi, yi + 1)) * sx;
    return top + (bot - top) * sy;
  };

  // heat of a cell (x, y in cells) + tint offset (-1 lighter, +1 warmer)
  const HEAT = {
    // two columns of tiles flanking the upload card's height, at the screen edges:
    // densest level with the card, thinning out above and below; text stays clear
    hero(x, y, cols, rows, { box, boost }) {
      if (!box) return { h: 0, tint: 0 };
      const edge = Math.min(x + 0.5, cols - x - 0.5);                 // distance to the nearest screen edge
      const width = (innerWidth < 760 ? 1.4 : Math.min(7, Math.max(3, cols * 0.11))) * (1 + 0.5 * boost);
      const across = 1 - smooth(0, width, edge);
      const mid = (box.y0 + box.y1) / 2, half = (box.y1 - box.y0) / 2;
      const along = 1 - smooth(half * 0.4, half + 4, Math.abs(y - mid));   // vertical window around the card
      let h = across * along;
      h *= 0.5 + 0.8 * noise(x / 3, y / 3);
      return { h, tint: x < cols / 2 ? -0.8 : 0.5 };                  // left sunnier, right redder
    },
  };

  // layout position of el inside ancestor, ignoring transforms (reveal animations)
  function offsetWithin(el, ancestor) {
    let x = 0, y = 0;
    for (let n = el; n && n !== ancestor; n = n.offsetParent) { x += n.offsetLeft; y += n.offsetTop; }
    return { x, y, w: el.offsetWidth, h: el.offsetHeight };
  }

  function pixelField(canvas) {
    const ctx = canvas.getContext("2d");
    const kind = canvas.dataset.pixels;
    const anchor = canvas.dataset.anchor && document.querySelector(canvas.dataset.anchor);
    let cols = 0, rows = 0, cell = 28, phase = [], boost = 0, target = 0, visible = true, box = null;

    function resize() {
      const { width, height } = canvas.parentElement.getBoundingClientRect();
      cell = width < 760 ? 12 : 32;
      cols = Math.ceil(width / cell);
      rows = Math.ceil(height / cell);
      canvas.width = cols;           // 1 canvas pixel = 1 cell, upscaled in CSS (pixelated)
      canvas.height = rows;
      canvas.style.width = cols * cell + "px";
      canvas.style.height = rows * cell + "px";
      phase = Array.from({ length: cols * rows }, () => Math.random() * Math.PI * 2);
      if (anchor) {
        const r = offsetWithin(anchor, canvas.parentElement);
        box = { x0: r.x / cell, x1: (r.x + r.w) / cell, y0: r.y / cell, y1: (r.y + r.h) / cell };
      }
      draw(0);
    }

    function draw(t) {
      ctx.clearRect(0, 0, cols, rows);
      boost += (target - boost) * 0.25;
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const i = y * cols + x;
          let { h, tint } = HEAT[kind](x, y, cols, rows, { box, boost });
          h += 0.07 * Math.sin(t * 0.0004 + phase[i]) + boost * (h > 0.05 ? 0.22 : 0);
          if (h < 0.16 || h <= BAYER[y & 3][x & 3]) continue;   // threshold: no stray pixels in the middle
          const k = Math.min(RAMP.length - 1, Math.max(0, Math.floor(h * RAMP.length + tint + (phase[i] - 3.1) * 0.25)));
          ctx.fillStyle = RAMP[k];
          ctx.fillRect(x, y, 1, 1);
        }
      }
    }

    // animate in small jumps (stop-motion) rather than a continuous fade
    let last = 0;
    function loop(t) {
      if (visible && t - last > 400) { draw(t); last = t; }
      requestAnimationFrame(loop);
    }

    const ro = new ResizeObserver(resize);
    ro.observe(canvas.parentElement);
    if (anchor) ro.observe(anchor);   // the card shrinks once files are added
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(canvas);
    if (!REDUCED_MOTION) requestAnimationFrame(loop);

    return { excite(on) { target = on ? 1 : 0; if (REDUCED_MOTION) { boost = target; draw(0); } } };
  }

  const fields = [...document.querySelectorAll("canvas[data-pixels]")].map(pixelField);
  const heroField = fields[0];

  /* ================================================================
     2. File upload
     ================================================================ */

  const card = $("#card");
  const dropzone = $("#dropzone");
  const input = $("#file-input");
  const listEl = $("#file-list");
  const statsEl = $("#stats");
  const filesEl = $("#files");
  const toastEl = $("#toast");

  /** @type {{id:string, file:File, kind:string, pages:number|null|undefined}[]} */
  let items = [];

  const KINDS = {
    pdf: { label: "PDF", test: (f, ext) => f.type === "application/pdf" || ext === "pdf" },
    img: { label: "IMG", test: (f, ext) => f.type.startsWith("image/") || ["png", "jpg", "jpeg", "tif", "tiff", "heic", "webp"].includes(ext) },
    audio: { label: "AUD", test: (f, ext) => f.type.startsWith("audio/") || ["mp3", "wav", "m4a"].includes(ext) },
  };
  const kindOf = f => {
    const ext = f.name.split(".").pop().toLowerCase();
    return Object.keys(KINDS).find(k => KINDS[k].test(f, ext)) ?? "other";
  };

  const fmtSize = b => b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  function toast(msg, ms = 4200) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toastEl.hidden = true; }, ms);
  }

  function addFiles(fileList) {
    if (demoMode) { $("#demo-mode").checked = false; setDemoMode(false); }
    const known = new Set(items.map(it => it.file.name + ":" + it.file.size));
    const fresh = [...fileList].filter(f => !known.has(f.name + ":" + f.size));
    for (const file of fresh) {
      const kind = kindOf(file);
      const it = { id: crypto.randomUUID(), file, kind, pages: kind === "img" ? 1 : kind === "pdf" ? undefined : null };
      items.push(it);
      if (kind === "pdf") countPdfPages(it);
    }
    const skipped = fileList.length - fresh.length;
    if (skipped) toast(`${plural(skipped, "file already added, skipped", "files already added, skipped")}.`);
    render();
  }

  /* Demo mode: simulates a large case file (thousands of documents) without uploading anything.
     Everything shown is labeled "simulated"; "Run" opens the built-in synthetic case. */
  const DEMO_FAKE = { docs: 7342, pages: 48215, bytes: 3.1 * 1024 ** 3 };
  const DEMO_SAMPLE = [
    ["pdf", "Hearing transcript — session 14.pdf", 212, 9.4e6],
    ["pdf", "Purchase order BC-2020-117.pdf", 64, 3.1e6],
    ["pdf", "Declaration of interests — scan.pdf", 6, 1.2e6],
    ["img", "Meeting notes — photo.jpg", 1, 2.4e6],
  ];
  let demoMode = false, demoShown = 0, demoTimer = 0;

  function setDemoMode(on) {
    demoMode = on;
    clearInterval(demoTimer);
    demoShown = 0;
    if (on) {
      items = [];
      const t0 = performance.now();
      demoTimer = setInterval(() => {                      // quick count-up, as if files were being read
        const k = Math.min(1, (performance.now() - t0) / 1400);
        demoShown = Math.round(DEMO_FAKE.docs * (1 - Math.pow(1 - k, 3)));
        render();
        if (k >= 1) clearInterval(demoTimer);
      }, 60);
    }
    render();
  }

  function renderDemo() {
    const frac = demoShown / DEMO_FAKE.docs;
    card.classList.add("has-files");
    filesEl.hidden = false;
    $(".dropzone__title").textContent = "Demo mode on";
    const rows = DEMO_SAMPLE.map(([kind, name, pages, bytes]) => {
      const li = document.createElement("li");
      li.className = "file file--sim";
      li.innerHTML = `<span class="file__kind file__kind--${kind}">${KINDS[kind].label}</span>
        <span class="file__name"></span><span class="file__meta">${pages} p. · ${fmtSize(bytes)}</span><span></span>`;
      $(".file__name", li).textContent = name;
      return li;
    });
    const more = document.createElement("li");
    more.className = "file file--sim";
    more.innerHTML = `<span class="file__kind file__kind--other">…</span>
      <span class="file__name">+ ${(Math.max(0, demoShown - DEMO_SAMPLE.length)).toLocaleString("en-US")} more documents</span>
      <span class="file__meta">simulated</span><span></span>`;
    listEl.replaceChildren(...rows, more);
    statsEl.innerHTML = [
      `<span><b>${demoShown.toLocaleString("en-US")}</b> docs</span>`,
      `<span><b>${Math.round(DEMO_FAKE.pages * frac).toLocaleString("en-US")}</b> pages</span>`,
      `<span><b>${fmtSize(DEMO_FAKE.bytes * frac)}</b></span>`,
      `<span>simulated</span>`,
    ].join("");
  }

  function removeFile(id) {
    items = items.filter(it => it.id !== id);
    render();
  }

  function render() {
    if (demoMode) return renderDemo();
    const has = items.length > 0;
    card.classList.toggle("has-files", has);
    filesEl.hidden = !has;
    $(".dropzone__title").textContent = has ? "Add more documents" : "Drop the case file";

    listEl.replaceChildren(...items.map(it => {
      const li = document.createElement("li");
      li.className = "file";
      const pages = it.pages === undefined ? "… p." : it.pages === null ? "" : it.pages === "?" ? "? p." : `${it.pages} p.`;
      li.innerHTML = `
        <span class="file__kind file__kind--${it.kind}">${KINDS[it.kind]?.label ?? "DOC"}</span>
        <span class="file__name"></span>
        <span class="file__meta">${[pages, fmtSize(it.file.size)].filter(Boolean).join(" · ")}</span>
        <button class="file__remove" type="button" aria-label="Remove">×</button>`;
      $(".file__name", li).textContent = it.file.name;
      $(".file__name", li).title = it.file.name;
      $(".file__remove", li).addEventListener("click", () => removeFile(it.id));
      return li;
    }));

    const count = k => items.filter(it => it.kind === k).length;
    const counting = items.some(it => it.pages === undefined);
    const pages = items.reduce((s, it) => s + (typeof it.pages === "number" ? it.pages : 0), 0);
    const size = items.reduce((s, it) => s + it.file.size, 0);
    statsEl.innerHTML = [
      `<span><b>${items.length}</b> ${items.length === 1 ? "doc" : "docs"}</span>`,
      `<span><b>${counting ? "…" : pages}</b> pages</span>`,
      count("img") && `<span><b>${count("img")}</b> images</span>`,
      count("audio") && `<span><b>${count("audio")}</b> audio</span>`,
      `<span><b>${fmtSize(size)}</b></span>`,
    ].filter(Boolean).join("");
  }

  // pdf.js is only loaded when the first PDF is dropped
  let pdfjsReady;
  function loadPdfJs() {
    pdfjsReady ??= new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = PDFJS + "pdf.min.js";
      s.onload = () => {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS + "pdf.worker.min.js";
        resolve(window.pdfjsLib);
      };
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return pdfjsReady;
  }

  async function countPdfPages(it) {
    try {
      const pdfjs = await loadPdfJs();
      const doc = await pdfjs.getDocument({ data: await it.file.arrayBuffer() }).promise;
      it.pages = doc.numPages;
      doc.destroy();
    } catch {
      it.pages = "?";
    }
    render();
  }

  input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });

  // accept drops anywhere on the page
  let dragDepth = 0;
  const hasFiles = e => [...(e.dataTransfer?.types ?? [])].includes("Files");
  window.addEventListener("dragenter", e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    if (dragDepth++ === 0) { dropzone.classList.add("is-over"); heroField?.excite(true); }
  });
  window.addEventListener("dragover", e => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("dragleave", e => {
    if (!hasFiles(e)) return;
    if (--dragDepth === 0) { dropzone.classList.remove("is-over"); heroField?.excite(false); }
  });
  window.addEventListener("drop", e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    dropzone.classList.remove("is-over");
    heroField?.excite(false);
    if (!$('[data-stage="drop"]').hidden) addFiles(e.dataTransfer.files);
  });

  // synthetic case file (generated server-side, CONTEXT.md §8): straight to the war room
  $("#demo").addEventListener("click", () => { location.href = "audit.html?intro"; });

  /* ================================================================
     3. Pipeline
     ================================================================ */

  const STEPS = [
    { id: "read",        label: "Reading",        detail: "OCR and vision, page and position kept" },
    { id: "reconstruct", label: "Linking",        detail: "People, companies, decisions, declarations" },
    { id: "check",       label: "Cross-checking", detail: "A statement against the other documents" },
    { id: "crosscheck",  label: "Spotting",       detail: "Roles, past ties, benefiting companies" },
    { id: "cascade",     label: "Tracing",        detail: "From the decision back to the original evidence" },
    { id: "ground",      label: "Weighing",       detail: "What depends on each link" },
    { id: "act",         label: "Next steps",     detail: "Points to review, with the pages" },
  ];
  const STATE_LABEL = { pending: "Pending", running: "Running", done: "Done", error: "Error" };

  const pipelineEl = $("#pipeline");
  const openTimeline = $("#open-timeline");

  function setStage(name) {
    document.querySelectorAll("[data-stage]").forEach(s => { s.hidden = s.dataset.stage !== name; });
  }

  function renderSteps() {
    pipelineEl.replaceChildren(...STEPS.map(s => {
      const li = document.createElement("li");
      li.dataset.step = s.id;
      li.innerHTML = `<span class="pipeline__dot"></span>
        <span><b>${s.label}</b><small>${s.detail}</small></span>
        <span class="pipeline__state">${STATE_LABEL.pending}</span>`;
      return li;
    }));
  }

  function setStep(id, state, detail) {
    const li = pipelineEl.querySelector(`[data-step="${id}"]`);
    if (!li) return;
    li.className = `is-${state}`;
    $(".pipeline__state", li).textContent = STATE_LABEL[state] ?? state;
    if (detail) $("small", li).textContent = detail;
  }

  function finish(dossierId) {
    openTimeline.classList.remove("is-disabled");
    openTimeline.removeAttribute("aria-disabled");
    openTimeline.href = `timeline.html?dossier=${encodeURIComponent(dossierId)}`;
  }

  /* Backend contract (casebreak/api/app.py):
       POST {API}/cases   multipart, field "files" → { case_id }
     then the app shows the war room (app.html?case=…) fed by GET /cases/{id}/status. */
  async function startPipeline() {
    if (!items.length) return;
    renderSteps();
    setStage("pipeline");
    $("#pipeline-mode").textContent = "";
    const form = new FormData();
    items.forEach(it => form.append("files", it.file, it.file.name));
    setStep(STEPS[0].id, "running", "Uploading the case file…");
    try {
      const res = await fetch(`${API_BASE}/cases`, { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.status);
      const { case_id } = await res.json();
      $("#dossier-id").textContent = case_id;
      setStep(STEPS[0].id, "done", "Case file received");
      location.href = `app.html?case=${encodeURIComponent(case_id)}`;
    } catch (e) {
      setStep(STEPS[0].id, "error", String(e.message ?? e));
      toast("Server unreachable: run `uv run casebreak serve`, then reload.");
    }
  }

  openTimeline.addEventListener("click", async e => {
    if (openTimeline.classList.contains("is-disabled")) return e.preventDefault();
    e.preventDefault();
    const res = await fetch(openTimeline.href, { method: "HEAD" }).catch(() => null);
    if (res?.ok) location.href = openTimeline.href;
    else toast("The timeline screen doesn’t exist yet.");
  });

  $("#demo-mode").addEventListener("change", e => setDemoMode(e.target.checked));
  $("#analyze").addEventListener("click", () => {
    if (demoMode) { location.href = "audit.html?intro"; return; }   // simulated case file → the McKinsey case
    startPipeline();
  });
  $("#reset").addEventListener("click", () => {
    items = [];
    $("#demo-mode").checked = false;
    setDemoMode(false);
    render();
    openTimeline.classList.add("is-disabled");
    openTimeline.setAttribute("aria-disabled", "true");
    setStage("drop");
  });

  /* ================================================================
     4. Scroll motion: Lenis smoothing, side-entry reveals,
        split headline, progress bar, parallax, scroll-linked ticker
     ================================================================ */

  // headline: wrap each word in a mask; the cut-out word slides in from the side
  const headline = $("[data-split]");
  if (headline) {
    let i = 0;
    const wrap = node => {
      const w = document.createElement("span");
      w.className = "w";
      w.style.setProperty("--i", i++);
      const inner = document.createElement("span");
      w.appendChild(inner);
      return [w, inner];
    };
    for (const node of [...headline.childNodes]) {
      if (node.nodeType === Node.TEXT_NODE) {
        const frag = document.createDocumentFragment();
        node.textContent.split(/(\s+)/).forEach(part => {
          if (!part) return;
          if (/^\s+$/.test(part)) return frag.append(" ");
          const [w, inner] = wrap();
          inner.textContent = part;
          frag.append(w);
        });
        node.replaceWith(frag);
      } else if (node.classList?.contains("cutout")) {
        const [w, inner] = wrap();
        w.classList.add("w--free");
        node.replaceWith(w);
        inner.appendChild(node);
      }
    }
    requestAnimationFrame(() => requestAnimationFrame(() => headline.classList.add("is-in")));
  }

  // reveals: once in view, elements slide in from their side
  const revealer = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add("is-in");
      revealer.unobserve(e.target);
    }
  }, { rootMargin: "0px 0px -12% 0px", threshold: 0.12 });
  document.querySelectorAll("[data-reveal]").forEach(el => revealer.observe(el));

  // smooth scroll (falls back to native scroll if the CDN is unreachable)
  let lenis = null;
  if (!REDUCED_MOTION && window.Lenis) {
    lenis = new window.Lenis({ duration: 1.15, easing: t => 1 - Math.pow(1 - t, 4) });
    const raf = t => { lenis.raf(t); requestAnimationFrame(raf); };
    requestAnimationFrame(raf);
    document.querySelectorAll('a[href^="#"]').forEach(a => a.addEventListener("click", e => {
      const target = a.hash.length > 1 && document.querySelector(a.hash);
      if (!target) return;
      e.preventDefault();
      lenis.scrollTo(target, { offset: -16 });
    }));
  }

  const progress = $("#progress");
  const parallax = [...document.querySelectorAll("[data-speed]")];
  const drifts = [...document.querySelectorAll("[data-drift]")];

  function onScroll() {
    const y = window.scrollY, vh = window.innerHeight;
    const max = document.documentElement.scrollHeight - vh;
    progress.style.transform = `scaleX(${max > 0 ? y / max : 0})`;
    if (REDUCED_MOTION) return;
    for (const el of parallax) el.style.setProperty("--py", `${y * parseFloat(el.dataset.speed)}px`);
    for (const el of drifts) {
      const r = el.parentElement.getBoundingClientRect();
      const t = (vh - r.top) / (vh + r.height);          // 0 → 1 while the section crosses the viewport
      el.style.setProperty("--dx", `${(t - 0.5) * parseFloat(el.dataset.drift) * 40}vw`);
    }
  }
  if (lenis) lenis.on("scroll", onScroll);
  else window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();
})();
