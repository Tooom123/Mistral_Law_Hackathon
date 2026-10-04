"""Command line: `casebreak serve | demo | bench | synth`."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(prog="casebreak", description="Find the procedural flaw before the deadline does.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="API + front end on http://localhost:8000")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    dm = sub.add_parser("demo", help="Generate and analyse a synthetic demo case file")
    dm.add_argument("--case", default="beckham", choices=["beckham", "mathurins"])
    co = sub.add_parser("coi", help="Conflict-of-interest audit of a case file (default: the McKinsey case)")
    co.add_argument("--case", default="mckinsey")
    co.add_argument("--llm", action="store_true", help="add Mistral reviewer notes (needs MISTRAL_API_KEY)")
    co.add_argument("--export", type=Path, help="write the audit JSON (the front end's offline snapshot)")
    co.add_argument("--memo", help="print the review memo of one flag, e.g. F1")
    co.add_argument("--pdf", type=Path, help="write the case file as one PDF per document into this folder")
    sub.add_parser("doctor", help="Check which engines work with the keys in .env (one tiny call per Mistral path)")
    b = sub.add_parser("bench", help="NullityBench-FR: N synthetic case files, recall/precision")
    b.add_argument("--n", type=int, default=10)
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--no-baseline", action="store_true")
    y = sub.add_parser("synth", help="Generate a synthetic case file (PDF + photos + ground truth)")
    y.add_argument("--out", type=Path, required=True)
    y.add_argument("--seed", type=int, default=0, help="0 = demo case file")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("casebreak.api.app:app", host=a.host, port=a.port, reload=a.reload)
    elif a.cmd == "demo":
        from casebreak.config import CASES
        from casebreak.graph import store
        from casebreak.pipeline import run_case
        from casebreak.synth import DEMO_CASES

        title, generate = DEMO_CASES[a.case]
        d = CASES / "demo-cli"
        shutil.rmtree(d, ignore_errors=True)
        truth = generate(d)
        run_case("demo-cli", truth["files"], title)
        _, checks = store.load(d)
        for c in sorted((c for c in checks if c.rank > 0), key=lambda c: -c.rank):
            print(f"{c.id}  {c.nullity_id:7} {c.status:16} {c.certainty:13} p.{','.join(str(s.page) for s in c.sources):8} "
                  f"{len(c.affected):2} affected  {c.statement_fr}")
    elif a.cmd == "coi":
        from casebreak.coi.audit import memo, run_audit

        if a.pdf:
            from casebreak.coi.casefile import CASES as COI_CASES, write_pdfs

            paths = write_pdfs(COI_CASES[a.case](), a.pdf)
            print(f"{len(paths)} PDFs written to {a.pdf}")
            return
        res = run_audit(a.case, llm=a.llm)
        if a.memo:
            print(memo(res, a.memo))
            return
        st = res["stats"]
        print(f"{res['case']['title']} — {st['documents']} documents, {st['pages']} pages, {st['facts']} facts, "
              f"{st['cross_references']} cross-references, {st['ms']} ms")
        for f in res["flags"]:
            pages = ", ".join(sorted({f"{e['doc']} p.{e['page']}" for e in f["evidence"]}))
            print(f"{f['id']:3} {f['rule']} {f['severity']:6} {f['certainty']:11} {f['headline']}\n"
                  f"    → {pages}\n    ≈ " + "; ".join(p["citation"] for p in f["precedents"]))
        print(f"cleared: {st['cleared']} checks")
        if a.export:
            a.export.parent.mkdir(parents=True, exist_ok=True)
            a.export.write_text(json.dumps(res, ensure_ascii=False, indent=1))
            from casebreak.coi import precedents as P

            db = a.export.with_name("precedents.json")
            db.write_text(json.dumps({"stats": P.stats(), "patterns": P.PATTERNS, "results": P.load()},
                                     ensure_ascii=False, indent=1))
            print(f"written {a.export} and {db}")
    elif a.cmd == "doctor":
        _doctor()
    elif a.cmd == "bench":
        from casebreak.eval.bench import run

        res = run(n=a.n, seed0=a.seed, baseline=not a.no_baseline, progress=lambda k, n: print(f"  case file {k}/{n}"))
        print(json.dumps({k: res[k] for k in ("n_dossiers", "pages", "seconds_per_1000_pages")}, ensure_ascii=False))
        print(json.dumps(res["casebreak"]["overall"], ensure_ascii=False))
        print("baseline:", json.dumps(res["baseline"], ensure_ascii=False))
        print(res["honesty"])
    elif a.cmd == "synth":
        from casebreak.synth import generate_demo, generate_random

        t = generate_demo(a.out) if a.seed == 0 else generate_random(a.out, a.seed)
        print(f"{t['pages']} pages, {t['pieces']} pieces, {len(t['entries'])} ground-truth entries → {a.out}")


def _doctor() -> None:
    import io

    from PIL import Image, ImageDraw

    from casebreak.config import settings
    from casebreak.llm import mistral

    print("engines:", json.dumps(settings.engines()))
    if not settings.mistral:
        print("No MISTRAL_API_KEY in .env: everything runs offline (Tesseract OCR, patterns, deterministic judge).")
        return
    img = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(img).text((20, 40), "Le 15 septembre 2026 a 21h35, nous transportons au domicile", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    probes = [
        ("chat (fast)", lambda: mistral.chat_meta([{"role": "user", "content": "Say ok"}], model=settings.fast_model, timeout=30)[1]),
        ("extract", lambda: mistral.chat_json("Answer in JSON {\"ok\": true}", "ping", model=settings.extract_model, cache=False)["_model"]),
        ("judge / tribunal / baseline", lambda: mistral.chat_json("Answer in JSON {\"ok\": true}", "ping", model=settings.judge_model, cache=False)["_model"]),
        ("ocr", lambda: "{1} → {0!r}".format(*mistral.ocr_image(buf.getvalue(), "image/png"))),
    ]
    if settings.lean_model:
        probes.append(("leanstral", lambda: mistral.chat_meta([{"role": "user", "content": "Say ok"}], model=settings.lean_model, fallback=False)[1]))
    for name, fn in probes:
        try:
            print(f"  ✓ {name:28} {fn()}")
        except mistral.MistralUnavailable as e:
            print(f"  ✕ {name:28} {e}")
    if mistral.refused_models():
        print("Refused on this workspace (403 or 0 req/min quota):", ", ".join(mistral.refused_models()))
        print("→ the next model of MISTRAL_FALLBACK_MODELS is used instead; enable a plan in the Mistral console to use them.")


if __name__ == "__main__":
    main()
