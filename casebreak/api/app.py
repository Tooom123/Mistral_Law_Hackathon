"""CASEBREAK API (ARCHITECTURE §9) + static front. Run: `uv run casebreak serve` → http://localhost:8000"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from pathlib import Path
from typing import Literal

import pymupdf as fitz
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from casebreak.api import service as svc
from casebreak.config import BENCH, CACHE, FRONTEND, settings
from casebreak.deadlines.clock import deadlines
from casebreak.eval import bench
from casebreak.judge.questions import PROSECUTION
from casebreak.nullities.versions import load_catalogue, reform_dates
from casebreak.output import report
from casebreak.output.alerts import card, highlights
from casebreak.pipeline import STAGES, run_case, status
from casebreak.precedents import judilibre
from casebreak.privacy.pseudonymize import mask_value
from casebreak.proofs import lean
from casebreak.propagate.cascade import simulate as simulate_cascade
from casebreak.schemas import LANES
from casebreak.synth import DEFAULT_DEMO, DEMO_CASES
from casebreak.tribunal.court import deliberate

log = logging.getLogger(__name__)
app = FastAPI(title="CASEBREAK", version="0.3", description="Find the procedural flaw before the deadline does.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

Mode = Literal["defense", "prosecution"]
DEMO_SRC = CACHE / "demo_src"  # + "_<case>" for the cases other than the first synthetic one
_demo_lock = threading.Lock()


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


def _graph(cid: str):
    try:
        return svc.load(cid)
    except KeyError:
        _404("case")


# ------------------------------------------------------------------ meta


@app.get("/api/engines")
def engines() -> dict:
    from casebreak.llm import mistral

    return {**settings.engines(), "pseudonymize": settings.pseudonymize, "stages": [s for s, _, _ in STAGES],
            "models": {"configured": {"ocr": settings.ocr_model, "extract": settings.extract_model,
                                      "judge": settings.judge_model, "fast": settings.fast_model},
                       "used": dict(mistral.LAST_MODEL), "refused": mistral.refused_models()}}


@app.get("/api/catalogue")
def catalogue() -> list[dict]:
    return [n.model_dump(mode="json") for n in load_catalogue().values()]


@app.get("/api/law/reforms")
def reforms() -> list[dict]:
    return reform_dates()


# ------------------------------------------------------------------ cases


@app.get("/cases")
def list_cases() -> list[dict]:
    return svc.list_cases()


@app.post("/cases")
async def create_case(files: list[UploadFile] = File(...), title: str = Query("")) -> dict:
    cid = svc.new_case_id()
    d = svc.case_path(cid)
    d.mkdir(parents=True)
    names = []
    for f in files:
        name = Path(f.filename or "piece").name
        if not name.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")):
            continue
        sub = "photos/" if not name.lower().endswith(".pdf") else ""
        (d / sub).mkdir(exist_ok=True)
        (d / sub / name).write_bytes(await f.read())
        names.append(sub + name)
    if not names:
        shutil.rmtree(d)
        raise HTTPException(400, "No PDF or image file received.")
    threading.Thread(target=_run_safe, args=(cid, names, title or names[0], 0.35), daemon=True).start()
    return {"case_id": cid, "files": names}


@app.post("/cases/demo")
def create_demo(pace: float = Query(1.0, ge=0, le=5), case: str = Query(DEFAULT_DEMO)) -> dict:
    """A frozen synthetic demo case file, run live for the war room: `beckham` (default) or `mathurins`."""
    if case not in DEMO_CASES:
        raise HTTPException(400, f"Unknown demo case {case!r}; available: {', '.join(DEMO_CASES)}.")
    title, generate = DEMO_CASES[case]
    src = DEMO_SRC if case == "mathurins" else DEMO_SRC.with_name(f"demo_src_{case}")
    with _demo_lock:
        if not (src / "ground_truth.json").exists():
            generate(src)
    cid = svc.new_case_id().replace("c", "demo-", 1)
    d = svc.case_path(cid)
    shutil.copytree(src, d)
    files = ["dossier.pdf"] + sorted(f"photos/{p.name}" for p in (d / "photos").glob("*.jpg"))
    threading.Thread(target=_run_safe, args=(cid, files, title, pace), daemon=True).start()
    return {"case_id": cid, "files": files, "title": title}


def _run_safe(cid: str, files: list[str], title: str, pace: float) -> None:
    try:
        run_case(cid, files, title, pace=pace)
    except Exception:  # noqa: BLE001 — status carries the error
        log.exception("case %s failed", cid)


@app.get("/cases/{cid}/status")
def case_status(cid: str) -> dict:
    st = status(cid)
    if st.get("state") == "unknown":
        _404("case")
    return st


@app.delete("/cases/{cid}")
def delete_case(cid: str) -> dict:
    svc.delete(cid)
    return {"deleted": cid}


@app.get("/cases/{cid}/graph")
def graph(cid: str, as_of: str | None = None, pseudo: bool = False) -> dict:
    g, _ = _graph(cid)
    checks = svc.checks_as_of(cid, as_of)
    m = mask_value if pseudo else (lambda s: s)
    by_node: dict[str, list] = {}
    for c in checks:
        by_node.setdefault(c.node_id, []).append({"nullity_id": c.nullity_id, "status": c.status, "certainty": c.certainty,
                                                  "alert": c.id or None, "title": c.title, "statement": m(c.statement_fr)})
    nodes = []
    for n in g.nodes:
        if n.type == "PIECE":
            continue
        attrs = {k: {"value": (m(a.value) if isinstance(a.value, str) else a.value), "status": a.status,
                     "src": ({**a.src.model_dump(), "quote": m(a.src.quote)} if a.src else None)}
                 for k, a in n.attrs.items() if not k.startswith("_")}
        nodes.append({"id": n.id, "type": n.type, "category": n.category, "subtype": n.subtype, "label": m(n.label),
                      "start": n.start.isoformat() if n.start else None, "end": n.end.isoformat() if n.end else None,
                      "framework": n.framework, "person": n.person, "doc_ids": n.doc_ids, "pages": n.pages[:20],
                      "attrs": attrs, "checks": by_node.get(n.id, [])})
    edges = [e.model_dump(mode="json") for e in g.edges if e.kind in ("SUPPORTS", "CONTRADICTS", "PART_OF", "INVOLVES")]
    pieces = [{"id": p.id, "number": p.number, "type": p.type, "category": p.category, "title": p.title,
               "pages": p.pages, "ocr": sorted({g.pages[i - 1].ocr for i in p.pages})} for p in g.pieces]
    times = [n.start for n in g.nodes if n.type == "ACT" and n.start]
    return {"case_id": cid, "title": g.title, "framework": g.framework, "lanes": LANES, "nodes": nodes, "edges": edges,
            "pieces": pieces, "stats": g.stats, "as_of": as_of,
            "range": {"min": min(times).isoformat(), "max": max(times).isoformat()} if times else None,
            "pages": [{"page": p.page, "ocr": p.ocr, "kind": p.kind, "readable": p.readable} for p in g.pages]}


@app.get("/cases/{cid}/alerts")
def alerts(cid: str, as_of: str | None = None, mode: Mode = "defense", pseudo: bool = False) -> dict:
    g, _ = _graph(cid)
    cards = svc.cards(cid, as_of, mode, pseudo)
    return {"case_id": cid, "as_of": as_of, "mode": mode, "count": len(cards), "alerts": cards,
            "counts": {s: sum(1 for c in cards if c["status"] == s) for s in ("possible_nullity", "needs_reading")},
            "deadline": deadlines(g)}


@app.get("/cases/{cid}/alerts/{aid}")
def alert(cid: str, aid: str, as_of: str | None = None, mode: Mode = "defense", pseudo: bool = False) -> dict:
    g, _ = _graph(cid)
    try:
        c = svc.find_alert(cid, aid, as_of)
    except KeyError:
        _404("alert")
    out = card(c, g, svc.reviews(cid), mode, pseudo)
    nl = load_catalogue().get(c.nullity_id)
    out["counter_arguments"] = [{"hint": h, "text": PROSECUTION.get(h, h)} for h in (nl.prosecution_hints if nl else [])]
    out["judilibre_query"] = nl.judilibre_query if nl else ""
    return out


class SimReq(BaseModel):
    node_id: str


@app.post("/cases/{cid}/simulate")
def simulate(cid: str, req: SimReq) -> dict:
    g, _ = _graph(cid)
    if req.node_id not in {n.id for n in g.nodes}:
        _404("node")
    return simulate_cascade(req.node_id, g.nodes, g.edges)


class ReviewReq(BaseModel):
    decision: Literal["accepted", "rejected", "pending"]
    note: str = ""


@app.post("/cases/{cid}/alerts/{aid}/review")
def review(cid: str, aid: str, req: ReviewReq) -> dict:
    _graph(cid)
    try:
        c = svc.find_alert(cid, aid)
    except KeyError:
        _404("alert")
    return svc.set_review(cid, c, req.decision, req.note)


@app.get("/cases/{cid}/alerts/{aid}/tribunal")
def tribunal(cid: str, aid: str, as_of: str | None = None) -> dict:
    g, _ = _graph(cid)
    try:
        return deliberate(svc.find_alert(cid, aid, as_of), g)
    except KeyError:
        _404("alert")


@app.get("/cases/{cid}/alerts/{aid}/proof")
def proof(cid: str, aid: str, as_of: str | None = None) -> dict:
    _graph(cid)
    try:
        return lean.prove(svc.find_alert(cid, aid, as_of))
    except KeyError:
        _404("alert")


@app.get("/cases/{cid}/alerts/{aid}/precedents")
def precedents(cid: str, aid: str) -> dict:
    _graph(cid)
    try:
        c = svc.find_alert(cid, aid)
    except KeyError:
        _404("alert")
    nl = load_catalogue().get(c.nullity_id)
    return judilibre.search(nl.judilibre_query if nl else "")


@app.get("/cases/{cid}/deadline")
def deadline(cid: str) -> dict:
    g, _ = _graph(cid)
    return deadlines(g)


# ------------------------------------------------------------------ pages


def _page_png(cid: str, page: int, dpi: int) -> Path:
    g, _ = _graph(cid)
    if not 1 <= page <= len(g.pages):
        _404("page")
    rec = g.pages[page - 1]
    out = svc.case_path(cid) / "pages" / f"p{page:04d}_{dpi}.png"
    if out.exists():
        return out
    out.parent.mkdir(exist_ok=True)
    src = svc.case_path(cid) / rec.file
    if rec.kind == "image":
        im = Image.open(src).convert("RGB")
        im.thumbnail((1400, 1400))
        im.save(out, "PNG")
    else:
        doc = fitz.open(src)
        doc[rec.file_page].get_pixmap(dpi=dpi).save(out)
        doc.close()
    return out


@app.get("/cases/{cid}/pages/{page}.png")
def page_png(cid: str, page: int, dpi: int = Query(110, ge=40, le=200)) -> FileResponse:
    return FileResponse(_page_png(cid, page, dpi), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/cases/{cid}/pages/{doc}/{page}")
def page(cid: str, doc: str, page: int, q: list[str] = Query(default=[]), alert: str | None = None,
         pseudo: bool = False) -> dict:
    g, _ = _graph(cid)
    if not 1 <= page <= len(g.pages):
        _404("page")
    rec = g.pages[page - 1]
    piece = next((p for p in g.pieces if p.id == doc), None) or next((p for p in g.pieces if page in p.pages), None)
    quotes = list(q)
    if alert:
        try:
            c = svc.find_alert(cid, alert)
            quotes += [s.quote for s in c.sources if s.page == page]
        except KeyError:
            pass
    m = mask_value if pseudo else (lambda s: s)
    return {"page": page, "doc_id": piece.id if piece else doc, "image": f"/cases/{cid}/pages/{page}.png",
            "kind": rec.kind, "ocr": rec.ocr, "readable": rec.readable, "width": rec.width, "height": rec.height,
            "text": m(rec.text), "exif": rec.exif, "highlights": highlights(rec, quotes),
            "piece": {"id": piece.id, "number": piece.number, "title": piece.title, "type": piece.type,
                      "category": piece.category, "pages": piece.pages} if piece else None,
            "total_pages": len(g.pages)}


# ------------------------------------------------------------------ report


@app.get("/cases/{cid}/report")
def get_report(cid: str, format: Literal["md", "pdf", "json"] = "md", mode: Mode = "defense", as_of: str | None = None,
               pseudo: bool = False, tribunal: bool = True):
    g, _ = _graph(cid)
    cards = svc.cards(cid, as_of, mode, pseudo)
    if tribunal:
        for c in cards:
            try:
                c["tribunal"] = deliberate(svc.find_alert(cid, c["id"], as_of), g)
            except KeyError:
                pass
    dl = deadlines(g)
    if format == "json":
        return {"title": g.title, "alerts": cards, "deadline": dl}
    if format == "pdf":
        data = report.pdf(g.title, cards, dl, mode)
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="casebreak-{cid}-{mode}.pdf"'})
    return PlainTextResponse(report.markdown(g.title, cards, dl, mode), media_type="text/markdown; charset=utf-8")


@app.get("/cases/{cid}/files/{path:path}")
def case_file(cid: str, path: str) -> FileResponse:
    p = (svc.case_path(cid) / path).resolve()
    if svc.case_path(cid) not in p.parents or not p.exists():
        _404("file")
    return FileResponse(p)


# ------------------------------------------------------------------ benchmark

_bench_state = {"running": False, "done": 0, "total": 0, "error": None}


@app.get("/benchmark")
def get_benchmark() -> dict:
    p = BENCH / "results.json"
    res = json.loads(p.read_text()) if p.exists() else None
    if res:
        res.pop("cases", None)
    return {"results": res, "state": _bench_state}


@app.post("/benchmark/run")
def run_benchmark(bg: BackgroundTasks, n: int = Query(10, ge=1, le=60)) -> dict:
    if _bench_state["running"]:
        return {"state": _bench_state}

    def job() -> None:
        _bench_state.update(running=True, done=0, total=n, error=None)
        try:
            bench.run(n=n, progress=lambda k, t: _bench_state.update(done=k))
        except Exception as e:  # noqa: BLE001
            _bench_state["error"] = str(e)
        finally:
            _bench_state["running"] = False

    bg.add_task(job)
    return {"state": {**_bench_state, "running": True, "total": n}}


@app.get("/benchmark/export")
def export_benchmark() -> Response:
    return Response(bench.export_zip(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="NullityBench-FR.zip"'})


# ------------------------------------------------------------------ front

# Compatibility with the landing page's first contract (POST /api/dossiers).
@app.post("/api/dossiers")
async def legacy_upload(files: list[UploadFile] = File(...)) -> JSONResponse:
    out = await create_case(files)
    return JSONResponse({"dossier_id": out["case_id"], **out})


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/index.html")


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="front")

