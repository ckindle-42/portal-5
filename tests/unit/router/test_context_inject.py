import pytest

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


def test_salience_explicit_marker():
    msgs = [{"role": "user", "content": "Please remember that my rig is an M4 Pro."}]
    assert ci._salient_user_text(msgs, "ws") is not None


def test_salience_skips_ordinary_question():
    msgs = [{"role": "user", "content": "what is the capital of France?"}]
    assert ci._salient_user_text(msgs, "ws") is None


@pytest.mark.asyncio
async def test_recalled_memory_stays_system_side_and_traces_only_ids_and_scores(monkeypatch):
    from portal.platform.inference.router import trace

    memories = [
        {
            "id": f"memory-{index}",
            "text": f"Security CVE exploitation and purple team example {index}.",
            "similarity": 0.81 - index / 100,
            "category": "project_context",
            "tags": ["private-tag"],
        }
        for index in range(4)
    ]

    async def dispatch(tool, args, request_id):
        assert tool == "recall"
        assert args["query"] == "Kubernetes RoleBinding request"
        return {"memories": memories}

    monkeypatch.setitem(ci.WORKSPACES, "auto-daily", {"inject_memory": True})
    monkeypatch.setattr(ci, "_AUTO_MEMORY_ENABLED", True)
    monkeypatch.setattr(ci.tool_registry, "dispatch", dispatch)
    record = trace.TurnTrace("test-private-memory-receipt")
    record.set(routing_receipt={"scorer": "router_handoff_gate", "memory_chars_excluded": 0})
    token = trace._current.set(record)
    body = {"messages": [{"role": "user", "content": "Kubernetes RoleBinding request"}]}
    try:
        result = await ci.inject_recalled_memory("auto-daily", body, "test-cid")
        receipt = record.to_dict()
    finally:
        trace._current.reset(token)

    assert result["messages"][0]["role"] == "system"
    assert result["messages"][-1] == body["messages"][0]
    assert receipt["memory_injected"] == 4
    assert receipt["memory_recall"] == [
        {"id": memory["id"], "score": memory["similarity"]} for memory in memories
    ]
    assert receipt["routing_receipt"]["memory_chars_excluded"] == sum(
        len(memory["text"]) for memory in memories
    )
