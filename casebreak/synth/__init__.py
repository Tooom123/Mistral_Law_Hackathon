"""Synthetic dossiers with injected nullities, decoys and ground truth (ARCHITECTURE.md §8)."""

from __future__ import annotations

from pathlib import Path

from casebreak.synth import beckham
from casebreak.synth.render import render_case
from casebreak.synth.scenario import demo_case, random_case

DEMO_TITLE = "The Mathurins case (synthetic)"
BECKHAM_TITLE = beckham.TITLE


def generate_demo(out_dir: Path) -> dict:
    return render_case(demo_case(), out_dir, DEMO_TITLE)


def generate_random(out_dir: Path, seed: int) -> dict:
    return render_case(random_case(seed), out_dir, f"NullityBench-FR #{seed:03d} (synthetic)")


def generate_beckham(out_dir: Path) -> dict:
    """The 2018 Beckham speeding case, reconstructed from public reports (every document synthetic)."""
    return beckham.generate(out_dir)


# name → (title, generator). The demo the team presents is the first one.
DEMO_CASES = {
    "beckham": (BECKHAM_TITLE, generate_beckham),
    "mathurins": (DEMO_TITLE, generate_demo),
}
DEFAULT_DEMO = "beckham"
