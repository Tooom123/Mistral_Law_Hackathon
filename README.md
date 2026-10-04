# BREACH

> **Don't summarize the case. Audit it.**
> BREACH reads thousands of documents, rebuilds who did what and when, and tells the lawyer *exactly which lines to read* to find a conflict of interest — with the page, the span, the chain of reasoning and the past cases that look like it.

Conflicts of interest are never written in one document. A consultant's name sits in a staffing annex; the company she also works for sits in an engagement letter three folders away; the box she ticked "No" sits in a declaration filed a month later; the decision that benefited that company sits in a memo nobody connected to any of the above. Finding it means cross-referencing everything against everything, on a timeline. That is what BREACH does.

```
            ┌──────────────┐    ┌─────────────────┐    ┌──────────────────────┐    ┌───────────────────┐
 PDFs ───▶ │  Read         │──▶│  Facts graph     │──▶│  Conflict detectors   │──▶│  Precedent engine  │──▶  Timeline · flags · memo
 scans      │  Mistral OCR  │    │  people, firms,  │    │  cross-document rules │    │  SQLite FTS5 BM25  │
 photos     │  + vision     │    │  roles, periods, │    │  6 patterns, each     │    │  + pattern overlap │
            │  page + span  │    │  declarations,   │    │  with evidence spans, │    │  + mistral-embed   │
            └──────────────┘    │  signatures …    │    │  chain, window,       │    │  46 past cases     │
                                 └─────────────────┘    │  certainty level      │    └───────────────────┘
                                                         └──────────────────────┘           │
                                                                    │                        ▼
                                                                    └──────────▶  Mistral reviewer note
                                                                                  (quotes verified on the page)
```

---

## The demo: consulting firms & the State — McKinsey

The French Senate's 2022 inquiry into consulting firms showed how hard it is to answer a simple question: *did the people who advised the State also work for the companies affected by that advice?* The committee collected more than 7,000 documents and obtained only a handful of declarations of interests.

The demo case file reconstructs that situation around the vaccination-campaign logistics mission: framework agreement, specifications, purchase order, staffing annex, declarations of interests, an engagement letter for a vaccine manufacturer, time reports, deliverables, a decision memo, a company-registry extract, a hearing under oath and the ministry's answer to the committee. *(Individuals, companies other than the firm, figures and relationships are fictional — every page says so in the viewer. The public chronology is real.)*

**No document states a conflict.** BREACH finds eight, in about 20 ms, and clears ten other checks:

| | Flag | Pattern | Cross-referenced documents |
|---|---|---|---|
| F1 | Partner advised the Ministry and Vaxellis SA at the same time, and reviewed the deliverable recommending Vaxellis | Dual mandate | engagement letter · staffing annex · specifications · time report · deliverable · ministry answer |
| F2 | Same for a senior associate, who also authored that deliverable | Dual mandate | idem |
| F3 | Her declaration of interests ticks "No" to *current health-sector engagement* — five weeks into the Vaxellis engagement | False declaration | declaration · engagement letter |
| F4 | The deputy director who signed the €3.96 M order left the firm 14 months earlier; no recusal on record | Revolving door | appointment declaration · purchase order · decision memo · ministry answer |
| F5 | Under oath: "every consultant filed a declaration" — 3 declarations for 9 consultants | Statement contradicted | hearing · staffing annex · ministry answer |
| F6 | Under oath: "no team member worked for a vaccine manufacturer" — two did, with the days recorded | Statement contradicted | hearing · engagement letter · time report |
| F7 | 6 of 9 consultants never filed the declaration art. 7.3 requires | Missing declaration | framework agreement · staffing annex · ministry answer |
| F8 | A consultant declared a spouse at Froidis Group; Froidis's 100 % subsidiary was selected on his deliverable | Relative's interest *(inferred via ownership)* | declaration · registry extract · decision memo |

…and **cleared**: a consultant whose former employer is not an affected company and whose employment ended six years earlier; seven team members with no private engagement in the sector; two declarations consistent with the rest of the file. Showing what was checked and cleared is half of an audit.

Two counter-tests in `tests/test_coi.py` prove the engine reasons rather than recites: tick "Yes" on the declaration and F3 disappears; move the signatory's departure to 2016 and F4 becomes a cleared check.

---

## The interface (`/audit.html`)

**Timeline first.** Lawyers think in chronology, so the case opens on it — drawn as a paper collage, the same visual language as the case graph of the procedural engine (`frontend/app/flow.js`, reused as is):

- **One cut-out tile per document**, in time order, **one row per category** (procurement · private clients · declarations · decisions · scrutiny).
- **Select a flag** → its documents are joined by a pen line in reading order, framed in yellow, and the line to read first becomes the **taped red tile with a sticker** (`F3 · false decl.`).
- **Click a tile → the document opens** beside the timeline, scrolled to the exact lines, highlighted, with margin notes saying which flag cites them and why. ← / → walks the file in time order.
- *All documents* shows the pieces no flag cites too — the negative space of the audit.

**Where to look.** Flags ranked by severity and certainty, each with:
- the **chain** (person → company → public order) as a diagram whose edges open their source document;
- **every line to read**, with its role in the reasoning (*declared*, *contradiction*, *time recorded*, *no recusal*…) — one click to the highlighted span;
- **aggravating elements** (authored the recommendation, no consent under art. 7.4, time reports confirm the overlap);
- a **Mistral reviewer note**, whose quotes are checked against the page before display;
- **comparable past cases** from the precedent database, with a similarity score and *why* they match (shared patterns, shared signals);
- the **framework** (contract clauses, Code de la commande publique, Directive 2014/24/EU, loi 2013-907, Code pénal…) and **next steps** as a checklist;
- one-click **review memo** in Markdown.

**Precedent database.** Searchable, filterable by pattern and provenance, with the retrieval engine in use.

---

## Architecture

### 1 · Read — every fact keeps its page and its span
`casebreak/coi/extract.py` turns pages into typed facts — assignments (person, engagement, role, allocation, period), engagements (client, sector), stakeholder lists, purchase orders and signatures, declarations (each answer and its checkbox), prior employment, authorship, recommendations, decisions, ownership, relatives' interests, sworn statements, administration attestations. Each fact carries a `Src(doc, page, start, end, quote)`: the character span on the page, which the viewer highlights and the tests verify (`text[start:end] == quote` for all 48 cross-references).

Scans and photos go through the shared ingestion layer (`casebreak/ingest/ocr.py`): **Mistral OCR** (`mistral-ocr-latest`) with a vision-model fallback and Tesseract offline, page positions preserved.

### 2 · Detect — cross-document conflict rules
`casebreak/coi/rules.py` + `rules.yaml`. The code finds facts; the YAML says what they mean (title, pattern, severity, legal framing, next steps, retrieval query). Six detectors:

| Rule | Pattern | Logic |
|---|---|---|
| COI-01 | dual_role | person staffed on a public order **and** on a private engagement for a company listed as affected, overlapping or within the contractual 12-month look-back; upgraded by time reports, authorship of a deliverable recommending that company, absence of consent |
| COI-02 | undeclared_interest | declaration answers "No" while an engagement in the file contradicts it at the declaration date |
| COI-03 | missing_declaration | contractual duty to declare × staffing annex × declarations held (and the administration's own count) |
| COI-04 | revolving_door | signatory's prior employment at the awarded firm within 3 years of signing, recusal record absent |
| COI-05 | family_tie | declared relative's employer → ownership chain → company selected on that person's work |
| COI-06 | false_statement | sworn statements parsed into claims, tested against the flags above |

Each flag ships with a **certainty level** — *documented* (every link is on a page), *inferred* (one link is derived, e.g. through an ownership chain), *needs reading* — never a fake percentage. Each flag also ships with its **time window**, a **chain graph** and the evidence **roles**, which is what drives the timeline and the viewer.

### 3 · Compare — the precedent engine
`casebreak/coi/precedents.py` · `data/precedents.json` → **SQLite** (`data/cache/precedents.sqlite`), rebuilt automatically when the JSON changes:

- an **FTS5** full-text index (Porter stemming) over title, facts, outcome, signals and lesson;
- a **pattern table** over a 10-pattern conflict taxonomy (dual mandate, false declaration, missing declaration, revolving door, relative's interest, tie to the beneficiary, preparatory role, statement contradicted, confidential information, appearance of bias);
- **hybrid ranking**: `0.4 · cosine(mistral-embed) + 0.3 · BM25 + 0.3 · Jaccard(patterns)`; without a key, `0.55 · BM25 + 0.45 · Jaccard`. Embeddings are cached on disk.
- every hit explains itself: shared patterns, shared signals, matched terms. Each flag is anchored on at least one public-record case.

46 entries across 9 jurisdictions: *Bolkiah v KPMG*, *eVigilo* (CJEU), *Fabricom* (CJEU), *Applicam* (Conseil d'État), *Porter v Magill*, *Caperton*, the US Trustee settlement with McKinsey RTS, the House Oversight report on the FDA and opioid manufacturers, the PwC Australia affair, the French Senate report, Sarbanes-Oxley s.201, Directive 2014/24/EU art. 24, loi 2013-907, Code pénal 432-12/13, ordonnance 58-1100, loi 2019-828 — plus 30 simulated training scenarios (labelled as such) covering health, defence, energy, transport, local government, EU funds, universities and sport, including *negative* cases where the tie is cleared, so the engine learns what does **not** count.

### 4 · Explain — Mistral, on a leash
With `MISTRAL_API_KEY`, each flag receives a reviewer note written by Mistral from the evidence and the precedents only. Quotes in the note are checked against the evidence; the UI says whether they were verified. Answers are cached by content hash; a workspace that refuses a model falls back through `MISTRAL_FALLBACK_MODELS` automatically. The rules, not the model, decide what is flagged.

### 5 · Serve
FastAPI (`casebreak/api/app.py`):

```
GET  /api/coi/cases                         case files available
GET  /api/coi/cases/{case}?llm=true         full audit: documents + spans, periods, flags, cleared checks, precedents
GET  /api/coi/cases/{case}/flags/{id}/memo  review memo (Markdown)
GET  /api/coi/precedents?q=&pattern=&provenance=&k=
GET  /api/coi/precedents/{id}
```

The front end is dependency-free vanilla JS (ES modules, SVG). It also runs from a static snapshot (`frontend/audit/data/`) when no server is up — useful on a projector with bad Wi-Fi.

---

## Run

```bash
uv sync
uv run casebreak serve                    # http://localhost:8000 → drop the case-files/mckinsey folder on the landing
                                          # http://localhost:8000/audit.html?intro  (straight to the audit)
uv run casebreak coi                      # the audit in the terminal: flags, pages, comparable cases
uv run casebreak coi --memo F3            # one review memo
uv run casebreak coi --pdf case-files/mckinsey   # the case file as 17 PDFs, ready to drag and drop
uv run casebreak coi --llm --export frontend/audit/data/mckinsey.json   # refresh the snapshot with Mistral notes
uv run casebreak doctor                   # which Mistral paths answer with the keys in .env
uv run pytest                             # 55 tests, fully offline
```

Copy `.env.example` to `.env` and set `MISTRAL_API_KEY` to switch on OCR, the Mistral reader, `mistral-embed` retrieval and reviewer notes. Everything else runs offline.

---

## Guardrails

- **No source, no flag.** Every flag points to spans that are verified to be on their page.
- **"Potential conflict of interest — to review."** BREACH never qualifies; the lawyer does.
- **No made-up confidence.** Three certainty levels, explained.
- **No invented relationship.** Derived links (ownership chains) are labelled *inferred*.
- **Negative space shown.** Every cleared check is listed with its source.
- **Provenance everywhere.** Public-record precedents and simulated scenarios are badged differently; synthetic pages carry a footer notice.

---

## Also in the repo: procedural-defect engine

BREACH started as CASEBREAK, an engine that finds procedural defects in criminal case files (`/app.html`): a generic **rules-as-data** DSL (YAML rules evaluated on a case graph, law-as-of-date versions, sandboxed expressions), rule-driven Mistral gap-filling, a 3D case graph, a domino effect showing which acts fall with a defective one, a defence/prosecution/presiding tribunal, Lean-checked deadline proofs and a synthetic benchmark (`casebreak bench`). The demo there is the 2018 Beckham speeding case (notice of intended prosecution received on day 15). Same philosophy — page-level evidence, the lawyer decides — applied to procedure instead of conflicts. See `ARCHITECTURE.md`.

---

## Roadmap

- **Scale-out ingestion**: stream thousands of PDFs through Mistral OCR in batches; incremental re-audit when a document is added.
- **Entity resolution** across spellings, initials and corporate groups (registry APIs: INSEE Sirene, OpenCorporates, GLEIF).
- **Detectors as data**, like the procedural engine: new conflict patterns as YAML over the facts graph.
- **Live sources**: HATVP declarations, BOAMP / TED award notices, Judilibre and CJEU case law feeding the precedent base.
- **Collaborative review**: accept / dismiss per flag, reviewer comments, exportable audit trail.

---

Built at the Mistral AI legal hackathon · powered by Mistral OCR, Mistral chat models and `mistral-embed`.
