"""Shared data contracts (ARCHITECTURE.md §6). Every module reads and writes these types."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

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

# Swim-lane order in the UI (top to bottom).
LANES: list[str] = [
    "INTERPELLATION",
    "GARDE_A_VUE",
    "AUDITION",
    "PERQUISITION_SAISIE",
    "EXPERTISE",
    "GEOLOCALISATION",
    "INTERCEPTIONS",
    "INSTRUCTION",
    "AUTRE",
]

Framework = Literal["flagrance", "preliminaire", "instruction", "unknown"]
Certainty = Literal["documented", "inferred", "needs_reading"]
CheckStatus = Literal["satisfied", "possible_nullity", "needs_reading", "not_applicable"]
EdgeKind = Literal["PRECEDES", "PART_OF", "DOCUMENTED_IN", "SUPPORTS", "INVOLVES", "CONTRADICTS"]
EdgeOrigin = Literal["structural", "cited_in_text", "llm_inferred"]


class Src(BaseModel):
    """Where a value comes from. `quote` is verbatim text of that page (checked by code)."""

    doc_id: str
    page: int  # 1-based, global within the case file
    quote: str


class Attr(BaseModel):
    value: str | bool | int | float | list | dict | None = None
    src: Src | None = None
    status: Literal["explicit", "inferred", "unreadable", "missing"] = "explicit"


class Check(BaseModel):
    """One possible nullity evaluated on one node."""

    id: str = ""  # alert id once ranked, e.g. "A03"
    nullity_id: str  # GAV-04
    node_id: str
    title: str = ""
    article: str = ""
    law_version: str = ""
    kind: Literal["rule", "missing_mention", "contradiction", "graph"] = "rule"
    status: CheckStatus
    certainty: Certainty
    statement_fr: str
    sources: list[Src] = Field(default_factory=list)
    judge: dict | None = None
    affected: list[str] = Field(default_factory=list)
    affected_depth: dict[str, int] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    rights_at_stake: list[str] = Field(default_factory=list)
    confidence: Literal["H", "M", "L", "n/a"] = "M"
    validated_by: str | None = None
    rank: float = 0.0


class Node(BaseModel):
    id: str
    type: Literal["ACT", "PIECE", "PERSON", "ITEM"]
    category: str | None = None
    subtype: str = ""
    label: str = ""
    start: datetime | None = None
    end: datetime | None = None
    framework: Framework = "unknown"
    attrs: dict[str, Attr] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    person: str | None = None  # node id of the person concerned (ACT)

    def attr(self, key: str) -> Attr | None:
        return self.attrs.get(key)

    def val(self, key: str, default=None):
        a = self.attrs.get(key)
        return default if a is None or a.value is None else a.value

    def src(self, key: str) -> Src | None:
        a = self.attrs.get(key)
        return None if a is None else a.src


class Edge(BaseModel):
    src: str
    dst: str
    kind: EdgeKind
    origin: EdgeOrigin = "structural"
    src_ref: Src | None = None
    label: str = ""


class PageRec(BaseModel):
    page: int  # global, 1-based
    file: str  # file name inside the case folder
    file_page: int  # 0-based page index inside that file (images: 0)
    kind: Literal["pdf_native", "pdf_scan", "image"] = "pdf_native"
    ocr: Literal["native", "tesseract", "mistral_ocr", "none"] = "native"
    text: str = ""
    readable: bool = True
    words: list[tuple[float, float, float, float, str]] = Field(default_factory=list)  # normalised bbox 0..1
    width: float = 0
    height: float = 0
    exif: dict[str, str] = Field(default_factory=dict)


class Piece(BaseModel):
    """One procès-verbal (or other piece), possibly spanning several pages."""

    id: str  # doc id, e.g. "D12"
    number: str = ""  # PV number as printed
    type: str  # PV_PLACEMENT_GAV, PV_NOTIFICATION_DROITS, PHOTO, ...
    category: str = "AUTRE"
    title: str = ""
    pages: list[int] = Field(default_factory=list)
    text: str = ""
    classified_by: Literal["rules", "llm", "unknown"] = "rules"


class Review(BaseModel):
    decision: Literal["accepted", "rejected", "pending"] = "pending"
    note: str = ""
    at: datetime | None = None


class CaseGraph(BaseModel):
    case_id: str
    title: str = ""
    framework: Framework = "unknown"
    pages: list[PageRec] = Field(default_factory=list)
    pieces: list[Piece] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


# --------------------------------------------------------------------------- catalogue


class Version(BaseModel):
    valid_from: date | None = None
    valid_to: date | None = None
    label: str = ""  # "CPP 63-1, version issue de la loi du 22 avril 2024"
    check: str  # name of a function in nullities/checks.py
    params: dict[str, Any] = Field(default_factory=dict)
    grey_zone: dict[str, Any] | None = None
    note: str = ""

    def applies(self, d: date | None) -> bool:
        if d is None:
            return self.valid_to is None
        return (self.valid_from is None or d >= self.valid_from) and (self.valid_to is None or d < self.valid_to)


class Nullity(BaseModel):
    id: str
    category: str
    title: str
    article: str
    applies_to: list[str]
    frameworks: list[str] = Field(default_factory=lambda: ["flagrance", "preliminaire", "instruction", "unknown"])
    needs: list[str] = Field(default_factory=list)
    kind: Literal["rule", "missing_mention", "contradiction", "graph"] = "rule"
    condition_type: Literal["measurable", "open_textured", "structural", "procedural"] = "measurable"
    versions: list[Version]
    confidence: Literal["H", "M", "L", "n/a"] = "M"
    validated_by: str | None = None
    rights_at_stake: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    prosecution_hints: list[str] = Field(default_factory=list)
    judilibre_query: str = ""
    weight: float = 1.0
    source_url: str = ""
    legal_todo: list[str] = Field(default_factory=list)

    def version_at(self, d: date | None) -> Version | None:
        for v in self.versions:
            if v.applies(d):
                return v
        return None
