"""Minimal Mistral client (httpx). Used only when MISTRAL_API_KEY is set; callers always have an offline path.

- Retries on 429 / 5xx / network errors (exponential backoff).
- JSON answers are cached on disk (data/cache/llm_*.json), keyed by model + messages: a re-run of the same
  case file (demo, time-travel slider, report) costs nothing and gives the same answer.
- OCR returns Markdown; `md_to_text` turns it back into plain lines so the French patterns and the quote
  check work on it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
import time

import httpx

from casebreak.config import CACHE, settings

log = logging.getLogger(__name__)
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class MistralUnavailable(RuntimeError):
    pass


def _headers() -> dict:
    if not settings.mistral:
        raise MistralUnavailable("MISTRAL_API_KEY absent")
    return {"Authorization": f"Bearer {settings.mistral_key}", "Content-Type": "application/json",
            "Accept": "application/json"}


class ModelRefused(MistralUnavailable):
    """The workspace cannot use this model (403/404, or a 0 requests/minute quota): try the next one."""


# Models refused in this process (persisted for an hour so a restart doesn't re-probe them).
_DEAD_FILE = CACHE / "mistral_refused.json"
_DEAD: dict[str, float] = {}
try:
    _DEAD = {k: v for k, v in json.loads(_DEAD_FILE.read_text()).items() if time.time() - v < 3600}
except (OSError, ValueError):
    pass
_LOCK = threading.Lock()
LAST_MODEL: dict[str, str] = {}  # purpose → model actually used (shown in /api/engines)


def _mark_dead(model: str) -> None:
    with _LOCK:
        _DEAD[model] = time.time()
        try:
            _DEAD_FILE.write_text(json.dumps(_DEAD))
        except OSError:
            pass


def refused_models() -> list[str]:
    return sorted(_DEAD)


def _post(path: str, body: dict, timeout: float, retries: int = 3) -> dict:
    headers = _headers()
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(f"{settings.mistral_base}{path}", headers=headers, json=body, timeout=timeout)
            if r.status_code in (401,):
                raise MistralUnavailable(f"{path} HTTP 401: invalid MISTRAL_API_KEY")
            if r.status_code in (403, 404) or (r.status_code == 429 and r.headers.get("x-ratelimit-limit-req-minute") == "0"):
                raise ModelRefused(f"{body.get('model')} refused on {path} (HTTP {r.status_code}): {r.text[:160]}")
            if r.status_code in RETRY_STATUS and attempt < retries:
                wait = float(r.headers.get("retry-after") or 0) or 1.5 * 2 ** attempt
                log.info("Mistral %s → %s, retry in %.1fs", path, r.status_code, wait)
                time.sleep(min(wait, 20))
                continue
            if r.status_code >= 400:
                raise MistralUnavailable(f"{path} HTTP {r.status_code}: {r.text[:300]}")
            return r.json()
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last = e
            if attempt < retries:
                time.sleep(1.5 * 2 ** attempt)
                continue
        except ValueError as e:  # body is not JSON
            raise MistralUnavailable(f"{path}: invalid response ({e})") from e
    raise MistralUnavailable(f"{path}: {last}")


def _chain(model: str, fallback: bool, pool: tuple | None = None) -> list[str]:
    out = [model] + (list(pool if pool is not None else settings.fallback_models) if fallback else [])
    seen: list[str] = []
    for m in out:
        if m and m not in seen and m not in _DEAD:
            seen.append(m)
    return seen


def _with_fallback(model: str, fallback: bool, call, purpose: str, pool: tuple | None = None):
    errors = []
    for m in _chain(model, fallback, pool):
        try:
            out = call(m)
            LAST_MODEL[purpose] = m
            return out, m
        except ModelRefused as e:
            log.warning("%s", e)
            _mark_dead(m)
            errors.append(str(e))
    raise MistralUnavailable("no usable Mistral model: " + ("; ".join(errors) or f"all refused ({', '.join(_DEAD)})"))


def _content(msg: dict) -> str:
    """`content` is a string, or a list of chunks for reasoning models (Magistral): keep the text chunks."""
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(ch.get("text", "") for ch in c if isinstance(ch, dict) and ch.get("type") == "text")
    return ""


def chat_meta(messages: list[dict], model: str | None = None, json_mode: bool = False, temperature: float = 0.0,
              timeout: float = 120.0, fallback: bool = True, purpose: str = "chat") -> tuple[str, str]:
    """Returns (text, model actually used)."""
    def call(m: str) -> str:
        body: dict = {"model": m, "messages": messages, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = _post("/chat/completions", body, timeout)
        try:
            return _content(data["choices"][0]["message"])
        except (KeyError, IndexError, TypeError) as e:
            raise MistralUnavailable(f"unexpected chat response: {str(data)[:200]}") from e
    return _with_fallback(model or settings.judge_model, fallback, call, purpose)


def chat(messages: list[dict], model: str | None = None, json_mode: bool = False, temperature: float = 0.0,
         timeout: float = 120.0, fallback: bool = True, purpose: str = "chat") -> str:
    return chat_meta(messages, model, json_mode, temperature, timeout, fallback, purpose)[0]


def _parse_json(out: str) -> dict:
    s = out.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    try:
        v = json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if i < 0 or j <= i:
            raise
        v = json.loads(s[i:j + 1])
    if not isinstance(v, dict):
        raise json.JSONDecodeError("top level is not an object", s, 0)
    return v


def chat_json(system: str, user: str, model: str | None = None, cache: bool = True, purpose: str = "chat") -> dict:
    """JSON answer. The model actually used is returned under the key `_model`."""
    model = model or settings.judge_model
    key = hashlib.sha256(json.dumps([model, system, user], ensure_ascii=False).encode()).hexdigest()[:24]
    path = CACHE / f"llm_{key}.json"
    if cache and path.exists():
        try:
            v = json.loads(path.read_text())
            LAST_MODEL[purpose] = v.get("_model", model)
            return v
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)
    out, used = chat_meta([{"role": "system", "content": system}, {"role": "user", "content": user}], model=model,
                          json_mode=True, purpose=purpose)
    try:
        v = _parse_json(out)
    except json.JSONDecodeError as e:
        raise MistralUnavailable(f"invalid JSON from {used}: {e}") from e
    v["_model"] = used
    if cache:
        path.write_text(json.dumps(v, ensure_ascii=False))
    return v


_MD = [
    (re.compile(r"^#{1,6}\s*", re.M), ""),           # headings
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),           # bold
    (re.compile(r"(?<!\w)[*_](\S.*?\S|\S)[*_](?!\w)"), r"\1"),  # italics
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),       # image placeholders
    (re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$", re.M), ""),  # table separators
    (re.compile(r"\s*\|\s*"), " "),                  # table cells → spaces
    (re.compile(r"\\([*_#|\-])"), r"\1"),             # escaped markdown chars
    (re.compile(r"\$\s*\^\s*\{?\s*(?:\\circ|o)\s*\}?\s*\$"), "°"),  # LaTeX degree sign ("n$^{\circ}$")
]


def md_to_text(md: str) -> str:
    out = md
    for rx, rep in _MD:
        out = rx.sub(rep, out)
    return "\n".join(line.rstrip() for line in out.split("\n"))


VISION_PROMPT = ("Transcribe ALL the text visible in this image, verbatim, line by line, in its original language "
                 "(French). Keep handwritten words and times exactly as written. If a word is illegible write [illegible]. "
                 "No commentary, no Markdown, no translation.")


def _ocr(document: dict, timeout: float) -> list[str]:
    def call(m: str) -> list[str]:
        data = _post("/ocr", {"model": m, "document": document, "include_image_base64": False}, timeout)
        return [md_to_text(p.get("markdown", "")) for p in data.get("pages", [])]
    return _with_fallback(settings.ocr_model, False, call, "ocr")[0]


def _vision(url: str) -> str:
    """Fallback OCR: a Mistral vision chat model transcribes the image (marked `mistral_vision`, never `native`)."""
    msgs = [{"role": "user", "content": [{"type": "text", "text": VISION_PROMPT}, {"type": "image_url", "image_url": url}]}]
    pool = settings.vision_models
    return md_to_text(_with_fallback(pool[0], True, lambda m: chat_meta(msgs, model=m, fallback=False, timeout=120,
                                                                      purpose="vision")[0], "vision", pool[1:])[0])


def ocr_pdf(pdf_bytes: bytes) -> list[str]:
    """Mistral OCR on a whole PDF. Returns one plain-text string per page."""
    url = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode()
    return _ocr({"type": "document_url", "document_url": url}, timeout=300)


def ocr_image(img_bytes: bytes, mime: str = "image/jpeg") -> tuple[str, str]:
    """Returns (text, engine) with engine `mistral_ocr`, or `mistral_vision` when /ocr is unavailable."""
    url = f"data:{mime};base64," + base64.b64encode(img_bytes).decode()
    try:
        pages = _ocr({"type": "image_url", "image_url": url}, timeout=120)
        return (pages[0] if pages else ""), "mistral_ocr"
    except MistralUnavailable as e:
        log.info("Mistral OCR unavailable (%s) — trying a vision model", e)
    return _vision(url), "mistral_vision"


def ping() -> dict:
    """Cheap check that the key works (used by `casebreak doctor`)."""
    t0 = time.time()
    out, used = chat_meta([{"role": "user", "content": "Reply with the single word: ok"}], model=settings.fast_model,
                          timeout=30, purpose="ping")
    return {"ok": "ok" in out.lower(), "model": used, "answer": out.strip()[:40], "ms": int((time.time() - t0) * 1000)}
