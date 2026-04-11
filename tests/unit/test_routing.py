"""Unit tests for LLM-based intent router (P5-FUT-006).

All Ollama HTTP calls are mocked — no running backend required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from portal_pipeline.router_pipe import (
    _VALID_WORKSPACE_IDS,
    _build_router_prompt,
    _detect_workspace,
    _route_with_llm,
)


def _user_messages(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def _mock_llm_response(workspace: str, confidence: float) -> MagicMock:
    """Build a mock httpx response that returns valid JSON from the LLM router."""
    payload = json.dumps({"workspace": workspace, "confidence": confidence})
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": payload}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestBuildRouterPrompt:
    """_build_router_prompt() must produce a non-empty prompt with key elements."""

    def test_returns_string(self):
        prompt = _build_router_prompt("write a Python script")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_includes_user_message(self):
        msg = "write a Splunk tstats query for failed logins"
        prompt = _build_router_prompt(msg)
        assert msg in prompt

    def test_includes_workspace_ids(self):
        prompt = _build_router_prompt("hello")
        # All workspace IDs that should appear in descriptions/prompt
        for ws in ["auto-coding", "auto-spl", "auto-security", "auto-redteam"]:
            assert ws in prompt, f"Expected '{ws}' in prompt"

    def test_capped_at_reasonable_length(self):
        """Prompt must stay under 4096 chars to fit within 512-token context budget."""
        prompt = _build_router_prompt("a" * 500)
        assert len(prompt) < 4096


class TestRouteWithLLM:
    """_route_with_llm() must correctly parse LLM responses and handle errors."""

    @pytest.mark.asyncio
    async def test_returns_workspace_on_high_confidence(self):
        mock_resp = _mock_llm_response("auto-coding", 0.95)
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("write a Python function"))
            assert result == "auto-coding"

    @pytest.mark.asyncio
    async def test_returns_none_on_low_confidence(self):
        mock_resp = _mock_llm_response("auto-coding", 0.3)
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("write a Python function"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_unknown_workspace(self):
        mock_resp = _mock_llm_response("auto-notaworkspace", 0.95)
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        import httpx

        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self):
        import httpx

        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_auto_workspace(self):
        """'auto' is the default — returning it provides no routing value."""
        mock_resp = _mock_llm_response("auto", 0.99)
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        """When LLM_ROUTER_ENABLED=false, must skip LLM call entirely."""
        with patch("portal_pipeline.router_pipe._LLM_ROUTER_ENABLED", False):
            result = await _route_with_llm(_user_messages("write a Python function"))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_malformed_json(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "not json {{{"}
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_empty_messages_returns_none(self):
        result = await _route_with_llm([])
        assert result is None

    @pytest.mark.asyncio
    async def test_spl_routing_via_llm(self):
        """Verify SPL workspace is returned and is a valid workspace ID."""
        mock_resp = _mock_llm_response("auto-spl", 0.98)
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(
                _user_messages("write a Splunk tstats query to count failed logins by user")
            )
            assert result == "auto-spl"
            assert result in _VALID_WORKSPACE_IDS

    @pytest.mark.asyncio
    async def test_security_routing_via_llm(self):
        mock_resp = _mock_llm_response("auto-security", 0.93)
        with patch(
            "portal_pipeline.router_pipe._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(
                _user_messages("analyze this CVE and explain the exploitation path")
            )
            assert result == "auto-security"

    def test_keyword_fallback_still_works(self):
        """_detect_workspace() must still route correctly as LLM fallback."""
        msgs = _user_messages("write a Splunk tstats query for authentication failures")
        assert _detect_workspace(msgs) == "auto-spl"

    def test_keyword_fallback_coding(self):
        msgs = _user_messages("write a Python function to parse JSON logs")
        result = _detect_workspace(msgs)
        assert result == "auto-coding"

    def test_keyword_fallback_redteam(self):
        msgs = _user_messages("generate a reverse shell payload using metasploit")
        result = _detect_workspace(msgs)
        assert result in ("auto-redteam", "auto-security")

    def test_valid_workspace_ids_covers_all_workspaces(self):
        """_VALID_WORKSPACE_IDS must match WORKSPACES keys exactly."""
        from portal_pipeline.router_pipe import WORKSPACES

        assert frozenset(WORKSPACES.keys()) == _VALID_WORKSPACE_IDS, (
            f"Mismatch: _VALID_WORKSPACE_IDS={_VALID_WORKSPACE_IDS - frozenset(WORKSPACES.keys())} "
            f"extra, missing={frozenset(WORKSPACES.keys()) - _VALID_WORKSPACE_IDS}"
        )
