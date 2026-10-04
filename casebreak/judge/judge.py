"""Tiered judge: offline heuristics → Jev (TypeSafe AI) → Mistral Small → Mistral Large (explanations, counter-arguments).

Every answer carries a quote; quotes are verified on the page by code. No probability is ever shown in the UI.
"""

from __future__ import annotations

import logging
import re

import httpx

from casebreak.config import settings
from casebreak.judge.questions import PROSECUTION, QUESTIONS
from casebreak.llm import mistral
from casebreak.privacy import pseudonymize
from casebreak.schemas import Node, Nullity, PageRec, Src
from casebreak.text import norm, quote_on_page_loose

log = logging.getLogger(__name__)

OBJECTIVE_MARKERS = ["unique moyen", "empecher", "concerte", "garantir", "presentation", "pressions", "preserver",
                     "mettre fin", "investigations impliquant"]
DELAY_MARKERS = ["ebriete", "ivresse", "soins", "hopital", "transport", "violence", "agitation", "interprete"]


def _excerpt(sources: list[Src], pages: dict[int, PageRec]) -> str:
    seen, parts = set(), []
    for s in sources:
        if s.page in pages and s.page not in seen:
            seen.add(s.page)
            parts.append(f"[page {s.page}]\n{pages[s.page].text[:3500]}")
    return "\n\n".join(parts)


def _offline(qid: str, node: Node, attr: str | None) -> dict:
    a = node.attr(attr) if attr else None
    text = norm(str(a.value)) if a and a.value else ""
    if qid == "objective_stated":
        if not text:
            return {"id": qid, "answer": "not_documented", "quote": a.src.quote if a and a.src else None,
                    "page": a.src.page if a and a.src else None}
        ok = any(m in text for m in OBJECTIVE_MARKERS)
        return {"id": qid, "answer": ok, "quote": a.src.quote if a.src else None, "page": a.src.page if a.src else None}
    if qid == "delay_justified":
        if not text:
            return {"id": qid, "answer": "none", "quote": None, "page": None}
        return {"id": qid, "answer": "circumstance_stated", "quote": a.src.quote if a.src else None,
                "page": a.src.page if a.src else None,
                "markers": [m for m in DELAY_MARKERS if m in text]}
    return {"id": qid, "answer": "not_documented", "quote": None, "page": None}


def _jev(qids: list[str], context: str) -> list[dict] | None:
    """Tier 1 — Jev typed questions. TODO: align payload with the Jev API docs once access is confirmed."""
    if not settings.jev:
        return None
    payload = {"questions": [{"id": q, "type": QUESTIONS[q]["type"], "options": QUESTIONS[q].get("options"),
                              "text": QUESTIONS[q]["text"]} for q in qids], "context": context, "require_quotes": True}
    try:
        r = httpx.post(f"{settings.jev_base}/v1/judge", json=payload, timeout=30,
                       headers={"Authorization": f"Bearer {settings.typesafe_key}"})
        r.raise_for_status()
        return r.json().get("answers")
    except (httpx.HTTPError, ValueError) as e:
        log.info("Jev unavailable, falling back to Mistral: %s", e)
        return None


def _mistral(qids: list[str], context: str, model: str) -> list[dict] | None:
    if not settings.mistral:
        return None
    qs = "\n".join(f"- {q} ({QUESTIONS[q]['type']}{', options: ' + str(QUESTIONS[q].get('options')) if QUESTIONS[q].get('options') else ''}): {QUESTIONS[q]['text']}" for q in qids)
    try:
        out = mistral.chat_json(
            "You answer FACTUAL questions about documents of a French criminal case file. You never say whether an act "
            "is void or lawful. Every answer quotes a passage copied word for word, with its page. If you do not know, "
            "answer 'not_documented'. JSON: {\"answers\": [{\"id\": str, \"answer\": bool|str, \"quote\": str|null, "
            "\"page\": int|null, \"unsure\": bool}]}",
            f"Questions:\n{qs}\n\nDocuments:\n{context}", model=model)
        return out.get("answers")
    except mistral.MistralUnavailable as e:
        log.info("Mistral judge unavailable: %s", e)
        return None


def _verify(answers: list[dict], pages: dict[int, PageRec], mapping: dict) -> list[dict]:
    for a in answers:
        q = a.get("quote")
        if q and mapping:
            q = pseudonymize.unmask(q, mapping)
            a["quote"] = q
        page = a.get("page")
        a["verified"] = bool(q and page in pages and quote_on_page_loose(q, pages[page].text)) or \
            bool(q and any(quote_on_page_loose(q, p.text) for p in pages.values() if page is None))
        if q and not a["verified"]:
            a["note"] = "quote not found on the page — answer discarded"
    return answers


def ask(nullity: Nullity, node: Node, grey_attr: str | None, sources: list[Src], pages: dict[int, PageRec]) -> dict:
    version = nullity.versions[-1]
    qids = [q for q in ((version.grey_zone or {}).get("judge_questions") or []) if q in QUESTIONS]
    if not qids:
        return {}
    context = _excerpt(sources, pages)
    masked, mapping = pseudonymize.mask(context) if settings.pseudonymize else (context, {})
    tier, answers = "offline", None
    answers = _jev(qids, masked)
    if answers:
        tier = "jev"
    else:
        answers = _mistral(qids, masked, settings.fast_model)
        tier = "mistral-small" if answers else "offline"
    if answers:
        answers = _verify(answers, pages, mapping)
        if any(a.get("unsure") or not a.get("verified") for a in answers):
            big = _mistral(qids, masked, settings.judge_model)
            if big:
                answers, tier = _verify(big, pages, mapping), "mistral-large"
    if not answers:
        answers = [_offline(q, node, grey_attr) for q in qids]
        for a in answers:
            a["verified"] = bool(a.get("quote"))
    for a in answers:
        a["question"] = QUESTIONS.get(a.get("id", ""), {}).get("text", "")
        a.pop("probability", None)  # never displayed (ARCHITECTURE §3.3)
    unsure = any(a.get("unsure") or not a.get("verified") or a.get("answer") == "not_documented" for a in answers)
    return {"tier": tier, "answers": answers, "unsure": unsure, "pseudonymized": bool(mapping),
            "calibrated": False, "note": "The judge answers on facts only, never on nullity or prejudice."}


def counter_arguments(nullity: Nullity, node: Node) -> list[dict]:
    """What the prosecution will answer (offline: catalogue hints + facts found in the file)."""
    out = []
    for h in nullity.prosecution_hints:
        if h in PROSECUTION:
            out.append({"hint": h, "text": PROSECUTION[h]})
    if not any(o["hint"] == "no_prejudice" for o in out):
        out.append({"hint": "no_prejudice", "text": PROSECUTION["no_prejudice"]})
    return out


def explain(statement: str, nullity: Nullity) -> str:
    """Tier 2 explanation (Mistral Large) — offline returns the factual statement only."""
    if not settings.mistral:
        return statement
    try:
        return mistral.chat(
            [{"role": "system", "content": "Rephrase in 2 sentences of sober legal English, without concluding that the act is void."},
             {"role": "user", "content": f"Rule: {nullity.title} ({nullity.article}). Finding: {statement}"}],
            model=settings.judge_model)
    except mistral.MistralUnavailable:
        return statement


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
