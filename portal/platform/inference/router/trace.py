"""Per-turn operational trace — bounded, file-backed, never consulted by routing.

Ground Rule 4 keeps conversation state out of the pipeline. This module holds
*operational* state only, on the same footing as ``metrics_state.json``: a
record of what the router decided and what the tool loop did on one turn,
written once at the end of that turn, read only by an operator through
``/v1/trace/*``. Nothing here is ever read back into a routing, backend or
tool decision, and the store is discarded when the container restarts.

Why a directory instead of a process-local ring: ``PIPELINE_WORKERS`` defaults
to 2, so an in-memory ring would scatter turns across worker processes and a
lookup would miss whenever the read landed on the wrong worker — the same
cross-process problem ``PROMETHEUS_MULTIPROC_DIR`` already solves for metrics.
Records go to a tmpfs directory shared by every worker in the container.

Capture is metadata by default: workspace resolution chain, backend and model,
tool names with durations and outcomes. Message and tool-argument bodies are
captured only when ``PORTAL_TRACE_BODIES`` is set, because prompts are user
content and this store is readable by anyone holding the pipeline key.

Every public helper swallows its own exceptions. A trace failure must never
change the outcome of a turn.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in _TRUE


def _int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


ENABLED: bool = _flag("PORTAL_TRACE", "1")
CAPTURE_BODIES: bool = _flag("PORTAL_TRACE_BODIES", "0")
MAX_RECORDS: int = _int("PORTAL_TRACE_MAX", 200)
# Keep enough room for the compact fallback record even when an operator sets
# an unusually small limit. Records stay valid JSON at every configured size.
MAX_RECORD_BYTES: int = max(512, _int("PORTAL_TRACE_MAX_BYTES", 32768))

# Correlation ids are minted as ``p5-<hex12>`` but may be supplied by a client
# through X-Correlation-ID, so the id is a filename component we do not trust.
_CID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_REDACT = ("authorization", "api_key", "apikey", "token", "password", "secret")


def trace_dir() -> Path:
    """Directory holding one JSON record per turn (tmpfs inside the container)."""
    configured = os.environ.get("PORTAL_TRACE_DIR", "").strip()
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "portal_traces"


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact(mapping: dict[str, Any]) -> dict[str, Any]:
    """Copy *mapping* with credential-shaped values replaced by a marker."""
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        lowered = str(key).lower()
        out[key] = (
            "<redacted>" if any(token in lowered for token in _REDACT) else _redact_value(value)
        )
    return out


class TurnTrace:
    """One turn's spans, written to disk by :meth:`finalize`.

    ``finalize`` overwrites rather than no-ops, which is what lets the handler's
    ``finally`` and the streaming generator's ``finally`` both call it: the
    handler returns as soon as the response headers are ready, so its write
    captures the routing decision, and the later streaming write replaces that
    record with the complete one including every tool hop. A client that
    disconnects mid-stream still leaves the earlier, partial record on disk.
    """

    __slots__ = ("cid", "started_at", "_t0", "_spans", "_meta", "_bodies")

    def __init__(self, cid: str) -> None:
        self.cid = cid
        self.started_at = time.time()
        self._t0 = time.monotonic()
        self._spans: list[dict[str, Any]] = []
        self._meta: dict[str, Any] = {}
        self._bodies: dict[str, Any] = {}

    def span(self, name: str, **fields: Any) -> None:
        """Append one named event with its offset from the start of the turn."""
        self._spans.append(
            {
                "name": name,
                "at_ms": round((time.monotonic() - self._t0) * 1000, 1),
                **redact(fields),
            }
        )

    def set(self, **fields: Any) -> None:
        """Merge turn-level facts (workspace, backend, model, outcome)."""
        self._meta.update(redact(fields))

    def capture(self, **fields: Any) -> None:
        """Keep opt-in message or tool-argument bodies on this turn."""
        for key, value in redact(fields).items():
            if key not in self._bodies:
                self._bodies[key] = value
            elif isinstance(self._bodies[key], list):
                self._bodies[key].append(value)
            else:
                self._bodies[key] = [self._bodies[key], value]

    def to_dict(self) -> dict[str, Any]:
        record = {
            "correlation_id": self.cid,
            "started_at": self.started_at,
            "duration_ms": round((time.monotonic() - self._t0) * 1000, 1),
            "bodies_captured": CAPTURE_BODIES,
            **self._meta,
            "spans": list(self._spans),
        }
        if self._bodies:
            record["bodies"] = dict(self._bodies)
        return record

    def finalize(self) -> None:
        """Write (or rewrite) this turn's record. Never raises."""
        with contextlib.suppress(Exception):
            _write(self.cid, self.to_dict())


_current: ContextVar[TurnTrace | None] = ContextVar("portal_turn_trace", default=None)


def start_trace(cid: str) -> TurnTrace | None:
    """Open a trace for *cid* and bind it to the request context.

    Bound inside the request handler rather than in ``CorrelationIdMiddleware``:
    the middleware resets its contextvar once ``call_next`` returns, which for a
    streaming response is before the body generator has run. The generator
    executes in a child task holding a copy of the context taken at spawn time,
    so a handler-bound trace stays reachable for the whole stream.
    """
    if not ENABLED or not _CID_RE.match(cid or ""):
        return None
    trace = TurnTrace(cid)
    _current.set(trace)
    return trace


def current_trace() -> TurnTrace | None:
    """The trace for the turn in flight, or ``None`` when tracing is off."""
    return _current.get()


def span(name: str, **fields: Any) -> None:
    """Record a span on the current turn. No-op when tracing is off."""
    with contextlib.suppress(Exception):
        trace = _current.get()
        if trace is not None:
            trace.span(name, **fields)


def note(**fields: Any) -> None:
    """Merge turn-level facts onto the current turn. No-op when tracing is off."""
    with contextlib.suppress(Exception):
        trace = _current.get()
        if trace is not None:
            trace.set(**fields)


def capture(**fields: Any) -> None:
    """Capture message or tool-argument bodies only when explicitly enabled."""
    with contextlib.suppress(Exception):
        trace = _current.get()
        if CAPTURE_BODIES and trace is not None:
            trace.capture(**fields)


def finalize_trace() -> None:
    """Write the current turn's record. Safe to call more than once."""
    with contextlib.suppress(Exception):
        trace = _current.get()
        if trace is not None:
            trace.finalize()


def _write(cid: str, record: dict[str, Any]) -> None:
    directory = trace_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, default=str, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_RECORD_BYTES:
        thin = {k: v for k, v in record.items() if k not in ("spans", "bodies")}
        thin["truncated"] = True
        thin["spans"] = []
        payload = json.dumps(thin, default=str, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_RECORD_BYTES:
            thin = {"correlation_id": cid, "truncated": True, "spans": []}
            payload = json.dumps(thin, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError("minimum trace record exceeds configured size limit")
    target = directory / f"{cid}.json"
    tmp = directory / f".{cid}.{os.getpid()}.tmp"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)
    _prune(directory)


def _prune(directory: Path) -> None:
    """Keep the newest ``MAX_RECORDS`` records; drop the rest."""
    with contextlib.suppress(Exception):
        entries = [e for e in os.scandir(directory) if e.name.endswith(".json")]
        if len(entries) <= MAX_RECORDS:
            return
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
        for stale in entries[MAX_RECORDS:]:
            with contextlib.suppress(OSError):
                os.unlink(stale.path)


def read_trace(cid: str) -> dict[str, Any] | None:
    """Load one record by correlation id, or ``None`` when it is not on disk."""
    if not _CID_RE.match(cid or ""):
        return None
    path = trace_dir() / f"{cid}.json"
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 — a missing or half-written record is not an error
        return None


def recent_traces(limit: int = 20) -> list[dict[str, Any]]:
    """Summaries of the most recent turns, newest first."""
    directory = trace_dir()
    try:
        entries = [e for e in os.scandir(directory) if e.name.endswith(".json")]
    except OSError:
        return []
    entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for entry in entries[: max(1, limit)]:
        record = read_trace(entry.name[: -len(".json")])
        if record is None:
            continue
        out.append(
            {
                key: record.get(key)
                for key in (
                    "correlation_id",
                    "started_at",
                    "duration_ms",
                    "workspace",
                    "persona",
                    "backend",
                    "model",
                    "outcome",
                    "tool_calls",
                )
            }
        )
    return out
