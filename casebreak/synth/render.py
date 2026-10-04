"""Render a synthetic scenario to files: one dossier PDF (native + scanned pages) + photos + ground truth."""

from __future__ import annotations

import io
import json
import random
import re
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from casebreak.synth.scenario import COURT, SERVICE, CaseBuilder, PieceSpec

W, H = 595, 842  # A4 points
MARGIN_X, TOP, BOTTOM = 62, 64, 70
BODY_SIZE, LEAD = 10.5, 15.2
HW_RE = re.compile(r"\{HW:([^}]*)\}")

_HAND_FONTS = [
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Noteworthy.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
]
_SANS_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(paths: list[str], size: int) -> ImageFont.ImageFont:
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, fontname: str, size: float, width: float) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if fitz.get_text_length(HW_RE.sub("        ", trial), fontname=fontname, fontsize=size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _lead(ln: tuple[str, str, float]) -> float:
    text, _, size = ln
    return size * 1.45 if not text else max(LEAD, size * 1.45)


def _header_lines(spec: PieceSpec, affaire: str) -> list[tuple[str, str, float]]:
    kind = "RAPPORT" if spec.header == "lab" else (
        "ORDONNANCE" if spec.type.startswith("ORDONNANCE") else
        "AUTORISATION" if spec.type.startswith("AUTORISATION") else
        "RÉQUISITOIRE" if spec.type.startswith("REQUISITOIRE") else
        "ARRÊT" if spec.type.startswith("ARRET") else "PROCÈS-VERBAL")
    top = {"police": "POLICE NATIONALE", "court": COURT, "lab": "LABORATOIRE D'EXPERTISE GÉNÉTIQUE - VALMORIN"}[spec.header]
    sub = {"police": SERVICE, "court": "Parquet et cabinets d'instruction", "lab": "Expert inscrit près la cour d'appel"}[spec.header]
    out = [(top, "hebo", 11), (sub, "helv", 8.5), ("", "helv", 6),
           (f"{kind} N° {spec.number}", "hebo", 12.5), (f"Affaire : {affaire}", "helv", 9),
           (f"Objet : {spec.objet}", "hebo", 9.5)]
    if spec.cadre:
        cadre = {"flagrance": "enquête de flagrance", "preliminaire": "enquête préliminaire",
                 "instruction": "information judiciaire"}.get(spec.cadre, spec.cadre)
        out.append((f"Cadre d'enquête : {cadre}", "helv", 9))
    if spec.person:
        out.append((f"Personne concernée : {spec.person}", "helv", 9))
    out.append(("", "helv", 8))
    return out


def _render_piece(doc: fitz.Document, spec: PieceSpec, affaire: str) -> list[dict]:
    """Write the piece into `doc`. Returns handwriting fields [{page_index, x, y, text}]."""
    hw_fields: list[dict] = []
    lines: list[tuple[str, str, float]] = _header_lines(spec, affaire)
    for para in spec.body:
        indent = "" if para.startswith(("QUESTION", "RÉPONSE", "-")) else ""
        for ln in _wrap(indent + para, "tiro", BODY_SIZE, W - 2 * MARGIN_X):
            lines.append((ln, "tiro", BODY_SIZE))
        lines.append(("", "tiro", 4))
    # signature block
    lines += [("", "tiro", 10), ("L'officier de police judiciaire\tLa personne", "tiro", 9),
              ("[signature]\t[signature]", "tiro", 9)]

    pages: list[list[tuple[str, str, float]]] = [[]]
    y = TOP
    for ln in lines:
        lead = _lead(ln)
        if y + lead > H - BOTTOM:
            pages.append([])
            y = TOP
        pages[-1].append(ln)
        y += lead
    n = len(pages)
    for k, pg_lines in enumerate(pages):
        page = doc.new_page(width=W, height=H)
        y = TOP
        for text, font, size in pg_lines:
            lead = _lead((text, font, size))
            if "\t" in text:
                left, right = text.split("\t")
                page.insert_text((MARGIN_X, y), left, fontname=font, fontsize=size)
                page.insert_text((W / 2 + 40, y), right, fontname=font, fontsize=size)
            elif text:
                m = HW_RE.search(text)
                if m:
                    before = text[: m.start()]
                    page.insert_text((MARGIN_X, y), before, fontname=font, fontsize=size)
                    x = MARGIN_X + fitz.get_text_length(before, fontname=font, fontsize=size)
                    hw_fields.append({"page_index": doc.page_count - 1, "x": x, "y": y, "text": m.group(1)})
                    after = text[m.end():]
                    page.insert_text((x + fitz.get_text_length("        ", fontname=font, fontsize=size), y), after,
                                     fontname=font, fontsize=size)
                else:
                    page.insert_text((MARGIN_X, y), text, fontname=font, fontsize=size)
            y += lead
        page.draw_line((MARGIN_X, H - 48), (W - MARGIN_X, H - 48), color=(0.6, 0.6, 0.6), width=0.5)
        page.insert_text((MARGIN_X, H - 34), f"Cote {spec.cote} - feuillet {k + 1}/{n}", fontname="helv", fontsize=8)
        page.insert_text((W - MARGIN_X - 150, H - 34), f"PV n° {spec.number}", fontname="helv", fontsize=8)
    return hw_fields


def _scanify(page_png: bytes, hw: list[dict], scale: float, rng: random.Random) -> bytes:
    img = Image.open(io.BytesIO(page_png)).convert("L")
    draw = ImageDraw.Draw(img)
    hand = _font(_HAND_FONTS, int(15 * scale))
    for f in hw:
        draw.text((f["x"] * scale + 4, (f["y"] - 13) * scale), f["text"], fill=40, font=hand)
    # stamp
    stamp = _font(_SANS_FONTS, int(11 * scale))
    sx, sy = int(W * scale * 0.62), int(H * scale * 0.82)
    draw.rectangle((sx, sy, sx + int(150 * scale), sy + int(34 * scale)), outline=110, width=3)
    draw.text((sx + 10, sy + 8), "COPIE CONFORME", fill=110, font=stamp)
    img = img.rotate(rng.uniform(-0.9, 0.9), resample=Image.BICUBIC, fillcolor=245, expand=False)
    noise = Image.effect_noise(img.size, 18).convert("L")
    img = Image.blend(img, noise, 0.07).filter(ImageFilter.GaussianBlur(0.45))
    img = img.point(lambda v: 248 if v > 205 else v)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=72)
    return out.getvalue()


def _photo(spec: PieceSpec, path: Path, rng: random.Random) -> None:
    ph = spec.photo or {}
    img = Image.new("RGB", (1200, 900), (52, 50, 48))
    d = ImageDraw.Draw(img)
    # table texture
    for _ in range(2200):
        x, y = rng.randrange(1200), rng.randrange(900)
        c = rng.randint(40, 70)
        d.point((x, y), fill=(c, c - 2, c - 4))
    # evidence bag
    d.rounded_rectangle((260, 140, 940, 760), radius=18, fill=(214, 218, 222), outline=(160, 166, 170), width=6)
    for i in range(14):
        cx, cy = rng.randint(380, 820), rng.randint(330, 640)
        r = rng.randint(14, 34)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(201, 164, 64), width=7)
    # seal label
    d.rectangle((330, 180, 870, 300), fill=(250, 250, 246), outline=(20, 20, 20), width=4)
    big = _font(_SANS_FONTS, 54)
    small = _font(_SANS_FONTS, 22)
    d.text((350, 192), ph.get("label", "SCELLÉ"), fill=(15, 15, 15), font=big)
    d.text((352, 258), f"PV n° {spec.number}", fill=(60, 60, 60), font=small)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    exif = Image.Exif()
    stamp = ph["exif"].strftime("%Y:%m:%d %H:%M:%S")
    exif[0x0132] = stamp
    exif[0x010F] = "Fictif"
    exif[0x0110] = "Appareil de service (synthétique)"
    exif.get_ifd(0x8769)[0x9003] = stamp
    img.save(path, format="JPEG", quality=86, exif=exif)


def render_case(b: CaseBuilder, out_dir: Path, title: str) -> dict:
    """Write dossier.pdf, photos/*.jpg, ground_truth.json and manifest.json. Returns the ground truth."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "photos").mkdir(exist_ok=True)
    rng = random.Random(b.rng.random())
    doc = fitz.open()
    piece_pages: dict[str, list[int]] = {}
    page_texts: dict[int, str] = {}
    photos: list[str] = []
    cote = 0
    for spec in b.pieces:
        if spec.photo:
            continue
        cote += 1
        spec.cote = f"D{cote}"
        first = doc.page_count
        if spec.scan:
            tmp = fitz.open()
            hw = _render_piece(tmp, spec, b.affaire)
            for i, pg in enumerate(tmp):
                page_texts[first + i + 1] = pg.get_text()
                scale = 200 / 72
                png = pg.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY).tobytes("png")
                jpg = _scanify(png, [h for h in hw if h["page_index"] == i], scale, rng)
                newp = doc.new_page(width=W, height=H)
                newp.insert_image(newp.rect, stream=jpg)
            tmp.close()
        else:
            _render_piece(doc, spec, b.affaire)
            for i in range(first, doc.page_count):
                page_texts[i + 1] = doc[i].get_text()
        piece_pages[spec.key] = list(range(first + 1, doc.page_count + 1))
    doc.set_metadata({"title": title, "author": "CASEBREAK synthetic generator", "subject": "Dossier fictif"})
    doc.save(out_dir / "dossier.pdf", deflate=True, garbage=3)
    n_pdf = doc.page_count
    doc.close()

    # photos come after the PDF in page numbering (one page per image)
    for spec in b.pieces:
        if not spec.photo:
            continue
        cote += 1
        spec.cote = f"D{cote}"
        name = f"photos/{spec.cote}_{re.sub(r'[^A-Za-z0-9]+', '_', spec.photo['label']).strip('_')}.jpg"
        _photo(spec, out_dir / name, rng)
        photos.append(name)
        piece_pages[spec.key] = [n_pdf + len(photos)]

    def locate(spec: PieceSpec, phrase: str) -> list[int]:
        pages = piece_pages.get(spec.key, [])
        if phrase:
            hit = [p for p in pages if phrase.lower() in page_texts.get(p, "").lower().replace("\n", " ")]
            if hit:
                return hit[:1]
        return pages

    entries = []
    for spec in b.pieces:
        for g in spec.gt:
            entries.append({
                "nullity_id": g["nullity_id"], "expected": g["expected"], "injected": g["injected"],
                "note": g["note"], "cote": spec.cote, "pv_number": spec.number, "piece_type": spec.type,
                "pages": locate(spec, g["phrase"]), "piece_pages": piece_pages.get(spec.key, []),
                "affected_pages": sorted({p for k in g["affected_keys"] for p in piece_pages.get(k, [])[:1]}),
                "certainty": g.get("certainty", ""),
            })
    truth = {"title": title, "pages": n_pdf + len(photos), "pieces": len(b.pieces), "entries": entries,
             "files": ["dossier.pdf", *photos], "generator": "casebreak.synth v1", "synthetic": True}
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2))
    (out_dir / "manifest.json").write_text(json.dumps({"name": title, "files": [{"path": f} for f in truth["files"]]},
                                                      ensure_ascii=False, indent=2))
    return truth
