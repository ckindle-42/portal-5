"""JudgeFn factories: grounded single readers and sequential panels with receipts."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import replace
from typing import Any

from portal.platform.inference.config import load_portal_config
from portal.platform.inference.model_addressing import workspace_model_hint

from .contracts import JudgeRecord, ReviewConcern, Verdict
from .intake import IntakeResult
from .judge import ModelClient, prompt_digest, run_judge
from .panel import PanelPolicy, run_panel
from .tools import ToolBox
from .wall import LABEL_IDENTIFIERS, WallViolation

DEFAULT_CONCERN_TIMEOUT_S = 600.0
MAX_EVENTS = 40
MAX_ROUNDS = 3
MAX_TOKENS = 2048
P95_PERCENTILE = 0.95

ToolFactory = Callable[[ReviewConcern, IntakeResult], ToolBox | None]
_LABEL_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    + "|".join(re.escape(item) for item in sorted(LABEL_IDENTIFIERS, key=len, reverse=True))
    + r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def assert_prompt_label_free(text: str) -> None:
    """Reject rendered case text that exposes a scorer label identifier."""
    match = _LABEL_TOKEN.search(text)
    if match:
        raise WallViolation(f"reader prompt contains a label identifier: {match.group(0)}")


def resolve_candidate_models() -> dict[str, str]:
    """Resolve T3's four candidate roles from the current Portal/security config."""
    from ..bully.config import resolve_investigation_models

    roles = resolve_investigation_models()
    portal = load_portal_config()
    deep = workspace_model_hint("general-deep")
    fast = workspace_model_hint("general-fast")
    if not deep:
        deep = getattr(portal.workspaces.get("general-deep"), "model_hint", None)
    if not fast:
        fast = getattr(portal.workspaces.get("general-fast"), "model_hint", None)
    if not deep or not fast:
        raise ValueError("general-deep and general-fast must have configured model hints")
    return {
        "auto_security_reasoning": str(roles["reasoning"]),
        "general_deep": str(deep),
        "general_fast": str(fast),
        "expert_role": str(roles["expert"]),
    }


def _safe_concern(concern: ReviewConcern) -> ReviewConcern:
    """Keep comparison evidence while removing known-item names from the model view."""
    safe = tuple(replace(item, anchor_label="known item") for item in concern.resembles)
    return replace(concern, resembles=safe)


def _verified(client: ModelClient, model: str) -> bool:
    check = getattr(client, "reasoning_verified", None)
    return bool(check(model)) if callable(check) else False


def _calls_since(client: ModelClient, index: int) -> list[Any]:
    calls = getattr(client, "call_receipts", ())
    return list(calls[index:])


def _receipt_index(client: ModelClient) -> int:
    return len(getattr(client, "call_receipts", ()))


def _fallback(model: str, concern: ReviewConcern, window: IntakeResult, why: str) -> JudgeRecord:
    available = sum(1 for item in concern.evidence if item.event_id in window.events)
    return JudgeRecord(
        model=model,
        verdict=Verdict.UNSURE,
        degraded=why,
        evidence_total=available,
        reader_receipt={
            "examined": available,
            "resolved": 0,
            "dropped_claims": 0,
            "latency_ms": 0.0,
            "tokens": None,
            "reasoning_produced": False,
            "prompt_version": "review-judge-v1",
            "prompt_digest": prompt_digest(),
        },
    )


def _attach_receipt(
    record: JudgeRecord,
    client: ModelClient,
    call_start: int,
    toolbox: ToolBox | None,
    *,
    prompt_version: str = "review-judge-v1",
) -> JudgeRecord:
    calls = _calls_since(client, call_start)
    pivots = list(toolbox.receipts) if toolbox is not None else []
    latency = [
        float(call.latency_ms) for call in calls if getattr(call, "latency_ms", None) is not None
    ]
    prompt_tokens = [
        int(call.prompt_tokens)
        for call in calls
        if getattr(call, "prompt_tokens", None) is not None
    ]
    completion_tokens = [
        int(call.completion_tokens)
        for call in calls
        if getattr(call, "completion_tokens", None) is not None
    ]
    receipt = {
        "examined": record.evidence_total + sum(int(item.fetched) for item in pivots),
        "resolved": record.evidence_shown + sum(int(item.shown) for item in pivots),
        "dropped_claims": record.dropped_claims,
        "latency_ms": sum(latency),
        "latency_ms_by_call": latency,
        "prompt_tokens": sum(prompt_tokens) if prompt_tokens else None,
        "completion_tokens": sum(completion_tokens) if completion_tokens else None,
        "reasoning_produced": any(int(getattr(call, "reasoning_chars", 0)) > 0 for call in calls),
        "model_digests": sorted(
            {str(call.model_digest) for call in calls if getattr(call, "model_digest", "")}
        ),
        "backends": sorted({str(call.backend) for call in calls if getattr(call, "backend", "")}),
        "pivot_calls": len(pivots),
        "pivots": [
            {
                "term_sha256": item.term_sha256,
                "partitions_examined": item.partitions_examined,
                "expected": item.expected,
                "fetched": item.fetched,
                "shown": item.shown,
                "complete": item.complete,
                "truncated": item.truncated,
                "degraded": item.degraded,
            }
            for item in pivots
        ],
        "prompt_version": prompt_version,
        "prompt_digest": prompt_digest(),
    }
    return replace(record, reader_receipt=receipt)


def build_judge_fn(
    client: ModelClient,
    model: str,
    *,
    challenger_model: str | None = None,
    toolbox_factory: ToolFactory | None = None,
    max_rounds: int = MAX_ROUNDS,
    max_events: int = MAX_EVENTS,
    max_tokens: int = MAX_TOKENS,
    timeout_s: float = DEFAULT_CONCERN_TIMEOUT_S,
) -> Callable[[ReviewConcern, IntakeResult], JudgeRecord]:
    """Build the pipeline callback; unprobed or non-reasoning models fail closed."""

    def judge(concern: ReviewConcern, window: IntakeResult) -> JudgeRecord:
        if not _verified(client, model):
            return _fallback(model, concern, window, "reasoning probe missing or failed")
        safe = _safe_concern(concern)
        from .judge import render_case  # local import keeps the pure payload transport-free

        case, _registry, _total = render_case(safe, window, max_events=max_events)
        try:
            assert_prompt_label_free(case)
        except WallViolation as exc:
            return _fallback(model, concern, window, f"label guard: {exc}")
        toolbox = toolbox_factory(concern, window) if toolbox_factory else None
        call_start = _receipt_index(client)
        deadline = getattr(client, "concern_deadline", None)
        scope = deadline(timeout_s) if callable(deadline) else nullcontext()
        try:
            with scope:
                record = run_judge(
                    safe,
                    window,
                    client=client,
                    model=model,
                    tools=toolbox,
                    challenger_model=challenger_model,
                    max_rounds=max_rounds,
                    max_events=max_events,
                    max_tokens=max_tokens,
                )
        except Exception as exc:  # deterministic concerns survive reader/runtime errors
            return _fallback(model, concern, window, f"reader unavailable: {type(exc).__name__}")
        return _attach_receipt(record, client, call_start, toolbox)

    return judge


def build_panel_judge_fn(
    client: ModelClient,
    models: Sequence[str],
    *,
    policy: PanelPolicy,
    toolbox_factory: ToolFactory | None = None,
    max_rounds: int = MAX_ROUNDS,
    max_events: int = MAX_EVENTS,
    max_tokens: int = MAX_TOKENS,
    timeout_s: float = DEFAULT_CONCERN_TIMEOUT_S,
) -> Callable[[ReviewConcern, IntakeResult], JudgeRecord]:
    """Build a sequential full-roster panel callback under the pipeline load guard."""
    roster = tuple(models)

    def panel_judge(concern: ReviewConcern, window: IntakeResult) -> JudgeRecord:
        unprobed = [model for model in roster if not _verified(client, model)]
        if not roster or unprobed:
            detail = (
                "empty panel" if not roster else f"reasoning probe missing or failed: {unprobed}"
            )
            return _fallback("panel:" + ",".join(roster), concern, window, detail)
        safe = _safe_concern(concern)
        from .judge import render_case  # local import keeps the pure payload transport-free

        case, _registry, _total = render_case(safe, window, max_events=max_events)
        try:
            assert_prompt_label_free(case)
        except WallViolation as exc:
            return _fallback("panel:" + ",".join(roster), concern, window, f"label guard: {exc}")
        toolbox = toolbox_factory(concern, window) if toolbox_factory else None
        call_start = _receipt_index(client)
        deadline = getattr(client, "concern_deadline", None)
        scope = deadline(timeout_s) if callable(deadline) else nullcontext()
        try:
            with scope:
                record = run_panel(
                    safe,
                    window,
                    members=[(client, model) for model in roster],
                    policy=policy,
                    tools=toolbox,
                    max_rounds=max_rounds,
                    max_events=max_events,
                    max_tokens=max_tokens,
                )
        except Exception as exc:
            return _fallback(
                "panel:" + ",".join(roster),
                concern,
                window,
                f"reader unavailable: {type(exc).__name__}",
            )
        return _attach_receipt(record, client, call_start, toolbox)

    return panel_judge


def p95_latency_ms(call_receipts: Sequence[Any]) -> float | None:
    """Nearest-rank p95 over observed model call latencies; no synthetic samples."""
    values = sorted(
        float(item.latency_ms)
        for item in call_receipts
        if getattr(item, "latency_ms", None) is not None
    )
    if not values:
        return None
    index = math.ceil(P95_PERCENTILE * len(values)) - 1
    return values[index]
