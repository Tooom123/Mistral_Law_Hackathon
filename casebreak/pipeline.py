"""Dossier → graph → checks. Emits live counters for the war room."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from casebreak.config import CASES, settings
from casebreak.graph import store
from casebreak.graph.extract import extract_piece
from casebreak.graph.link import build_graph
from casebreak.ingest.ocr import read_files
from casebreak.ingest.split import split_pieces
from casebreak.nullities.engine import run_checks
from casebreak.schemas import CaseGraph

log = logging.getLogger(__name__)

STAGES = [
    ("read", "Reading", "OCR and vision — every page keeps its position"),
    ("split", "Splitting", "One document per police report"),
    ("classify", "Classifying", "Document type → category"),
    ("extract", "Extracting", "Acts, times, people — with page and quote"),
    ("link", "Linking", "Order, dependencies, contradictions"),
    ("check", "Checking", "Conditions of the law in force on the date of the act"),
    ("cascade", "Domino effect", "Acts potentially affected"),
    ("done", "Ready", "Graph and alerts available"),
]

_STATUS: dict[str, dict] = {}
_LOCK = threading.Lock()


def case_dir(case_id: str) -> Path:
    return CASES / case_id


def status(case_id: str) -> dict:
    with _LOCK:
        if case_id in _STATUS:
            return json.loads(json.dumps(_STATUS[case_id], default=str))
    p = case_dir(case_id) / "status.json"
    return json.loads(p.read_text()) if p.exists() else {"case_id": case_id, "state": "unknown"}


def _new_status(case_id: str, title: str) -> dict:
    return {"case_id": case_id, "title": title, "state": "running", "stage": "read", "started_at": time.time(),
            "stages": {s: {"state": "pending", "label": l, "detail": d} for s, l, d in STAGES},
            "counters": {"pages": 0, "pages_native": 0, "pages_ocr": 0, "pages_unreadable": 0, "images": 0, "pieces": 0,
                         "acts": 0, "attributes": 0, "quotes_verified": 0, "edges": 0, "supports": 0, "contradictions": 0,
                         "checks": 0, "alerts": 0, "possible_nullity": 0, "needs_reading": 0, "documented": 0},
            "categories": {}, "log": [], "engines": settings.engines(), "error": None}


def _upd(case_id: str, **kw) -> None:
    with _LOCK:
        st = _STATUS[case_id]
        for k, v in kw.items():
            st[k] = v


def _stage(case_id: str, stage: str, state: str) -> None:
    with _LOCK:
        st = _STATUS[case_id]
        st["stages"][stage]["state"] = state
        if state == "running":
            st["stage"] = stage


def _log(case_id: str, msg: str, kind: str = "info") -> None:
    with _LOCK:
        st = _STATUS[case_id]
        st["log"].append({"t": round(time.time() - st["started_at"], 2), "msg": msg, "kind": kind})
        st["log"] = st["log"][-400:]


def _count(case_id: str, key: str, inc: int = 1) -> None:
    with _LOCK:
        _STATUS[case_id]["counters"][key] = _STATUS[case_id]["counters"].get(key, 0) + inc


def _persist(case_id: str) -> None:
    with _LOCK:
        (case_dir(case_id) / "status.json").write_text(json.dumps(_STATUS[case_id], default=str, ensure_ascii=False))


def run_case(case_id: str, files: list[str], title: str = "", pace: float = 0.0) -> CaseGraph:
    """Full pipeline. `pace` (seconds) slows the war-room log down for live demos; 0 in tests."""
    d = case_dir(case_id)
    with _LOCK:
        _STATUS[case_id] = _new_status(case_id, title or case_id)
    try:
        # ① READ
        _stage(case_id, "read", "running")

        def on_page(kind: str, info: dict) -> None:
            _count(case_id, "pages")
            if info["kind"] == "image":
                _count(case_id, "images")
            if info["ocr"] == "native":
                _count(case_id, "pages_native")
            elif info["ocr"] == "none":
                _count(case_id, "pages_unreadable")
                _log(case_id, f"p. {info['page']} · unreadable without OCR — to read", "warn")
            else:
                _count(case_id, "pages_ocr")
                _log(case_id, f"p. {info['page']} · {'photo' if info['kind'] == 'image' else 'scan'} read by "
                     f"{'Mistral OCR' if info['ocr'] == 'mistral_ocr' else 'Tesseract'}", "ocr")
            if pace:
                time.sleep(pace / 60)

        pages = read_files(d, files, on_page)
        _stage(case_id, "read", "done")

        # ② SPLIT ③ CLASSIFY
        _stage(case_id, "split", "running")
        pieces = split_pieces(pages)
        _stage(case_id, "split", "done")
        _stage(case_id, "classify", "running")
        cats: dict[str, int] = {}
        for pc in pieces:
            _count(case_id, "pieces")
            cats[pc.category] = cats.get(pc.category, 0) + 1
            _upd(case_id, categories=dict(cats))
            label = f"PV n° {pc.number}" if pc.number else pc.title
            _log(case_id, f"{pc.id} · p. {pc.pages[0]}{'–' + str(pc.pages[-1]) if len(pc.pages) > 1 else ''} · "
                 f"{label} → {pc.category}", "piece")
            if pace:
                time.sleep(pace / 10)
        _stage(case_id, "classify", "done")

        # ④ EXTRACT
        _stage(case_id, "extract", "running")
        page_idx = {p.page: p for p in pages}
        drafts = []
        for pc in pieces:
            ds = extract_piece(pc, page_idx)
            drafts += ds
            for dr in ds:
                _count(case_id, "acts")
                n_attr = sum(1 for k, a in dr.node.attrs.items() if not k.startswith("_") and a.status != "missing")
                _count(case_id, "attributes", n_attr)
                _count(case_id, "quotes_verified", sum(1 for a in dr.node.attrs.values() if a.src))
                if dr.node.start and dr.node.subtype not in ("other",):
                    _log(case_id, f"{dr.node.label} · {dr.node.start:%d/%m %H:%M} · {pc.id}", "act")
            if pace:
                time.sleep(pace / 16)
        _stage(case_id, "extract", "done")

        # ⑤ LINK
        _stage(case_id, "link", "running")
        nodes, edges = build_graph(pieces, drafts, page_idx)
        sup = sum(1 for e in edges if e.kind == "SUPPORTS")
        con = sum(1 for e in edges if e.kind == "CONTRADICTS")
        _upd(case_id, counters={**status(case_id)["counters"], "edges": len(edges), "supports": sup, "contradictions": con,
                                "acts": sum(1 for n in nodes if n.type == "ACT")})
        for e in edges:
            if e.kind == "CONTRADICTS":
                _log(case_id, f"contradiction · {e.label}", "contradiction")
        _stage(case_id, "link", "done")
        g = CaseGraph(case_id=case_id, title=title or case_id, pages=pages, pieces=pieces, nodes=nodes, edges=edges,
                      created_at=datetime.now())
        fw = [n.framework for n in nodes if n.type == "ACT" and n.framework != "unknown"]
        g.framework = max(set(fw), key=fw.count) if fw else "unknown"  # type: ignore[assignment]

        # ⑥ CHECK
        _stage(case_id, "check", "running")
        checks = run_checks(g)
        for c in sorted(checks, key=lambda c: -c.rank):
            _count(case_id, "checks")
            if c.status == "possible_nullity":
                _count(case_id, "possible_nullity")
                _log(case_id, f"⚠ {c.nullity_id} · {c.statement_fr[:110]}", "alert")
            elif c.status == "needs_reading":
                _count(case_id, "needs_reading")
            if c.rank > 0:
                _count(case_id, "alerts")
                if c.certainty == "documented":
                    _count(case_id, "documented")
            if pace and c.rank > 0:
                time.sleep(pace / 2.5)
        _stage(case_id, "check", "done")
        _stage(case_id, "cascade", "running")
        top = max(checks, key=lambda c: len(c.affected), default=None)
        if top and top.affected:
            _log(case_id, f"domino · {top.nullity_id} → {len(top.affected)} acts potentially affected", "cascade")
        _stage(case_id, "cascade", "done")

        g.stats = {**status(case_id)["counters"], "categories": cats}
        store.save(d, g, checks)
        _stage(case_id, "done", "done")
        _upd(case_id, state="done", stage="done", finished_at=time.time())
        _log(case_id, "Case file ready.", "done")
        return g
    except Exception as e:
        log.exception("pipeline failed")
        _upd(case_id, state="error", error=str(e))
        _log(case_id, f"Error: {e}", "error")
        raise
    finally:
        _persist(case_id)
