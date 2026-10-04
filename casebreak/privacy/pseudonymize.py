"""Privacy shield — pseudonymise names, addresses, birth dates and phone numbers before any external call.

Deterministic and reversible inside one call: `mask()` returns the masked text and the mapping,
`unmask()` puts the originals back into the model's answer (quotes are then verified on the page).
"""

from __future__ import annotations

import re

_UP = r"[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ][A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ'-]{1,}"
_CAP = r"[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ][a-zàâäçéèêëîïôöùûü'-]{1,}"
_STOP = {"PV", "OPJ", "APJ", "CPP", "N", "D", "S", "LE", "LA", "LES", "DE", "DU", "ET", "EN", "AU", "DES", "SMS",
         "POLICE", "NATIONALE", "PROCÈS-VERBAL", "PROCES-VERBAL", "OBJET", "AFFAIRE", "TRIBUNAL", "JUDICIAIRE",
         "RAPPORT", "ORDONNANCE", "AUTORISATION", "ARRÊT", "QUESTION", "RÉPONSE", "COPIE", "CONFORME", "VOL",
         "AVEC", "EFFRACTION", "BIJOUTERIE", "FILS", "SORTANT", "ENTRANT", "RELAIS", "ANNEXE", "GARDE", "VUE",
         "PERQUISITION", "SAISIES", "AUDITION", "TÉMOIN", "NOTIFICATION", "DROITS", "PLACEMENT", "FIN", "AVIS",
         "AVOCAT", "FAMILLE", "EXAMEN", "MÉDICAL", "INTERPELLATION", "SCELLÉ", "RÉQUISITOIRE", "INTRODUCTIF",
         "RECEL", "AGGRAVÉ", "ESCROQUERIE", "BANDE", "EXPLOITATION", "VALMORIN", "LABORATOIRE", "GÉNÉTIQUE",
         "EXPERTISE", "INTERCEPTIONS", "RETRANSCRIPTION", "GÉOLOCALISATION", "PROLONGATION", "DÉPÔT", "PLAINTE",
         "CONSTATATIONS", "TRANSPORT", "LIEUX", "SUR", "RÉQUISITION", "SYNTHÈSE", "COMPTE", "RENDU", "ENQUÊTE",
         "DONNÉES", "BORNAGE", "RELEVÉ", "DÉTAILLÉ", "COMMUNICATIONS", "NORD", "SUD", "EST", "GARE", "HALLES", "ZI"}

PATTERNS = [
    ("ADRESSE", re.compile(r"\b\d{1,3},? (?:rue|allée|allee|chemin|impasse|boulevard|place|avenue) [^,.;\n]{3,40}")),
    ("NAISSANCE", re.compile(r"\bné(?:e)? le \d{2}/\d{2}/\d{4}")),
    ("TEL", re.compile(r"\+33(?: ?\d{1,2}){5}")),
    ("NOM", re.compile(rf"\b({_UP}) ({_CAP})\b")),  # VASSEUR Théo
    ("NOM", re.compile(rf"\b({_CAP}) ({_UP})\b")),  # Théo VASSEUR
]


def mask(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    counters: dict[str, int] = {}

    def token(kind: str, original: str) -> str:
        if original in reverse:
            return reverse[original]
        counters[kind] = counters.get(kind, 0) + 1
        tok = f"[{kind}_{counters[kind]}]"
        mapping[tok] = original
        reverse[original] = tok
        return tok

    out = text
    for kind, rx in PATTERNS:
        def repl(m: re.Match) -> str:
            s = m.group(0)
            if kind == "NOM":
                up = m.group(1) if m.group(1).isupper() else m.group(2)
                if up.strip("'-") in _STOP or len(up) < 3:
                    return s
            return token(kind, s)
        out = rx.sub(repl, out)
    return out, mapping


def unmask(text: str, mapping: dict[str, str]) -> str:
    for tok, orig in mapping.items():
        text = text.replace(tok, orig)
    return text


def mask_value(text: str) -> str:
    """One-way masking for display (UI pseudonymisation toggle)."""
    return mask(text)[0]
