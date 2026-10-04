"""Synthetic dossiers with injected nullities, decoys and ground truth (ARCHITECTURE.md §8)."""

from __future__ import annotations

from pathlib import Path

from casebreak.synth.render import render_case
from casebreak.synth.scenario import demo_case, random_case

DEMO_TITLE = "Affaire des Mathurins (synthétique)"


def generate_demo(out_dir: Path) -> dict:
    return render_case(demo_case(), out_dir, DEMO_TITLE)


def generate_random(out_dir: Path, seed: int) -> dict:
    return render_case(random_case(seed), out_dir, f"NullityBench-FR #{seed:03d} (synthétique)")
