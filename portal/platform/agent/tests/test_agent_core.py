"""Hermetic tests for the platform agent core. No network, no live pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from portal.platform.agent import (
    Goal,
    decide_next_action,
    run_loop,
    select_tools,
    validate_goal,
)


@dataclass
class FakeCap:
    id: str
    tools: list[str]
    oracle: str | None = None


class FakeProvider:
    def __init__(self, caps):
        self._caps = caps
        self.calls = []

    def query(self, observations, *, domain=None, goal=None, limit=8):
        self.calls.append({"domain": domain, "goal": goal})
        return list(self._caps)


class ScriptedExecutor:
    """Reveals open_ports on step 0, then flips `owned` true on step 1."""

    def __init__(self):
        self.n = 0

    def execute(self, decision, state):
        self.n += 1
        if self.n == 1:
            return {"observation_delta": {"open_ports": [445]}, "oracle_result": None, "raw": {}}
        return {"observation_delta": {"owned": True}, "oracle_result": True, "raw": {}}


def _goal(**kw):
    base = {
        "intent": "poke the box",
        "scope": {"targets": ["10.10.11.5"]},
        "budget": {"max_iterations": 5, "max_wall_clock_sec": 0, "max_lab_actions": 5},
        "stop_when": [{"observation": "owned", "equals": True}],
        "domain_hint": "ad",
    }
    base.update(kw)
    return Goal(**base)


def test_validate_goal_rejects_unbounded():
    assert "scope.targets is empty or missing" in validate_goal(Goal(intent="x"))
    assert any("budget" in p for p in validate_goal(Goal(intent="x", scope={"targets": ["a"]})))
    assert validate_goal(_goal()) == []


def test_decide_is_grounded_and_deterministic():
    prov = FakeProvider([FakeCap("cap.a", ["exploit_smb"]), FakeCap("cap.b", ["check_ldap"])])
    d = decide_next_action(_goal(), {}, [], provider=prov)
    assert d["outcome"] == "proposed"
    assert d["tool"] in {"exploit_smb", "check_ldap"}
    assert "alternatives_considered" in d
    # narrowed-by-intent query is tried first
    assert prov.calls[0]["goal"] == "poke the box"


def test_decide_declines_when_no_candidates():
    d = decide_next_action(_goal(), {}, [], provider=FakeProvider([]))
    assert d["outcome"] == "no_applicable_capability"
    assert d["action"] is None


def test_model_turn_is_never_load_bearing():
    prov = FakeProvider([FakeCap("cap.a", ["exploit_smb"])])
    d = decide_next_action(_goal(), {}, [], provider=prov, model_turn=lambda *a: None)
    assert d["outcome"] == "proposed"  # fell through to deterministic ranker


def test_loop_completes_on_stop_condition():
    prov = FakeProvider([FakeCap("cap.a", ["exploit_smb"])])
    res = run_loop(_goal(), provider=prov, executor=ScriptedExecutor())
    assert res.outcome == "completed"
    assert res.observations.get("owned") is True
    assert res.iterations >= 1


def test_loop_honest_blocked_not_faked_green():
    res = run_loop(_goal(), provider=FakeProvider([]), executor=ScriptedExecutor())
    assert res.outcome == "blocked"  # no applicable capability -> clean stop


def test_loop_respects_iteration_budget():
    prov = FakeProvider([FakeCap("cap.a", ["scan"])])

    class Noop:
        def execute(self, d, s):
            return {"observation_delta": {}, "oracle_result": None, "raw": {}}

    res = run_loop(
        _goal(budget={"max_iterations": 2, "max_wall_clock_sec": 0, "max_lab_actions": 2}),
        provider=prov,
        executor=Noop(),
    )
    assert res.outcome == "budget_exhausted"
    assert res.iterations == 2


def test_loop_flags_low_confidence():
    prov = FakeProvider([FakeCap("cap.a", [])])  # no tools -> confidence 0.5

    class Noop:
        def execute(self, d, s):
            return {"observation_delta": {}, "raw": {}}

    res = run_loop(_goal(), provider=prov, executor=Noop(), confidence_floor=0.9)
    assert res.outcome == "flagged_for_human"
    assert res.flagged


def test_invalid_goal_short_circuits():
    res = run_loop(Goal(intent="x"), provider=FakeProvider([]), executor=ScriptedExecutor())
    assert res.outcome == "invalid_goal"


def test_select_tools_initial_coverage():
    cands = select_tools({}, ["a", "b", "c", "d"])
    assert [c.name for c in cands] == ["a", "b", "c"]


def test_writeback_is_hermetic(tmp_path):
    from portal.platform.agent import writeback
    from portal.platform.wiki.writeback import list_proposed, reset_proposed_dir, set_proposed_dir

    set_proposed_dir(tmp_path)
    try:
        pid = writeback.record_outcome(
            title="loop outcome — smoke",
            body="# outcome\n\nreached owned=true",
            sources=[{"type": "agent-loop", "path": "trajectory:test"}],
            tags=["agent-loop", "test"],
        )
        assert pid
        assert any(u.status == "proposed" for u in list_proposed())
    finally:
        reset_proposed_dir()
