"""Rules are data: a YAML entry + the generic engine, no Python per rule. Rule-driven extraction fills only gaps."""

import copy
from datetime import datetime

import pytest

from casebreak.nullities import dsl
from casebreak.nullities.versions import load_attributes, load_catalogue
from casebreak.schemas import Attr, Node, Nullity, Src


def test_no_python_function_per_rule():
    import casebreak.nullities as pkg
    from pathlib import Path

    assert not (Path(pkg.__file__).parent / "checks.py").exists()
    for nl in load_catalogue().values():
        for v in nl.versions:
            assert not hasattr(v, "check")


def test_every_attribute_read_by_a_rule_is_described():
    reg = load_attributes()
    missing = {k for subtype, keys in dsl.needs_by_subtype(load_catalogue()).items() for k in keys if k not in reg}
    assert not missing, f"describe these attributes in nullities/attributes.yaml: {sorted(missing)}"


def test_expressions_are_sandboxed():
    for bad in ["__import__('os')", "open('x')", "(lambda: 1)()", "x.__class__", "[c for c in 'a']"]:
        with pytest.raises(dsl.RuleError):
            dsl.compile_expr(bad)


def test_a_new_rule_is_only_yaml(demo_case):
    """A rule nobody coded: 'search lasting more than 60 min' — written as data, evaluated by the generic engine."""
    g = demo_case["graph"]
    rule = Nullity(**{
        "id": "TST-01", "category": "PERQUISITION_SAISIE", "title": "Long search", "article": "— (test)",
        "applies_to": ["search"],
        "versions": [{"params": {"max": 60},
                      "let": {"s": "t('start')", "e": "t('end')", "m": "minutes(s, e)"},
                      "outcomes": [
                          {"when": "m is None", "status": "skip"},
                          {"when": "m > params['max']", "status": "possible_nullity",
                           "say": "Search lasted {dur(m)} ({hm(s)} → {hm(e)}).", "cite": ["start", "end"]},
                          {"when": "True", "status": "satisfied", "say": "Search lasted {dur(m)}."}]}]})
    dsl.validate_version(rule.versions[0])
    ctx = dsl.GraphCtx(g.nodes, g.edges, {p.page: p for p in g.pages})
    night = next(n for n in g.nodes if n.subtype == "search" and n.val("is_home") is True and n.end)
    res = dsl.evaluate(rule.versions[0], night, ctx)
    assert res.status == "possible_nullity"
    assert "21:35 → 23:10" in res.statement and {s.page for s in res.sources} == {11}


def test_paths_reach_related_acts(demo_case):
    g = demo_case["graph"]
    ctx = dsl.GraphCtx(g.nodes, g.edges, {p.page: p for p in g.pages})
    hearing = next(n for n in g.nodes if n.subtype == "hearing" and n.val("in_custody"))
    env = dsl.Env(hearing, ctx, {})
    assert env.attr("custody.custody_start") is not None
    assert env.attr("rights_notification.lawyer_requested") is not None
    assert env.attr("custody.@start").value.startswith("2026-")


def test_gap_fill_keeps_only_verified_quotes(demo_case, monkeypatch):
    from casebreak.graph import fill
    from casebreak.nullities.engine import run_checks

    g = copy.deepcopy(demo_case["graph"])
    srch = next(n for n in g.nodes if n.subtype == "search" and n.val("is_home") is True and n.end)
    srch.attrs.pop("start")
    srch.start = None
    gaps: list = []
    run_checks(g, use_judge=False, gaps=gaps)
    assert (srch.id, "start") in gaps
    p11 = next(p for p in g.pages if p.page == 11).text
    real = next(line for line in p11.split("\n") if "21h35" in line).strip()

    def fake(system, user, model=None, cache=True, purpose="chat"):
        if "Search" in user:
            return {"attrs": {"start": {"found": True, "value": "21:35", "page": 11, "quote": real}}, "_model": "fake"}
        return {"attrs": {k: {"found": True, "value": True, "page": 1, "quote": "texte inventé absent de la page"}
                          for k in ("prosecutor_informed_at", "seal_number", "special_regime")}, "_model": "fake"}

    monkeypatch.setattr(fill.mistral, "chat_json", fake)
    monkeypatch.setattr(fill.settings.__class__, "mistral", property(lambda s: True))
    n = fill.fill_gaps(g, gaps)
    assert n == 1
    a = srch.attrs["start"]
    assert a.status == "inferred" and a.value == "2026-09-15T21:35:00" and a.src.page == 11
    checks = run_checks(g, use_judge=False)
    prq = next(c for c in checks if c.nullity_id == "PRQ-01" and c.node_id == srch.id)
    assert prq.status == "possible_nullity" and prq.certainty == "inferred"  # never "documented" on model output
