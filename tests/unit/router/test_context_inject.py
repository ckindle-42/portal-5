import asyncio

import portal.platform.inference.router.context_inject as ci


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


def test_writeback_noop_when_not_opted_in(monkeypatch):
    monkeypatch.setattr(ci, "_AUTO_MEMORY_WRITEBACK_ENABLED", True)
    before = len(ci._writeback_tasks)
    ci.schedule_writeback(
        "ws-without-flag", [{"role": "user", "content": "remember that x"}], "cid"
    )
    assert len(ci._writeback_tasks) == before


def test_writeback_all_captures_everything(monkeypatch):
    from portal.platform.inference.router.workspaces import WORKSPACES

    monkeypatch.setitem(WORKSPACES, "ws-aggr", {"memory_writeback_all": True})
    msgs = [{"role": "user", "content": "the capital of France is Paris"}]
    assert ci._salient_user_text(msgs, "ws-aggr") is not None
