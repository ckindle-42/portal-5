"""Pipeline-backed model transport for the grounded security reader.

All model calls use Portal's streamed public chat API. The router keeps the call
inside its load guard and maps the two native reasoning controls: ``think`` for
Ollama and ``chat_template_kwargs.enable_thinking`` for oMLX. The client sends
both affirmative forms because a workspace may fail over between those engines.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from portal.platform.inference.model_addressing import (
    alias_targets_for_model,
    is_addressable,
    workspace_id_for_model,
    workspace_model_hint,
)
from portal.platform.inference.streaming_client import (
    StreamTurnCancelledError,
    StreamTurnStalledError,
    stream_chat_turn,
)

from .judge import ModelClient, ModelReply

MAX_ATTEMPTS = 2
CONNECT_TIMEOUT_S = 10.0
STREAM_IDLE_TIMEOUT_S = 300.0
TRACE_TIMEOUT_S = 3.0
CATALOG_TIMEOUT_S = 3.0
REASONING_PROBE_MAX_TOKENS = 128
CORRELATION_ID_HEX_CHARS = 16

_DEFAULT_PIPELINE_URL = "http://127.0.0.1:9099"
_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "review_reader_deadline", default=None
)
_StreamFn = Callable[..., dict[str, Any]]
_TraceFn = Callable[[str], Mapping[str, Any]]
_DigestFn = Callable[[str, str, str], tuple[str, str]]


def _setting(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    env_file = _REPO_ROOT / ".env"
    if not env_file.is_file():
        return default
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(f"{name}="):
            return line.partition("=")[2].strip().strip("\"'") or default
    return default


def _default_base_url() -> str:
    explicit = os.environ.get("PORTAL_REVIEW_PIPELINE_URL")
    if explicit:
        return explicit.rstrip("/")
    configured = os.environ.get("PIPELINE_URL")
    if configured:
        host = urlsplit(configured).hostname
        if Path("/.dockerenv").exists() or host not in {"portal-pipeline", "portal_pipeline"}:
            return configured.rstrip("/")
    return _DEFAULT_PIPELINE_URL


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CallReceipt:
    model: str
    workspace: str
    backend: str
    served_model: str
    model_digest: str
    digest_source: str
    latency_ms: float
    attempts: int
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_chars: int
    structured_output: bool
    trace_available: bool
    error: str = ""


class PortalModelClient(ModelClient):
    """``judge.ModelClient`` implementation over the shared Portal pipeline."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        omlx_api_key: str | None = None,
        ollama_url: str | None = None,
        omlx_url: str | None = None,
        streamer: _StreamFn = stream_chat_turn,
        trace_reader: _TraceFn | None = None,
        digest_resolver: _DigestFn | None = None,
    ) -> None:
        self.base_url = (base_url or _default_base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else _setting("PIPELINE_API_KEY")
        in_container = Path("/.dockerenv").exists()
        self.ollama_url = (
            ollama_url
            or os.environ.get("PORTAL_REVIEW_OLLAMA_URL")
            or (os.environ.get("OLLAMA_URL") if in_container else None)
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        self.omlx_url = (
            omlx_url
            or os.environ.get("PORTAL_REVIEW_OMLX_URL")
            or (os.environ.get("OMLX_URL") if in_container else None)
            or "http://127.0.0.1:8085"
        ).rstrip("/")
        self.omlx_api_key = omlx_api_key if omlx_api_key is not None else _setting("OMLX_API_KEY")
        self.endpoint = f"{self.base_url}/v1/chat/completions"
        self._streamer = streamer
        self._trace_reader = trace_reader or self._fetch_turn_trace
        self._digest_resolver = digest_resolver or self._resolve_digest
        self._receipts: list[CallReceipt] = []
        self._receipt_lock = threading.Lock()
        self._verified_reasoning: set[str] = set()
        self._verification_lock = threading.Lock()
        self._ollama_tags: dict[str, str] | None = None
        self._omlx_catalog: dict[str, dict[str, Any]] | None = None
        self._catalog_lock = threading.Lock()

    @property
    def call_receipts(self) -> tuple[CallReceipt, ...]:
        with self._receipt_lock:
            return tuple(self._receipts)

    def mark_reasoning_probe(self, model: str, passed: bool) -> None:
        with self._verification_lock:
            if passed:
                self._verified_reasoning.add(model)
            else:
                self._verified_reasoning.discard(model)

    def reasoning_verified(self, model: str) -> bool:
        with self._verification_lock:
            return model in self._verified_reasoning

    @contextmanager
    def concern_deadline(self, timeout_s: float) -> Iterator[None]:
        token = _DEADLINE.set(time.monotonic() + timeout_s)
        try:
            yield
        finally:
            _DEADLINE.reset(token)

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str,
        schema: Mapping[str, Any] | None,
        max_tokens: int,
        think: bool,
    ) -> ModelReply:
        if think is not True:
            raise ValueError("the grounded reader requires reasoning on for every model call")
        requested_hint = workspace_model_hint(model) or model
        if not is_addressable(model) and not is_addressable(requested_hint):
            raise ValueError(f"model {model!r} is not addressable through a Portal workspace")
        workspace = workspace_id_for_model(requested_hint)
        if not is_addressable(workspace):
            raise ValueError(f"model {model!r} resolves to an unaddressable workspace")
        hint = workspace_model_hint(workspace) or requested_hint
        expected_models = {hint, *alias_targets_for_model(hint)}
        payload = self._build_payload(workspace, messages, schema, max_tokens)
        correlation_id = f"review-{uuid.uuid4().hex[:CORRELATION_ID_HEX_CHARS]}"
        headers = {"Accept": "text/event-stream", "X-Correlation-ID": correlation_id}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        message, attempts, elapsed_ms, error = self._send(payload, headers, expected_models)
        trace = self._trace_reader(correlation_id) if message is not None else {}
        backend = str(trace.get("backend") or "")
        served_model = str(trace.get("model") or (message or {}).get("served_model") or "")
        model_digest, digest_source = (
            self._digest_resolver(backend, served_model, hint)
            if message is not None
            else ("", "unavailable")
        )
        usage = (message or {}).get("usage") or {}
        receipt = CallReceipt(
            model=model,
            workspace=workspace,
            backend=backend,
            served_model=served_model,
            model_digest=model_digest,
            digest_source=digest_source,
            latency_ms=elapsed_ms,
            attempts=attempts,
            prompt_tokens=_optional_int(usage.get("prompt_tokens") or usage.get("input_tokens")),
            completion_tokens=_optional_int(
                usage.get("completion_tokens") or usage.get("output_tokens")
            ),
            reasoning_chars=len(str((message or {}).get("reasoning_content") or "")),
            structured_output=schema is not None,
            trace_available=bool(trace),
            error=error,
        )
        with self._receipt_lock:
            self._receipts.append(receipt)
        if message is None:
            return ModelReply(text="", error=error or "ModelTransportError")
        return ModelReply(
            text=str(message.get("content") or ""),
            reasoning=str(message.get("reasoning_content") or ""),
        )

    @staticmethod
    def _build_payload(
        workspace: str,
        messages: Sequence[Mapping[str, str]],
        schema: Mapping[str, Any] | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": workspace,
            "messages": [dict(message) for message in messages],
            "max_tokens": max_tokens,
            "think": True,
            "chat_template_kwargs": {"enable_thinking": True},
            "portal_no_tools": True,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "portal_review", "schema": dict(schema)},
            }
        return payload

    def _send(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        expected_models: set[str],
    ) -> tuple[dict[str, Any] | None, int, float, str]:
        cancel_event = threading.Event()
        deadline = _DEADLINE.get()
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            return None, 0, 0.0, "ConcernTimeout"
        timeout_s = (
            STREAM_IDLE_TIMEOUT_S if remaining is None else min(STREAM_IDLE_TIMEOUT_S, remaining)
        )
        timer: threading.Timer | None = None
        if remaining is not None:
            timer = threading.Timer(remaining, cancel_event.set)
            timer.daemon = True
            timer.start()

        started = time.monotonic()
        attempts = 0
        message: dict[str, Any] | None = None
        error = ""
        try:
            for attempt_index in range(MAX_ATTEMPTS):
                attempts = attempt_index + 1
                try:
                    message = self._streamer(
                        self.endpoint,
                        headers,
                        payload,
                        is_pipeline_mode=True,
                        idle_timeout_s=timeout_s,
                        connect_timeout_s=min(CONNECT_TIMEOUT_S, timeout_s),
                        expected_model_hint=expected_models,
                        should_cancel=cancel_event.is_set,
                    )
                    error = ""
                    break
                except StreamTurnCancelledError:
                    error = "ConcernTimeout" if deadline is not None else "StreamCancelled"
                    break
                except (httpx.TransportError, StreamTurnStalledError) as exc:
                    error = type(exc).__name__
                    if attempts >= MAX_ATTEMPTS or cancel_event.is_set():
                        break
                except Exception as exc:  # server errors and routing failures are not retried
                    error = type(exc).__name__
                    break
        finally:
            if timer is not None:
                timer.cancel()
        elapsed_ms = (time.monotonic() - started) * 1000
        return message, attempts, elapsed_ms, error

    def _fetch_turn_trace(self, correlation_id: str) -> Mapping[str, Any]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            response = httpx.get(
                f"{self.base_url}/v1/trace/{correlation_id}",
                headers=headers,
                timeout=TRACE_TIMEOUT_S,
            )
            if response.is_success:
                body = response.json()
                return body if isinstance(body, Mapping) else {}
        except (httpx.HTTPError, ValueError):
            return {}
        return {}

    def _load_ollama_tags(self) -> dict[str, str]:
        with self._catalog_lock:
            if self._ollama_tags is not None:
                return self._ollama_tags
            try:
                response = httpx.get(f"{self.ollama_url}/api/tags", timeout=CATALOG_TIMEOUT_S)
                response.raise_for_status()
                rows = response.json().get("models") or []
                self._ollama_tags = {
                    str(row.get("name") or row.get("model")): str(row.get("digest") or "")
                    for row in rows
                    if isinstance(row, Mapping)
                }
            except (httpx.HTTPError, ValueError):
                self._ollama_tags = {}
            return self._ollama_tags

    def _load_omlx_catalog(self) -> dict[str, dict[str, Any]]:
        with self._catalog_lock:
            if self._omlx_catalog is not None:
                return self._omlx_catalog
            headers = {"Authorization": f"Bearer {self.omlx_api_key}"} if self.omlx_api_key else {}
            try:
                response = httpx.get(
                    f"{self.omlx_url}/v1/models", headers=headers, timeout=CATALOG_TIMEOUT_S
                )
                response.raise_for_status()
                rows = response.json().get("data") or []
                self._omlx_catalog = {
                    str(row.get("id")): dict(row)
                    for row in rows
                    if isinstance(row, Mapping) and row.get("id")
                }
            except (httpx.HTTPError, ValueError):
                self._omlx_catalog = {}
            return self._omlx_catalog

    def _resolve_digest(self, backend: str, served_model: str, hint: str) -> tuple[str, str]:
        if "omlx" in backend.lower() or served_model in self._load_omlx_catalog():
            row = self._load_omlx_catalog().get(served_model)
            if row:
                digest = hashlib.sha256(
                    json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                return digest, "omlx_catalog_identity_sha256"
        tags = self._load_ollama_tags()
        for candidate in (served_model, hint):
            if candidate in tags and tags[candidate]:
                return tags[candidate], "ollama_artifact_digest"
        identity = json.dumps(
            {"backend": backend, "served_model": served_model, "hint": hint},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest(), "route_identity_sha256"


def probe_reasoning(client: PortalModelClient, model: str) -> dict[str, Any]:
    """Probe a model with a harmless arithmetic task; persist only capability metrics."""
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "integer"}, "explanation": {"type": "string"}},
        "required": ["answer", "explanation"],
    }
    before = len(client.call_receipts)
    reply = client.complete(
        [
            {
                "role": "system",
                "content": "Return one JSON object with answer and a short explanation.",
            },
            {"role": "user", "content": "Compute 19 + 23. The answer is a small integer."},
        ],
        model=model,
        schema=schema,
        max_tokens=REASONING_PROBE_MAX_TOKENS,
        think=True,
    )
    receipts = client.call_receipts[before:]
    receipt = receipts[-1] if receipts else None
    passed = not reply.error and bool(reply.reasoning.strip())
    client.mark_reasoning_probe(model, passed)
    return {
        "model": model,
        "reasoning_produced": passed,
        "reasoning_chars": len(reply.reasoning),
        "latency_ms": receipt.latency_ms if receipt else None,
        "attempts": receipt.attempts if receipt else 0,
        "prompt_tokens": receipt.prompt_tokens if receipt else None,
        "completion_tokens": receipt.completion_tokens if receipt else None,
        "model_digest": receipt.model_digest if receipt else "",
        "digest_source": receipt.digest_source if receipt else "unavailable",
        "backend": receipt.backend if receipt else "",
        "served_model": receipt.served_model if receipt else "",
        "error": receipt.error if receipt else reply.error,
    }
