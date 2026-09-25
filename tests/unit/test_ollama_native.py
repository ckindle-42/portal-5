"""OllamaNativeTransport — OpenAI /v1 surface served from Ollama /api/chat.

Ollama's /v1 drops `options` and top_k/min_p/repeat_penalty (measured
2026-09-25, Ollama 0.34.2), so Ollama-served workspaces never received their
sampling. These tests pin the translation both ways and the pass-through rules;
live parity against /v1 (content, tool calls, prompt_tokens) was verified on
the same date.
"""

from __future__ import annotations

import json

import httpx
import pytest

from portal.platform.inference.ollama_native import (
    OllamaNativeTransport,
    messages_to_native,
    to_native_request,
    to_openai_completion,
)

BASE = "http://ollama:11434"


def test_sampling_reaches_native_options_and_load_options_do_not():
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.2,
        "max_tokens": 99,
        "options": {"top_k": 40, "repeat_penalty": 1.05, "num_ctx": 32768, "num_batch": 2048},
    }
    native = to_native_request(body, can_think=False)
    assert native["options"] == {
        "temperature": 0.2,
        "top_k": 40,
        "repeat_penalty": 1.05,
        "num_predict": 99,
    }
    # load-time options would reload a resident model on any mismatch
    assert "num_ctx" not in native["options"] and "num_batch" not in native["options"]
    assert native["stream"] is False


def test_keep_alive_not_forwarded():
    """/v1 never delivered keep_alive; the pipeline's -1 default would pin models
    oMLX cannot reclaim (and the bare "-1" string 400s on /api/chat)."""
    native = to_native_request({"model": "m", "messages": [], "keep_alive": "-1"}, False)
    assert "keep_alive" not in native


def test_think_only_sent_to_thinking_capable_models():
    body = {"model": "m", "messages": [], "think": True}
    assert to_native_request(body, can_think=True)["think"] is True
    assert "think" not in to_native_request(body, can_think=False)
    effort_none = {"model": "m", "messages": [], "reasoning_effort": "none"}
    assert to_native_request(effort_none, can_think=True)["think"] is False


def test_messages_tool_round_trip_and_content_parts():
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "reasoning": "thinking...",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"a":1}'}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    out = messages_to_native(msgs)
    # /v1 splits a parts list into one message per part — parity target
    assert out[0] == {"role": "user", "content": "what is this"}
    assert out[1] == {"role": "user", "content": "", "images": ["QUJD"]}
    assert out[2]["tool_calls"] == [{"function": {"name": "f", "arguments": {"a": 1}}, "id": "c1"}]
    assert out[2]["thinking"] == "thinking..."
    assert out[3] == {"role": "tool", "content": "ok", "tool_call_id": "c1", "tool_name": "f"}


def test_completion_shape_matches_v1():
    native = {
        "model": "m",
        "message": {
            "role": "assistant",
            "content": "",
            "thinking": "hmm",
            "tool_calls": [{"id": "x", "function": {"name": "f", "arguments": {"a": 1}}}],
        },
        "done_reason": "stop",
        "prompt_eval_count": 10,
        "eval_count": 5,
    }
    out = to_openai_completion(native)
    ch = out["choices"][0]
    assert ch["finish_reason"] == "tool_calls"
    assert ch["message"]["reasoning"] == "hmm"
    assert ch["message"]["tool_calls"][0]["function"]["arguments"] == '{"a":1}'
    assert out["usage"]["total_tokens"] == 15


def _mock(handler):
    seen: list[httpx.Request] = []

    def wrap(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    t = OllamaNativeTransport(httpx.MockTransport(wrap), is_ollama=lambda b: b == BASE)
    return httpx.AsyncClient(transport=t), seen


def _show(req):
    return httpx.Response(200, json={"capabilities": ["completion", "tools", "thinking"]})


@pytest.mark.asyncio
async def test_stream_translated_to_v1_sse():
    ndjson = "\n".join(
        json.dumps(x)
        for x in [
            {"model": "m", "message": {"role": "assistant", "content": "", "thinking": "t"}},
            {"model": "m", "message": {"role": "assistant", "content": "Hel"}},
            {"model": "m", "message": {"role": "assistant", "content": "lo"}},
            {
                "model": "m",
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 3,
                "eval_count": 2,
            },
        ]
    )

    def handler(req):
        if req.url.path == "/api/show":
            return _show(req)
        assert req.url.path == "/api/chat"
        sent = json.loads(req.content)
        assert sent["options"]["top_k"] == 20 and sent["think"] is True
        return httpx.Response(200, content=ndjson.encode())

    client, _ = _mock(handler)
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": "x"}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "think": True,
        "options": {"top_k": 20},
    }
    chunks = []
    async with client.stream("POST", f"{BASE}/v1/chat/completions", json=body) as r:
        assert r.headers["content-type"] == "text/event-stream"
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])
    assert chunks[-1] == "[DONE]"
    objs = [json.loads(c) for c in chunks[:-1]]
    assert objs[0]["choices"][0]["delta"]["role"] == "assistant"
    assert objs[0]["choices"][0]["delta"]["reasoning"] == "t"
    text = "".join(o["choices"][0]["delta"].get("content", "") for o in objs if o["choices"])
    assert text == "Hello"
    assert [o["choices"][0]["finish_reason"] for o in objs if o["choices"]][-1] == "stop"
    assert objs[-1]["usage"]["prompt_tokens"] == 3


@pytest.mark.asyncio
async def test_non_ollama_and_non_chat_requests_pass_through():
    def handler(req):
        return httpx.Response(200, json={"path": req.url.path})

    client, seen = _mock(handler)
    r = await client.post("http://omlx:8085/v1/chat/completions", json={"model": "m"})
    assert r.json() == {"path": "/v1/chat/completions"}
    r = await client.get(f"{BASE}/api/tags")
    assert r.json() == {"path": "/api/tags"}
    assert [s.url.path for s in seen] == ["/v1/chat/completions", "/api/tags"]


@pytest.mark.asyncio
async def test_error_reshaped_like_v1():
    def handler(req):
        if req.url.path == "/api/show":
            return httpx.Response(404, json={"error": "model 'x' not found"})
        return httpx.Response(404, json={"error": "model 'x' not found"})

    client, _ = _mock(handler)
    r = await client.post(f"{BASE}/v1/chat/completions", json={"model": "x", "messages": []})
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "not_found_error"


@pytest.mark.asyncio
async def test_non_thinking_model_never_gets_think():
    def handler(req):
        if req.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        assert "think" not in json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "model": "g",
                "message": {"role": "assistant", "content": "hi"},
                "done": True,
                "done_reason": "stop",
            },
        )

    client, _ = _mock(handler)
    r = await client.post(
        f"{BASE}/v1/chat/completions",
        json={"model": "g", "messages": [], "reasoning_effort": "none"},
    )
    assert r.json()["choices"][0]["message"]["content"] == "hi"
