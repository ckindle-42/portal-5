"""The conversation never reads on truncated material — it routes instead.

The sweep has :func:`portal.modules.compliance.core.sweep.window_fit`; until
now the conversation did not. ``compliance_context(mode=material)`` returned
the whole reading material unbudgeted, and Ollama truncates an oversized prompt
SILENTLY — measured in LOAD_AND_CONVERSE, CIP-003-8 R1 answered from its last
Part alone while 65 operator sections were sent, and said "no operator
sections". A five-turn session is exactly where accumulated material crosses
the window, so the conversational material is priced BEFORE it is returned,
against the seat the conversation actually runs on.

**The pricing constant is measured, not carried.** Five graded probes of real
reading material against this seat (gemma4 26b ctx32k, ollama chat template,
``num_predict=1``) measured a median of 3.28 and a MINIMUM of 3.17 bytes per
token (module_complete p0_5/seat_bytes_per_token.json). The guard prices at
the measured MINIMUM: bytes-per-token below the true ratio would under-count
tokens, and under-counting is the one direction a truncation guard may never
err. The sweep keeps its own 3.3, measured on mapping-call prompts.

**Routing, not clipping.** An oversize requirement-level material is refused
as one message and replaced by the PART-level refs the requirement is made of,
each priced, so the conversation can read what fits and say what doesn't.
Nothing is omitted from a returned material; nothing is silently shortened.
"""

from __future__ import annotations

import re
from typing import Any

#: Measured minimum bytes per token on the conversational seat — see module
#: docstring. Over-counts tokens relative to the 3.28 median: the safe side.
CONVERSATION_BYTES_PER_TOKEN = 3.17

#: Room left for the answer and the chat template on top of the material.
ANSWER_RESERVE_TOKENS = 4_096

_CTX_RE = re.compile(r"-ctx(\d+)k$")

_DEFAULT_WINDOW = 32_768


def seat_window(seat: str) -> int:
    """The window baked into the seat tag (``...-ctx32k`` → 32768).

    A tag with no ``-ctxNk`` suffix reads as UNKNOWN and the caller must treat
    it as NOT FITTING — an unmeasurable window is not a safe one (the sweep's
    own rule).
    """
    match = _CTX_RE.search(seat)
    return int(match.group(1)) * 1024 if match else 0


def fit_material(payload: dict[str, Any], seat: str) -> dict[str, Any]:
    """Price one rendered material against the conversational seat's window."""
    from portal.modules.compliance.core.sweep import window_fit

    window = seat_window(seat)
    text = str(payload.get("text") or "")
    fitted = window_fit(
        len(text.encode()),
        window,
        ANSWER_RESERVE_TOKENS,
        bytes_per_token=CONVERSATION_BYTES_PER_TOKEN,
    )
    fitted.update({"seat": seat, "window_known": bool(window), "material_chars": len(text)})
    if not window:
        fitted["fits"] = False
        fitted["why"] = f"seat tag {seat!r} declares no -ctxNk window; refusing to price blind"
    return fitted


def route(repo: Any, ref: str, seat: str) -> dict[str, Any]:
    """Where a conversation should look instead: the Part-level refs this
    requirement is made of, each priced against the same window."""
    from portal.modules.compliance.core.requirement_scope import resolve

    scope = resolve(repo, ref)
    rows: list[dict[str, Any]] = []
    for identity in scope.refs[1:] or [scope.ref]:
        from portal.modules.compliance.core import reading_material

        payload = reading_material.render(repo, identity, citation="quote")
        if "error" in payload:
            rows.append({"ref": identity, "error": str(payload["error"])})
            continue
        fitted = fit_material(payload, seat)
        rows.append(
            {
                "ref": identity,
                "bytes": fitted["prompt_bytes"],
                "estimated_tokens": fitted["estimated_tokens"],
                "fits": fitted["fits"],
            }
        )
    return rows
