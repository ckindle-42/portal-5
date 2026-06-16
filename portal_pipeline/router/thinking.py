"""Shared think-content handling for streaming and non-streaming paths.

Centralises the three operations that both paths need:

* :func:`strip_think` — remove ``<think>…</think>`` blocks from a string.
* :func:`extract_think_inner` — pull the text *inside* the first think block.
* :func:`normalize_think_message` — in-place promotion of reasoning fields to
  ``content`` on a completed non-streaming message dict.

The streaming path's per-chunk rewriting and end-of-stream fallback are
stateful (they accumulate across chunks), so they stay in ``streaming.py``
and call the helpers here rather than importing a full state machine.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_INNER_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Return *text* with all ``<think>…</think>`` blocks removed and stripped."""
    return _THINK_RE.sub("", text).strip()


def extract_think_inner(text: str) -> str:
    """Return the text inside the first ``<think>…</think>`` block, or ``""``."""
    m = _THINK_INNER_RE.search(text)
    return m.group(1).strip() if m else ""


def normalize_think_message(msg: dict, *, workspace_id: str = "", backend_id: str = "") -> None:
    """Promote reasoning fields to ``content`` on a completed non-streaming message.

    Mutates *msg* in place. Priority order:

    1. ``reasoning`` field present and ``content`` is empty → set content = reasoning.
    2. ``reasoning_content`` field present and ``content`` is empty → set content = reasoning_content.
    3. ``content`` contains only a ``<think>…</think>`` wrapper → strip it; if nothing
       remains, surface the inner text as content instead.

    Logs at DEBUG/WARNING level using *workspace_id* and *backend_id* for
    traceability; both are optional.
    """
    content: str = msg.get("content") or ""
    reasoning: str = msg.get("reasoning") or ""
    reasoning_content: str = msg.get("reasoning_content") or ""

    if not content and reasoning:
        logger.debug(
            "Backend %s: reasoning→content promotion for workspace=%s "
            "(thinking chain consumed all tokens)",
            backend_id,
            workspace_id,
        )
        msg["content"] = reasoning
        return

    if not content and reasoning_content:
        msg["content"] = reasoning_content
        return

    if content and "<think>" in content:
        stripped = strip_think(content)
        if not stripped:
            inner = extract_think_inner(content)
            if inner:
                logger.warning(
                    "workspace=%s backend=%s: content was pure <think> block — "
                    "promoting inner reasoning as response.",
                    workspace_id,
                    backend_id,
                )
                msg["content"] = inner
