# BREACH (code name CASEBREAK)

> Find the procedural flaw before the deadline does — with the page number.

A French criminal case file becomes **one graph**: every act is a node placed in **time × category**, each
category carries its **checklist of possible nullities**, the conditions of the law are checked **by code** on
the graph (law in force at the date of the act), and the **domino effect** shows what falls with a defective act.
Architecture: `ARCHITECTURE.md` · law: `CONTEXT.md`.

## Run (no API key needed)

```bash
uv sync
uv run casebreak serve          # http://localhost:8000 → landing ; app.html?demo → live demo
uv run casebreak demo           # CLI: generate + analyse the synthetic Mathurins case
uv run casebreak bench --n 10   # NullityBench-FR: recall / precision vs ground truth
uv run pytest
```

Optional local tools, used when present: **Tesseract** (OCR of scans/photos) and **Lean 4** (`elan`, kernel-checked
proofs). Mistral, Jev and Judilibre switch on only when their keys are in `.env` (see `.env.example`).

## What is built

| Level | Feature | Where |
|---|---|---|
| L0 | Synthetic dossiers: French PVs, scans with handwritten times, photos with EXIF, injected nullities, decoys, ground truth | `casebreak/synth/` |
| L0 | Read (native / Tesseract / Mistral OCR) → split per PV → classify → extract acts with `{value, page, quote}` | `casebreak/ingest/`, `casebreak/graph/extract.py` |
| L0 | Graph: custody containers, `SUPPORTS` (structure, seals, "vu le PV n°" citations), `CONTRADICTS`, SQLite + NetworkX | `casebreak/graph/` |
| L0 | Catalogue of CONTEXT §7 (+ graph checks), one YAML per nullity, versions by date | `casebreak/nullities/` |
| L1 | Domino effect along `SUPPORTS`, "simulate impact" | `casebreak/propagate/` |
| L1 | Contradictions between pieces (custody start, EXIF vs PV) · law-as-of-date | `graph/link.py`, `nullities/versions.py` |
| L1 | Evaluation per nullity and per certainty level, LLM-alone baseline (key only) | `casebreak/eval/` |
| L2 | Judge for grey zones (offline → Jev → Mistral), verified quotes, counter-arguments | `casebreak/judge/` |
| L2 | Judilibre precedents (key only, never generated) · deadline clock (both regimes, "to verify") | `precedents/`, `deadlines/` |
| L2 | Accept / reject · report Markdown / PDF | `output/`, API |
| L3 | Tribunal (defence / prosecution / presiding judge) · Lean 4 proofs · time-travel slider · pseudonymisation · prosecution mode · NullityBench-FR export | `tribunal/`, `proofs/`, `privacy/`, front |
| — | FastAPI (ARCHITECTURE §9) + front (war room, timeline, alert card, domino, report, benchmark) | `casebreak/api/`, `frontend/` |

## Guardrails (CONTEXT §14)

- Every attribute has a page and a quote that is checked to be on that page.
- No invented article, decision or deadline: unknowns are `TODO(legal)` in the catalogue and shown in the UI.
- No percentage: three certainty levels (documented / inferred / needs reading).
- The interface is in English; the synthetic case files are French police reports, and quotes stay verbatim.
- The tool never decides grief or nullity. Synthetic data only in the repo.
- Benchmark numbers come from `casebreak bench`. The generator and extractors were written by the same team:
  the score measures the chain end to end, not generalisation to real files.
