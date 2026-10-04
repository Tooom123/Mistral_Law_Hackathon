"""Shared data contracts. Every module reads and writes these types (see ARCHITECTURE.md §12)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "INTERPELLATION",
    "GARDE_A_VUE",
    "AUDITION",
    "PERQUISITION_SAISIE",
    "EXPERTISE",
    "INSTRUCTION",
    "INTERCEPTIONS",
    "GEOLOCALISATION",
    "AUTRE",
]
CATEGORIES: list[str] = list(Category.__args__)  # type: ignore[attr-defined]

Framework = Literal["flagrance", "preliminaire", "instruction", "unknown"]
Certainty = Literal["documented", "inferred", "needs_reading"]


class Page(BaseModel):
    doc_file: str
    page: int  # 1-based, global within the file
    text: str
    ocr: Literal["native", "mistral_ocr", "none"] = "native"


class Source(BaseModel):
    doc_id: str
    page: int
    quote: str


class Document(BaseModel):
    """One procès-verbal (or other piece), possibly spanning several pages."""

    id: str  # e.g. PV number "2026/0412/07"
    type: str  # PV_PLACEMENT_GAV, PV_NOTIFICATION_DROITS, ...
    title: str
    pages: list[int]
    text: str


class Fact(BaseModel):
    id: str
    doc_id: str
    kind: str
    value: str | bool | None
    source: Source
    extraction: Literal["explicit", "inferred", "unreadable"] = "explicit"


class Act(BaseModel):
    id: str
    category: str
    type: str
    label: str
    start: datetime | None = None
    end: datetime | None = None
    framework: Framework = "unknown"
    doc_ids: list[str] = Field(default_factory=list)
    facts: dict[str, Fact] = Field(default_factory=dict)  # kind -> fact (first occurrence)

    def fact(self, kind: str) -> Fact | None:
        return self.facts.get(kind)

    def value(self, kind: str):
        f = self.facts.get(kind)
        return None if f is None else f.value


class Edge(BaseModel):
    src: str
    dst: str
    kind: Literal["PRECEDES", "SUPPORTS", "CONTRADICTS"]
    basis: Literal["structural", "cited_in_text", "llm_inferred"] = "structural"
    evidence: Source | None = None


class RequirementVersion(BaseModel):
    valid_from: date | None = None
    valid_to: date | None = None
    check: str  # name of a predicate in judge/predicates.py
    params: dict = Field(default_factory=dict)
    note: str = ""


class Requirement(BaseModel):
    id: str
    category: str
    title: str
    provision: str
    source_url: str = ""
    applies_to: list[str]  # act types
    frameworks: list[str] = Field(default_factory=lambda: ["flagrance", "preliminaire", "instruction", "unknown"])
    needs_facts: list[str] = Field(default_factory=list)
    test: Literal["deterministic", "judgment"] = "deterministic"
    versions: list[RequirementVersion]
    rights_at_stake: list[str] = Field(default_factory=list)
    confidence: Literal["H", "M", "L"] = "M"
    validated_by: str | None = None
    statement_template: str = ""

    def version_at(self, d: date | None) -> RequirementVersion | None:
        if d is None:
            return self.versions[-1]
        for v in self.versions:
            if (v.valid_from is None or d >= v.valid_from) and (v.valid_to is None or d < v.valid_to):
                return v
        return None


class Verdict(BaseModel):
    status: Literal["violated", "satisfied", "missing_fact", "needs_judgment"]
    statement: str = ""
    sources: list[Source] = Field(default_factory=list)
    certainty: Certainty = "documented"
    details: dict = Field(default_factory=dict)


class Finding(BaseModel):
    id: str
    requirement_id: str | None
    category: str
    kind: Literal["rule_violation", "missing_mention", "contradiction", "discovered"]
    act_ids: list[str]
    title: str
    statement: str
    certainty: Certainty
    sources: list[Source]
    law: dict = Field(default_factory=dict)
    cascade: list[str] = Field(default_factory=list)
    cascade_basis: dict[str, str] = Field(default_factory=dict)
    precedents: list[dict] = Field(default_factory=list)
    counter_arguments: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    judge: dict = Field(default_factory=dict)
    rank: float = 0.0


class CaseResult(BaseModel):
    case_id: str
    title: str
    framework: Framework
    stats: dict
    documents: list[Document]
    acts: list[Act]
    edges: list[Edge]
    findings: list[Finding]
    deadline: dict = Field(default_factory=dict)
    unreadable_pages: list[int] = Field(default_factory=list)
