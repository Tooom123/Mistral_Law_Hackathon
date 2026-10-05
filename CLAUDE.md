# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

BREACH (code name CASEBREAK) turns a French criminal case file (PDF, scans, photos) into one graph of procedural acts placed in time × category, checks the possible nullities of each category **by code** against the law in force at the date of the act, and propagates what falls with a defective act.

- `ARCHITECTURE.md` wins on architecture; `CONTEXT.md` wins on law (catalogue §7, sources §12, rules §14).
- Code and docs are in English; UI strings, log lines and legal terms are in **French**.

## Commands

Python ≥ 3.11, managed with `uv`. No build step for the front.

```bash
uv sync
uv run casebreak serve [--port 8000] [--reload]   # API + front: / = landing, /app.html?demo = live demo
uv run casebreak demo                             # generate + analyse the synthetic demo dossier, print alerts
uv run casebreak bench --n 10 [--seed 1] [--no-baseline]   # NullityBench-FR recall/precision
uv run casebreak synth --out <dir> [--seed N]     # seed 0 = demo dossier, else random dossier + ground truth

uv run pytest                                     # whole suite
uv run pytest tests/test_units.py::test_name      # single test
uv run pytest -k normalize                        # by keyword
```

E2E browser test (`tests/e2e/browser_walkthrough.py`) is not part of pytest: it needs Playwright + Chromium, a server on port 8811 and a synth dossier with seed 7 — instructions are in the file header.

## Offline by default

Everything runs without keys. External engines switch on only when configured (`casebreak/config.py`, `.env` — see `.env.example`):
Mistral (OCR, extraction, judge, Leanstral), Jev/TypeSafe (judge tier 1), Judilibre (precedents), plus local Tesseract (OCR) and Lean 4 via `elan` (proofs), detected on `PATH`. `settings.engines()` reports what is active and is shown in the UI. Code paths must keep working when every engine is off.

`tests/conftest.py` forces this: it blanks all API keys, points `CASEBREAK_DATA` at a temp dir and freezes `CASEBREAK_TODAY=2026-10-04`. The session fixture `demo_case` generates and runs the demo dossier once; reuse it rather than re-running the pipeline per test. `CASEBREAK_PSEUDONYMIZE` (default on) pseudonymises names before any external call.

## Architecture

**Pipeline** (`casebreak/pipeline.py::run_case`) — stages mirror ARCHITECTURE §2 and also feed the live war-room status (in-memory `_STATUS`, persisted to `status.json`; the front polls `/cases/{id}/status`):
read (`ingest/ocr.py`: native text → Tesseract → Mistral OCR) → split + classify (`ingest/split.py`, one piece per PV) → extract (`graph/extract.py`, French time parsing in `facts/normalize_time.py`) → link (`graph/link.py`: `SUPPORTS`, `CONTRADICTS`, custody containers) → check (`nullities/engine.py`) → cascade (`propagate/cascade.py`) → save (`graph/store.py`: `graph.json`, `checks.json`, `graph.sqlite` under `data/cases/<id>/`).

**Contract:** `casebreak/schemas.py` (Node, Edge, Attr, Src, Check, Nullity, CaseGraph). Every attribute carries `Src{doc_id, page, quote}` and the quote is verified to be on that page (`text.py`); unverifiable attributes are not stored.

**Nullity catalogue ↔ checks** — the core extension point:
- One YAML per nullity in `casebreak/nullities/catalogue/` (`id`, `category`, `applies_to` subtypes, `needs`, `versions` with `valid_from`/`valid_to`, `check`, optional `grey_zone.judge_questions`, `weight`, `legal_todo`). Loaded once via `lru_cache` in `versions.py`.
- `versions[].check` names a function in `nullities/checks.py`. `CHECKS` is built from **every public callable in that module's globals** minus an explicit exclusion set — so new helpers must be `_`-prefixed (or added to the exclusion set), and any new import must be excluded too, or it becomes a "check".
- A check returns `Result | None` (None = not applicable) and contains no LLM call. Open-textured conditions return `grey=True`; `engine.py` then consults `judge/judge.py` (offline heuristics → Jev → Mistral Small → Mistral Large) and adjusts status/certainty. Values read by OCR downgrade `documented` → `inferred`.
- `engine.py` picks the law version by act date, or a forced `as_of` date (time-travel slider; slider stops come from `versions.reform_dates()`).
- New nullities should also be injectable by the synthetic generator (`synth/scenario.py`) so they appear in ground truth and `eval/bench.py` can score them.

**Downstream of checks:** `output/alerts.py` (alert cards), `output/report.py` (Markdown/PDF via reportlab), `tribunal/court.py` (défense / parquet / président debate per alert), `proofs/lean.py` (Lean 4 proof of the measurable arithmetic from `Result.proof`), `precedents/judilibre.py`, `deadlines/clock.py`, `privacy/pseudonymize.py`. `api/service.py` glues them for `api/app.py` (FastAPI; routes in ARCHITECTURE §9, plus tribunal/proof/precedents/deadline/benchmark), which also mounts `frontend/` as static files.

**Front** (`frontend/`, vanilla JS, no bundler): `index.html` + `app.js` = landing/upload; `app.html` + `app/*.js` ES modules = the app (`main.js` routing, `warroom.js`, `timeline.js` swim lanes, `acard.js` alert card, `report.js`, `bench.js`; `api.js` wraps fetch). Visual style guides live in `front_mistral-main/*.md`.

## Rules (CONTEXT §14 and README guardrails)

- **The LLM extracts, Python decides.** No legal judgement inside prompts; conditions live in `checks.py`.
- **Never invent law**: no article, decision, date or deadline unless it is in CONTEXT §7/§12 or retrieved from an official API. Unknown → `TODO(legal)` (catalogue `legal_todo`), surfaced in the UI. Precedents only from Judilibre, never generated.
- **Every finding has a source** (doc, page, verified quote); no source → not displayed.
- **No percentages**: three certainty levels only — `documented` / `inferred` / `needs_reading`. UI says « nullité possible », never « nul »; the tool never decides grief or nullity.
- **No made-up numbers**: metrics come from `casebreak bench`; synthetic ≠ real accuracy.
- **Synthetic data only** in the repo, prompts and logs; `data/cases/` stays out of git.
