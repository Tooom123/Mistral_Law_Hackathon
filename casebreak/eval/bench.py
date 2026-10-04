"""NullityBench-FR — synthetic dossiers with injected nullities and decoys; recall/precision per nullity and
per certainty level; comparison with an LLM alone when a Mistral key is set (ARCHITECTURE §8).

Say it honestly: "on our synthetic set of N case files". Synthetic ≠ real accuracy.
"""

from __future__ import annotations

import io
import json
import shutil
import time
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from casebreak.config import BENCH
from casebreak.eval.baseline import run_baseline
from casebreak.schemas import Check

DOSSIERS = BENCH / "dossiers"


def match(alert: Check, entry: dict) -> bool:
    pages = set(entry["piece_pages"]) | set(entry["pages"])
    return alert.nullity_id == entry["nullity_id"] and bool({s.page for s in alert.sources} & pages)


def score_case(checks: list[Check], truth: dict) -> dict:
    """Per-entry outcome + false positives. Strict = flagged "possible nullity"; any = possible or to investigate."""
    alerts = [c for c in checks if c.status in ("possible_nullity", "needs_reading")]
    used: set[int] = set()
    rows = []
    for e in truth["entries"]:
        hits = [i for i, a in enumerate(alerts) if match(a, e)]
        strict = [i for i in hits if alerts[i].status == "possible_nullity"]
        used.update(hits)
        page_ok = any(set(e["pages"]) & {s.page for s in alerts[i].sources} for i in hits) if hits else False
        casc = None
        if e["affected_pages"] and strict:
            a = alerts[strict[0]]
            got = {p for nid in a.affected for p in _node_pages(nid, a)}
            casc = len(set(e["affected_pages"]) & got) / len(e["affected_pages"])
        rows.append({**{k: e[k] for k in ("nullity_id", "expected", "injected", "note", "cote")},
                     "found_strict": bool(strict), "found_any": bool(hits),
                     "certainty": alerts[strict[0]].certainty if strict else (alerts[hits[0]].certainty if hits else None),
                     "page_ok": page_ok, "cascade_recall": casc})
    fps = [{"nullity_id": a.nullity_id, "certainty": a.certainty, "statement": a.statement_fr, "pages": [s.page for s in a.sources]}
           for i, a in enumerate(alerts) if i not in used and a.status == "possible_nullity"]
    extra_reading = sum(1 for i, a in enumerate(alerts) if i not in used and a.status == "needs_reading")
    return {"entries": rows, "false_positives": fps, "extra_needs_reading": extra_reading}


_PAGES_BY_NODE: dict[str, list[int]] = {}


def _node_pages(nid: str, _a: Check) -> list[int]:
    return _PAGES_BY_NODE.get(nid, [])[:1]


def aggregate(per_case: list[dict]) -> dict:
    by = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tp_any": 0, "decoys": 0, "decoy_fp": 0})
    cert = defaultdict(lambda: {"tp": 0, "fp": 0})
    page_ok = page_n = 0
    casc = []
    for c in per_case:
        for r in c["entries"]:
            b = by[r["nullity_id"]]
            if r["injected"] and r["expected"] == "possible_nullity":
                b["tp" if r["found_strict"] else "fn"] += 1
                b["tp_any"] += int(r["found_any"])
                if r["found_strict"]:
                    cert[r["certainty"]]["tp"] += 1
                    page_n += 1
                    page_ok += int(r["page_ok"])
            elif r["injected"]:  # expected needs_reading (contradictions, missing pieces)
                b["tp_any" if r["found_any"] else "fn"] += 1
                if r["found_any"]:
                    b["tp"] += 1
            else:
                b["decoys"] += 1
                if r["found_strict"]:
                    b["decoy_fp"] += 1
                    b["fp"] += 1
            if r["cascade_recall"] is not None:
                casc.append(r["cascade_recall"])
        for fp in c["false_positives"]:
            by[fp["nullity_id"]]["fp"] += 1
            cert[fp["certainty"]]["fp"] += 1
    table = []
    for nid, b in sorted(by.items()):
        tp, fn, fp = b["tp"], b["fn"], b["fp"]
        table.append({"nullity_id": nid, **b, "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                      "precision": round(tp / (tp + fp), 3) if tp + fp else None})
    tp = sum(b["tp"] for b in by.values())
    fn = sum(b["fn"] for b in by.values())
    fp = sum(b["fp"] for b in by.values())
    return {
        "per_nullity": table,
        "per_certainty": {k: {**v, "precision": round(v["tp"] / (v["tp"] + v["fp"]), 3) if v["tp"] + v["fp"] else None}
                          for k, v in cert.items()},
        "overall": {"tp": tp, "fn": fn, "fp": fp, "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                    "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                    "decoys": sum(b["decoys"] for b in by.values()), "decoy_fp": sum(b["decoy_fp"] for b in by.values())},
        "page_accuracy": round(page_ok / page_n, 3) if page_n else None,
        "cascade_recall": round(sum(casc) / len(casc), 3) if casc else None,
    }


def run(n: int = 10, seed0: int = 1, baseline: bool = True, progress=None) -> dict:
    from casebreak.graph import store
    from casebreak.pipeline import run_case
    from casebreak.synth import generate_random

    DOSSIERS.mkdir(parents=True, exist_ok=True)
    per_case, base_cases, pages_total, t0 = [], [], 0, time.time()
    for k in range(n):
        seed = seed0 + k
        d = DOSSIERS / f"nb{seed:03d}"
        if d.exists():
            shutil.rmtree(d)
        truth = generate_random(d, seed)
        cid = f"bench-{seed:03d}"
        from casebreak.config import CASES
        cd = CASES / cid
        if cd.exists():
            shutil.rmtree(cd)
        shutil.copytree(d, cd)
        run_case(cid, truth["files"], truth["title"])
        g, checks = store.load(cd)
        _PAGES_BY_NODE.update({nd.id: nd.pages for nd in g.nodes})
        sc = score_case(checks, truth)
        sc["seed"], sc["pages"] = seed, truth["pages"]
        per_case.append(sc)
        pages_total += truth["pages"]
        if baseline:
            base_cases.append(run_baseline(g, truth))
        shutil.rmtree(cd, ignore_errors=True)
        if progress:
            progress(k + 1, n)
    elapsed = time.time() - t0
    res = {
        "name": "NullityBench-FR", "version": "0.1", "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_dossiers": n, "pages": pages_total, "seconds": round(elapsed, 1),
        "seconds_per_1000_pages": round(elapsed / pages_total * 1000, 1) if pages_total else None,
        "casebreak": aggregate(per_case), "cases": per_case,
        "baseline": _agg_baseline(base_cases),
        "honesty": f"On our synthetic set of {n} case files ({pages_total} pages). The generator and the extractors were "
                   "written by the same team: this score measures the pipeline end to end, not generalisation to real "
                   "case files. Synthetic data is cleaner than reality; real validation requires anonymised files.",
    }
    (BENCH / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def _agg_baseline(cases: list[dict]) -> dict:
    if not cases or all(c.get("status") != "ok" for c in cases):
        reason = cases[0].get("reason") if cases else "not run"
        return {"status": "not_run", "reason": reason}
    tp = sum(c["tp"] for c in cases if c.get("status") == "ok")
    fn = sum(c["fn"] for c in cases if c.get("status") == "ok")
    fp = sum(c["fp"] for c in cases if c.get("status") == "ok")
    return {"status": "ok", "model": cases[0].get("model"), "tp": tp, "fn": fn, "fp": fp,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None, "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "matching": "same rule id AND a page of the faulty piece (same rule as CASEBREAK)",
            "id_only_recall": round(sum(c.get("id_only", 0) for c in cases if c.get("status") == "ok") / (tp + fn), 3) if tp + fn else None,
            "truncated_cases": sum(1 for c in cases if c.get("truncated"))}


def export_zip() -> bytes:
    """NullityBench-FR as an open benchmark: dossiers, ground truth, generator note, scorer, results."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("NullityBench-FR/README.md", README)
        res = BENCH / "results.json"
        if res.exists():
            z.write(res, "NullityBench-FR/results.json")
        z.write(Path(__file__), "NullityBench-FR/scorer/bench.py")
        for d in sorted(DOSSIERS.glob("nb*")):
            for f in d.rglob("*"):
                if f.is_file() and f.suffix in {".pdf", ".jpg", ".json"}:
                    z.write(f, f"NullityBench-FR/dossiers/{d.name}/{f.relative_to(d)}")
    return buf.getvalue()


README = """# NullityBench-FR (v0.1, synthetic)

**Fictional** French criminal case files (native police reports, scans with handwritten times, photos with EXIF)
with **injected** procedural irregularities and **decoys** (situations that look irregular but are lawful).

- `dossiers/nbXXX/dossier.pdf` + `photos/`: the case file to analyse.
- `dossiers/nbXXX/ground_truth.json`: ground truth `(nullity_id, doc, pages, expected, injected/decoy)`.
- `scorer/bench.py`: alert ↔ truth matching (same catalogue id, overlapping pages),
  recall/precision per nullity and per certainty level, page accuracy, cascade recall.
- `results.json`: CASEBREAK results (and the "LLM alone" baseline when run).

No real data. The legal content of the catalogue has not been validated by a lawyer.
Synthetic data ≠ real-world accuracy.
"""
