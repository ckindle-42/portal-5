"""SecurityRunTrace — shared schema for theory/exec/chain/purple result rows.

All four paths emit rows conforming to this schema.  Additive on top of
existing shapes — consumers can migrate at their own pace.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class SecurityRunTrace(TypedDict, total=False):
    """Unified result schema across all security bench run modes."""

    # Identity
    workspace: str
    prompt_key: str
    run_mode: Literal["theory", "exec", "chain", "purple"]
    model: str  # backend model actually invoked

    # Timing
    duration_s: float
    warmup_ms: NotRequired[float]

    # Call accounting (feeds --no-theory-for-exec tests)
    tool_call_count: int
    _calls: dict[str, int]  # {"theory": 0|1, "exec": 0|1, "chain": 0|1}

    # Evidence
    evidence_refs: list[str]
    correlation_summary: NotRequired[dict[str, str]]  # {technique_id: reason_code}

    # Reason-code lifecycle (purple only)
    reason_code_transitions: NotRequired[list[dict]]


def make_trace(
    workspace: str,
    prompt_key: str,
    run_mode: str,
    model: str,
    duration_s: float,
    _calls: dict[str, int],
    **kwargs,
) -> dict:
    """Build a trace dict conforming to SecurityRunTrace.

    Extra kwargs allowed (schema is additive).
    """
    trace = {
        "workspace": workspace,
        "prompt_key": prompt_key,
        "run_mode": run_mode,
        "model": model,
        "duration_s": duration_s,
        "_calls": _calls,
        "tool_call_count": _calls.get("exec", 0) + _calls.get("chain", 0),
        "evidence_refs": [],
    }
    trace.update(kwargs)
    return trace
