"""Cooperative cancellation for compliance tool calls (HOST_MEMORY_SAFETY W3.4).

``invoke_tool`` binds a :class:`CancelToken` in a ``ContextVar`` and runs the
tool in an executor under a copy of that context. When the HTTP client goes
away it cancels the token. Model calls check it before each request and while
streaming; the council and sweep loops check it between seats and readings.

:class:`TurnCancelled` derives from ``BaseException`` on purpose: the reading
and council loops catch ``Exception`` to turn a failed call into a non-vote or
a transport-failure receipt, and a cancelled call must not become either. It
propagates to ``invoke_tool``, which records ``cancelled`` instead of a partial
verdict. Lives in the compliance module so MCP code does not import the
pipeline (Rule 3).
"""

from __future__ import annotations

import contextvars
import threading

__all__ = ["CancelToken", "TurnCancelled", "bind", "cancelled", "check"]


class TurnCancelled(BaseException):  # noqa: N818 - named by the task contract
    """The client that asked for this work disconnected."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason = ""

    def cancel(self, reason: str = "client disconnected") -> None:
        self.reason = reason
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


_TOKEN: contextvars.ContextVar[CancelToken | None] = contextvars.ContextVar(
    "compliance_cancel_token", default=None
)


def bind(token: CancelToken) -> None:
    """Install ``token`` in the current context (call inside the copied context)."""
    _TOKEN.set(token)


def cancelled() -> bool:
    token = _TOKEN.get()
    return token is not None and token.is_set()


def check() -> None:
    """Raise :class:`TurnCancelled` if this context's work was cancelled."""
    token = _TOKEN.get()
    if token is not None and token.is_set():
        raise TurnCancelled(token.reason)
