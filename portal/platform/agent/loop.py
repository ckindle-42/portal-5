"""The bounded agent loop engine — the reusable "key" for every module.

Borrows the Campaign Supervisor's discipline: caps, a confidence floor,
flag-for-human, and honest-BLOCKED over faked-green. Each iteration:
decide -> execute (module Executor) -> fold observation delta -> check
budget/stop/confidence. Everything is event-driven; the only wall-clock bound
is the goal's declared budget (a safety backstop, not control flow).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .decide import decide_next_action
from .goal import validate_goal


@dataclass
class LoopResult:
    outcome: str  # completed | blocked | budget_exhausted | invalid_goal | flagged_for_human
    iterations: int
    observations: dict[str, Any]
    trajectory: list[dict] = field(default_factory=list)
    reason: str = ""
    flagged: list[dict] = field(default_factory=list)


def run_loop(
    goal: Any,
    *,
    provider: Any,
    executor: Any,
    model_turn: Any | None = None,
    confidence_floor: float = 0.0,
    observations: dict[str, Any] | None = None,
) -> LoopResult:
    problems = validate_goal(goal)
    if problems:
        return LoopResult(
            outcome="invalid_goal",
            iterations=0,
            observations={},
            reason="; ".join(problems),
        )

    obs: dict[str, Any] = dict(observations or {})
    history: list[dict] = []
    flagged: list[dict] = []
    budget = goal.budget
    max_iters = int(budget.get("max_iterations", 0))
    max_wall = float(budget.get("max_wall_clock_sec", 0))
    started = time.monotonic()

    i = 0
    while i < max_iters:
        if max_wall and (time.monotonic() - started) >= max_wall:
            return LoopResult(
                "budget_exhausted", i, obs, history, "wall-clock budget reached", flagged
            )

        decision = decide_next_action(goal, obs, history, provider=provider, model_turn=model_turn)

        if decision.get("outcome") == "no_applicable_capability":
            # Clean stop, not a flail: nothing grounded to try.
            return LoopResult("blocked", i, obs, history, decision.get("reason", ""), flagged)

        if float(decision.get("confidence", 0.0)) < confidence_floor:
            # Below the floor -> surface for a human rather than guess.
            flagged.append({"iteration": i, "decision": decision, "why": "confidence_below_floor"})
            return LoopResult(
                "flagged_for_human", i, obs, history, "confidence below floor", flagged
            )

        step = executor.execute(decision, {"observations": obs, "history": history})
        record = {"iteration": i, "decision": decision, "result": step}
        history.append(record)

        delta = step.get("observation_delta") or {}
        if isinstance(delta, dict):
            obs.update(delta)

        i += 1

        if _stop_satisfied(goal.stop_when, obs):
            return LoopResult("completed", i, obs, history, "stop condition satisfied", flagged)

    return LoopResult("budget_exhausted", i, obs, history, "max_iterations reached", flagged)


def _stop_satisfied(stop_when: list[dict] | None, observations: dict[str, Any]) -> bool:
    if not stop_when:
        return False
    for cond in stop_when:
        key = cond.get("observation")
        if key is None:
            continue
        want = cond.get("equals", True)
        if observations.get(key) == want:
            return True
    return False
