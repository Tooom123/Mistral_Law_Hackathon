from datetime import date, datetime

from casebreak.deadlines.clock import add_months
from casebreak.ingest.ocr import repair_ocr
from casebreak.privacy.pseudonymize import mask, unmask
from casebreak.synth import fr
from casebreak.text import norm, quote_on_page


def test_norm_keeps_length():
    s = "Procès-verbal n° 12 — « Théo » œuvre"
    assert len(norm(s)) == len(s)
    assert norm("GARDÉ À VUE") == "garde a vue"


def test_quote_must_be_on_page():
    assert quote_on_page("placé en garde  à vue", "Il est\nplacé en garde à vue à 11h05")
    assert not quote_on_page("placé à 10h35", "placé à 11h05")


def test_french_numbers_roundtrip():
    from casebreak.facts.normalize_time import parse_time, words_to_int

    for n in [1, 5, 17, 21, 31, 45, 59]:
        assert words_to_int(fr.int_fr(n, feminine=True)) == n
    dt = datetime(2026, 9, 15, 21, 35)
    assert parse_time("à " + fr.time_words(dt)).hour == 21


def test_pseudonymize_roundtrip():
    text = "Notifions à VASSEUR Théo, né le 04/02/1998, demeurant 14, allée des Tilleuls à Valmorin."
    masked, m = mask(text)
    assert "VASSEUR" not in masked and "1998" not in masked and "Tilleuls" not in masked
    assert unmask(masked, m) == text


def test_ocr_repair():
    assert repair_ocr("Mettons fin la garde 4 vue a 12 H 35") == "Mettons fin à la garde à vue à 12 H 35"
    assert repair_ocr("Le 4 décembre") == "Le 4 décembre"


def test_add_months():
    assert add_months(date(2026, 9, 21), 4) == date(2027, 1, 21)
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)


def test_lean_rejects_false_statement():
    """The Lean kernel is the judge: a false inequality must not be 'proved'."""
    import pytest

    from casebreak.config import settings
    from casebreak.proofs.lean import _check

    if settings.lean is None:
        pytest.skip("lean not installed")
    bad = "def a : Nat := 100\ndef b : Nat := 200\ntheorem t : a > b := by decide\n"
    assert _check(settings.lean, bad, "test_false")["status"] == "failed"
    good = "def a : Nat := 300\ndef b : Nat := 200\ntheorem t : a > b := by decide\n"
    assert _check(settings.lean, good, "test_true")["status"] == "proved"
