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
        """Prompt must stay under 10000 chars (fits within Llama-3.2-3B 4096-token context).
        Cap raised from 6000 → 10000 to accommodate the 94-workspace catalog (was 13)."""
        prompt = _build_router_prompt("a" * 500)
        assert len(prompt) < 10000


class TestRouteWithLLM:
    """_route_with_llm() must correctly parse LLM responses and handle errors."""

    @pytest.mark.asyncio
    async def test_returns_workspace_on_high_confidence(self):
        mock_resp = _mock_llm_response("auto-coding", 0.95)
        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("write a Python function"))
            assert result == "auto-coding"

    @pytest.mark.asyncio
    async def test_returns_none_on_low_confidence(self):
        mock_resp = _mock_llm_response("auto-coding", 0.3)
        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("write a Python function"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_unknown_workspace(self):
        mock_resp = _mock_llm_response("auto-notaworkspace", 0.95)
        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        import httpx

        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self):
        import httpx

        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

            result = await _route_with_llm(_user_messages("hello"))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_auto_workspace(self):
        """'auto' is the default — returning it provides no routing value."""
        mock_resp = _mock_llm_response("auto", 0.99)
        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
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
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
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
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
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
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
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
        """_VALID_WORKSPACE_IDS must cover all non-bench workspaces.

        bench-* workspaces are user-selected only and intentionally excluded
        from the LLM intent classifier allowlist (_VALID_WORKSPACE_IDS /
        _ROUTER_JSON_SCHEMA) so the auto-router never routes to them.
        """
        from portal_pipeline.router_pipe import WORKSPACES

        production_ids = frozenset(k for k in WORKSPACES if not k.startswith("bench-"))
        bench_ids = frozenset(k for k in WORKSPACES if k.startswith("bench-"))

        missing_from_router = production_ids - _VALID_WORKSPACE_IDS
        assert not missing_from_router, (
            f"Production workspaces missing from _VALID_WORKSPACE_IDS: {missing_from_router}"
        )
        leaked_bench = bench_ids & _VALID_WORKSPACE_IDS
        assert not leaked_bench, (
            f"Bench workspaces must not appear in _VALID_WORKSPACE_IDS: {leaked_bench}"
        )

    @pytest.mark.asyncio
    async def test_llm_router_payload_includes_keep_alive(self):
        """_route_with_llm payload must include top-level keep_alive=-1 (int).
        String '-1' was changed to int -1 in commit 3f20d51 (warmup keep_alive fix)."""
        mock_resp = _mock_llm_response("auto-coding", 0.95)
        with patch(
            "portal_pipeline.router.routing._http_client", new_callable=AsyncMock
        ) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)
            await _route_with_llm(_user_messages("write a Python function"))
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload.get("keep_alive") == -1, (
                f"Expected keep_alive=-1 (int) in LLM router payload, got {payload.get('keep_alive')!r}"
            )
            assert "keep_alive" in payload


class TestLastUserText:
    """_last_user_text() extracts and truncates the last user message."""

    def test_string_content_truncation(self):
        from portal_pipeline.router.routing import _last_user_text

        result = _last_user_text([{"role": "user", "content": "hello world"}], 5)
        assert result == "hello"

    def test_list_content_extraction(self):
        from portal_pipeline.router.routing import _last_user_text

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "first part"},
                    {"type": "image_url", "image_url": {"url": "http://img"}},
                    {"type": "text", "text": "second part"},
                ],
            }
        ]
        result = _last_user_text(messages, 100)
        assert result == "first part second part"

    def test_list_content_truncation(self):
        from portal_pipeline.router.routing import _last_user_text

        messages = [{"role": "user", "content": [{"type": "text", "text": "abcdefghij"}]}]
        result = _last_user_text(messages, 5)
        assert result == "abcde"

    def test_finds_last_user_message(self):
        from portal_pipeline.router.routing import _last_user_text

        messages = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "second question"},
        ]
        result = _last_user_text(messages, 100)
        assert result == "second question"

    def test_returns_empty_for_no_user(self):
        from portal_pipeline.router.routing import _last_user_text

        result = _last_user_text([{"role": "assistant", "content": "hello"}], 100)
        assert result == ""


class TestResolvePersonaTools:
    """_resolve_persona_tools semantics: absent, null, explicit list, empty list, deny."""

    def test_absent_tools_allow_uses_workspace_default(self):
        from portal_pipeline.router.workspaces import _resolve_persona_tools

        result = _resolve_persona_tools({}, "auto-coding")
        assert "execute_python" in result
        assert len(result) > 0

    def test_null_tools_allow_uses_workspace_default(self):
        from portal_pipeline.router.workspaces import _resolve_persona_tools

        result = _resolve_persona_tools({"tools_allow": None}, "auto-coding")
        assert "execute_python" in result
        assert len(result) > 0

    def test_empty_tools_allow_means_no_tools(self):
        from portal_pipeline.router.workspaces import _resolve_persona_tools

        result = _resolve_persona_tools({"tools_allow": []}, "auto-coding")
        assert result == []

    def test_nonempty_tools_allow_replaces_workspace_default(self):
        from portal_pipeline.router.workspaces import _resolve_persona_tools

        result = _resolve_persona_tools(
            {"tools_allow": ["execute_bash", "remember"]}, "auto-coding"
        )
        assert set(result) == {"execute_bash", "remember"}

    def test_deny_still_subtracts(self):
        from portal_pipeline.router.workspaces import _resolve_persona_tools

        result = _resolve_persona_tools(
            {
                "tools_allow": ["execute_python", "execute_bash", "remember"],
                "tools_deny": ["execute_bash"],
            },
            "auto-coding",
        )
        assert set(result) == {"execute_python", "remember"}

    def test_deny_works_on_workspace_default(self):
        from portal_pipeline.router.workspaces import _resolve_persona_tools

        result = _resolve_persona_tools({"tools_deny": ["execute_python"]}, "auto-coding")
        assert "execute_python" not in result
        assert len(result) > 0


class TestPersonaCatalogAudit:
    """Audit persona YAMLs: ensure no silent semantics traps."""

    def test_no_stale_empty_tools_allow_without_comment(self):
        """Every persona with tools_allow: [] should document the no-tools intent."""
        from pathlib import Path

        import yaml

        personas_dir = Path(__file__).resolve().parent.parent.parent / "config" / "personas"
        if not personas_dir.is_dir():
            pytest.skip("config/personas/ not found")
        issues = []
        for yf in sorted(personas_dir.glob("*.yaml")):
            raw = yf.read_text()
            data = yaml.safe_load(raw) or {}
            # tools_allow explicitly present as empty list (not just missing/null)
            if (
                "tools_allow" in data
                and data["tools_allow"] == []
                and "no tools" not in raw.lower()
                and "no-tools" not in raw.lower()
            ):
                issues.append(f"{yf.name}: tools_allow: [] without 'no tools' comment")
        assert not issues, f"Personas with tools_allow: [] missing intent comment: {issues}"
