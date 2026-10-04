"""Conditions of the law, checked on the graph by code (ARCHITECTURE §3).

One function per `check` name used in the catalogue. Each returns a `Result` or None (not applicable).
No LLM here. Grey zones return `grey=True` and the judge is consulted by the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from casebreak.schemas import Attr, Edge, Node, PageRec, Src


@dataclass
class Result:
    status: str  # satisfied | possible_nullity | needs_reading
    statement: str
    sources: list[Src] = field(default_factory=list)
    certainty: str = "documented"  # engine may downgrade (OCR, inferred inputs)
    details: dict = field(default_factory=dict)
    grey: bool = False
    grey_attr: str | None = None
    proof: dict | None = None  # measurable facts for the Lean proof
    kind: str | None = None


class GraphCtx:
    def __init__(self, nodes: list[Node], edges: list[Edge], pages: dict[int, PageRec]):
        self.nodes = {n.id: n for n in nodes}
        self.edges = edges
        self.pages = pages
        self.by_person: dict[str, list[Node]] = {}
        for n in nodes:
            if n.type == "ACT" and n.person:
                self.by_person.setdefault(n.person, []).append(n)

    def person_acts(self, n: Node, subtype: str) -> list[Node]:
        return [x for x in self.by_person.get(n.person or "", []) if x.subtype == subtype]

    def custody(self, n: Node) -> Node | None:
        if n.subtype == "garde_a_vue":
            return n
        cid = n.val("custody_id")
        if cid and cid in self.nodes:
            return self.nodes[cid]
        lst = self.person_acts(n, "garde_a_vue")
        return lst[0] if lst else None

    def name(self, n: Node) -> str:
        p = self.nodes.get(n.person or "")
        return p.label if p else "the person"

    def ocr_pages(self, srcs: list[Src]) -> list[int]:
        return [s.page for s in srcs if s.page in self.pages and self.pages[s.page].ocr != "native"]


def dt(a: Attr | None) -> datetime | None:
    return datetime.fromisoformat(a.value) if a and isinstance(a.value, str) and "T" in a.value else None


def hm(d: datetime | None) -> str:
    return "?" if d is None else d.strftime("%H:%M")


def dhm(d: datetime | None) -> str:
    return "?" if d is None else d.strftime("%d/%m/%Y %H:%M")


def dur(minutes: float) -> str:
    m = int(round(minutes))
    h, mm = divmod(abs(m), 60)
    return f"{h}h{mm:02d}" if h else f"{mm} min"


def srcs(*attrs: Attr | None) -> list[Src]:
    return [a.src for a in attrs if a is not None and a.src is not None]


def _minutes(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60


# ============================================================================ CUSTODY


def objectives_stated(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    a = n.attr("objectives_text")
    if a is None:
        return None
    if a.value:
        return Result("satisfied", "Grounds for custody found; whether they match the legal objectives is to be assessed.",
                      srcs(a), grey=True, grey_attr="objectives_text", certainty="inferred")
    return Result("needs_reading", f"No grounds for custody found for {ctx.name(n)}; "
                  "the report only contains a generic phrase." if a.src else
                  f"No grounds for custody found for {ctx.name(n)}.",
                  srcs(a), grey=True, grey_attr="objectives_text", certainty="needs_reading")


def custody_duration(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    s, e = n.attr("custody_start"), n.attr("custody_end")
    start, end = dt(s), dt(e)
    base = int(p.get("initial_hours", 24)) * 60
    ext = n.attr("extension_authorized")
    limit = base + (int(p.get("extension_hours", 24)) * 60 if ext else 0)
    if n.attr("special_regime"):
        return Result("needs_reading", "Special regime invoked: specific maximum durations to be checked (GAV-03).",
                      srcs(n.attr("special_regime")), certainty="needs_reading")
    if start is None:
        return Result("needs_reading", "Custody start time unreadable or missing.", srcs(s), certainty="needs_reading")
    if end is None:
        d_attr = n.attr("custody_end_date")
        if d_attr and d_attr.value:
            upper = datetime.combine(date.fromisoformat(d_attr.value), time(23, 59))
            up = _minutes(start, upper)
            if up <= limit:
                return Result("satisfied", f"End time not recorded; upper bound (end of day {upper:%d/%m}): "
                              f"{dur(up)} ≤ {dur(limit)}{' (extension authorised)' if ext else ''}.",
                              srcs(s, d_attr, ext), certainty="needs_reading")
        return Result("needs_reading", "Custody end time not recorded: duration cannot be computed.",
                      srcs(s, e), certainty="needs_reading")
    total = _minutes(start, end)
    proof = {"start": start.isoformat(), "end": end.isoformat(), "limit_minutes": limit, "kind": "duration_gt"}
    if total > limit:
        if ext:
            stmt = (f"Custody of {ctx.name(n)}: {dhm(start)} → {dhm(end)}, i.e. {dur(total)}, beyond "
                    f"{dur(limit)} despite the extension.")
        else:
            stmt = (f"Custody of {ctx.name(n)}: {dhm(start)} → {dhm(end)}, i.e. {dur(total)}. "
                    f"No extension authorisation in the file.")
        return Result("possible_nullity", stmt, srcs(s, e, ext), proof=proof,
                      details={"duration_minutes": total, "limit_minutes": limit, "extension": bool(ext)})
    if ext:
        auth_at = dt(n.attr("extension_authorized_at"))
        if auth_at and auth_at > start + timedelta(minutes=base):
            return Result("needs_reading", f"Extension authorised at {dhm(auth_at)}, after the initial {dur(base)} expired "
                          f"({dhm(start + timedelta(minutes=base))}). TODO(legal): consequences.",
                          srcs(s, n.attr("extension_authorized_at")), certainty="needs_reading")
    return Result("satisfied", f"Duration {dur(total)} ≤ {dur(limit)}{' (extension authorised)' if ext else ''}.",
                  srcs(s, e, ext), proof={**proof, "kind": "duration_le"},
                  details={"duration_minutes": total, "limit_minutes": limit})


def special_regime(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    a = n.attr("special_regime")
    if not a:
        return None
    return Result("needs_reading", f"Special regime invoked: \"{a.value}\". Specific authorisations to be checked.",
                  srcs(a), certainty="needs_reading")


def rights_delay(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    if n.subtype == "garde_a_vue":
        if not ctx.person_acts(n, "rights_notification"):
            return Result("possible_nullity", f"Custody of {ctx.name(n)} with no rights-notification report "
                          "in the file.", srcs(n.attr("custody_start")), certainty="needs_reading", kind="missing_mention")
        return None
    cust = ctx.custody(n)
    if cust is None:
        return None
    s, nt = cust.attr("custody_start"), n.attr("notified_at")
    start, notified = dt(s), dt(nt)
    if start is None or notified is None:
        return Result("needs_reading", "Custody or notification time unreadable: delay cannot be computed.",
                      srcs(s, nt), certainty="needs_reading")
    delay = _minutes(start, notified)
    thr = float(p.get("review_threshold_minutes", 60))
    just = n.attr("delay_justification")
    details = {"delay_minutes": delay, "threshold_minutes": thr, "threshold_note": "internal flagging threshold, not a legal one — TODO(legal)"}
    proof = {"start": start.isoformat(), "end": notified.isoformat(), "limit_minutes": int(thr), "kind": "duration_gt"}
    if delay < thr:
        return Result("satisfied", f"Rights notified {dur(delay)} after custody began ({hm(start)} → {hm(notified)}).",
                      srcs(s, nt), details=details)
    if just:
        return None  # handled by GAV-05 (grey zone) — the delay is justified on the face of the PV
    return Result("possible_nullity",
                  f"Rights notified at {hm(notified)}; custody began at {hm(start)} ({dur(delay)}). No justification found.",
                  srcs(s, nt), details=details, proof=proof)


def rights_delay_justified(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    just = n.attr("delay_justification")
    cust = ctx.custody(n)
    if not just or cust is None:
        return None
    start, notified = dt(cust.attr("custody_start")), dt(n.attr("notified_at"))
    delay = _minutes(start, notified) if start and notified else None
    lead = f"Rights notified {dur(delay)} after custody began" if delay is not None else "Notification deferred"
    return Result("needs_reading", f"{lead}; justification stated in the report: \"{just.value}\". For the lawyer to assess.",
                  srcs(cust.attr("custody_start"), n.attr("notified_at"), just), grey=True,
                  grey_attr="delay_justification", certainty="inferred", details={"delay_minutes": delay})


def prosecutor_informed(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    a = n.attr("prosecutor_informed_at")
    if a is None:
        return None
    if a.status == "missing":
        return Result("possible_nullity", f"Custody of {ctx.name(n)}: no record that the public prosecutor was informed.",
                      srcs(n.attr("custody_start")), certainty="needs_reading", kind="missing_mention")
    start, at = dt(n.attr("custody_start")), dt(a)
    if start and at:
        return Result("satisfied", f"Prosecutor informed at {hm(at)} ({dur(_minutes(start, at))} after custody began).",
                      srcs(a))
    return Result("needs_reading", "Time the prosecutor was informed is unreadable.", srcs(a), certainty="needs_reading")


def lawyer_meeting(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    return None  # only explicit refusals would be flagged; none extracted by the patterns (see catalogue GAV-07)


def hearing_lawyer(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    cust = ctx.custody(n)
    if cust is None or n.val("in_custody") is not True:
        return None
    notifs = ctx.person_acts(n, "rights_notification")
    req = notifs[0].attr("lawyer_requested") if notifs else None
    if req is None or req.value is not True:
        return None
    lp = n.attr("lawyer_present")
    if lp is None or lp.value is None:
        return Result("needs_reading", "Lawyer's presence at the hearing not recorded although one was requested.",
                      srcs(req, n.attr("start")), certainty="needs_reading", kind="missing_mention")
    if lp.value is True:
        return Result("satisfied", "Hearing held with the lawyer present.", srcs(lp))
    waiver, auth = n.attr("lawyer_waiver"), n.attr("prosecutor_authorization")
    if waiver:
        return Result("satisfied", "Express waiver of the lawyer recorded in the report.", srcs(waiver))
    if auth:
        return Result("needs_reading", "Written authorisation from the prosecutor invoked: exceptional circumstances to be assessed.",
                      srcs(auth), certainty="needs_reading")
    start = dt(n.attr("start"))
    if p.get("regime") == "before_2024":
        notices = ctx.person_acts(n, "lawyer_notice")
        notified = dt(notices[0].attr("lawyer_notified_at")) if notices else dt(n.attr("lawyer_notified_at_stated"))
        if notified is None or start is None:
            return Result("needs_reading", "Time the lawyer was notified is unknown: waiting time cannot be computed.",
                          srcs(req, lp), certainty="needs_reading")
        wait = _minutes(notified, start)
        need = float(p.get("wait_minutes", 120))
        src_notice = notices[0].attr("lawyer_notified_at") if notices else n.attr("lawyer_notified_at_stated")
        if wait >= need:
            return Result("satisfied", f"Pre-2024 version: questioned without the lawyer after a {dur(wait)} wait "
                          f"(lawyer notified at {hm(notified)}, hearing at {hm(start)}) ≥ {dur(need)}.",
                          srcs(src_notice, n.attr("start"), lp))
        return Result("possible_nullity", f"Pre-2024 version: questioned without the lawyer after only a {dur(wait)} "
                      f"wait (lawyer notified at {hm(notified)}, hearing at {hm(start)}).", srcs(src_notice, n.attr("start"), lp),
                      proof={"start": notified.isoformat(), "end": start.isoformat(), "limit_minutes": int(need), "kind": "duration_lt"})
    return Result("possible_nullity", f"Hearing of {dhm(start)} without the requested lawyer ({ctx.name(n)}), with no waiver "
                  "or prosecutor authorisation in the report.", srcs(req, lp, n.attr("start")))


def doctor_seen(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    notifs = ctx.person_acts(n, "rights_notification")
    req = notifs[0].attr("doctor_requested") if notifs else None
    if not req or req.value is not True:
        return None
    exams = ctx.person_acts(n, "medical_exam")
    if exams:
        return Result("satisfied", "Medical examination carried out.", srcs(exams[0].attr("exam_at")))
    return Result("possible_nullity", f"{ctx.name(n)} asked for a medical examination; no examination report or "
                  "certificate in the file.", srcs(req), certainty="needs_reading", kind="missing_mention")


def interpreter(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    cust = ctx.custody(n)
    if cust is None:
        return None
    uf = cust.attr("understands_french")
    if not uf or uf.value is not False:
        return None
    ip = n.attr("interpreter_present")
    act = "the rights notification" if n.subtype == "rights_notification" else "the hearing"
    if ip and ip.value is True:
        return Result("satisfied", f"Interpreter present during {act}.", srcs(ip))
    if ip and ip.value is False and ip.src:
        return Result("possible_nullity", f"{ctx.name(n)} states they do not understand French; {act} at {hm(n.start)} "
                      "was conducted in French, without an interpreter.", srcs(uf, ip))
    return Result("needs_reading", f"{ctx.name(n)} does not understand French; no interpreter recorded during {act}.", srcs(uf), certainty="needs_reading", kind="missing_mention")


def family_informed(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    notifs = ctx.person_acts(n, "rights_notification")
    req = notifs[0].attr("family_requested") if notifs else None
    if not req or req.value is not True:
        return None
    done = ctx.person_acts(n, "family_notice")
    if done:
        return Result("satisfied", "Relative informed.", srcs(done[0].attr("family_notified_at")))
    return Result("possible_nullity", "Relative to be informed was requested; no notice report in the file.", srcs(req),
                  certainty="needs_reading", kind="missing_mention")


def pv_mentions(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    if n.subtype == "garde_a_vue":
        e = n.attr("custody_end")
        ends = ctx.person_acts(n, "custody_end")
        if not ends:
            return Result("needs_reading", f"No end-of-custody report for {ctx.name(n)}.",
                          srcs(n.attr("custody_start")), certainty="needs_reading")
        if e is None or e.value is None:
            src = e.src if e and e.src else ends[0].attrs.get("end_date", Attr()).src
            return Result("possible_nullity", f"End-of-custody report for {ctx.name(n)}: end time not recorded.",
                          [s for s in [src] if s], certainty="needs_reading", kind="missing_mention")
        return Result("satisfied", f"End time recorded ({hm(dt(e))}).", srcs(e))
    if n.subtype == "hearing" and n.val("in_custody"):
        if n.attr("end") is None:
            return Result("needs_reading", "Hearing end time not recorded.", srcs(n.attr("start")),
                          certainty="needs_reading", kind="missing_mention")
    return None


def custody_start_consistency(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    c = n.attr("custody_start_conflict")
    if not c:
        return None
    raw = n.val("_conflict_sources") or []
    sources = [Src(**s) for s in raw]
    return Result("needs_reading", f"Documents disagree on when custody of {ctx.name(n)} began: {c.value}. "
                  "Time limits must be recomputed from the earliest time.", sources,
                  certainty="needs_reading", details={"values": c.value})


# ============================================================================ SEARCH / SEIZURE


def search_hours(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    home = n.attr("is_home")
    if home is None or home.value is not True:
        return None
    s = n.attr("start")
    start = dt(s)
    e = n.attr("end")
    early = time.fromisoformat(p.get("earliest", "06:00"))
    late = time.fromisoformat(p.get("latest", "21:00"))
    if start is None:
        why = "unreadable (handwritten?)" if s and s.status == "unreadable" else "not recorded"
        end = dt(e)
        tail = f"; operations ended at {hm(end)}" if end else ""
        return Result("needs_reading", f"Home search start time {why}{tail}. "
                      "Read the page to check the legal hours.", srcs(s, e), certainty="needs_reading")
    if start.time() < early or start.time() >= late:
        lim = late if start.time() >= late else early
        return Result("possible_nullity", f"Home search started at {hm(start)} "
                      f"(outside {early:%H:%M}–{late:%H:%M}).", srcs(s, home),
                      proof={"start_clock": start.strftime("%H:%M"), "bound": lim.strftime("%H:%M"),
                             "kind": "clock_ge" if start.time() >= late else "clock_lt"},
                      details={"start": start.isoformat()})
    end = dt(e)
    if end and end.time() >= late:
        return Result("satisfied", f"Started at {hm(start)} (before {late:%H:%M}), continued until {hm(end)}.",
                      srcs(s, e))
    return Result("satisfied", f"Started at {hm(start)}, within legal hours.", srcs(s))


def search_presence(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    occ, wit = n.attr("occupant_present"), n.attr("witnesses_present")
    if occ is None:
        return None
    if occ.value or (wit and wit.value):
        return Result("satisfied", "Presence of the occupant or two witnesses recorded.", srcs(occ if occ.value else wit))
    return Result("possible_nullity", "Search: neither the occupant nor two witnesses are recorded as present.",
                  srcs(occ), certainty="needs_reading", kind="missing_mention")


def search_consent(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    if n.framework != "preliminaire":
        return None
    if n.attr("jld_authorization"):
        return Result("satisfied", "Authorisation from the liberty and custody judge cited.", srcs(n.attr("jld_authorization")))
    c = n.attr("consent")
    if c and c.value == "handwritten":
        return Result("satisfied", "Express consent handwritten by the person concerned.", srcs(c))
    if c and c.value == "verbal":
        return Result("possible_nullity", "Preliminary inquiry: verbal agreement only, with no handwritten statement "
                      "and no JLD authorisation.", srcs(c))
    return Result("possible_nullity", "Preliminary inquiry: no consent or JLD authorisation recorded.",
                  [s for s in [n.attr("start").src if n.attr("start") else None] if s], certainty="needs_reading",
                  kind="missing_mention")


def seized_sealed(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    s = n.attr("seal_number")
    if s is None:
        return None
    if s.value:
        return Result("satisfied", f"Placed under seal {s.value}.", srcs(s))
    return Result("possible_nullity", f"\"{n.val('item')}\" seized with no record of being placed under seal.", srcs(s))


# ============================================================================ GRAPH / PROCEDURE


def seal_traceable(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    o = n.attr("orphan_seals")
    if not o:
        return None
    return Result("needs_reading", f"Seal(s) {o.value} analysed: no matching seizure in the file.",
                  srcs(o), certainty="needs_reading")


def authorization_present(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    want = p.get("auth_subtype")
    auths = [x for x in ctx.nodes.values() if x.type == "ACT" and x.subtype == want]
    ref = n.attr("authorization_ref")
    if auths:
        return Result("satisfied", "Authorisation present in the file.", srcs(ref) + srcs(auths[0].attr("date")))
    return Result("needs_reading", ("Authorisation cited in the report" + (f" (dated {n.val('authorization_date')})" if n.val("authorization_date") else "")
                  + " but missing from the file."), srcs(ref) or srcs(n.attr("start")), certainty="needs_reading")


def hearing_in_custody_window(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    if n.val("in_custody") is not True or n.start is None:
        return None
    cust = ctx.custody(n)
    if cust is None or cust.start is None:
        return None
    if n.start < cust.start - timedelta(minutes=1) or (cust.end and n.start > cust.end):
        return Result("needs_reading", f"\"Custody\" hearing at {dhm(n.start)}, outside the custody period "
                      f"{dhm(cust.start)} → {dhm(cust.end)}.", srcs(n.attr("start")), certainty="needs_reading")
    return None


def arrest_before_custody(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    cust = ctx.custody(n)
    a = n.attr("arrest_time")
    if cust is None or cust.start is None or dt(a) is None:
        return None
    if dt(a) > cust.start:
        return Result("needs_reading", f"Arrest at {hm(dt(a))}, after custody began ({hm(cust.start)}).",
                      srcs(a, cust.attr("custody_start")), certainty="needs_reading")
    return None


def exif_consistency(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    c = n.attr("exif_conflict")
    if not c:
        return None
    return Result("needs_reading", f"Photo of seal {n.val('seal_label')}: {c.value}. Metadata can be "
                  "wrong — never a ground on its own.", srcs(n.attr("seal_label"), c), certainty="needs_reading",
                  details={"search": n.val("exif_conflict_search")})


def purge(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    return Result("needs_reading", f"Investigating chamber ruling of {dhm(n.start)}: earlier defects not raised "
                  "may be purged (unless they could not have been known).", srcs(n.attr("date")), certainty="needs_reading")


def info_only(n: Node, ctx: GraphCtx, p: dict) -> Result | None:
    return None


CHECKS = {name: fn for name, fn in globals().items() if callable(fn) and not name.startswith("_")
          and name not in {"dt", "hm", "dhm", "dur", "srcs", "Result", "GraphCtx", "dataclass", "field", "date",
                           "datetime", "time", "timedelta", "Attr", "Edge", "Node", "PageRec", "Src"}}
