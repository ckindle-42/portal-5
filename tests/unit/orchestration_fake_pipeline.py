"""Fake OpenAI-compatible Pipeline API for offline orchestration tests.

The fake scripts the ENGINE, not the pipeline's decisions: bearer auth is the
production ``_verify_key``, the bite-tool allowlist decision is the production
``apply_bite_tool_scope``, and the SSE wire shape is the production converter
(``_json_completion_to_sse`` / ``_exec_audit_event``). There is no offline MCP
registry, so ``pipeline_tools=None`` assumes the pipeline owns exactly the
request's allowlisted names; pass a set to model a registry that lacks one and
watch the trace (and the runner's guard) report the missing tool. The fake
never forwards a usage chunk — the live pipeline does not either — so token
counts travel through the worker's estimate path, as in production.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from portal.modules.orchestration.service import load_arm_config, seated_model_tags
from portal.platform.inference.router import auth
from portal.platform.inference.router.eval_gate import apply_bite_tool_scope
from portal.platform.inference.router.streaming import (
    _exec_audit_event,
    _json_completion_to_sse,
)
from portal.platform.inference.router.thinking import _thinking_enabled

SEAT_TAGS = seated_model_tags(
    load_arm_config(Path(__file__).resolve().parents[2] / "config" / "orchestration_arm.yaml")
)


class SignalResponse:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response


class DelayedResponse:
    def __init__(
        self,
        response: dict[str, Any],
        delay: float,
        on_serve: Callable[[], object] | None = None,
    ) -> None:
        self.response = response
        self.delay = delay
        self.on_serve = on_serve


class _HttpError(Exception):
    """A scripted status response the handler turns into send_error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class FakePipeline:
    """One fake Pipeline port for both seats, chat, and load-plan requests."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        pipeline_tools: set[str] | None = None,
    ) -> None:
        self.api_key = auth.PIPELINE_API_KEY if api_key is None else api_key
        self._prior_api_key: str | None = None
        if api_key is not None:
            self._prior_api_key = auth.PIPELINE_API_KEY
            auth.PIPELINE_API_KEY = self.api_key
        self.pipeline_tools = pipeline_tools
        self.responses: dict[str, queue.Queue[Any]] = {
            SEAT_TAGS["fast"]: queue.Queue(),
            SEAT_TAGS["deep"]: queue.Queue(),
        }
        self.admin_responses: queue.Queue[Any] = queue.Queue()
        self.requests: list[dict[str, Any]] = []
        self.admin_requests: list[dict[str, Any]] = []
        self.traces: dict[str, dict[str, Any]] = {}
        self.offered_tools_override: list[str] | None = None
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                prefix = "/v1/trace/"
                if not self.path.startswith(prefix):
                    self.send_error(404)
                    return
                if not owner._authenticated(self):
                    return
                with owner._lock:
                    trace = owner.traces.get(self.path.removeprefix(prefix))
                if trace is None:
                    self.send_error(404)
                    return
                _json_response(self, trace)

            def do_POST(self) -> None:
                if not owner._authenticated(self):
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/admin/load-plan":
                    with owner._lock:
                        owner.admin_requests.append(body)
                    try:
                        response = owner.admin_responses.get_nowait()
                    except queue.Empty:
                        response = {"busy": False, "fits": True, "models": body["models"]}
                    _json_response(self, response)
                    return
                if self.path != "/v1/chat/completions":
                    self.send_error(404)
                    return
                model = body.get("model", "")
                correlation_id = self.headers.get("X-Correlation-ID", "")
                with owner._lock:
                    owner.requests.append({**body})
                    if correlation_id:
                        owner.traces[correlation_id] = {
                            "correlation_id": correlation_id,
                            "requested": model,
                            "workspace": model,
                            "persona": None,
                            "tools_offered": owner._tools_offered(body),
                            "backend": "fake",
                            "model": model,
                        }
                try:
                    response = owner._next_response(model)
                except _HttpError as exc:
                    self.send_error(exc.code, exc.message)
                    return
                try:
                    _sse_response(self, response, _thinking_enabled(body))
                except BrokenPipeError:
                    return

            def log_message(self, format: str, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def _authenticated(self, handler: BaseHTTPRequestHandler) -> bool:
        try:
            auth._verify_key(handler.headers.get("Authorization"))
        except HTTPException:
            handler.send_error(401, "invalid or missing API key")
            return False
        return True

    def _next_response(self, model: str) -> dict[str, Any]:
        """Pop the seat's scripted completion, resolving the response controls."""
        try:
            response = self.responses[model].get_nowait()
        except (KeyError, queue.Empty):
            return text_response("no finish call")
        if response == "HTTP_500":
            raise _HttpError(500, "fake Pipeline failure")
        if isinstance(response, SignalResponse):
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(0.2)
            return response.response
        if isinstance(response, DelayedResponse):
            if response.on_serve is not None:
                response.on_serve()
            time.sleep(response.delay)
            return response.response
        return response

    def _tools_offered(self, body: dict[str, Any]) -> list[str]:
        """The production bite gate over this fake's declared registry.

        ``offered_tools_override`` stays as fault injection for harness-error
        tests; everything else goes through apply_bite_tool_scope. The default
        registry (None) is the request's own allowlist — the assumption that
        the live registry carries every allowlisted name.
        """
        if self.offered_tools_override is not None:
            return self.offered_tools_override
        requested = body.get("portal_bite_tools")
        registry = (
            set(requested)
            if self.pipeline_tools is None and isinstance(requested, list)
            else (self.pipeline_tools or set())
        )
        schemas = body.get("tools")
        names = [
            tool.get("function", {}).get("name", "")
            for tool in (schemas or [])
            if isinstance(tool, dict)
        ]
        owned = sorted(registry | set(names))
        offered, _allowed = apply_bite_tool_scope(body, owned)
        return offered

    def add(self, seat: str, response: Any) -> None:
        self.responses[SEAT_TAGS[seat]].put(response)

    def add_model(self, model: str, response: Any) -> None:
        self.responses.setdefault(model, queue.Queue()).put(response)

    def add_admin_response(self, response: dict[str, Any]) -> None:
        self.admin_responses.put(response)

    def close(self) -> None:
        if self._prior_api_key is not None:
            auth.PIPELINE_API_KEY = self._prior_api_key
            self._prior_api_key = None
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def finish_response(output: Any, *, path: str | None = None) -> dict[str, Any]:
    args = {"output": output}
    if path is not None:
        args["output_path"] = path
    return tool_response("finish", json.dumps(args))


def tool_response(name: str, arguments: str) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"completion_tokens": 4},
    }


def text_response(
    content: str, *, exec_audit: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": content, "tool_calls": []},
                "finish_reason": "stop",
            }
        ],
        "usage": {"completion_tokens": 4},
    }
    if exec_audit is not None:
        response["exec_audit"] = exec_audit
    return response


def _json_response(handler: BaseHTTPRequestHandler, value: dict[str, Any]) -> None:
    payload = json.dumps(value).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _sse_response(
    handler: BaseHTTPRequestHandler, response: dict[str, Any], thinking: bool
) -> None:
    """Serve one completion through the production JSON-to-SSE converter.

    The exec_audit event rides after [DONE] here; the live pipeline emits it
    before the finish chunk. Every consumer of this fake merges events
    order-insensitively (worker _merge_event, SuiteEngine capture).
    """
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    for chunk in _json_completion_to_sse(response, "fake", thinking_enabled=thinking):
        handler.wfile.write(chunk)
    calls = response.get("exec_audit")
    if calls:
        handler.wfile.write(_exec_audit_event(calls))
