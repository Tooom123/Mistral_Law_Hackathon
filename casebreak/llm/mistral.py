"""Minimal Mistral client (httpx). Used only when MISTRAL_API_KEY is set; callers always have an offline path."""

from __future__ import annotations

import base64
import json
import logging

import httpx

from casebreak.config import settings

log = logging.getLogger(__name__)


class MistralUnavailable(RuntimeError):
    pass


def _headers() -> dict:
    if not settings.mistral:
        raise MistralUnavailable("MISTRAL_API_KEY absent")
    return {"Authorization": f"Bearer {settings.mistral_key}", "Content-Type": "application/json"}


def chat(messages: list[dict], model: str | None = None, json_mode: bool = False, temperature: float = 0.0,
         timeout: float = 90.0) -> str:
    body: dict = {"model": model or settings.judge_model, "messages": messages, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(f"{settings.mistral_base}/chat/completions", headers=_headers(), json=body, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise MistralUnavailable(str(e)) from e
    return r.json()["choices"][0]["message"]["content"]


def chat_json(system: str, user: str, model: str | None = None) -> dict:
    out = chat([{"role": "system", "content": system}, {"role": "user", "content": user}], model=model, json_mode=True)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise MistralUnavailable(f"invalid JSON from model: {e}") from e


def ocr_pdf(pdf_bytes: bytes) -> list[str]:
    """Mistral OCR on a PDF. Returns one markdown string per page."""
    url = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode()
    body = {"model": settings.ocr_model, "document": {"type": "document_url", "document_url": url}}
    try:
        r = httpx.post(f"{settings.mistral_base}/ocr", headers=_headers(), json=body, timeout=180)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise MistralUnavailable(str(e)) from e
    return [p.get("markdown", "") for p in r.json().get("pages", [])]


def ocr_image(img_bytes: bytes, mime: str = "image/jpeg") -> str:
    url = f"data:{mime};base64," + base64.b64encode(img_bytes).decode()
    body = {"model": settings.ocr_model, "document": {"type": "image_url", "image_url": url}}
    try:
        r = httpx.post(f"{settings.mistral_base}/ocr", headers=_headers(), json=body, timeout=120)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise MistralUnavailable(str(e)) from e
    pages = r.json().get("pages", [])
    return pages[0].get("markdown", "") if pages else ""
