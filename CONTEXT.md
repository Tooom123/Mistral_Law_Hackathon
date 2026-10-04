# CASEBREAK — Claude Code Context

## 1. Project Overview

**CASEBREAK** is an AI-native legal forensic system built for the **LLM × Law Hackathon**, organized by **Mistral AI and Stanford Law**.

### Core problem

Large legal cases can contain hundreds or thousands of pages:

* court filings
* legal briefs
* contracts
* witness statements
* emails
* reports
* evidence
* expert reports
* annexes
* previous decisions
* procedural documents

A critical contradiction or inconsistency can be buried deep inside the case.

The goal is **not** to build another legal chatbot or document summarizer.

The goal is:

> **Find the structural weaknesses in a legal case that could materially undermine its arguments or potentially create procedural issues.**

### Core pitch

> **We don't summarize legal cases. We find the inconsistencies that can break them.**

Alternative:

> **Upload a case. Reconstruct it. Attack it. Find the flaw. Prove why it matters.**

---

# 2. Product Vision

CASEBREAK ingests an entire legal case and constructs a structured representation of it.

The system connects:

* documents
* people
* organizations
* facts
* claims
* evidence
* events
* dates
* legal arguments
* legal authorities
* procedural steps

into a **Case Graph**.

It then uses multiple specialized AI agents to detect:

* factual contradictions
* timeline inconsistencies
* contradictory witness statements
* unsupported claims
* evidence gaps
* conflicting documents
* incorrect references
* legal argument weaknesses
* procedural inconsistencies
* contradictions between different sections of the same report
* contradictions across different documents

The most important goal is to identify **load-bearing facts**.

A load-bearing fact is a fact that supports many other claims or arguments.

If that fact is disproven, many downstream parts of the case may become weaker.

---

# 3. Critical Product Principle

Do NOT build:

> "ChatGPT for lawyers."

Do NOT prioritize:

* generic chat
* generic PDF summarization
* generic RAG Q&A
* simple contract summarization

These are not sufficiently differentiated for this hackathon.

The product must feel like:

> **A legal forensic investigation system.**

The system should actively **attack the case** rather than passively answer questions.

---

# 4. Main User Flow

## Step 1 — Upload Case

The user uploads:

* PDFs
* DOCX
* emails
* text files
* potentially ZIPs containing multiple documents

Example:

```text
CASE_2048/

127 documents
2,400 pages
38 witnesses
217 entities
534 claims
```

The system processes the case.

---

## Step 2 — Case Reconstruction

Extract:

### Entities

* people
* companies
* organizations
* lawyers
* witnesses
* judges
* locations

### Events

* meetings
* emails
* signatures
* payments
* incidents
* filings
* decisions
* communications

### Claims

Every meaningful factual/legal assertion.

Example:

> "John was present at the meeting on March 12."

### Evidence

What supports or contradicts each claim.

### Legal arguments

How facts are used to support a legal conclusion.

### Legal authorities

* statutes
* regulations
* cases
* precedents
* contractual clauses

---

# 5. Case Graph

The Case Graph is one of the most important parts of the product.

Example:

```text
                         CASE
                          |
             +------------+------------+
             |            |            |
           FACTS       PEOPLE       EVENTS
             |            |            |
        +----+----+       |       +----+----+
        |         |       |       |         |
     CLAIM A   CLAIM B  WITNESS  DATE     ACTION
        |         |               |
        +----+----+---------------+
             |
       CONTRADICTION
             |
       LEGAL ISSUE
```

### Node types

* Document
* Person
* Organization
* Event
* Date
* Location
* Claim
* Evidence
* Legal Rule
* Contract Clause
* Procedural Step
* Contradiction

### Relationship types

* `MENTIONS`
* `SUPPORTS`
* `CONTRADICTS`
* `REFUTES`
* `OCCURRED_BEFORE`
* `OCCURRED_AFTER`
* `SIGNED_BY`
* `SENT_BY`
* `REFERENCES`
* `DEPENDS_ON`
* `DERIVED_FROM`
* `EVIDENCES`
* `AFFECTS`

Every important AI conclusion should ideally be traceable back to source documents and page numbers.

---

# 6. Multi-Agent Architecture

The system should conceptually contain specialized agents.

## Document Agent

Reads and structures documents.

Responsibilities:

* document classification
* section extraction
* metadata
* page references

---

## Entity Agent

Extracts:

* people
* organizations
* dates
* locations
* documents
* events

Resolves aliases.

Example:

```text
"John Smith"
"J. Smith"
"Mr Smith"
```

should potentially resolve to the same entity.

---

## Claim Agent

Extracts meaningful assertions.

Example:

```text
CLAIM #284

"The contract was signed on March 12."

Source:
Contract.pdf
Page 4
```

---

## Evidence Agent

Determines what supports or contradicts each claim.

Example:

```text
CLAIM #284

Supporting:
✓ Contract.pdf p.4

Contradicting:
⚠ Email_032.pdf
⚠ Amendment.pdf p.2
```

---

## Timeline Agent

Builds a chronological timeline.

It should detect:

* impossible chronology
* conflicting dates
* events occurring before their alleged causes
* inconsistent timestamps
* impossible presence/location

---

## Contradiction Agent

Looks for contradictions:

### Direct contradiction

```text
Document A:
"The meeting occurred on March 12."

Document B:
"The meeting occurred on March 15."
```

### Indirect contradiction

```text
A says:
John was present.

B says:
John was abroad.

C shows:
John's flight departed that morning.
```

### Internal contradiction

Two sections of the same document disagree.

---

## Legal Research Agent

Finds relevant legal authorities.

It should never invent citations.

Every legal proposition should be connected to a verifiable source where possible.

---

## Red Team Lawyer Agent

Its objective is:

> **Attack the case.**

It should actively search for ways an opposing lawyer could exploit:

* contradictions
* unsupported claims
* missing evidence
* procedural issues
* weak legal reasoning
* inconsistent timelines
* problematic documents

---

## Judge / Reviewer Agent

The reviewer evaluates findings.

It should determine:

* Is this actually a contradiction?
* How confident are we?
* How important is it?
* Which claims depend on it?
* Could it materially affect the case?
* Is additional evidence required?

---

# 7. Contradiction Severity

Do not simply return a list of contradictions.

Classify them.

### 🟢 Minor

Likely typo or irrelevant inconsistency.

### 🟡 Relevant

Real inconsistency but limited impact.

### 🟠 Material

Could affect an argument or important factual issue.

### 🔴 Critical

Potentially affects a fundamental part of the case.

### 🔥 Load-Bearing

A fact or assumption that supports many downstream arguments.

This is one of the most important concepts in CASEBREAK.

---

# 8. Dependency / Cascade Analysis

A contradiction should not be treated in isolation.

The system should ask:

> **What depends on this fact?**

Example:

```text
FACT A
 |
 +-- CLAIM 1
 |     |
 |     +-- ARGUMENT 1
 |
 +-- CLAIM 4
 |     |
 |     +-- ARGUMENT 3
 |
 +-- EVIDENCE 12
       |
       +-- LEGAL CONCLUSION
```

If Fact A is invalidated:

```text
FACT A ❌
 |
 +-- CLAIM 1 ❌
 |     |
 |     +-- ARGUMENT 1 ⚠
 |
 +-- CLAIM 4 ❌
       |
       +-- ARGUMENT 3 ⚠
```

The UI should explain:

> **This contradiction affects 4 claims, 2 arguments and 1 procedural conclusion.**

---

# 9. "Find the Fatal Flaw"

This should be a major feature.

Button:

> ⚔️ ATTACK THE CASE

The system launches its forensic analysis.

Potential output:

```text
CASE ANALYSIS COMPLETE

127 documents
2,400 pages
534 claims

12 inconsistencies detected

3 Critical
4 Material
5 Minor

TOP FINDING

🔴 LOAD-BEARING CONTRADICTION

Confidence: 94%

This contradiction affects:

4 claims
2 legal arguments
1 procedural step
```

---

# 10. "What Breaks If This Is False?"

A key feature.

When the user opens a contradiction, allow:

> **SIMULATE IMPACT**

The system removes the disputed fact/claim from the Case Graph and recomputes dependencies.

Example:

```text
FACT REMOVED
      ↓
4 CLAIMS AFFECTED
      ↓
2 ARGUMENTS AFFECTED
      ↓
1 PROCEDURAL STEP AFFECTED
      ↓
POTENTIAL MATERIAL IMPACT
```

This turns contradiction detection into **structural case analysis**.

---

# 11. Evidence Coverage

For every important claim, show:

```text
CLAIM

"The defendant knew about the breach before January 15."

Evidence coverage:

████████░░ 80%

Supporting:
✓ Email #32
✓ Witness #4

Contradicting:
⚠ Email #41

Missing:
❌ Direct evidence
```

This helps identify:

* unsupported claims
* weak claims
* contradictory evidence
* missing evidence

---

# 12. Missing Evidence

Another important feature.

The system should ask:

> **What evidence would resolve this uncertainty?**

Example:

```text
CONFLICT

Witness says:
Meeting occurred March 12.

Email says:
Meeting occurred March 15.

Potential resolving evidence:

→ Calendar records
→ Email metadata
→ Building access logs
→ Travel records
```

This turns CASEBREAK from a passive analyzer into an **investigation assistant**.

---

# 13. Legal / Procedural Issues

The system can identify potential procedural issues.

IMPORTANT:

Never claim automatically:

> "This contradiction makes the procedure null."

Instead use:

> "Potential procedural issue detected."

Then show:

```text
ISSUE
  ↓
Relevant procedural rule
  ↓
Requirement
  ↓
Detected potential violation
  ↓
Affected procedural step
  ↓
Potential consequence
  ↓
Evidence required
```

The product should clearly distinguish:

1. AI-detected inconsistency
2. legal relevance
3. potential procedural implication
4. final legal determination

The system is an investigative/research tool, not a lawyer or court.

---

# 14. Main Application Pages

## Page 1 — Dashboard

Show:

* Case overview
* Number of documents
* Number of claims
* Number of entities
* Number of contradictions
* Critical findings
* Case health / consistency overview

Example:

```text
CASE #2048

127 documents
2,400 pages
534 claims
217 entities

🔴 3 Critical
🟠 4 Material
🟡 5 Minor
```

---

## Page 2 — Case Graph

Interactive graph.

Allow filtering by:

* people
* documents
* claims
* events
* contradictions
* legal issues

Clicking a node should show source information.

---

## Page 3 — Timeline

Interactive chronological reconstruction.

Show:

* events
* documents
* claims
* people
* contradictions

Highlight impossible or disputed chronology.

---

## Page 4 — Findings

List all detected issues.

Filters:

* Critical
* Material
* Minor
* Timeline
* Evidence
* Witness
* Legal
* Procedural

---

## Page 5 — Finding Detail

Example:

```text
🔴 CASE-BREAKING CONTRADICTION

Claim:
"The agreement was signed on March 12."

Source A:
Contract.pdf — page 4

Source B:
Email_032.pdf — March 11

Contradiction:
...

Why it matters:
...

Affected claims:
4

Affected arguments:
2

Affected procedural steps:
1

Confidence:
94%

Impact:
HIGH
```

Include buttons:

* `View in Graph`
* `View Timeline`
* `Simulate Impact`
* `Find Supporting Evidence`
* `Find Counterarguments`
* `Research Legal Relevance`

---

## Page 6 — War Room

A visually impressive "Attack the Case" interface.

Show the Red Team agent working through the case.

Example:

```text
⚔️ RED TEAM ANALYSIS

✓ Checking timeline
✓ Checking witness statements
✓ Checking evidence
✓ Checking legal claims
✓ Checking citations
✓ Searching contradictions

3 critical vulnerabilities found.
```

---

## Page 7 — Report

Generate:

**CASEBREAK RED TEAM REPORT**

Sections:

1. Executive Summary
2. Critical Findings
3. Material Findings
4. Timeline Issues
5. Evidence Gaps
6. Contradictory Statements
7. Load-Bearing Facts
8. Procedural Issues
9. Recommended Further Investigation
10. Source References

Export as PDF if time allows.

---

# 15. Source Traceability

This is critical.

Never show an important AI conclusion without allowing the user to inspect its source.

Every finding should contain:

```text
SOURCE

Contract.pdf
Page 47
Paragraph 3
```

Clicking it should open the relevant document/page.

This is important for trust and is particularly relevant given the previous success of citation-verification tools such as NeoMagus.

---

# 16. UX Principles

The UI should feel like:

* Bloomberg Terminal
* Palantir
* forensic investigation software
* modern legal intelligence platform

NOT:

* ChatGPT clone
* generic SaaS dashboard

Prioritize visual information:

* graph
* timeline
* evidence chains
* severity indicators
* dependency maps
* document highlighting

The user should understand the product visually before reading long explanations.

---

# 17. Demo Strategy

The demo should use a deliberately large case.

Example:

```text
127 documents
2,400 pages
38 witnesses
217 entities
534 claims
```

Start with:

> "A human lawyer would need days to manually cross-check this."

Then:

### Upload

↓

### Build Case Graph

↓

### ATTACK CASE

↓

### Find 3 Critical Vulnerabilities

↓

Open the strongest one.

Show:

```text
Document A
    ↓
Claim
    ↓
Document B
    ↓
Contradiction
    ↓
Load-bearing fact
    ↓
4 affected claims
    ↓
2 affected arguments
    ↓
Potential procedural issue
```

Then click:

> **SIMULATE IMPACT**

This should be the main "wow moment."

---

# 18. Technical Priorities

Build the smallest system that convincingly demonstrates the concept.

Priority order:

### P0 — MUST HAVE

* Multi-document ingestion
* Chunking / retrieval
* Entity extraction
* Claim extraction
* Evidence linking
* Contradiction detection
* Source/page citations
* Findings dashboard
* Case Graph
* Timeline
* Red Team analysis

### P1 — HIGH VALUE

* Dependency analysis
* Load-bearing fact detection
* Impact simulation
* Missing evidence detection
* Legal research
* procedural issue detection

### P2 — NICE TO HAVE

* PDF report export
* authentication
* collaborative features
* email integration
* continuous monitoring

Do NOT spend hackathon time on:

* complex auth
* billing
* production infrastructure
* unnecessary settings
* generic chat interface

---

# 19. Mistral / Sponsor Alignment

The project should make meaningful use of the sponsors.

Potential roles:

### Mistral

Use Mistral models for:

* document understanding
* extraction
* reasoning
* agent orchestration
* structured outputs

### Jus Mundi

Potentially use for:

* international legal research
* case law
* arbitration
* precedent discovery

### Legora

Position the product as complementary to legal workflows:

> CASEBREAK is the **red-team / forensic layer** that challenges a legal matter before the lawyer relies on it.

### Hector

Potentially leverage legal workflow / document intelligence capabilities depending on available APIs or hackathon access.

---

# 20. Core Differentiation

The product is NOT:

> "AI reads your legal documents."

It is:

> **"AI reconstructs the entire case as a dependency graph and searches for structural weaknesses that humans might miss."**

The key phrase:

> **Structural weakness.**

Not just contradiction.

A contradiction is useful because it can propagate through the graph.

---

# 21. Product Philosophy

The system should always answer four questions:

### 1. WHAT IS WRONG?

What inconsistency or weakness was detected?

### 2. WHERE IS IT?

Which documents/pages/evidence demonstrate it?

### 3. WHY DOES IT MATTER?

Which claims, arguments or procedural steps depend on it?

### 4. WHAT SHOULD WE DO?

What evidence or legal research should be performed next?

This four-step structure should guide the entire UX.

---

# 22. Final Product Statement

The strongest version of the product is:

> **CASEBREAK is an AI legal forensic system that turns thousands of pages of case material into a living dependency graph, automatically finds contradictions and unsupported claims, identifies the load-bearing facts behind a case, and shows how a single inconsistency could propagate through the entire legal argument.**

Short pitch:

> **"Don't summarize the case. Break it."**

Alternative:

> **"Find the flaw before the opposing counsel does."**

---

# 23. Development Rule

Always prioritize the **demo-critical path**:

```text
UPLOAD
  ↓
INGEST
  ↓
CASE GRAPH
  ↓
ATTACK CASE
  ↓
CONTRADICTION
  ↓
SOURCE EVIDENCE
  ↓
IMPACT ANALYSIS
  ↓
PROCEDURAL RELEVANCE
```

Every implementation decision should help make this flow more convincing.

If a feature does not improve this flow, deprioritize it during the hackathon.
