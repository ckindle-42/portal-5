"""Pre-flight validation and per-backend option injection.

Pure functions — no module-level state. Imported by lifespan (validation) and
by the non-streaming + streaming dispatch paths (option injection).
"""

from __future__ import annotations

import os
import re

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


# Model families whose chat template opens a `<think>` block by default when
# `enable_thinking` isn't explicitly set (Qwen3.5/3.6/3.8, DeepSeek-R1, GLM-Z1,
# Magistral, olmo-think). A non-reasoning workspace on one of these that leaves
# `think` unset will silently reason — and on hard prompts that degenerates
# into repetition or eats the whole token budget (empty content). Coder
# variants (qwen3-coder) are instruct-only, not thinking.
_THINKING_FAMILY_RE = re.compile(
    r"qwen3\.[568]|qwen3-?next|deepseek-?r1|glm-z1|glm.*think|magistral|olmo.*think|"
    r"phi4-reasoning|qwopus|aeon",
    re.IGNORECASE,
)
_CODER_HINT_RE = re.compile(r"qwen3-coder|coder-next", re.IGNORECASE)


def warn_unset_thinking_mode() -> list[str]:
    """Workspaces on a thinking-capable model that don't set ``think``.

    Advisory only — returns human-readable strings for ``lifespan`` to log at
    WARNING. Not a hard failure: the template default may be what the operator
    wants. See feedback_thinking_model_needs_think_false.
    """
    out: list[str] = []

    def _scan(ws_id: str, cfg: dict) -> None:
        hint = cfg.get("model_hint") or ""
        if (
            hint
            and _THINKING_FAMILY_RE.search(hint)
            and not _CODER_HINT_RE.search(hint)
            and cfg.get("think") is None
        ):
            out.append(
                f"workspace={ws_id!r} model_hint={hint!r} is a thinking-capable "
                f"model but `think` is unset — it will default to the template's "
                f"behavior (usually ON for Qwen3). Set `think: true|false` explicitly."
            )
        for vn, vcfg in (cfg.get("variants") or {}).items():
            merged = {**cfg, **vcfg}
            merged.pop("variants", None)  # a variant has no nested variants
            _scan(f"{ws_id}::{vn}", merged)

    for ws_id, cfg in WORKSPACES.items():
        _scan(ws_id, cfg)
    return out


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


_SAMPLING_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
    "presence_penalty",
    "seed",
)


def _resolve_sampling_values(ws_cfg_local: dict) -> dict:
    """think_profiles wins over flat sampling fields when `think` is set."""
    think_profiles = ws_cfg_local.get("think_profiles")
    ws_think = ws_cfg_local.get("think")
    profile: dict = {}
    if think_profiles and ws_think is not None:
        profile = think_profiles.get("thinking" if ws_think else "instruct") or {}

    resolved = {}
    for key in _SAMPLING_KEYS:
        val = profile.get(key, ws_cfg_local.get(key))
        if val is not None:
            resolved[key] = val
    return resolved


# reasoning_effort -> output-token cap. Explicit request-level override of a
# reasoning lane's fixed predict_limit (A4, TASK_REASONING_GROUP_OVERHAUL_V1 §1).
# Env-overridable so the three tiers retune without a code change.
_REASONING_EFFORT_PREDICT: dict[str, int] = {
    "low": int(os.environ.get("REASONING_EFFORT_LOW", "4096")),
    "medium": int(os.environ.get("REASONING_EFFORT_MEDIUM", "16384")),
    "high": int(os.environ.get("REASONING_EFFORT_HIGH", "49152")),
}


def _apply_reasoning_effort(body: dict) -> tuple[int, str] | None:
    """Pop ``reasoning_effort`` from ``body`` (mutates in place) and, when it is a
    recognised tier, hard-set ``max_tokens`` to the mapped cap.

    An explicit effort is a user override, so it wins over the workspace's fixed
    predict_limit (hard assignment, not setdefault). Returns ``(cap, label)`` when
    applied, else ``None``. Always removes the key so it never reaches the backend.
    """
    effort = body.pop("reasoning_effort", None)
    if not effort:
        return None
    label = str(effort).strip().lower()
    cap = _REASONING_EFFORT_PREDICT.get(label)
    if cap is None:
        return None
    body["max_tokens"] = cap
    return cap, label


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
    ``min_p``, ``repeat_penalty``, ``presence_penalty``, ``seed``),
    ``mirostat``/``mirostat_tau``/``mirostat_eta`` (mutually exclusive with
    top_p/top_k; injected only when the workspace opts in), and ``think``.

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

    # reasoning_effort override wins over the workspace's fixed predict_limit
    _effort = _apply_reasoning_effort(body)
    # output token cap — map to top-level max_tokens (OpenAI standard)
    predict_limit = ws_cfg_local.get("predict_limit")
    if predict_limit and _effort is None:
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
    # setdefault — caller wins; values from _resolve_sampling_values.
    for key, val in _resolve_sampling_values(ws_cfg_local).items():
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
    """Per-request injection for ``type == "omlx"`` backends. Verified live
    (2026-08-15): oMLX wires top_k/min_p/presence_penalty/seed, but names
    repeat_penalty "repetition_penalty" and has no bare think (mapped to
    chat_template_kwargs.enable_thinking). All via setdefault so caller wins.
    """
    body = dict(body)
    ws_cfg_local = WORKSPACES.get(workspace_id, {}) if workspace_id else {}

    _effort = _apply_reasoning_effort(body)
    predict_limit = ws_cfg_local.get("predict_limit")
    if predict_limit and _effort is None:
        body.setdefault("max_tokens", predict_limit)
    if _effort is not None:
        _ctk = dict(body.get("chat_template_kwargs") or {})
        _ctk.setdefault("reasoning_effort", _effort[1])
        body["chat_template_kwargs"] = _ctk

    if body.get("stream", True):
        body.setdefault("stream_options", {})["include_usage"] = True

    sampling_values = _resolve_sampling_values(ws_cfg_local)
    for key in ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "seed"):
        val = sampling_values.get(key)
        if val is not None:
            body.setdefault(key, val)

    repeat_penalty = sampling_values.get("repeat_penalty")
    if repeat_penalty is not None:
        body.setdefault("repetition_penalty", repeat_penalty)

    ws_think = ws_cfg_local.get("think")
    if ws_think is not None:
        ctk = dict(body.get("chat_template_kwargs") or {})
        ctk.setdefault("enable_thinking", ws_think)
        body["chat_template_kwargs"] = ctk

    return body
