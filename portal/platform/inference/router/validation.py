"""Pre-flight validation and per-backend option injection.

Pure functions — no module-level state. Imported by lifespan (validation) and
by the non-streaming + streaming dispatch paths (option injection).
"""

from __future__ import annotations

import os

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.router.workspaces import WORKSPACES

# Env-overridable Ollama request defaults
_OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE_REQUEST", "-1")
_OLLAMA_NUM_BATCH: int = int(os.environ.get("OLLAMA_NUM_BATCH", "2048"))

# Mutable reference set by lifespan
registry: BackendRegistry | None = None


def _validate_workspace_hints(registry: BackendRegistry) -> list[str]:
    """Verify every ``WORKSPACES`` ``model_hint`` resolves.

    Each workspace's ``model_hint`` must be in some backend's ``models`` list
    AND that backend must be in one of the workspace's routing groups per
    ``config/backends.yaml``. Returns failures rather than raising — ``lifespan``
    decides to raise (``STRICT_HINT_VALIDATION=true``) or log-and-continue,
    and the operator sees every misconfigured workspace in one pass.

    Args:
        registry: The pipeline's ``BackendRegistry``, already loaded from YAML.

    Returns:
        Human-readable error strings, one per failed hint; empty = all resolve.
    """
    group_models: dict[str, set[str]] = {}
    for be in registry.list_backends():
        group_models.setdefault(be.group, set()).update(be.models)

    errors: list[str] = []
    for ws_id, ws_cfg in WORKSPACES.items():
        groups = registry.workspace_routes.get(ws_id, [])
        ollama_available: set[str] = set()
        for g in groups:
            ollama_available |= group_models.get(g, set())

        hint = ws_cfg.get("model_hint")
        if not hint:
            continue
        available = ollama_available
        if hint not in available:
            errors.append(
                f"workspace={ws_id!r} model_hint={hint!r} "
                f"not in any backend's models for groups={groups}. "
                f"Add it to config/backends.yaml or correct the WORKSPACES hint."
            )
    return errors


def _model_supports_tools(model_id: str) -> bool:
    """Return whether ``model_id`` declares ``supports_tools: true``.

    Delegates to ``BackendRegistry.model_supports_tools`` (O(1) against the
    pre-built tool-support map).

    Args:
        model_id: Concrete model id (e.g. ``"qwen3-coder:30b"``). Unknown
            models return ``False``.

    Returns:
        ``True`` if the model's metadata declares ``supports_tools: true``.
    """
    if registry is None or not model_id:
        return False
    return registry.model_supports_tools(model_id)


def _inject_ollama_options(body: dict, workspace_id: str = "") -> dict:
    """Add Ollama-specific tuning to the outgoing request body. Returns a copy.

    Only called for ``type == "ollama"`` backends — vLLM doesn't recognise
    these fields. Body is copied at entry; the ``options`` sub-dict is
    deep-copied so injections never pollute the caller's dict.

    Global tuning: ``keep_alive`` (-1 keeps the model in VRAM; workspace
    override wins via hard assignment), ``num_batch`` (2048 prefill speedup).

    ``num_ctx`` here is belt-and-suspenders, not load-bearing: verified live
    (2026-08-05, Ollama 0.32.5) that a runtime ``options.num_ctx`` sent to
    ``/v1/chat/completions`` is silently ignored — the model loads at its full
    trained context regardless. The mechanism that actually works is a
    Modelfile-baked ``PARAMETER num_ctx`` on a dedicated ``-ctxNk`` tagged
    model (see the many such tags in ``config/backends.yaml``); every
    workspace's ``model_hint`` MUST point at one of those tags if
    ``context_limit`` is meant to take effect, not a bare model id.

    Workspace-driven, all via ``setdefault`` so caller values win:
    ``num_ctx`` from ``context_limit``, top-level ``max_tokens`` from
    ``predict_limit``, sampling keys (``temperature``, ``top_p``, ``top_k``,
    ``min_p``, ``repeat_penalty``, ``seed``), ``mirostat``/``mirostat_tau``/
    ``mirostat_eta`` (mutually exclusive with top_p/top_k; injected only when
    the workspace opts in), and ``think``.

    Args:
        body: Outgoing request body. Not mutated.
        workspace_id: Workspace key used for per-workspace field lookup.

    Returns:
        Shallow copy of ``body`` with injections applied.
    """
    body = dict(body)
    body["options"] = dict(body.get("options") or {})
    ws_cfg_local = WORKSPACES.get(workspace_id, {}) if workspace_id else {}

    # context cap
    ctx_limit = ws_cfg_local.get("context_limit")
    if ctx_limit:
        body["options"].setdefault("num_ctx", ctx_limit)

    # output token cap — map to top-level max_tokens (OpenAI standard)
    predict_limit = ws_cfg_local.get("predict_limit")
    if predict_limit:
        body.setdefault("max_tokens", predict_limit)

    # keep_alive: workspace override wins; hard assignment (not setdefault) so
    # bench workspace lifecycle takes precedence over OWUI's own value.
    ws_keep_alive = ws_cfg_local.get("keep_alive")
    if ws_keep_alive is not None:
        body["keep_alive"] = ws_keep_alive
    else:
        body.setdefault("keep_alive", _OLLAMA_KEEP_ALIVE)

    # global prefill speedup
    body["options"].setdefault("num_batch", _OLLAMA_NUM_BATCH)

    # usage stats for TPS recording
    if body.get("stream", True):
        body.setdefault("stream_options", {})["include_usage"] = True

    # ── Per-workspace sampling tuning ────────────────────────────────────────
    # All use setdefault — OWUI/user values always take precedence.
    sampling_keys = (
        "temperature",  # creativity vs determinism
        "top_p",  # nucleus sampling cutoff
        "top_k",  # vocabulary candidate pool size
        "min_p",  # minimum token probability floor
        "repeat_penalty",  # n-gram repetition penalty
        "seed",  # RNG seed (bench reproducibility)
    )
    for key in sampling_keys:
        val = ws_cfg_local.get(key)
        if val is not None:
            body["options"].setdefault(key, val)

    # mirostat (perplexity-based adaptive sampling) — mutually exclusive with
    # top_p/top_k; only inject when workspace explicitly opts in
    mirostat = ws_cfg_local.get("mirostat")
    if mirostat is not None:
        body["options"].setdefault("mirostat", mirostat)
        for mk in ("mirostat_tau", "mirostat_eta"):
            mv = ws_cfg_local.get(mk)
            if mv is not None:
                body["options"].setdefault(mk, mv)

    # extended thinking toggle (Qwen3/DeepSeek)
    ws_think = ws_cfg_local.get("think")
    if ws_think is not None:
        body.setdefault("think", ws_think)

    return body


def _inject_omlx_options(body: dict, workspace_id: str = "") -> dict:
    """Per-request injection for ``type == "omlx"`` backends.

    oMLX speaks plain OpenAI — no ``options`` sub-dict, no ``keep_alive``
    (residency is server-side: EnginePool pinning/TTL), no ``num_ctx``/
    ``num_batch``. Injects ``max_tokens`` from ``predict_limit``,
    ``stream_options.include_usage`` for TPS accounting, and top-level
    ``temperature``/``top_p`` when declared (caller values win via setdefault).
    Body is copied at entry.
    """
    body = dict(body)
    ws_cfg_local = WORKSPACES.get(workspace_id, {}) if workspace_id else {}

    predict_limit = ws_cfg_local.get("predict_limit")
    if predict_limit:
        body.setdefault("max_tokens", predict_limit)

    if body.get("stream", True):
        body.setdefault("stream_options", {})["include_usage"] = True

    for key in ("temperature", "top_p"):
        val = ws_cfg_local.get(key)
        if val is not None:
            body.setdefault(key, val)

    return body
