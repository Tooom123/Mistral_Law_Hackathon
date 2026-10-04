"""Deadline clock (CONTEXT §6.6). Always displayed « à vérifier »: a wrong deadline is worse than none.

Anchor: mise en examen (art. 173-1 CPP). Both regimes are computed (6 months / 4 months, loi n° 2026-651)
because the entry into force of art. 9 is ambiguous in the official source — TODO(legal).
"""

from __future__ import annotations

import calendar
from datetime import date

from casebreak.config import settings
from casebreak.nullities.versions import load_catalogue
from casebreak.schemas import CaseGraph


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def today() -> date:
    return date.fromisoformat(settings.today) if settings.today else date.today()


def deadlines(g: CaseGraph, ref: date | None = None) -> dict:
    nl = load_catalogue()["DLN-01"]
    params = nl.versions[-1].params
    now = ref or today()
    anchors = [n for n in g.nodes if n.type == "ACT" and n.subtype == "mise_en_examen" and n.start]
    out = []
    for a in sorted(anchors, key=lambda n: n.start):
        d0 = a.start.date()
        person = a.val("person_name") or a.label
        regimes = []
        for months, label in [(params.get("after_months", 4), "loi n° 2026-651 (art. 9) — entrée en vigueur à vérifier"),
                              (params.get("before_months", 6), "régime antérieur")]:
            dl = add_months(d0, int(months))
            regimes.append({"months": months, "label": label, "deadline": dl.isoformat(), "days_left": (dl - now).days})
        src = a.attr("date").src if a.attr("date") else None
        out.append({"node_id": a.id, "person": person, "anchor": d0.isoformat(), "anchor_label": "Mise en examen",
                    "source": src.model_dump() if src else None, "regimes": regimes})
    return {
        "today": now.isoformat(), "article": nl.article, "anchors": out, "status": "à vérifier",
        "entry_into_force": params.get("entry_into_force"),
        "note": "Délai calculé depuis la mise en examen. Date d'entrée en vigueur de la loi n° 2026-651 et dispositions "
                "transitoires à vérifier sur Légifrance. Les deux régimes sont affichés. TODO(legal)",
        "cutoff": {"id": "DLN-02", "article": load_catalogue()["DLN-02"].article,
                   "note": "Date butoir des mémoires en nullité : modalités à vérifier. TODO(legal)"},
    }
