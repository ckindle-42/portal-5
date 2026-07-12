import asyncio

import portal.platform.inference.router.context_inject as ci


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_extract_snippets_shapes():
    assert ci._extract_snippets({"error": "x"}) == []
    assert ci._extract_snippets({"results": [{"text": "a"}, "b"]}) == ["a", "b"]
    assert ci._extract_snippets({"memories": [{"content": "m"}]}) == ["m"]
    assert ci._extract_snippets({"text": "solo"}) == ["solo"]
    assert ci._extract_snippets({}) == []


def test_extract_unknown_shape_raises():
    import pytest

    with pytest.raises(ValueError):
        ci._extract_snippets({"weird": 123})


def test_inject_merges_into_system():
    body = {
        "messages": [
            {"role": "system", "content": "base"},
            {"role": "user", "content": "q"},
        ]
    }
    out = ci._inject_context_block(body, "Header:", ["x"])
    assert "Header:" in out["messages"][0]["content"]
    assert out["messages"][0]["content"].startswith("base")


def test_inject_prepends_when_no_system():
    body = {"messages": [{"role": "user", "content": "q"}]}
    out = ci._inject_context_block(body, "Header:", ["x"])
    assert out["messages"][0]["role"] == "system"


def test_recall_noop_when_not_opted_in(monkeypatch):
    monkeypatch.setattr(ci, "_AUTO_MEMORY_ENABLED", True)
    body = {"messages": [{"role": "user", "content": "hi"}]}
    out = asyncio.run(ci.inject_recalled_memory("ws-without-flag", body, "cid"))
    assert out == body


def test_salience_explicit_marker():
    msgs = [{"role": "user", "content": "Please remember that my rig is an M4 Pro."}]
    assert ci._salient_user_text(msgs, "ws") is not None


def test_salience_skips_ordinary_question():
    msgs = [{"role": "user", "content": "what is the capital of France?"}]
    assert ci._salient_user_text(msgs, "ws") is None
