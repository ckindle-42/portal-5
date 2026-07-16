"""Objective-mode emergent entry (DESIGN_EMERGENT_LAB_AGENT_V2 Δ2, invariants D1/I4/I7).

Flag-gated (`PORTAL_EMERGENT=1`, default off — I7). Builds an `EngagementGoal`
with no pinned scenario / no seeded first-move and runs the platform
`run_loop` against the live lab via `SecurityExecutor`. Budget derives from
the capability graph (D1, `derive_max_iterations`).

The platform loop (`portal.platform.agent.loop.run_loop`) is NOT edited. The
event-driven no-progress halt (I4) is implemented by stepping `run_loop` one
iteration at a time from this wrapper and stopping BLOCKED(no-progress) when
neither the observation delta nor the oracle result advances for
`no_progress_k` consecutive iterations — budget remains only the backstop.
"""

from __future__ import annotations

import os
from typing import Any

from portal.modules.security.core.goal import EngagementGoal
from portal.modules.security.core.loop import HARD_MAX_ITERATIONS, HARD_MAX_WALL_CLOCK_SEC

PORTAL_EMERGENT_FLAG = "PORTAL_EMERGENT"
_SLACK = 2.5
_DEFAULT_NO_PROGRESS_K = 3

# Objective-class -> keywords used to find known procedures targeting it, so
# the derived budget (D1) is grounded in real known-path length, not a guess.
_OBJECTIVE_PROCEDURE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "da_equivalent": ("da", "domain_admin", "kerberoast", "golden_ticket"),
    "host_foothold": ("foothold", "initial_access", "rce", "exploit"),
    "credential": ("cred", "kerberoast", "dump", "harvest"),
    "data_access": ("exfil", "data", "share"),
}


def emergent_enabled() -> bool:
    return os.environ.get(PORTAL_EMERGENT_FLAG) == "1"


def derive_max_iterations(objective_class: str, graph: Any = None) -> int:
    """D1: longest known procedure path to this objective class x slack, hard-capped.

    `graph` defaults to a freshly seeded CapabilityGraph (real assets, not
    invented). Falls back to a floor of 1 known step when no procedure
    matches, so an unrecognized objective class still gets a bounded budget.
    """
    if graph is None:
        from portal.modules.security.core.capability_graph import seed_graph_from_assets

        graph = seed_graph_from_assets()

    keywords = _OBJECTIVE_PROCEDURE_KEYWORDS.get(objective_class, ())
    procs = list(graph.procedures.values())
    matching = (
        [p for p in procs if any(k in p.scenario.lower() for k in keywords)] if keywords else procs
    )

    longest = max((len(p.technique_ids) for p in matching), default=1)
    derived = max(1, int(longest * _SLACK))
    return min(derived, HARD_MAX_ITERATIONS)


def _step_progressed(obs_before: dict, obs_after: dict, step_result: dict) -> bool:
    """Progress means the observed state actually changed, or the oracle
    advanced — never just "the executor returned a non-empty delta" (the
    Executor always attaches bookkeeping keys like last_tool/last_target,
    which are non-empty on every step regardless of whether anything moved).
    """
    oracle_advance = step_result.get("oracle_result") is True
    return obs_before != obs_after or oracle_advance


def run_with_no_progress_halt(
    goal: EngagementGoal,
    *,
    provider: Any,
    executor: Any,
    observations: dict[str, Any] | None = None,
    no_progress_k: int = _DEFAULT_NO_PROGRESS_K,
) -> Any:
    """I4: the real stop condition is event-driven, budget is a backstop.

    Steps `run_loop` one iteration at a time (the platform loop is never
    edited) so this wrapper can halt BLOCKED(no-progress) independently of
    the budget check inside `run_loop` itself.
    """
    from portal.platform.agent.loop import LoopResult, run_loop

    obs = dict(observations or {})
    trajectory: list[dict] = []
    flagged: list[dict] = []
    max_iters = int(goal.budget.get("max_iterations", 0))
    stagnant = 0
    iterations = 0

    step_goal = EngagementGoal(
        intent=goal.intent,
        role=goal.role,
        targets=goal.targets,
        scope=goal.scope,
        budget={**goal.budget, "max_iterations": 1},
        stop_when=goal.stop_when,
        domain_hint=goal.domain_hint,
    )

    while iterations < max_iters:
        obs_before = dict(obs)
        result = run_loop(step_goal, provider=provider, executor=executor, observations=obs)
        obs = result.observations
        trajectory.extend(result.trajectory)
        flagged.extend(result.flagged)

        if result.outcome != "budget_exhausted":
            # invalid_goal / blocked / flagged_for_human / completed all end the run here.
            return LoopResult(
                result.outcome,
                iterations + len(result.trajectory),
                obs,
                trajectory,
                result.reason,
                flagged,
            )

        if not result.trajectory:
            return LoopResult(
                "blocked", iterations, obs, trajectory, "no iteration executed", flagged
            )

        step_result = result.trajectory[-1]["result"]
        iterations += 1
        stagnant = 0 if _step_progressed(obs_before, obs, step_result) else stagnant + 1
        if stagnant >= no_progress_k:
            return LoopResult(
                "blocked", iterations, obs, trajectory, "no-progress halt (I4)", flagged
            )

    return LoopResult(
        "budget_exhausted", iterations, obs, trajectory, "max_iterations reached", flagged
    )


def run_emergent_engagement(
    *,
    targets: list[str],
    objective_class: str = "host_foothold",
    intent: str | None = None,
    domain_hint: str | None = None,
    provider: Any = None,
    executor: Any = None,
    no_progress_k: int = _DEFAULT_NO_PROGRESS_K,
) -> dict:
    """PORTAL_EMERGENT-gated top-level entry (I7).

    Flag-off => inert, existing paths unchanged (no goal built, nothing runs).
    Flag-on => builds a goal with no pinned scenario / no seeded first-move
    and runs it to a no-progress halt or budget exhaustion.
    Artifact = the returned `trajectory` (mirrors `LoopResult.trajectory`).
    """
    if not emergent_enabled():
        return {"status": "disabled", "reason": f"{PORTAL_EMERGENT_FLAG} flag is off"}

    from portal.modules.security.core.goal import validate_goal
    from portal.modules.security.core.goal_decide import _SecurityCapabilityProvider
    from portal.modules.security.core.objective_executor import SecurityExecutor

    max_iterations = derive_max_iterations(objective_class)
    goal = EngagementGoal(
        intent=intent or f"reach {objective_class} state",
        role="red",
        targets=list(targets),
        scope={"targets": list(targets)},
        budget={
            "max_iterations": max_iterations,
            "max_wall_clock_sec": HARD_MAX_WALL_CLOCK_SEC,
            "max_lab_actions": max_iterations,
        },
        domain_hint=domain_hint,
    )
    problems = validate_goal(goal)
    if problems:
        return {"status": "rejected", "reason": "; ".join(problems)}

    result = run_with_no_progress_halt(
        goal,
        provider=provider or _SecurityCapabilityProvider(),
        executor=executor or SecurityExecutor(),
        observations={},
        no_progress_k=no_progress_k,
    )
    return {
        "status": result.outcome,
        "objective_class": objective_class,
        "max_iterations": max_iterations,
        "iterations": result.iterations,
        "trajectory": result.trajectory,
        "observations": result.observations,
        "reason": result.reason,
        "flagged": result.flagged,
    }
