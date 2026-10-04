import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="casebreak-test-"))
os.environ["CASEBREAK_DATA"] = str(_TMP)
# Tests are offline by construction: never call external APIs, whatever the developer's .env says.
for k in ("MISTRAL_API_KEY", "TYPESAFE_API_KEY", "JUDILIBRE_KEY_ID"):
    os.environ[k] = ""
os.environ.setdefault("CASEBREAK_TODAY", "2026-10-04")


@pytest.fixture(scope="session")
def demo_case():
    """The demo dossier, generated and processed once for the whole test session."""
    from casebreak.config import CASES
    from casebreak.graph import store
    from casebreak.pipeline import run_case
    from casebreak.synth import generate_demo

    d = CASES / "demo-test"
    if d.exists():
        shutil.rmtree(d)
    truth = generate_demo(d)
    run_case("demo-test", truth["files"], "demo")
    g, checks = store.load(d)
    return {"dir": d, "truth": truth, "graph": g, "checks": checks}
