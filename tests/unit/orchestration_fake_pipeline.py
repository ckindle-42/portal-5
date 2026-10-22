"""Fake OpenAI-compatible Pipeline API for offline orchestration tests."""

from __future__ import annotations

import json
import os
import queue
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class SignalResponse:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response


class DelayedResponse:
    def __init__(self, response: dict[str, Any], delay: float) -> None:
        self.response = response
        self.delay = delay


class FakePipeline:
    """One fake Pipeline port for both seats, chat, and load-plan requests."""

    def __init__(self) -> None:
        self.responses: dict[str, queue.Queue[Any]] = {
            "auto-daily::fast": queue.Queue(),
            "auto-daily::deep": queue.Queue(),
        }
        self.admin_responses: queue.Queue[Any] = queue.Queue()
        self.requests: list[dict[str, Any]] = []
        self.admin_requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
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
                with owner._lock:
                    owner.requests.append(body)
                try:
                    response = owner.responses[model].get_nowait()
                except (KeyError, queue.Empty):
                    response = text_response("no finish call")
                if response == "HTTP_500":
                    self.send_error(500, "fake Pipeline failure")
                    return
                if isinstance(response, SignalResponse):
                    os.kill(os.getpid(), signal.SIGTERM)
                    time.sleep(0.2)
                    response = response.response
                if isinstance(response, DelayedResponse):
                    time.sleep(response.delay)
                    response = response.response
                try:
                    _sse_response(self, response)
                except BrokenPipeError:
                    return

            def log_message(self, format: str, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def add(self, seat: str, response: Any) -> None:
        self.responses[f"auto-daily::{seat}"].put(response)

    def add_admin_response(self, response: dict[str, Any]) -> None:
        self.admin_responses.put(response)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def finish_response(output: Any, *, path: str | None = None, tokens: int = 4) -> dict[str, Any]:
    args = {"output": output}
    if path is not None:
        args["output_path"] = path
    return tool_response("finish", json.dumps(args), tokens=tokens)


def tool_response(name: str, arguments: str, *, tokens: int = 4) -> dict[str, Any]:
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
        "usage": {"completion_tokens": tokens},
    }


def text_response(content: str, *, tokens: int = 4) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content, "tool_calls": []},
                "finish_reason": "stop",
            }
        ],
        "usage": {"completion_tokens": tokens},
    }


def _json_response(handler: BaseHTTPRequestHandler, value: dict[str, Any]) -> None:
    payload = json.dumps(value).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _sse_response(handler: BaseHTTPRequestHandler, response: dict[str, Any]) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    choice = response["choices"][0]
    message = choice["message"]
    if message.get("content"):
        _event(handler, {"choices": [{"delta": {"content": message["content"]}}]})
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call["function"]
        _event(
            handler,
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": index,
                                    "id": call["id"],
                                    "type": call["type"],
                                    "function": {"name": function["name"]},
                                }
                            ]
                        }
                    }
                ]
            },
        )
        _event(
            handler,
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": index, "function": {"arguments": function["arguments"]}}
                            ]
                        }
                    }
                ]
            },
        )
    _event(handler, {"choices": [{"delta": {}, "finish_reason": choice["finish_reason"]}]})
    _event(handler, {"choices": [], "usage": response.get("usage", {})})
    handler.wfile.write(b"data: [DONE]\n\n")
    handler.wfile.flush()


def _event(handler: BaseHTTPRequestHandler, value: dict[str, Any]) -> None:
    handler.wfile.write(f"data: {json.dumps(value)}\n\n".encode())
    handler.wfile.flush()
