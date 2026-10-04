"""The Beckham speeding case (2018), reconstructed as a case file for the demo.

What is real (public press reports, see SOURCES): a Bentley on loan from the manufacturer was recorded at 59 mph in a
40 mph zone on the A40 in Paddington on 23 January 2018. Because the car belonged to Bentley Motors Ltd, the notice of
intended prosecution (NIP) was sent to the company, by first class post on 2 February. It reached the company's post
room on 7 February — day 15 — one day outside the 14-day window of s.1 Road Traffic Offenders Act 1988. On 27 September
2018 the district judge held the notice had more likely than not not arrived in time and the charge was dismissed.

What is NOT real: every document below. They are a SYNTHETIC RECONSTRUCTION written for this demo from those
reports. Times of day, reference numbers, the witness and the document layouts are invented; each page says so in
its footer. No original document, personal data or real vehicle registration is reproduced.

The generator never writes the outcome in the file: finding the defect is the job of the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

from casebreak.synth.render import BOTTOM, MARGIN_X, TOP, W, H, _wrap

TITLE = "The Beckham speeding case, 2018 (synthetic reconstruction)"
SOURCES = [
    {"title": "ITV News — David Beckham's speeding charge thrown out on technicality (27 Sep 2018)",
     "url": "https://itv.com/news/2018-09-27/david-beckhams-speeding-charge-thrown-out-on-technicality"},
    {"title": "Express & Star — David Beckham faces trial over speeding charge (28 Aug 2018)",
     "url": "https://www.expressandstar.com/news/motors/2018/08/28/david-beckham-faces-trial-over-speeding-charge"},
    {"title": "Shortlist — Beckham got out of a speeding ticket on a technicality",
     "url": "https://www.shortlist.com/news/david-beckham-speeding-ticket-technicality-mr-loophole"},
]
REAL_OUTCOME = (
    "27 September 2018: District Judge Barbara Barnes held that the notice of intended prosecution, posted on 2 "
    "February 2018, more likely than not did not reach Bentley Motors Ltd (the registered keeper) until 7 February, "
    "day 15, outside the 14-day statutory window; the defendant could not be convicted and the charge was dismissed."
)
FOOTER = "SYNTHETIC RECONSTRUCTION from public press reports - not an authentic document"

REPORT, KEEPER, NIP, REGISTER, STATEMENT, RESPONSE, SUMMONS, RECORD = (
    "TCJU/2018/00123", "DVLA/2018/48213", "NIP/2018/04417", "BML/MS/2018/006", "BML/WS/2018/001",
    "BML/LEG/2018/0117", "SUM/2018/09352", "WMC/2018/0827")
DRIVER = "Mr David Beckham"
PLACE = "A40 Westway (flyover), Paddington, London"


@dataclass
class Doc:
    key: str
    kind: str  # header word, matches ingest.split.EN_HEADER_RE
    number: str
    subject: str
    org: str
    sub: str
    lines: list[str]
    person: str = ""
    gt: list[dict] = field(default_factory=list)
    cote: str = ""


def documents() -> list[Doc]:
    return [
        Doc("report", "OFFENCE REPORT", REPORT, "Speed camera detection - A40 Westway, Paddington",
            "TRAFFIC CRIMINAL JUSTICE UNIT", "Enforcement authority - London", [
                "Date and time of offence: 23 January 2018 at 14:36.",
                f"Place of offence: {PLACE}.",
                "Recorded speed: 59 mph. Posted speed limit: 40 mph.",
                "Detection: fixed digital speed camera; the offence image was reviewed and confirmed by an enforcement officer.",
                "Vehicle: Bentley saloon, supplied on loan by the manufacturer. Registration mark withheld in this reconstruction.",
                "Alleged offence: driving in excess of the posted speed limit.",
                "Next steps: registered keeper enquiry; notice of intended prosecution to be served within 14 days of the offence.",
            ]),
        Doc("keeper", "KEEPER ENQUIRY", KEEPER, "Registered keeper enquiry - vehicle recorded at Paddington",
            "VEHICLE KEEPER RECORDS", "Registered keeper enquiry result", [
                "Date of enquiry: 24 January 2018.",
                "Registered keeper at the date of the offence: Bentley Motors Limited, Crewe.",
                f"Enquiry made in respect of offence report {REPORT}.",
                "Note: the vehicle is registered to a motor manufacturer and was supplied on loan. The driver at the time of "
                "the offence is not known from this enquiry.",
            ]),
        Doc("nip", "NOTICE OF INTENDED PROSECUTION", NIP, "Notice of intended prosecution - speeding offence",
            "TRAFFIC CRIMINAL JUSTICE UNIT", "Enforcement authority - London", [
                "Date of notice: 2 February 2018.",
                "Addressed to: Bentley Motors Limited, Crewe (registered keeper of the vehicle).",
                "Offence date and time stated: 23 January 2018 at 14:36.",
                f"Offence place stated: {PLACE}.",
                "Nature of offence stated: driving in excess of the 40 mph speed limit.",
                "Method of service: first class post.",
                "Date and time of posting: 2 February 2018 at 16:30.",
                f"This notice is issued in respect of offence report {REPORT} and keeper enquiry {KEEPER}.",
                "You are required to identify the driver within 28 days beginning with the day on which this notice is served.",
            ], gt=[
                {"nullity_id": "NIP-01", "expected": "possible_nullity", "injected": True, "phrase": "date and time of posting",
                 "affected_keys": ["response", "summons", "record"], "certainty": "documented",
                 "note": "Notice posted on day 10 but received on day 15 (7 February): outside the 14-day window."},
                {"nullity_id": "NIP-02", "expected": "satisfied", "injected": False, "phrase": "nature of offence stated",
                 "affected_keys": [], "note": "Decoy: the notice states nature, time and place of the offence."},
                {"nullity_id": "NIP-03", "expected": "satisfied", "injected": False, "phrase": "addressed to",
                 "affected_keys": [], "note": "Decoy: addressed to the registered keeper named in the keeper enquiry."},
            ]),
        Doc("register", "INCOMING POST REGISTER", REGISTER, "Incoming post register - 5 to 8 February 2018",
            "BENTLEY MOTORS LIMITED", "Mail Services - Crewe", [
                "Register kept by: Mail Services, Bentley Motors Limited, Crewe.",
                "Period covered: 5 February 2018 to 8 February 2018.",
                "Logged: 5 February 2018 - no item received from the Traffic Criminal Justice Unit.",
                "Logged: 6 February 2018 - no item received from the Traffic Criminal Justice Unit.",
                f"Received: 7 February 2018 at 09:40 - Notice of intended prosecution {NIP}, envelope postmarked 2 February 2018, "
                "opened, logged and forwarded to Legal.",
                "Logged: 8 February 2018 - routine supplier correspondence only.",
            ]),
        Doc("statement", "WITNESS STATEMENT", STATEMENT, "Witness statement of the Mail Services Supervisor, Bentley Motors Limited",
            "BENTLEY MOTORS LIMITED", "Statement for use in criminal proceedings", [
                "Date of statement: 20 August 2018.",
                "I am the Mail Services Supervisor at Bentley Motors Limited, Crewe. I make this statement from my own knowledge.",
                f"I opened the envelope containing notice {NIP} in the post room on 7 February 2018 at 09:40.",
                "The envelope was postmarked 2 February 2018.",
                "I have checked the incoming post register for 5 and 6 February 2018. No notice from the Traffic Criminal "
                "Justice Unit reached the post room on or before 6 February 2018.",
                "This statement is true to the best of my knowledge and belief.",
            ]),
        Doc("response", "RESPONSE TO NOTICE", RESPONSE, f"Driver identification in response to notice {NIP}",
            "BENTLEY MOTORS LIMITED", "Legal department - Crewe", [
                "Date of response: 12 February 2018.",
                f"Bentley Motors Limited acknowledges notice {NIP}, received in the post room on 7 February 2018.",
                f"Bentley Motors Limited identifies the driver at the date and time of the offence as {DRIVER}.",
            ], person=DRIVER),
        Doc("summons", "SUMMONS", SUMMONS, "Summons - speeding offence",
            "MAGISTRATES' COURT", "Wimbledon", [
                "Date of summons: 2 July 2018.",
                "Court: Wimbledon Magistrates' Court.",
                f"Issued further to notice {NIP} and driver identification {RESPONSE}.",
                "You are summoned to answer a charge of driving in excess of the 40 mph speed limit on 23 January 2018 on the "
                "A40 Westway, Paddington.",
            ], person=DRIVER),
        Doc("record", "COURT RECORD", RECORD, "Record of hearing - plea",
            "MAGISTRATES' COURT", "Wimbledon", [
                "Date of hearing: 28 August 2018.",
                "Court: Wimbledon Magistrates' Court.",
                "Plea entered on behalf of the defendant: not guilty.",
                "Trial listed: 27 September 2018.",
                "The defence intimates a preliminary point as to the timing of service of the notice of intended prosecution.",
                f"Record made further to summons {SUMMONS}.",
            ], person=DRIVER),
    ]


def _render(doc: fitz.Document, d: Doc) -> int:
    page = doc.new_page(width=W, height=H)
    y = TOP
    head = [(d.org, "hebo", 11), (d.sub, "helv", 8.5), ("RECONSTRUCTION - SYNTHETIC DOCUMENT", "helv", 7.5), ("", "helv", 6),
            (f"{d.kind} No: {d.number}", "hebo", 12.5), (f"Subject: {d.subject}", "hebo", 9.5)]
    if d.person:
        head.append((f"Person concerned: {d.person}.", "helv", 9))
    head.append(("", "helv", 8))
    for text, font, size in head:
        if text:
            for ln in _wrap(text, font, size, W - 2 * MARGIN_X):
                page.insert_text((MARGIN_X, y), ln, fontname=font, fontsize=size)
                y += size * 1.45
        else:
            y += size * 1.45
    for para in d.lines:
        for ln in _wrap(para, "tiro", 10.5, W - 2 * MARGIN_X):
            page.insert_text((MARGIN_X, y), ln, fontname="tiro", fontsize=10.5)
            y += 15.2
        y += 4
    y += 14
    page.insert_text((MARGIN_X, y), "[signature]", fontname="tiro", fontsize=9)
    page.draw_line((MARGIN_X, H - 48), (W - MARGIN_X, H - 48), color=(0.6, 0.6, 0.6), width=0.5)
    page.insert_text((MARGIN_X, H - 34), f"Cote {d.cote} - sheet 1/1", fontname="helv", fontsize=8)
    page.insert_text((MARGIN_X + 130, H - 34), FOOTER, fontname="helv", fontsize=6.5)
    return y


def generate(out_dir: Path) -> dict:
    """Write dossier.pdf, ground_truth.json and manifest.json. Returns the ground truth."""
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = documents()
    pdf = fitz.open()
    pages: dict[str, list[int]] = {}
    texts: dict[int, str] = {}
    for k, d in enumerate(docs, 1):
        d.cote = f"D{k}"
        first = pdf.page_count
        _render(pdf, d)
        pages[d.key] = list(range(first + 1, pdf.page_count + 1))
        for p in pages[d.key]:
            texts[p] = pdf[p - 1].get_text()
    pdf.set_metadata({"title": TITLE, "author": "CASEBREAK synthetic generator",
                      "subject": "SYNTHETIC RECONSTRUCTION of the 2018 Beckham speeding case - not an authentic document"})
    pdf.save(out_dir / "dossier.pdf", deflate=True, garbage=3)
    n = pdf.page_count
    pdf.close()

    entries = []
    for d in docs:
        for g in d.gt:
            hit = [p for p in pages[d.key] if g["phrase"].lower() in texts[p].lower().replace("\n", " ")]
            entries.append({
                "nullity_id": g["nullity_id"], "expected": g["expected"], "injected": g["injected"], "note": g["note"],
                "cote": d.cote, "pv_number": d.number, "piece_type": d.kind, "pages": hit[:1] or pages[d.key],
                "piece_pages": pages[d.key],
                "affected_pages": sorted({p for key in g["affected_keys"] for p in pages[key][:1]}),
                "certainty": g.get("certainty", ""),
            })
    truth = {"title": TITLE, "pages": n, "pieces": len(docs), "entries": entries, "files": ["dossier.pdf"],
             "generator": "casebreak.synth.beckham v1", "synthetic": True, "real_outcome": REAL_OUTCOME, "sources": SOURCES}
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2))
    (out_dir / "manifest.json").write_text(json.dumps({"name": TITLE, "files": [{"path": "dossier.pdf"}]},
                                                      ensure_ascii=False, indent=2))
    return truth
