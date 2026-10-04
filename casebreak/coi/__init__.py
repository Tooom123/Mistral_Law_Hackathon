"""Conflict-of-interest audit.

A case file (contracts, staffing plans, declarations of interests, deliverables, decisions, hearings) is read into
facts with their page and span; conflict-of-interest rules cross-reference those facts across documents; every flag
is matched against a database of past conflict-of-interest cases, and points the reviewer to the exact lines to read.

    casefile   → documents and pages (the McKinsey case ships as a synthetic reconstruction)
    extract    → facts: assignments, engagements, declarations, employment, signatures, statements, ownership…
    rules      → cross-document detectors (metadata in rules.yaml)
    precedents → past-case database + hybrid retrieval (BM25 + pattern overlap, Mistral embeddings with a key)
    audit      → orchestration: facts → flags → precedents → timeline → JSON
"""

from casebreak.coi.audit import run_audit  # noqa: F401
