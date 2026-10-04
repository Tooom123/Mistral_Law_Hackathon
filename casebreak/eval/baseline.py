"""Baseline: the same dossier given to an LLM alone ("find the procedural defects"). Needs a Mistral key."""

from __future__ import annotations

import logging

from casebreak.config import settings
from casebreak.llm import mistral
from casebreak.nullities.versions import load_catalogue
from casebreak.privacy import pseudonymize
from casebreak.schemas import CaseGraph

log = logging.getLogger(__name__)
MAX_CHARS = 120_000


def run_baseline(g: CaseGraph, truth: dict) -> dict:
    if not settings.mistral:
        return {"status": "not_run", "reason": "No MISTRAL_API_KEY: the LLM-alone baseline was not run."}
    ids = sorted(k for k, v in load_catalogue().items() if v.versions[0].check != "info_only")
    text = "\n\n".join(f"[page {p.page}]\n{p.text}" for p in g.pages)[:MAX_CHARS]
    masked, _ = pseudonymize.mask(text) if settings.pseudonymize else (text, {})
    try:
        out = mistral.chat_json(
            "You are a French criminal defence lawyer. Find the possible procedural defects in this case file. Answer in JSON "
            "{\"findings\": [{\"nullity_id\": un de " + str(ids) + ", \"page\": int, \"why\": str}]}",
            masked, model=settings.judge_model)
    except mistral.MistralUnavailable as e:
        return {"status": "error", "reason": str(e)}
    found = out.get("findings", [])
    used, tp, page_ok = set(), 0, 0
    expected = [e for e in truth["entries"] if e["injected"]]
    for e in expected:
        pages = set(e["piece_pages"]) | set(e["pages"])
        hit = next((i for i, f in enumerate(found) if i not in used and f.get("nullity_id") == e["nullity_id"]), None)
        if hit is not None:
            used.add(hit)
            tp += 1
            page_ok += int(found[hit].get("page") in pages)
    return {"status": "ok", "model": settings.judge_model, "tp": tp, "fn": len(expected) - tp,
            "fp": len(found) - len(used), "page_ok": page_ok}
