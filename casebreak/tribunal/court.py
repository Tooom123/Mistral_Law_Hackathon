"""Adversarial tribunal on each alert (ARCHITECTURE §10, moonshot 1).

Défense argues from the check (statement, pages, cascade). Parquet objects: for each objection it looks
for a piece of the file that supports it (justification, waiver, authorization, purge, deadline…).
Président rules on what survives, with quotes — never on nullity or grief.

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
    "justification_retard": [("self", "delay_justification")],
    "renonciation": [("self", "lawyer_waiver")],
    "autorisation_procureur": [("self", "prosecutor_authorization")],
    "prolongation": [("custody", "extension_authorized")],
    "regime_derogatoire": [("custody", "special_regime")],
    "autorisation_jld": [("self", "jld_authorization")],
    "assentiment": [("self", "consent")],
}
# Keywords looked for in OTHER pieces of the file (piece "hors cote" arguments).
SEARCH = {
    "avis_ailleurs": ["procureur", "avisons"],
    "piece_hors_dossier": ["certificat", "autorisation"],
    "mention_ailleurs": ["fin de la garde", "heure de fin"],
    "scelle_ulterieur": ["scelle n"],
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
            return {"hint": hint, "text_fr": text, "strength": "appuyee", "source": a.src.model_dump(),
                    "why": "Pièce du dossier à l'appui."}
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
                    return {"hint": hint, "text_fr": text, "strength": "a_verifier",
                            "source": Src(doc_id="?", page=p.page, quote=line.strip()[:200]).model_dump(),
                            "why": "Mention possiblement pertinente ailleurs dans le dossier : à lire."}
    if hint == "grief":
        return {"hint": hint, "text_fr": text, "strength": "principe", "source": None,
                "why": "Question de droit réservée à l'avocat et au juge — jamais tranchée par l'outil."}
    return {"hint": hint, "text_fr": text, "strength": "sans_piece", "source": None,
            "why": "Argument possible, aucune pièce du dossier ne l'appuie."}


def _procedural(g: CaseGraph, c: Check) -> list[dict]:
    out = []
    ruling = next((n for n in g.nodes if n.subtype == "chamber_ruling"), None)
    if ruling and ruling.attr("date") and ruling.attr("date").src:
        out.append({"hint": "purge", "text_fr": "Les moyens antérieurs à l'arrêt de la chambre de l'instruction seraient purgés "
                    "(art. 174 CPP).", "strength": "appuyee", "source": ruling.attr("date").src.model_dump(),
                    "why": "Arrêt présent au dossier."})
    dl = deadlines(g)
    for a in dl["anchors"]:
        if all(r["days_left"] < 0 for r in a["regimes"]):
            out.append({"hint": "forclusion", "text_fr": "La requête serait tardive (forclusion).", "strength": "appuyee",
                        "source": a["source"], "why": f"Délais expirés dans les deux régimes depuis la mise en examen du {a['anchor']}."})
        elif any(r["days_left"] < 0 for r in a["regimes"]):
            out.append({"hint": "forclusion", "text_fr": "La requête pourrait être tardive selon le régime applicable.",
                        "strength": "a_verifier", "source": a["source"], "why": "Entrée en vigueur de la loi 2026-651 à vérifier."})
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
    defense = (f"{c.statement_fr} Ce constat repose sur le texte même de la procédure ({pg}). "
               f"Règle invoquée : {c.article} — {c.law_version}. "
               + (f"Sont potentiellement affectés {len(aff)} acte(s) à viser dans la requête : {aff_txt}."
                  if aff else "Aucun acte dépendant identifié dans le graphe."))
    objections = [_objection(h, c, n, g, pages) for h in (nl.prosecution_hints if nl else [])] if n else []
    if not any(o["hint"] == "grief" for o in objections):
        objections.append(_objection("grief", c, n, g, pages) if n else
                          {"hint": "grief", "text_fr": PROSECUTION["grief"], "strength": "principe", "source": None, "why": ""})
    objections += _procedural(g, c)
    strong = [o for o in objections if o["strength"] == "appuyee"]
    check = [o for o in objections if o["strength"] == "a_verifier"]
    if c.status == "needs_reading":
        verdict, label = "a_instruire", "À instruire"
        motive = "Le constat dépend d'une lecture humaine de la page (illisible, absent ou contradictoire)."
    elif strong:
        verdict, label = "fragilise", "Moyen fragilisé"
        motive = "Le parquet produit une pièce du dossier : " + "; ".join(
            f"« {o['source']['quote'][:120]} » (p. {o['source']['page']})" for o in strong if o.get("source"))
    elif check:
        verdict, label = "survit_sous_reserve", "Survit — points à vérifier"
        motive = "Aucune objection appuyée par une pièce ; des mentions ailleurs dans le dossier sont à lire."
    else:
        verdict, label = "survit", "Le moyen survit à la contradiction"
        motive = "Aucune objection du parquet n'est appuyée par une pièce du dossier."
    motive += " Le grief reste à démontrer par la défense ; l'outil ne se prononce ni sur le grief ni sur la nullité."
    return {"tier": "offline", "defense": {"role": "Défense", "text_fr": defense, "sources": [s.model_dump() for s in c.sources]},
            "parquet": {"role": "Parquet", "objections": objections},
            "president": {"role": "Président", "verdict": verdict, "label": label, "text_fr": motive}}


def deliberate(c: Check, g: CaseGraph) -> dict:
    base = _offline(c, g)
    if not settings.mistral:
        return base
    pages = {p.page: p for p in g.pages}
    excerpt = "\n\n".join(f"[page {s.page}]\n{pages[s.page].text[:2500]}" for s in c.sources if s.page in pages)
    masked, mapping = pseudonymize.mask(excerpt) if settings.pseudonymize else (excerpt, {})
    try:
        out = mistral.chat_json(
            "Tu simules un débat contradictoire sur un moyen de nullité possible en procédure pénale française. "
            "Défense, puis parquet (objections, chacune avec une citation exacte du dossier ou null), puis président. "
            "Le président ne conclut JAMAIS à la nullité ni au grief : il dit si le moyen survit à la contradiction. "
            "N'invente aucun article ni aucune décision. JSON: {\"defense\": str, \"objections\": [{\"text\": str, "
            "\"quote\": str|null, \"page\": int|null}], \"president\": str}",
            f"Constat : {c.statement_fr}\nRègle : {c.article} ({c.law_version})\nObjections déjà identifiées : "
            f"{[o['text_fr'] for o in base['parquet']['objections']]}\n\nPièces :\n{masked}", model=settings.judge_model)
    except mistral.MistralUnavailable:
        return base
    llm_obj = []
    for o in out.get("objections", [])[:6]:
        q = pseudonymize.unmask(o.get("quote") or "", mapping) if mapping else (o.get("quote") or "")
        page = o.get("page")
        ok = bool(q and page in pages and quote_on_page_loose(q, pages[page].text))
        llm_obj.append({"hint": "llm", "text_fr": pseudonymize.unmask(o.get("text", ""), mapping),
                        "strength": "appuyee" if ok else "sans_piece",
                        "source": {"doc_id": "?", "page": page, "quote": q} if ok else None,
                        "why": "Citation vérifiée sur la page." if ok else "Aucune citation vérifiée : argument non retenu comme appuyé."})
    base["tier"] = "mistral"
    base["defense"]["text_fr"] = pseudonymize.unmask(out.get("defense", base["defense"]["text_fr"]), mapping)
    base["parquet"]["objections"] += llm_obj
    base["president"]["llm_text_fr"] = pseudonymize.unmask(out.get("president", ""), mapping)
    return base


def tribunal_summary(checks: list[Check], g: CaseGraph) -> dict:
    out = {}
    for c in checks:
        if c.rank > 0:
            out[c.id] = _offline(c, g)["president"]["verdict"]
    return out

