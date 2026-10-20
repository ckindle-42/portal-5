"""Pre-dispatch request transforms.

Functions in this module take the incoming request body + workspace_id
and apply context-aware mutations (persona → workspace resolution, auto
routing, vision fallback, temporal context, system prompt append, file
attachment normalization) before the request is dispatched to the
selected backend.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from portal.platform.inference.router.metrics import _alias_hits_total, _router_layer_total
from portal.platform.inference.router.routing import (
    _HARMFUL_INTENT_LANE,
    _detect_workspace,
    _route_with_llm,
    detect_harmful_intent,
)
from portal.platform.inference.router.workspaces import _PERSONA_MAP, WORKSPACES

logger = logging.getLogger(__name__)
_DEPRECATED_ALIAS_LOGGED: set[str] = set()


def append_text_to_content(content: Any, text: str) -> Any:
    """Append ``text`` to a message's content in whichever form the client sent.

    OpenAI allows ``content`` as a string or a list of typed parts (IDE clients
    and SDKs send system prompts as parts); string concatenation onto a list
    raised TypeError and failed the request with a 500.
    """
    if isinstance(content, list):
        return [*content, {"type": "text", "text": text}]
    return (content if isinstance(content, str) else "") + text


def _resolve_persona_workspace(workspace_id: str) -> str:
    """Resolve a persona slug or deprecated workspace id before routing.

    Deprecated workspace aliases count every use and log once per id.
    """
    requested_id = workspace_id
    if workspace_id in WORKSPACES:
        return workspace_id
    persona = _PERSONA_MAP.get(workspace_id)
    if persona is not None:
        workspace_id = persona.workspace_model
        if workspace_id in WORKSPACES:
            return workspace_id
    from portal.platform.inference.config import load_portal_config

    alias = load_portal_config().aliases.get(workspace_id)
    if alias is None:
        return requested_id
    if workspace_id not in _DEPRECATED_ALIAS_LOGGED:
        logger.warning(
            "Workspace alias %s is deprecated; use %s (remove after %s): %s",
            workspace_id,
            alias.to,
            alias.remove_after,
            alias.reason,
        )
        _DEPRECATED_ALIAS_LOGGED.add(workspace_id)
    _alias_hits_total.labels(alias=workspace_id).inc()
    return alias.to


def _unpack_synthetic_workspace(workspace_id: str) -> tuple[str, str | None]:
    """Unpack the canonical ``"<base>::<variant>"`` synthetic form into
    (base id, variant). Returns ``(workspace_id, None)`` unchanged for any
    plain base id (or unrecognized string) with no ``::``.

    This is the sole surviving piece of what was, pre-alias-retirement-
    closeout, ``_resolve_legacy_workspace_alias`` — a shim that also mapped
    ~25 pre-collapse bare workspace ids (``auto-agentic``, ``auto-redteam``,
    etc.) to their current (base, variant). The shim was removed once every
    live caller (opencode, Incalmo, the security bench harness, and both
    internal routing layers) was proven to address workspaces canonically —
    see ``CLOSEOUT_ALIAS_REMOVAL.md`` and ``docs/RESULTS_ALIAS_RETIRE_V1_
    20260713.md``'s Finish section for the live-traffic zero-trip evidence.
    A caller that still sends a bare pre-collapse alias id today gets it
    back unchanged (treated as an unknown workspace, same as any typo).
    """
    if "::" in workspace_id:
        base, variant = workspace_id.split("::", 1)
        return base, variant
    return workspace_id, None


def _resolve_workspace_variant(
    original_model_id: str, workspace_id: str, variant_param: str | None
) -> str:
    """Apply a named variant override onto a factored workspace (e.g.
    ``auto-coding`` folding the old auto-coding-agentic/auto-agentic/…
    siblings — BUILD_PROGRAM_COLLAPSE_V1.md Phase 5/6).

    Variant selection, in priority order: an explicit ``?variant=`` query
    param on the request, else the persona's own declared ``variant``
    field (when ``original_model_id`` names a persona). No variant
    resolved, or the workspace declares no ``variants`` block, or the name
    doesn't match one of its variants -> ``workspace_id`` unchanged
    (a typo'd/unknown variant is a silent no-op, not an error, so a bad
    query param never breaks a request).

    Merging is idempotent and allocation-free after the first call for a
    given (workspace_id, variant) pair: the merged config is cached in the
    live ``WORKSPACES`` dict under a synthetic ``f"{workspace_id}::{variant}"``
    key. This is safe under concurrent requests — the key space is the
    small, fixed set of declared variant names (not per-request/unbounded),
    and a dict `__setitem__` with the same key/value from two concurrent
    requests is a harmless race, not a corruption.
    """
    variant_name = variant_param
    if not variant_name:
        persona = _PERSONA_MAP.get(original_model_id)
        if persona is not None:
            variant_name = persona.variant
    if not variant_name:
        return workspace_id

    from portal.platform.inference.config import load_portal_config

    spec = load_portal_config().workspaces.get(workspace_id)
    if spec is None or variant_name not in spec.variants:
        return workspace_id

    synthetic_id = f"{workspace_id}::{variant_name}"
    if synthetic_id not in WORKSPACES:
        WORKSPACES[synthetic_id] = {
            **WORKSPACES.get(workspace_id, {}),
            **spec.variants[variant_name],
        }
    return synthetic_id


def _known_backend_models() -> frozenset[str]:
    """Every model id declared anywhere in config/backends.yaml's backend
    groups — the bounded catalog ?model= overrides are restricted to (see
    _resolve_model_override). Cached at module scope: backends.yaml is
    read-only at runtime, so this never needs to be recomputed per-request.
    """
    import yaml

    from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH

    try:
        with open(DEFAULT_CONFIG_PATH) as fh:
            cfg = yaml.safe_load(fh.read())
    except OSError:
        return frozenset()
    models: set[str] = set()
    for group in cfg.get("backends", []):
        for m in group.get("models", []):
            if isinstance(m, dict) and m.get("id"):
                models.add(m["id"])
    return frozenset(models)


_KNOWN_BACKEND_MODELS: frozenset[str] | None = None


def _resolve_model_override(workspace_id: str, model_param: str | None) -> str:
    """Apply an explicit ``?model=<hint>`` override onto the resolved
    workspace (DESIGN_COLLAPSE_V1.md §D5 — "model choice moves to a router
    param"). ``model_param`` must be one of the model ids declared in
    config/backends.yaml — this bounds the synthetic-key space to the fixed,
    finite model catalog (~150 ids), same discipline as the variant cache;
    unlike a variant name, ``model_param`` is arbitrary user input, so
    without this check an attacker could grow WORKSPACES unboundedly with
    junk keys. An unknown/mistyped model param is a silent no-op, not an
    error — matches _resolve_workspace_variant's "bad param never breaks
    the request" behavior.
    """
    global _KNOWN_BACKEND_MODELS
    if not model_param:
        return workspace_id
    if _KNOWN_BACKEND_MODELS is None:
        _KNOWN_BACKEND_MODELS = _known_backend_models()
    if model_param not in _KNOWN_BACKEND_MODELS:
        return workspace_id

    synthetic_id = f"{workspace_id}::model={model_param}"
    if synthetic_id not in WORKSPACES:
        WORKSPACES[synthetic_id] = {**WORKSPACES.get(workspace_id, {}), "model_hint": model_param}
    return synthetic_id


async def _resolve_auto_routing(workspace_id: str, messages: list[dict[str, Any]]) -> str:
    """Run LLM-based and keyword-based auto-routing when workspace_id is 'auto'.

    When workspace_id is not 'auto', returns it unchanged. Otherwise attempts
    Layer 1 LLM intent classification, falling back to Layer 2 keyword scoring.
    Returns the detected workspace_id, or 'auto' if no workspace was detected.
    """
    if workspace_id != "auto":
        return workspace_id
    # Harmful-intent gate (adaptive UAT FINDINGS C1/C2/C3): a genuinely harmful
    # ask — targeting a private individual, deception/fraud, harassment — must
    # be handled by a standard-posture lane so it refuses, never by the
    # abliterated default. Non-harmful `auto` traffic still routes normally
    # (mostly to abliterated lanes, by design).
    if detect_harmful_intent(messages):
        logger.warning(
            "Auto-routing: harmful-intent gate fired — routing to standard-posture "
            "lane '%s' instead of the abliterated default.",
            _HARMFUL_INTENT_LANE,
        )
        _router_layer_total.labels(
            layer="harmful_intent_gate", workspace=_HARMFUL_INTENT_LANE
        ).inc()
        return _HARMFUL_INTENT_LANE
    # LLM router first — semantic intent, ~100ms, falls back on timeout/low confidence
    detected = await _route_with_llm(messages)
    if detected:
        logger.info("Auto-routing (LLM): detected workspace '%s' from message content", detected)
        _router_layer_total.labels(layer="llm", workspace=detected).inc()
        return detected
    # Keyword fallback — deterministic, zero-latency
    detected = _detect_workspace(messages)
    if detected:
        logger.info(
            "Auto-routing (keywords): detected workspace '%s' from message content",
            detected,
        )
        _router_layer_total.labels(layer="keywords", workspace=detected).inc()
        return detected
    _router_layer_total.labels(layer="fallback_auto", workspace=workspace_id).inc()
    return workspace_id


def _resolve_vision_fallback(workspace_id: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Reroute auto-vision text-only requests to auto-reasoning with vision context.

    Vision-language models return empty content when no image is provided. Detect
    absence of image_url content parts and reroute to auto-reasoning for text-only
    queries, injecting a vision-domain system prompt so responses use vision vocabulary.

    Returns (workspace_id, body) — body may be mutated if the fallback fires.
    """
    if workspace_id != "auto-vision":
        return workspace_id, body
    messages = body.get("messages", [])
    has_image = any(
        isinstance(part, dict) and part.get("type") == "image_url"
        for msg in messages
        for part in (msg.get("content", []) if isinstance(msg.get("content"), list) else [])
    )
    if not has_image:
        logger.info(
            "auto-vision: no image_url in request — rerouting to auto-reasoning "
            "with vision system context injected"
        )
        workspace_id = "auto-reasoning"
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            vision_system = {
                "role": "system",
                "content": (
                    "You are a vision AI assistant. When answering questions about "
                    "your capabilities, focus on visual analysis tasks: image "
                    "understanding, diagram interpretation, visual element detection, "
                    "object recognition, scene description, chart reading, and "
                    "multimodal reasoning from images and diagrams."
                ),
            }
            body = {**body, "messages": [vision_system] + messages}
    return workspace_id, body


def _inject_temporal_context(workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Inject today's date and search-first instructions for web-tool-enabled workspaces.

    Gated by RESEARCH_DATE_INJECTION (env, default on) and the workspace declaring a
    web tool or inject_temporal_context flag. Merges into an existing system message
    or prepends a new one. Returns body (possibly with updated messages).
    """
    if os.environ.get("RESEARCH_DATE_INJECTION", "true").lower() not in ("1", "true", "yes"):
        return body
    _ws_cfg = WORKSPACES.get(workspace_id, {})
    _ws_tools = set(_ws_cfg.get("tools", []) or [])
    _web_tools = {"web_search", "news_search", "web_fetch"}
    if not (_ws_tools & _web_tools or _ws_cfg.get("inject_temporal_context")):
        return body
    _today = datetime.now(UTC).strftime("%A, %B %d, %Y")
    _temporal = (
        f"\n\nToday's date is {_today} (UTC). Your training data has a fixed "
        "cutoff and is very likely out of date for anything that changes over "
        "time — current events, news, software and library versions, CVEs and "
        "exploit availability, prices, or who currently holds a role.\n"
        "Follow this order strictly:\n"
        "1. For any such question, call web_search (or news_search) FIRST and "
        "answer from the results. Cite the source URL for each fact you use.\n"
        "2. If search is unavailable or returns nothing useful, you MAY answer "
        "from training knowledge — but state plainly that it may be outdated and "
        "was not verified against a current source.\n"
        "3. If you cannot get reliable information either way, say you don't "
        "know. Never invent specifics — version numbers, CVE IDs, dates, names, "
        "statistics, or URLs. A clear 'I don't know' is correct; a confident "
        "fabrication is a failure."
    )
    _msgs = body.get("messages", [])
    _sys_i = next((i for i, m in enumerate(_msgs) if m.get("role") == "system"), None)
    if _sys_i is not None:
        _u = dict(_msgs[_sys_i])
        _u["content"] = append_text_to_content(_u.get("content"), _temporal)
        _msgs = list(_msgs)
        _msgs[_sys_i] = _u
        return {**body, "messages": _msgs}
    return {
        **body,
        "messages": [{"role": "system", "content": _temporal.lstrip()}] + _msgs,
    }


def _inject_persona_system_prompt(model_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Put a persona slug's system prompt first unless the request already has it."""
    persona = _PERSONA_MAP.get(model_id)
    prompt = persona.system_prompt if persona is not None else ""
    if not prompt:
        return body
    messages = list(body.get("messages") or [])
    idx = next((i for i, message in enumerate(messages) if message.get("role") == "system"), None)
    if idx is None:
        return {**body, "messages": [{"role": "system", "content": prompt}, *messages]}
    current = messages[idx].get("content")
    if str(current).strip() == prompt.strip():
        return body
    updated = dict(messages[idx])
    if isinstance(current, list):
        updated["content"] = [{"type": "text", "text": prompt}, *current]
    else:
        caller = current if isinstance(current, str) else ""
        gap = "" if (not caller or prompt.endswith("\n\n")) else "\n"
        updated["content"] = f"{prompt}{gap}{caller}" if caller else prompt
    messages[idx] = updated
    return {**body, "messages": messages}


# A known persona slug, then one space. Anything else that starts with "/" stays.
_ROLE_SLASH = re.compile(r"^/([A-Za-z0-9_-]+) (.*)$", re.DOTALL)


def _strip_role_prefix(content: Any) -> tuple[str | None, Any]:
    """Return (slug, content without the `/slug ` token) when the text starts with one."""
    if isinstance(content, str):
        match = _ROLE_SLASH.match(content)
        persona = _PERSONA_MAP.get(match.group(1)) if match is not None else None
        # Only prompt-only roles ride on another engine; behavioural personas keep their tools.
        if match is not None and getattr(persona, "delivery", None) == "role":
            return match.group(1), match.group(2)
        return None, content
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            text = first.get("text")
        elif isinstance(first, str):
            text = first
        else:
            text = None
        if isinstance(text, str):
            slug, rest = _strip_role_prefix(text)
            if slug is not None:
                updated: Any = {**first, "text": rest} if isinstance(first, dict) else rest
                return slug, [updated, *content[1:]]
    return None, content


def _apply_role_slash(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Strip a leading `/slug ` from user messages. The last slug wins."""
    messages = body.get("messages") or []
    role_slug: str | None = None
    changed = False
    updated_messages: list[Any] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            updated_messages.append(message)
            continue
        slug, content = _strip_role_prefix(message.get("content"))
        if slug is None:
            updated_messages.append(message)
            continue
        role_slug = slug
        changed = True
        updated_messages.append({**message, "content": content})
    if not changed:
        return body, None
    return {**body, "messages": updated_messages}, role_slug


def _inject_requested_prompts(model_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Inject a slash-command persona prompt, then the model persona's prompt."""
    body, role_slug = _apply_role_slash(body)
    if role_slug:
        body = _inject_persona_system_prompt(role_slug, body)
    return _inject_persona_system_prompt(model_id, body)


def _inject_system_prompt_append(workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Append workspace-level system_prompt_append to the system message.

    If the workspace defines system_prompt_append, appends it to an existing system
    message or injects a new system message if none is present. Returns body
    (possibly with updated messages).
    """
    _prompt_append = WORKSPACES.get(workspace_id, {}).get("system_prompt_append", "")
    if not _prompt_append:
        return body
    messages = body.get("messages", [])
    sys_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), None)
    if sys_idx is not None:
        updated = dict(messages[sys_idx])
        updated["content"] = append_text_to_content(updated.get("content"), _prompt_append)
        messages = list(messages)
        messages[sys_idx] = updated
        return {**body, "messages": messages}
    return {
        **body,
        "messages": [{"role": "system", "content": _prompt_append}] + messages,
    }


def _inject_attached_files(body: dict[str, Any]) -> dict[str, Any]:
    """Inject OWUI file attachments as notes in the last user message.

    OWUI sends uploaded files in body["files"] but does not include them in the
    messages array. Inject a note into the last user message so the model can
    reference audio/document file IDs in tool calls. Returns body (possibly with
    updated messages).
    """
    _attached_files = body.get("files") or []
    if not _attached_files:
        return body
    _file_notes: list[str] = []
    for _f in _attached_files:
        _fid = _f.get("id") or ""
        _fname = _f.get("name") or _f.get("filename") or ""
        _ftype = _f.get("type") or _f.get("meta", {}).get("content_type") or ""
        if _fid or _fname:
            _file_notes.append(
                f"[Attached file — id: {_fid!r}, name: {_fname!r}, type: {_ftype!r}]"
            )
    if not _file_notes:
        return body
    _msgs = list(body.get("messages", []))
    _note = "\n".join(_file_notes)
    # Append to last user message so the model sees it in context
    for _i in range(len(_msgs) - 1, -1, -1):
        if _msgs[_i].get("role") == "user":
            _c = _msgs[_i].get("content", "")
            if isinstance(_c, str):
                _msgs[_i] = {**_msgs[_i], "content": _c + "\n\n" + _note}
            elif isinstance(_c, list):
                _msgs[_i] = {
                    **_msgs[_i],
                    "content": _c + [{"type": "text", "text": _note}],
                }
            break
    logger.debug("Injected %d file reference(s) into messages", len(_file_notes))
    return {**body, "messages": _msgs}
