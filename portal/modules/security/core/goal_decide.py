"""Goal-driven decide turn (security).

The grounded decide-turn now lives in portal.platform.agent.decide
(TASK_AGENT_LOOP_PLATFORM_V1). This module supplies security's grounding: a
CapabilityProvider wrapping capability.query, and the (quality-only) model turn
that renders security capabilities and calls the pipeline. Public signature is
unchanged: decide_next_action(goal, observations, history, *, workspace=None).
"""

from __future__ import annotations

from typing import Any

from portal.platform.agent.decide import decide_next_action as _platform_decide

from .capability.index import Capability, query
from .goal import EngagementGoal


class _SecurityCapabilityProvider:
    """Adapts security's capability.query to the platform CapabilityProvider."""

    def query(
        self,
        observations: dict[str, Any],
        *,
        domain: str | None = None,
        goal: str | None = None,
        limit: int = 8,
    ) -> list[Capability]:
        if goal is not None:
            return query(observations, domain=domain, goal=goal, limit=limit)
        return query(observations, domain=domain, limit=limit)


def _decide_via_model(
    goal: EngagementGoal,
    observations: dict[str, Any],
    history: list[dict],
    candidates: list[Capability],
    workspace: str,
) -> dict | None:
    """Best-effort model decide turn. Any failure returns None so the caller
    falls back to the deterministic ranker — never load-bearing for correctness.
    """
    try:
        from .capability.render import render_capabilities, render_tool_arsenal

        rendered = render_capabilities(candidates)
        arsenal = render_tool_arsenal(phase=candidates[0].phase)
        prompt = (
            f"Goal: {goal.intent} (role={goal.role})\n"
            f"Observations so far: {observations}\n"
            f"History: {len(history)} prior step(s)\n\n"
            f"Candidate capabilities:\n{rendered}\n\n"
            f"Available tools:\n{arsenal}\n\n"
            "Choose exactly ONE next action from the candidates above. "
            "Respond with the capability id, the tool to use, and your reasoning."
        )
        from . import call_pipeline  # local import: optional/live dependency

        raw_text, _elapsed = call_pipeline(workspace, prompt)
        if not raw_text:
            return None
        # Loose parse is not shape-stable across models; fall back rather than trust it.
        return None
    except Exception:
        return None


def decide_next_action(
    goal: EngagementGoal,
    observations: dict[str, Any],
    history: list[dict],
    *,
    workspace: str | None = None,
) -> dict:
    """One decide step, grounded in security's capability index. Delegates the
    control flow to the platform decide-turn; supplies the security provider and
    (when a workspace is available) the security model turn.
    """
    model_turn = None
    if workspace is not None:
        model_turn = lambda g, o, h, c: _decide_via_model(g, o, h, c, workspace)  # noqa: E731

    return _platform_decide(
        goal,
        observations,
        history,
        provider=_SecurityCapabilityProvider(),
        model_turn=model_turn,
    )
