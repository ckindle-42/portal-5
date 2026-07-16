"""Slice 1.3 gate: objective-mode emergent entry (D1 budget, I4 no-progress, I7 flag).

The platform run_loop is never edited (see objective_entry.py docstring) — the
no-progress halt is implemented by this module's own step-wise wrapper, so
these tests exercise that wrapper directly with fake provider/executor pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from portal.modules.security.core.goal import EngagementGoal
from portal.modules.security.core.objective_entry import (
    derive_max_iterations,
    run_emergent_engagement,
    run_with_no_progress_halt,
)


class _FakeCapability:
    def __init__(self, cap_id="probe", tools=("run_nmap_scan",), oracle=None):
        self.id = cap_id
        self.tools = list(tools)
        self.oracle = oracle


class _FakeProvider:
    def query(self, observations, *, domain=None, goal=None, limit=8):
        return [_FakeCapability()]


class _FakeExecutor:
    """Returns a scripted sequence of results, one per call."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def execute(self, decision, state):
        step = self._results[min(self.calls, len(self._results) - 1)]
        self.calls += 1
        return step


def _goal(max_iterations=10, targets=("10.10.11.5",)) -> EngagementGoal:
    return EngagementGoal(
        intent="reach host_foothold state",
        role="red",
        targets=list(targets),
        scope={"targets": list(targets)},
        budget={
            "max_iterations": max_iterations,
            "max_wall_clock_sec": 3600,
            "max_lab_actions": max_iterations,
        },
    )


# ── D1: derived budget ───────────────────────────────────────────────────────


@dataclass
class _FakeProc:
    scenario: str
    technique_ids: frozenset = field(default_factory=frozenset)


class _FakeGraph:
    def __init__(self, procedures):
        self.procedures = {f"proc-{i}": p for i, p in enumerate(procedures)}


def test_derive_max_iterations_grounded_in_matching_procedure():
    graph = _FakeGraph(
        [
            _FakeProc("kerberoast_to_da", frozenset({"T1558.003", "T1078", "T1021"})),
            _FakeProc("unrelated_scenario", frozenset({"T1595"})),
        ]
    )
    # longest matching (da_equivalent -> "kerberoast_to_da") technique count is 3, slack 2.5 -> 7
    assert derive_max_iterations("da_equivalent", graph=graph) == 7


def test_derive_max_iterations_hard_capped():
    graph = _FakeGraph([_FakeProc("kerberoast_to_da", frozenset({f"T{i}" for i in range(100)}))])
    from portal.modules.security.core.loop import HARD_MAX_ITERATIONS

    assert derive_max_iterations("da_equivalent", graph=graph) == HARD_MAX_ITERATIONS


def test_derive_max_iterations_no_match_floors_to_one_slack():
    graph = _FakeGraph([_FakeProc("totally_unrelated", frozenset({"T1595"}))])
    assert derive_max_iterations("da_equivalent", graph=graph) >= 1


# ── I4: no-progress halt ─────────────────────────────────────────────────────


def test_no_progress_halts_blocked_after_k_stagnant_iterations():
    stagnant_step = {"observation_delta": {}, "oracle_result": None, "raw": "no change"}
    executor = _FakeExecutor([stagnant_step] * 10)
    result = run_with_no_progress_halt(
        _goal(max_iterations=10), provider=_FakeProvider(), executor=executor, no_progress_k=3
    )
    assert result.outcome == "blocked"
    assert result.reason == "no-progress halt (I4)"
    assert result.iterations == 3  # halts at K, not at budget


def test_progress_resets_stagnation_and_runs_to_budget():
    class _GenuinelyProgressingExecutor:
        """Each step reports a distinct observation key — real new information,
        not the same static delta repeated (which would itself be stagnation)."""

        def __init__(self):
            self.calls = 0

        def execute(self, decision, state):
            self.calls += 1
            return {
                "observation_delta": {f"step_{self.calls}": True},
                "oracle_result": None,
                "raw": "ok",
            }

    executor = _GenuinelyProgressingExecutor()
    result = run_with_no_progress_halt(
        _goal(max_iterations=5), provider=_FakeProvider(), executor=executor, no_progress_k=3
    )
    assert result.outcome == "budget_exhausted"
    assert result.iterations == 5


def test_blocked_from_no_applicable_capability_propagates_immediately():
    class _EmptyProvider:
        def query(self, observations, *, domain=None, goal=None, limit=8):
            return []

    executor = _FakeExecutor([{"observation_delta": {}, "oracle_result": None, "raw": ""}])
    result = run_with_no_progress_halt(
        _goal(max_iterations=10), provider=_EmptyProvider(), executor=executor, no_progress_k=3
    )
    assert result.outcome == "blocked"
    assert executor.calls == 0  # no_applicable_capability short-circuits before execute


# ── I7: flag gate ────────────────────────────────────────────────────────────


def test_flag_off_is_inert(monkeypatch):
    monkeypatch.delenv("PORTAL_EMERGENT", raising=False)
    executor = _FakeExecutor([{"observation_delta": {}, "oracle_result": None, "raw": ""}])
    result = run_emergent_engagement(
        targets=["10.10.11.5"], provider=_FakeProvider(), executor=executor
    )
    assert result == {"status": "disabled", "reason": "PORTAL_EMERGENT flag is off"}
    assert executor.calls == 0  # nothing executed


def test_flag_on_builds_unseeded_goal_and_runs(monkeypatch):
    monkeypatch.setenv("PORTAL_EMERGENT", "1")
    progressing_step = {"observation_delta": {"changed": True}, "oracle_result": None, "raw": "ok"}
    executor = _FakeExecutor([progressing_step])
    result = run_emergent_engagement(
        targets=["10.10.11.5"],
        objective_class="host_foothold",
        provider=_FakeProvider(),
        executor=executor,
        no_progress_k=1,
    )
    assert result["status"] in ("budget_exhausted", "blocked", "completed")
    assert executor.calls >= 1
    assert isinstance(result["trajectory"], list)


def test_flag_on_threads_domain_hint_into_provider_query(monkeypatch):
    """--domain-hint (added after live verification surfaced that the
    default None domain_hint let the ranker pick a non-lab-dispatchable
    capability) must reach provider.query(domain=...)."""
    monkeypatch.setenv("PORTAL_EMERGENT", "1")

    seen_domains = []

    class _RecordingProvider:
        def query(self, observations, *, domain=None, goal=None, limit=8):
            seen_domains.append(domain)
            return [_FakeCapability()]

    executor = _FakeExecutor(
        [{"observation_delta": {"changed": True}, "oracle_result": None, "raw": "ok"}]
    )
    run_emergent_engagement(
        targets=["10.10.11.5"],
        domain_hint="ad",
        provider=_RecordingProvider(),
        executor=executor,
        no_progress_k=1,
    )
    assert "ad" in seen_domains


def test_flag_on_rejects_empty_targets(monkeypatch):
    monkeypatch.setenv("PORTAL_EMERGENT", "1")
    result = run_emergent_engagement(
        targets=[], provider=_FakeProvider(), executor=_FakeExecutor([])
    )
    assert result["status"] == "rejected"
