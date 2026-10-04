"""Facts → flags → precedents → timeline. One JSON document the front end renders as is."""

from __future__ import annotations

import logging
import time
from datetime import date

from casebreak.coi import extract, precedents, rules
from casebreak.coi.casefile import CASES, LANES, CaseFile
from casebreak.config import settings

log = logging.getLogger(__name__)

SEVERITY = {"high": 3, "medium": 2, "low": 1}
CERTAINTY = {"documented": 3, "inferred": 2, "needs_reading": 1}
PRIORITY = ["COI-01", "COI-02", "COI-04", "COI-06", "COI-03", "COI-05"]  # narrative order within a severity


def _iso(x):
    return x.isoformat() if isinstance(x, date) else x


def run_audit(case_id: str = "mckinsey", llm: bool = False, case: CaseFile | None = None) -> dict:
    t0 = time.perf_counter()
    case = case or CASES[case_id]()
    facts = extract.read(case)
    ctx = rules.Ctx(facts)
    meta = rules.meta()

    found, cleared = [], []
    for det in rules.DETECTORS:
        f, c = det(ctx)
        found += f
        cleared += c
    f, _ = rules.statement_contradicted(ctx, found)
    found += f

    for fl in found:
        m = meta[fl["rule"]]
        fl.update(title=m["title"], pattern=m["pattern"], patterns=m["patterns"], severity=m["severity"],
                  legal=m["legal"], next=m["next"], pattern_label=precedents.PATTERNS[m["pattern"]])
    found.sort(key=lambda x: (-SEVERITY[x["severity"]], -CERTAINTY[x["certainty"]], PRIORITY.index(x["rule"]),
                              x["window"][0]))
    for i, fl in enumerate(found, 1):
        fl["id"] = f"F{i}"
        fl["docs"] = sorted({e["doc"] for e in fl["evidence"]})
        signals = [e["label"] for e in fl["evidence"]] + fl["aggravating"]
        hits = precedents.search(meta[fl["rule"]]["query"] + " " + fl["headline"], fl["patterns"], k=8,
                                 signals=signals)
        top = hits[:3]
        if hits and not any(h["provenance"] == "public_record" for h in top):   # always anchor on a public case
            pub = next((h for h in hits if h["provenance"] == "public_record"), None)
            top = hits[:2] + [pub] if pub else top
        fl["precedents"] = [_slim(h) for h in top]
        fl["note"] = _note(fl, case) if llm else None

    docs = _documents(case, found)
    out = {
        "case": {"id": case.id, "title": case.title, "subtitle": case.subtitle, "jurisdiction": case.jurisdiction},
        "lanes": LANES,
        "documents": docs,
        "context": case.context,
        "periods": _periods(ctx, facts, found),
        "flags": found,
        "cleared": cleared,
        "entities": _entities(facts, found),
        "stats": {},
        "engine": {"extraction": "line readers",
                   "precedents": precedents.stats()["engine"],
                   "notes": "mistral" if llm and settings.mistral else "rules"},
    }
    n_facts = sum(len(x) for x in (facts.assignments, facts.time_entries, facts.employment, facts.authorship,
                                   facts.recommendations, facts.decisions, facts.relatives, facts.statements)) \
        + len(facts.engagements) + len(facts.declarations) + len(facts.orders) + len(facts.ownership) \
        + len(facts.requirements) + len(facts.attestations)
    out["stats"] = {
        "documents": len(case.docs), "pages": sum(len(d.pages) for d in case.docs),
        "facts": n_facts, "people": len(facts.people), "companies": len(facts.companies),
        "cross_references": sum(len(f["evidence"]) for f in found),
        "flags": len(found), "high": sum(f["severity"] == "high" for f in found),
        "medium": sum(f["severity"] == "medium" for f in found), "cleared": len(cleared),
        "rules": len(meta), "precedents": precedents.stats()["total"],
        "ms": round((time.perf_counter() - t0) * 1000),
    }
    return out


def _slim(h: dict) -> dict:
    keep = ("id", "title", "citation", "forum", "jurisdiction", "year", "kind", "provenance", "outcome", "lesson",
            "patterns", "score", "why")
    return {k: h[k] for k in keep}


def _documents(case: CaseFile, flags: list[dict]) -> list[dict]:
    out = []
    for d in case.docs:
        pages = []
        for n, text in enumerate(d.pages, 1):
            marks = []
            for fl in flags:
                for e in fl["evidence"]:
                    if e["doc"] == d.id and e["page"] == n:
                        marks.append({"start": e["start"], "end": e["end"], "flag": fl["id"], "role": e["role"],
                                      "label": e["label"], "severity": fl["severity"]})
            pages.append({"n": n, "text": text, "marks": sorted(marks, key=lambda m: (m["start"], -m["end"]))})
        touched = sorted({fl["id"] for fl in flags for e in fl["evidence"] if e["doc"] == d.id},
                         key=lambda x: int(x[1:]))
        out.append({"id": d.id, "date": d.date, "precision": d.precision, "lane": d.lane, "kind": d.kind,
                    "title": d.title, "issuer": d.issuer, "provenance": d.provenance, "notice": d.notice,
                    "tags": d.tags, "pages": pages, "flags": touched,
                    "severity": max((fl["severity"] for fl in flags if fl["id"] in touched),
                                    key=lambda s: SEVERITY[s], default=None)})
    return out


def _periods(ctx: rules.Ctx, facts: extract.Facts, flags: list[dict]) -> list[dict]:
    """Bars for the people lanes: engagements, employment, and the revolving-door window."""
    people = {p for f in flags if f["rule"] in ("COI-01", "COI-02", "COI-04", "COI-05") for p in f["persons"]}

    def cited(src) -> list[str]:
        return [f["id"] for f in flags
                if any(e["doc"] == src.doc and e["page"] == src.page and e["start"] == src.start for e in f["evidence"])]

    out = []
    for a in facts.assignments:
        if a["person"] in people:
            eng = facts.engagements.get(a["engagement"], {})
            out.append({"person": a["person"], "label": f"{eng.get('client', a['engagement'])} · {a['alloc']} %",
                        "kind": "public" if a["engagement"] in ctx.public else "private",
                        "start": _iso(a["start"]), "end": _iso(a["end"]), "doc": a["src"].doc,
                        "flags": [x for x in cited(a["src"]) if x not in _rule_ids(flags, "COI-03", "COI-06")]})
    for e in facts.employment:
        if e["person"] in people:
            out.append({"person": e["person"], "label": e["org"], "kind": "employment", "start": _iso(e["start"]),
                        "end": _iso(e["end"]), "doc": e["src"].doc, "flags": cited(e["src"])})
    for f in flags:
        if f["rule"] == "COI-04":
            out.append({"person": f["persons"][0], "label": "within 3 years of leaving the firm", "kind": "window",
                        "start": f["window"][0], "end": f["window"][1], "doc": None, "flags": [f["id"]]})
    order = {p: i for i, p in enumerate(dict.fromkeys(p for f in flags for p in f["persons"]))}
    out.sort(key=lambda p: (order.get(p["person"], 99), p["start"]))
    return out


def _rule_ids(flags: list[dict], *rule_ids: str) -> set[str]:
    return {f["id"] for f in flags if f["rule"] in rule_ids}


def _entities(facts: extract.Facts, flags: list[dict]) -> dict:
    roles: dict[str, set] = {}
    for a in facts.assignments:
        roles.setdefault(a["person"], set()).add(a["role"])
    for o in facts.orders.values():
        if o.get("signer"):
            roles.setdefault(o["signer"], set()).add(o.get("signer_role", "signatory"))
    people = [{"name": n, "roles": sorted(roles.get(n, [])), "mentions": len(v["mentions"]),
               "docs": sorted({s.doc for s in v["mentions"]}),
               "flags": [f["id"] for f in flags if n in f["persons"]]} for n, v in facts.people.items()]
    companies = [{"name": n, "mentions": len(v["mentions"]), "docs": sorted({s.doc for s in v["mentions"]}),
                  "flags": [f["id"] for f in flags if n in f["companies"]]} for n, v in facts.companies.items()]
    people.sort(key=lambda p: (-len(p["flags"]), p["name"]))
    companies.sort(key=lambda c: (-len(c["flags"]), c["name"]))
    return {"people": people, "companies": companies}


# ------------------------------------------------------------------ reviewer note (Mistral, optional)

NOTE_SYSTEM = """You assist a lawyer reviewing a case file for conflicts of interest.
You receive one flag raised by deterministic rules, with its evidence quotes and similar precedents.
Write a short reviewer note in English: 2–3 sentences on why this deserves a look and what to read first.
Rules: use only the facts in the evidence; never state that a conflict of interest exists — say "potential";
cite evidence by quoting it exactly inside « ». Answer JSON: {"note": "...", "quotes": ["exact quote", ...]}"""


def _note(fl: dict, case: CaseFile) -> dict | None:
    if not settings.mistral:
        return None
    from casebreak.llm import mistral

    ev = "\n".join(f"- [{e['doc']} p.{e['page']}] ({e['role']}) {e['quote']}" for e in fl["evidence"])
    pr = "\n".join(f"- {p['citation']}: {p['lesson']}" for p in fl["precedents"])
    try:
        out = mistral.chat_json(NOTE_SYSTEM, f"Flag: {fl['title']}\n{fl['summary']}\n\nEvidence:\n{ev}\n\nPrecedents:\n{pr}",
                                model=settings.judge_model, purpose="coi_note")
    except Exception as e:  # noqa: BLE001 — the note is optional
        log.warning("reviewer note unavailable: %s", e)
        return None
    allq = " ".join(e["quote"] for e in fl["evidence"])
    quotes = [q for q in out.get("quotes", []) if isinstance(q, str) and q and q in allq]
    if not out.get("note"):
        return None
    return {"text": out["note"], "quotes": quotes, "model": out.get("_model"),
            "verified": len(quotes) == len(out.get("quotes", []))}


# ------------------------------------------------------------------ review memo


def memo(audit: dict, fid: str) -> str:
    fl = next((f for f in audit["flags"] if f["id"] == fid), None)
    if not fl:
        raise KeyError(fid)
    titles = {d["id"]: d["title"] for d in audit["documents"]}
    out = [f"# {fl['id']} — {fl['title']}", "",
           f"**{fl['headline']}**  ", f"Severity: {fl['severity']} · certainty: {fl['certainty'].replace('_', ' ')} · "
           f"pattern: {fl['pattern_label']}", "", fl["summary"], ""]
    if fl["aggravating"]:
        out += ["## Aggravating elements", *[f"- {a}" for a in fl["aggravating"]], ""]
    out += ["## Where to look", ""]
    for e in fl["evidence"]:
        out.append(f"- **{e['doc']} p.{e['page']}** — {titles.get(e['doc'], '')} · _{e['role']}_  \n  > {e['quote']}")
    out += ["", "## Framework", *[f"- **{x['ref']}** — {x['text']}" for x in fl["legal"]], "",
            "## Comparable cases", *[f"- **{p['citation']}** ({p['jurisdiction']}, {p['year']}"
                                     f"{', simulated' if p['provenance'] == 'synthetic' else ''}) — {p['lesson']}"
                                     for p in fl["precedents"]], "",
            "## Next steps", *[f"- [ ] {x}" for x in fl["next"]], "",
            "_Potential conflict of interest, to review. The legal qualification belongs to the reviewing lawyer._"]
    return "\n".join(out)
