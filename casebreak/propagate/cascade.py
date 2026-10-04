"""Propagation — what falls with it (ARCHITECTURE §4, art. 174 CPP logic: acts potentially affected).

Walks SUPPORTS edges from a node. The UI says "potentially affected" — the necessary-support
question is for the judge.
"""

from __future__ import annotations

from collections import deque

from casebreak.schemas import Edge, Node


def affected(start: str, edges: list[Edge], nodes: dict[str, Node] | None = None) -> dict[str, dict]:
    """BFS over SUPPORTS. Returns {node_id: {depth, via, origin, parent}} (start excluded)."""
    out_edges: dict[str, list[Edge]] = {}
    for e in edges:
        if e.kind == "SUPPORTS":
            out_edges.setdefault(e.src, []).append(e)
    seen: dict[str, dict] = {}
    q = deque([(start, 0, "structural")])
    while q:
        cur, depth, origin = q.popleft()
        for e in out_edges.get(cur, []):
            if e.dst == start or e.dst in seen:
                continue
            if nodes is not None and (e.dst not in nodes or nodes[e.dst].type != "ACT"):
                continue
            o = "llm_inferred" if "llm_inferred" in (origin, e.origin) else (e.origin if depth == 0 else origin)
            seen[e.dst] = {"depth": depth + 1, "via": e.label, "origin": o, "parent": cur}
            q.append((e.dst, depth + 1, o))
    return seen


def simulate(node_id: str, nodes: list[Node], edges: list[Edge]) -> dict:
    """Remove the node and list what loses its support, in BFS order (for the stop-motion animation)."""
    idx = {n.id: n for n in nodes}
    aff = affected(node_id, edges, idx)
    order = sorted(aff.items(), key=lambda kv: (kv[1]["depth"], idx[kv[0]].start.isoformat() if idx[kv[0]].start else ""))
    return {
        "removed": node_id,
        "count": len(aff),
        "affected": [{"id": k, "label": idx[k].label, "category": idx[k].category, "depth": v["depth"], "via": v["via"],
                      "origin": v["origin"], "parent": v["parent"], "doc_ids": idx[k].doc_ids,
                      "start": idx[k].start.isoformat() if idx[k].start else None} for k, v in order],
        "waves": max((v["depth"] for v in aff.values()), default=0),
    }
