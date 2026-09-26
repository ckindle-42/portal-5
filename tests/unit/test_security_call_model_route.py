"""TASK_AUTO_COUNCIL_PIPELINE_REVISIT_V1 P1 regression coverage for
``agentic_blue_eval._call_model``'s pipeline-mode contract:

* an unaddressable role tag must fail closed (``UnaddressableSecurityModelError``)
  instead of letting the pipeline silently substitute the routing group's
  first model (the root cause of both live wrong-seat cases in the task doc).
* a tool-bearing security call must mark its request ``portal_client_tools_only``
  so the pipeline dispatches exactly the caller-supplied schema instead of
  merging in the resolved workspace's own tool whitelist (P1.4).
"""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.security.core import agentic_blue_eval as abe


@pytest.fixture(autouse=True)
def _direct_ollama_off(monkeypatch):
    # These tests exercise the pipeline-mode branch only.
    monkeypatch.delenv("CHAIN_DIRECT_OLLAMA", raising=False)
    monkeypatch.delenv("PORTAL_SECURITY_DIRECT_ENGINE_DIAGNOSTIC", raising=False)


def test_unaddressable_tag_fails_closed(monkeypatch):
    monkeypatch.setattr(abe, "resolve_pipeline_model", lambda model: model)
    monkeypatch.setattr(
        "portal.platform.inference.model_addressing.is_addressable", lambda model: False
    )
    captured: dict[str, Any] = {}

    def _fake_stream(url, headers, payload, **kwargs):
        captured["called"] = True
        return {"content": "should not be reached"}

    from portal.modules.security.core import exec_chain

    monkeypatch.setattr(exec_chain, "_stream_chain_turn", _fake_stream)

    with pytest.raises(abe.UnaddressableSecurityModelError):
        abe._call_model("not-a-real-role-tag", [{"role": "user", "content": "hi"}])

    assert "called" not in captured


def test_addressable_tag_dispatches(monkeypatch):
    monkeypatch.setattr(abe, "resolve_pipeline_model", lambda model: model)
    monkeypatch.setattr(
        "portal.platform.inference.model_addressing.is_addressable", lambda model: True
    )
    captured: dict[str, Any] = {}

    def _fake_stream(url, headers, payload, **kwargs):
        captured["payload"] = payload
        return {"content": "ok"}

    from portal.modules.security.core import exec_chain

    monkeypatch.setattr(exec_chain, "_stream_chain_turn", _fake_stream)

    msg = abe._call_model("granite4.1:8b-ctx8k", [{"role": "user", "content": "hi"}])

    assert msg == {"content": "ok"}
    assert "portal_client_tools_only" not in captured["payload"]
    assert captured["payload"]["portal_strict_seat"] is True


def test_tool_bearing_call_sets_client_tools_only(monkeypatch):
    monkeypatch.setattr(abe, "resolve_pipeline_model", lambda model: model)
    monkeypatch.setattr(
        "portal.platform.inference.model_addressing.is_addressable", lambda model: True
    )
    captured: dict[str, Any] = {}

    def _fake_stream(url, headers, payload, **kwargs):
        captured["payload"] = payload
        return {"content": "", "tool_calls": []}

    from portal.modules.security.core import exec_chain

    monkeypatch.setattr(exec_chain, "_stream_chain_turn", _fake_stream)

    retrieval_tools = [
        {"type": "function", "function": {"name": "query_windows_events", "parameters": {}}}
    ]
    abe._call_model(
        "granite4.1:8b-ctx8k",
        [{"role": "user", "content": "investigate"}],
        tools=retrieval_tools,
    )

    payload = captured["payload"]
    assert payload["tools"] == retrieval_tools
    assert payload["portal_client_tools_only"] is True
