"""Goal-driven decide turn (security).

The grounded decide-turn now lives in portal.platform.agent.decide
(TASK_AGENT_LOOP_PLATFORM_V1). This module supplies security's grounding: a
CapabilityProvider wrapping capability.query, and the (quality-only) model turn
that renders security capabilities and calls the pipeline (workspace) or,
for a raw candidate not wired into any workspace, oMLX/Ollama directly
(model + engine). Public signature: decide_next_action(goal, observations,
history, *, workspace=None, model=None, engine="pipeline").
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from portal.platform.agent.decide import decide_next_action as _platform_decide

from .capability.index import Capability, query
from .exec_chain import OLLAMA_URL, OMLX_URL
from .goal import EngagementGoal


class _SecurityCapabilityProvider:
    """Adapts security's capability.query to the platform CapabilityProvider."""

    def __init__(self, *, live_dispatchable_only: bool = False):
        self._live_dispatchable_only = live_dispatchable_only

    def query(
        self,
        observations: dict[str, Any],
        *,
        domain: str | None = None,
        goal: str | None = None,
        limit: int = 8,
    ) -> list[Capability]:
        if goal is not None:
            return query(
                observations,
                domain=domain,
                goal=goal,
                limit=limit,
                live_dispatchable_only=self._live_dispatchable_only,
            )
        return query(
            observations,
            domain=domain,
            limit=limit,
            live_dispatchable_only=self._live_dispatchable_only,
        )


def _call_model_direct(engine: str, model: str, prompt: str) -> str | None:
    """One-shot, non-streaming JSON-mode call straight against oMLX or Ollama's
    OpenAI-compatible endpoint — for a raw candidate model that isn't wired
    into any workspace, bypassing the pipeline entirely. Best-effort: any
    failure returns None so the caller falls back to the deterministic ranker.
    """
    base = OMLX_URL if engine == "omlx" else OLLAMA_URL
    try:
        resp = httpx.post(
            f"{base}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "stream": False,
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        resp.raise_for_status()
        msg = (resp.json().get("choices") or [{}])[0].get("message", {})
        return msg.get("content") or None
    except Exception:
        return None


def _parse_model_decision(raw_text: str, candidates: list[Capability]) -> dict[str, Any] | None:
    """Parse the model's JSON decision into the platform's decision shape.

    Kept honest, not lenient: an invalid/hallucinated capability_id is
    recorded as-is (confidence 0.0, no matched oracle) rather than silently
    swapped for a valid one — that mismatch is itself real signal about the
    model's grounding, and goal_eval.py's coverage/grounding checks depend on
    seeing the model's actual pick, not a laundered one. Only a genuine parse
    failure (no JSON object at all) returns None to fall back.
    """
    try:
        parsed = json.loads(raw_text)
    except Exception:
        m = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not m:
            return None
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            return None

    if not isinstance(parsed, dict):
        return None
    cap_id = parsed.get("capability_id")
    if not isinstance(cap_id, str) or not cap_id:
        return None

    matched = next((c for c in candidates if c.id == cap_id), None)
    return {
        "action": cap_id,
        "tool": parsed.get("tool") or (matched.tools[0] if matched and matched.tools else ""),
        "args": {},
        "reason": parsed.get("reasoning", ""),
        "confidence": 1.0 if matched else 0.0,
        "expected_oracle": getattr(matched, "oracle", None) if matched else None,
        "expected_observation_delta": {"technique_attempted": cap_id},
        "alternatives_considered": [c.id for c in candidates if c.id != cap_id][:3],
        "outcome": "proposed",
    }


def _decide_via_model(
    goal: EngagementGoal,
    observations: dict[str, Any],
    history: list[dict[str, Any]],
    candidates: list[Capability],
    workspace: str | None,
    *,
    model: str | None = None,
    engine: str = "pipeline",
) -> dict[str, Any] | None:
    """Best-effort model decide turn. Any failure returns None so the caller
    falls back to the deterministic ranker — never load-bearing for correctness.
    """
    try:
        from .capability.render import render_capabilities, render_tool_arsenal

        rendered = render_capabilities(candidates)
        arsenal = render_tool_arsenal(phase=candidates[0].phase)
        valid_ids = ", ".join(c.id for c in candidates)
        prompt = (
            f"Goal: {goal.intent} (role={goal.role})\n"
            f"Observations so far: {observations}\n"
            f"History: {len(history)} prior step(s)\n\n"
            f"Candidate capabilities:\n{rendered}\n\n"
            f"Available tools:\n{arsenal}\n\n"
            "Choose exactly ONE next action from the candidates above. Respond "
            "with ONLY a JSON object of this exact shape, no other text: "
            '{"capability_id": "<one of: '
            f"{valid_ids}"
            '>", "tool": "<tool name>", "reasoning": "<your reasoning>"}'
        )

        if engine == "pipeline":
            if workspace is None:
                return None
            from . import call_pipeline  # local import: optional/live dependency

            raw_text, _elapsed = call_pipeline(workspace, prompt)
            if not raw_text:
                return None
            # Unchanged from before TASK_RBP_OMLX_ENGINE_V1: across the FULL
            # live fleet (dozens of workspaces/templates, no response_format
            # enforcement on this path) loose parsing is not shape-stable
            # enough to trust — fall back rather than risk it. The direct-
            # engine branch below is the one that actually parses, because it
            # forces JSON mode server-side and is scoped to specific
            # candidates evaluated deliberately, not the whole fleet.
            return None

        if model is None:
            return None
        raw_text = _call_model_direct(engine, model, prompt)
        if not raw_text:
            return None
        return _parse_model_decision(raw_text, candidates)
    except Exception:
        return None


def decide_next_action(
    goal: EngagementGoal,
    observations: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    workspace: str | None = None,
    model: str | None = None,
    engine: str = "pipeline",
) -> dict[str, Any]:
    """One decide step, grounded in security's capability index. Delegates the
    control flow to the platform decide-turn; supplies the security provider
    and (when a workspace or a raw model+engine is available) the security
    model turn.
    """
    model_turn = None
    if workspace is not None or model is not None:
        model_turn = lambda g, o, h, c: _decide_via_model(  # noqa: E731
            g, o, h, c, workspace, model=model, engine=engine
        )

    return _platform_decide(
        goal,
        observations,
        history,
        provider=_SecurityCapabilityProvider(),
        model_turn=model_turn,
    )
