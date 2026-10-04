"""⑥ ATTACH + DETECT — run every catalogue entry on every node of its category (ARCHITECTURE §3).

Law-as-of-date: by default the version in force at the date of the act; `as_of` forces one date
(time-travel slider: « droit applicable au … »).
"""

from __future__ import annotations

import logging
from datetime import date

from casebreak.judge import judge
from casebreak.nullities.checks import CHECKS, GraphCtx, Result
from casebreak.nullities.versions import load_catalogue, version_label
from casebreak.propagate.cascade import affected
from casebreak.schemas import CaseGraph, Check, Node, Nullity

log = logging.getLogger(__name__)

CERT_SCORE = {"documented": 3, "inferred": 2, "needs_reading": 1}


def node_date(n: Node) -> date | None:
    if n.start:
        return n.start.date()
    for k in ("start_date_only", "end_date", "custody_end_date"):
        a = n.attr(k)
        if a and a.value:
            try:
                return date.fromisoformat(str(a.value)[:10])
            except ValueError:
                continue
    return None


def _applies(nl: Nullity, n: Node) -> bool:
    return n.subtype in nl.applies_to and (n.framework in nl.frameworks or n.framework == "unknown" and "unknown" in nl.frameworks)


def _build(nl: Nullity, n: Node, res: Result, law_date: date | None, ctx: GraphCtx, use_judge: bool) -> Check:
    certainty = res.certainty
    details = dict(res.details)
    ocr = ctx.ocr_pages(res.sources)
    if ocr and certainty == "documented":
        certainty = "inferred"
        details["ocr_note"] = f"Valeurs lues par OCR (p. {', '.join(map(str, sorted(set(ocr))))}) — vérifier la page."
    status = res.status
    jd = None
    if res.grey and use_judge:
        jd = judge.ask(nl, n, res.grey_attr, res.sources, ctx.pages)
        if jd:
            if nl.id == "GAV-01":
                ans = next((a for a in jd["answers"] if a.get("id") == "objective_stated"), {})
                if ans.get("answer") is False:
                    status, res.statement = "needs_reading", (
                        "Motivation du placement relevée, mais aucun objectif concret identifié : formule à lire.")
                elif ans.get("answer") is True and not jd["unsure"]:
                    status = "satisfied"
            certainty = "needs_reading" if jd["unsure"] else ("inferred" if certainty != "needs_reading" else certainty)
    if res.proof:
        details["proof_facts"] = res.proof
    return Check(
        nullity_id=nl.id, node_id=n.id, title=nl.title, article=nl.article,
        law_version=version_label(nl, law_date), kind=res.kind or nl.kind, status=status, certainty=certainty,
        statement_fr=res.statement, sources=res.sources, judge=jd, details=details,
        next_steps=list(nl.next_steps), rights_at_stake=list(nl.rights_at_stake), confidence=nl.confidence,
        validated_by=nl.validated_by,
    )


def run_checks(g: CaseGraph, as_of: date | None = None, use_judge: bool = True) -> list[Check]:
    cat = load_catalogue()
    ctx = GraphCtx(g.nodes, g.edges, {p.page: p for p in g.pages})
    node_idx = {n.id: n for n in g.nodes}
    checks: list[Check] = []
    for n in g.nodes:
        n.checks = []
        if n.type != "ACT":
            continue
        for nl in cat.values():
            if not _applies(nl, n):
                continue
            law_date = as_of or node_date(n)
            v = nl.version_at(law_date)
            if v is None or v.check not in CHECKS:
                continue
            try:
                res = CHECKS[v.check](n, ctx, v.params)
            except Exception as e:  # noqa: BLE001 — one broken check must not kill the case
                log.exception("check %s on %s failed: %s", nl.id, n.id, e)
                continue
            if res is None:
                continue
            c = _build(nl, n, res, law_date, ctx, use_judge)
            if c.status in ("possible_nullity", "needs_reading"):
                aff = affected(n.id, g.edges, node_idx)
                c.affected = list(aff.keys())
                c.affected_depth = {k: v["depth"] for k, v in aff.items()}
                c.details["cascade"] = aff
            n.checks.append(c)
            checks.append(c)
    rank(checks, cat)
    return checks


def rank(checks: list[Check], cat: dict[str, Nullity]) -> None:
    """certainty → number of acts affected → category weight (ARCHITECTURE §4)."""
    for c in checks:
        if c.status not in ("possible_nullity", "needs_reading"):
            c.rank = 0
            continue
        w = cat[c.nullity_id].weight if c.nullity_id in cat else 0.5
        c.rank = (100 if c.status == "possible_nullity" else 0) + CERT_SCORE[c.certainty] * 30 + \
            min(len(c.affected), 12) * 4 + w * 10
    alerts = sorted([c for c in checks if c.rank > 0], key=lambda c: -c.rank)
    for i, c in enumerate(alerts, 1):
        c.id = f"A{i:02d}"
