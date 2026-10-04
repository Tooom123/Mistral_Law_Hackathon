"""④ EXTRACT — per piece, ACT nodes with attributes {value, page, quote}.

Offline: deterministic French patterns per piece type (accent- and OCR-tolerant).
With MISTRAL_API_KEY: unknown pieces are also sent to Mistral with a JSON schema; every returned
quote must be found on the page or the attribute is dropped.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from casebreak.config import settings
from casebreak.facts.normalize_time import parse_date, parse_time
from casebreak.llm import mistral
from casebreak.schemas import Attr, Node, PageRec, Piece, Src
from casebreak.text import PieceText, norm, quote_on_page_loose, squash

log = logging.getLogger(__name__)

SEAL = r"s\s?(\d{1,3})"
PV_NUM = r"n[o0]\s?(\d{4}/\d{3,6}/\d{1,3})"


@dataclass
class Draft:
    node: Node
    cites: list[tuple[str, Src]] = field(default_factory=list)  # PV numbers cited ("vu le PV n°…")
    seals_used: list[tuple[str, Src]] = field(default_factory=list)  # seals this act relies on
    seals_seized: list[str] = field(default_factory=list)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", norm(s)).strip("_")


def person_id(name: str) -> str:
    return "person:" + slug(name)


# ---------------------------------------------------------------- small parsers


def _time_in(text_norm: str) -> time | None:
    return parse_time(text_norm.replace("premier", "un"))


def _date_in(text_norm: str) -> date | None:
    return parse_date(text_norm.replace("premier", "un").replace("le 1er", "le 1er"))


def _combine(d: date | None, t: time | None) -> datetime | None:
    return datetime.combine(d, t) if d and t else None


class Ctx:
    """Extraction context for one piece."""

    def __init__(self, piece: Piece, pages: dict[int, PageRec]):
        self.piece = piece
        self.pt = PieceText(piece, pages)
        self.n = self.pt.norm
        self.pages = pages
        self.framework = self._framework()
        self.person = self._person()
        self.opener_dt, self.opener_date, self.opener_src, self.opener_time_unreadable = self._opener()

    def _framework(self) -> str:
        if "enquete de flagrance" in self.n:
            return "flagrance"
        if "enquete preliminaire" in self.n:
            return "preliminaire"
        if "information judiciaire" in self.n:
            return "instruction"
        return "unknown"

    def _person(self) -> str | None:
        h = self.pt.find(r"personne concernee\s*:\s*([a-z' -]{3,60}?)(?=\s{1,3}(?:le |l'an |nous|$))")
        if h:
            raw = self.pt.raw(h, 1).strip()
            return re.sub(r"\s+", " ", raw)
        return None

    def _opener(self) -> tuple[datetime | None, date | None, Src | None, bool]:
        pos = 0
        for ln in self.pt.orig.split("\n")[:60]:
            n = norm(ln).strip()
            if re.match(r"^(le|l'an)\s", n) and not n.startswith(("lecture", "le temoin", "le dispositif", "le quartier",
                                                                    "le certificat", "le prejudice", "le message")):
                d = _date_in(n)
                if d is None:
                    pos += len(ln) + 1
                    continue
                t = None
                parts = re.split(r"\s(?:a|à)\s", n, maxsplit=1)
                if len(parts) == 2:
                    t = _time_in(parts[1])
                    unreadable = t is None
                else:
                    unreadable = bool(re.search(r"\sa\S", n))  # OCR glued garbage after "à" (handwriting)
                return _combine(d, t), d, self.pt.src_at(pos, pos + len(ln)), unreadable
            pos += len(ln) + 1
        return None, None, None, False

    # ------------------------------------------------------------ helpers
    def hit(self, pattern: str):
        return self.pt.find(pattern)

    def time_attr(self, pattern: str, group: int = 1, day: date | None = None) -> Attr | None:
        h = self.pt.find(pattern)
        if not h:
            return None
        g = h.group(group)
        t = _time_in(g)
        d = _date_in(g) or day or self.opener_date
        if t is None:
            return Attr(value=None, src=h.src, status="unreadable")
        dt = _combine(d, t)
        return Attr(value=dt.isoformat() if dt else None, src=h.src, status="explicit")

    def flag(self, pattern: str, value=True) -> Attr | None:
        h = self.pt.find(pattern)
        return Attr(value=value, src=h.src) if h else None

    def opener_attr(self) -> Attr:
        if self.opener_dt:
            return Attr(value=self.opener_dt.isoformat(), src=self.opener_src)
        if self.opener_src is not None and self.opener_time_unreadable:
            return Attr(value=None, src=self.opener_src, status="unreadable")
        return Attr(value=None, src=self.opener_src, status="missing")

    def cites(self) -> list[tuple[str, Src]]:
        return [(h.group(1), h.src) for h in self.pt.find_all(r"vu (?:le|l')[^.]{0,40}?proces[- ]verbal[^.]{0,30}?" + PV_NUM)] + \
               [(h.group(1), h.src) for h in self.pt.find_all(r"\(proces[- ]verbal " + PV_NUM + r"\)")] + \
               [(h.group(1), h.src) for h in self.pt.find_all(r"(?:ordonnance|autorisation) " + PV_NUM)]

    def node(self, subtype: str, category: str, label: str, suffix: str = "") -> Node:
        nid = f"act:{self.piece.id}:{subtype}{suffix}"
        return Node(id=nid, type="ACT", category=category, subtype=subtype, label=label, framework=self.framework,
                    doc_ids=[self.piece.id], pages=list(self.piece.pages),
                    person=person_id(self.person) if self.person else None)


def _dt(a: Attr | None) -> datetime | None:
    return datetime.fromisoformat(a.value) if a and isinstance(a.value, str) else None


# ---------------------------------------------------------------- extractors per type


def _interpellation(c: Ctx) -> list[Draft]:
    n = c.node("interpellation", "INTERPELLATION", "Arrest")
    n.attrs["arrest_time"] = c.opener_attr()
    pa = c.time_attr(r"place en garde a vue (a [^,.;]{2,40}?)(?: par|[,.;])")
    if pa:
        n.attrs["placed_at_stated"] = pa
    g = c.flag(r"dispositif de geolocalisation")
    if g:
        n.attrs["geoloc_used"] = g
    n.start = _dt(n.attrs["arrest_time"])
    m = c.pt.find(r"interpellation de ([a-z' -]{3,50}?), ne le")
    if m and not c.person:
        c.person = c.pt.raw(m, 1)
        n.person = person_id(c.person)
    return [Draft(n, cites=c.cites())]


def _placement(c: Ctx) -> list[Draft]:
    n = c.node("placement_gav", "GARDE_A_VUE", "Placed in custody")
    a = c.time_attr(r"decidons de placer en garde a vue .{0,80}?a compter de ([^.,;]{2,40})")
    n.attrs["custody_start"] = a if a and a.value else c.opener_attr()
    obj = c.hit(r"aux motifs? que [^.]{20,400}")
    if obj:
        n.attrs["objectives_text"] = Attr(value=squash(c.pt.raw(obj)), src=obj.src)
    else:
        weak = c.hit(r"pour les necessites de l'enquete")
        n.attrs["objectives_text"] = Attr(value=None, src=weak.src if weak else None, status="missing")
    pr = c.time_attr(r"avisons (a [^m]{2,40}?) m(?:me|\.|onsieur|adame)? ?l[ea] procureure? de la republique")
    n.attrs["prosecutor_informed_at"] = pr or Attr(value=None, status="missing")
    nf = c.hit(r"ne pas comprendre la langue francaise et s'exprimer en langue ([a-z]+)")
    if nf:
        n.attrs["understands_french"] = Attr(value=False, src=nf.src)
        n.attrs["language"] = Attr(value=nf.group(1), src=nf.src)
    else:
        f = c.hit(r"comprendre parfaitement la langue francaise")
        n.attrs["understands_french"] = Attr(value=True, src=f.src) if f else Attr(value=None, status="missing")
    rg = c.hit(r"regime derogatoire[^.]{0,120}")
    if rg:
        n.attrs["special_regime"] = Attr(value=squash(c.pt.raw(rg)), src=rg.src)
    n.start = _dt(n.attrs["custody_start"])
    return [Draft(n, cites=c.cites())]


def _notification(c: Ctx) -> list[Draft]:
    n = c.node("rights_notification", "GARDE_A_VUE", "Rights notification")
    n.attrs["notified_at"] = c.opener_attr()
    st = c.time_attr(r"place en garde a vue ce jour (a [^,.;]{2,40})")
    if st:
        n.attrs["custody_start_stated"] = st
    ip = c.hit(r"par l'intermediaire de ([a-z' .-]{3,50}?), interprete en langue ([a-z]+)")
    if ip:
        n.attrs["interpreter_present"] = Attr(value=True, src=ip.src)
    else:
        fr_ = c.hit(r"en langue francaise")
        n.attrs["interpreter_present"] = Attr(value=False, src=fr_.src if fr_ else None,
                                              status="explicit" if fr_ else "missing")
    j = c.hit(r"notification des droits a ete differee en raison de [^.]{5,200}")
    if j:
        n.attrs["delay_justification"] = Attr(value=squash(c.pt.raw(j)), src=j.src)
    for key, yes, no in [
        ("lawyer_requested", r"souhaiter etre assistee? par maitre [^.]{3,80}", r"ne pas souhaiter etre assistee? par un avocat"),
        ("doctor_requested", r"(?<!pas )souhaiter etre examinee? par un medecin", r"ne pas souhaiter etre examinee? par un medecin"),
        ("family_requested", r"(?<!pas )souhaiter faire prevenir [^.]{3,80}", r"ne pas souhaiter faire prevenir"),
    ]:
        h = c.hit(r"declare " + yes)
        if h:
            n.attrs[key] = Attr(value=True, src=h.src)
        else:
            h = c.hit(r"declare " + no)
            n.attrs[key] = Attr(value=False, src=h.src) if h else Attr(value=None, status="missing")
    s = c.hit(r"persiste et signe")
    r = c.hit(r"refuse de signer")
    n.attrs["signed"] = Attr(value=True, src=s.src) if s else Attr(value=False, src=r.src) if r else Attr(value=None, status="missing")
    n.start = _dt(n.attrs["notified_at"])
    return [Draft(n, cites=c.cites())]


def _simple(subtype: str, label: str, key: str):
    def f(c: Ctx) -> list[Draft]:
        n = c.node(subtype, "GARDE_A_VUE", label)
        n.attrs[key] = c.opener_attr()
        n.start = _dt(n.attrs[key])
        return [Draft(n, cites=c.cites())]
    return f


def _prolongation(c: Ctx) -> list[Draft]:
    n = c.node("extension", "GARDE_A_VUE", "Extension authorisation")
    n.attrs["authorized_at"] = c.opener_attr()
    a = c.hit(r"autorisons la prolongation de la garde a vue[^.]{0,200}")
    if a:
        n.attrs["extension_authorized"] = Attr(value=True, src=a.src)
        fr_ = c.time_attr(r"a compter du ([^.]{8,40})")
        if fr_:
            n.attrs["extension_from"] = fr_
    n.start = _dt(n.attrs["authorized_at"])
    return [Draft(n, cites=c.cites())]


def _fin(c: Ctx) -> list[Draft]:
    n = c.node("custody_end", "GARDE_A_VUE", "End of custody")
    end = c.time_attr(r"mettons fin a la (?:mesure de )?garde a vue de [a-z' -]{3,50}? (a [^.]{2,40})")
    if end is None or end.value is None:
        end = c.opener_attr() if c.opener_dt else end
    if end is None:
        h = c.hit(r"mettons fin a la (?:mesure de )?garde a vue[^.]{0,80}")
        end = Attr(value=None, src=h.src if h else c.opener_src, status="missing")
    n.attrs["end_time"] = end
    n.start = _dt(end)
    n.attrs["end_date"] = Attr(value=c.opener_date.isoformat() if c.opener_date else None, src=c.opener_src)
    return [Draft(n, cites=c.cites())]


def _audition(c: Ctx) -> list[Draft]:
    witness = c.piece.type == "PV_AUDITION_TEMOIN"
    n = c.node("hearing_witness" if witness else "hearing", "AUDITION",
               "Witness hearing" if witness else "Custody hearing")
    n.attrs["start"] = c.opener_attr()
    e = c.time_attr(r"fin de l'audition (a [^.]{2,40})")
    if e:
        n.attrs["end"] = e
    w = c.hit(r"entendons en qualite de temoin ([a-z' -]{3,50}?), ne le")
    if w and not c.person:
        c.person = c.pt.raw(w, 1)
        n.person = person_id(c.person)
    if not witness:
        n.attrs["in_custody"] = Attr(value=True, src=(c.hit(r"actuellement en garde a vue") or c.hit(r"entendons")).src)
        p = c.hit(r"en presence de maitre [^.]{3,80}")
        a = c.hit(r"hors la presence de (?:l'|son )avocat[^.]{0,60}|ne s'etant pas presentee?")
        if p:
            n.attrs["lawyer_present"] = Attr(value=True, src=p.src)
        elif a:
            n.attrs["lawyer_present"] = Attr(value=False, src=a.src)
            ln = c.time_attr(r"avisee? (a [^,]{2,40}),")
            if ln:
                n.attrs["lawyer_notified_at_stated"] = ln
        else:
            n.attrs["lawyer_present"] = Attr(value=None, status="missing")
        wv = c.hit(r"renonce expressement a l'assistance d'un avocat[^.]{0,120}")
        if wv:
            n.attrs["lawyer_waiver"] = Attr(value=True, src=wv.src)
        au = c.hit(r"autorisation ecrite[^.]{0,40}procureur[^.]{0,120}")
        if au:
            n.attrs["prosecutor_authorization"] = Attr(value=True, src=au.src)
    ip = c.hit(r"assistance de ([a-z' .-]{3,50}?), interprete en langue ([a-z]+)")
    if ip:
        n.attrs["interpreter_present"] = Attr(value=True, src=ip.src)
    seals = [(f"S{h.group(1)}", h.src) for h in c.pt.find_all(r"exploitation du scelle n[o0]\s?" + SEAL)]
    n.start, n.end = _dt(n.attrs["start"]), _dt(n.attrs.get("end"))
    return [Draft(n, cites=c.cites(), seals_used=seals)]


def _perquisition(c: Ctx) -> list[Draft]:
    n = c.node("search", "PERQUISITION_SAISIE", "Search")
    n.attrs["start"] = c.opener_attr()
    e = c.time_attr(r"fin des operations (a [^.]{2,40})")
    if e:
        n.attrs["end"] = e
    t = c.hit(r"nous transportons ([^,]{5,90}?), sis ([^.]{5,80})")
    if t:
        n.attrs["place"] = Attr(value=squash(c.pt.raw(t)), src=t.src)
        n.attrs["is_home"] = Attr(value="domicile" in t.group(1), src=t.src)
    occ = c.hit(r"en presence constante de [^.]{3,60}occupant des lieux")
    wit = c.hit(r"en presence de deux temoins[^.]{0,120}")
    plain = c.hit(r"procedons a la perquisition des lieux")
    n.attrs["occupant_present"] = Attr(value=bool(occ), src=(occ or plain or wit).src if (occ or plain or wit) else None,
                                       status="explicit" if (occ or plain or wit) else "missing")
    n.attrs["witnesses_present"] = Attr(value=bool(wit), src=(wit or occ or plain).src if (wit or occ or plain) else None,
                                        status="explicit" if (wit or occ or plain) else "missing")
    hw = c.hit(r"assentiment expres[^.]{0,80}(?:ecrite? de sa main|manuscrite)[^»]{0,140}")
    vb = c.hit(r"donne verbalement son accord[^.]{0,60}")
    if hw:
        n.attrs["consent"] = Attr(value="handwritten", src=hw.src)
    elif vb:
        n.attrs["consent"] = Attr(value="verbal", src=vb.src)
    else:
        n.attrs["consent"] = Attr(value=None, status="missing")
    jl = c.hit(r"autorisation ecrite et motivee du juge des libertes[^,]{0,80}")
    if jl:
        n.attrs["jld_authorization"] = Attr(value=True, src=jl.src)
    n.start, n.end = _dt(n.attrs["start"]), _dt(n.attrs.get("end"))
    if n.start is None and n.end is not None:
        n.attrs["start_date_only"] = Attr(value=(c.opener_date or n.end.date()).isoformat(), src=c.opener_src)
    drafts = [Draft(n, cites=c.cites())]
    # seizures: one ACT per seized item
    for k, h in enumerate(c.pt.find_all(r"- ([^;]{4,120}?), (place sous scelle n[o0]\s?" + SEAL + r"|saisi)\s?;")):
        desc = squash(c.pt.raw(h, 1))
        seal = f"S{h.group(3)}" if h.group(3) else None
        s = c.node("seizure", "PERQUISITION_SAISIE", f"Seizure — {desc[:40]}", suffix=f":{k}")
        s.attrs["item"] = Attr(value=desc, src=h.src)
        s.attrs["seal_number"] = Attr(value=seal, src=h.src) if seal else Attr(value=None, src=h.src, status="missing")
        s.start = n.start or (n.end - timedelta(minutes=1) if n.end else None)
        s.label = f"Seizure {seal}" if seal else "Seizure without seal"
        drafts.append(Draft(s, seals_seized=[seal] if seal else []))
    return drafts


def _exploitation(c: Ctx) -> list[Draft]:
    n = c.node("seal_analysis", "EXPERTISE", "Seal analysis")
    n.attrs["start"] = c.opener_attr()
    seals = [(f"S{h.group(1)}", h.src) for h in c.pt.find_all(r"scelles? n[o0]\s?" + SEAL)]
    if seals:
        n.label = f"Analysis of {seals[0][0]}"
    n.start = _dt(n.attrs["start"])
    return [Draft(n, cites=c.cites(), seals_used=seals)]


def _expertise(c: Ctx) -> list[Draft]:
    n = c.node("lab_report", "EXPERTISE", "Expert report")
    n.attrs["start"] = c.opener_attr()
    h = c.hit(r"analyse genetique des scelles ([^.]{3,80})")
    seals = []
    if h:
        seals = [(f"S{m}", h.src) for m in re.findall(SEAL, h.group(1))]
        n.label = "DNA analysis " + ", ".join(s for s, _ in seals)
    n.attrs["seals_analysed"] = Attr(value=", ".join(s for s, _ in seals) or None, src=h.src if h else None)
    n.start = _dt(n.attrs["start"])
    return [Draft(n, cites=c.cites(), seals_used=seals)]


def _geoloc(c: Ctx) -> list[Draft]:
    n = c.node("geolocation", "GEOLOCALISATION", "GPS tracker fitted")
    n.attrs["start"] = c.opener_attr()
    a = c.hit(r"en execution de l'autorisation( n[o0]\s?(\d{4}/\d{3,6}/\d{1,3}))? delivree par [^,]{5,80} en date du (\d{2}/\d{2}/\d{4})")
    if a:
        n.attrs["authorization_ref"] = Attr(value=a.group(2) or a.group(3), src=a.src)
        n.attrs["authorization_date"] = Attr(value=a.group(3), src=a.src)
    n.start = _dt(n.attrs["start"])
    return [Draft(n, cites=c.cites())]


def _court(subtype: str, category: str, label: str):
    def f(c: Ctx) -> list[Draft]:
        n = c.node(subtype, category, label)
        n.attrs["date"] = c.opener_attr()
        n.start = _dt(n.attrs["date"])
        if subtype == "mise_en_examen":
            m = c.hit(r"mettons en examen ([a-z' -]{3,50}?) des chefs")
            if m:
                n.attrs["person_name"] = Attr(value=c.pt.raw(m, 1), src=m.src)
        if subtype == "interception":
            o = c.hit(r"en execution de l'ordonnance" + r"(?: n[o0]\s?(\d{4}/\d{3,6}/\d{1,3}))?[^,]{0,60}")
            if o:
                n.attrs["authorization_ref"] = Attr(value=o.group(1) or "cited", src=o.src)
        if subtype == "geolocation_authorization":
            n.attrs["authorizes"] = Attr(value=True, src=c.opener_src)
        return [Draft(n, cites=c.cites())]
    return f


OTHER_LABELS = {"PV_PLAINTE": "Complaint", "PV_CONSTATATIONS": "Findings report", "PV_VIDEOPROTECTION": "CCTV review",
                "PV_REQUISITION": "Information request", "PV_ANNEXE": "Annex", "INCONNU": "Document"}


def _other(c: Ctx) -> list[Draft]:
    label = OTHER_LABELS.get(c.piece.type) or c.piece.title.capitalize()[:60] or "Document"
    n = c.node("other", c.piece.category if c.piece.category != "AUTRE" else "AUTRE", label)
    n.attrs["date"] = c.opener_attr()
    n.start = _dt(n.attrs["date"])
    return [Draft(n, cites=c.cites())]


def _photo(c: Ctx) -> list[Draft]:
    pg = c.pages[c.piece.pages[0]]
    n = c.node("photo", "PERQUISITION_SAISIE", "Photograph")
    stamp = pg.exif.get("DateTimeOriginal") or pg.exif.get("DateTime")
    if stamp:
        try:
            dt = datetime.strptime(stamp, "%Y:%m:%d %H:%M:%S")
            n.attrs["exif_time"] = Attr(value=dt.isoformat(), src=None, status="explicit")
            n.start = dt
        except ValueError:
            pass
    m = c.hit(r"scell[ea]\s*n[o0°]?\s?" + SEAL)
    seals = []
    if m:
        seal = f"S{m.group(1)}"
        n.attrs["seal_label"] = Attr(value=seal, src=m.src)
        n.label = f"Photo of seal {seal}"
        seals = [(seal, m.src)]
    return [Draft(n, seals_used=seals)]


EXTRACTORS = {
    "PV_INTERPELLATION": _interpellation,
    "PV_PLACEMENT_GAV": _placement,
    "PV_NOTIFICATION_DROITS": _notification,
    "PV_AVIS_AVOCAT": _simple("lawyer_notice", "Lawyer notified", "lawyer_notified_at"),
    "PV_AVIS_FAMILLE": _simple("family_notice", "Relative informed", "family_notified_at"),
    "PV_EXAMEN_MEDICAL": _simple("medical_exam", "Medical examination", "exam_at"),
    "AUTORISATION_PROLONGATION": _prolongation,
    "PV_FIN_GAV": _fin,
    "PV_AUDITION_GAV": _audition,
    "PV_AUDITION_TEMOIN": _audition,
    "PV_PERQUISITION": _perquisition,
    "PV_EXPLOITATION": _exploitation,
    "RAPPORT_EXPERTISE": _expertise,
    "PV_GEOLOCALISATION": _geoloc,
    "AUTORISATION_GEOLOC": _court("geolocation_authorization", "GEOLOCALISATION", "Geolocation authorisation"),
    "ORDONNANCE_INTERCEPTION": _court("interception_order", "INTERCEPTIONS", "Interception order"),
    "PV_INTERCEPTION": _court("interception", "INTERCEPTIONS", "Interceptions — transcript"),
    "REQUISITOIRE_INTRODUCTIF": _court("opening", "INSTRUCTION", "Opening of judicial investigation"),
    "PV_MISE_EN_EXAMEN": _court("mise_en_examen", "INSTRUCTION", "Formal charge"),
    "ORDONNANCE_EXPERTISE": _court("expert_order", "INSTRUCTION", "Expert appointment"),
    "ARRET_CHAMBRE_INSTRUCTION": _court("chamber_ruling", "INSTRUCTION", "Investigating chamber ruling"),
    "PHOTO": _photo,
}


LLM_SCHEMA = (
    '{"acts": [{"subtype": str, "category": one of [INTERPELLATION, GARDE_A_VUE, AUDITION, PERQUISITION_SAISIE, '
    'EXPERTISE, INSTRUCTION, INTERCEPTIONS, GEOLOCALISATION, AUTRE], "label": str, '
    '"attrs": {name: {"value": str|bool|null, "page": int, "quote": str (verbatim, copied from the page)}}}]}'
)


def _llm_extract(c: Ctx) -> list[Draft]:
    """Mistral extraction for pieces the patterns don't know. Quotes are verified; unverified attrs are dropped."""
    from casebreak.privacy import pseudonymize

    pages_txt = "\n\n".join(f"[page {p}]\n{c.pages[p].text}" for p in c.piece.pages[:6])
    masked, mapping = pseudonymize.mask(pages_txt) if settings.pseudonymize else (pages_txt, {})
    try:
        out = mistral.chat_json(
            "You extract the procedural acts from a document of a French criminal case file. You make no legal "
            "qualification. Every attribute must quote a passage copied word for word. Answer in JSON: " + LLM_SCHEMA,
            masked, model=settings.extract_model)
    except mistral.MistralUnavailable as e:
        log.warning("LLM extraction skipped: %s", e)
        return []
    drafts = []
    for k, a in enumerate(out.get("acts", [])[:6]):
        n = c.node(slug(a.get("subtype", "act")) or "act", a.get("category", "AUTRE"), a.get("label", "Act")[:60], suffix=f":llm{k}")
        for name, v in (a.get("attrs") or {}).items():
            q = pseudonymize.unmask(str(v.get("quote", "")), mapping) if mapping else str(v.get("quote", ""))
            page = v.get("page") if v.get("page") in c.piece.pages else c.piece.pages[0]
            if q and quote_on_page_loose(q, c.pages[page].text):
                n.attrs[slug(name)] = Attr(value=v.get("value"), src=Src(doc_id=c.piece.id, page=page, quote=q),
                                           status="inferred")
        n.start = c.opener_dt
        drafts.append(Draft(n))
    return drafts


def extract_piece(piece: Piece, pages: dict[int, PageRec]) -> list[Draft]:
    c = Ctx(piece, pages)
    fn = EXTRACTORS.get(piece.type)
    if fn is None:
        drafts = _llm_extract(c) if (settings.mistral and piece.type == "INCONNU") else []
        drafts = drafts or _other(c)
    else:
        drafts = fn(c)
    for d in drafts:
        if d.node.person is None and c.person:
            d.node.person = person_id(c.person)
        d.node.attrs.setdefault("_person_name", Attr(value=c.person, src=None)) if c.person else None
    return drafts
