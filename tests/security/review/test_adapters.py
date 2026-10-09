from __future__ import annotations

import httpx

from portal.modules.security.core.review.judge import ModelReply
from portal.modules.security.core.review.model_client import PortalModelClient
from portal.platform.inference.model_addressing import alias_targets_for_model, workspace_model_hint


def test_portal_client_keeps_reasoning_separate_and_maps_both_engine_controls() -> None:
    calls: list[dict[str, object]] = []

    def stream(url: str, headers: dict[str, str], payload: dict[str, object], **kwargs: object):
        calls.append({"url": url, "headers": headers, "payload": payload, **kwargs})
        return {
            "content": '{"action":"conclude"}',
            "reasoning_content": "short reasoning",
            "served_model": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k",
            "usage": {"prompt_tokens": 9, "completion_tokens": 4},
        }

    client = PortalModelClient(
        base_url="http://pipeline.test",
        api_key="test-key",
        streamer=stream,
        trace_reader=lambda _cid: {"backend": "ollama-general", "model": "served"},
        digest_resolver=lambda *_args: ("digest-1", "test"),
    )
    reply = client.complete(
        [{"role": "user", "content": "return json"}],
        model="general-deep",
        schema={"type": "object"},
        max_tokens=64,
        think=True,
    )

    assert reply == ModelReply(text='{"action":"conclude"}', reasoning="short reasoning")
    payload = calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["think"] is True
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["portal_no_tools"] is True
    assert calls[0]["is_pipeline_mode"] is True
    assert client.call_receipts[0].model_digest == "digest-1"
    assert client.call_receipts[0].prompt_tokens == 9
    hint = workspace_model_hint("general-deep")
    assert calls[0]["expected_model_hint"] == {hint, *alias_targets_for_model(hint or "")}


def test_hidden_security_variant_resolves_to_a_listed_workspace() -> None:
    calls: list[dict[str, object]] = []

    def stream(url: str, headers: dict[str, str], payload: dict[str, object], **kwargs: object):
        calls.append({"url": url, "headers": headers, "payload": payload, **kwargs})
        return {
            "content": "{}",
            "reasoning_content": "reason",
            "served_model": "granite4.1:30b-ctx16k",
            "usage": {},
        }

    client = PortalModelClient(
        base_url="http://pipeline.test",
        api_key="test-key",
        streamer=stream,
        trace_reader=lambda _cid: {},
        digest_resolver=lambda *_args: ("", "unavailable"),
    )
    client.complete(
        [{"role": "user", "content": "return json"}],
        model="auto-security::security-council-granite41-30b",
        schema=None,
        max_tokens=64,
        think=True,
    )
    payload = calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "compliance-council-granite41"


def test_portal_client_retries_one_transport_failure_only() -> None:
    attempts = 0

    def stream(*_args: object, **_kwargs: object):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            request = httpx.Request("POST", "http://pipeline.test/v1/chat/completions")
            raise httpx.ConnectError("transient", request=request)
        return {"content": "{}", "reasoning_content": "reason", "served_model": "m", "usage": {}}

    client = PortalModelClient(
        base_url="http://pipeline.test",
        api_key="test-key",
        streamer=stream,
        trace_reader=lambda _cid: {},
        digest_resolver=lambda *_args: ("", "unavailable"),
    )
    reply = client.complete(
        [{"role": "user", "content": "x"}],
        model="general-deep",
        schema=None,
        max_tokens=8,
        think=True,
    )
    assert reply.error == ""
    assert attempts == 2
    assert client.call_receipts[0].attempts == 2
