"""Pre-flight validation and per-backend option injection.

Extracted from router_pipe.py during M6-A finish. Pure functions —
no module-level state. Imported by lifespan (validation) and by the
non-streaming + streaming dispatch paths (option injection).
"""

from __future__ import annotations

import os

from portal_pipeline.cluster_backends import BackendRegistry
from portal_pipeline.router.workspaces import WORKSPACES

# Module-level constants from router_pipe.py (now in validation.py)
_OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE_REQUEST", "-1")
_OLLAMA_NUM_BATCH: int = int(os.environ.get("OLLAMA_NUM_BATCH", "2048"))

# Mutable reference set by lifespan
registry: BackendRegistry | None = None


def _validate_workspace_hints(registry: BackendRegistry) -> list[str]:
    """Verify every ``WORKSPACES`` ``model_hint`` resolves.

    Run once at startup from ``lifespan``. For each workspace,
    ``model_hint`` (Ollama) must be in some backend's ``models``
    list, AND that backend must be in one of the workspace's
    routing groups per ``config/backends.yaml``.

    Returns the list of failures rather than raising. The caller
    decides what to do: ``lifespan`` raises ``RuntimeError`` under
    ``STRICT_HINT_VALIDATION=true``, or logs warnings and starts
    anyway in permissive mode. Returning a list lets the operator
    see every misconfigured workspace in one startup pass instead
    of fail-on-first.

    Without this check, a typo in ``WORKSPACES`` produces silent
    fallback at request time — the workspace serves, but with a
    different model than intended.

    Args:
        registry: The pipeline's ``BackendRegistry``, already
            loaded from YAML.

    Returns:
        Human-readable error strings, one per failed hint. Empty
        list means all hints resolve.
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
    """Return whether ``model_id`` declares ``supports_tools: true`` in its metadata.

    Delegates to ``BackendRegistry.model_supports_tools`` for O(1) lookup
    against the pre-built tool-support map built during ``_load_config``.

    Args:
        model_id: Concrete model id (e.g. ``"qwen3-coder:30b"``).
            Unknown models return ``False``.

    Returns:
        ``True`` if the model's metadata explicitly declares
        ``supports_tools: true``, ``False`` otherwise.
    """
    if registry is None or not model_id:
        return False
    return registry.model_supports_tools(model_id)


def _inject_ollama_options(body: dict, workspace_id: str = "") -> dict:
    """Add Ollama-specific tuning to the outgoing request body. Returns a copy.

    Only called for backends with ``type == "ollama"``. vLLM
    does not recognise these fields and would either error or silently
    ignore them.

    Body is copied at function entry — the original is never
    mutated. The ``options`` sub-dict is deep-copied so workspace
    injections never pollute the caller's original options dict.

    **Global tuning** (applies to every Ollama request):

    * ``keep_alive``: ``-1`` keeps model in VRAM, eliminates cold-load cost.
    * ``num_batch``: 2048 — 4× faster prefill vs Ollama default 512.

    **Workspace-driven** (only when workspace declares the field):

    * ``num_ctx`` from ``context_limit`` — explicit KV-cache cap for big models.
    * ``max_tokens`` from ``predict_limit`` — output token cap (CoT exhaustion guard).
    * ``temperature`` — sampling temperature. 0.1 for exec/tool workspaces;
      0.2 for coding; 0.6 for reasoning/research; 0.8 for creative.
    * ``top_p`` — nucleus sampling cutoff. Tighter (0.9) for tool-calling roles;
      wider (0.95) for reasoning and creative roles.
    * ``top_k`` — vocabulary candidate pool. 20 for exec precision; 40 default.
    * ``min_p`` — minimum token probability floor. Filters degenerate low-prob
      tokens that abliterated models can drift toward. 0.05 is safe across fleet.
    * ``repeat_penalty`` — penalises repeated n-grams. 1.1 for exec/tool chains
      that show looping behaviour; 1.0 (default) elsewhere.
    * ``seed`` — RNG seed for reproducibility. Set on bench workspaces only so
      theory/exec scores are comparable across runs without non-determinism noise.
    * ``think`` — extended thinking toggle for Qwen3/similar.

    All injections use ``setdefault`` so caller-supplied values
    (e.g. Open WebUI passing its own ``temperature``) always win.

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

    # keep_alive: workspace override wins; fall back to global "-1"
    # Hard assignment (not setdefault) — OWUI sends its own keep_alive but bench
    # workspace lifecycle must take precedence to avoid pinning large models.
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
