"""L0 end to end on the frozen demo dossier: every injected nullity found on its page, decoys not flagged."""

from casebreak.text import quote_on_page, quote_on_page_loose


def _alerts(checks):
    return [c for c in checks if c.status in ("possible_nullity", "needs_reading")]


def test_pages_and_pieces(demo_case):
    g = demo_case["graph"]
    assert len(g.pages) == demo_case["truth"]["pages"]
    assert len(g.pieces) == demo_case["truth"]["pieces"]
    assert any(p.ocr == "tesseract" for p in g.pages) or all(p.ocr != "tesseract" for p in g.pages)


def test_injected_nullities_found_on_their_page(demo_case):
    alerts = _alerts(demo_case["checks"])
    for e in demo_case["truth"]["entries"]:
        if not e["injected"]:
            continue
        hits = [a for a in alerts if a.nullity_id == e["nullity_id"] and
                {s.page for s in a.sources} & set(e["piece_pages"] + e["pages"])]
        assert hits, f"missed {e['nullity_id']} ({e['note']})"
        if e["expected"] == "possible_nullity":
            assert any(h.status == "possible_nullity" for h in hits), e


def test_decoys_not_flagged(demo_case):
    alerts = [c for c in demo_case["checks"] if c.status == "possible_nullity"]
    for e in demo_case["truth"]["entries"]:
        if e["injected"]:
            continue
        bad = [a for a in alerts if a.nullity_id == e["nullity_id"] and {s.page for s in a.sources} & set(e["piece_pages"])]
        assert not bad, f"decoy flagged: {e['note']}"


def test_every_attribute_quote_is_on_its_page(demo_case):
    g = demo_case["graph"]
    pages = {p.page: p for p in g.pages}
    n = 0
    for node in g.nodes:
        for a in node.attrs.values():
            if a.src is None:
                continue
            n += 1
            text = pages[a.src.page].text
            assert quote_on_page(a.src.quote, text) or quote_on_page_loose(a.src.quote, text), (node.id, a.src)
    assert n > 50


def test_cascade_of_night_search(demo_case):
    prq = next(c for c in demo_case["checks"] if c.nullity_id == "PRQ-01" and c.status == "possible_nullity")
    labels = {n.id: n for n in demo_case["graph"].nodes}
    affected = [labels[a].subtype for a in prq.affected]
    assert "seizure" in affected and "seal_analysis" in affected and "mise_en_examen" in affected


def test_law_as_of_date_gav08():
    """Same hearing: possible nullity under the 2024 law, lawful under the old 2-hour rule."""
    from datetime import date

    from casebreak.config import CASES
    from casebreak.graph import store
    from casebreak.nullities.engine import run_checks

    g, _ = store.load(CASES / "demo-test")
    now = [c for c in run_checks(g, use_judge=False) if c.nullity_id == "GAV-08" and c.node_id == "act:D10:hearing"][0]
    old = [c for c in run_checks(g, as_of=date(2023, 5, 1), use_judge=False)
           if c.nullity_id == "GAV-08" and c.node_id == "act:D10:hearing"][0]
    assert now.status == "possible_nullity"
    assert old.status == "satisfied" and "2h15" in old.statement_fr
