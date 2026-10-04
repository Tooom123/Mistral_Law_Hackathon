"""Precedents from the Judilibre API (Cour de cassation open data, PISTE). Only retrieved decisions are shown —
never a decision recalled by a model. Without JUDILIBRE_KEY_ID: nothing, and the UI says why."""

from __future__ import annotations

import hashlib
import json
import logging

import httpx

from casebreak.config import CACHE, settings

log = logging.getLogger(__name__)


def search(query: str, chamber: str = "cr", size: int = 5) -> dict:
    if not query:
        return {"status": "no_query", "results": []}
    if not settings.judilibre:
        return {"status": "unavailable", "reason": "No JUDILIBRE_KEY_ID: no precedent retrieved.",
                "results": [], "query": query}
    key = hashlib.sha256(f"{query}|{chamber}|{size}".encode()).hexdigest()[:16]
    cache = CACHE / f"judilibre_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        r = httpx.get(f"{settings.judilibre_base}/search", timeout=20,
                      params={"query": query, "chamber": chamber, "page_size": size, "resolve_references": "true"},
                      headers={"KeyId": settings.judilibre_key, "accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Judilibre failed: %s", e)
        return {"status": "error", "reason": f"Judilibre unreachable ({type(e).__name__}).", "results": [], "query": query}
    results = []
    for d in data.get("results", [])[:size]:
        hl = d.get("highlights") or {}
        snippet = " … ".join(sum((v for v in hl.values() if isinstance(v, list)), []))[:400] or d.get("summary", "")[:400]
        results.append({
            "id": d.get("id"), "date": d.get("decision_date"), "number": d.get("number"),
            "chamber": d.get("chamber"), "solution": d.get("solution"), "publication": d.get("publication"),
            "snippet": snippet, "url": f"https://www.courdecassation.fr/decision/{d.get('id')}",
        })
    out = {"status": "ok", "query": query, "total": data.get("total"), "results": results,
           "corpus": "Judilibre — Cour de cassation, criminal chamber", "retrieved": True}
    cache.write_text(json.dumps(out, ensure_ascii=False))
    return out
