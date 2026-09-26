"""The pipeline dialect: the compliance transport speaking to the pipeline.

P5-FANOUT-001 W1/W2. The load-bearing properties pinned here:

* the wire carries a WORKSPACE id (a raw tag resolves through
  ``model_addressing``) plus ``portal_client_tools_only`` — the WFE contract —
  and NOT the direct-call fields the pipeline drops (``num_ctx``, a
  caller-side reasoning effort);
* failures arrive in the shapes the reading loop already handles
  (``ContextCeilingError``/``HTTPError``/``URLError``) — an httpx exception
  would escape ``read()`` and kill a reading with no receipt;
* every call stamps its routing truth (workspace, backend, served model,
  correlation id) onto the receipt;
* the seat window is consulted only where it is FIXED (pipeline), never on
  the native endpoint where a request may raise it.
"""

from __future__ import annotations

import urllib.error
from typing import Any

import httpx
import pytest

import portal.platform.inference.streaming_client as streaming_client_module
from portal.modules.compliance.core import reading_transport
from portal.modules.compliance.core.reading_transport import chat
from portal.modules.compliance.core.transport_dialects import (
    OllamaNative,
    PipelineCompat,
    resolve_dialect,
)
from portal.platform.inference import model_addressing

# ── addressing ───────────────────────────────────────────────────────────────


def test_workspace_passthrough_for_known_workspace():
    assert model_addressing.workspace_id_for_model("auto-security") == "auto-security"


def test_workspace_mapping_for_registered_hint():
    assert model_addressing.workspace_id_for_model("granite4.1:8b-ctx8k") == "tools-specialist"


def test_unknown_tag_passes_through():
    assert model_addressing.workspace_id_for_model("no-such-tag:latest") == "no-such-tag:latest"


def test_context_limit_declared_and_absent():
    assert model_addressing.workspace_context_limit("auto-compliance") == 32768
    assert model_addressing.workspace_context_limit("no-such-workspace") == 0


# ── resolution default ───────────────────────────────────────────────────────


def test_resolve_dialect_defaults_to_pipeline():
    assert resolve_dialect().name == "pipeline"


def test_resolve_dialect_explicit_still_works():
    assert resolve_dialect("ollama-native").name == "ollama-native"
    with pytest.raises(ValueError, match="unknown transport dialect"):
        resolve_dialect("carrier-pigeon")


# ── build shape ──────────────────────────────────────────────────────────────


def _built(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": "granite4.1:8b-ctx8k",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "t"}}],
        "fmt": "json",
        "think": False,
        "num_predict": 256,
        "num_ctx": 98304,
        "temperature": 0.0,
        "keep_alive": "30m",
    }
    kwargs.update(overrides)
    return PipelineCompat().build(**kwargs)


def test_build_resolves_tag_to_workspace_on_the_wire():
    assert _built()["model"] == "tools-specialist"


def test_build_keeps_client_tools_and_marks_them_client_only():
    body = _built()
    assert body["tools"] == [{"type": "function", "function": {"name": "t"}}]
    assert body["portal_client_tools_only"] is True


def test_build_drops_direct_call_fields():
    body = _built()
    # num_ctx/keep_alive are memory-lifecycle decisions the pipeline owns; a
    # request-time window change on ollama is a measured 3.4-5.6s reload.
    assert "num_ctx" not in body
    assert "keep_alive" not in body
    # think maps to reasoning_effort on the parent dialect; the pipeline takes
    # its policy from the workspace, so the caller-side value must not travel.
    assert "reasoning_effort" not in body
    assert "options" not in body


def test_build_maps_json_format():
    assert _built()["response_format"] == {"type": "json_object"}
    assert "response_format" not in _built(fmt=None)


# ── failure translation ──────────────────────────────────────────────────────


def test_post_translates_http_status_error(monkeypatch):
    request = httpx.Request("POST", "http://localhost:9099/v1/chat/completions")
    response = httpx.Response(400, text='{"error":"context"}', request=request)

    def _boom(*a: Any, **k: Any):
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    monkeypatch.setattr(streaming_client_module, "stream_chat_turn", _boom)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        PipelineCompat().post({"model": "x", "messages": []}, timeout=60)
    assert excinfo.value.code == 400


def test_post_translates_stall_to_urlerror(monkeypatch):
    def _boom(*a: Any, **k: Any):
        raise streaming_client_module.StreamTurnStalledError("no data for 60s")

    monkeypatch.setattr(streaming_client_module, "stream_chat_turn", _boom)
    with pytest.raises(urllib.error.URLError, match="stalled"):
        PipelineCompat().post({"model": "x", "messages": []}, timeout=60)


def test_post_synthesizes_body_and_carries_trace(monkeypatch):
    def _fake(url, headers, payload, **k):
        assert headers["X-Correlation-ID"].startswith("compliance-")
        assert payload["model"] == "tools-specialist"
        return {
            "role": "assistant",
            "content": '{"ok": true}',
            "tool_calls": [],
            "served_model": "granite-4.1-8b-mxfp8",
            "usage": {"prompt_tokens": 11, "completion_tokens": 4},
        }

    monkeypatch.setattr(streaming_client_module, "stream_chat_turn", _fake)
    dialect = PipelineCompat()
    monkeypatch.setattr(
        dialect,
        "_trace",
        lambda cid: {"backend": "omlx-general", "served_model": "granite-4.1-8b-mxfp8"},
    )
    body = dialect.post({"model": "tools-specialist", "messages": []}, timeout=60)
    assert body["choices"][0]["message"]["content"] == '{"ok": true}'
    assert body["usage"]["prompt_tokens"] == 11
    assert body["_portal"]["backend"] == "omlx-general"
    assert body["_portal"]["served_model"] == "granite-4.1-8b-mxfp8"
    assert body["_portal"]["correlation_id"].startswith("compliance-")


# ── receipt lift ─────────────────────────────────────────────────────────────


def test_chat_receipt_stamps_pipeline_attribution():
    class _PipelineFake(PipelineCompat):
        def post(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
            return {
                "model": "granite-4.1-8b-mxfp8",
                "choices": [{"message": {"role": "assistant", "content": '{"ok": 1}'}}],
                "_portal": {
                    "correlation_id": "compliance-abc123",
                    "workspace": "tools-specialist",
                    "backend": "omlx-general",
                    "served_model": "granite-4.1-8b-mxfp8",
                },
            }

    reading_transport._THINK_CAPABLE.clear()
    try:
        result = chat(
            "granite4.1:8b-ctx8k",
            system="s",
            user="u",
            fmt="json",
            dialect=_PipelineFake(),
        )
    finally:
        reading_transport._THINK_CAPABLE.clear()
    assert result["dialect"] == "pipeline"
    assert result["workspace"] == "tools-specialist"
    assert result["route_backend"] == "omlx-general"
    assert result["served_model"] == "granite-4.1-8b-mxfp8"
    assert result["correlation_id"] == "compliance-abc123"
    assert result["context_source"] == "seat_baked_window"


# ── seat window authority ────────────────────────────────────────────────────


def test_seat_window_pipeline_reads_workspace_context_limit(monkeypatch):
    monkeypatch.delenv("COMPLIANCE_TRANSPORT", raising=False)
    assert reading_transport.seat_window("bench-granite41-30b-ctx98k") == 98304
    assert reading_transport.seat_window("bench-granite41-30b") == 16384


def test_seat_window_native_is_zero_because_the_request_can_raise_it(monkeypatch):
    monkeypatch.delenv("COMPLIANCE_TRANSPORT", raising=False)
    # OllamaNative reports baked num_ctx, but its context_source is
    # request_num_ctx — the window is requestable, so the caller keeps sizing.
    monkeypatch.setattr(OllamaNative, "seat_window", lambda self, model: 16384)
    assert reading_transport.seat_window("granite4.1:30b-ctx16k", dialect=OllamaNative()) == 0


# ── unaddressable names are refused, not silently served ────────────────────


def test_build_refuses_unmapped_tag():
    with pytest.raises(ValueError, match="neither a portal.yaml workspace id"):
        _built(model="no-such-tag-xyz:latest")


def test_build_accepts_variant_workspace_ids():
    body = _built(model="auto-security::redteam")
    assert body["model"] == "auto-security::redteam"


# ── applied options lift (PIPELINE_ALIGNMENT_V1 §P3) ─────────────────────────


def test_trace_lifts_applied_options_when_recorded(monkeypatch):
    """The receipt carries what the pipeline APPLIED, not what was requested."""
    captured: dict[str, Any] = {}

    def _fake_get(url, timeout, headers):
        captured["url"] = url
        return {
            "backend": "omlx-general",
            "model": "mlx-community--gemma-4-26b-a4b-it-4bit",
            "options_applied": {
                "workspace": "compliance-reading",
                "temperature": 0.0,
                "max_tokens": 3072,
                "enable_thinking": False,
                "workspace_context_limit": 32768,
            },
        }

    import portal.modules.compliance.core.transport_dialects as td

    monkeypatch.setattr(td, "_get", _fake_get)
    applied = PipelineCompat()._trace("compliance-abc123")
    assert applied["backend"] == "omlx-general"
    assert applied["options_applied"]["temperature"] == 0.0
    assert applied["options_applied"]["enable_thinking"] is False
    assert applied["options_applied"]["workspace_context_limit"] == 32768


def test_trace_records_applied_options_absence_as_none(monkeypatch):
    """A trace without applied options says so — the receipt never invents them."""
    import portal.modules.compliance.core.transport_dialects as td

    monkeypatch.setattr(td, "_get", lambda url, timeout, headers: {"backend": "omlx-general"})
    applied = PipelineCompat()._trace("compliance-abc123")
    assert applied["options_applied"] is None


def test_chat_receipt_carries_applied_options():
    class _PipelineFake(PipelineCompat):
        def post(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
            return {
                "model": "granite-4.1-8b-mxfp8",
                "choices": [{"message": {"role": "assistant", "content": '{"ok": 1}'}}],
                "_portal": {
                    "correlation_id": "compliance-def456",
                    "workspace": "tools-specialist",
                    "backend": "omlx-general",
                    "served_model": "granite-4.1-8b-mxfp8",
                    "options_applied": {"temperature": 0.0, "max_tokens": 3072},
                },
            }

    reading_transport._THINK_CAPABLE.clear()
    try:
        result = chat(
            "granite4.1:8b-ctx8k",
            system="s",
            user="u",
            fmt="json",
            dialect=_PipelineFake(),
        )
    finally:
        reading_transport._THINK_CAPABLE.clear()
    assert result["applied_options"] == {"temperature": 0.0, "max_tokens": 3072}


def test_note_applied_options_records_post_injection_body():
    """The recorder reads the WIRE body after injection, caller values included."""
    from portal.platform.inference.router import trace as trace_module
    from portal.platform.inference.router.validation import _note_applied_options

    seen: dict[str, Any] = {}

    def _fake_note(**fields):
        seen.update(fields)

    original = trace_module.note
    trace_module.note = _fake_note
    try:
        body = {
            "model": "x",
            "temperature": 0.42,  # caller-supplied wins and is what shows
            "max_tokens": 777,
            "options": {"num_ctx": 16384},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        _note_applied_options(body, "compliance-reading")
    finally:
        trace_module.note = original
    applied = seen["options_applied"]
    assert applied["temperature"] == 0.42
    assert applied["max_tokens"] == 777
    assert applied["num_ctx"] == 16384
    assert applied["enable_thinking"] is False
    assert applied["workspace"] == "compliance-reading"
