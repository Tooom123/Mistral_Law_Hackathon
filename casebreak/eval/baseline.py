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
    """Same dossier, one prompt, no graph. Scored with the SAME rule as CASEBREAK (bench.match): same catalogue id
    AND a page of the faulty piece — otherwise the comparison would favour one side."""
    if not settings.mistral:
        return {"status": "not_run", "reason": "No MISTRAL_API_KEY: the LLM-alone baseline was not run."}
    cat = load_catalogue()
    ids = sorted(k for k, v in cat.items() if any(ver.outcomes for ver in v.versions))
    menu = "\n".join(f"- {k}: {cat[k].title} ({cat[k].article})" for k in ids)
    text = "\n\n".join(f"[page {p.page}]\n{p.text}" for p in g.pages)
    truncated = len(text) > MAX_CHARS
    text = text[:MAX_CHARS]
    masked = pseudonymize.mask(text)[0] if settings.pseudonymize else text
    try:
        out = mistral.chat_json(
            "You are a French criminal defence lawyer. Find the possible procedural defects in this case file. "
            "Use only these rule ids:\n" + menu + "\nAnswer in JSON {\"findings\": [{\"nullity_id\": str, "
            "\"page\": int, \"why\": str}]}. Give the page where the defect appears.",
            masked, model=settings.judge_model, purpose="baseline")
    except mistral.MistralUnavailable as e:
        return {"status": "error", "reason": str(e)}
    found = []
    for f in out.get("findings", []):
        if not isinstance(f, dict):
            continue
        try:
            page = int(f.get("page"))
        except (TypeError, ValueError):
            page = None
        found.append({"nullity_id": str(f.get("nullity_id", "")), "page": page})
    used, tp, lenient = set(), 0, 0
    expected = [e for e in truth["entries"] if e["injected"]]
    for e in expected:
        pages = set(e["piece_pages"]) | set(e["pages"])
        same_id = [i for i, f in enumerate(found) if i not in used and f["nullity_id"] == e["nullity_id"]]
        lenient += int(bool(same_id))
        hit = next((i for i in same_id if found[i]["page"] in pages), None)
        if hit is not None:
            used.add(hit)
            tp += 1
    return {"status": "ok", "model": out.get("_model", settings.judge_model), "tp": tp, "fn": len(expected) - tp,
            "fp": len(found) - len(used), "page_ok": tp, "id_only": lenient, "truncated": truncated}
