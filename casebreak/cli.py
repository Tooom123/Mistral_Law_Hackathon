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
    sub.add_parser("demo", help="Generate and analyse the synthetic demo case file")
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
        from casebreak.synth import DEMO_TITLE, generate_demo

        d = CASES / "demo-cli"
        shutil.rmtree(d, ignore_errors=True)
        truth = generate_demo(d)
        run_case("demo-cli", truth["files"], DEMO_TITLE)
        _, checks = store.load(d)
        for c in sorted((c for c in checks if c.rank > 0), key=lambda c: -c.rank):
            print(f"{c.id}  {c.nullity_id:7} {c.status:16} {c.certainty:13} p.{','.join(str(s.page) for s in c.sources):8} "
                  f"{len(c.affected):2} affected  {c.statement_fr}")
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


if __name__ == "__main__":
    main()
