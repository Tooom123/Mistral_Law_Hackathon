# CASEBREAK — Claude Code Context

> Shared context for the team and for Claude Code. Read §0–§4 before writing code (10 min).
> Last update: **4 Oct 2026, morning of the hackathon.**
> Legal content status: **researched, NOT validated by a lawyer.** Every rule carries a source and a confidence level (§7). Nothing legal is shown in the demo before our legal teammate (LSE) or Hector signs it off.

---

## 0. TL;DR

**CASEBREAK reads a French criminal case file (thousands of pages, scans, photos), rebuilds the timeline of every procedural act, and finds the procedural defects that could get evidence thrown out — then shows exactly what else would fall with it.**

- **Input:** a *dossier pénal*: police reports (PV), custody records, searches, wiretaps, geolocation, photos, court orders.
- **Output:** a **timeline × category graph** of the case, a ranked list of **potential procedural defects (moyens de nullité)** each pinned to the exact page, the **cascade** of acts that depend on it, the **precedents** where the same defect was argued, and the **deadline** to raise it.
- **Why we win:** real buyer (Hector told us they would hire for this), legally grounded concept (not a metaphor), measurable accuracy, and a deadline that just got shorter (§2).
- **Rule of thumb for every feature:** *the LLM reads, the code judges, the lawyer decides.*

Pitch line: **"Find the procedural flaw before the deadline does."**
Alternate: **"Don't summarize the case. Break it — with the page number."**

---

## 1. Why we changed the previous version of this file

The first CASEBREAK draft was "find contradictions in any legal case" (civil, contracts, witnesses, emails). Good instincts — load-bearing facts, impact simulation, traceability — but four problems in front of *this* jury:

1. **It already exists.** Relativity *aiR for Case Strategy* (launched Jan 2026) extracts facts with citations, builds chronologies with **"issue swim lanes"**, and flags harmful/contradictory facts; Everlaw and CoCounsel do deposition contradictions. A generic version built in 8 h looks like a weaker clone.
2. **"Load-bearing fact" is our metaphor, not a legal concept.** Lawyers will ask "under which rule does this fact matter?" Without a rule, a contradiction is trivia.
3. **Too broad to be credible.** Partners from Cleary, Darrois, Orrick will poke at one example. A tool that covers "all cases" is shallow on every one.
4. **It dropped the actual lead.** Hector said they'd hire for **criminal cases with huge files where one procedural error can sink everything**. That is a specific, French, legally-codified problem.

**What we keep from the draft:** case graph, impact simulation, the four questions (what / where / why it matters / what next), source traceability, red-team framing, "never claim nullity automatically".

**What changes:** the domain is **French criminal procedure**; "load-bearing" becomes the real legal doctrine of **nullity cascade** (an annulled act takes down the acts it is the *necessary support* of — art. 174 CPP); contradictions are hunted **only where they touch a procedural rule**; we add **law-as-of-date**, **precedents** and **deadlines**; we **remove fake confidence percentages** (an expert jury will ask how "94 %" was computed).

---

## 2. The problem, in plain words (for engineers)

- A French criminal investigation produces a **file of thousands of pages**: each act (arrest, custody, search, seizure, wiretap, geolocation, hearing, indictment) produces an official report (**procès-verbal, PV**).
- Each act must follow **formal rules** of the Code de procédure pénale (CPP): who may authorize it, when, how long, which rights must be read and when, who must be present.
- If a rule was violated **and** it harmed the person's interests (**grief**), the defense can ask the court to **annul** the act (**nullité**). The annulled act is removed from the file — and so are the acts that **depend on it**. A bad search can take down the seizure, the lab report on what was seized, and the interrogation about it.
- The defense must find these defects by **reading everything**, and **must raise them within strict deadlines**, or lose the right forever (**forclusion**).

### Why now (verified against the Ministry of Justice table, see §12)

**Loi n° 2026-651 du 23 juillet 2026 sur la justice criminelle et le respect des victimes**, article 9:

- **Shortens the deadline to file a nullity request during an investigation from 6 to 4 months** (art. 173-1 CPP).
- **Imposes a hard cut-off for filing nullity briefs** before the investigating chamber and the criminal court (art. 198, 221-3, 385 CPP), except when the party could not have known the defect or was summoned less than 20 days before the hearing.
- **Entry into force: ambiguous in the official source.** The DACG table lists article 9 as "Immédiate" on one page and "3 mois après la promulgation, soit le 23 octobre 2027" on another; a secondary source says 25 October 2026. Three months after July 2026 is late October 2026 — the "2027" looks like a typo. **Check on Légifrance before saying a date on stage.**

So: **same thousands of pages, one third less time.** That is our "why now". (Bonus anecdote, use carefully: the government's own implementation table contradicts itself on the date — exactly the kind of inconsistency CASEBREAK flags.)

Second recent change worth knowing: **loi du 22 avril 2024** removed the 2-hour waiting period after which police could interrogate a custody suspect without their lawyer (art. 63-4-2 CPP). **Which rule applies depends on the date of the act.** That is our "law-as-of-date" feature (§5.4) and a detail experts will notice.

---

## 3. Users and positioning

| User | Job | What CASEBREAK gives them |
|---|---|---|
| **Criminal defense lawyer** (primary, Hector's target) | Find defects in a huge file before the deadline | Ranked potential defects with page, cascade, precedents, deadline |
| **Prosecutor / investigating judge** (secondary) | Make sure the procedure is clean before trial | Same engine as a **regularity audit** — fix defects before they become nullities |
| **Legal tech platforms** (Hector, Legora) | Add a criminal-procedure layer | API: dossier in → structured procedural graph + findings out |

Framing for the jury: **this is not a tool to "get criminals off".** It enforces **procedural guarantees** and helps **both sides** — the same audit helps prosecutors avoid losing a case on a technicality. Equality of arms.

**Confidentiality:** a criminal file is covered by investigation secrecy. Mistral's open-weight models can run **on the firm's own servers** — say it in the pitch; it is a real differentiator vs US cloud tools.

---

## 4. The product

### 4.1 Main flow (the golden path)

```text
UPLOAD DOSSIER  (PDF scans, images, maybe audio)
   ↓
READ            OCR + vision, every fact keeps its page & position
   ↓
RECONSTRUCT     acts + timestamps + actors → timeline × category graph
   ↓
CHECK           rules-as-code per category, law in force at the act's date
   ↓
CROSS-CHECK     contradictions between documents on rule-relevant facts
   ↓
CASCADE         what depends on the defective act → what falls with it
   ↓
GROUND          precedents (Cour de cassation) + verbatim article text
   ↓
ACT             deadline clock + draft list of "moyens" for the lawyer
```

### 4.2 The four questions every finding must answer (kept from v1)

1. **What is wrong?** — factual statement: "Rights notified at 14:20; custody started at 11:05 (3 h 15 gap)."
2. **Where is it?** — doc, page, highlighted line. Click → page opens.
3. **Why does it matter?** — rule (article, version in force at that date) + cascade (acts potentially affected) + precedents.
4. **What next?** — what the lawyer must check (grief, justification in the file), what evidence would settle it, and the deadline.

### 4.3 Vocabulary we use in the UI (credibility)

- ✅ "**Potential procedural defect**", "**moyen de nullité à examiner**", "**actes potentiellement affectés**"
- ❌ Never "nullity", "null", "this act is void", "the case collapses".
- ❌ No percentage confidence. Use **categorical confidence** derived from how the finding was produced (§6.5).

---

## 5. Architecture

> **Full architecture lives in `ARCHITECTURE.md`** (Fact Bank × Law Bank, two-way matcher, judge, certainty, API, repo layout, build plan). The overview below is kept for context; if they differ, `ARCHITECTURE.md` wins.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ 1. INGEST    PDF/images → pages → OCR text + layout + bbox               │
│              images → vision description + visible text + EXIF          │
│              document classifier: PV GAV / PV perquisition / ordonnance… │
├──────────────────────────────────────────────────────────────────────────┤
│ 2. EXTRACT   per document, schema-constrained LLM extraction:            │
│              Acts, Timestamps, Actors, Mentions (rights, consent, auth.) │
│              each Fact = value + Source(doc, page, quote, bbox) + conf.  │
├──────────────────────────────────────────────────────────────────────────┤
│ 3. GRAPH     nodes: Act / Fact / Actor / Document / Finding / Precedent  │
│              edges: PRECEDES, SUPPORTS(necessary support), CONTRADICTS,  │
│                     FLAGGED_BY(rule), HAS_PRECEDENT, SOURCED_FROM        │
│              two axes: TIME (timestamp) × CATEGORY (swim lane)           │
├──────────────────────────────────────────────────────────────────────────┤
│ 4. ENGINES   a. Rules engine (deterministic, versioned by date)          │
│              b. Contradiction engine (same fact, two sources, ≠ values)  │
│              c. Cascade engine (graph traversal on SUPPORTS edges)       │
│              d. Precedent retrieval (Judilibre, by category)             │
│              e. Deadline engine (forclusion clock, flagged "to verify")  │
├──────────────────────────────────────────────────────────────────────────┤
│ 5. REVIEW    Reviewer agent: drops findings without source, merges       │
│              duplicates, ranks; never upgrades a finding's certainty     │
├──────────────────────────────────────────────────────────────────────────┤
│ 6. UI        Timeline × category swim lanes · Findings · Page viewer     │
│              · Cascade simulation · Report export                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Categories (the swim lanes — fix this list in the first hour, one owner: legal teammate)

| Category | Typical acts | MVP? |
|---|---|---|
| `INTERPELLATION` | arrest, identity check | P1 |
| `GARDE_A_VUE` | placement, rights notification, lawyer, doctor, extension, release | **P0** |
| `PERQUISITION_SAISIE` | search, seizure, sealing (scellés) | **P0** |
| `AUDITION` | hearings, confrontations | P1 (linked to GAV) |
| `INTERCEPTIONS` | wiretaps | P2 |
| `GEOLOCALISATION` | tracking devices, phone geolocation | P2 |
| `EXPERTISE` | lab reports, phone extraction | P1 (cascade target) |
| `INSTRUCTION` | mise en examen, orders of the judge | P1 (deadline anchor) |

### 5.2 Data model (Pydantic — the contract between components)

```python
class Source(BaseModel):
    doc_id: str; page: int; quote: str            # verbatim text
    bbox: tuple[float, float, float, float] | None
    ocr_confidence: float | None

class Fact(BaseModel):
    id: str; act_id: str
    kind: str          # "custody_start", "rights_notified", "lawyer_requested", "search_start", "consent_signed"…
    value: str | datetime | bool
    source: Source
    extraction: Literal["explicit", "inferred", "unreadable"]

class Act(BaseModel):
    id: str; category: str; type: str
    start: datetime | None; end: datetime | None
    framework: Literal["flagrance", "preliminaire", "instruction", "unknown"]
    actors: list[str]; facts: list[str]; sources: list[Source]

class Edge(BaseModel):
    src: str; dst: str
    kind: Literal["PRECEDES", "SUPPORTS", "CONTRADICTS", "FLAGGED_BY", "HAS_PRECEDENT", "SOURCED_FROM"]
    basis: Literal["structural", "cited_in_text", "llm_inferred"]   # how we know
    evidence: Source | None

class Rule(BaseModel):
    id: str            # "GAV-04"
    category: str; description: str
    articles: list[str]
    valid_from: date | None; valid_to: date | None    # law-as-of-date
    source_url: str; confidence: Literal["H", "M", "L"]
    validated_by: str | None

class Finding(BaseModel):
    id: str; rule_id: str | None; kind: Literal["rule_violation", "contradiction", "missing_mention"]
    act_ids: list[str]; statement: str                  # factual, no legal conclusion
    sources: list[Source]
    certainty: Literal["documented", "inferred", "needs_reading"]
    rights_at_stake: list[str]                          # grief is for the lawyer
    cascade: list[str]                                  # act ids potentially affected
    precedents: list[str]
    next_steps: list[str]
```

### 5.3 Why the cascade is legally real (our "load-bearing" feature)

- Art. 174 CPP (secondary sources): the court annuls the defective act **and may annul all or part of the subsequent procedure** that depends on it; recent case law requires the request to **name precisely** each subsequent act targeted.
- So the cascade output is directly useful: **a list of acts to name in the request**, each with why it depends (cites the seized item, follows from the custody, etc.).
- `SUPPORTS` edges come from: (1) **structural** links (seizure PV ← search PV; lab report cites seal n°X ← seizure), (2) **cited_in_text** ("vu le PV n°…"), (3) **llm_inferred** (shown dashed, lower certainty).
- UI says "**potentially affected**" — "necessary support" is for the judge to decide.

### 5.4 Law-as-of-date

Every rule has `valid_from` / `valid_to`. The engine applies **the version in force at the date of the act**, not today's. Example: an interrogation without lawyer after a 2-hour wait was lawful under the old art. 63-4-2 and is not after the 2024 reform. Same for deadlines (6 vs 4 months). **Show the version used** next to each finding.

### 5.5 Multimodal inputs

- **Scans:** OCR with page + bbox kept. Handwritten times are the #1 source of false positives → `certainty = needs_reading` when OCR is unsure.
- **Images:** vision model describes the photo and reads visible text (seal labels, screens). **EXIF timestamps** can corroborate or contradict a PV time — but may be stripped or wrong; never a finding on EXIF alone.
- **Audio (stretch):** Voxtral to transcribe recorded hearings and compare with the written PV.

---

## 6. Engines in detail

### 6.1 Rules engine (P0)
Pure Python functions over the graph, one per rule, unit-tested with fixtures. Input: acts of a category + framework + dates. Output: Findings. **No LLM inside a rule.**

### 6.2 Contradiction engine (P0 for times, P1 otherwise)
Only on **rule-relevant facts**: the same fact (e.g., custody start, arrest time, search start, persons present) reported by two documents with different values. A contradiction becomes a finding when **one of the values triggers a rule** — or is shown as "inconsistency to clarify" otherwise.

### 6.3 Cascade engine (P0)
Graph traversal from the flagged act over `SUPPORTS` edges. "Simulate impact" = remove node, recompute reachable set, animate. Report: "this defect potentially affects 6 acts: …".

### 6.4 Precedent engine (P1)
**Judilibre API** (Cour de cassation open data, free on the PISTE portal after registration; filter `chamber=cr` for the criminal chamber; endpoints `/search`, `/decision`, `/export`). Build a small **precedent base per category**: decisions where a similar defect was **accepted** *and* **rejected** (e.g., no grief) — both are useful. Show 1–3 per finding with link. **Never show a precedent we haven't retrieved from the API** (no LLM-recalled case law). Register on PISTE in the first hour — it can take time; fallback: a pre-fetched set.

### 6.5 Certainty (replaces fake percentages)

| Certainty | Meaning |
|---|---|
| `documented` | Deterministic rule fired on explicit facts with good OCR, all sources shown |
| `inferred` | Depends on an LLM-inferred link or an implicit fact |
| `needs_reading` | OCR doubt, missing mention, or contradicting sources — the lawyer must read the page |

### 6.6 Deadline engine (P1)
Computes the latest date to raise defects from the anchor act (mise en examen / copy of file) using the version in force. **Always displayed with "to verify"** and the article text. Showing a wrong deadline is worse than showing none.

---

## 7. Rule catalogue v1 (MVP = custody + search)

> **H** = confirmed by a primary/official or several consistent sources; **M** = secondary sources only; **L** = unverified.
> **Before coding any rule, someone opens the article on Légifrance and pastes the text in `rules/<id>.md`.** Automated Légifrance fetches failed during research.

### Custody — `GARDE_A_VUE`

| ID | Check | Art. | Conf. |
|---|---|---|---|
| GAV-01 | Placement decided by an OPJ; one of the legal objectives stated | 62-2 | H |
| GAV-02 | Initial max 24 h; one 24 h extension authorized by the prosecutor (ordinary offenses) | 63 | H |
| GAV-03 | Special regimes (organised crime, drugs, terrorism) up to 96 h / 144 h with specific authorizations | 706-88 s. | M |
| GAV-04 | Rights notified **immediately** (offense, duration, rights to inform someone, doctor, lawyer, interpreter, silence); notification recorded in the PV and signed | 63-1 | H |
| GAV-05 | Delay between placement and notification without operational justification | 63-1 | M |
| GAV-06 | Prosecutor informed from the start of custody | 63 | L |
| GAV-07 | Lawyer: confidential meeting (30 min) | 63-4 | M |
| GAV-08 | **Since the 22 April 2024 law:** no interrogation on the facts without the lawyer, unless express waiver in the PV or written prosecutor authorization in exceptional circumstances. **Before:** interrogation possible after 2 h wait. → law-as-of-date | 63-4-2 | H (reform), M (details) |
| GAV-09 | Doctor examination if requested | 63-3 | M |
| GAV-10 | Interpreter if the person doesn't understand French | 63-1 | H |
| GAV-11 | Right to inform a third party — since 2024 extended to "any person they designate" | 63-2 | M |
| GAV-12 | PV mentions: start/end, durations of hearings and rest, reasons | 64 | L |
| GAV-13 | Internal consistency: times across PVs agree | — | n/a (quality) |

### Search & seizure — `PERQUISITION_SAISIE`

| ID | Check | Art. | Conf. |
|---|---|---|---|
| PRQ-01 | Home searches not started before 6:00 or after 21:00 (save exceptions); one started before 21:00 may continue | 59 | H |
| PRQ-02 | Presence of the occupant, else representative / two witnesses (scope depends on framework) | 57 | M |
| PRQ-03 | Preliminary inquiry: **express consent** of the occupant (handwritten), unless judge authorization | 76 | H |
| PRQ-04 | Seized items inventoried and sealed (scellés) | 56 | M |

### Procedure-level (deadlines, framing)

| ID | Check | Art. | Conf. |
|---|---|---|---|
| DLN-01 | Nullity request deadline during investigation: 6 months → **4 months** (loi 2026-651, entry into force to verify) | 173-1 | H (change), L (date) |
| DLN-02 | Hard cut-off for nullity briefs before investigating chamber / criminal court | 198, 221-3, 385 | H (principle), M (details) |
| PRG-01 | Purge: once the investigating chamber has ruled, defects not raised are lost (unless unknowable) | 174 | M |
| GEN-01 | "No nullity without grief" — **grief is never decided by the tool** | 171, 802 | H |

### Do NOT cite on stage without retrieving them
Case-law dates found only on law-firm blogs (e.g., Crim. 7 Nov 2018, 6 May 2019, 12 Dec 2018, 29 Sept 2020, 18 Nov 2020). Use Judilibre or nothing.

---

## 8. Evaluation — our credibility weapon (P0)

Stanford's CodeX/RegLab community (Dan Ho, "Large Legal Fictions") judges legal AI by **measured** error rates. We bring numbers, honestly framed.

**NullityBench-FR (synthetic):**
1. Generate a coherent fictional case ("Affaire Mathurins"): people, places, a timeline of 20–60 acts across categories.
2. Render realistic PVs (French administrative style) → **300–1,000 pages**, some degraded to scans (rotation, noise, stamps, handwritten times), some photos with EXIF.
3. **Inject K defects** from the catalogue with ground truth `(rule_id, act_id, page)`, plus **decoys**: irregular-looking but lawful situations (justified delay, express waiver, special regime) to measure false positives.
4. Inject **cross-document contradictions** (two PVs disagree on a time) with known answer.
5. Measure per rule: **recall, precision, page-pin accuracy, cascade accuracy, time and € per 1,000 pages.**
6. **Baseline:** same dossier given to a strong LLM alone ("find procedural defects"). Our claim is the delta, not an absolute number.

How to say it on stage: *"On our synthetic set of N dossiers with M injected defects…"* — never more. State that synthetic data is cleaner than reality and that real validation needs Hector's files.

Publishing the generator + benchmark as open source is a credible "contribution to the field" line for academics.

---

## 9. Mistral stack (sponsor alignment that actually matters)

> Model names change: **check the console when credits arrive.** If we remove Mistral, OCR + extraction + on-prem story disappear → the integration is load-bearing.

| Need | Candidate | Note |
|---|---|---|
| OCR, layout, tables, handwriting | Mistral OCR (latest: OCR 3 per changelog, newer may exist) | keep page + bbox |
| Structured extraction | Mistral Large 3 / Medium | JSON schema, temperature 0 |
| Image understanding | Pixtral / multimodal Mistral | photos, seals, screenshots |
| Reasoning on ambiguous links | Magistral / Small 4 | only to propose `SUPPORTS` edges, never to judge |
| Retrieval inside the file | Mistral Embed | find passages for a fact |
| Audio (stretch) | Voxtral | recorded hearings vs PV |
| **Moonshot** | **Leanstral** (open-source Lean 4 prover, Apache-2.0, released 2026) | encode 2–3 rules in Lean and **prove** a violation on the timeline. Only if P0 is done by 15:00. |

On-prem line: "All models used are available as open weights or deployable in a private environment." **Verify for each model before saying it.**

---

## 10. UI

Pages, in demo order:

1. **Upload / War room** — dossier stats appearing live (docs, pages, acts, facts) as the pipeline runs.
2. **Timeline × category** (the hero screen): horizontal time axis, one swim lane per category, acts as blocks, defects as red markers, contradictions as zig-zag links, `SUPPORTS` arrows on hover.
3. **Finding detail** — the four questions; source page with highlighted line; article text (version in force); precedents; deadline; buttons `Simulate impact`, `Open page`, `Show precedents`.
4. **Cascade simulation** — remove the act, dependent acts grey out in stop-motion, counter "6 acts potentially affected".
5. **Report** — list of moyens to examine, each with sources and acts to name. Export PDF if time allows.

Style: the repo has a Mistral brand kit and a "cut-out collage" guide (`front_mistral-main/`). **Use collage for the landing and the cascade animation; keep the working screens sober and dense** (lawyers judge legibility of a timestamp, not stickers). No fake numbers in the UI.

---

## 11. Plan

### Priorities

**P0 (demo-critical, must work end-to-end on the demo dossier)**
- Ingest PDFs (+ images) → OCR with pages
- Extraction of GAV + search acts/facts with sources
- Timeline × category view
- Rules GAV-01/02/04/05/08/10 + PRQ-01/03
- Time contradictions between PVs
- Cascade + simulate impact
- Page viewer with highlight
- Synthetic dossier with ground truth + metrics table

**P1** — precedents via Judilibre · deadline clock · law-as-of-date on GAV-08 · more rules · reviewer agent · report

**P2** — wiretaps/geolocation · Voxtral · Leanstral proof · PDF export · prosecutor mode toggle

**Never** — auth, billing, generic chat, "ask your file" box.

### Timeline

| Time | Goal |
|---|---|
| 9:40–10:00 | Team, roles, **Hector questions (§13)**, categories frozen |
| 10:00–11:00 | Repo skeleton, schemas, OCR on 1 PDF end-to-end; **PISTE registration**; generator v0 |
| 11:00–12:30 | Extraction GAV/search; first 4 rules; demo dossier v1 with 6 injected defects |
| 12:30–14:30 | Graph + cascade; contradictions; timeline UI; metrics script |
| 14:30–16:00 | Finding detail + page highlight; precedents; law-as-of-date; more rules |
| 16:00–17:00 | Polish golden path; run eval, freeze numbers; stretch only if green |
| 17:00–17:40 | **Code freeze**, rehearsal ×2, backup video recorded |
| 17:40–18:00 | **Submit** (before 18:00 hard stop) |
| 19:00 | Pitch |

### Roles
- **Legal (LSE):** freezes categories; validates every rule text on Légifrance; picks decoys; owns pitch narrative and Q&A on law; talks to Hector.
- **Eng 1 – Ingest/extract:** OCR, classifier, extraction, French date/time parser (formats "14h20", "14 H 20", midnight crossing).
- **Eng 2 – Graph/engines:** rules, contradictions, cascade, deadlines.
- **Eng 3 – Data/eval:** synthetic dossier generator, ground truth, metrics, baseline.
- **Eng 4 – Front/demo:** timeline swim lanes, finding detail, cascade animation, backup video.

### Demo script (4 min)
1. **Hook (20 s):** "A criminal file: 1,000 pages. One custody report where rights were read three hours late can take down the search, the seizure, the lab report. And since this summer, the defense has 4 months instead of 6 to find it."
2. **Upload (20 s):** dossier in, war room counters.
3. **Timeline (40 s):** swim lanes appear — custody, search, hearings, expertise.
4. **Finding (60 s):** open the top defect → exact page, highlighted line, article text in force *at that date*, precedent from the Cour de cassation.
5. **Simulate impact (40 s):** the act is removed, 6 dependent acts grey out → "acts to name in the request".
6. **Proof (30 s):** metrics table vs LLM-alone baseline, on synthetic data, said honestly.
7. **Close (30 s):** both sides benefit, runs on-prem with Mistral, Hector's use case.

---

## 12. Sources and verification ledger

### Verified (primary/official)
- **Loi n° 2026-651 du 23 juillet 2026**, art. 9: nullity deadline 6 → 4 months (173-1), cut-off for nullity briefs (198, 221-3, 385), 15-day citation delay (552). Source: Ministry of Justice, DACG entry-into-force table (PDF, justice.gouv.fr, July 2026). **Table is internally inconsistent on the date** (immediate vs "23 octobre 2027").
- **Loi du 22 avril 2024** (art. 32): GAV reform — 2-hour waiting period removed, lawyer access to hearing PVs, right to inform any designated person. Source: [CNB](https://cnb.avocat.fr/actualite/garde-a-vue-elargissement-des-droits-et-suppression-du-delai-de-carence).
- **Ordonnance n° 2025-1091** recodifying the CPP, entry into force planned 1 Jan 2029 (possible postponement to 31 Jan 2030). We use **current numbering**. Source: [Actu-Juridique](https://www.actu-juridique.fr/procedure-penale/la-reecriture-du-code-de-procedure-penale-enjeux-methode-et-architecture-de-lordonnance-n-2025-1091-du-19-novembre-2025/).
- **Judilibre API**: free via PISTE, criminal chamber filter `cr`, endpoints search/decision/export. Sources: [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/api-judilibre/), [pyjudilibre](https://pyjudilibre.readthedocs.io/en/latest/), [GitHub](https://github.com/Cour-de-cassation/judilibre-search/).
- **Relativity aiR for Case Strategy** (chronologies, issue swim lanes, contradictions): [LawNext, Jan 2026](https://www.lawnext.com/2026/01/relativity-launches-air-for-case-strategy-to-extract-and-organize-key-facts-using-generative-ai.html).
- **Leanstral** (Mistral, open-source Lean 4 prover): [Mistral news](https://mistral.ai/news/leanstral-1-5/).

### Secondary only (law-firm sites) — verify before coding
- Art. 171/802 grief principle; art. 174 cascade and "name each act" requirement; art. 173 formalities; GAV durations; search hours and presence rules. Sources: [Cabinet ACI – requête en nullité](https://www.cabinetaci.com/requete-en-nullite-quand-et-comment-agir-en-procedure-penale/), [Documentissime – GAV](https://www.documentissime.fr/actualites-juridiques/la-garde-a-vue-causes-de-nullite-et-importance-de-la-presence-de-l-avocat-520-imprimer.html), [Cabinet ACI – perquisition](https://www.cabinetaci.com/perquisition-penale-droits-nullites-et-defense/).
- Summary of loi 2026-651 incl. "25 October 2026": [L'Officiel des métiers](https://www.lofficieldesmetiers.fr/justice-penale-et-droits-des-victimes-la-nouvelle-loi-est-promulguee/).

### Unknown
- What **Hector** already builds (no public info found).
- Today's **judging criteria** (briefing 9:20).
- Exact Mistral model IDs available with our credits.
- "NeoMagus" (cited in v1 as a past winner) — **not found**; removed. Closest real examples: *ConsistencyCheck* (1st, Cambridge Hack the Law 2026) and *Citrus* (citation checker).

### Research context (for Q&A)
- Legal AI trust gap and hallucinations: [LePhantomCite](https://arxiv.org/abs/2606.21155), [LexAgentHallu](https://arxiv.org/pdf/2609.09754), [Legal warrant](https://arxiv.org/pdf/2609.17546), [Know Your Limits – "scope laundering"](https://arxiv.org/pdf/2606.16118) → why the code, not the LLM, applies the rules.
- [Charlotin AI hallucination cases database](https://www.damiencharlotin.com/hallucinations/) (CC BY 4.0).

---

## 13. Questions for Hector (ask before 10:00 — write answers here)

1. Who is the user (defense lawyer? firm size?) and where does the time go today?
2. **Top 5 defects** that actually win in practice?
3. What does a real file look like: native PDF or scans, size, document types, images, audio?
4. Ideal output: list, report, annotations in the PDF, timeline?
5. What do you already have? What's missing?
6. Cost of a false positive vs a false negative?
7. Can you share an **anonymized file or PV templates**?
8. Can someone **review our rule list** for 15 minutes today?
9. Do you also see value for prosecutors / judges (regularity audit)?
10. Is there a Hector challenge prize, and what are its criteria?

**Answers:** _to fill_

**Go/no-go:** if Hector can neither give an example nor confirm the defects list, fall back to the **plan B** (citation/warrant checker + injected-error benchmark) reusing ingest, page-pinning and eval.

---

## 14. Rules for Claude Code and for us

- **Never invent law.** No article, case, date or deadline in code or UI that is not in §7/§12 or retrieved from an official API. If missing → `TODO(legal)`.
- **Every finding has a source** (doc, page, quote). No source → not displayed.
- **The LLM extracts; Python decides.** No legal judgement inside prompts.
- **No real case data** in the repo, prompts or logs. Synthetic only, unless Hector provides anonymized material (kept out of git).
- **No made-up numbers** in UI or pitch. Metrics come from the eval script.
- Keep the golden path green at all times; features that don't serve it wait.
- Language: code and docs in English; UI and legal terms in **French** (the jury reads French PVs).
