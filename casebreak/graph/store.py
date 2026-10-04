"""Case storage: SQLite tables nodes/edges (+ a JSON snapshot) and NetworkX in memory (ARCHITECTURE §2)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import networkx as nx

from casebreak.schemas import CaseGraph, Check


def save(case_dir: Path, g: CaseGraph, checks: list[Check]) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "graph.json").write_text(g.model_dump_json())
    (case_dir / "checks.json").write_text(json.dumps([c.model_dump(mode="json") for c in checks], ensure_ascii=False))
    db = case_dir / "graph.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE nodes (id TEXT PRIMARY KEY, type TEXT, category TEXT, subtype TEXT, label TEXT,
                            start TEXT, end_ TEXT, framework TEXT, person TEXT, json TEXT);
        CREATE TABLE edges (src TEXT, dst TEXT, kind TEXT, origin TEXT, label TEXT, json TEXT);
        CREATE TABLE checks (nullity_id TEXT, node_id TEXT, status TEXT, certainty TEXT, rank REAL, json TEXT);
        CREATE INDEX edges_src ON edges(src); CREATE INDEX edges_dst ON edges(dst);
    """)
    con.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (n.id, n.type, n.category, n.subtype, n.label, n.start.isoformat() if n.start else None,
         n.end.isoformat() if n.end else None, n.framework, n.person, n.model_dump_json()) for n in g.nodes])
    con.executemany("INSERT INTO edges VALUES (?,?,?,?,?,?)", [
        (e.src, e.dst, e.kind, e.origin, e.label, e.model_dump_json()) for e in g.edges])
    con.executemany("INSERT INTO checks VALUES (?,?,?,?,?,?)", [
        (c.nullity_id, c.node_id, c.status, c.certainty, c.rank, c.model_dump_json()) for c in checks])
    con.commit()
    con.close()


def load(case_dir: Path) -> tuple[CaseGraph, list[Check]]:
    g = CaseGraph.model_validate_json((case_dir / "graph.json").read_text())
    raw = json.loads((case_dir / "checks.json").read_text()) if (case_dir / "checks.json").exists() else []
    return g, [Check(**c) for c in raw]


def to_nx(g: CaseGraph) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    for n in g.nodes:
        G.add_node(n.id, type=n.type, category=n.category, subtype=n.subtype, label=n.label)
    for e in g.edges:
        G.add_edge(e.src, e.dst, kind=e.kind, origin=e.origin)
    return G
