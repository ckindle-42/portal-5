"""An interactive turn refused for memory gets a lighter declared seat, not a dead end.

When every candidate refused a chat-UI turn for host memory (HTTP 507 / capacity),
the workspace's own declared variants are the seats it already sanctions: try the
ones that fit right now, in declaration order, and prepend a visible note naming
the seat that answered. A variant only substitutes from a group the workspace's
own routing declares — a stranger group's backend is another workspace's chain,
not this seat's fallback. A ``::model=`` pin, a chain or a council is an explicit
multi-model or single-model contract — those are never substituted, and the
no-answer notice (``no_answer``) remains the last resort for every audience.
API clients keep their real error status; this path is chat-UI only.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.responses import JSONResponse

from portal.platform.inference.router import no_answer
from portal.platform.inference.router.metrics import _capacity_fallback_total
from portal.platform.inference.router.trace import note as trace_note
from portal.platform.inference.router.trace import span as trace_span
from portal.platform.inference.router.workspaces import WORKSPACES

logger = logging.getLogger(__name__)


def _eligible(workspace_id: str, reasons: list[str]) -> bool:
    """Chat UI, memory refusal, and no explicit model pin or multi-model contract."""
    if not no_answer.chat_ui() or no_answer.reason_class(reasons) != "memory_refused":
        return False
    if "::model=" in workspace_id:
        return False
    base = WORKSPACES.get(workspace_id.split("::", 1)[0], {})
    return not base.get("chain") and not base.get("council")


def _variant_names(workspace_id: str) -> list[str]:
    """Declared variants of the base workspace that name a different, stack-up seat."""
    from portal.platform.inference.config import load_portal_config

    base_id, _, current = workspace_id.partition("::")
    spec = load_portal_config().workspaces.get(base_id)
    if spec is None:
        return []
    failed_hint = str(WORKSPACES.get(workspace_id, {}).get("model_hint") or "")
    names = []
    for name, variant in spec.variants.items():
        hint = str(variant.get("model_hint") or "")
        if name == current or not hint or hint == failed_hint or variant.get("stack_down_only"):
            continue
        names.append(name)
    return names


def _register_variant(base_id: str, name: str) -> str | None:
    """Resolve through the router's own variant path (merge, cache, disabled gate)."""
    from portal.platform.inference.router.preinject import _resolve_workspace_variant

    synthetic_id = f"{base_id}::{name}"
    resolved = _resolve_workspace_variant(base_id, base_id, name)
    return resolved if resolved == synthetic_id else None


async def _seat_fits(backend: Any, hint: str) -> bool:
    """Whether this backend's seat fits host memory right now (pure measurement)."""
    from portal.platform.inference import load_guard
    from portal.platform.inference.router import validation

    resolved = backend.resolve_model(hint)
    if resolved is None:
        return False
    registry = validation.registry
    ollama = (
        next((b.url for b in registry.list_backends() if b.type == "ollama"), None)
        if registry
        else None
    )
    if load_guard.GUARD is None or not ollama:
        return True  # unmeasurable: let admission decide
    plan = await load_guard.GUARD.plan(ollama.rstrip("/"), [(backend.type, resolved)])
    return bool(plan.get("fits"))


def _with_note(result: JSONResponse, note: str) -> JSONResponse:
    """Prepend the visible seat-substitution note to the answer content."""
    data = json.loads(bytes(result.body))
    for choice in data.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            message["content"] = [{"type": "text", "text": note}, *content]
        else:
            message["content"] = f"{note}\n\n{content or ''}"
    return JSONResponse(content=data, headers=dict(result.headers))


def _note_fallback_receipt(backend: Any, served: str, synthetic_id: str, name: str) -> None:
    """Name the seat that actually answered. Without this the record has no
    outcome and no backend/model, because the candidate loop that normally
    notes them never succeeded."""
    trace_note(
        backend=backend.id,
        model=served,
        workspace=synthetic_id,
        outcome="ok",
        capacity_fallback=name,
    )
    trace_span(
        "backend.selected",
        backend=backend.id,
        model=served,
        fallback=True,
        capacity_fallback=name,
    )


async def try_capacity_fallback(
    workspace_id: str,
    body: dict[str, Any],
    reasons: list[str],
    *,
    persona: str = "",
    start_time: float | None = None,
    tried: dict[tuple[str, str], str] | None = None,
    max_hops: int = 1,
    dispatch: Any = None,
) -> JSONResponse | None:
    """Answer a memory-refused chat turn from a lighter declared variant that fits.

    Returns the noted completion, or ``None`` when no declared seat fits or serves;
    the caller then delivers the no-answer notice. Never substitutes for a pin, and
    never raises: a fallback failure falls through to the notice. ``dispatch`` is
    the caller's ``_try_non_streaming`` seam (each path's tests patch their own).
    """
    import time

    from portal.platform.inference.router import validation

    if not _eligible(workspace_id, reasons):
        return None
    registry = validation.registry
    if registry is None:
        return None
    if dispatch is None:
        from portal.platform.inference.router.non_streaming import _try_non_streaming as dispatch
    base_id = workspace_id.split("::", 1)[0]
    failed_model = no_answer.workspace_model(workspace_id, body)
    started = time.monotonic() if start_time is None else start_time
    declared = set(registry.declared_groups(base_id))
    for name in _variant_names(workspace_id):
        synthetic_id = _register_variant(base_id, name)
        if synthetic_id is None:
            continue
        hint = str(WORKSPACES[synthetic_id].get("model_hint") or "")
        for backend in registry.get_backend_candidates(synthetic_id):
            if getattr(backend, "group", "") not in declared:
                # A variant served from a group the workspace never routes to is
                # another workspace's chain, not this seat's fallback (2026-11-26:
                # auto-documents' tiny extract variant answered from ollama-creative).
                continue
            try:
                if not await _seat_fits(backend, hint):
                    continue
                result = await dispatch(
                    backend,
                    {**body, "stream": False},
                    synthetic_id,
                    started,
                    enforce_hint=True,
                    persona=persona,
                    tried=tried,
                    max_hops=max_hops,
                )
            except Exception as exc:
                logger.warning("capacity fallback via %s failed: %s", synthetic_id, exc)
                continue
            if result is None:
                continue
            route = str(result.headers.get("x-portal-route", "")).split(";")
            served = route[2] if len(route) > 2 and route[2] else hint
            note = (
                f"⚠️ **`{failed_model}` could not be loaded — host memory is full. "
                f"This answer was produced by `{served}`, the lighter `{synthetic_id}` "
                f"seat of this workspace, instead.**"
            )
            _capacity_fallback_total.labels(workspace=base_id, variant=name).inc()
            logger.warning(
                "workspace=%s: memory refusal answered by declared variant %s (%s)",
                workspace_id,
                synthetic_id,
                served,
            )
            # The receipt a trace consumer reads must name the seat that actually
            # answered: without this the record has no outcome and no backend/model,
            # because the candidate loop that normally notes them never succeeded.
            _note_fallback_receipt(backend, served, synthetic_id, name)
            return _with_note(result, note)
    return None
