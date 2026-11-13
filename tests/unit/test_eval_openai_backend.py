"""Eval-only OpenAI backend: exclusive bench routes, no production fallthrough."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from portal.platform.inference.cluster_backends import Backend, BackendRegistry
from portal.platform.inference.router import council, non_streaming
from portal.platform.inference.sync_config import _routing_default

CONFIG = "config/backends.yaml"


def _registry(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> BackendRegistry:
    if enabled:
        monkeypatch.setenv("PORTAL_ENABLE_EVAL", "1")
    else:
        monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
    monkeypatch.delenv("PORTAL_BENCH_WORKSPACES", raising=False)
    return BackendRegistry(config_path=CONFIG)


def test_exclusive_ids_do_not_fall_through_when_eval_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = _registry(monkeypatch, False)
    assert reg.is_exclusive("bench-engine-daily-moe")
    assert reg.get_backend_candidates("bench-engine-daily-moe") == []
    assert "eval-openai" not in {b.id for b in reg.list_backends()}
    daily = [b.id for b in reg.get_backend_candidates("auto-daily")]
    assert daily
    assert "eval-openai" not in daily


def test_enabled_eval_backend_is_exclusive_and_not_a_degrade_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = _registry(monkeypatch, True)
    coding = reg.get_backend_candidates("bench-engine-coding")
    assert [b.id for b in coding] == ["eval-openai"]
    assert coding[0].type == "eval_openai"
    assert coding[0].health_url.endswith("/v1/models")
    assert coding[0].resolve_model("Qwen3.8-27B-4bit") == "Qwen3.8-27B-4bit"
    assert coding[0].resolve_model("hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k") is None
    production = reg.get_backend_candidates("auto-coding")
    assert production
    assert all(b.type != "eval_openai" for b in production)


def test_eval_openai_health_defaults_to_models() -> None:
    backend = Backend(
        id="eval-openai",
        type="eval_openai",
        url="http://127.0.0.1:11234",
        group="eval",
        models=["Qwen3.8-27B-4bit"],
    )
    assert backend.health_url == "http://127.0.0.1:11234/v1/models"


def test_routing_default_sends_exclusive_ids_to_eval() -> None:
    exclusive = frozenset({"bench-engine-hunt"})
    assert _routing_default("bench-engine-hunt", exclusive) == ["eval"]
    assert _routing_default("auto-daily", exclusive) == ["general"]


def test_eval_openai_uses_the_omlx_seat_dialect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(non_streaming, "registry", SimpleNamespace(request_timeout=300.0))
    assert non_streaming._request_timeout_for(SimpleNamespace(type="eval_openai"), {}) == 600.0
    payload: dict = {}
    council._apply_think(payload, False, "eval_openai")
    assert payload["chat_template_kwargs"]["enable_thinking"] is False


def test_exclusive_hop_does_not_fall_through_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    eval_backend = SimpleNamespace(
        id="eval-openai",
        type="eval_openai",
        chat_url="http://eval/v1/chat/completions",
        resolve_model=lambda hint: hint if hint == "Qwen3.8-27B-4bit" else None,
    )
    ollama = SimpleNamespace(
        id="ollama-general",
        type="ollama",
        chat_url="http://ollama/v1/chat/completions",
        resolve_model=lambda _hint: "gguf-tag",
    )
    reg = SimpleNamespace(
        get_backend_candidates=lambda _ws: [eval_backend],
        list_healthy_backends=lambda: [eval_backend, ollama],
        is_exclusive=lambda _ws: True,
    )
    monkeypatch.setattr(non_streaming, "registry", reg)
    monkeypatch.setitem(non_streaming.WORKSPACES, "bench-engine-coding", {"temperature": 0.1})
    url, body = non_streaming.resolve_hop_target(
        "bench-engine-coding",
        "Qwen3.8-27B-4bit",
        "http://primary/v1/chat/completions",
        {"model": "Qwen3.8-27B-4bit"},
    )
    assert url == eval_backend.chat_url
    assert body["model"] == "Qwen3.8-27B-4bit"
    assert "think" not in body or body.get("chat_template_kwargs")


def test_production_hop_skips_an_eval_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    eval_backend = SimpleNamespace(
        id="eval-openai",
        type="eval_openai",
        chat_url="http://eval/v1/chat/completions",
        resolve_model=lambda _hint: "Qwen3.8-27B-4bit",
    )
    ollama = SimpleNamespace(
        id="ollama-coding",
        type="ollama",
        chat_url="http://ollama/v1/chat/completions",
        resolve_model=lambda hint: hint,
    )
    reg = SimpleNamespace(
        get_backend_candidates=lambda _ws: [ollama],
        list_healthy_backends=lambda: [ollama, eval_backend],
        is_exclusive=lambda _ws: False,
    )
    monkeypatch.setattr(non_streaming, "registry", reg)
    monkeypatch.setitem(
        non_streaming.WORKSPACES, "auto-coding", {"temperature": 1.0, "think": True}
    )
    url, _body = non_streaming.resolve_hop_target(
        "auto-coding",
        "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k",
        "http://primary/v1/chat/completions",
        {"model": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k"},
    )
    assert url == ollama.chat_url


def test_council_posts_repetition_penalty_for_eval_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

    class _Client:
        async def post(self, url: str, json: dict) -> _Response:
            captured["url"] = url
            captured["json"] = json
            return _Response()

    backend = SimpleNamespace(
        id="eval-openai",
        type="eval_openai",
        models=["Qwen3.8-27B-4bit"],
        chat_url="http://eval/v1/chat/completions",
    )
    reg = SimpleNamespace(
        get_backend_candidates=lambda _ws: [backend],
        list_healthy_backends=lambda: [backend],
        is_exclusive=lambda _ws: True,
    )
    monkeypatch.setattr(council, "_http_client", _Client())
    asyncio.run(
        council._post_model(
            model="Qwen3.8-27B-4bit",
            system="sys",
            user="user",
            max_tokens=32,
            sampling={"repeat_penalty": 1.0, "temperature": 0.7},
            think=False,
            workspace_id="bench-engine-council-json",
            registry=reg,
            role="evidence",
        )
    )
    assert captured["json"]["repetition_penalty"] == 1.0
    assert captured["json"]["chat_template_kwargs"]["enable_thinking"] is False
