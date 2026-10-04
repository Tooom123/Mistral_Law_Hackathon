"""Text helpers shared by ingestion, extraction and verification.

`norm()` lowercases and strips accents *without changing the length* of the string, so a regex
match on the normalised text maps back to the exact same span of the original (verbatim quotes).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from casebreak.schemas import PageRec, Piece, Src

_SPECIAL = {"œ": "o", "Œ": "o", "æ": "a", "Æ": "a", "’": "'", "‘": "'", "«": '"', "»": '"', " ": " ",
            "–": "-", "—": "-", "°": "o", "\n": " ", "\t": " "}


def _norm_char(c: str) -> str:
    if c in _SPECIAL:
        return _SPECIAL[c]
    d = unicodedata.normalize("NFD", c)
    base = "".join(ch for ch in d if unicodedata.category(ch) != "Mn")
    base = base.lower()
    return base if len(base) == 1 else c.lower()[:1] or " "


def norm(s: str) -> str:
    """Same-length, lowercase, accent-free version of `s`."""
    return "".join(_norm_char(c) for c in s)


def squash(s: str) -> str:
    """Collapse whitespace (for quote comparison)."""
    return re.sub(r"\s+", " ", s).strip()


def quote_on_page(quote: str, page_text: str) -> bool:
    """Hard rule (ARCHITECTURE §2): a quote is valid only if literally present on its page."""
    q = squash(quote)
    return bool(q) and q in squash(page_text)


def quote_on_page_loose(quote: str, page_text: str) -> bool:
    """Same check, accent/case-insensitive (OCR'd pages lose accents)."""
    q = squash(norm(quote))
    return bool(q) and q in squash(norm(page_text))


@dataclass
class Hit:
    start: int
    end: int
    page: int
    quote: str
    m: re.Match
    doc_id: str

    def group(self, i: int | str = 0) -> str:
        return self.m.group(i) or ""

    @property
    def src(self) -> Src:
        return Src(doc_id=self.doc_id, page=self.page, quote=self.quote)


class PieceText:
    """The text of one piece across its pages, searchable on the normalised form."""

    def __init__(self, piece: Piece, pages: dict[int, PageRec]):
        self.piece = piece
        parts, self.offsets = [], []
        pos = 0
        for p in piece.pages:
            t = pages[p].text if p in pages else ""
            self.offsets.append((pos, p, t))
            parts.append(t)
            pos += len(t) + 1
        self.orig = "\n".join(parts)
        self.norm = norm(self.orig)

    def _page_of(self, idx: int) -> tuple[int, int, str]:
        cur = self.offsets[0]
        for o in self.offsets:
            if o[0] <= idx:
                cur = o
        return cur

    def _quote(self, start: int, end: int) -> tuple[int, str]:
        base, page, text = self._page_of(start)
        s, e = start - base, min(end - base, len(text))
        ls = text.rfind("\n", 0, s) + 1
        le = text.find("\n", e)
        le = len(text) if le == -1 else le
        # extend to the next line when the sentence obviously continues (wrapped lines)
        q = text[ls:le]
        if len(q) > 220:
            q = text[max(ls, s - 60): min(le, e + 80)]
        return page, squash(q)

    def find(self, pattern: str, start: int = 0) -> Hit | None:
        m = re.compile(pattern).search(self.norm, start)
        if not m:
            return None
        page, q = self._quote(m.start(), m.end())
        return Hit(m.start(), m.end(), page, q, m, self.piece.id)

    def find_all(self, pattern: str) -> list[Hit]:
        out = []
        for m in re.compile(pattern).finditer(self.norm):
            page, q = self._quote(m.start(), m.end())
            out.append(Hit(m.start(), m.end(), page, q, m, self.piece.id))
        return out

    def src_at(self, start: int, end: int) -> Src:
        page, q = self._quote(start, end)
        return Src(doc_id=self.piece.id, page=page, quote=q)

    def raw(self, hit: Hit, group: int | str = 0) -> str:
        """Original (accented) text of a group."""
        return self.orig[hit.m.start(group): hit.m.end(group)]

    def line_at(self, idx: int) -> str:
        ls = self.orig.rfind("\n", 0, idx) + 1
        le = self.orig.find("\n", idx)
        return self.orig[ls: len(self.orig) if le == -1 else le]
