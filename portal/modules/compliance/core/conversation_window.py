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

**The window is the engine's, not the tag's (P6 A5).** The seat tag's baked
``-ctxNk`` is an instruction to an adapter, and it went stale: the workspace
declares 32,768 while the serving engine reports 262,144 — so the guard was
routing away whole-requirement material the served window holds (the Q1b M8
finding). Before pricing, the guard asks the engine that serves the workspace
what window IT applies (:meth:`BackendRegistry.get_backend_for_workspace`, the
router's own resolution, then the engine's model metadata), and prices against
that. A tag window is the fallback of record when the engine cannot be read —
over-counting is the safe direction; under-counting is not.

**Routing, not clipping.** An oversize requirement-level material is refused
as one message and replaced by the PART-level refs the requirement is made of,
each priced, so the conversation can read what fits and say what doesn't.
Nothing is omitted from a returned material; nothing is silently shortened.
"""

from __future__ import annotations

import re
import time
from typing import Any

#: Measured minimum bytes per token on the conversational seat — see module
#: docstring. Over-counts tokens relative to the 3.28 median: the safe side.
CONVERSATION_BYTES_PER_TOKEN = 3.17

#: Room left for the answer and the chat template on top of the material.
ANSWER_RESERVE_TOKENS = 4_096

#: How long a read serving window stays trusted. An engine reload can change
#: the applied window; ten minutes bounds how stale the guard's fact can be
#: without putting an HTTP probe on every tool call.
_SERVED_WINDOW_TTL_S = 600.0

_CTX_RE = re.compile(r"-ctx(\d+)k$")

_served_window_cache: dict[str, tuple[float, int, str]] = {}


def seat_window(seat: str) -> int:
    """The window baked into the seat tag (``...-ctx32k`` → 32768).

    A tag with no ``-ctxNk`` suffix reads as UNKNOWN and the caller must treat
    it as NOT FITTING — an unmeasurable window is not a safe one (the sweep's
    own rule).
    """
    match = _CTX_RE.search(seat)
    return int(match.group(1)) * 1024 if match else 0


def _engine_window(backend: Any, model: str) -> int:
    """The window the serving engine itself reports for ``model`` — 0 when it
    will not say. Same metadata fields ``scripts.compliance.truth.served_turn``
    reads, through the backend the router would route to. The backend URL is
    used as configured: this read runs where the pipeline runs, and
    ``host.docker.internal`` is exactly how the container reaches the engines
    (a host-side script, which cannot resolve that name, is the one that
    rewrites it)."""
    import httpx

    from portal.platform.inference.omlx_auth import omlx_headers

    url = backend.url.rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as session:
            if backend.type == "ollama":
                response = session.get(f"{url}/api/ps", timeout=5.0)
                response.raise_for_status()
                entry = next(
                    (
                        m
                        for m in response.json().get("models", [])
                        if model in (m.get("name"), m.get("model"))
                    ),
                    {},
                )
                return int(entry.get("context_length") or 0)
            headers = omlx_headers() if backend.type == "omlx" else {}
            response = session.get(f"{url}/v1/models", headers=headers, timeout=5.0)
            response.raise_for_status()
            entry = next((m for m in response.json().get("data", []) if m.get("id") == model), {})
            for key in ("max_model_len", "max_context", "context_length", "n_ctx"):
                value = entry.get(key)
                if isinstance(value, int) and value > 0:
                    return value
    except Exception:  # noqa: BLE001 - an unreadable engine leaves the tag in charge
        return 0
    return 0


def served_window(seat: str) -> tuple[int, str]:
    """``(window, source)`` — the serving engine's own window for the model the
    router resolves this seat to, or ``(0, "")`` when unknown.

    Cached per seat for :data:`_SERVED_WINDOW_TTL_S`: the read costs one HTTP
    round trip and the applied window does not change inside a pipeline run.
    """
    cached = _served_window_cache.get(seat)
    if cached and time.monotonic() - cached[0] < _SERVED_WINDOW_TTL_S:
        return cached[1], cached[2]
    window, source = 0, ""
    try:
        from portal.platform.inference.cluster_backends import BackendRegistry
        from portal.platform.inference.model_addressing import workspace_model_hint

        # the reading workspace by name: its model_hint is shared with
        # compliance-mapping, and workspace_id_for_model resolves a shared hint
        # to the FIRST workspace that declares it
        hint = workspace_model_hint("compliance-reading") or seat
        backend = BackendRegistry().get_backend_for_workspace("compliance-reading")
        if backend is not None:
            model = backend.resolve_model(hint) or hint
            window = _engine_window(backend, model)
            if window:
                source = f"serving engine {backend.id} reporting {model}"
    except Exception:  # noqa: BLE001 - unknown is recorded, never guessed
        window, source = 0, ""
    _served_window_cache[seat] = (time.monotonic(), window, source)
    return window, source


def fit_material(payload: dict[str, Any], seat: str) -> dict[str, Any]:
    """Price one rendered material against the window the conversation runs on.

    The serving engine's window when it can be read, the seat tag's baked
    window as the fallback of record (never a guess in the other direction):
    pricing against a LARGER window than the engine applies would let an
    oversized payload through to a silent truncation, so an unreadable engine
    must fall to the tag, not to optimism.
    """
    from portal.modules.compliance.core.sweep import window_fit

    tag_window = seat_window(seat)
    served, source = served_window(seat)
    window = served or tag_window
    text = str(payload.get("text") or "")
    fitted = window_fit(
        len(text.encode()),
        window,
        ANSWER_RESERVE_TOKENS,
        bytes_per_token=CONVERSATION_BYTES_PER_TOKEN,
    )
    fitted.update(
        {
            "seat": seat,
            "window_known": bool(window),
            "material_chars": len(text),
            "window_source": source or ("seat tag" if tag_window else "unknown"),
            "seat_tag_window": tag_window or None,
            "served_window": served or None,
        }
    )
    if not window:
        fitted["fits"] = False
        fitted["why"] = (
            f"seat tag {seat!r} declares no -ctxNk window and no serving engine "
            "reported one; refusing to price blind"
        )
    return fitted


def route(repo: Any, ref: str, seat: str) -> list[dict[str, Any]]:
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
