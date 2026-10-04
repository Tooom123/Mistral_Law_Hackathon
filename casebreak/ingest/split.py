"""② SPLIT + ③ CLASSIFY — cut the file into pieces (one PV = one piece) and give each a type and a category."""

from __future__ import annotations

import logging
import re

from casebreak.config import settings
from casebreak.llm import mistral
from casebreak.schemas import PageRec, Piece
from casebreak.text import norm

log = logging.getLogger(__name__)

HEADER_RE = re.compile(
    r"^\s*(proc[e]s[- ]?verbal|ordonnance|rapport|autorisation|r[e]quisitoire|arr[e]t)\b[^\n]{0,40}?\bn\s?[o0]\s*[:.]?\s*([\w/.-]+)",
    re.M,
)
COTE_RE = re.compile(r"\bcote\s+(d\d+)\b")
OBJET_RE = re.compile(r"^\s*objet\s*:\s*(.+)$", re.M)

# (keywords in "Objet", type, category) — first match wins, order matters.
TYPES: list[tuple[str, str, str]] = [
    ("placement en garde a vue", "PV_PLACEMENT_GAV", "GARDE_A_VUE"),
    ("notification des droits", "PV_NOTIFICATION_DROITS", "GARDE_A_VUE"),
    ("avis a avocat", "PV_AVIS_AVOCAT", "GARDE_A_VUE"),
    ("avis a famille", "PV_AVIS_FAMILLE", "GARDE_A_VUE"),
    ("examen medical", "PV_EXAMEN_MEDICAL", "GARDE_A_VUE"),
    ("prolongation", "AUTORISATION_PROLONGATION", "GARDE_A_VUE"),
    ("fin de garde a vue", "PV_FIN_GAV", "GARDE_A_VUE"),
    ("audition de personne gardee a vue", "PV_AUDITION_GAV", "AUDITION"),
    ("audition de temoin", "PV_AUDITION_TEMOIN", "AUDITION"),
    ("interpellation", "PV_INTERPELLATION", "INTERPELLATION"),
    ("perquisition", "PV_PERQUISITION", "PERQUISITION_SAISIE"),
    ("exploitation du scelle", "PV_EXPLOITATION", "EXPERTISE"),
    ("commission d'expert", "ORDONNANCE_EXPERTISE", "INSTRUCTION"),
    ("expertise", "RAPPORT_EXPERTISE", "EXPERTISE"),
    ("autorisation de geolocalisation", "AUTORISATION_GEOLOC", "GEOLOCALISATION"),
    ("geolocalisation", "PV_GEOLOCALISATION", "GEOLOCALISATION"),
    ("autorisant l'interception", "ORDONNANCE_INTERCEPTION", "INTERCEPTIONS"),
    ("retranscription", "PV_INTERCEPTION", "INTERCEPTIONS"),
    ("synthese des interceptions", "PV_ANNEXE", "INTERCEPTIONS"),
    ("requisitoire introductif", "REQUISITOIRE_INTRODUCTIF", "INSTRUCTION"),
    ("premiere comparution", "PV_MISE_EN_EXAMEN", "INSTRUCTION"),
    ("chambre de l'instruction", "ARRET_CHAMBRE_INSTRUCTION", "INSTRUCTION"),
    ("plainte", "PV_PLAINTE", "AUTRE"),
    ("videoprotection", "PV_VIDEOPROTECTION", "AUTRE"),
    ("constatations", "PV_CONSTATATIONS", "AUTRE"),
    ("compte rendu", "PV_CONSTATATIONS", "AUTRE"),
    ("requisition", "PV_REQUISITION", "AUTRE"),
    ("annexe", "PV_ANNEXE", "AUTRE"),
]
TYPE_CATEGORY = {t: c for _, t, c in TYPES} | {"PHOTO": "PERQUISITION_SAISIE", "INCONNU": "AUTRE"}


def classify_objet(objet_norm: str) -> tuple[str, str] | None:
    for kw, typ, cat in TYPES:
        if kw in objet_norm:
            return typ, cat
    return None


def _llm_classify(text: str) -> tuple[str, str] | None:
    if not settings.mistral:
        return None
    from casebreak.privacy import pseudonymize

    allowed = sorted({t for _, t, _ in TYPES})
    head = text[:1800]
    if settings.pseudonymize:
        head = pseudonymize.mask(head)[0]
    try:
        out = mistral.chat_json(
            "You classify documents from French criminal case files. Answer in JSON {\"type\": <one of the types>}.",
            f"Allowed types: {allowed}\n\nStart of the document:\n{head}", model=settings.fast_model, purpose="classify")
    except mistral.MistralUnavailable:
        return None
    t = out.get("type")
    return (t, TYPE_CATEGORY[t]) if t in TYPE_CATEGORY else None


def split_pieces(pages: list[PageRec]) -> list[Piece]:
    pieces: list[Piece] = []
    used_ids: set[str] = set()
    for pg in pages:
        if pg.kind == "image":
            pid = _unique(f"PH{pg.page}", used_ids)
            pieces.append(Piece(id=pid, type="PHOTO", category="PERQUISITION_SAISIE",
                                title=f"Photographie — {pg.file.split('/')[-1]}", pages=[pg.page], text=pg.text))
            continue
        n = norm(pg.text)
        m = HEADER_RE.search(_lines(pg.text, 14))
        if m or not pieces or pieces[-1].type == "PHOTO":
            cm = COTE_RE.search(n)
            cote = cm.group(1).upper() if cm else f"P{pg.page}"
            prev = _cote_num(pieces[-1].id) if pieces else 0
            if cm and prev and pg.ocr != "native" and _cote_num(cote) != prev + 1:
                cote = f"D{prev + 1}"  # OCR misread the cote number on a scan: trust the sequence
            pid = _unique(cote, used_ids)
            number = m.group(2).rstrip(".,;") if m else ""
            om = OBJET_RE.search(_lines(pg.text, 16))
            objet = om.group(1).strip() if om else ""
            pieces.append(Piece(id=pid, number=number, type="INCONNU", title=_raw_objet(pg.text) or objet,
                                pages=[pg.page], text=pg.text))
        else:
            pieces[-1].pages.append(pg.page)
            pieces[-1].text += "\n" + pg.text
    for pc in pieces:
        if pc.type == "PHOTO":
            continue
        got = classify_objet(norm(pc.title)) or classify_objet(norm(pc.text[:600]))
        if got is None:
            got = _llm_classify(pc.text)
            if got:
                pc.classified_by = "llm"
        if got is None:
            pc.type, pc.category, pc.classified_by = "INCONNU", "AUTRE", "unknown"
        else:
            pc.type, pc.category = got
    return pieces


def _lines(text: str, n: int) -> str:
    """First n lines, normalised, newlines kept (for ^-anchored header regexes)."""
    return "\n".join(norm(line) for line in text.split("\n")[:n])


def _raw_objet(text: str) -> str:
    for line in text.split("\n")[:16]:
        if norm(line).strip().startswith("objet"):
            return line.split(":", 1)[-1].strip()
    return ""


def _cote_num(pid: str) -> int:
    m = re.fullmatch(r"D(\d+)", pid)
    return int(m.group(1)) if m else 0


def _unique(pid: str, used: set[str]) -> str:
    base, k = pid, 2
    while pid in used:
        pid = f"{base}-{k}"
        k += 1
    used.add(pid)
    return pid
