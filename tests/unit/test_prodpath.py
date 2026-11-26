"""Offline regression checks for the shared production-path client."""

from __future__ import annotations

from scripts import prodpath


def test_variant_route_uses_owui_alias_or_pipeline_fallback() -> None:
    assert prodpath.resolve_route("auto-security::uncensored") == (
        "owui",
        "securityuncensored",
    )
    assert prodpath.resolve_route("auto-security::purpleteam-deep") == ("pipeline", None)
    assert prodpath.resolve_route("auto-daily::inkling") == ("pipeline", None)


def test_stream_parser_reads_content_usage_and_audit_calls() -> None:
    parsed = prodpath.parse_stream(
        [
            'data: {"choices":[{"delta":{"content":"READY"}}]}',
            'data: {"usage":{"prompt_tokens":53,"completion_tokens":1}}',
            'data: {"type":"exec_audit","tool_calls":[{"name":"lookup_cve"}]}',
            "data: [DONE]",
        ]
    )
    assert parsed.text == "READY"
    assert parsed.usage["prompt_tokens"] == 53
    assert parsed.tool_calls == [{"name": "lookup_cve"}]


def test_trace_match_prefers_request_id_then_workspace_and_time() -> None:
    target = prodpath.SeatTarget("auto-daily", "ollama-general", "model-x", engine="ollama")
    rows = [
        {"correlation_id": "old", "workspace": "auto-daily", "started_at": 90},
        {"correlation_id": "current", "workspace": "auto-daily", "started_at": 101},
        {"correlation_id": "other", "workspace": "auto-coding", "started_at": 101},
    ]
    assert prodpath.select_trace(rows, target, 100, "current") == rows[1]
    assert prodpath.select_trace(rows, target, 100) == rows[1]


def test_trace_match_accepts_the_owui_alias_for_a_variant() -> None:
    target = prodpath.SeatTarget("auto-security::uncensored", None, "model-x")
    row = {"requested": "securityuncensored", "started_at": 100}
    assert prodpath.select_trace([row], target, 100) == row


def test_deprecated_workspace_alias_resolves_to_pipeline_target() -> None:
    target = prodpath.configured_target("general-fast")
    assert target.workspace == "auto-daily::fast"
    assert target.request_workspace == "general-fast"
    assert target.route == "pipeline"


def test_trace_gate_accepts_the_requested_workspace_alias() -> None:
    target = prodpath.SeatTarget(
        "auto-daily::fast", None, "model-x", request_workspace="general-fast"
    )
    trace = {
        "workspace": "general-fast",
        "outcome": "ok",
        "backend": "backend-x",
        "model": "model-x",
    }
    assert prodpath.trace_failures(target, trace) == []


def test_stream_chat_uses_explicit_pipeline_arm_for_preflight(monkeypatch) -> None:
    target = prodpath.SeatTarget(
        "auto-daily", "backend-x", "arm-model", route="pipeline", request_model="arm-model"
    )
    captured = {}

    def fake_stream(url, body, headers, timeout, client=None):
        captured.update(url=url, body=body)
        return 200, prodpath.StreamResult(usage={"prompt_tokens": 5}), ""

    monkeypatch.setattr(prodpath, "_http_stream", fake_stream)
    monkeypatch.setattr(prodpath, "fetch_trace", lambda *_a, **_k: None)
    receipt = prodpath.stream_chat(
        target,
        [{"role": "user", "content": "ready"}],
        owui_url="http://owui",
        pipeline_url="http://pipeline",
        owui_key="key",
        pipeline_key="key",
    )
    assert captured["url"] == "http://pipeline/v1/chat/completions?model=arm-model"
    assert captured["body"]["model"] == "auto-daily"
    assert receipt.prompt_tokens == 5


def test_trace_gate_accepts_ok_and_safety_refusal_but_checks_identity() -> None:
    target = prodpath.SeatTarget("auto-daily", None, "model-x", engine="ollama")
    ok = {
        "workspace": "auto-daily",
        "outcome": "ok",
        "backend": "ollama-general",
        "model": "model-x",
    }
    assert prodpath.trace_failures(target, ok) == []
    refusal = {"workspace": "auto-daily", "outcome": "safety_refusal"}
    assert prodpath.trace_failures(target, refusal) == []
    assert "served model 'fallback', expected 'model-x'" in prodpath.trace_failures(
        target, {**ok, "model": "fallback"}
    )


def test_preflight_rejects_http_200_without_measured_tokens(monkeypatch, capsys) -> None:
    target = prodpath.SeatTarget("auto-daily", "ollama-general", "model-x")
    receipt = prodpath.TurnReceipt(
        status=200,
        trace={
            "workspace": "auto-daily",
            "outcome": "complete",
            "backend": "ollama-general",
            "model": "model-x",
        },
        outcome="complete",
        backend="ollama-general",
        model="model-x",
    )
    monkeypatch.setattr(prodpath, "stream_chat", lambda *_a, **_k: receipt)
    result = prodpath.preflight([target], owui_key="key", pipeline_key="key")
    assert not result[0].ok
    assert "no measured prompt_tokens in the stream or Pipeline trace" in result[0].failures
    assert "prompt_tokens=0" in capsys.readouterr().out


def test_fill_calibration_subtracts_fixed_system_prompt_usage(monkeypatch) -> None:
    target = prodpath.SeatTarget("auto-daily", "ollama-general", "model-x")
    baseline = prodpath.TurnReceipt(status=200, prompt_tokens=150)
    trace = {
        "workspace": "auto-daily",
        "outcome": "complete",
        "backend": "ollama-general",
        "model": "model-x",
    }
    measured = prodpath.TurnReceipt(
        status=200,
        prompt_tokens=200,
        trace=trace,
        outcome="complete",
        backend="ollama-general",
        model="model-x",
    )
    monkeypatch.setattr(prodpath, "stream_chat", lambda *_a, **_k: measured)
    ratio = prodpath.calibrate_context_fill(
        target,
        baseline,
        owui_url="http://owui",
        pipeline_url="http://pipeline",
        owui_key="key",
        pipeline_key="key",
    )
    assert ratio == (len(prodpath.PREFLIGHT_PROMPT) / 50, 100)


def test_configured_target_resolves_alias_and_fallback_from_config() -> None:
    target = prodpath.configured_target("auto-documents")

    assert target.engine == "omlx"
    assert target.model == "gemma-4-26b-a4b-it-QAT-4bit"
    assert any(
        fallback.engine == "ollama" and fallback.model == "gemma4:26b-a4b-it-qat-ctx32k"
        for fallback in target.fallbacks
    )


def test_trace_gate_accepts_a_configured_fallback() -> None:
    target = prodpath.configured_target("auto-documents")
    fallback = next(item for item in target.fallbacks if item.engine == "ollama")
    trace = {
        "workspace": "auto-documents",
        "outcome": "complete",
        "backend": fallback.backend,
        "model": fallback.model,
    }

    assert prodpath.trace_failures(target, trace) == []


def test_vision_preflight_requires_and_sends_an_existing_image(monkeypatch) -> None:
    target = prodpath.configured_target("auto-vision")
    assert target.preflight_image == prodpath.REPO / "tests/fixtures/vision/natural-00.png"
    captured = {}

    def fake_stream(target, messages, **_kwargs):
        captured["messages"] = messages
        return prodpath.TurnReceipt(
            status=200,
            prompt_tokens=50,
            trace={
                "workspace": target.workspace,
                "outcome": "complete",
                "backend": target.primary_backend,
                "model": target.model,
            },
            outcome="complete",
            backend=target.primary_backend or "",
            model=target.model,
        )

    monkeypatch.setattr(prodpath, "stream_chat", fake_stream)
    assert prodpath.preflight([target])[0].ok
    content = captured["messages"][0]["content"]
    assert any(part.get("type") == "image_url" for part in content)


def test_vision_preflight_rejects_missing_image_before_request(monkeypatch) -> None:
    target = prodpath.SeatTarget("auto-vision", "test-backend", "model-x")
    called = False

    def fake_stream(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("text-only auto-vision preflight must not be sent")

    monkeypatch.setattr(prodpath, "stream_chat", fake_stream)
    result = prodpath.preflight([target])

    assert not result[0].ok
    assert "vision preflight requires an image fixture" in result[0].failures
    assert not called
