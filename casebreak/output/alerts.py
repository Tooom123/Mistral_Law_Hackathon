"""Alert cards — the four questions (ARCHITECTURE §5): what · where · why it matters · what next.

`mode="prosecution"` reframes the same graph as a pre-trial regularity audit (equality of arms).
"""

from __future__ import annotations

import re

from casebreak.nullities.versions import load_catalogue
from casebreak.privacy.pseudonymize import mask_value
from casebreak.schemas import CaseGraph, Check, Node, PageRec
from casebreak.text import norm

CERTAINTY_LABEL = {"documented": "documented", "inferred": "inferred", "needs_reading": "needs reading"}
STATUS_LABEL = {"possible_nullity": "possible nullity", "needs_reading": "to investigate", "satisfied": "compliant",
             "not_applicable": "not applicable"}
PARQUET_STEPS = {
    "default": "Check the document and, where possible, regularise or document it before the investigation closes.",
    "missing_mention": "Find the missing entry and add the corresponding document to the file.",
    "contradiction": "Have the clerical error corrected by a report; recompute the time limits.",
    "graph": "Add the cited but missing document to the file.",
}


def review_key(c: Check) -> str:
    return f"{c.nullity_id}@{c.node_id}"


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", norm(s)) if t]


def highlights(page: PageRec, quotes: list[str]) -> list[dict]:
    """Boxes (normalised 0..1) of each quote on the page, merged per line."""
    words = [(w[0], w[1], w[2], w[3], _tokens(w[4])) for w in page.words]
    flat = []  # (word_index, token)
    for i, w in enumerate(words):
        for t in w[4]:
            flat.append((i, t))
    out = []
    for qi, q in enumerate(quotes):
        qt = _tokens(q)
        if not qt or not flat:
            continue
        best, best_i = 0, -1
        for i in range(len(flat)):
            k = 0
            while i + k < len(flat) and k < len(qt) and flat[i + k][1] == qt[k]:
                k += 1
            if k > best:
                best, best_i = k, i
                if k == len(qt):
                    break
        if best < min(3, len(qt)):
            continue
        idxs = sorted({flat[j][0] for j in range(best_i, best_i + best)})
        lines: dict[int, list] = {}
        for j in idxs:
            x0, y0, x1, y1, _ = words[j]
            key = round(((y0 + y1) / 2) * 200)
            lines.setdefault(key, []).append((x0, y0, x1, y1))
        for boxes in lines.values():
            out.append({"x0": min(b[0] for b in boxes), "y0": min(b[1] for b in boxes), "x1": max(b[2] for b in boxes),
                        "y1": max(b[3] for b in boxes), "quote": qi, "complete": best == len(qt)})
    return out


def _piece_of(g: CaseGraph, doc_id: str):
    return next((p for p in g.pieces if p.id == doc_id), None)


def card(c: Check, g: CaseGraph, reviews: dict, mode: str = "defense", pseudo: bool = False) -> dict:
    cat = load_catalogue()
    nl = cat.get(c.nullity_id)
    idx: dict[str, Node] = {n.id: n for n in g.nodes}
    node = idx.get(c.node_id)
    m = (lambda s: mask_value(s)) if pseudo else (lambda s: s)
    cascade = c.details.get("cascade", {})
    acts = []
    for aid in c.affected:
        n = idx.get(aid)
        if not n:
            continue
        pcs = [_piece_of(g, d) for d in n.doc_ids]
        acts.append({"id": aid, "label": n.label, "category": n.category, "depth": c.affected_depth.get(aid, 1),
                     "via": cascade.get(aid, {}).get("via", ""), "origin": cascade.get(aid, {}).get("origin", "structural"),
                     "start": n.start.isoformat() if n.start else None,
                     "pieces": [{"cote": p.id, "number": p.number, "pages": p.pages[:3]} for p in pcs if p]})
    sources = []
    for s in c.sources:
        pc = _piece_of(g, s.doc_id)
        sources.append({"doc_id": s.doc_id, "page": s.page, "quote": m(s.quote),
                        "piece": {"number": pc.number, "title": pc.title, "type": pc.type} if pc else None})
    rv = reviews.get(review_key(c), {"decision": "pending"})
    is_parquet = mode == "prosecution"
    headline = ("Regularity issue to fix" if is_parquet else
                {"possible_nullity": "Possible nullity — ground to examine", "needs_reading": "To investigate — reading needed"}
                .get(c.status, STATUS_LABEL.get(c.status, c.status)))
    next_steps = ([PARQUET_STEPS.get(c.kind, PARQUET_STEPS["default"])] if is_parquet else list(c.next_steps))
    return {
        "id": c.id, "key": review_key(c), "nullity_id": c.nullity_id, "title": c.title, "headline": headline,
        "status": c.status, "status_label": STATUS_LABEL.get(c.status, c.status), "certainty": c.certainty,
        "certainty_label": CERTAINTY_LABEL[c.certainty], "kind": c.kind, "rank": c.rank, "confidence": c.confidence,
        "category": node.category if node else None,
        "node": {"id": c.node_id, "label": m(node.label) if node else "", "start": node.start.isoformat() if node and node.start else None,
                 "subtype": node.subtype if node else ""},
        "what": m(c.statement_fr),
        "where": sources,
        "why": {"article": c.article, "law_version": c.law_version, "rights_at_stake": c.rights_at_stake,
                "affected": acts, "affected_count": len(acts),
                "legal_todo": nl.legal_todo if nl else [], "validated_by": c.validated_by,
                "grief_note": "No nullity without prejudice (art. 171 and 802 CPP): prejudice is never assessed by the tool."},
        "next": next_steps,
        "judge": c.judge, "details": {k: v for k, v in c.details.items() if k not in ("cascade",)},
        "review": rv, "mode": mode,
        "has_proof": bool(c.details.get("proof_facts")),
    }
