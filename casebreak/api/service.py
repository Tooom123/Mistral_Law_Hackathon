"""Case service used by the API: loading, caching, as-of re-runs, reviews."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

from casebreak.config import CASES
from casebreak.graph import store
from casebreak.nullities.engine import run_checks
from casebreak.output.alerts import card, review_key
from casebreak.schemas import CaseGraph, Check

_CACHE: dict[str, tuple[float, CaseGraph, list[Check]]] = {}
_ASOF: dict[tuple[str, str], list[Check]] = {}
_LOCK = threading.Lock()
DEMO_ID = "demo-mathurins"


def new_case_id() -> str:
    return datetime.now().strftime("c%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def case_path(cid: str) -> Path:
    p = (CASES / cid).resolve()
    if CASES.resolve() not in p.parents:
        raise KeyError(cid)
    return p


def exists(cid: str) -> bool:
    try:
        return (case_path(cid) / "graph.json").exists()
    except KeyError:
        return False


def load(cid: str) -> tuple[CaseGraph, list[Check]]:
    p = case_path(cid) / "graph.json"
    if not p.exists():
        raise KeyError(cid)
    mtime = p.stat().st_mtime
    with _LOCK:
        hit = _CACHE.get(cid)
        if hit and hit[0] == mtime:
            return hit[1], hit[2]
    g, checks = store.load(case_path(cid))
    with _LOCK:
        _CACHE[cid] = (mtime, g, checks)
        for k in [k for k in _ASOF if k[0] == cid]:
            del _ASOF[k]
    return g, checks


def checks_as_of(cid: str, as_of: str | None) -> list[Check]:
    g, checks = load(cid)
    if not as_of:
        return checks
    key = (cid, as_of)
    with _LOCK:
        if key in _ASOF:
            return _ASOF[key]
    out = run_checks(g, as_of=date.fromisoformat(as_of))
    with _LOCK:
        _ASOF[key] = out
    return out


def alerts(checks: list[Check]) -> list[Check]:
    return sorted([c for c in checks if c.rank > 0], key=lambda c: -c.rank)


def reviews(cid: str) -> dict:
    p = case_path(cid) / "reviews.json"
    return json.loads(p.read_text()) if p.exists() else {}


def set_review(cid: str, c: Check, decision: str, note: str) -> dict:
    r = reviews(cid)
    r[review_key(c)] = {"decision": decision, "note": note, "at": datetime.now().isoformat(timespec="seconds"),
                        "nullity_id": c.nullity_id, "node_id": c.node_id}
    (case_path(cid) / "reviews.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    return r[review_key(c)]


def find_alert(cid: str, aid: str, as_of: str | None = None) -> Check:
    for c in checks_as_of(cid, as_of):
        if c.id == aid or review_key(c) == aid:
            return c
    raise KeyError(aid)


def cards(cid: str, as_of: str | None, mode: str, pseudo: bool) -> list[dict]:
    g, _ = load(cid)
    rv = reviews(cid)
    return [card(c, g, rv, mode, pseudo) for c in alerts(checks_as_of(cid, as_of))]


def list_cases() -> list[dict]:
    out = []
    for d in sorted(CASES.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        st = d / "status.json"
        if not d.is_dir() or not st.exists():
            continue
        s = json.loads(st.read_text())
        out.append({"case_id": d.name, "title": s.get("title"), "state": s.get("state"),
                    "pages": s.get("counters", {}).get("pages"), "alerts": s.get("counters", {}).get("alerts")})
    return out


def delete(cid: str) -> None:
    shutil.rmtree(case_path(cid), ignore_errors=True)
    with _LOCK:
        _CACHE.pop(cid, None)
