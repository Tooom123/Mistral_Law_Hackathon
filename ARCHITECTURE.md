# CASEBREAK — Architecture

> **One case file = one graph.** Everything in the file becomes a node, placed in **time** and in a **category**. Each node carries the **possible nullities of its category**. We check them on the graph, show the page, and propagate what falls with it.
> Companion to `CONTEXT.md` (product, law, pitch). This file wins on architecture, `CONTEXT.md` wins on law.
> Last update: 4 Oct 2026.

---

## 0. The idea in one picture

```text
 time ─────────────────────────────────────────────────────────────────────────────────►
                12/03 10:50      11:05      14:20        15:00            13/03 16:00     14/03
 INTERPELLATION  ●arrest
 GARDE_A_VUE                     ●placement─●rights─────────────────────────●end
                                    │          ⚠ GAV-04 "3h15 after placement" (p. 42–43)
 AUDITION                           ├──────────●hearing 1 (no lawyer?) ⚠ GAV-08
 PERQUISITION_SAISIE                │                      ●search──●seizure (seal S1)
 EXPERTISE                          │                                  └──────●phone analysis (S1)
 INSTRUCTION                        └───────────────────────────────────────────────────●mise en examen
                                    ──── SUPPORTS (what depends on what)   ⚠ possible nullity on the node
```

- **Rows** = categories (swim lanes). **X axis** = time. **Nodes** = acts and moments of the file. **Edges** = time order, dependency, contradiction.
- Each node **knows which nullities are possible for its category** (a checklist attached to the category).
- A defect on one node **propagates** along dependency edges: that's the "what falls with it" view.

---

## 1. Mental model

### 1.1 Nodes

| Node type | Example | Key attributes |
|---|---|---|
| `ACT` | custody placement, rights notification, hearing, search, seizure, lab analysis, mise en examen | `category`, `start`, `end`, `framework` (flagrance / préliminaire / instruction), attributes (lawyer present, consent signed, interpreter…) |
| `PIECE` | a procès-verbal, a photo, an order | `doc_id`, `pages`, `type` |
| `PERSON` | suspect, OPJ, lawyer, interpreter, witness | `role`, aliases |
| `ITEM` | seal S1 (phone), seized jewels | `seal_number` |

**Every attribute keeps its source**: `{value, doc_id, page, quote}`. No attribute without a page.

### 1.2 Edges

| Edge | Meaning | Where it comes from |
|---|---|---|
| `PRECEDES` | time order | timestamps |
| `PART_OF` | rights notification is part of custody #1 | same custody number / same PV chain |
| `DOCUMENTED_IN` | act → the PV(s) that record it | segmentation |
| `SUPPORTS` | act B depends on act A (seizure ← search; lab report on S1 ← seizure of S1; hearing ← custody) | structural rules, "vu le PV n°…", seal numbers; LLM only as last resort (dashed) |
| `INVOLVES` | act ↔ person / item | extraction |
| `CONTRADICTS` | two pieces state different values for the same attribute of the same act | comparison |

### 1.3 Categories (the swim lanes) and their possible nullities

The **nullity catalogue** is not a knowledge base: it is **the list of what to look for, per category**, written once with our legal teammate, attached to the graph.

| Category | Possible nullities checked (MVP in bold) |
|---|---|
| `GARDE_A_VUE` | **duration > 24 h without extension (GAV-02)** · **rights not notified immediately (GAV-04/05)** · prosecutor not informed (GAV-06) · **hearing without lawyer (GAV-08, law-as-of-date)** · doctor requested not seen (GAV-09) · **no interpreter (GAV-10)** · missing PV mentions (GAV-12) |
| `PERQUISITION_SAISIE` | **home search before 6:00 / after 21:00 (PRQ-01)** · occupant/witnesses absent (PRQ-02) · **no express consent in préliminaire (PRQ-03)** · items not sealed (PRQ-04) |
| `AUDITION` | (inherits GAV-08) · hearing outside custody times |
| `INTERPELLATION` | time inconsistent with custody start |
| `EXPERTISE` | analysed seal not traceable to a seizure |
| `INSTRUCTION` | anchor for deadlines (4 / 6 months, loi 2026-651) |
| `INTERCEPTIONS`, `GEOLOCALISATION` | authorization / duration (later) |

Each catalogue entry = article (CPP), the **conditions** to check, the **attributes** it needs, the **versions by date**, and a status `validated_by`. Details and confidence levels: `CONTEXT.md` §7.

---

## 2. Input → graph (construction pipeline)

```text
 DOSSIER (PDF · scans · photos)
   │
 ① READ        OCR (Mistral OCR / Document AI) + vision for photos · keep page + position
   │
 ② SPLIT       cut the PDF into pieces (each PV = one PIECE node): headers "PROCÈS-VERBAL", n°, signatures
   │
 ③ CLASSIFY    piece type → category (PV placement GAV → GARDE_A_VUE, PV perquisition → PERQUISITION_SAISIE…)
   │
 ④ EXTRACT     per piece, JSON schema per type: ACT nodes + attributes {value, page, quote} + PERSON / ITEM
   │           French time parser in code ("onze heures cinq", "14 H 20", midnight crossing)
   │
 ⑤ LINK        merge the same act seen in several pieces (PART_OF), order in time (PRECEDES),
   │           dependencies (SUPPORTS: seal numbers, "vu le PV n°", custody → hearings), contradictions
   │
 ⑥ ATTACH      for each ACT node: attach the checklist of its category (possible nullities)
   ▼
 CASE GRAPH  (SQLite tables nodes/edges + NetworkX in memory)
```

**Hard rule:** an attribute is stored only if its `quote` is literally present in the OCR text of that page (checked by code). This alone removes invented facts.

Embeddings (Mistral Embed) are used **only to find text**: "every page that mentions the arrest time", to feed ④ and the contradiction check. The graph itself is not vectorised.

---

## 3. Detection — "is this a possible nullity?"

The most credible approach in front of lawyers and Stanford academics: **the conditions of the law, checked on the graph, with the page in hand.** Similarity to past cases is a support, never the decision.

For each `ACT` node, for each possible nullity of its category:

```text
           ┌─────────────────────────────────────────────────────────────┐
 node ───► │ 1. Which version of the law applies?  (date of the act)     │
           │ 2. Are the needed attributes present?  no → "missing        │
           │    mention" (absences are defects too)                      │
           │ 3. Condition type?                                          │
           │    ├─ measurable (time, duration, hour, present/absent)     │
           │    │     → checked by CODE                     → documented │
           │    └─ open-textured ("immediately", "only means",           │
           │          "exceptional circumstances", justification)        │
           │          → JUDGE: Jev typed questions → Mistral if unsure    │
           │            quotes mandatory                      → inferred  │
           │ 4. Graph checks: contradictions between pieces, expected    │
           │    node missing (custody with no rights-notification PV),   │
           │    impossible order (hearing before placement)              │
           └─────────────────────────────────────────────────────────────┘
                                   │
                                   ▼  possible nullity on the node (⚠)
```

### 3.1 Why this is the credible choice

| Approach | Problem in front of this jury |
|---|---|
| LLM reads the file and "finds nullities" | Unverifiable, hallucinates law, can't explain thresholds; LLMs report formal conclusions without doing the reasoning ("scope laundering", [Know Your Limits](https://arxiv.org/pdf/2606.16118)) |
| Similarity to past cases only | "This looks like case X" is not a legal argument; no page, no condition |
| **Conditions of the law on the graph + judge for grey zones** | Every alert = article + condition + attribute + page. Reproducible, testable, measurable. Grey zones are labelled as such |

### 3.2 The judge (grey zones only)

- **Tier 1 — Jev** (TypeSafe AI, typed questions with probabilities): e.g. `objective_stated: boolean`, `delay_justified: yes/no/not_documented`. Fast and cheap. If access fails or French is poor → **Mistral Small** with JSON enums.
- **Tier 2 — Mistral Large** when tier 1 is unsure or when the alert will be displayed: explanation in French, quotes (verified to exist), and **counter-arguments** (what the prosecution will answer).
- The judge **never** decides grief or nullity.

### 3.3 Certainty (no fake percentages)

| Level | When |
|---|---|
| `documented` | measurable condition checked by code on explicit attributes with clean OCR |
| `inferred` | judge decision above a threshold **calibrated on our benchmark**, all quotes verified |
| `needs_reading` | unreadable/missing attribute, contradicting pieces, or judge unsure — the lawyer must read the page |

---

## 4. Propagation — what falls with it

- From a node with a possible nullity, walk `SUPPORTS` edges → **acts potentially affected** (art. 174 CPP logic: the annulled act and the acts it is the necessary support of; the request must name them — see `CONTEXT.md`).
- **Simulate impact:** remove the node, recompute, grey out dependents, count them.
- Edges by origin: `structural` / `cited_in_text` (solid) vs `llm_inferred` (dashed, lower certainty).
- Ranking of alerts: certainty → number of acts affected → category weight (set by the legal teammate).

---

## 5. Output

**Graph view (hero screen):** the swim-lane timeline of §0. Click a node → its pieces, attributes with pages, and its checklist (✓ satisfied / ⚠ possible nullity / ? needs reading).

**Alert card — the four questions:**
1. **What** — "Droits notifiés à 14h20 ; placement à 11h05 (3h15). Aucune justification relevée."
2. **Where** — page viewer with the line highlighted (p. 42, p. 43).
3. **Why it matters** — article, version in force on 12/03/2026 · acts potentially affected (cascade) · precedents (Judilibre, if retrieved) · counter-arguments.
4. **What next** — check a justification, qualify the grief, deadline (to verify).

**Report:** list of "moyens de nullité à examiner", each with pages and acts to name. Export Markdown/PDF.

UI language: French. Words: "nullité possible", "à instruire". Never "nul".

---

## 6. Data model

```python
class Src(BaseModel):     doc_id: str; page: int; quote: str
class Attr(BaseModel):    value: str | bool | None; src: Src | None; status: Literal["explicit", "inferred", "unreadable", "missing"]

class Node(BaseModel):
    id: str
    type: Literal["ACT", "PIECE", "PERSON", "ITEM"]
    category: str | None              # swim lane (ACT, PIECE)
    subtype: str                      # placement_gav, rights_notification, hearing, search, seizure…
    start: datetime | None; end: datetime | None
    framework: Literal["flagrance", "preliminaire", "instruction", "unknown"]
    attrs: dict[str, Attr]            # lawyer_present, consent_signed, interpreter_present, seal_number…
    checks: list["Check"]             # attached from the category checklist

class Edge(BaseModel):
    src: str; dst: str
    kind: Literal["PRECEDES", "PART_OF", "DOCUMENTED_IN", "SUPPORTS", "INVOLVES", "CONTRADICTS"]
    origin: Literal["structural", "cited_in_text", "llm_inferred"]
    src_ref: Src | None

class Check(BaseModel):              # one possible nullity on one node
    nullity_id: str                   # GAV-04
    law_version: str                  # "CPP 63-1, version in force 12/03/2026"
    status: Literal["satisfied", "possible_nullity", "needs_reading", "not_applicable"]
    certainty: Literal["documented", "inferred", "needs_reading"]
    statement_fr: str
    sources: list[Src]
    judge: dict | None                # tier, answers, probabilities, counter-arguments
    affected: list[str]               # node ids via SUPPORTS
```

Catalogue entry (config, one file per nullity):

```yaml
id: GAV-04
category: GARDE_A_VUE
applies_to: [rights_notification]
article: CPP 63-1
needs: [custody_start, rights_notified_at]
versions:
  - valid_from: 2011-06-01        # TODO(legal)
    condition: {type: measurable, check: delay_minutes(custody_start, rights_notified_at) <= tolerance}
    grey_zone: {if_attr: operational_justification, judge_questions: [delay_justified]}
validated_by: null
```

---

## 7. Models

| Step | Model |
|---|---|
| OCR, layout, structured annotations | Mistral OCR / Document AI |
| Photos (seals, screens, visible times) | Pixtral / multimodal Mistral |
| Extraction per piece | Mistral Large 3 (JSON schema) |
| Judge tier 1 | Jev (TypeSafe AI) → fallback Mistral Small |
| Judge tier 2, explanations, counter-arguments | Mistral Large 3 (+ Magistral as second opinion) |
| Text search inside the file | Mistral Embed |
| Moonshot proofs | Leanstral |
| Audio (stretch) | Voxtral |

Verify model IDs in the console when credits arrive. On-prem story: open-weight Mistral models where available.

---

## 8. Evaluation

- **Synthetic dossiers** with a known graph: generate a coherent case, render PVs (300–1,000 pages, scans, handwritten times, photos), **inject** nullities on chosen nodes, add **decoys** (lawful-looking: justified delay, express waiver, special regime, search started 20:50 and continuing after 21:00) and contradictions. Ground truth = `(nullity_id, node, page)`.
- **Metrics:** recall / precision per nullity and per certainty level · page accuracy · cascade accuracy · time and cost per 1,000 pages.
- **Baseline:** the same dossier given to an LLM alone ("find the procedural nullities"). We report the difference.
- Say it honestly: "on our synthetic set of N dossiers".

---

## 9. API and repo

| Method | Path | Returns |
|---|---|---|
| POST | `/cases` | upload → `case_id` |
| GET | `/cases/{id}/status` | pipeline progress (war-room counters) |
| GET | `/cases/{id}/graph` | nodes + edges (swim lanes) |
| GET | `/cases/{id}/alerts` | ranked possible nullities |
| GET | `/cases/{id}/alerts/{aid}` | alert card |
| POST | `/cases/{id}/simulate` `{node_id}` | affected nodes |
| GET | `/cases/{id}/pages/{doc}/{page}` | page image + highlights |
| POST | `/cases/{id}/alerts/{aid}/review` | lawyer accepts / rejects |
| GET | `/cases/{id}/report` | Markdown / PDF |

```text
casebreak/
  ingest/    ocr · split · classify
  graph/     extract · normalize_time · link · store (SQLite + NetworkX)
  nullities/ catalogue/*.yaml · checks.py (measurable conditions) · versions.py
  judge/     jev.py · mistral.py · certainty.py
  propagate/ cascade.py
  output/    alerts.py · report.py
  synth/ eval/ api/
web/         swim-lane graph · alert card · page viewer
```

Freeze `schemas.py` (Node, Edge, Check) by 11:00; the front works on a mock `graph.json` from minute one.

---

## 10. Ambition ladder

| Level | Works | Demo moment | By |
|---|---|---|---|
| **L0** | dossier → graph (GAV + search) → 6 measurable checks → alert card with page | "3 h 15 — page 43" | 13:30 |
| **L1** | cascade + simulate impact · contradictions · law-as-of-date · metrics | dependents grey out; same file dated 2023 vs 2025 → different alerts | 15:30 |
| **L2** | judge on grey zones · Judilibre precedents · deadline clock · review buttons | "annulled in these decisions, rejected in those (no grief)" | 17:00 |
| **L3** | one moonshot below | wow + roadmap | pitch |

### Moonshots (pick one for the pitch)

1. **Adversarial tribunal on each alert** — defense agent argues, prosecution agent objects (justification? waiver? special regime? no grief? purge?), presiding agent rules with quotes. Only alerts that survive reach the lawyer; decoys should fall. Inspired by [multi-agent deliberation in law](https://arxiv.org/pdf/2606.30906), used adversarially.
2. **Proved, not estimated** — measurable conditions compiled to Lean 4 and proved by **Leanstral** (Mistral's open-source prover) on the extracted times. Proves the arithmetic, not the extraction nor the law — say so.
3. **Time-travel slider** — move "law applicable as of" and watch alerts appear/disappear (custody reform 1 July 2024; nullity deadline 6 → 4 months, loi 2026-651).
4. **Law watch** — Légifrance changes on tracked articles → new version of the catalogue entry, proposed for validation.
5. **Empirical annulment rates** — from Judilibre criminal-chamber decisions on the same provision: retrieved counts, never generated; state corpus and date.
6. **Multimodal corroboration** — photo EXIF vs PV time; seal labels read by vision vs seizure PV; Voxtral on recorded hearings vs written PV; re-reading handwritten times on `needs_reading` nodes.
7. **Privacy shield** — pseudonymise names/addresses before any external call; on-prem deployment answers investigation secrecy.
8. **Prosecutor mode** — same graph as a pre-trial regularity audit (equality of arms).
9. **NullityBench-FR** — release the generator, dossiers, decoys and scorer as an open benchmark.

### Never overclaim
Synthetic ≠ real accuracy · the tool never decides grief or nullity · counts are retrieved, not predicted · proofs cover arithmetic on extracted facts.

---

## 11. Failure modes and guards

| Failure | Guard |
|---|---|
| Invented attribute | quote must exist on the page |
| Invented law / case | catalogue from verbatim articles; precedents only from Judilibre |
| Wrong law version | versions by date, shown on the alert |
| OCR misreads a time | `needs_reading` + page shown |
| Overconfident judge | no raw %; thresholds calibrated on the benchmark |
| Missed defect | checklist runs on every node of the category, including "expected node missing" |
| Demo breaks | frozen dossier, cached run, recorded video |
| Real data leak | synthetic only in git |

---

## 12. Code status

Branch `feat/casebreak`: L0 → L3 built, offline by default (see `README.md`). Schemas follow §6 (`casebreak/schemas.py`);
`casebreak/facts/normalize_time.py` is reused by the extractors. Every `TODO(legal)` in `casebreak/nullities/catalogue/`
must be cleared by our legal teammate before the demo.

---

## 13. Sources

- LLMs skipping formal reasoning: [Know Your Limits](https://arxiv.org/pdf/2606.16118)
- LLM confidence miscalibration: [arXiv 2603.09985](https://arxiv.org/pdf/2603.09985)
- Multi-agent deliberation in law: [arXiv 2606.30906](https://arxiv.org/pdf/2606.30906)
- Jev (TypeSafe AI): [Arize docs](https://arize.com/docs/ax/evaluate/jev-as-a-judge), [overview](https://www.everydev.ai/tools/jev/llms.txt)
- Mistral Document AI annotations: [docs](https://docs.mistral.ai/capabilities/document_ai/annotations) · Leanstral: [Mistral](https://mistral.ai/news/leanstral-1-5/)
- Légifrance API: [data.gouv.fr](https://www.data.gouv.fr/dataservices/legifrance/) · Judilibre API: [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/api-judilibre/)
- Custody reform in force 1 July 2024: [Eurojuris](https://www.eurojuris.fr/articles/reforme-garde-a-vue-changements-42735.htm) · Loi 2026-651 and other legal sources: `CONTEXT.md` §12
