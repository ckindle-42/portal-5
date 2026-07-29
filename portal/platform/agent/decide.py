"""Grounded decide-turn — reason over retrieved candidates, never free-form.

Promoted from portal.modules.security.core.goal_decide and generalized: the
concrete capability source is injected as a `provider` (CapabilityProvider),
and the optional model turn is injected as `model_turn` so the platform does
not hardcode any module's prompt/rendering. Deterministic-fallback path is
hermetic (no network), so tests never require a live pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import rank

ModelTurn = Callable[[Any, dict, list, list], dict | None]

_NO_APPLICABLE: dict[str, Any] = {
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


def _attempted_actions(history: list[dict]) -> set[str]:
    """Read action ids from both platform-loop and direct decision histories."""
    attempted: set[str] = set()
    for entry in history:
        if not isinstance(entry, dict):
            continue
        decision = entry.get("decision") if isinstance(entry.get("decision"), dict) else entry
        action = decision.get("action") or decision.get("tool")
        if isinstance(action, str) and action:
            attempted.add(action)
    return attempted


def _select_capability(candidates: list[Any], history: list[dict]) -> tuple[Any, str]:
    """Choose capability progression before ranking tools within that capability."""
    attempted = _attempted_actions(history)
    unattempted = [cap for cap in candidates if cap.id not in attempted]
    if not unattempted:
        return candidates[0], "all grounded capabilities attempted; retrying top match"

    attempted_recon = any(
        cap.id in attempted and getattr(cap, "phase", "") == "recon" for cap in candidates
    )
    if attempted_recon:
        oracle_candidates = [cap for cap in unattempted if getattr(cap, "oracle", None)]
        if oracle_candidates:
            return oracle_candidates[0], "progressing from reconnaissance to an oracle-bound action"
        non_recon = [cap for cap in unattempted if getattr(cap, "phase", "") != "recon"]
        if non_recon:
            return non_recon[0], "progressing beyond completed reconnaissance"

    if not history:
        recon_candidates = [cap for cap in unattempted if getattr(cap, "phase", "") == "recon"]
        if recon_candidates:
            return recon_candidates[0], "initial reconnaissance coverage"

    return unattempted[0], "next unattempted grounded capability"


def decide_next_action(
    goal: Any,
    observations: dict[str, Any],
    history: list[dict],
    *,
    provider: Any,
    model_turn: ModelTurn | None = None,
) -> dict:
    """One decide step. Retrieves grounded candidates via `provider.query`
    (narrowed by goal.intent first, then observations+domain alone), then
    chooses one next action. The model turn is quality-only and never
    load-bearing: any None result falls through to the deterministic ranker.
    """
    domain = getattr(goal, "domain_hint", None)
    intent = getattr(goal, "intent", None)

    candidates = provider.query(observations, domain=domain, goal=intent, limit=8)
    if not candidates:
        candidates = provider.query(observations, domain=domain, limit=8)
    if not candidates:
        return dict(_NO_APPLICABLE)

    decision = None
    if model_turn is not None:
        decision = model_turn(goal, observations, history, candidates)

    if decision is None:
        decision = _decide_via_deterministic_fallback(observations, candidates, history)

    return decision


def _decide_via_deterministic_fallback(
    observations: dict[str, Any],
    candidates: list[Any],
    history: list[dict],
) -> dict:
    top, progression_reason = _select_capability(candidates, history)
    available_tools = sorted(top.tools)
    if not available_tools:
        return {
            "action": top.id,
            "tool": top.id,
            "args": {},
            "reason": f"{progression_reason} (capability has no declared tool)",
            "confidence": 0.5,
            "expected_oracle": getattr(top, "oracle", None),
            "expected_observation_delta": {"technique_attempted": top.id},
            "alternatives_considered": [c.id for c in candidates[1:4]],
            "outcome": "proposed",
        }

    ranked = rank.select_tools(observations, available_tools)
    chosen = ranked[0] if ranked else None
    chosen_tool = chosen.name if chosen else available_tools[0]

    return {
        "action": top.id,
        "tool": chosen_tool,
        "args": {},
        "reason": (
            f"deterministic fallback: {progression_reason}; "
            f"{chosen.reason if chosen else 'top-ranked tool match'}"
        ),
        "confidence": chosen.score if chosen else 0.5,
        "expected_oracle": getattr(top, "oracle", None),
        "expected_observation_delta": {"technique_attempted": top.id},
        "alternatives_considered": [c.id for c in candidates if c.id != top.id][:3],
        "outcome": "proposed",
    }
