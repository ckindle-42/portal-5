"""Model addressing: raw engine tags → pipeline workspace ids, and back.

Why this exists: the pipeline's ``/v1/chat/completions`` treats the ``model``
field as a workspace/persona id, NOT a literal model selector — an
unrecognized value silently falls back to the routing group's first model
rather than erroring. Every model a caller wants to address through the
pipeline therefore needs a workspace entry in ``config/portal.yaml`` whose
``model_hint`` matches the tag. This module is the single authority for that
mapping (P5-FANOUT-001 W2); `portal.modules.security.core._data` delegates
here so the security benches and the compliance transport resolve identically
instead of each carrying a private copy that drifts.

It also exposes the workspace's declared ``context_limit``: through the
pipeline the context window is a SEAT property — the workspace declares it and
the operator bakes the same number into the model tag via
``./launch.sh apply-model-params`` (the pipeline warns on the mismatch at
startup, ``lifespan.py``). The compliance transport uses it to size a reading
window from the seat it will actually hit instead of a module constant.

Host-side and in-container both work: the path derives from this file's
location, which sits the same number of levels under the repo root (host) and
under ``/app`` (pipeline image).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

__all__ = [
    "alias_targets_for_model",
    "is_addressable",
    "workspace_context_limit",
    "workspace_id_for_model",
    "workspace_model_hint",
    "workspaces",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PORTAL_YAML = _REPO_ROOT / "config" / "portal.yaml"
_BACKENDS_YAML = _REPO_ROOT / "config" / "backends.yaml"

_LOCK = threading.Lock()
_BY_HINT: dict[str, str] = {}
_BY_WORKSPACE: dict[str, dict[str, Any]] = {}
_BY_ALIAS: dict[str, set[str]] = {}


def _load() -> None:
    if _BY_WORKSPACE:
        return
    with _LOCK:
        if _BY_WORKSPACE:
            return
        try:
            import yaml  # noqa: PLC0415

            data = yaml.safe_load(_PORTAL_YAML.read_text()) or {}
        except Exception:  # noqa: BLE001 - an unreadable registry addresses nothing
            data = {}
        top_level = data.get("workspaces") or {}
        for ws_id, ws_cfg in top_level.items():
            hint = (ws_cfg or {}).get("model_hint")
            if hint:
                # First workspace wins per hint — same rule the security
                # resolver always applied.
                _BY_HINT.setdefault(str(hint), ws_id)
            _BY_WORKSPACE[ws_id] = ws_cfg or {}
        # TASK_AUTO_COUNCIL_PIPELINE_REVISIT_V1 P1: this used to stop at
        # top-level workspace ids only. A role-scoped seat declared under a
        # base workspace's `variants:` (e.g. security's
        # auto-security::blueteam-council, auto-security::bully-handoff-
        # drafter) is a real, independently routable workspace — the
        # pipeline's own catalog (router/workspaces.py::get_workspace_dict)
        # flattens it to the synthetic id `f"{base}::{variant_id}"` and
        # serves it — but this module never indexed it, so a caller
        # addressing a variant by that synthetic id, or by its model_hint,
        # silently fell through to "unaddressable" even when the pipeline
        # could serve it correctly. Index every variant the same way as its
        # base, in a SEPARATE second pass: a top-level workspace's own
        # model_hint must keep first-match priority over any variant's
        # (e.g. tools-specialist's granite4.1:8b-ctx8k over
        # auto-security::blueteam's identical hint) — existing callers rely
        # on that precedence, so this only fills gaps, never reorders it.
        for ws_id, ws_cfg in top_level.items():
            for variant_id, variant_cfg in ((ws_cfg or {}).get("variants") or {}).items():
                synthetic_id = f"{ws_id}::{variant_id}"
                variant_hint = (variant_cfg or {}).get("model_hint")
                if variant_hint:
                    _BY_HINT.setdefault(str(variant_hint), synthetic_id)
                _BY_WORKSPACE[synthetic_id] = variant_cfg or {}
        try:
            import yaml  # noqa: PLC0415

            be = yaml.safe_load(_BACKENDS_YAML.read_text()) or {}
        except Exception:  # noqa: BLE001 - an unreadable alias map guards nothing
            be = {}
        for backend in be.get("backends") or []:
            for hint, target in ((backend or {}).get("aliases") or {}).items():
                _BY_ALIAS.setdefault(str(hint), set()).add(str(target))


def workspaces() -> dict[str, dict[str, Any]]:
    """Every workspace config keyed by id. Loading is cached, thread-safe."""
    _load()
    return dict(_BY_WORKSPACE)


def workspace_id_for_model(model: str) -> str:
    """The workspace whose ``model_hint`` is ``model``, else ``model`` itself.

    Already-workspace ids (and unrecognized tags, which the pipeline's own
    silent-fallback behavior will surface through the substitution guard)
    pass through unchanged.
    """
    _load()
    return _BY_HINT.get(model, model)


def workspace_model_hint(workspace_id: str) -> str | None:
    """The ``model_hint`` registered for ``workspace_id``, or None."""
    _load()
    cfg = _BY_WORKSPACE.get(workspace_id) or {}
    hint = cfg.get("model_hint")
    return str(hint) if hint else None


def workspace_context_limit(workspace_id: str) -> int:
    """The workspace's declared context window in tokens, 0 when undeclared.

    This is the DECLARED value. That it is actually served is the operator's
    bake (`apply-model-params`) plus the pipeline's startup warning — this
    module reports, it does not verify.
    """
    _load()
    cfg = _BY_WORKSPACE.get(workspace_id) or {}
    limit = cfg.get("context_limit")
    return int(limit) if limit else 0


def alias_targets_for_model(model_hint: str) -> set[str]:
    """Every engine-native id some backend aliases ``model_hint`` onto.

    The substitution guard's acceptable set is NOT just the hint: a
    priority-10 shadow alias legitimately serves the alias target (an oMLX
    conversion id, not the GGUF tag the workspace names), and a guard that
    only knew the hint would reject every correctly-routed aliased call.
    """
    _load()
    return set(_BY_ALIAS.get(model_hint, ()))


def is_addressable(model: str) -> bool:
    """Whether the pipeline can serve ``model`` without silent substitution.

    True when it IS a workspace id (``base::variant`` ids count via their
    base), or the model_hint of one. Anything else would fall through the
    pipeline's routing to the group's first model — the exact failure
    ``resolve_workspace`` exists to prevent — so a caller that refuses to
    send unaddressable names turns a silent substitution into a named error.
    """
    _load()
    if model in _BY_WORKSPACE:
        return True
    base = model.split("::", 1)[0]
    if base in _BY_WORKSPACE:
        return True
    return model in _BY_HINT
