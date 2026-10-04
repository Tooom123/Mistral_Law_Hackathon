"""⑤ LINK — custody containers, PART_OF / PRECEDES / DOCUMENTED_IN / INVOLVES / SUPPORTS / CONTRADICTS.

SUPPORTS edges come from structure (custody → hearings, search → seizures, seal numbers) or from the
text ("vu le procès-verbal n°…"). With a Mistral key, acts with no incoming support may get an
`llm_inferred` edge (drawn dashed, lower certainty).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from casebreak.graph.extract import Draft, person_id
from casebreak.schemas import Attr, Edge, Node, PageRec, Piece, Src
from casebreak.text import squash

log = logging.getLogger(__name__)

GAV_CHILDREN = {"placement_gav", "rights_notification", "lawyer_notice", "family_notice", "medical_exam", "extension",
                "custody_end"}


def _dt(a: Attr | None) -> datetime | None:
    return datetime.fromisoformat(a.value) if a and isinstance(a.value, str) else None


def build_graph(pieces: list[Piece], drafts: list[Draft], pages: dict[int, PageRec]) -> tuple[list[Node], list[Edge]]:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    seen_edges: set[tuple] = set()

    def edge(src: str, dst: str, kind: str, origin: str = "structural", ref: Src | None = None, label: str = "") -> None:
        if src == dst or src not in nodes or dst not in nodes:
            return
        k = (src, dst, kind)
        if k in seen_edges:
            return
        seen_edges.add(k)
        edges.append(Edge(src=src, dst=dst, kind=kind, origin=origin, src_ref=ref, label=label))

    # PIECE nodes
    by_number: dict[str, Piece] = {}
    for pc in pieces:
        nodes[f"piece:{pc.id}"] = Node(id=f"piece:{pc.id}", type="PIECE", category=pc.category, subtype=pc.type,
                                       label=pc.title or pc.type, doc_ids=[pc.id], pages=pc.pages)
        if pc.number:
            by_number[pc.number] = pc

    acts = [d.node for d in drafts]
    for n in acts:
        nodes[n.id] = n

    # PERSON nodes
    names: dict[str, str] = {}
    for d in drafts:
        nm = d.node.attrs.get("_person_name")
        if d.node.person and nm and nm.value:
            names.setdefault(d.node.person, str(nm.value))
        d.node.attrs.pop("_person_name", None)
    for pid, nm in names.items():
        nodes[pid] = Node(id=pid, type="PERSON", label=nm, subtype="person")

    # custody containers: one per person with a placement
    by_person: dict[str, list[Node]] = defaultdict(list)
    for n in acts:
        if n.person:
            by_person[n.person].append(n)
    for pid, lst in by_person.items():
        placement = next((n for n in lst if n.subtype == "placement_gav"), None)
        if placement is None:
            continue
        cid = f"gav:{pid.split(':', 1)[1]}"
        end = next((n for n in lst if n.subtype == "custody_end"), None)
        ext = next((n for n in lst if n.subtype == "extension"), None)
        start = placement.start
        end_dt = end.start if end else None
        c = Node(id=cid, type="ACT", category="GARDE_A_VUE", subtype="garde_a_vue",
                 label=f"Custody — {names.get(pid, pid)}", start=start, end=end_dt,
                 framework=placement.framework, person=pid,
                 doc_ids=sorted({x for n in lst if n.subtype in GAV_CHILDREN for x in n.doc_ids}),
                 pages=sorted({x for n in lst if n.subtype in GAV_CHILDREN for x in n.pages}))
        c.attrs["custody_start"] = placement.attrs.get("custody_start", Attr(status="missing"))
        if end:
            c.attrs["custody_end"] = end.attrs.get("end_time", Attr(status="missing"))
            if c.attrs["custody_end"].value is None and end.attrs.get("end_date"):
                c.attrs["custody_end_date"] = end.attrs["end_date"]
        else:
            c.attrs["custody_end"] = Attr(value=None, status="missing")
        if ext and ext.attrs.get("extension_authorized"):
            c.attrs["extension_authorized"] = ext.attrs["extension_authorized"]
            if ext.attrs.get("authorized_at"):
                c.attrs["extension_authorized_at"] = ext.attrs["authorized_at"]
        for k in ("special_regime", "understands_french", "language", "prosecutor_informed_at", "objectives_text"):
            if k in placement.attrs:
                c.attrs[k] = placement.attrs[k]
        nodes[cid] = c
        for n in lst:
            if n.subtype in GAV_CHILDREN:
                edge(n.id, cid, "PART_OF")
        # hearings during the custody window
        for n in lst:
            if n.subtype == "hearing" and n.start and start and n.start >= start - timedelta(hours=1) and \
                    (end_dt is None or n.start <= end_dt + timedelta(hours=1)):
                n.attrs["custody_id"] = Attr(value=cid)
                edge(cid, n.id, "SUPPORTS", label="hearing during custody")
            if n.subtype == "interpellation":
                edge(n.id, cid, "SUPPORTS", label="arrest → custody")
        notif = next((n for n in lst if n.subtype == "rights_notification"), None)
        if notif:
            for n in lst:
                if n.subtype == "hearing" and n.start and notif.start and n.start >= notif.start and \
                        (end_dt is None or n.start <= end_dt):
                    edge(notif.id, n.id, "SUPPORTS", label="rights notified → hearing")

    # DOCUMENTED_IN, INVOLVES
    for d in drafts:
        n = d.node
        for doc in n.doc_ids:
            edge(n.id, f"piece:{doc}", "DOCUMENTED_IN")
        if n.person and n.person in nodes:
            edge(n.id, n.person, "INVOLVES")

    # ITEMS (seals) and SUPPORTS via seal numbers
    seized_by: dict[str, Node] = {}
    for d in drafts:
        for seal in d.seals_seized:
            seized_by[seal] = d.node
            iid = f"item:{seal}"
            nodes.setdefault(iid, Node(id=iid, type="ITEM", subtype="seal", label=f"Seal {seal}",
                                       attrs={"seal_number": Attr(value=seal)}))
            edge(d.node.id, iid, "INVOLVES")
    search_of: dict[str, Node] = {}
    for d in drafts:
        if d.node.subtype == "search":
            for d2 in drafts:
                if d2.node.subtype == "seizure" and d2.node.doc_ids == d.node.doc_ids:
                    edge(d.node.id, d2.node.id, "SUPPORTS", label="perquisition → saisie")
                    for s in d2.seals_seized:
                        search_of[s] = d.node
    orphan_seals: dict[str, list[tuple[Node, Src]]] = defaultdict(list)
    for d in drafts:
        for seal, src in d.seals_used:
            iid = f"item:{seal}"
            if seal in seized_by:
                edge(seized_by[seal].id, d.node.id, "SUPPORTS", ref=src, label=f"seal {seal}")
                edge(d.node.id, iid, "INVOLVES")
            else:
                orphan_seals[seal].append((d.node, src))
                nodes.setdefault(iid, Node(id=iid, type="ITEM", subtype="seal", label=f"Seal {seal} (origin?)",
                                           attrs={"seal_number": Attr(value=seal), "seized": Attr(value=False, status="missing")}))
                edge(d.node.id, iid, "INVOLVES")
    for seal, uses in orphan_seals.items():
        for n, src in uses:
            if n.subtype != "photo":
                n.attrs.setdefault("orphan_seals", Attr(value=seal, src=src))
                n.attrs["orphan_seals"] = Attr(value=", ".join(sorted(set(str(n.attrs["orphan_seals"].value).split(", ")) | {seal})),
                                               src=n.attrs["orphan_seals"].src)

    # SUPPORTS cited in text ("vu le procès-verbal n° …")
    act_by_piece: dict[str, list[Node]] = defaultdict(list)
    for n in acts:
        for doc in n.doc_ids:
            act_by_piece[doc].append(n)
    main_act = {doc: (lst[0] if lst else None) for doc, lst in act_by_piece.items()}
    for d in drafts:
        for num, src in d.cites:
            pc = by_number.get(num)
            if pc is None:
                d.node.attrs.setdefault("cited_missing", Attr(value=num, src=src))
                continue
            a = main_act.get(pc.id)
            if a is not None:
                edge(a.id, d.node.id, "SUPPORTS", origin="cited_in_text", ref=src, label=f"cites report no. {num}")

    # PRECEDES (global time order of acts, skipping containers)
    timed = sorted([n for n in acts if n.start], key=lambda n: n.start)
    for a, b in zip(timed, timed[1:]):
        edge(a.id, b.id, "PRECEDES")

    # CONTRADICTS — same fact, two pieces, two values
    for pid, lst in by_person.items():
        cid = f"gav:{pid.split(':', 1)[1]}"
        if cid not in nodes:
            continue
        stated: list[tuple[datetime, Src, str]] = []
        for n in lst:
            for key in ("custody_start", "custody_start_stated", "placed_at_stated"):
                a = n.attrs.get(key)
                if a and a.value and a.src:
                    stated.append((_dt(a), a.src, n.id))
        vals = {s[0] for s in stated if s[0]}
        if len(vals) > 1:
            base = stated[0]
            for other in stated[1:]:
                if other[0] != base[0] and other[2] != base[2]:
                    edge(base[2], other[2], "CONTRADICTS", ref=other[1],
                         label=f"custody start: {base[0]:%H:%M} / {other[0]:%H:%M}")
            nodes[cid].attrs["custody_start_conflict"] = Attr(
                value=" / ".join(sorted({f"{v:%H:%M}" for v in vals})), src=stated[1][1] if len(stated) > 1 else None)
            nodes[cid].attrs["_conflict_sources"] = Attr(value=[s[1].model_dump() for s in stated])
    # EXIF of a photo vs time window of the search that seized the photographed seal
    for d in drafts:
        n = d.node
        if n.subtype != "photo" or not n.start:
            continue
        for seal, _src in d.seals_used:
            srch = search_of.get(seal)
            if srch is None:
                continue
            edge(srch.id, n.id, "INVOLVES", label=f"photo of seal {seal}")
            if srch.start and (n.start < srch.start - timedelta(minutes=5) or (srch.end and n.start > srch.end + timedelta(hours=2))):
                edge(n.id, srch.id, "CONTRADICTS", ref=srch.attrs.get("start").src if srch.attrs.get("start") else None,
                     label=f"EXIF {n.start:%H:%M} / search {srch.start:%H:%M}")
                n.attrs["exif_conflict"] = Attr(value=f"EXIF {n.start:%d/%m %H:%M}; search started {srch.start:%d/%m %H:%M}",
                                                src=srch.attrs["start"].src if srch.attrs.get("start") else None)
                n.attrs["exif_conflict_search"] = Attr(value=srch.id)

    _llm_supports(nodes, edges, edge)
    return list(nodes.values()), edges


def _llm_supports(nodes: dict[str, Node], edges: list[Edge], edge) -> None:
    """Optional: propose SUPPORTS for orphan acts with Mistral (dashed). Never used for checks' certainty above inferred."""
    from casebreak.config import settings

    if not settings.mistral:
        return
    from casebreak.llm import mistral

    acts = [n for n in nodes.values() if n.type == "ACT" and n.subtype not in ("other", "photo")]
    has_in = {e.dst for e in edges if e.kind == "SUPPORTS"}
    orphans = [n for n in acts if n.id not in has_in and n.category in ("EXPERTISE", "AUDITION", "INSTRUCTION")]
    if not orphans:
        return
    from casebreak.privacy import pseudonymize

    # Short opaque ids (A1, A2…) instead of node ids, which contain person names.
    alias = {f"A{k}": n.id for k, n in enumerate(acts, 1)}
    back = {v: k for k, v in alias.items()}
    listing = "\n".join(f"{back[n.id]} | {n.category} | {n.subtype} | {n.label} | {n.start}" for n in acts)
    if settings.pseudonymize:
        listing = pseudonymize.mask_value(listing)
    try:
        out = mistral.chat_json(
            "You propose dependency links (act B relies on act A) between the acts of a criminal case file. "
            "Only propose obvious links. JSON: {\"links\": [{\"src\": id, \"dst\": id, \"why\": str}]}",
            f"Acts:\n{listing}\n\nActs with no identified support: {[back[n.id] for n in orphans]}", purpose="link")
    except mistral.MistralUnavailable:
        return
    orphan_ids = {n.id for n in orphans}
    for link in [x for x in out.get("links", []) if isinstance(x, dict)][:20]:
        src, dst = alias.get(str(link.get("src"))), alias.get(str(link.get("dst")))
        if src and dst in orphan_ids:
            edge(src, dst, "SUPPORTS", origin="llm_inferred", label=squash(str(link.get("why", "")))[:80])


def person_of(name: str) -> str:
    return person_id(name)
