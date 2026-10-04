"""① READ — every page of the file becomes a PageRec with its text, word boxes and provenance.

Native PDF text → kept as is. Scanned pages / photos → Mistral OCR if a key is set, else Tesseract
if installed, else marked unreadable (the checks that need them become `needs_reading`).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from collections.abc import Callable
from pathlib import Path

import pymupdf as fitz
from PIL import ExifTags, Image

from casebreak.config import CACHE, settings
from casebreak.llm import mistral
from casebreak.schemas import PageRec

log = logging.getLogger(__name__)
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
NATIVE_MIN_CHARS = 40


def _cache_get(key: str) -> dict | None:
    p = CACHE / f"ocr_{key}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _cache_put(key: str, val: dict) -> None:
    (CACHE / f"ocr_{key}.json").write_text(json.dumps(val, ensure_ascii=False))


def _tesseract(img: Image.Image) -> tuple[str, list]:
    import pytesseract

    langs = pytesseract.get_languages(config="")
    lang = "fra" if "fra" in langs else "eng"
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT, config="--psm 4")
    w, h = img.size
    lines: dict[tuple, list[str]] = {}
    words = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        if not txt or float(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(txt)
        x, y, ww, hh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append((x / w, y / h, (x + ww) / w, (y + hh) / h, txt))
    text = "\n".join(" ".join(v) for _, v in sorted(lines.items()))
    return text, words


def _ocr_image(img: Image.Image, raw: bytes, mime: str, key: str) -> dict:
    cached = _cache_get(key)
    if cached:
        return cached
    out = {"text": "", "words": [], "ocr": "none"}
    if settings.mistral:
        try:
            out = {"text": mistral.ocr_image(raw, mime), "words": [], "ocr": "mistral_ocr"}
        except mistral.MistralUnavailable as e:
            log.warning("Mistral OCR failed, falling back: %s", e)
    if out["ocr"] == "none" and settings.tesseract:
        try:
            text, words = _tesseract(img)
            out = {"text": text, "words": words, "ocr": "tesseract"}
        except Exception as e:  # noqa: BLE001 — OCR is best effort, the page becomes unreadable
            log.warning("tesseract failed: %s", e)
    if out["ocr"] != "none" and out["text"].strip() and not out["words"] and settings.tesseract:
        # Mistral OCR gives no word boxes: get boxes from tesseract for highlighting only.
        try:
            out["words"] = _tesseract(img)[1]
        except Exception:  # noqa: BLE001
            pass
    _cache_put(key, out)
    return out


def _exif(img: Image.Image) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        ex = img.getexif()
        for k, v in ex.items():
            out[ExifTags.TAGS.get(k, str(k))] = str(v)
        for k, v in ex.get_ifd(0x8769).items():
            out[ExifTags.TAGS.get(k, str(k))] = str(v)
    except Exception:  # noqa: BLE001
        pass
    return out


def read_files(case_dir: Path, files: list[str], progress: Callable[[str, dict], None] | None = None) -> list[PageRec]:
    pages: list[PageRec] = []
    emit = progress or (lambda *_: None)
    pdfs = [f for f in files if f.lower().endswith(".pdf")]
    imgs = sorted(f for f in files if Path(f).suffix.lower() in IMG_EXT)
    for f in pdfs:
        path = case_dir / f
        doc = fitz.open(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        for i, pg in enumerate(doc):
            text = pg.get_text()
            rec = PageRec(page=len(pages) + 1, file=f, file_page=i, width=pg.rect.width, height=pg.rect.height)
            if len(text.strip()) >= NATIVE_MIN_CHARS:
                rec.kind, rec.ocr, rec.text = "pdf_native", "native", text
                W, H = pg.rect.width, pg.rect.height
                rec.words = [(x0 / W, y0 / H, x1 / W, y1 / H, w) for x0, y0, x1, y1, w, *_ in pg.get_text("words")]
            else:
                rec.kind = "pdf_scan"
                pix = pg.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
                raw = pix.tobytes("png")
                img = Image.open(io.BytesIO(raw))
                o = _ocr_image(img, raw, "image/png", f"{digest}_{i}")
                rec.text, rec.words, rec.ocr = o["text"], [tuple(w) for w in o["words"]], o["ocr"]
                rec.readable = o["ocr"] != "none" and len(o["text"].strip()) > 20
            pages.append(rec)
            emit("page", {"page": rec.page, "kind": rec.kind, "ocr": rec.ocr, "file": f})
        doc.close()
    for f in imgs:
        path = case_dir / f
        raw = path.read_bytes()
        img = Image.open(io.BytesIO(raw))
        exif = _exif(img)
        digest = hashlib.sha256(raw).hexdigest()[:16]
        o = _ocr_image(img.convert("L"), raw, "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png",
                       digest)
        rec = PageRec(page=len(pages) + 1, file=f, file_page=0, kind="image", ocr=o["ocr"], text=o["text"],
                      words=[tuple(w) for w in o["words"]], readable=bool(o["text"].strip()),
                      width=img.size[0], height=img.size[1], exif=exif)
        pages.append(rec)
        emit("page", {"page": rec.page, "kind": "image", "ocr": rec.ocr, "file": f})
    return pages
