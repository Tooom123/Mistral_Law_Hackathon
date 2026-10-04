"""Mistral client without network: model fallback chain, JSON parsing, Markdown cleanup."""

import pytest

from casebreak.llm import mistral


def test_md_to_text_keeps_the_words():
    md = "# PROCÈS-VERBAL N$^{\\circ}$ 2026/00873/11\n**Objet** : PERQUISITION\n| a | b |\n|---|---|\n"
    out = mistral.md_to_text(md)
    assert "PROCÈS-VERBAL N° 2026/00873/11" in out
    assert "Objet : PERQUISITION" in out
    assert "|" not in out and "**" not in out


def test_parse_json_fenced():
    assert mistral._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert mistral._parse_json('Sure: {"a": 2} done') == {"a": 2}


def test_fallback_skips_refused_models(monkeypatch):
    monkeypatch.setattr(mistral, "_DEAD", {})
    monkeypatch.setattr(mistral, "_mark_dead", lambda m: mistral._DEAD.__setitem__(m, 0))
    monkeypatch.setattr(mistral, "_headers", lambda: {})
    calls = []

    def fake_post(path, body, timeout, retries=3):
        calls.append(body["model"])
        if body["model"] != "ministral-14b-latest":
            raise mistral.ModelRefused(f"{body['model']} refused")
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(mistral, "_post", fake_post)
    monkeypatch.setattr(mistral.settings.__class__, "mistral", property(lambda s: True))
    text, used = mistral.chat_meta([{"role": "user", "content": "x"}], model="mistral-large-latest", purpose="t")
    assert used == "ministral-14b-latest" and text == '{"ok": true}'
    assert calls[0] == "mistral-large-latest"
    assert "mistral-large-latest" in mistral._DEAD
    # a refused model is not tried again
    calls.clear()
    mistral.chat_meta([{"role": "user", "content": "x"}], model="mistral-large-latest", purpose="t")
    assert "mistral-large-latest" not in calls


def test_no_fallback_for_leanstral(monkeypatch):
    monkeypatch.setattr(mistral, "_DEAD", {})
    monkeypatch.setattr(mistral, "_mark_dead", lambda m: None)

    def fake_post(path, body, timeout, retries=3):
        raise mistral.ModelRefused("labs model")

    monkeypatch.setattr(mistral, "_post", fake_post)
    monkeypatch.setattr(mistral, "_headers", lambda: {})
    with pytest.raises(mistral.MistralUnavailable):
        mistral.chat_meta([{"role": "user", "content": "x"}], model="labs-leanstral-1-5-1", fallback=False)


def test_tribunal_verdict_consistent_with_objections(demo_case):
    from casebreak.tribunal.court import _presiding, deliberate

    g, checks = demo_case["graph"], demo_case["checks"]
    for c in [c for c in checks if c.rank > 0]:
        t = deliberate(c, g)
        assert t["presiding"]["verdict"] == _presiding(c, t["prosecution"]["objections"])["verdict"]
