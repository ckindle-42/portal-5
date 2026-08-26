"""Budget + LoopResult (no LLM, no RE MCP)."""

from portal.modules.binary_research.harness.loop import Budget, LoopResult


def test_budget_turns():
    b = Budget(max_turns=2, max_tool_calls=100)
    b.tick_turn()
    b.tick_turn()
    assert not b.ok()


def test_budget_tools():
    b = Budget(max_turns=100, max_tool_calls=2)
    b.tick_tool("a", hash("1"))
    b.tick_tool("b", hash("2"))
    assert not b.ok()


def test_stuck():
    b = Budget(max_repeat_same_call=3)
    for _ in range(3):
        b.tick_tool("cmd", hash("out"))
    assert b.is_stuck("cmd", hash("out"))


def test_not_stuck_varying():
    b = Budget(max_repeat_same_call=3)
    for i in range(5):
        b.tick_tool("cmd", hash(f"out{i}"))
    assert not b.is_stuck("cmd", hash("new"))


def test_result():
    assert LoopResult("completed", 5, 12).outcome == "completed"
    assert LoopResult("error", 1, 0, error="x").error == "x"
