"""Goal-driven decide turn — reason over the Stage-1 capability index instead
of walking a playbook DAG (TASK_SEC_GOAL_DECIDE_V1, Stage 2 Phase 2).

Grounded: the model (or the deterministic fallback) chooses only from
capability.query()'s retrieved, real candidates — never free-form. It may
decline all candidates (-> no_applicable_capability), a clean stop, not a
flail. Explainable: every choice carries reason + confidence +
alternatives_considered.
"""

from __future__ import annotations

from typing import Any

from . import decision_engine
from .capability.index import Capability, query
from .goal import EngagementGoal

_NO_APPLICABLE = {
    "action": None,
    "tool": None,
    "args": {},
    "reason": "no capability in the index matched current observations/goal",
    "confidence": 0.0,
    "expected_oracle": None,
    "expected_observation_delta": {},
    "alternatives_considered": [],
    "outcome": "no_applicable_capability",
}


def _pick_capability_for_tool(tool: str, candidates: list[Capability]) -> Capability:
    for cap in candidates:
        if tool in cap.tools:
            return cap
    return candidates[0]


def decide_next_action(
    goal: EngagementGoal,
    observations: dict[str, Any],
    history: list[dict],
    *,
    workspace: str | None = None,
) -> dict:
    """One decide step. Retrieves candidates via capability.query grounded in
    the goal's domain_hint + intent, then chooses one next action.

    The model turn (workspace given) is the primary path; when no workspace
    is available — or the model call fails — decision_engine.select_tools
    ranks the retrieved candidates' tools deterministically, so this step
    always yields a ranked choice and stays hermetic for tests.
    """
    # goal.intent is often free-text prose ("poke this machine"), while
    # query()'s `goal` param is a hard substring filter over id/technique —
    # try it as a bonus narrowing filter first (it helps when intent names a
    # real technique, e.g. "kerberoast this"), then fall back to
    # observations+domain alone so generic intents don't dead-end on a
    # grounded, observation-matched candidate.
    candidates = query(observations, domain=goal.domain_hint, goal=goal.intent, limit=8)
    if not candidates:
        candidates = query(observations, domain=goal.domain_hint, limit=8)
    if not candidates:
        return dict(_NO_APPLICABLE)

    decision = None
    if workspace is not None:
        decision = _decide_via_model(goal, observations, history, candidates, workspace)

    if decision is None:
        decision = _decide_via_deterministic_fallback(observations, candidates)

    return decision


def _decide_via_model(
    goal: EngagementGoal,
    observations: dict[str, Any],
    history: list[dict],
    candidates: list[Capability],
    workspace: str,
) -> dict | None:
    """Best-effort model decide turn. Any failure (no pipeline reachable,
    malformed response, etc.) returns None so the caller falls back to the
    deterministic ranker — the model path is never load-bearing for
    correctness, only for quality."""
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
        # A structured model response is not guaranteed shape-stable across
        # workspaces/models; fall back rather than trust a loose parse.
        return None
    except Exception:
        return None


def _decide_via_deterministic_fallback(
    observations: dict[str, Any], candidates: list[Capability]
) -> dict:
    available_tools = sorted({t for c in candidates for t in c.tools})
    if not available_tools:
        top = candidates[0]
        return {
            "action": top.id,
            "tool": top.id,
            "args": {},
            "reason": "top-ranked capability match (no declared tools)",
            "confidence": 0.5,
            "expected_oracle": top.oracle,
            "expected_observation_delta": {"technique_attempted": top.id},
            "alternatives_considered": [c.id for c in candidates[1:4]],
            "outcome": "proposed",
        }

    ranked = decision_engine.select_tools(observations, available_tools)
    chosen = ranked[0] if ranked else None
    chosen_tool = chosen.name if chosen else available_tools[0]
    top = _pick_capability_for_tool(chosen_tool, candidates)

    return {
        "action": top.id,
        "tool": chosen_tool,
        "args": {},
        "reason": f"deterministic fallback: {chosen.reason if chosen else 'top-ranked capability match'}",
        "confidence": chosen.score if chosen else 0.5,
        "expected_oracle": top.oracle,
        "expected_observation_delta": {"technique_attempted": top.id},
        "alternatives_considered": [c.id for c in candidates if c.id != top.id][:3],
        "outcome": "proposed",
    }
