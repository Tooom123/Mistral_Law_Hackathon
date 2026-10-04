"""Catalogue loading and law-as-of-date (ARCHITECTURE §1.3, CONTEXT §5.4)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from casebreak.schemas import Nullity

CATALOGUE_DIR = Path(__file__).parent / "catalogue"


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Nullity]:
    out: dict[str, Nullity] = {}
    for f in sorted(CATALOGUE_DIR.glob("*.yaml")):
        raw = yaml.safe_load(f.read_text())
        out[raw["id"]] = Nullity(**raw)
    return out


def version_label(n: Nullity, d: date | None) -> str:
    v = n.version_at(d)
    if v is None:
        return f"{n.article} — no version applicable on that date"
    when = d.strftime("%d/%m/%Y") if d else "unknown date"
    return f"{v.label} — in force on {when}"


def reform_dates() -> list[dict]:
    """Every date at which a catalogue rule changes: the time-travel slider snaps to these."""
    seen: dict[date, list[str]] = {}
    for n in load_catalogue().values():
        for v in n.versions:
            for d in (v.valid_from, v.valid_to):
                if d:
                    seen.setdefault(d, []).append(n.id)
    return [{"date": d.isoformat(), "rules": sorted(set(ids))} for d, ids in sorted(seen.items())]
