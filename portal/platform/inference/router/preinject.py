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
from datetime import UTC, datetime

from portal.platform.inference.router.metrics import _router_layer_total
from portal.platform.inference.router.routing import _detect_workspace, _route_with_llm
from portal.platform.inference.router.workspaces import _PERSONA_MAP, WORKSPACES

logger = logging.getLogger(__name__)


def _resolve_persona_workspace(workspace_id: str) -> str:
    """Resolve a persona slug to its backing workspace_model if not already a known workspace.

    If workspace_id is already a key in WORKSPACES, returns it unchanged.
    Otherwise looks up _PERSONA_MAP[workspace_id].workspace_model and returns that
    if it resolves to a known workspace. Falls back to the original workspace_id.
    """
    if workspace_id not in WORKSPACES:
        persona = _PERSONA_MAP.get(workspace_id)
        if persona is not None and persona.workspace_model in WORKSPACES:
            return persona.workspace_model
    return workspace_id


async def _resolve_auto_routing(workspace_id: str, messages: list[dict]) -> str:
    """Run LLM-based and keyword-based auto-routing when workspace_id is 'auto'.

    When workspace_id is not 'auto', returns it unchanged. Otherwise attempts
    Layer 1 LLM intent classification, falling back to Layer 2 keyword scoring.
    Returns the detected workspace_id, or 'auto' if no workspace was detected.
    """
    if workspace_id != "auto":
        return workspace_id
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


def _resolve_vision_fallback(workspace_id: str, body: dict) -> tuple[str, dict]:
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


def _inject_temporal_context(workspace_id: str, body: dict) -> dict:
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
        _u["content"] = _u.get("content", "") + _temporal
        _msgs = list(_msgs)
        _msgs[_sys_i] = _u
        return {**body, "messages": _msgs}
    return {
        **body,
        "messages": [{"role": "system", "content": _temporal.lstrip()}] + _msgs,
    }


def _inject_system_prompt_append(workspace_id: str, body: dict) -> dict:
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
        updated["content"] = updated.get("content", "") + _prompt_append
        messages = list(messages)
        messages[sys_idx] = updated
        return {**body, "messages": messages}
    return {
        **body,
        "messages": [{"role": "system", "content": _prompt_append}] + messages,
    }


def _inject_attached_files(body: dict) -> dict:
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
