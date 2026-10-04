def test_bench_two_dossiers():
    """NullityBench-FR end to end on 2 random dossiers; baseline is skipped without a key."""
    from casebreak.eval.bench import export_zip, run

    res = run(n=2, seed0=101)
    o = res["casebreak"]["overall"]
    assert o["tp"] + o["fn"] > 0 and o["recall"] is not None
    assert res["baseline"]["status"] == "not_run"
    assert "synthétique" in res["honesty"]
    assert export_zip()[:2] == b"PK"
