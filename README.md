# BREACH (code name CASEBREAK)

> Find the procedural flaw before the deadline does — with the page number.

A French criminal case file becomes **one graph**: every act is a node placed in **time × category**. The
conditions of the law are checked **on the graph by a generic rules engine** (law in force at the date of the act),
each possible nullity comes with its **page and verbatim quote**, and the **domino effect** shows what falls with a
defective act. Architecture: `ARCHITECTURE.md` · law: `CONTEXT.md`.

## Run

```bash
uv sync
uv run casebreak serve          # http://localhost:8000 → landing ; http://localhost:8000/app.html?demo → live demo
uv run casebreak demo           # CLI: generate + analyse the synthetic "Mathurins" case
uv run casebreak doctor         # which engines work with the keys in .env (one tiny call per Mistral path)
uv run casebreak bench --n 10   # NullityBench-FR: recall / precision vs ground truth
uv run pytest                   # 40 tests, always offline (keys are blanked in tests/conftest.py)
```

Without any key everything runs offline. With `MISTRAL_API_KEY` in `.env` (copy `.env.example`), the Mistral paths
switch on — see below. Optional local tools: **Tesseract** (OCR of scans/photos without a key) and **Lean 4** (`elan`,
kernel-checked proofs).

## Rules are data

There is **no Python function per rule**. Each rule is one YAML file in `casebreak/nullities/catalogue/`, evaluated by
one generic engine (`casebreak/nullities/dsl.py`):

```yaml
id: GAV-02
applies_to: [garde_a_vue]
versions:
  - label: art. 63 CPP
    params: {initial_hours: 24, extension_hours: 24}
    let:
      start: t('custody_start')
      end: t('custody_end')
      ext: has('extension_authorized')
      limit: params['initial_hours'] * 60 + (params['extension_hours'] * 60 if ext else 0)
      total: minutes(start, end)
    outcomes:                       # ordered, the first `when` that holds wins
      - when: start is None
        status: needs_reading
        say: Custody start time unreadable or missing.
        cite: [custody_start]
      - when: total > limit and not ext
        status: possible_nullity
        say: "Custody of {name}: {dhm(start)} → {dhm(end)}, i.e. {dur(total)}. No extension authorisation in the file."
        cite: [custody_start, custody_end]
        proof: {kind: duration_gt, start: iso(start), end: iso(end), limit_minutes: limit}
```

- **Attribute paths are generic over the graph**: `notified_at` (this act), `custody.custody_start` (its custody),
  `rights_notification.lawyer_requested` (the act of that subtype for the same person),
  `case:geolocation_authorization.date` (anywhere in the file), `custody.@start` (a node field).
- Expressions are a **sandboxed** subset of Python (comparisons, arithmetic, `x if c else y`, whitelisted functions:
  `minutes`, `clock`, `hhmm`, `has`, `missing`, `acts`, …). Every expression is compiled when the catalogue loads: a
  broken rule fails at startup, not during an analysis.
- Law-as-of-date: each rule has `versions` with `valid_from` / `valid_to`; the time-travel slider re-runs the engine.
- Rules are indexed by act subtype, so cost grows with *acts × rules that apply to them*, not with the whole catalogue.
- **Adding a rule = adding a YAML file.** If it reads a new attribute, describe it in
  `casebreak/nullities/attributes.yaml` (`tests/test_rules_as_data.py` fails otherwise).

## Rule-driven extraction

1. Offline readers (French patterns per document type, `graph/extract.py`) build the first graph.
2. The engine runs once and **traces every attribute a rule needed and did not find** (absent, unreadable).
3. For those gaps only, Mistral reads the act's own pages with the attribute's description from
   `attributes.yaml` (`graph/fill.py`). An answer is kept only if its **quote is found on one of the act's pages**;
   times are parsed from the quote by our French parser, never taken from the model's value.
4. Filled attributes are `inferred`: an alert relying on them is never `documented`. The engine runs again.

A new rule that reads a new attribute therefore gets it extracted on real files without new code. The offline French
patterns remain the no-key path and are tuned to the synthetic generator — say so (see *Limits*).

## What uses Mistral (with a key) — and what was verified

| Step | Model (configurable in `.env`) | Fallback without key |
|---|---|---|
| OCR of scans / photos | `mistral-ocr-latest`; if `/ocr` is unavailable, a vision chat model transcribes the page (`mistral_vision`) | Tesseract, else page "unreadable" |
| Classification of unknown documents | `MISTRAL_FAST_MODEL` | patterns on the "Objet" line |
| Extraction of unknown documents + rule-driven gap filling | `MISTRAL_EXTRACT_MODEL` | patterns |
| Dependency links for orphan acts (dashed) | `MISTRAL_JUDGE_MODEL` | structural + "vu le PV n°" links only |
| Judge on grey zones (facts only, quotes verified) | Jev if `TYPESAFE_API_KEY`, else fast → judge model | keyword heuristics |
| Tribunal (defence / prosecution / presiding) | `MISTRAL_JUDGE_MODEL` | deterministic agents over the graph |
| "LLM alone" baseline in the benchmark | `MISTRAL_JUDGE_MODEL` | not run (says so) |
| Lean proofs | Leanstral if `MISTRAL_LEAN_MODEL` (Labs model, must be enabled by a workspace admin) | `by decide`, checked by Lean |

- **Model fallback**: a model refused by the workspace (403/404, or a 0 requests/minute quota) is skipped and the next
  one of `MISTRAL_FALLBACK_MODELS` is used; `/api/engines` and `casebreak doctor` show which model actually answered.
- Answers are cached on disk (`data/cache/llm_*.json`): re-running the demo, moving the time slider or exporting the
  report does not call the API again.
- Pseudonymisation (names, addresses, dates of birth, phones) before every **text** call; act ids sent to the model
  are opaque. Page **images** sent to OCR cannot be pseudonymised.
- Verified on 4 Oct 2026 with the team key: chat, JSON extraction, judge, tribunal and vision OCR answer through the
  fallback chain (`ministral-14b-latest`). On that workspace `mistral-large`, `mistral-medium`, `mistral-small` and the
  `/ocr` endpoint are refused or have a 0 quota, and Leanstral needs Labs enabled — activate a plan in the console to
  use them; nothing else to change.

## Interface (`app.html`)

- **War room** while the file is read: live counters, stages and feed, all from `/cases/{id}/status`.
- **Case graph** (centre): 3D graph of the file — acts (colour = category), people, seals, alerts; links = depends on,
  contradiction, involves, part of custody. Hover = neighbourhood, click = details (act checklist + attributes with
  quotes; people/seals → their acts; alert → alert card). Slow rotation until touched. Built with
  [3d-force-graph](https://github.com/vasturiano/3d-force-graph) (CDN).
- **Timeline**: one lane per category, time on X (long gaps compressed), every act labelled with its time, custody
  bars with start → end, dependencies shown on hover.
- **Alert card**: what · where (page image, quote highlighted) · why (article, version in force, acts affected) · what
  next; tribunal, Lean proof, judge answers, Judilibre precedents (key only), accept / dismiss.
- Domino effect (graph or timeline), time-travel slider, defence / prosecution mode, pseudonymisation, report MD/PDF,
  benchmark page. White theme; Tailwind (CDN, preflight off) for the new components.

## Guardrails (CONTEXT §14)

- Every attribute has a page and a quote that is checked to be on that page.
- No invented article, decision or deadline: unknowns are `TODO(legal)` in the catalogue and shown in the UI.
- No confidence percentage: three certainty levels (documented / inferred / needs reading). The benchmark page shows
  measured recall/precision on synthetic files only.
- The tool never decides prejudice or nullity. Synthetic data only in the repo (`data/` is git-ignored).

## Limits (to say honestly)

- The offline extractors are French patterns written alongside the synthetic generator: the benchmark (100 % recall
  and precision on 10 synthetic files) measures the pipeline end to end, not generalisation to real files. On real
  files, rule-driven Mistral extraction is what closes the gap — not yet measured on real (anonymised) files.
- The legal content of the catalogue is not validated by a lawyer (`validated_by: null` everywhere, `TODO(legal)` items).
- The tribunal, the judge and the baseline ran on `ministral-14b` with the current key; quality with larger models
  is untested here.
- Jev (TypeSafe) payload is unverified (no access); Judilibre needs a PISTE key.
