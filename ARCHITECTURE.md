# CASEBREAK — Architecture

> How the whole system works, end to end: what goes in, what comes out, how every piece connects, and who builds what.
> Companion to `CONTEXT.md` (product, legal background, pitch). If they disagree, **this file wins on architecture, `CONTEXT.md` wins on law.**
> Last update: 4 Oct 2026.

---

## 0. One-paragraph summary

CASEBREAK has **two knowledge banks** and **one judge**.
The **Fact Bank** holds neutral, sourced facts extracted from the case file ("custody started 11:05, p. 42").
The **Law Bank** holds the legal provisions (CPP articles, versions by date) **compiled into atomic requirements** ("rights must be notified immediately after placement").
The system checks the case **in both directions**: every requirement looks for the facts it needs (**rule → facts**: catches missing and late things), and every fact looks for the requirements it might touch (**fact → rules**: catches what we didn't anticipate).
Deterministic requirements are decided by **code**; open-textured ones by an **LLM judge** that must justify each legal element with quotes. Every finding carries its sources, the article version in force at that date, the acts that depend on it (cascade), precedents, and a certainty level we have **measured**, not asked the model for.

```text
                ┌──────────────────────────┐        ┌───────────────────────────┐
  case file ──► │        FACT BANK         │        │         LAW BANK          │ ◄── Légifrance API
 (PDF, scans,   │ acts · facts · actors    │        │ provisions (versioned)    │     (CPP articles)
  photos)       │ every fact → page + quote│        │ → requirements (atomic)   │ ◄── Judilibre API
                └────────────┬─────────────┘        │ → precedents per req.     │     (case law)
                             │                      └─────────────┬─────────────┘
                             │     ┌──────────────────────────┐   │
                             └────►│        MATCHER           │◄──┘
                                   │ A. rule → facts (code)   │
                                   │ B. fact → rules (search) │
                                   └────────────┬─────────────┘
                                                ▼
                                   ┌──────────────────────────┐
                                   │          JUDGE           │
                                   │ deterministic checks     │
                                   │ + LLM element-by-element │
                                   │ + self-consistency       │
                                   └────────────┬─────────────┘
                                                ▼
                                   ┌──────────────────────────┐
                                   │ FINDINGS + CASCADE + UI  │──► lawyer accepts / rejects
                                   └────────────┬─────────────┘            │
                                                └────── feedback ◄─────────┘
                                                        (Nullity Wiki grows)
```

---

## 1. Review of the team's proposal ("facts bank × law bank × confidence")

The proposal: (1) a bank of neutral facts, (2) a bank of laws/clauses; for each fact, search the law bank for related clauses, then run the pair through an LLM to get a confidence that the fact complies.

**What's right — we keep it:**
- Separating **facts** (what happened) from **law** (what should happen) is exactly how lawyers reason (facts → rule → application). It makes the system explainable and testable.
- Fact → law retrieval is a real, benchmarked task: COLIEE 2026 "statute law retrieval and entailment" reports up to ~91 % accuracy with retrieval + LLM reasoning ([NOWJ@COLIEE 2026](https://arxiv.org/pdf/2607.16603)). So the direction works — on clean, short queries.

**What breaks if we do only that — and how we fix it:**

| Problem | Why it matters here | Fix |
|---|---|---|
| **Defects are often absences.** "No mention that rights were notified", "no signed consent". There is no fact to iterate from. | Missing mentions are among the most common procedural defects. A fact-driven loop is blind to them. | Add the **reverse pass: rule → facts.** Each requirement declares which facts must exist; missing = finding. |
| **Defects are relations between facts.** "Notification 3 h after placement", "search started 21:40". One fact alone is lawful. | Retrieval per fact never sees the pair. | Requirements are **predicates over several facts of the same act** (and across acts). |
| **LLM "confidence levels" are not trustworthy.** Verbalized confidence is badly calibrated (expected calibration error > 0.37 in a 2026 study; [Dunning-Kruger in LLMs](https://arxiv.org/pdf/2603.09985)). | A jury from Stanford/Cleary will ask "what does 87 % mean?" | Certainty = **how** the finding was produced (code vs LLM, extraction quality, agreement across runs), **calibrated on our benchmark**. No raw model percentage in the UI. |
| **Cost.** Thousands of facts × dozens of clauses = tens of thousands of LLM calls. | 8-hour hackathon, live demo. | Facts are **typed and categorised**; we filter by category/framework/date first, retrieve second, and only call the LLM when code can't decide. |
| **Law changes over time.** | The 2024 custody reform and the 2026 nullity-deadline reform change the answer depending on the date. | Law Bank is **versioned**: each requirement has `valid_from/valid_to`; matcher uses the version in force at the act's date. |
| **Clauses are long and mix several obligations.** | An LLM judging "article 63-1 vs this fact" mixes 6 obligations into 1 verdict. | **Compile** each article into **atomic requirements** once, offline, validated by our legal teammate. |

**Verdict:** keep the two banks and the fact → law search; add the requirement compiler, the reverse pass, and measured certainty. That is the architecture below.

> "Jev": we're not sure which model/tool this refers to. Below it's the **Judge** stage; plug any Mistral model in it (see §9).

---

## 2. Input

### 2.1 What the user gives us

A **dossier**: a folder or ZIP of PDFs (native or scanned), images (JPG/PNG/HEIC), optionally audio. Real files are messy: one PDF can contain many PVs, pages can be out of order, times can be handwritten.

### 2.2 What we turn it into (the case manifest)

```yaml
# data/cases/<case_id>/manifest.yaml  (auto-generated, editable)
case_id: affaire-mathurins
jurisdiction: FR
framework_hint: preliminaire        # flagrance | preliminaire | instruction | unknown
key_dates:
  mise_en_examen: 2026-03-14        # anchor for deadlines (if present)
documents:
  - id: D001
    file: raw/scelle_photos.zip
    kind: images
  - id: D002
    file: raw/tome1.pdf
    pages: 412
    kind: pdf_scanned
```

The UI shows this manifest after upload so the user sees what we understood ("412 pages, 37 documents detected, 9 photos").

---

## 3. Stage 1 — Ingest (read everything, lose nothing)

```text
raw files ─► split ─► OCR / vision ─► page records ─► document segmentation ─► typed documents
```

- **OCR:** Mistral OCR / Document AI. Keep **page number, text, layout, bounding boxes** for every block. Mistral's Document AI supports schema-constrained **annotations** on the whole document and on each bbox ([docs](https://docs.mistral.ai/capabilities/document_ai/annotations)) → we can OCR and pre-extract in one pass.
- **Images:** vision model describes the photo and reads visible text (seal labels, screens, timestamps); read **EXIF** (time, device). EXIF is corroboration only, never a finding on its own.
- **Segmentation:** a 400-page PDF contains many PVs. Detect boundaries (headers like "PROCÈS-VERBAL", "N° PV", signatures) → one `Document` per PV.
- **Classification:** each document gets a type: `PV_PLACEMENT_GAV`, `PV_NOTIFICATION_DROITS`, `PV_AUDITION`, `PV_PERQUISITION`, `PV_SAISIE`, `ORDONNANCE`, `RAPPORT_EXPERTISE`, `PHOTO`, `OTHER`.

**Output:** `pages.jsonl`, `documents.jsonl`. Everything later points back here via `Source(doc_id, page, quote, bbox)`.

**Rule:** nothing downstream may contain a fact whose `quote` is not literally present in `pages.jsonl` (checked by code — this kills invented facts).

---

## 4. Stage 2 — Fact Bank (what happened)

### 4.1 Extraction

Per document (not per page — context matters), schema-constrained extraction with a **fact-kind vocabulary per document type**:

| Document type | Fact kinds extracted |
|---|---|
| `PV_PLACEMENT_GAV` | `custody_start`, `custody_reason`, `offence`, `officer`, `framework` |
| `PV_NOTIFICATION_DROITS` | `rights_notified_at`, `rights_list`, `language`, `interpreter_present`, `signature_or_refusal` |
| `PV_AUDITION` | `hearing_start`, `hearing_end`, `lawyer_present`, `waiver_mentioned`, `prosecutor_authorization` |
| `PV_PERQUISITION` | `search_start`, `search_end`, `place`, `occupant_present`, `witnesses`, `consent_signed`, `judge_authorization` |
| `PV_SAISIE` | `items_seized`, `seal_numbers` |
| `RAPPORT_EXPERTISE` | `analysed_seals`, `conclusions` |
| `PHOTO` | `depicted`, `visible_text`, `exif_time` |

Each extracted fact:

```json
{
  "id": "F-0193",
  "act_id": "A-012",
  "kind": "rights_notified_at",
  "value": "2026-03-12T14:20:00+01:00",
  "raw": "à quatorze heures vingt",
  "source": {"doc_id": "D002-PV17", "page": 43, "quote": "à quatorze heures vingt, nous notifions…", "bbox": [0.12, 0.33, 0.88, 0.37]},
  "extraction": "explicit",
  "ocr_confidence": 0.94
}
```

`extraction ∈ {explicit, inferred, unreadable}`. **Never guess a time**: unreadable stays unreadable and becomes a `needs_reading` finding if a rule needs it.

### 4.2 Normalisation (code, not LLM)
- French time/date parser: "14h20", "14 H 20", "quatorze heures vingt", "le 12 courant", midnight crossings, Europe/Paris timezone.
- Actor resolution: "OPJ Martin", "le brigadier MARTIN", "Martin J." → one actor (string rules + LLM tie-break, logged).

### 4.3 Acts and the graph

Facts are grouped into **Acts** (one custody, one search, one hearing…). Acts are the nodes of the **Case Graph**:

- **Axis 1 — time:** `start`, `end` from facts.
- **Axis 2 — category:** `GARDE_A_VUE`, `PERQUISITION_SAISIE`, `AUDITION`, `INTERPELLATION`, `EXPERTISE`, `INSTRUCTION`, `INTERCEPTIONS`, `GEOLOCALISATION`.
- **Edges:**
  - `PRECEDES` (time order),
  - `SUPPORTS` (necessary-support dependency, for the cascade): `structural` (seizure ← search; lab report cites seal n° ← seizure), `cited_in_text` ("vu le PV n°…"), `llm_inferred` (dashed, lower certainty),
  - `CONTRADICTS` (two facts of the same kind and act with different values),
  - `SOURCED_FROM` (fact → page).

**Storage:** SQLite (facts, acts, edges) + NetworkX in memory for traversal. **No vectors in the graph.**

### 4.4 Case Wiki (readable view, Karpathy-style)

Generated from the graph, one Markdown page per act, actor and category, every line linked to its page. Useful for the lawyer to read and for agents to navigate. **Regenerated, never hand-edited; never read by the rules engine.**

---

## 5. Stage 3 — Law Bank (what should happen)

### 5.1 Layers

```text
PROVISIONS   verbatim article text, per version (valid_from / valid_to), from Légifrance
     │  compiled once (LLM draft → legal teammate validates)
     ▼
REQUIREMENTS atomic obligations, typed, with the facts they need
     │  linked
     ▼
PRECEDENTS   Cour de cassation decisions (Judilibre) — accepted AND rejected, per requirement
     │  summarised by the LLM, curated by humans
     ▼
NULLITY WIKI one Markdown page per requirement/defect type: rule, elements, pitfalls, precedents
             (the compounding knowledge base — grows with every reviewed case)
```

**Sources:**
- **Légifrance API** (DILA, via the PISTE portal, free after registration, JSON, consolidated texts with versions) → provisions. [data.gouv.fr](https://www.data.gouv.fr/dataservices/legifrance/)
- **Judilibre API** (Cour de cassation, same PISTE account, `chamber=cr` for criminal) → precedents. [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/api-judilibre/)
- **Fallback if PISTE is slow:** articles pasted by hand into `law/provisions/*.md` by our legal teammate (that's also the validation step), and a pre-fetched precedent set.

### 5.2 The requirement — the core object of the system

```yaml
# law/requirements/GAV-04.yaml
id: GAV-04
category: GARDE_A_VUE
title: Notification immédiate des droits
provision: CPP art. 63-1
provision_versions: [LEGIARTI…]           # filled from Légifrance
valid_from: 2011-06-01                    # TODO(legal): confirm
valid_to: null
applies_when:
  act_type: custody
  framework: [flagrance, preliminaire, instruction]
needs_facts: [custody_start, rights_notified_at]
test:
  type: deterministic                     # deterministic | judgment
  check: rights_notified_at - custody_start <= threshold
  threshold: TODO(legal)                  # "immédiatement": case law tolerates operational justification
  if_missing: needs_reading               # rights_notified_at absent → finding
exceptions:
  - fact: operational_justification       # e.g. intoxicated person → delay may be justified
    effect: downgrade_to_judgment
rights_at_stake: [droit à l'information, droits de la défense]
grief: lawyer_decides                     # never computed
precedents: []                            # filled from Judilibre
confidence: H                             # H / M / L — see CONTEXT.md §7
validated_by: null
```

Two test types:
- **`deterministic`** — times, durations, presence/absence, counts, hours of day, required authorization present. Decided by Python. Examples: GAV-02 (24 h), PRQ-01 (6:00–21:00), GAV-08 (no hearing without lawyer, post-2024 version).
- **`judgment`** — open texture: "only means to achieve the objectives" (art. 62-2), "operational justification", "exceptional circumstances". Decided by the **LLM judge**, element by element, with quotes, flagged `inferred`.

### 5.3 Requirement compiler (the ambitious part)

An offline tool: `casebreak law compile --article "CPP 63-1" --version 2024-07-01`
1. Fetch the article text (version in force at a date) from Légifrance.
2. LLM proposes atomic requirements in the YAML schema, each with the **exact sentence** of the article it comes from.
3. Code checks every quoted sentence exists in the article text.
4. Our legal teammate validates / edits → `validated_by`.

This turns "a bank of laws" into "a bank of checkable obligations", and it scales: new article → new requirements without new code (for deterministic tests that reuse existing predicates).

**Moonshot (P2):** compile 2–3 deterministic requirements to **Lean 4** and let **Leanstral** (Mistral's open-source prover) produce a machine-checked proof that the timeline violates them. Pitch line: "for the simple rules, we don't estimate — we prove."

---

## 6. Stage 4 — Matcher (connecting the two banks)

### Pass A — rule → facts (completeness, P0)

```python
for act in graph.acts:
    for req in law.requirements_applicable(act.category, act.type, act.framework, at=act.start):
        facts = graph.facts_for(act, req.needs_facts)   # exact query, no vectors
        candidates.append((req, act, facts))            # missing facts are kept as gaps
```

Catches **absences** and **relations** (§1). Cheap: no LLM.

### Pass B — fact → rules (discovery, P1 — the team's original idea)

For facts **not consumed** by any Pass A requirement, or flagged unusual (outlier durations, night-time acts, contradictions):

1. **Filter** requirements by category/framework/date (structured).
2. **Retrieve** with hybrid search over requirement texts + Nullity Wiki pages: BM25 + Mistral Embed + article cross-references.
3. **Rerank** top-k with the LLM ("which of these could apply to this fact? quote why").
4. Send surviving pairs to the Judge as `judgment` checks, flagged `discovered`.

This is where unanticipated defects show up — and where new requirements are proposed for the Law Bank (feedback loop §8).

### Pass C — contradictions (P0 for times)

Same `kind` + same act + different values from different sources → `CONTRADICTS` edge. If either value fails a requirement → finding; otherwise "inconsistency to clarify". Uses the **text index** (embeddings on page passages) to find every other place a fact is mentioned.

---

## 7. Stage 5 — Judge (the "Jev" step)

### 7.1 Deterministic checks
Python predicates. Output `violated | satisfied | missing_fact`. Certainty `documented` if all facts are `explicit` with good OCR, else `needs_reading`.

### 7.2 LLM judge for `judgment` requirements

Input: requirement (text + elements), the article sentence, the relevant facts **with quotes**, neighbouring facts of the same act, the version date.
Output (JSON schema, temperature 0):

```json
{
  "requirement_id": "GAV-01",
  "elements": [
    {"element": "objectif légal mentionné", "status": "missing", "evidence": []},
    {"element": "unique moyen", "status": "unclear", "evidence": [{"doc_id":"D002-PV12","page":31,"quote":"…"}]}
  ],
  "verdict": "potential_defect | no_defect | insufficient_information",
  "explanation_fr": "…",
  "counter_arguments_fr": ["…"]          // what the prosecution would answer
}
```

Guards:
- Every `evidence.quote` must exist verbatim in `pages.jsonl` (code check) — otherwise the judgement is discarded.
- **Self-consistency:** run 3× (or 2 different Mistral models); agreement is part of certainty.
- The judge **never** decides grief, never says "nul".
- It must produce **counter-arguments** — that's what makes it credible to lawyers (and it's what the opposing side will say).

### 7.3 Certainty (replaces "confidence %")

| Certainty | Produced when |
|---|---|
| `documented` | deterministic test, explicit facts, OCR OK |
| `inferred` | LLM judge agreed 3/3, all quotes verified, or `llm_inferred` edge involved |
| `needs_reading` | missing/unreadable fact, judge disagreement, conflicting sources |

On the benchmark we compute **precision per certainty level** (e.g. "documented: 0.95 precision, inferred: 0.7"). Those **measured** numbers are what we may show — labelled "on our synthetic set".

---

## 8. Stage 6 — Findings, cascade, precedents, deadlines

```json
{
  "id": "FND-007",
  "requirement_id": "GAV-04",
  "category": "GARDE_A_VUE",
  "kind": "rule_violation",                      // rule_violation | missing_mention | contradiction | discovered
  "statement_fr": "Droits notifiés à 14h20 ; placement en garde à vue à 11h05 (écart : 3h15). Aucune justification relevée dans le PV.",
  "certainty": "documented",
  "sources": [{"doc_id":"D002-PV16","page":42,"quote":"…11h05…"}, {"doc_id":"D002-PV17","page":43,"quote":"…quatorze heures vingt…"}],
  "law": {"provision": "CPP art. 63-1", "version_in_force_at": "2026-03-12", "text_excerpt": "…"},
  "precedents": [{"ecli":"ECLI:FR:CCASS:…","outcome":"annulation|rejet","why":"…"}],   // only if retrieved from Judilibre
  "cascade": {"acts": ["A-013","A-014","A-021"], "basis": ["structural","cited_in_text","llm_inferred"]},
  "counter_arguments_fr": ["Retard justifié par l'état d'ébriété ?"],
  "next_steps_fr": ["Vérifier une éventuelle justification opérationnelle", "Qualifier le grief"],
  "deadline": {"anchor": "mise_en_examen", "rule": "DLN-01", "status": "to_verify"}
}
```

- **Cascade:** BFS on `SUPPORTS` from the defective act; output is the list of acts to name in the request (art. 174 practice, see `CONTEXT.md`). UI: "Simulate impact".
- **Ranking:** certainty first, then cascade size, then category weight (set by legal teammate). No made-up "severity score".
- **Deadlines:** computed from the anchor with the version in force; always "to verify".

### Feedback loop (what makes it compound)
Lawyer clicks **Accept / Reject / Not relevant** with an optional note →
- stored as labels (future eval set),
- Pass B discoveries accepted twice become **draft requirements** for the compiler,
- the **Nullity Wiki** page of that requirement gets the case pattern (anonymised).
Pitch: *"every case the firm reviews makes the next review better."*

---

## 9. Model map (Mistral)

> Verify model IDs in the console when credits arrive.

| Stage | Model | Why |
|---|---|---|
| OCR + pre-annotation | Mistral OCR / Document AI (annotations with JSON schema) | text + bbox + structured fields in one call |
| Photos | Pixtral / multimodal Mistral | seals, screens, visible times |
| Fact extraction | Mistral Large 3 (or Medium) | long PVs, French administrative style, JSON schema |
| Rerank (Pass B) | Mistral Small | cheap, many calls |
| Judge | Mistral Large 3 + Magistral (reasoning) as second opinion | two models = self-consistency signal |
| Embeddings | Mistral Embed | page passages, requirement texts, precedents |
| Requirement compiler | Mistral Large 3 | drafts YAML from article text |
| Moonshot proofs | Leanstral | Lean 4 proofs of deterministic violations |
| Audio (stretch) | Voxtral | recorded hearings vs written PV |

**On-prem story:** open-weight models where available → deployable inside a firm. Check per model before saying it.

---

## 10. Output (what the user sees)

1. **Upload → live "war room":** counters fill in (pages read, documents typed, acts, facts, requirements checked).
2. **Timeline × category (hero screen):** swim lanes per category, acts as blocks on a time axis, red markers on findings, zig-zag on contradictions, dependency arrows on hover.
3. **Finding card:** the four questions — *what* (statement), *where* (page viewer, highlighted bbox), *why it matters* (article text in force that day + cascade + precedents + counter-arguments), *what next* (steps, deadline).
4. **Simulate impact:** dependent acts grey out in stop-motion; "6 acts potentially affected".
5. **Report (Markdown → PDF):** list of "moyens de nullité à examiner", each with sources and acts to name; appendix with timeline and method/limits.
6. **Case Wiki** browser (secondary).

UI language: French. Labels: "défaut de procédure potentiel", "à instruire", never "nul".

---

## 11. Evaluation (built in, not bolted on)

**Synthetic dossier generator** (`casebreak synth`):
1. Generate a coherent case skeleton (people, places, 20–60 acts across categories, valid timeline).
2. Render PVs in French administrative style from templates (ideally Hector/LSE-provided) → 300–1,000 pages.
3. Degrade: scan noise, rotation, stamps, handwritten times; photos with EXIF.
4. **Inject** K defects drawn from requirements (ground truth: requirement, act, page), **decoys** (lawful-looking: justified delay, express waiver, special regime), and cross-document contradictions.
5. Emit `ground_truth.json`.

**Metrics** (`casebreak eval`): recall/precision per requirement and per certainty level, page-pin accuracy, cascade accuracy, cost and time per 1,000 pages. **Baseline:** same dossier to a strong LLM alone ("find procedural defects"). We report the delta.

**Golden demo dossier:** one synthetic case, frozen at 16:30, with results cached so the demo cannot fail on network.

---

## 12. Repository layout

```text
casebreak/
  ingest/        ocr.py · images.py · segment.py · classify.py
  facts/         schemas.py · extract.py · normalize_time.py · actors.py · graph.py · wiki.py
  law/
    provisions/  CPP-63-1.md …            (verbatim text + version + URL)
    requirements/GAV-04.yaml …
    precedents/  GAV-04.jsonl …
    compiler.py · legifrance.py · judilibre.py
  match/         rule_to_facts.py · fact_to_rules.py · contradictions.py · index.py (embeddings)
  judge/         deterministic.py · llm_judge.py · certainty.py
  findings/      build.py · cascade.py · deadlines.py · report.py
  synth/         skeleton.py · render.py · degrade.py · inject.py
  eval/          run.py · metrics.py · baseline.py
  api/           main.py (FastAPI)
web/             front (timeline, finding card, page viewer, cascade)
data/            cases/<case_id>/…   (synthetic only — real data never committed)
tests/           fixtures per requirement
```

### API (FastAPI)

| Method | Path | Returns |
|---|---|---|
| POST | `/cases` (multipart) | `case_id`, manifest |
| GET | `/cases/{id}/status` | stage progress (for the war room) |
| GET | `/cases/{id}/timeline` | acts by category with times |
| GET | `/cases/{id}/findings` | ranked findings |
| GET | `/cases/{id}/findings/{fid}` | full finding card |
| POST | `/cases/{id}/simulate` `{act_id}` | cascade set |
| GET | `/cases/{id}/pages/{doc}/{page}` | page image + bboxes |
| POST | `/cases/{id}/findings/{fid}/review` | accept/reject (feedback loop) |
| GET | `/cases/{id}/report` | Markdown/PDF |

### Interfaces between people (freeze by 11:00)
`schemas.py` (Source, Fact, Act, Edge, Requirement, Finding) is the contract. Front works on a **mock `findings.json`** from minute one; back replaces it with real output.

---

## 13. Build plan (who does what)

| Owner | Builds | Ready-by |
|---|---|---|
| **Legal (LSE)** | categories, 10–12 requirement YAMLs with verbatim article text, decoy list, Nullity Wiki pages, Q&A prep | YAMLs v1 by 12:00 |
| **Eng 1 – Ingest & Facts** | OCR, segmentation, classification, extraction, time parser, graph | text+facts on demo dossier by 13:00 |
| **Eng 2 – Law & Judge** | requirement loader, Pass A, deterministic checks, LLM judge, certainty, Légifrance/Judilibre clients | first findings by 13:30 |
| **Eng 3 – Synth & Eval** | generator, injection, ground truth, metrics, baseline; Pass B if time | demo dossier v1 by 12:00, metrics by 16:00 |
| **Eng 4 – Front & Demo** | timeline swim lanes, finding card, page viewer, cascade animation, war room, backup video | mock UI by 12:30, real data by 15:30 |

**Priorities:** P0 = Stage 1–2, Pass A, deterministic judge, cascade, contradictions on times, timeline + finding card, synthetic dossier + metrics. P1 = LLM judge, Pass B, precedents, deadlines, report, feedback buttons. P2 = requirement compiler UI, Leanstral proofs, Voxtral, prosecutor mode.

**Code freeze 17:00. Submit before 18:00.**

---

## 14. Failure modes we design against

| Failure | Guard |
|---|---|
| Invented fact / quote | quote-must-exist check against OCR text |
| Invented law / case | provisions only from Légifrance or hand-pasted verbatim; precedents only from Judilibre |
| Wrong version of the law | `valid_from/valid_to`, version shown on each finding |
| OCR misreads a time → false alarm | `needs_reading` certainty, page shown with bbox |
| LLM overconfidence | no verbalized %; certainty from method + agreement; precision per certainty measured |
| Missing defect (false negative) | Pass A completeness + Pass B discovery; UI lists pages we couldn't read |
| Demo breaks live | cached run on frozen dossier + recorded video |
| Real data leak | synthetic only in git; anonymised samples kept outside the repo |

---

## 15. Sources

- COLIEE 2026, statute retrieval & entailment: [NOWJ@COLIEE 2026](https://arxiv.org/pdf/2607.16603)
- LLM verbalized confidence miscalibration: [Dunning-Kruger effect in LLMs (2026)](https://arxiv.org/pdf/2603.09985), [Wired for Overconfidence](https://www.alphaxiv.org/abs/2604.01457)
- LLMs skipping the formal step ("scope laundering"): [Know Your Limits](https://arxiv.org/pdf/2606.16118)
- Mistral Document AI annotations (JSON schema, bbox): [docs.mistral.ai](https://docs.mistral.ai/capabilities/document_ai/annotations)
- Légifrance API (PISTE, consolidated texts, versions): [data.gouv.fr](https://www.data.gouv.fr/dataservices/legifrance/)
- Judilibre API (PISTE, criminal chamber `cr`): [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/api-judilibre/), [pyjudilibre](https://pyjudilibre.readthedocs.io/en/latest/)
- Karpathy "LLM Wiki" pattern: [overview](https://www.analyticsvidhya.com/blog/2026/04/llm-wiki-by-andrej-karpathy/)
- Leanstral: [Mistral news](https://mistral.ai/news/leanstral-1-5/)
- Legal rules, reforms and their verification status: see `CONTEXT.md` §7 and §12.
