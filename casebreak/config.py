"""Settings. Everything runs offline; Mistral, Jev and Judilibre switch on only when their key is in `.env`."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("CASEBREAK_DATA", ROOT / "data"))
CASES = DATA / "cases"
CACHE = DATA / "cache"
BENCH = DATA / "bench"
FRONTEND = ROOT / "frontend"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    mistral_key: str = os.environ.get("MISTRAL_API_KEY", "")
    mistral_base: str = os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    ocr_model: str = os.environ.get("MISTRAL_OCR_MODEL", "mistral-ocr-latest")
    extract_model: str = os.environ.get("MISTRAL_EXTRACT_MODEL", "mistral-large-latest")
    judge_model: str = os.environ.get("MISTRAL_JUDGE_MODEL", "mistral-large-latest")
    fast_model: str = os.environ.get("MISTRAL_FAST_MODEL", "mistral-small-latest")
    # Tried in order when a model is refused (403/404) or has no quota on the workspace (429 with a 0 limit).
    fallback_models: tuple = tuple(m.strip() for m in os.environ.get(
        "MISTRAL_FALLBACK_MODELS",
        "mistral-medium-latest,mistral-small-latest,ministral-14b-latest,ministral-8b-latest,open-mistral-nemo",
    ).split(",") if m.strip())
    # Vision chat models used to transcribe a scan/photo when the /ocr endpoint is unavailable.
    vision_models: tuple = tuple(m.strip() for m in os.environ.get(
        "MISTRAL_VISION_MODELS", "mistral-small-latest,mistral-medium-latest,ministral-14b-latest,ministral-8b-latest",
    ).split(",") if m.strip())
    # Leanstral is a "Labs" model (e.g. labs-leanstral-1-5-1): an admin must enable Labs models on the workspace.
    lean_model: str = os.environ.get("MISTRAL_LEAN_MODEL", "")
    typesafe_key: str = os.environ.get("TYPESAFE_API_KEY", "")
    jev_base: str = os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai")
    judilibre_key: str = os.environ.get("JUDILIBRE_KEY_ID", "")
    judilibre_base: str = os.environ.get("JUDILIBRE_BASE_URL", "https://api.piste.gouv.fr/cassation/judilibre/v1.0")
    # Date used as "today" by the deadline clock (demo can freeze it).
    today: str = os.environ.get("CASEBREAK_TODAY", "")
    pseudonymize: bool = os.environ.get("CASEBREAK_PSEUDONYMIZE", "1") != "0"
    # Rule-driven extraction: ask Mistral for the attributes the rules needed and did not find (0 disables).
    llm_fill: bool = os.environ.get("CASEBREAK_LLM_FILL", "1") != "0"

    @property
    def mistral(self) -> bool:
        return bool(self.mistral_key)

    @property
    def jev(self) -> bool:
        return bool(self.typesafe_key)

    @property
    def judilibre(self) -> bool:
        return bool(self.judilibre_key)

    @property
    def tesseract(self) -> bool:
        return shutil.which("tesseract") is not None

    @property
    def lean(self) -> str | None:
        p = shutil.which("lean") or str(Path.home() / ".elan/bin/lean")
        return p if Path(p).exists() else None

    def engines(self) -> dict:
        return {
            "mistral": self.mistral, "jev": self.jev, "judilibre": self.judilibre,
            "tesseract": self.tesseract, "lean": self.lean is not None, "leanstral": self.mistral and bool(self.lean_model),
        }


settings = Settings()
for d in (CASES, CACHE, BENCH):
    d.mkdir(parents=True, exist_ok=True)
