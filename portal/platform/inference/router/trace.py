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
import contextvars
import hashlib
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
#: Characters of each captured message kept verbatim; the rest is a size and a hash.
HEAD_CHARS: int = 160

# Correlation ids are minted as ``p5-<hex12>`` but may be supplied by a client
# through X-Correlation-ID, so the id is a filename component we do not trust.
_CID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_REDACT = ("authorization", "api_key", "apikey", "password", "secret")


def _is_credential_key(lowered: str) -> bool:
    """A credential-shaped key: the names in _REDACT, or a singular *token (access_token,
    x-token). Token *counts* (reasoning_tokens, prompt_tokens, max_tokens) are not secrets:
    blanking them turned the T1 timing rollup's counts into "<redacted>" in /v1/trace and the
    WFE runner then failed adding to them (campaign wfe_math_20261018c, every row
    HARNESS_ERROR)."""
    return any(name in lowered for name in _REDACT) or lowered.endswith("token")


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
        out[key] = "<redacted>" if _is_credential_key(lowered) else _redact_value(value)
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

    __slots__ = ("cid", "started_at", "_t0", "_spans", "_meta", "_bodies", "_seen")

    def __init__(self, cid: str) -> None:
        self.cid = cid
        self.started_at = time.time()
        self._t0 = time.monotonic()
        self._spans: list[dict[str, Any]] = []
        self._meta: dict[str, Any] = {}
        self._bodies: dict[str, Any] = {}
        self._seen = 0

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
            if key == "backend_request" and isinstance(value, dict):
                value = self._digest_request(value)
            if key not in self._bodies:
                self._bodies[key] = value
            elif isinstance(self._bodies[key], list):
                self._bodies[key].append(value)
            else:
                self._bodies[key] = [self._bodies[key], value]

    def _digest_request(self, body: dict[str, Any]) -> dict[str, Any]:
        """One tool-loop hop's request, compact: the messages new since the previous
        hop (role, size, sha256, head) plus a hash of the prefix already seen.

        A hop re-sends the whole conversation, so keeping every hop's full messages
        outgrows the record cap and loses the lot. The digest still shows whether each
        ``role:tool`` result arrived whole (``chars``/``sha256``), in order (``i``), and
        whether earlier messages were left untouched (``prefix_sha256``).
        """
        messages = body.get("messages") or []
        start = min(self._seen, len(messages))
        prefix = json.dumps(messages[:start], default=str, sort_keys=True)
        entries = []
        for i, msg in enumerate(messages[start:], start):
            raw = msg.get("content") if isinstance(msg, dict) else msg
            text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
            entry: dict[str, Any] = {
                "i": i,
                "role": msg.get("role") if isinstance(msg, dict) else None,
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "head": text[:HEAD_CHARS],
            }
            if len(text) > HEAD_CHARS:
                entry["head_truncated"] = True
            if isinstance(msg, dict) and msg.get("tool_call_id"):
                entry["tool_call_id"] = msg["tool_call_id"]
            if isinstance(msg, dict) and msg.get("tool_calls"):
                entry["tool_calls"] = len(msg["tool_calls"])
            entries.append(entry)
        self._seen = len(messages)
        return {
            "n_messages": len(messages),
            "new_from": start,
            "prefix_sha256": hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:16],
            "tools": len(body.get("tools") or []),
            "params": {k: v for k, v in body.items() if k not in ("messages", "tools")},
            "messages": entries,
        }

    def to_dict(self) -> dict[str, Any]:
        record = {
            "correlation_id": self.cid,
            "started_at": self.started_at,
            "duration_ms": round((time.monotonic() - self._t0) * 1000, 1),
            "bodies_captured": CAPTURE_BODIES,
            # Derived from completed spans so this count cannot drift from the record.
            "tool_calls": sum(1 for s in self._spans if s.get("name") == "tool.completed"),
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
        # Spans go first: the captured bodies are the opt-in evidence, so they stay
        # whenever they fit on their own.
        thin = {k: v for k, v in record.items() if k != "spans"}
        thin["truncated"] = True
        thin["spans"] = []
        payload = json.dumps(thin, default=str, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_RECORD_BYTES:
            thin.pop("bodies", None)
            thin["bodies_dropped"] = True
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


_FIELDS = (
    "prefill_s",
    "ttft_s",
    "reasoning_tokens",
    "reasoning_s",
    "answer_tokens",
    "answer_s",
    "answer_tps",
    "tool_s",
    "total_s",
    "timing_source",
)
_ADDITIVE = (
    "prefill_s",
    "reasoning_tokens",
    "reasoning_s",
    "answer_tokens",
    "answer_s",
    "tool_s",
    "total_s",
)
_CURRENT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "portal_timings", default=None
)


def _empty() -> dict[str, Any]:
    return {name: (0 if name == "tool_s" else None) for name in _FIELDS}


def _blank() -> dict[str, Any]:
    return dict.fromkeys(_FIELDS)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _finish(values: dict[str, Any]) -> dict[str, Any]:
    out = {name: values.get(name) for name in _FIELDS}
    if out.get("timing_source") not in ("engine", "measured"):
        out["timing_source"] = "measured"
    answer_s, answer_tokens = out.get("answer_s"), out.get("answer_tokens")
    out["answer_tps"] = (
        round(answer_tokens / answer_s, 3)
        if isinstance(answer_s, int | float)
        and answer_s > 0
        and isinstance(answer_tokens, int | float)
        else None
    )
    for name in _ADDITIVE:
        if out.get(name) is not None:
            out[name] = round(out[name], 6) if name.endswith("_s") else int(out[name])
    for name in ("ttft_s",):
        if out.get(name) is not None:
            out[name] = round(out[name], 6)
    return out


def _explicit_timings(data: dict[str, Any]) -> dict[str, Any]:
    explicit = data.get("portal_timings")
    values = _blank()
    if not isinstance(explicit, dict):
        return values
    for name in _FIELDS:
        value = explicit.get(name)
        if name in ("reasoning_tokens", "answer_tokens"):
            values[name] = _int(value) if value is not None else None
        elif name not in ("timing_source", "answer_tps"):
            values[name] = _number(value) if value is not None else None
    values["timing_source"] = explicit.get("timing_source")
    return values


def _engine_timings(data: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    prompt_duration = _number(usage.get("prompt_eval_duration"))
    if prompt_duration is None:
        prompt_ns = _number(
            data.get("prompt_eval_duration") or usage.get("prompt_eval_duration_ns")
        )
        prompt_duration = prompt_ns / 1_000_000_000 if prompt_ns is not None else None

    generation_duration = _number(
        usage.get("generation_duration") or data.get("generation_duration")
    )
    eval_ns = _number(data.get("eval_duration") or usage.get("eval_duration"))
    if generation_duration is None and eval_ns is not None:
        generation_duration = eval_ns / 1_000_000_000

    total_duration = _number(usage.get("total_time") or data.get("total_time"))
    if total_duration is None and prompt_duration is not None and generation_duration is not None:
        total_duration = prompt_duration + generation_duration
    ttft = _number(usage.get("time_to_first_token") or data.get("time_to_first_token"))
    completion_tokens = _int(
        next(
            (
                value
                for value in (
                    usage.get("completion_tokens"),
                    data.get("eval_count"),
                    usage.get("eval_count"),
                )
                if value is not None
            ),
            None,
        )
    )
    completion_details = usage.get("completion_tokens_details") or {}
    return {
        "prefill_s": prompt_duration,
        "generation_s": generation_duration,
        "total_s": total_duration,
        "ttft_s": ttft,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": _int(completion_details.get("reasoning_tokens")),
        "has_timing": any(
            value is not None
            for value in (prompt_duration, generation_duration, total_duration, ttft)
        ),
    }


def _content_phases(data: dict[str, Any], measured: dict[str, Any]) -> tuple[bool, bool]:
    choices = data.get("choices") or []
    message = choices[0].get("message") or {} if choices and isinstance(choices[0], dict) else {}
    native = data.get("message") if isinstance(data.get("message"), dict) else {}
    has_reasoning = any(
        message.get(name) or native.get(name)
        for name in ("reasoning", "reasoning_content", "thinking")
    ) or bool(_int(measured.get("reasoning_tokens")))
    has_answer = bool(
        message.get("content") or native.get("content") or _int(measured.get("answer_tokens"))
    )
    return has_reasoning, has_answer


def _answer_token_count(
    engine: dict[str, Any], measured: dict[str, Any], has_reasoning: bool, has_answer: bool
) -> int | None:
    total = engine["completion_tokens"]
    reasoning = engine["reasoning_tokens"]
    measured_reasoning = _int(measured.get("reasoning_tokens"))
    if not has_answer:
        return _int(measured.get("answer_tokens"))
    if reasoning is not None and total is not None:
        return max(0, total - reasoning)
    if total is not None and has_reasoning and measured_reasoning is not None:
        return max(0, total - measured_reasoning)
    if total is not None and not has_reasoning and has_answer:
        return total
    return _int(measured.get("answer_tokens"))


def _answer_duration(
    values: dict[str, Any],
    engine: dict[str, Any],
    measured: dict[str, Any],
    has_reasoning: bool,
    has_answer: bool,
) -> float | None:
    generation_s = engine["generation_s"]
    if (
        generation_s is not None
        and has_answer
        and (not has_reasoning or values.get("reasoning_s") is not None)
    ):
        return max(0.0, generation_s - (_number(values.get("reasoning_s")) or 0.0))
    return _number(measured.get("answer_s"))


def normalize_engine_timings(
    data: dict[str, Any], measured: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Map Ollama-native, oMLX OpenAI, and Portal timing shapes to one object."""
    measured = measured or {}
    values = _explicit_timings(data)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    engine = _engine_timings(data, usage)
    has_reasoning, has_answer = _content_phases(data, measured)

    for name in ("prefill_s", "ttft_s", "total_s"):
        if values.get(name) is None:
            values[name] = engine[name]
        if values.get(name) is None:
            values[name] = _number(measured.get(name))
    if values.get("reasoning_tokens") is None:
        values["reasoning_tokens"] = engine["reasoning_tokens"]
        if values["reasoning_tokens"] is None:
            values["reasoning_tokens"] = _int(measured.get("reasoning_tokens"))
    if values.get("answer_tokens") is None:
        values["answer_tokens"] = _answer_token_count(engine, measured, has_reasoning, has_answer)
    if values.get("reasoning_s") is None:
        values["reasoning_s"] = _number(measured.get("reasoning_s"))
    if values.get("answer_s") is None:
        values["answer_s"] = _answer_duration(values, engine, measured, has_reasoning, has_answer)
    if measured.get("tool_s") is not None:
        values["tool_s"] = _number(measured.get("tool_s"))
    if values.get("reasoning_tokens") is None and not has_reasoning and has_answer:
        values["reasoning_tokens"] = 0
    if values.get("timing_source") not in ("engine", "measured"):
        values["timing_source"] = "engine" if engine["has_timing"] else "measured"
    return _finish(values)


def usage_metric_kwargs(
    data: dict[str, Any], measured: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build per-model-call timing kwargs for ``power._record_usage``.

    Engine generation duration wins for decode time. Otherwise a streamed
    measurement supplies decode time as request-to-last-token minus TTFT; the
    non-streaming caller deliberately does not pass wall time as decode time.
    Tool dispatch is never included because this input describes one model call.
    """
    measured = measured or {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    engine = _engine_timings(data, usage)
    timings = normalize_engine_timings(data, measured)
    decode_seconds = engine["generation_s"]
    if (
        decode_seconds is None
        and "ttft_s" in measured
        and ("answer_s" in measured or "reasoning_s" in measured)
    ):
        total_s = _number(measured.get("total_s"))
        ttft_s = _number(measured.get("ttft_s"))
        if total_s is not None and ttft_s is not None:
            decode_seconds = max(0.0, total_s - ttft_s)
    return {
        "decode_seconds": decode_seconds,
        "ttft_seconds": timings.get("ttft_s"),
        "reasoning_tokens": timings.get("reasoning_tokens"),
        "answer_seconds": timings.get("answer_s"),
        "answer_tokens": timings.get("answer_tokens"),
    }


def start_timings() -> None:
    """Start a fresh timing rollup for the current pipeline request."""
    _CURRENT.set(_empty())


def current_portal_timings() -> dict[str, Any]:
    """Return a stable copy of the request timing rollup."""
    current = _CURRENT.get()
    return _finish(dict(current)) if current is not None else _finish(_empty())


def add_model_turn(data: dict[str, Any], measured: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize and add one engine call to the current request rollup."""
    turn = normalize_engine_timings(data, measured)
    current = _CURRENT.get()
    if current is None:
        current = _empty()
        _CURRENT.set(current)
    for name in _ADDITIVE:
        value = turn.get(name)
        if value is not None:
            current[name] = (current.get(name) or 0) + value
    if current.get("ttft_s") is None and turn.get("ttft_s") is not None:
        current["ttft_s"] = turn["ttft_s"]
    if turn.get("timing_source") == "measured" or (
        current.get("timing_source") == "engine" and turn.get("timing_source") == "engine"
    ):
        current["timing_source"] = turn["timing_source"]
    elif turn.get("timing_source") == "engine" and current.get("timing_source") is None:
        current["timing_source"] = "engine"
    return current_portal_timings()


def add_tool_time(seconds: float) -> dict[str, Any]:
    """Add elapsed tool dispatch time; it remains separate from model total_s."""
    current = _CURRENT.get()
    if current is None:
        current = _empty()
        _CURRENT.set(current)
    current["tool_s"] = (current.get("tool_s") or 0) + max(0.0, seconds)
    return current_portal_timings()


class StreamMeasurement:
    """Observe response events while preserving their original SSE payloads."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.first_any: float | None = None
        self.first_reasoning: float | None = None
        self.first_answer: float | None = None
        self.last_reasoning: float | None = None
        self.last_answer: float | None = None
        self.last_any: float | None = None
        self.reasoning_tokens = 0
        self.answer_tokens = 0
        self.saw_tool_calls = False
        self.finish_reason: str | None = None
        self.engine_data: dict[str, Any] = {}

    def observe(
        self,
        frame: dict[str, Any],
        *,
        visible_content: str | None = None,
        content_override: bool = False,
        inline_reasoning: bool = False,
    ) -> None:
        if isinstance(frame.get("portal_timings"), dict):
            self.engine_data["portal_timings"] = frame["portal_timings"]
        if isinstance(frame.get("usage"), dict):
            self.engine_data["usage"] = frame["usage"]
        elif any(k in frame for k in ("eval_count", "eval_duration", "prompt_eval_duration")):
            self.engine_data.update(frame)
        choices = frame.get("choices") or []
        if choices:
            choice = choices[0] if isinstance(choices[0], dict) else {}
            delta = choice.get("delta") or {}
        else:
            message = frame.get("message") or {}
            if not message:
                return
            choice = {"finish_reason": "tool_calls" if message.get("tool_calls") else None}
            delta = {
                "content": message.get("content"),
                "reasoning": message.get("thinking"),
                "tool_calls": message.get("tool_calls"),
            }
        if choice.get("finish_reason"):
            self.finish_reason = str(choice["finish_reason"])
        now = time.monotonic()
        reasoning = next(
            (delta.get(k) for k in ("reasoning", "reasoning_content", "thinking") if delta.get(k)),
            "inline" if inline_reasoning else None,
        )
        answer = visible_content if content_override else delta.get("content")
        tool_calls = delta.get("tool_calls")
        self.saw_tool_calls = self.saw_tool_calls or bool(tool_calls)
        if not (reasoning or answer or tool_calls):
            return
        self.first_any = self.first_any or now
        self.last_any = now
        if reasoning:
            self.first_reasoning = self.first_reasoning or now
            self.last_reasoning = now
            self.reasoning_tokens += 1
        if answer:
            self.first_answer = self.first_answer or now
            self.last_answer = now
            self.answer_tokens += 1

    def result(self) -> dict[str, Any]:
        end = self.last_any or time.monotonic()
        ttft = self.first_any - self.started if self.first_any is not None else None
        total = end - self.started if self.first_any is not None else None
        reasoning_end = self.first_answer or self.last_reasoning
        reasoning_s = (
            max(0.0, reasoning_end - self.first_reasoning)
            if self.first_reasoning is not None and reasoning_end is not None
            else None
        )
        answer_s = (
            max(0.0, self.last_answer - self.first_answer)
            if self.first_answer is not None
            and self.last_answer is not None
            and self.finish_reason != "tool_calls"
            else None
        )
        answer_tokens = (
            0 if self.saw_tool_calls or self.finish_reason == "tool_calls" else self.answer_tokens
        )
        if answer_s == 0 and total is not None and answer_tokens:
            answer_s = max(0.0, total - (ttft or 0.0) - (reasoning_s or 0.0))
        return {
            "prefill_s": ttft,
            "ttft_s": ttft,
            "reasoning_tokens": self.reasoning_tokens,
            "reasoning_s": reasoning_s,
            "answer_tokens": answer_tokens,
            "answer_s": answer_s,
            "total_s": total,
        }
