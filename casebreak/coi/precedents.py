"""Conflict-of-interest precedent database and retrieval.

Source of truth: `data/precedents.json` (court decisions, regulatory settlements, parliamentary reports, statutes,
and simulated training scenarios — each entry says which in `provenance`). At first use it is loaded into a SQLite
database (data/cache/precedents.sqlite) with an FTS5 full-text index and a pattern table; it is rebuilt whenever
the JSON changes.

Ranking is hybrid:
- lexical: FTS5 BM25 over title, facts, outcome, signals and lesson;
- structural: overlap between the flag's conflict patterns and the precedent's (Jaccard);
- semantic: cosine similarity of `mistral-embed` vectors, when MISTRAL_API_KEY is set (vectors cached on disk).
Each hit says why it matched: shared patterns, shared signals, matched terms.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from casebreak.config import CACHE, settings

log = logging.getLogger(__name__)
SOURCE = Path(__file__).with_name("data") / "precedents.json"
_LOCK = threading.Lock()

PATTERNS = {
    "dual_role": "Dual mandate",
    "undeclared_interest": "Undeclared / false declaration",
    "missing_declaration": "Missing declaration",
    "revolving_door": "Revolving door",
    "family_tie": "Relative's interest",
    "beneficiary_link": "Tie to the beneficiary",
    "preparatory_role": "Preparatory role",
    "false_statement": "Statement contradicted",
    "information_barrier": "Confidential information",
    "appearance_of_bias": "Appearance of bias",
}
STOP = set("""a an and are as at be by for from has have in into is it its of on or that the their this to was were
with which who whose same at time all any not no was been after before during while""".split())


@lru_cache(maxsize=1)
def load() -> list[dict]:
    return json.loads(SOURCE.read_text())


def _digest() -> str:
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:16]


def _db() -> sqlite3.Connection:
    path = CACHE / "precedents.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        con = sqlite3.connect(path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        cur = con.execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone()
        built = cur and con.execute("SELECT v FROM meta WHERE k='digest'").fetchone()
        if not built or built["v"] != _digest():
            _build(con)
        return con


def _build(con: sqlite3.Connection) -> None:
    con.executescript("""
        DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS precedent; DROP TABLE IF EXISTS pattern;
        DROP TABLE IF EXISTS precedent_fts;
        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE precedent (id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE pattern (precedent_id TEXT, pattern TEXT);
        CREATE INDEX pattern_idx ON pattern(pattern);
        CREATE VIRTUAL TABLE precedent_fts USING fts5(id UNINDEXED, title, facts, outcome, signals, lesson,
                                                      tokenize='porter unicode61');
    """)
    for p in load():
        con.execute("INSERT INTO precedent VALUES (?, ?)", (p["id"], json.dumps(p, ensure_ascii=False)))
        con.executemany("INSERT INTO pattern VALUES (?, ?)", [(p["id"], x) for x in p["patterns"]])
        con.execute("INSERT INTO precedent_fts VALUES (?, ?, ?, ?, ?, ?)",
                    (p["id"], p["title"], p["facts"], p["outcome"], " ; ".join(p["signals"]), p["lesson"]))
    con.execute("INSERT INTO meta VALUES ('digest', ?)", (_digest(),))
    con.commit()
    log.info("precedent database built: %d entries", len(load()))


def terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zà-ÿ0-9]+", text.lower()) if len(w) > 2 and w not in STOP]


def _lexical(query: str) -> dict[str, float]:
    words = sorted(set(terms(query)))
    if not words:
        return {}
    q = " OR ".join(f'"{w}"' for w in words)
    rows = _db().execute("SELECT id, bm25(precedent_fts) AS s FROM precedent_fts WHERE precedent_fts MATCH ?",
                         (q,)).fetchall()
    if not rows:
        return {}
    best = max(-r["s"] for r in rows) or 1.0
    return {r["id"]: max(0.0, -r["s"]) / best for r in rows}


# ------------------------------------------------------------------ embeddings (optional)


def _embed(texts: list[str]) -> list[list[float]] | None:
    if not settings.mistral:
        return None
    from casebreak.llm import mistral

    out: list[list[float] | None] = []
    todo = []
    for t in texts:
        p = CACHE / f"emb_{hashlib.sha256(t.encode()).hexdigest()[:24]}.json"
        if p.exists():
            out.append(json.loads(p.read_text()))
        else:
            out.append(None)
            todo.append((len(out) - 1, t, p))
    if todo:
        try:
            data = mistral._post("/embeddings", {"model": "mistral-embed", "input": [t for _, t, _ in todo]}, 60)
        except mistral.MistralUnavailable as e:
            log.warning("embeddings unavailable: %s", e)
            return None
        for (i, _, p), item in zip(todo, data["data"]):
            out[i] = item["embedding"]
            p.write_text(json.dumps(item["embedding"]))
    return out  # type: ignore[return-value]


def _cos(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _semantic(query: str) -> dict[str, float]:
    corpus = load()
    vecs = _embed([query] + [f"{p['title']}. {p['facts']} {p['lesson']}" for p in corpus])
    if not vecs:
        return {}
    return {p["id"]: _cos(vecs[0], v) for p, v in zip(corpus, vecs[1:])}


# ------------------------------------------------------------------ search


def search(query: str = "", patterns: list[str] | None = None, k: int = 5, provenance: str | None = None,
           signals: list[str] | None = None) -> list[dict]:
    patterns = patterns or []
    lex = _lexical(" ".join([query] + (signals or [])))
    sem = _semantic(query) if query else {}
    qterms = set(terms(query + " " + " ".join(signals or [])))
    hits = []
    for p in load():
        if provenance and p["provenance"] != provenance:
            continue
        shared = [x for x in p["patterns"] if x in patterns]
        jac = len(shared) / len(set(p["patterns"]) | set(patterns)) if patterns else 0.0
        if sem:
            score = 0.4 * sem.get(p["id"], 0) + 0.3 * lex.get(p["id"], 0) + 0.3 * jac
        else:
            score = (0.55 * lex.get(p["id"], 0) + 0.45 * jac) if patterns else lex.get(p["id"], 0)
        if score <= 0:
            continue
        sig = [s for s in p["signals"] if set(terms(s)) & qterms]
        matched = sorted(set(terms(" ".join([p["title"], p["facts"], " ".join(p["signals"])]))) & qterms)[:8]
        hits.append({**p, "score": round(score, 3), "why": {
            "patterns": [PATTERNS.get(x, x) for x in shared], "signals": sig, "terms": matched,
            "semantic": bool(sem)}})
    hits.sort(key=lambda h: (-h["score"], h["provenance"] != "public_record", h["id"]))
    return hits[:k]


def stats() -> dict:
    corpus = load()
    by = lambda key: {v: sum(1 for p in corpus if p[key] == v) for v in sorted({p[key] for p in corpus})}  # noqa: E731
    return {"total": len(corpus), "by_provenance": by("provenance"), "by_jurisdiction": by("jurisdiction"),
            "by_kind": by("kind"),
            "by_pattern": {k: sum(1 for p in corpus if k in p["patterns"]) for k in PATTERNS},
            "engine": "sqlite-fts5 bm25 + pattern overlap" + (" + mistral-embed" if settings.mistral else "")}
