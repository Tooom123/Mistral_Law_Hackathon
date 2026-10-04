"""Adversarial tribunal on each alert (ARCHITECTURE §10, moonshot 1).

The defence argues from the check (statement, pages, cascade). The prosecution objects: for each objection it looks
for a piece of the file that supports it (justification, waiver, authorization, purge, deadline…).
The presiding judge rules on what survives, with quotes — never on nullity or grief.

Offline: deterministic agents over the graph. With a Mistral key: the three agents write their own text,
but objections only count when their quote is found on a page of the file.
"""

from __future__ import annotations

import logging

from casebreak.config import settings
from casebreak.deadlines.clock import deadlines
from casebreak.judge.questions import PROSECUTION
from casebreak.llm import mistral
from casebreak.nullities.versions import load_catalogue
from casebreak.privacy import pseudonymize
from casebreak.schemas import CaseGraph, Check, Node, Src
from casebreak.text import norm, quote_on_page_loose

log = logging.getLogger(__name__)

# Which attribute of which node, if present, gives the prosecution a quote from the file.
EVIDENCE = {
    "delay_justified_claim": [("self", "delay_justification")],
    "waiver": [("self", "lawyer_waiver")],
    "prosecutor_authorisation": [("self", "prosecutor_authorization")],
    "extension": [("custody", "extension_authorized")],
    "special_regime": [("custody", "special_regime")],
    "jld_authorisation": [("self", "jld_authorization")],
    "consent": [("self", "consent")],
}
# Keywords looked for in OTHER pieces of the file (piece "hors cote" arguments).
SEARCH = {
    "notice_elsewhere": ["procureur", "avisons"],
    "document_outside_file": ["certificat", "autorisation"],
    "entry_elsewhere": ["fin de la garde", "heure de fin"],
    "later_seal": ["scelle n"],
    "renotification": ["renotif", "notifions a nouveau"],
}


def _node_for(g: CaseGraph, c: Check) -> Node | None:
    return next((n for n in g.nodes if n.id == c.node_id), None)


def _custody(g: CaseGraph, n: Node) -> Node | None:
    if n.subtype == "garde_a_vue":
        return n
    return next((x for x in g.nodes if x.subtype == "garde_a_vue" and x.person == n.person), None)


def _objection(hint: str, c: Check, n: Node, g: CaseGraph, pages: dict) -> dict:
    text = PROSECUTION.get(hint, hint)
    for where, attr in EVIDENCE.get(hint, []):
        target = n if where == "self" else _custody(g, n)
        a = target.attr(attr) if target else None
        if a and a.src and a.value not in (None, False, "verbal"):
            return {"hint": hint, "text": text, "strength": "supported", "source": a.src.model_dump(),
                    "why": "Backed by a document in the file."}
    if hint in SEARCH:
        own = {s.page for s in c.sources}
        for kw in SEARCH[hint]:
            for p in pages.values():
                if p.page in own:
                    continue
                t = norm(p.text)
                if kw in t and (n.person is None or norm(n.person.split(":")[-1].split("_")[0]) in t):
                    i = t.index(kw)
                    line = p.text[max(0, p.text.rfind("\n", 0, i) + 1): (p.text.find("\n", i) if p.text.find("\n", i) > 0 else len(p.text))]
                    return {"hint": hint, "text": text, "strength": "to_verify",
                            "source": Src(doc_id="?", page=p.page, quote=line.strip()[:200]).model_dump(),
                            "why": "Possibly relevant entry elsewhere in the file: to read."}
    if hint == "no_prejudice":
        return {"hint": hint, "text": text, "strength": "principle", "source": None,
                "why": "A question of law for the lawyer and the judge — never decided by the tool."}
    return {"hint": hint, "text": text, "strength": "no_evidence", "source": None,
            "why": "Possible argument, but no document in the file backs it."}


def _procedural(g: CaseGraph, c: Check) -> list[dict]:
    out = []
    ruling = next((n for n in g.nodes if n.subtype == "chamber_ruling"), None)
    if ruling and ruling.attr("date") and ruling.attr("date").src:
        out.append({"hint": "purge", "text": "Defects predating the investigating chamber ruling are purged "
                    "(art. 174 CPP).", "strength": "supported", "source": ruling.attr("date").src.model_dump(),
                    "why": "Ruling present in the file."})
    dl = deadlines(g)
    for a in dl["anchors"]:
        if all(r["days_left"] < 0 for r in a["regimes"]):
            out.append({"hint": "time_bar", "text": "The request is out of time (time bar).", "strength": "supported",
                        "source": a["source"], "why": f"Deadlines expired under both regimes since the formal charge of {a['anchor']}."})
        elif any(r["days_left"] < 0 for r in a["regimes"]):
            out.append({"hint": "time_bar", "text": "The request may be out of time depending on the applicable regime.",
                        "strength": "to_verify", "source": a["source"], "why": "Entry into force of law 2026-651 to be checked."})
    return out


def _offline(c: Check, g: CaseGraph) -> dict:
    cat = load_catalogue()
    nl = cat.get(c.nullity_id)
    n = _node_for(g, c)
    pages = {p.page: p for p in g.pages}
    idx = {x.id: x for x in g.nodes}
    pg = ", ".join(f"p. {s.page}" for s in c.sources)
    aff = [idx[a] for a in c.affected if a in idx]
    aff_txt = "; ".join(f"{x.label} ({', '.join(x.doc_ids)})" for x in aff[:6])
    defense = (f"{c.statement_fr} This finding rests on the very text of the proceedings ({pg}). "
               f"Rule relied on: {c.article} — {c.law_version}. "
               + (f"{len(aff)} act(s) are potentially affected and should be named in the request: {aff_txt}."
                  if aff else "No dependent act identified in the graph."))
    objections = [_objection(h, c, n, g, pages) for h in (nl.prosecution_hints if nl else [])] if n else []
    if not any(o["hint"] == "no_prejudice" for o in objections):
        objections.append(_objection("no_prejudice", c, n, g, pages) if n else
                          {"hint": "no_prejudice", "text": PROSECUTION["no_prejudice"], "strength": "principle", "source": None, "why": ""})
    objections += _procedural(g, c)
    strong = [o for o in objections if o["strength"] == "supported"]
    check = [o for o in objections if o["strength"] == "to_verify"]
    if strong:
        verdict, label = "weakened", "Ground weakened"
        motive = "The prosecution produces a document from the file: " + "; ".join(
            f"\"{o['source']['quote'][:120]}\" (p. {o['source']['page']})" for o in strong if o.get("source"))
    elif c.status == "needs_reading":
        verdict, label = "to_investigate", "To investigate"
        motive = "The finding depends on a human reading of the page (unreadable, missing or contradictory)."
    elif check:
        verdict, label = "survives_with_caveats", "Survives — points to check"
        motive = "No objection is backed by a document; entries elsewhere in the file should be read."
    else:
        verdict, label = "survives", "The ground survives cross-examination"
        motive = "No prosecution objection is backed by a document in the file."
    motive += " Prejudice is still for the defence to prove; the tool rules on neither prejudice nor nullity."
    return {"tier": "offline", "defense": {"role": "Defence", "text": defense, "sources": [s.model_dump() for s in c.sources]},
            "prosecution": {"role": "Prosecution", "objections": objections},
            "presiding": {"role": "Presiding judge", "verdict": verdict, "label": label, "text": motive}}


def deliberate(c: Check, g: CaseGraph) -> dict:
    base = _offline(c, g)
    if not settings.mistral:
        return base
    pages = {p.page: p for p in g.pages}
    excerpt = "\n\n".join(f"[page {s.page}]\n{pages[s.page].text[:2500]}" for s in c.sources if s.page in pages)
    masked, mapping = pseudonymize.mask(excerpt) if settings.pseudonymize else (excerpt, {})
    try:
        out = mistral.chat_json(
            "You simulate an adversarial debate on a possible nullity ground in French criminal procedure. Answer in English. "
            "Defence, then prosecution (objections, each with an exact quote from the file or null), then the presiding judge. "
            "The presiding judge NEVER concludes on nullity or prejudice: they say whether the ground survives cross-examination. "
            "Do not invent any article or decision. JSON: {\"defense\": str, \"objections\": [{\"text\": str, "
            "\"quote\": str|null, \"page\": int|null}], \"president\": str}",
            f"Finding: {c.statement_fr}\nRule: {c.article} ({c.law_version})\nObjections already identified: "
            f"{[o['text'] for o in base['prosecution']['objections']]}\n\nDocuments:\n{masked}", model=settings.judge_model)
    except mistral.MistralUnavailable:
        return base
    llm_obj = []
    for o in out.get("objections", [])[:6]:
        q = pseudonymize.unmask(o.get("quote") or "", mapping) if mapping else (o.get("quote") or "")
        page = o.get("page")
        ok = bool(q and page in pages and quote_on_page_loose(q, pages[page].text))
        llm_obj.append({"hint": "llm", "text": pseudonymize.unmask(o.get("text", ""), mapping),
                        "strength": "supported" if ok else "no_evidence",
                        "source": {"doc_id": "?", "page": page, "quote": q} if ok else None,
                        "why": "Quote verified on the page." if ok else "No verified quote: argument not counted as backed."})
    base["tier"] = "mistral"
    base["defense"]["text"] = pseudonymize.unmask(out.get("defense", base["defense"]["text"]), mapping)
    base["prosecution"]["objections"] += llm_obj
    base["presiding"]["llm_text"] = pseudonymize.unmask(out.get("president", ""), mapping)
    return base


def tribunal_summary(checks: list[Check], g: CaseGraph) -> dict:
    out = {}
    for c in checks:
        if c.rank > 0:
            out[c.id] = _offline(c, g)["presiding"]["verdict"]
    return out

