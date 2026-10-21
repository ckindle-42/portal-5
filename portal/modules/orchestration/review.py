"""Deep-seat review and configurable vote aggregation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .contracts import Bite
from .worker import Engine, PipelineError, QueueYieldError, _response_parts


@dataclass(frozen=True)
class ReviewResult:
    passed: bool
    approvals: int
    required: int
    votes: tuple[dict[str, str], ...]


def is_high_risk(bite: Bite, discipline: dict[str, Any], policy: dict[str, Any]) -> bool:
    """Apply configured risk labels, tools and write scopes to one bite."""
    criteria = policy.get("high_risk")
    if not isinstance(criteria, dict):
        raise ValueError("review.high_risk must be a mapping")
    risk_levels = _strings(criteria, "risk_levels")
    risky_tools = _strings(criteria, "tools")
    risky_scopes = _strings(criteria, "write_scopes")
    return (
        bite.risk in risk_levels
        or bool(set(bite.tools) & risky_tools)
        or str(discipline.get("write_scope", "")) in risky_scopes
    )


def review_output(
    engine: Engine,
    bite: Bite,
    output: Any,
    *,
    vote_count: int,
    minimum_approve_votes: int,
    require_idle: bool = False,
    gate: Callable[[], bool] | None = None,
) -> ReviewResult:
    """Ask Deep for independent JSON votes and require the configured quorum."""
    if vote_count < 1 or not 1 <= minimum_approve_votes <= vote_count:
        raise ValueError("Deep review vote configuration is invalid")
    votes = []
    for _ in range(vote_count):
        if gate is not None and not gate():
            raise QueueYieldError("the queue gate closed before a Deep review vote")
        _admit_review_seat(engine, require_idle)
        body = {
            "model": engine.model_tag,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Review one completed task bite against its goal and stated review reason. "
                        "Return only JSON with decision='approve' or 'reject' and a concise reason. "
                        "Keep reasoning enabled."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "bite_id": bite.bite_id,
                            "goal": bite.goal,
                            "procedure": bite.procedure,
                            "review_reason": bite.review_reason,
                            "acceptance_checks": list(bite.accept),
                            "output": output,
                        },
                        sort_keys=True,
                        default=str,
                    ),
                },
            ],
            "max_tokens": 512,
            "temperature": 0,
            "stream": True,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": True},
        }
        response = engine.chat(body, 300, lambda _event: None)
        content, _ = _response_parts(response)
        votes.append(_parse_vote(content))
    approvals = sum(vote["decision"] == "approve" for vote in votes)
    return ReviewResult(
        approvals >= minimum_approve_votes,
        approvals,
        minimum_approve_votes,
        tuple(votes),
    )


def _admit_review_seat(engine: Engine, require_idle: bool) -> None:
    """Ask the load guard for the review seat; a gated review waits instead of losing an attempt."""
    try:
        plan = engine.load_plan(300)
    except PipelineError as exc:
        if not require_idle:
            raise
        raise QueueYieldError(str(exc)) from exc
    if require_idle and (plan.get("busy") is not False or plan.get("fits") is not True):
        raise QueueYieldError(f"Pipeline load-plan is busy or cannot admit the review seat: {plan}")


def _parse_vote(content: str) -> dict[str, str]:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        return {"decision": "reject", "reason": "review response was not JSON"}
    if not isinstance(raw, dict) or raw.get("decision") not in {"approve", "reject"}:
        return {"decision": "reject", "reason": "review response had an invalid decision"}
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return {"decision": "reject", "reason": "review response omitted its reason"}
    return {"decision": raw["decision"], "reason": reason.strip()}


def _strings(raw: dict[str, Any], key: str) -> set[str]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"review.high_risk.{key} must be a list of strings")
    return set(value)
