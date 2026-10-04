# Case Study — McKinsey / French Senate Investigation

## 1. General Context

Between 2018 and 2022, the French government increasingly relied on private consulting firms to support public policy and government operations.

Firms such as **McKinsey**, BCG, Accenture, and Capgemini were hired by various government administrations for consulting, organizational transformation, crisis management, and operational support.

The issue became particularly visible during the **COVID-19 pandemic**, when consulting firms were involved in several aspects of the French government's response, including the vaccination campaign.

In November 2021, the **French Senate launched an investigative committee** to examine the influence of private consulting firms on public policy.

---

# 2. The French Senate Investigation

The investigation examined:

* The French government's use of private consulting firms
* The cost of consulting contracts
* How contracts were awarded
* The actual role of consultants in public decision-making
* Ethical and deontological rules
* Potential conflicts of interest
* Consultants' declarations of interests
* Information flows between consulting firms and government administrations
* Relationships between public officials and private consulting firms

The committee conducted:

* **40 hearings**
* Including **22 hearings under oath**
* And collected **more than 7,000 documents**

The final report was published in **March 2022**.

---

# 3. Why McKinsey Became Central

McKinsey became one of the main firms examined by the committee.

The firm worked with the French government during the COVID-19 crisis, including on aspects of the **COVID-19 vaccination campaign**.

Its missions included topics such as:

* Vaccination strategy
* Logistics
* Campaign monitoring
* Organization and coordination
* Operational support for government administrations

The investigation therefore sought to answer questions such as:

> **What was the actual role of consulting firms in public decision-making?**

and:

> **What safeguards existed to prevent conflicts of interest and ensure the independence of consultants?**

---

# 4. The Conflict-of-Interest Issue

One of the major issues identified by the committee concerned **ethical rules and potential conflicts of interest**.

When a private consulting firm works for the government, several questions arise:

* Who are the consultants working on the mission?
* Who are their other clients?
* Have they previously worked for companies affected by the relevant public policy?
* Do they have personal or professional relationships with relevant decision-makers?
* Did they submit declarations of interest?
* Were those declarations actually reviewed?
* Did the administration have enough information to identify potential conflicts?

The Senate highlighted difficulties surrounding the government's ability to effectively identify and control potential conflicts of interest involving consultants.

---

# 5. Declarations of Interest

For certain government consulting missions, mechanisms requiring consultants to declare their interests were in place.

However, the committee found that it had access to a **very limited number of declarations of interest** compared with the number of consultants involved in certain missions.

This raised a fundamental question:

> **Was the conflict-of-interest prevention mechanism actually effective?**

This is particularly relevant to CASEBREAK because answering this question requires connecting information spread across multiple documents.

For example:

```text
Consultant
    ↓
Government Mission
    ↓
Government Administration
    ↓
Declaration of Interest
    ↓
Previous Employers / Clients
    ↓
Relationships with Relevant Actors
```

An individual document may reveal nothing problematic.

The potential issue only becomes visible when **multiple documents are cross-referenced**.

---

# 6. The Tax Statement Case

Another particularly interesting episode concerns a hearing before the Senate committee.

On **January 18, 2022**, a McKinsey executive was questioned **under oath** by the investigative committee.

The committee questioned him about McKinsey's tax situation in France.

The executive stated that McKinsey paid corporate income tax in France.

The committee subsequently sought to verify this statement using information obtained from the French tax administration.

The Senate considered the information it obtained to be inconsistent with the statement made during the hearing and considered that the facts could potentially constitute **false testimony before a parliamentary investigative committee**.

The Senate subsequently referred the matter to the judicial authorities.

---

# 7. Why This Episode Is Important for CASEBREAK

This is almost exactly the type of problem our system should be able to identify.

The reasoning chain is:

```text
HEARING
    ↓
Statement made under oath
    ↓
"McKinsey pays corporate tax in France"
    ↓
        CROSS-CHECK
    ↓
Tax / administrative information
    ↓
Potential contradiction
    ↓
Committee investigation
    ↓
Potential false testimony
    ↓
Referral to judicial authorities
```

The important point is that the contradiction is **not necessarily visible in a single document**.

It emerges when multiple sources are connected:

* Hearing transcripts
* Administrative documents
* Tax-related information
* Committee reports
* Legal documents concerning the referral

This is precisely the type of **cross-document reasoning** CASEBREAK is designed for.

---

# 8. Why This Case Is Relevant to Our Project

The McKinsey case has several characteristics that make it particularly suitable for CASEBREAK.

### Large volume

The committee collected **more than 7,000 documents**.

### Heterogeneous information

The corpus includes different types of material:

* Hearing transcripts
* Investigation reports
* Contracts
* Administrative documents
* Statements
* Financial information
* Information about consultants
* Information about consulting missions

### Complex relationships

The same people and organizations appear across many different documents.

For example:

```text
PERSON
   ↓
CONSULTING FIRM
   ↓
MISSION
   ↓
MINISTRY
   ↓
CONTRACT
   ↓
DECISION
```

### Cross-document inconsistencies

Important statements may need to be compared against information found in completely different documents.

### Ethical questions

Conflicts of interest, declarations of interest, and consultant independence require information to be connected across multiple sources.

---

# 9. What CASEBREAK Should Demonstrate

The goal is **not** to reproduce the Senate's investigation.

The goal is to demonstrate that CASEBREAK can automate part of the investigative process.

## Input

A large legal/institutional case file containing:

> 1,000+ documents
> 10,000+ pages
> Hundreds of entities
> Dozens of missions
> Thousands of relationships

## Processing

CASEBREAK:

1. Extracts people and organizations
2. Identifies consulting missions
3. Reconstructs events
4. Extracts important claims and statements
5. Links claims to supporting evidence
6. Reconstructs relationships between entities
7. Builds a timeline
8. Detects contradictions
9. Detects potential conflicts of interest
10. Checks evidence chains
11. Identifies procedural inconsistencies

## Output

```text
CASE INTEGRITY AUDIT

Documents analyzed: 7,000+
Entities identified: XXX
Claims extracted: XXX
Evidence links: XXX

CRITICAL FINDINGS
────────────────────────

1. Potential conflict of interest
2. Contradictory statement
3. Missing evidence
4. Timeline inconsistency
5. Broken evidence chain
```

Every finding must be **traceable back to its original source**:

```text
Finding
   ↓
Claim
   ↓
Evidence
   ↓
Document
   ↓
Page
```

---

# 10. Important: Do Not Overinterpret

CASEBREAK should never automatically present an anomaly as a legal violation.

The system should distinguish between:

### Observation

> Two documents contain incompatible information.

↓

### Analysis

> The contradiction concerns information relevant to the procedure.

↓

### Potential Risk

> This may raise an ethical, procedural, or legal issue.

↓

### Human Review

> **Requires legal / compliance review.**

The AI **identifies and documents potential problems**.

It does not make the final legal determination.

---

# 11. Our New Niche

## Legal Integrity & Procedural Forensics

Our niche is:

> **Auditing the integrity of complex legal and institutional processes by automatically cross-referencing thousands of documents.**

CASEBREAK looks for:

* Contradictions
* Potential conflicts of interest
* Unverified statements
* Broken evidence chains
* Timeline anomalies
* Important claims lacking supporting evidence
* Inconsistencies between the documented procedure and the available evidence

## Core Principle

> **Don't summarize the case. Audit it.**

Or:

> **Turn thousands of documents into an integrity audit.**
