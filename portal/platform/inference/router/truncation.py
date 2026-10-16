"""P-4 detect: an Ollama prompt longer than the served tag's window is cut silently.

Measured 2026-10-15 on Ollama 0.40.5 through the pipeline, ``bench``-style
non-streamed requests of a ~20k-token prompt:
  * gemma4 ``-ctx8k`` (Ollama engine): HTTP 200, ``prompt_tokens`` = 4099, the
    head of the prompt dropped (the model quoted a word from the tail). No error.
  * LFM2.5 ``-ctx8k`` (llama.cpp runner): HTTP 400 ``request (20082 tokens)
    exceeds the available context size (8192 tokens)``. Loud, not silent.
``prompt_tokens`` is therefore the POST-truncation count, so truncation shows as
an estimated input far above the window while the reported count sits at or
under it. The window is the tag's ``-ctxNk`` suffix (the platform's convention,
enforced by ``tests.wfe.settings_audit``); a tag without the suffix is not judged.
The estimate is ``chars / 4`` over messages and tools, which under-counts tokens,
so a flag needs a wide margin and never fires on an untruncated prompt.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from typing import Any

from portal.platform.inference.router import trace
from portal.platform.inference.router.metrics import _errors_total

_CTX_RE = re.compile(r"-ctx(\d+)k$", re.IGNORECASE)
#: Estimated tokens must exceed the window by this factor before a flag is raised.
_MARGIN = 1.25

_estimate: ContextVar[int] = ContextVar("portal_prompt_estimate", default=0)
_notice: ContextVar[str] = ContextVar("portal_truncation_notice", default="")


def window_of(model: str) -> int | None:
    """Baked window in tokens from a ``-ctxNk`` tag, else ``None``."""
    match = _CTX_RE.search(model or "")
    return int(match.group(1)) * 1024 if match else None


def set_estimate(body: dict[str, Any]) -> None:
    """Remember the request's estimated prompt tokens for this turn."""
    try:
        chars = len(json.dumps(body.get("messages") or [], default=str))
        chars += len(json.dumps(body.get("tools") or [], default=str))
        _estimate.set(chars // 4)
        _notice.set("")
    except Exception:
        _estimate.set(0)


def check(model: str, workspace: str, prompt_tokens: int) -> bool:
    """Flag a truncated prompt: trace note, metric, pending visible notice."""
    window, est = window_of(model), _estimate.get()
    if not window or not prompt_tokens or est <= window * _MARGIN or prompt_tokens > window:
        return False
    trace.note(
        prompt_truncated={
            "model": model,
            "window": window,
            "estimated_prompt": est,
            "reported_prompt": prompt_tokens,
        }
    )
    _errors_total.labels(workspace=workspace, error_type="prompt_truncated").inc()
    _notice.set(
        f"⚠️ Input truncated: about {est:,} tokens were sent but {model} holds "
        f"{window:,}; the start of the conversation was dropped."
    )
    return True


def take_notice() -> str:
    """The one-line notice for this turn, once; empty when nothing was truncated."""
    text = _notice.get()
    if text:
        _notice.set("")
    return text
