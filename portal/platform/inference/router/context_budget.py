"""Fit a prompt to the seat's context window before an engine silently drops its head.

Ollama cuts an over-long prompt from the head to fit the tag's ``num_ctx`` and answers
from the tail: measured live 2026-11-16 on ``granite4.1:8b-ctx8k``, a 112 KB tool
result became a 237-token prompt with the system prompt, the persona and the user's
question gone — no error, no log line. The pipeline carries no tokenizer, so the prompt
is estimated from its own bytes with a per-engine ratio that errs high; the window is
resolved from config (the workspace's declared ``context_limit``, the served tag's
baked ``-ctxNk``, or the model card's documented ceiling for oMLX). When the estimate
does not fit, the oldest tool results are cut first (head plus a marker), then the
oldest assistant and user turns; the system prompt, the tool schemas and the latest
user turn are never touched. A prompt that still cannot fit is refused in band instead
of being sent for the engine to truncate.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from portal.platform.inference.model_addressing import (
    workspace_context_limit,
    workspace_model_hint,
)
from portal.platform.inference.model_cards import card_entry
from portal.platform.inference.router.metrics import _context_fit_total
from portal.platform.inference.router.truncation import note_fit, window_of

logger = logging.getLogger(__name__)

#: Characters per token, per engine, erring high. Ollama cuts silently, so its estimate
#: must never under-count; oMLX/llama.cpp refuses loudly, so 3.5 avoids a needless shrink.
_CHARS_PER_TOKEN = {"ollama": 3.0, "omlx": 3.5}
_DEFAULT_CHARS_PER_TOKEN = 3.0
#: Chat-template scaffolding charged per message.
_PER_MESSAGE_TOKENS = 4
#: Room held back from the window for the answer: at most a quarter of it.
_RESERVE_DIVISOR = 4
#: Smallest head kept when a piece is cut, so the marker is never the whole message.
_MIN_HEAD_CHARS = 400
#: Characters cut beyond the measured overshoot: the marker and template scaffolding.
_CUT_SLACK_CHARS = 512
#: Marker appended to a cut message; a later, tighter fit cuts the head again.
_MARKER = "\n\n[…truncated {removed:,} characters to fit the model's context window…]\n\n"


#: Prefix of the local refusal message; fallback wrappers match it so a refusal
#: that never reached a backend cannot pin that backend (P-2 exemption).
REFUSAL_PREFIX = "⚠️ **The conversation exceeds this workspace's context**"


class ContextOverflowError(Exception):
    """A prompt that cannot be shrunk into the seat's window, so it is never sent."""

    def __init__(self, workspace: str, model: str, estimated: int, limit: int) -> None:
        self.workspace = workspace
        self.model = model
        self.estimated = estimated
        self.limit = limit
        super().__init__(
            f"{REFUSAL_PREFIX} "
            f"(about {estimated:,} tokens for a {limit:,}-token window), so it was not "
            "sent. Start a new chat, or send less material in one turn."
        )


@dataclass(frozen=True)
class FitReport:
    """What the guard found and did, for the caller's trace and log line."""

    workspace: str
    model: str
    engine: str
    limit: int | None
    budget: int
    estimated: int
    estimated_after: int
    shrunk: tuple[str, ...] = ()

    @property
    def fitted(self) -> bool:
        """True when at least one piece of the prompt was cut."""
        return bool(self.shrunk)


def context_window(workspace_id: str, model: str, engine: str) -> int | None:
    """The tokens this engine can hold for this request, or ``None`` when undeclared."""
    declared = workspace_context_limit(workspace_id) or None
    baked = window_of(model)
    if engine == "omlx":
        return declared or _card_context(model, workspace_id) or baked
    windows = [window for window in (declared, baked) if window]
    return min(windows) if windows else None


def estimate_tokens(body: dict[str, Any], engine: str) -> int:
    """Prompt tokens from the request's own bytes, erring high on purpose."""
    messages = body.get("messages") or []
    chars = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        chars += _content_chars(message.get("content"))
        chars += len(str(message.get("role") or "")) + len(str(message.get("name") or ""))
        if message.get("tool_calls"):
            chars += len(json.dumps(message["tool_calls"], default=str))
    if body.get("tools"):
        chars += len(json.dumps(body["tools"], default=str))
    ratio = _CHARS_PER_TOKEN.get(engine, _DEFAULT_CHARS_PER_TOKEN)
    return int(chars / ratio) + len(messages) * _PER_MESSAGE_TOKENS


def fit_prompt(body: dict[str, Any], *, workspace_id: str, model: str, engine: str) -> FitReport:
    """Cut ``body``'s oldest content until it fits; raise when it cannot.

    Mutates ``messages`` in ``body`` only (a rebuilt list — the caller's message dicts
    are never touched). No-op when the window is undeclared or the prompt already fits.
    """
    limit = context_window(workspace_id, model, engine)
    estimated = estimate_tokens(body, engine)
    if limit is None:
        report = FitReport(workspace_id, model, engine, None, 0, estimated, estimated)
        _log_body(body, report)
        return report
    budget = _prompt_budget(body, limit)
    if estimated <= budget:
        report = FitReport(workspace_id, model, engine, limit, budget, estimated, estimated)
        _log_body(body, report)
        return report

    before = estimated
    ratio = _CHARS_PER_TOKEN.get(engine, _DEFAULT_CHARS_PER_TOKEN)
    rebuilt = [
        dict(message) if isinstance(message, dict) else message
        for message in (body.get("messages") or [])
    ]
    shrunk: list[str] = []
    cuts: list[tuple[str, int, int, int]] = []
    for index in _candidates(rebuilt):
        if estimated <= budget:
            break
        message = rebuilt[index]
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        cut = _shrunk_content(content, int((estimated - budget) * ratio) + _CUT_SLACK_CHARS)
        if cut is None:
            continue
        shrunk.append(f"{message.get('role')}[{index}] {len(content):,}→{len(cut):,} chars")
        cuts.append((str(message.get("role")), index, len(content), len(cut)))
        message["content"] = cut
        body["messages"] = rebuilt
        estimated = estimate_tokens(body, engine)

    if estimated > budget:
        _context_fit_total.labels(workspace=workspace_id, engine=engine, outcome="overflow").inc()
        logger.warning(
            "Context overflow: workspace=%s model=%s engine=%s estimated=%d tokens "
            "limit=%d prompt_budget=%d — refusing the call instead of a silent truncation",
            workspace_id,
            model,
            engine,
            estimated,
            limit,
            budget,
        )
        raise ContextOverflowError(workspace_id, model, estimated, limit)

    if shrunk:
        _context_fit_total.labels(workspace=workspace_id, engine=engine, outcome="shrunk").inc()
        logger.warning(
            "Context fit: workspace=%s model=%s engine=%s estimated=%d→%d tokens "
            "limit=%d prompt_budget=%d shrunk=%s %s",
            workspace_id,
            model,
            engine,
            before,
            estimated,
            limit,
            budget,
            "; ".join(shrunk),
            _system_fingerprint(body),
        )
        note_fit(model=model, limit=limit, estimate=estimated, cuts=tuple(cuts))
    report = FitReport(workspace_id, model, engine, limit, budget, before, estimated, tuple(shrunk))
    _log_body(body, report)
    return report


def _system_text(message: Any) -> str:
    """The system message's text as the engine receives it."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str) if content else ""


def _system_fingerprint(body: dict[str, Any]) -> str:
    """The system prompt that will reach the engine: size, hash, opening words."""
    messages = [m for m in (body.get("messages") or []) if isinstance(m, dict)]
    system = _system_text(next((m for m in messages if m.get("role") == "system"), None))
    digest = hashlib.sha256(system.encode()).hexdigest()[:12]
    return f"system={len(system)} chars sha256={digest} first={system[:80]!r}"


def _log_body(body: dict[str, Any], report: FitReport) -> None:
    """DEBUG: the body the caller is about to POST, message sizes included."""
    messages = [m for m in (body.get("messages") or []) if isinstance(m, dict)]
    logger.debug(
        "Context body: workspace=%s model=%s limit=%s estimate=%d roles=[%s] %s",
        report.workspace,
        report.model,
        report.limit,
        report.estimated_after,
        ", ".join(f"{m.get('role')}:{len(str(m.get('content') or ''))}" for m in messages),
        _system_fingerprint(body),
    )


def _card_context(model: str, workspace_id: str) -> int | None:
    """The model card's documented context ceiling, for an oMLX-served model."""
    for tag in (model, workspace_model_hint(workspace_id) or ""):
        hit = card_entry(tag) if tag else None
        value = hit[1].get("max_context") if hit else None
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def _content_chars(content: Any) -> int:
    """Text characters in a message's content; an image/audio part is charged flat."""
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, list):
        return 0
    total = 0
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            total += len(part["text"])
        else:
            total += 4 * 1024  # a non-text part: no tokenizer, so a per-attachment cost
    return total


def _prompt_budget(body: dict[str, Any], limit: int) -> int:
    """The window left for the prompt once the requested answer budget is held back."""
    reserve = limit // _RESERVE_DIVISOR
    for key in ("max_tokens", "max_completion_tokens"):
        value = body.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            reserve = min(value, reserve)
            break
    return max(0, limit - reserve)


def _candidates(messages: list[Any]) -> list[int]:
    """Message indices to cut, in the order the guard gives them up."""
    last_user = max(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, dict) and message.get("role") == "user"
        ),
        default=-1,
    )
    tool_results = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, dict) and message.get("role") == "tool"
    ]
    turns = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, dict)
        and message.get("role") in ("assistant", "user")
        and index != last_user
    ]
    return tool_results + turns


def _shrunk_content(content: str, cut_chars: int) -> str | None:
    """The piece's head plus the marker, or ``None`` when there is nothing worth cutting."""
    keep = max(_MIN_HEAD_CHARS, len(content) - cut_chars)
    if keep >= len(content):
        return None
    return content[:keep].rstrip() + _MARKER.format(removed=len(content) - keep)
