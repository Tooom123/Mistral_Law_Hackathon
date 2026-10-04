"""Conflict-of-interest audit on the McKinsey case, offline."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

from casebreak.coi import precedents, run_audit
from casebreak.coi.casefile import mckinsey


@pytest.fixture(scope="module")
def audit():
    return run_audit("mckinsey")


def by_rule(a, rule):
    return [f for f in a["flags"] if f["rule"] == rule]


def test_expected_flags(audit):
    assert {p for f in by_rule(audit, "COI-01") for p in f["persons"]} == {"Clara Vasseur", "Julien Marchetti"}
    assert by_rule(audit, "COI-02")[0]["persons"] == ["Clara Vasseur"]
    assert by_rule(audit, "COI-04")[0]["persons"] == ["Mathilde Rousseau"]
    missing = by_rule(audit, "COI-03")[0]
    assert len(missing["persons"]) == 6 and "Raphaël Dumont" in missing["persons"]
    assert len(by_rule(audit, "COI-06")) == 2
    assert by_rule(audit, "COI-05")[0]["certainty"] == "inferred"
    assert [f["id"] for f in audit["flags"]] == [f"F{i}" for i in range(1, 9)]


def test_decoys_are_cleared(audit):
    flagged = {p for f in audit["flags"] if f["rule"] in ("COI-01", "COI-02") for p in f["persons"]}
    assert "Inès Haddad" not in flagged and "Thomas Le Gall" not in flagged
    assert any("Medilab SA" in c["text"] for c in audit["cleared"])


def test_every_evidence_span_is_on_its_page(audit):
    docs = {d.id: d for d in mckinsey().docs}
    for f in audit["flags"]:
        assert f["evidence"]
        for e in f["evidence"]:
            text = docs[e["doc"]].pages[e["page"] - 1]
            assert text[e["start"]:e["end"]] == e["quote"]


def test_counter_case_true_declaration_removes_the_flag():
    case = mckinsey()
    d05 = next(d for d in case.docs if d.id == "D05")
    pages = [p.replace("company in the health sector? [ ] Yes [X] No", "company in the health sector? [X] Yes [ ] No")
             .replace("affected by the order? [ ] Yes [X] No", "affected by the order? [X] Yes [ ] No") for p in d05.pages]
    case.docs[case.docs.index(d05)] = dataclasses.replace(d05, pages=pages)
    assert not by_rule(run_audit(case=case), "COI-02")


def test_counter_case_recusal_outside_window():
    case = mckinsey()
    d02 = next(d for d in case.docs if d.id == "D02")
    pages = [p.replace("09/2014 to 09/2019", "09/2010 to 09/2016") for p in d02.pages]
    case.docs[case.docs.index(d02)] = dataclasses.replace(d02, pages=pages)
    a = run_audit(case=case)
    assert not by_rule(a, "COI-04")
    assert any(c["rule"] == "COI-04" for c in a["cleared"])


def test_precedents_ranked_and_anchored_on_public_record(audit):
    for f in audit["flags"]:
        assert len(f["precedents"]) == 3
        assert any(p["provenance"] == "public_record" for p in f["precedents"])
        assert set(f["patterns"]) & set(f["precedents"][0]["patterns"])
    hits = precedents.search("former employee signs contract awarded to former employer", ["revolving_door"], k=5)
    assert all("revolving_door" in h["patterns"] for h in hits[:3])
    st = precedents.stats()
    assert st["total"] >= 40 and st["by_provenance"]["public_record"] >= 15


def test_api():
    from casebreak.api.app import app

    c = TestClient(app)
    a = c.get("/api/coi/cases/mckinsey").json()
    assert a["stats"]["flags"] == 8 and a["documents"][0]["pages"][0]["text"]
    assert c.get("/api/coi/cases/nope").status_code == 404
    memo = c.get("/api/coi/cases/mckinsey/flags/F1/memo").text
    assert memo.startswith("# F1") and "Where to look" in memo
    r = c.get("/api/coi/precedents", params={"q": "declaration of interests", "pattern": "missing_declaration"}).json()
    assert r["results"] and r["stats"]["total"] >= 40
