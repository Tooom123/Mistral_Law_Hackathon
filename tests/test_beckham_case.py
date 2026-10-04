"""The Beckham 2018 speeding case: the engine must find the defect the court found — the notice of intended
prosecution received on day 15 — without the file saying so, and must not cry wolf on the lawful points."""

import shutil

import pytest


@pytest.fixture(scope="module")
def beckham():
    from casebreak.config import CASES
    from casebreak.graph import store
    from casebreak.pipeline import run_case
    from casebreak.synth import generate_beckham

    d = CASES / "beckham-test"
    if d.exists():
        shutil.rmtree(d)
    truth = generate_beckham(d)
    run_case("beckham-test", truth["files"], "beckham")
    g, checks = store.load(d)
    return {"truth": truth, "graph": g, "checks": checks}


def test_file_is_split_and_classified(beckham):
    g = beckham["graph"]
    assert len(g.pieces) == 8 and {p.type for p in g.pieces} >= {"NIP", "POST_ROOM_REGISTER", "SUMMONS"}
    assert {n.category for n in g.nodes if n.type == "ACT"} == {"TRAFFIC", "KEEPER", "COURT"}


def test_the_outcome_is_not_written_in_the_file(beckham):
    text = " ".join(p.text.lower() for p in beckham["graph"].pages)
    assert "dismissed" not in text and "out of time" not in text and "technicality" not in text


def test_finds_the_notice_served_on_day_15(beckham):
    nip = next(c for c in beckham["checks"] if c.nullity_id == "NIP-01")
    entry = next(e for e in beckham["truth"]["entries"] if e["nullity_id"] == "NIP-01")
    assert nip.status == "possible_nullity" and nip.certainty == "documented"
    assert nip.details["day_posted"] == 10 and nip.details["day_received"] == 15
    assert {s.page for s in nip.sources} >= set(entry["pages"]) | {1, 4}
    assert nip.rank > 0 and nip.id == "A01"


def test_cascade_names_what_depends_on_the_notice(beckham):
    nip = next(c for c in beckham["checks"] if c.nullity_id == "NIP-01")
    assert set(nip.affected) == {"act:D6:driver_identification", "act:D7:summons", "act:D8:hearing_record"}


def test_lawful_points_are_not_flagged(beckham):
    by = {c.nullity_id: c for c in beckham["checks"]}
    assert by["NIP-02"].status == "satisfied" and by["NIP-03"].status == "satisfied"
    assert sum(1 for c in beckham["checks"] if c.rank > 0) == 1


def test_every_source_quote_is_on_its_page(beckham):
    g = beckham["graph"]
    pages = {p.page: p.text for p in g.pages}
    from casebreak.text import quote_on_page

    for c in beckham["checks"]:
        for s in c.sources:
            assert quote_on_page(s.quote, pages[s.page]), (c.nullity_id, s)


def test_if_the_notice_had_arrived_in_time_there_is_no_alert(beckham):
    """Counter-test: same graph, receipt moved to day 14 → the rule is satisfied (the engine reads dates, not words)."""
    from casebreak.nullities.engine import run_checks

    g = beckham["graph"].model_copy(deep=True)
    reg = next(n for n in g.nodes if n.subtype == "post_room_entry")
    reg.attrs["nip_received_at"].value = "2018-02-06T09:40:00"
    nip = next(c for c in run_checks(g) if c.nullity_id == "NIP-01")
    assert nip.status == "satisfied"


def test_demo_endpoint_defaults_to_beckham():
    import time

    from fastapi.testclient import TestClient

    from casebreak.api.app import app

    c = TestClient(app)
    r = c.post("/cases/demo?pace=0").json()
    assert "Beckham" in r["title"]
    for _ in range(300):
        st = c.get(f"/cases/{r['case_id']}/status").json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["state"] == "done", st.get("error")
    alerts = c.get(f"/cases/{r['case_id']}/alerts").json()
    top = alerts[0] if isinstance(alerts, list) else alerts["alerts"][0]
    assert top["nullity_id"] == "NIP-01"
    card = c.get(f"/cases/{r['case_id']}/alerts/{top['id']}").json()
    assert card["why"]["article"].startswith("s.1 Road Traffic Offenders Act 1988") and card["why"]["affected_count"] == 3
    trib = c.get(f"/cases/{r['case_id']}/alerts/{top['id']}/tribunal").json()
    assert "art. 171" not in str(trib)  # French-law objections are not applied to an English case
    assert c.post("/cases/demo?case=nope").status_code == 400
