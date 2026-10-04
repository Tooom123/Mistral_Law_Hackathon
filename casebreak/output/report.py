"""Report — « moyens de nullité à examiner », each with pages and acts to name. Markdown and PDF."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ORANGE = colors.HexColor("#FA500F")
INK = colors.HexColor("#151524")
GREY = colors.HexColor("#6B6B78")

DISCLAIMER = ("Document de travail généré par CASEBREAK à partir d'un dossier synthétique. Il liste des moyens à "
              "examiner : il ne conclut ni à la nullité ni au grief (art. 171 et 802 CPP). Chaque constat renvoie à une "
              "page du dossier ; le contenu juridique n'a pas été validé par un avocat.")


def _order(cards: list[dict]) -> list[dict]:
    keep = [c for c in cards if c["review"].get("decision") != "rejected"]
    return sorted(keep, key=lambda c: (c["review"].get("decision") != "accepted", -c["rank"]))


def markdown(title: str, cards: list[dict], deadline: dict, mode: str = "defense") -> str:
    parquet = mode == "parquet"
    head = "Audit de régularité — points à corriger" if parquet else "Moyens de nullité à examiner"
    lines = [f"# {head}", "", f"**Dossier :** {title}  ", f"**Généré le :** {datetime.now():%d/%m/%Y %H:%M}  ",
             f"**Mode :** {'parquet (audit de régularité)' if parquet else 'défense'}", "", f"> {DISCLAIMER}", ""]
    if deadline.get("anchors"):
        lines += ["## Délai (à vérifier)", ""]
        for a in deadline["anchors"]:
            lines.append(f"- **{a['person']}** — mise en examen le {a['anchor']} :")
            for r in a["regimes"]:
                lines.append(f"  - {r['months']} mois ({r['label']}) → **{r['deadline']}** ({r['days_left']} jours)")
        lines += ["", f"_{deadline['note']}_", ""]
    rejected = 0
    lines += [f"## {'Points' if parquet else 'Moyens'} ({len(_order(cards))})", ""]
    for i, c in enumerate(_order(cards), 1):
        st = {"accepted": "retenu par l'avocat", "pending": "à examiner"}.get(c["review"].get("decision"), "")
        lines += [f"### {i}. {c['title']} — {c['nullity_id']}",
                  f"*{c['headline']}* · certitude : **{c['certainty_fr']}** · {st}", "",
                  f"**Constat.** {c['what']}", "",
                  f"**Règle.** {c['why']['article']} — {c['why']['law_version']}", ""]
        lines.append("**Sources.**")
        for s in c["where"]:
            num = f"PV n° {s['piece']['number']}, " if s.get("piece") and s["piece"].get("number") else ""
            lines.append(f"- {num}cote {s['doc_id']}, p. {s['page']} : « {s['quote']} »")
        if c["why"]["affected"]:
            lines += ["", f"**Actes potentiellement affectés à viser ({len(c['why']['affected'])}).**"]
            for a in c["why"]["affected"]:
                pcs = ", ".join(f"cote {p['cote']}" + (f" (PV n° {p['number']})" if p["number"] else "") for p in a["pieces"])
                dashed = " — lien déduit par le modèle" if a["origin"] == "llm_inferred" else ""
                lines.append(f"- {a['label']} — {pcs}{dashed}")
        if c.get("tribunal"):
            t = c["tribunal"]
            lines += ["", f"**Contradiction simulée.** {t['president']['label']} — {t['president']['text_fr']}"]
            for o in t["parquet"]["objections"]:
                src = f" (p. {o['source']['page']})" if o.get("source") else ""
                lines.append(f"- Parquet : {o['text_fr']} [{o['strength'].replace('_', ' ')}]{src}")
        if c.get("precedents", {}).get("results"):
            lines += ["", "**Précédents récupérés (Judilibre).**"]
            for p in c["precedents"]["results"]:
                lines.append(f"- Crim., {p['date']}, n° {p['number']} — {p.get('solution') or ''} — {p['url']}")
        lines += ["", "**À faire.**"] + [f"- {s}" for s in c["next"]]
        if c["why"]["legal_todo"]:
            lines += [f"- TODO(legal) : {t}" for t in c["why"]["legal_todo"]]
        lines += ["", "---", ""]
    rejected = sum(1 for c in cards if c["review"].get("decision") == "rejected")
    if rejected:
        lines.append(f"_{rejected} alerte(s) écartée(s) par l'avocat, non reprises._")
    return "\n".join(lines)


def pdf(title: str, cards: list[dict], deadline: dict, mode: str = "defense") -> bytes:
    parquet = mode == "parquet"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=title, author="CASEBREAK")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=22, textColor=INK, alignment=TA_LEFT,
                        spaceAfter=4)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=INK, spaceBefore=10)
    H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=11.5, textColor=INK, spaceBefore=6)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.4, leading=13, textColor=INK)
    S = ParagraphStyle("s", parent=B, fontSize=8.2, leading=11, textColor=GREY)
    Q = ParagraphStyle("q", parent=B, fontName="Times-Italic", fontSize=9.6, leftIndent=8, borderPadding=4,
                       textColor=colors.HexColor("#2B2B3A"))
    TAG = ParagraphStyle("tag", parent=S, textColor=ORANGE, fontName="Helvetica-Bold")

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = [Paragraph("CASEBREAK", TAG),
             Paragraph("Audit de régularité — points à corriger" if parquet else "Moyens de nullité à examiner", H1),
             Paragraph(f"{esc(title)} · généré le {datetime.now():%d/%m/%Y %H:%M}", S), Spacer(1, 4),
             HRFlowable(width="100%", thickness=2, color=ORANGE), Spacer(1, 6), Paragraph(esc(DISCLAIMER), S)]
    if deadline.get("anchors"):
        story.append(Paragraph("Délai — à vérifier", H2))
        rows = [["Personne", "Mise en examen", "Régime", "Date limite", "Jours"]]
        for a in deadline["anchors"]:
            for r in a["regimes"]:
                rows.append([a["person"], a["anchor"], f"{r['months']} mois — {r['label']}", r["deadline"], str(r["days_left"])])
        t = Table(rows, colWidths=[38 * mm, 26 * mm, 62 * mm, 24 * mm, 14 * mm])
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                               ("LINEBELOW", (0, 0), (-1, 0), 1, INK), ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                                                                         [colors.white, colors.HexColor("#FFF4EC")])]))
        story += [t, Paragraph(esc(deadline["note"]), S)]
    ordered = _order(cards)
    story.append(Paragraph(f"{'Points' if parquet else 'Moyens'} ({len(ordered)})", H2))
    for i, c in enumerate(ordered, 1):
        block = [Paragraph(f"{i}. {esc(c['title'])} <font color='#FA500F'>· {c['nullity_id']}</font>", H3),
                 Paragraph(f"{esc(c['headline'])} · certitude : <b>{c['certainty_fr']}</b>", S),
                 Paragraph(f"<b>Constat.</b> {esc(c['what'])}", B),
                 Paragraph(f"<b>Règle.</b> {esc(c['why']['article'])} — {esc(c['why']['law_version'])}", B)]
        for s in c["where"]:
            num = f"PV n° {s['piece']['number']}, " if s.get("piece") and s["piece"].get("number") else ""
            block.append(Paragraph(f"« {esc(s['quote'])} » <font size=7 color='#6B6B78'>— {num}cote {s['doc_id']}, p. {s['page']}</font>", Q))
        if c["why"]["affected"]:
            items = "; ".join(f"{esc(a['label'])} ({', '.join(p['cote'] for p in a['pieces'])})" for a in c["why"]["affected"])
            block.append(Paragraph(f"<b>Actes potentiellement affectés ({len(c['why']['affected'])}).</b> {items}", B))
        if c.get("tribunal"):
            block.append(Paragraph(f"<b>Contradiction simulée.</b> {esc(c['tribunal']['president']['label'])}.", B))
        block.append(Paragraph("<b>À faire.</b> " + esc(" ".join(c["next"])), B))
        block += [Spacer(1, 3), HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#E7E2DC"))]
        story.append(KeepTogether(block))
    doc.build(story)
    return buf.getvalue()
