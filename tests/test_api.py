"""The §9 API on the demo dossier, offline."""

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client_case():
    from casebreak.api.app import app

    c = TestClient(app)
    cid = c.post("/cases/demo?pace=0&case=mathurins").json()["case_id"]
    for _ in range(300):
        st = c.get(f"/cases/{cid}/status").json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["state"] == "done", st.get("error")
    return c, cid


def test_status_counters(client_case):
    c, cid = client_case
    st = c.get(f"/cases/{cid}/status").json()
    assert st["counters"]["pages"] == 120 and st["counters"]["alerts"] >= 10
    assert all(s["state"] == "done" for s in st["stages"].values())


def test_graph_lanes_and_sources(client_case):
    c, cid = client_case
    g = c.get(f"/cases/{cid}/graph").json()
    assert "GARDE_A_VUE" in g["lanes"]
    acts = [n for n in g["nodes"] if n["type"] == "ACT"]
    assert any(n["subtype"] == "garde_a_vue" for n in acts)
    assert any(e["kind"] == "SUPPORTS" for e in g["edges"]) and any(e["kind"] == "CONTRADICTS" for e in g["edges"])
    pseudo = c.get(f"/cases/{cid}/graph?pseudo=true").json()
    assert "VASSEUR" not in str([n["label"] for n in pseudo["nodes"]])


def test_alert_card_four_questions(client_case):
    c, cid = client_case
    al = c.get(f"/cases/{cid}/alerts").json()
    top = al["alerts"][0]
    assert top["status"] == "possible_nullity"
    card = c.get(f"/cases/{cid}/alerts/{top['id']}").json()
    assert card["what"] and card["where"] and card["why"]["article"] and card["next"]
    assert al["deadline"]["status"] == "to verify"
    parquet = c.get(f"/cases/{cid}/alerts?mode=prosecution").json()["alerts"][0]
    assert parquet["headline"].startswith("Regularity issue")


def test_page_highlight(client_case):
    c, cid = client_case
    top = c.get(f"/cases/{cid}/alerts").json()["alerts"][0]
    src = top["where"][0]
    page = c.get(f"/cases/{cid}/pages/{src['doc_id']}/{src['page']}?alert={top['id']}").json()
    assert page["highlights"], "the quoted line must be highlighted"
    img = c.get(page["image"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"


def test_simulate_and_review(client_case):
    c, cid = client_case
    al = c.get(f"/cases/{cid}/alerts").json()["alerts"]
    prq = next(a for a in al if a["nullity_id"] == "PRQ-01" and a["status"] == "possible_nullity")
    sim = c.post(f"/cases/{cid}/simulate", json={"node_id": prq["node"]["id"]}).json()
    assert sim["count"] >= 5 and sim["waves"] >= 2
    r = c.post(f"/cases/{cid}/alerts/{prq['id']}/review", json={"decision": "accepted", "note": "à plaider"}).json()
    assert r["decision"] == "accepted"
    assert c.get(f"/cases/{cid}/alerts/{prq['id']}").json()["review"]["decision"] == "accepted"


def test_time_travel(client_case):
    c, cid = client_case
    now = c.get(f"/cases/{cid}/alerts").json()["alerts"]
    old = c.get(f"/cases/{cid}/alerts?as_of=2023-06-01").json()["alerts"]
    gav08 = lambda lst: [a for a in lst if a["nullity_id"] == "GAV-08" and a["status"] == "possible_nullity"]  # noqa: E731
    assert gav08(now) and not gav08(old)


def test_tribunal_and_proof(client_case):
    c, cid = client_case
    al = c.get(f"/cases/{cid}/alerts").json()["alerts"]
    gav04 = next(a for a in al if a["nullity_id"] == "GAV-04")
    t = c.get(f"/cases/{cid}/alerts/{gav04['id']}/tribunal").json()
    assert t["presiding"]["verdict"] in ("survives", "survives_with_caveats")
    assert any(o["hint"] == "no_prejudice" and o["strength"] == "principle" for o in t["prosecution"]["objections"])
    decoy = next(a for a in al if a["nullity_id"] == "GAV-05")
    td = c.get(f"/cases/{cid}/alerts/{decoy['id']}/tribunal").json()
    assert any(o["strength"] == "supported" for o in td["prosecution"]["objections"])
    p = c.get(f"/cases/{cid}/alerts/{gav04['id']}/proof").json()
    assert "theorem" in p["code"] and p["status"] in ("proved", "unchecked")


def test_report_md_pdf(client_case):
    c, cid = client_case
    md = c.get(f"/cases/{cid}/report?format=md").text
    assert "Grounds of nullity to examine" in md and "p. " in md
    pdf = c.get(f"/cases/{cid}/report?format=pdf")
    assert pdf.content[:4] == b"%PDF"


def test_precedents_without_key(client_case):
    c, cid = client_case
    top = c.get(f"/cases/{cid}/alerts").json()["alerts"][0]
    p = c.get(f"/cases/{cid}/alerts/{top['id']}/precedents").json()
    assert p["status"] == "unavailable" and p["results"] == []
