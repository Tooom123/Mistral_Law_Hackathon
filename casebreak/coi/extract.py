"""Facts out of the case file, each with its page and character span.

Readers work line by line on the page text (OCR or native PDF text) and recognise the shapes these documents take:
team tables, declarations of interests, signature blocks, ownership lines, sworn answers. Every fact points to a
span a reviewer can open.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from casebreak.coi.casefile import CaseFile, Doc

DATE = r"(\d{2})/(\d{2})/(\d{4})"
MONTH = r"(\d{2})/(\d{4})"
NAME = r"[A-ZÀ-Ý][a-zà-ÿ]+(?:[ -](?:Le |de |La )?[A-ZÀ-Ý][a-zà-ÿ]+)+"
COMPANY = r"[A-Z][A-Za-z]+ (?:SAS|SA|AG|Group|Logistique)\b"


@dataclass
class Src:
    doc: str
    page: int
    start: int
    end: int
    quote: str

    def ref(self) -> dict:
        return asdict(self)


def d(s: str | None, end: bool = False) -> date | None:
    """dd/mm/yyyy, or mm/yyyy (first day of the month, last day when `end`)."""
    if not s:
        return None
    m = re.fullmatch(DATE, s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    m = re.fullmatch(MONTH, s)
    if m:
        y, mo = int(m[2]), int(m[1])
        if not end:
            return date(y, mo, 1)
        return date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)
    return None


@dataclass
class Facts:
    engagements: dict = field(default_factory=dict)      # id → {client, sector, src}
    assignments: list = field(default_factory=list)      # {person, engagement, role, alloc, start, end, src}
    time_entries: list = field(default_factory=list)     # {person, engagement, days, start, end, src}
    stakeholders: dict = field(default_factory=dict)     # spec ref → {companies, src}
    orders: dict = field(default_factory=dict)           # order id → {holder, spec, start, end, signer, signed, src…}
    declarations: dict = field(default_factory=dict)     # person → {doc, date, answers{q: (bool, src)}, relative, src}
    employment: list = field(default_factory=list)       # {person, org, role, start, end, src}
    requirements: dict = field(default_factory=dict)     # declaration_before_start | consent_12_months → src
    authorship: list = field(default_factory=list)       # {person, deliverable, role, src}
    recommendations: list = field(default_factory=list)  # {deliverable, company, src}
    decisions: list = field(default_factory=list)        # {doc, kind, company|scenario, basis, persons, src}
    ownership: dict = field(default_factory=dict)        # company → {parent, share, src}
    relatives: list = field(default_factory=list)        # {person, relation, org, src}
    statements: list = field(default_factory=list)       # {speaker, claim, text, date, src}
    attestations: dict = field(default_factory=dict)     # declarations_held | no_consent | no_recusal → {...}
    people: dict = field(default_factory=dict)           # name → {mentions: [src]}
    companies: dict = field(default_factory=dict)        # name → {mentions: [src]}

    def mention(self, kind: str, name: str, src: Src) -> None:
        bucket = self.people if kind == "person" else self.companies
        bucket.setdefault(name, {"mentions": []})["mentions"].append(src)


def _lines(text: str):
    pos = 0
    for line in text.split("\n"):
        yield pos, line
        pos += len(line) + 1


def _src(doc: Doc, page: int, offset: int, line: str, sub: str | None = None) -> Src:
    """Span of `sub` inside the line (whole line, trimmed, by default)."""
    if sub and sub in line:
        i = line.index(sub)
        return Src(doc.id, page, offset + i, offset + i + len(sub), sub)
    stripped = line.strip()
    i = line.index(stripped) if stripped else 0
    return Src(doc.id, page, offset + i, offset + i + len(stripped), stripped)


ASSIGN = re.compile(rf"^\s*(?P<name>{NAME}) — (?P<role>[^—]+?) — (?P<alloc>\d+) % — (?P<s>{DATE}) to (?P<e>{DATE})\s*$")
TIME = re.compile(rf"^\s*(?P<name>{NAME}) — (?P<days>\d+) days — (?P<s>{DATE}) to (?P<e>{DATE})\s*$")
ENGAGEMENT = re.compile(r"Engagement:\s*(?P<id>[A-Z]{2}-\d{4}-\d+)\s*·\s*Client:\s*(?P<client>[^·]+?)\s*·\s*Sector:\s*(?P<sector>.+)$")
TIME_HEAD = re.compile(r"^\s*Engagement (?P<id>[A-Z]{2}-\d{4}-\d+) \((?P<client>[^)]+)\)\s*$")
EMPLOY = re.compile(rf"Previous activity:\s*(?P<org>[^—]+?) — (?P<role>[^—]+?) — (?P<s>{MONTH}) to (?P<e>{MONTH})")
ANSWER = re.compile(r"^\s*(?P<q>Q\d)\.\s*(?P<text>.+?)\s*\[(?P<y>[ X])\] Yes \[(?P<n>[ X])\] No\s*$")
RELATIVE = re.compile(r"^\s*Q\d\.\s*Interests of a close relative:\s*(?P<text>.+)$")
SIGNED = re.compile(rf"Signed for the Minister, by delegation:\s*(?P<name>{NAME}),\s*(?P<role>.+)$")
PREPARED = re.compile(r"^\s*(?P<role>Prepared|Reviewed) by:\s*(?P<names>.+)$")
OWNER = re.compile(rf"Sole shareholder:\s*(?P<parent>{COMPANY}) \((?P<share>\d+) %\)")
SPEAKER = re.compile(rf"^\s*M(?:r|s|rs) (?P<name>{NAME}):\s*(?P<text>.+)$")
HELD = re.compile(r"holds (?P<n>\d+) declarations of interests for order (?P<order>[A-Z]{2}-\d{4}-\d+):\s*(?P<names>.+?)\.?\s*$")


def _date_line(doc: Doc) -> date | None:
    m = re.search(rf"Date:\s*({DATE}|{MONTH})", doc.pages[0])
    return d(m[1]) if m else None


def read(case: CaseFile) -> Facts:
    f = Facts()
    for doc in case.docs:
        for pno, text in enumerate(doc.pages, start=1):
            _read_page(f, doc, pno, text)
    return f


def _read_page(f: Facts, doc: Doc, pno: int, text: str) -> None:  # noqa: C901 — one reader per line shape
    engagement = None
    declarant = None
    for off, line in _lines(text):
        if not line.strip():
            continue
        if m := ENGAGEMENT.search(line):
            engagement = m["id"]
            f.engagements[m["id"]] = {"client": m["client"].strip(), "sector": m["sector"].strip(),
                                      "doc": doc.id, "src": _src(doc, pno, off, line)}
            f.mention("company", m["client"].strip(), _src(doc, pno, off, line, m["client"].strip()))
            continue
        if m := TIME_HEAD.match(line):
            engagement = m["id"]
            continue
        if m := ASSIGN.match(line):
            if doc.kind == "time_report":
                continue
            f.assignments.append({"person": m["name"], "engagement": engagement, "role": m["role"].strip(),
                                  "alloc": int(m["alloc"]), "start": d(m["s"]), "end": d(m["e"]),
                                  "src": _src(doc, pno, off, line)})
            f.mention("person", m["name"], _src(doc, pno, off, line, m["name"]))
            continue
        if m := TIME.match(line):
            f.time_entries.append({"person": m["name"], "engagement": engagement, "days": int(m["days"]),
                                   "start": d(m["s"]), "end": d(m["e"]), "src": _src(doc, pno, off, line)})
            continue
        if line.startswith("Reference:") and doc.kind == "specifications":
            ref = line.split(":", 1)[1].strip()
            f.stakeholders.setdefault(ref, {"companies": [], "src": None, "doc": doc.id})
            continue
        if line.startswith("Stakeholders affected"):
            ref = next((r for r, v in f.stakeholders.items() if v["doc"] == doc.id), doc.id)
            names = re.findall(COMPANY, line.split(":", 1)[1])
            f.stakeholders.setdefault(ref, {"doc": doc.id})
            f.stakeholders[ref].update(companies=names, src=_src(doc, pno, off, line))
            for n in names:
                f.mention("company", n, _src(doc, pno, off, line, n))
            continue
        if line.startswith("Declarant:"):
            declarant = line.split(":", 1)[1].strip()
            f.mention("person", declarant, _src(doc, pno, off, line, declarant))
            if doc.kind == "consultant_declaration":
                f.declarations[declarant] = {"doc": doc.id, "date": _date_line(doc), "answers": {}, "relative": None,
                                             "src": _src(doc, pno, off, line)}
            continue
        if (m := ANSWER.match(line)) and declarant in f.declarations:
            yes = m["y"] == "X"
            box = f"[{m['y']}] Yes [{m['n']}] No"
            f.declarations[declarant]["answers"][m["q"]] = {"yes": yes, "question": m["text"],
                                                            "src": _src(doc, pno, off, line),
                                                            "box": _src(doc, pno, off, line, box)}
            continue
        if (m := RELATIVE.match(line)) and declarant:
            txt = m["text"].strip()
            if txt.lower() != "none":
                org = re.search(COMPANY, txt)
                rel = re.match(r"(\w+)", txt)
                f.relatives.append({"person": declarant, "relation": rel[1] if rel else "relative",
                                    "org": org[0] if org else None, "text": txt, "src": _src(doc, pno, off, line)})
                if declarant in f.declarations:
                    f.declarations[declarant]["relative"] = txt
            continue
        if (m := EMPLOY.search(line)) and declarant:
            f.employment.append({"person": declarant, "org": m["org"].strip(), "role": m["role"].strip(),
                                 "start": d(m["s"]), "end": d(m["e"], end=True), "src": _src(doc, pno, off, line)})
            continue
        if doc.kind == "purchase_order":
            o = f.orders.setdefault(doc.id, {"doc": doc.id})
            if mm := re.match(r"PURCHASE ORDER (\S+)", line):
                o["id"] = mm[1]
            elif line.startswith("Holder:"):
                o["holder"] = line.split(":", 1)[1].strip()
            elif mm := re.search(r"specifications ([A-Z]+-\d{4}-[A-Z]+-\d+)", line):
                o["spec"] = mm[1]
                o["object_src"] = _src(doc, pno, off, line)
            elif mm := re.match(rf"Period:\s*({DATE}) to ({DATE})", line):
                o["start"], o["end"] = d(mm[1]), d(mm[5])
            elif mm := SIGNED.search(line):
                o["signer"], o["signer_role"] = mm["name"], mm["role"].strip()
                o["signer_src"] = _src(doc, pno, off, line)
                f.mention("person", mm["name"], _src(doc, pno, off, line, mm["name"]))
            elif mm := re.match(rf"Date:\s*({DATE})", line):
                o["signed"] = d(mm[1])
            continue
        if "shall file a declaration of interests" in line:
            f.requirements["declaration_before_start"] = _src(doc, pno, off, line)
            continue
        if "shall not be assigned without the buyer's written consent" in line:
            f.requirements["consent_12_months"] = _src(doc, pno, off, line)
            continue
        if m := PREPARED.match(line):
            for n in re.findall(NAME, m["names"]):
                f.authorship.append({"person": n, "deliverable": doc.id, "role": m["role"].lower(),
                                     "src": _src(doc, pno, off, line, n)})
            continue
        if "(recommended)" in line:
            for c in re.findall(COMPANY, line):
                f.recommendations.append({"deliverable": doc.id, "company": c, "src": _src(doc, pno, off, line)})
            continue
        if line.startswith("Selected provider:"):
            c = re.search(COMPANY, line)
            basis = re.search(r"deliverable (L\d)", line)
            persons = re.findall(NAME, line.split("prepared by", 1)[1]) if "prepared by" in line else []
            f.decisions.append({"doc": doc.id, "kind": "provider", "date": _date_line(doc), "company": c[0] if c else None,
                                "basis": basis[1] if basis else None, "persons": persons,
                                "src": _src(doc, pno, off, line)})
            continue
        if line.startswith("Allocation scenario retained:"):
            sc = re.search(r"Scenario (\w)", line)
            basis = re.search(r"deliverable (L\d)", line)
            f.decisions.append({"doc": doc.id, "kind": "scenario", "date": _date_line(doc), "scenario": sc[1] if sc else None,
                                "basis": basis[1] if basis else None, "persons": [], "src": _src(doc, pno, off, line)})
            continue
        if line.startswith("Prepared for signature by:"):
            n = re.search(NAME, line)
            if n:
                for dec in f.decisions:
                    if dec["doc"] == doc.id:
                        dec["signatory"] = n[0]
                        dec["signatory_src"] = _src(doc, pno, off, line)
            continue
        if (m := OWNER.search(line)):
            company = re.search(r"Company:\s*(.+)", text)
            if company:
                f.ownership[company[1].strip()] = {"parent": m["parent"], "share": int(m["share"]),
                                                   "src": _src(doc, pno, off, line)}
            continue
        if (m := SPEAKER.match(line)) and doc.kind == "hearing":
            claim = _claim(m["text"])
            if claim:
                f.statements.append({"speaker": m["name"], "claim": claim, "text": m["text"].strip(),
                                     "date": _date_line(doc), "under_oath": "under oath" in text.lower(),
                                     "src": _src(doc, pno, off, line)})
            continue
        if m := HELD.search(line):
            f.attestations["declarations_held"] = {"order": m["order"], "n": int(m["n"]),
                                                   "names": [n.strip() for n in m["names"].split(",")],
                                                   "src": _src(doc, pno, off, line)}
            continue
        if line.startswith("No written consent under article 7.4"):
            f.attestations["no_consent"] = {"src": _src(doc, pno, off, line)}
            continue
        if line.startswith("No recusal record exists"):
            f.attestations["no_recusal"] = {"src": _src(doc, pno, off, line)}
            continue


def _claim(text: str) -> str | None:
    t = text.lower()
    if "every consultant" in t and "declaration of interests" in t:
        return "all_declared"
    if "no member of the team worked for" in t:
        return "no_dual_mandate"
    return None


def deliverable_code(case: CaseFile, doc_id: str) -> str | None:
    doc = next((x for x in case.docs if x.id == doc_id), None)
    m = re.search(r"DELIVERABLE (L\d)", doc.pages[0]) if doc else None
    return m[1] if m else None
