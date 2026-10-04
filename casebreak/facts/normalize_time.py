"""French date/time parsing for procès-verbaux.

Handles "11h05", "11 H 05", "11:05", "à onze heures cinq", "quatorze heures vingt",
"le douze mars deux mille vingt-six", "12/03/2026", "12 mars 2026".
Never guesses: returns None when the string is not understood.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time

UNITS = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13,
    "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60, "mille": 1000, "cent": 100,
}
MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def words_to_int(s: str) -> int | None:
    """'vingt et une' -> 21, 'dix-sept' -> 17, 'deux mille vingt-six' -> 2026."""
    s = _strip(s).replace("-", " ").replace(" et ", " ")
    tokens = [t for t in s.split() if t]
    if not tokens:
        return None
    total, current = 0, 0
    for t in tokens:
        if t.isdigit():
            current += int(t)
            continue
        if t not in UNITS:
            return None
        v = UNITS[t]
        if v == 1000:
            total += (current or 1) * 1000
            current = 0
        elif v == 100:
            current = (current or 1) * 100
        else:
            current += v
    return total + current


_NUM_TIME = re.compile(r"\b([01]?\d|2[0-3])\s*(?:h|H|:)\s*([0-5]\d)?\b")
_WORD_TIME = re.compile(
    r"\b((?:[a-z]+[\s-]?){1,3}?)\s+heures?(?:\s+((?:[a-z]+[\s-]?){1,4}))?",
)


def parse_time(s: str) -> time | None:
    if not s:
        return None
    m = _NUM_TIME.search(s)
    if m:
        return time(int(m.group(1)), int(m.group(2) or 0))
    t = _strip(s)
    if "midi" in t and "heure" not in t:
        return time(12, 0)
    if "minuit" in t and "heure" not in t:
        return time(0, 0)
    m = _WORD_TIME.search(t)
    if not m:
        return None
    h_words = m.group(1).strip().split()
    # keep only trailing number words before "heures"
    h_tokens: list[str] = []
    for w in reversed(h_words):
        if w == "et" or all(p in UNITS for p in w.split("-")):
            h_tokens.insert(0, w)
        else:
            break
    h = words_to_int(" ".join(h_tokens)) if h_tokens else None
    if h is None or h > 23:
        return None
    minutes = 0
    if m.group(2):
        mw: list[str] = []
        for w in m.group(2).strip().split():
            if all(p in UNITS for p in w.split("-")) or w == "et":
                mw.append(w)
            else:
                break
        if mw:
            parsed = words_to_int(" ".join(mw))
            if parsed is None or parsed > 59:
                return None
            minutes = parsed
    return time(h, minutes)


_NUM_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_TEXT_DATE = re.compile(r"\b(\d{1,2}|1er)\s+([a-zéû]+)\s+(\d{4})\b")
_WORD_DATE = re.compile(r"\b((?:[a-z]+[\s-]){1,3}?)(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\s+((?:[a-z]+[\s-]?){2,5})")


def parse_date(s: str) -> date | None:
    if not s:
        return None
    m = _NUM_DATE.search(s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    t = _strip(s)
    m = _TEXT_DATE.search(t)
    if m and m.group(2) in MONTHS:
        day = 1 if m.group(1) == "1er" else int(m.group(1))
        return date(int(m.group(3)), MONTHS[m.group(2)], day)
    m = _WORD_DATE.search(t)
    if m:
        day_words = [w for w in m.group(1).split() if all(p in UNITS for p in w.split("-"))]
        day = words_to_int(" ".join(day_words[-2:])) if day_words else None
        year = words_to_int(m.group(3))
        if day and year and 1900 < year < 2100:
            return date(year, MONTHS[m.group(2)], day)
    return None


def parse_datetime(s: str, default_date: date | None = None) -> datetime | None:
    t = parse_time(s)
    d = parse_date(s) or default_date
    if t is None or d is None:
        return None
    return datetime.combine(d, t)


def fmt_fr(dt: datetime | None) -> str:
    if dt is None:
        return "?"
    return dt.strftime("%d/%m/%Y %Hh%M")
