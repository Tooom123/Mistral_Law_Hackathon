"""Rule-driven extraction — ask Mistral only for what the rules needed and did not find.

The rules engine traces every attribute it had to read and found absent / unreadable (`run_checks(gaps=…)`).
For those gaps only, grouped by act, Mistral reads the act's own pages and answers with a value, a page and a
verbatim quote, guided by the attribute registry (nullities/attributes.yaml). Nothing here is specific to one
rule: a new rule that reads a new attribute gets it extracted as soon as the attribute is described.

Guards (ARCHITECTURE §2, §11):
- the quote must be found on the page, or the answer is dropped;
- times are parsed from the QUOTE by our French time parser, never taken from the model's value;
- filled attributes are `inferred`: an alert that relies on them is at most `inferred`, never `documented`;
- pages are pseudonymised before the call; derived attributes (computed by the graph) are never asked.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from casebreak.config import settings
from casebreak.facts.normalize_time import parse_date, parse_time
from casebreak.llm import mistral
from casebreak.nullities.versions import load_attributes
from casebreak.schemas import Attr, CaseGraph, Src
from casebreak.text import norm, quote_on_page_loose

log = logging.getLogger(__name__)
MAX_CALLS = 60  # bound the cost on very large files; the remaining gaps stay "needs reading"
MAX_PAGES = 4


TIME_KEYS = {"start", "custody_start", "notified_at", "arrest_time", "exam_at", "date", "lawyer_notified_at",
             "family_notified_at", "end_time"}


def _coerce(spec: dict, value, quote: str, node) -> tuple[object, bool]:
    """Value to store, or (None, False) if the answer cannot be trusted."""
    t = spec.get("type", "text")
    if t in ("datetime", "date"):
        qn = norm(quote).replace("premier", "un")
        from casebreak.nullities.engine import node_date

        d = parse_date(qn) or node_date(node)
        if t == "date":
            return (d.isoformat(), True) if d else (None, False)
        tm = parse_time(qn)
        if d is None or tm is None:
            return None, False
        return datetime.combine(d, tm).isoformat(), True
    if t == "bool":
        return (value, True) if isinstance(value, bool) else (None, False)
    if t == "enum":
        return (value, True) if value in spec.get("values", []) else (None, False)
    return (str(value) if value not in (None, "") else quote), True


def fill_gaps(g: CaseGraph, gaps: list[tuple[str, str]], log_cb=None) -> int:
    """Fill traced gaps in place on the graph nodes. Returns the number of attributes filled."""
    if not settings.mistral or not gaps:
        return 0
    from casebreak.privacy import pseudonymize

    registry = load_attributes()
    nodes = {n.id: n for n in g.nodes}
    pages = {p.page: p for p in g.pages}
    wanted: dict[str, set[str]] = defaultdict(set)
    for nid, key in gaps:
        spec = registry.get(key)
        n = nodes.get(nid)
        if spec is None or spec.get("derived") or n is None or not n.pages:
            continue
        a = n.attrs.get(key)
        if a is not None and a.value is not None and a.status not in ("missing", "unreadable"):
            continue
        wanted[nid].add(key)
    filled, calls = 0, 0
    for nid, keys in sorted(wanted.items()):
        if calls >= MAX_CALLS:
            log.info("rule-driven extraction: call budget reached, %d acts left", len(wanted) - calls)
            break
        n = nodes[nid]
        pg = [p for p in n.pages if p in pages][:MAX_PAGES]
        text = "\n\n".join(f"[page {p}]\n{pages[p].text}" for p in pg)
        masked, mapping = pseudonymize.mask(text) if settings.pseudonymize else (text, {})
        ask = {k: {"type": registry[k]["type"], "description": registry[k]["description"],
                   **({"values": registry[k]["values"]} if "values" in registry[k] else {}),
                   **({"usually_phrased": registry[k]["fr"]} if "fr" in registry[k] else {})} for k in sorted(keys)}
        try:
            out = mistral.chat_json(
                "You read documents of a French criminal case file and report FACTS only, never a legal assessment. "
                "For each requested attribute, say whether the documents state it. If they do, give the value, the page "
                "number and a quote copied WORD FOR WORD from that page that contains the value (for a time, the quote "
                "must contain the time). If they do not, found=false. Never guess. JSON: {\"attrs\": {name: "
                "{\"found\": bool, \"value\": ..., \"page\": int, \"quote\": str}}}",
                f"Act: {n.label} ({n.category})\nAttributes requested: {ask}\n\nDocuments:\n{masked}",
                model=settings.extract_model, purpose="extract")
        except mistral.MistralUnavailable as e:
            log.warning("rule-driven extraction stopped: %s", e)
            break
        calls += 1
        for key, ans in (out.get("attrs") or {}).items():
            if key not in keys or not isinstance(ans, dict) or not ans.get("found"):
                continue
            q = pseudonymize.unmask(str(ans.get("quote") or ""), mapping)
            try:
                page = int(ans.get("page"))
            except (TypeError, ValueError):
                page = next((p for p in pg if q and quote_on_page_loose(q, pages[p].text)), None)
            if not q or page not in pg or not quote_on_page_loose(q, pages[page].text):  # the act's own pages only
                continue
            val = ans.get("value")
            val = pseudonymize.unmask(val, mapping) if isinstance(val, str) else val
            v, ok = _coerce(registry[key], val, q, n)
            if not ok:
                continue
            doc = next((d for d in n.doc_ids if any(page in pc.pages for pc in g.pieces if pc.id == d)), n.doc_ids[0] if n.doc_ids else "?")
            n.attrs[key] = Attr(value=v, src=Src(doc_id=doc, page=page, quote=q), status="inferred")
            if n.start is None and key in TIME_KEYS and isinstance(v, str) and "T" in v:
                n.start = datetime.fromisoformat(v)
            filled += 1
            if log_cb:
                log_cb(f"{n.label} · {key} = {v} · p. {page} (Mistral, quote verified)")
    return filled
