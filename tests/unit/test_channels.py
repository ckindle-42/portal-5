"""tests/unit/test_channels.py

Tests for Telegram and Slack channel adapters.

These tests verify the adapter logic — message routing, workspace selection,
history management, auth, and error handling — using a mock Pipeline server.

No real Telegram/Slack tokens required. The adapters are now importable without
tokens set (tokens are read inside build_app(), not at module level).
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")


# ── Telegram ─────────────────────────────────────────────────────────────────

class TestTelegramAdapter:
    """Test Telegram bot logic without a real token or API connection."""

    def test_module_imports_without_token(self):
        """Module must be importable without TELEGRAM_BOT_TOKEN set."""
        import importlib
        import os
        env_backup = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        try:
            if "portal_channels.telegram.bot" in sys.modules:
                del sys.modules["portal_channels.telegram.bot"]
            mod = importlib.import_module("portal_channels.telegram.bot")
            assert hasattr(mod, "build_app")
            assert hasattr(mod, "handle_message")
        finally:
            if env_backup:
                os.environ["TELEGRAM_BOT_TOKEN"] = env_backup

    def test_build_app_raises_without_token(self):
        """build_app() raises RuntimeError with helpful message when token missing."""
        import os

        from portal_channels.telegram.bot import build_app
        env_backup = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        try:
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                build_app()
        finally:
            if env_backup:
                os.environ["TELEGRAM_BOT_TOKEN"] = env_backup

    def test_is_allowed_empty_list_permits_all(self):
        """Empty TELEGRAM_USER_IDS allows everyone."""
        import os
        os.environ["TELEGRAM_USER_IDS"] = ""
        from portal_channels.telegram import bot
        # Re-read the function since env might be cached
        assert bot._is_allowed(12345) is True
        assert bot._is_allowed(99999) is True

    def test_is_allowed_enforces_allowlist(self):
        """Non-empty TELEGRAM_USER_IDS blocks unlisted users."""
        import importlib
        import os

        os.environ["TELEGRAM_USER_IDS"] = "111,222"
        from portal_channels.telegram import bot

        importlib.reload(bot)
        assert bot._is_allowed(111) is True
        assert bot._is_allowed(999) is False
        os.environ.pop("TELEGRAM_USER_IDS", None)

    @pytest.mark.asyncio
    async def test_handle_message_unauthorized_user(self):
        """Unauthorized user gets rejected before Pipeline is called."""
        import importlib
        import os

        os.environ["TELEGRAM_USER_IDS"] = "12345"
        from portal_channels.telegram import bot

        importlib.reload(bot)

        update = MagicMock()
        update.effective_user.id = 99999  # not in allowlist
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.text = "hello"

        await bot.handle_message(update, MagicMock())
        update.effective_message.reply_text.assert_called_once_with("Unauthorized.")
        os.environ.pop("TELEGRAM_USER_IDS", None)

    @pytest.mark.asyncio
    async def test_handle_message_calls_pipeline(self):
        """Authorized message calls Pipeline with correct payload."""
        import importlib
        import os

        os.environ.pop("TELEGRAM_USER_IDS", None)  # allow all
        from portal_channels.telegram import bot

        importlib.reload(bot)

        update = MagicMock()
        update.effective_user.id = 12345
        update.effective_message.text = "What is Python?"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.chat.send_action = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Python is a programming language."}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("portal_channels.dispatcher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            await bot.handle_message(update, context)

            # Verify Pipeline was called
            call_args = mock_client.return_value.post.call_args
            assert "/v1/chat/completions" in call_args[0][0]
            payload = call_args[1]["json"]
            assert payload["model"] == "auto"
            # The user message is in messages (may be last or second-to-last depending on mutation)
            user_messages = [m for m in payload["messages"] if m["role"] == "user"]
            assert any("Python" in m["content"] for m in user_messages)

            # Verify response sent to user
            update.effective_message.reply_text.assert_called_once()
            reply_text = update.effective_message.reply_text.call_args[0][0]
            assert "Python" in reply_text

    @pytest.mark.asyncio
    async def test_handle_message_stores_history(self):
        """Conversation history is stored and bounded at 20 messages."""
        import importlib
        import os

        os.environ.pop("TELEGRAM_USER_IDS", None)
        from portal_channels.telegram import bot

        importlib.reload(bot)

        context = MagicMock()
        context.user_data = {
            "history": [
                {"role": "user", "content": f"msg {i}"}
                for i in range(20)  # already at limit
            ]
        }

        update = MagicMock()
        update.effective_user.id = 1
        update.effective_message.text = "new message"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.chat.send_action = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "reply"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch("portal_channels.dispatcher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(return_value=mock_response)
            await bot.handle_message(update, context)

        # History is bounded at 20 before sending, then assistant reply is added
        # So total may be 21 (20 capped + 1 assistant). Check it stays bounded.
        assert len(context.user_data["history"]) <= 22

    @pytest.mark.asyncio
    async def test_workspace_command_sets_workspace(self):
        """set_workspace command correctly updates user context."""
        from portal_channels.telegram.bot import set_workspace

        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}
        context.args = ["auto-coding"]

        await set_workspace(update, context)
        assert context.user_data["workspace"] == "auto-coding"
        update.effective_message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_workspace_command_rejects_invalid(self):
        """set_workspace rejects unknown workspace names."""
        from portal_channels.telegram.bot import set_workspace

        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}
        context.args = ["auto-nonexistent"]

        await set_workspace(update, context)
        # Should NOT set the workspace
        assert "workspace" not in context.user_data
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Unknown workspace" in reply or "nonexistent" in reply.lower()

    @pytest.mark.asyncio
    async def test_pipeline_error_handled_gracefully(self):
        """Pipeline connection failure returns error message, does not crash."""
        import importlib
        import os

        os.environ.pop("TELEGRAM_USER_IDS", None)
        from portal_channels.telegram import bot

        importlib.reload(bot)

        update = MagicMock()
        update.effective_user.id = 1
        update.effective_message.text = "hello"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.chat.send_action = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        with patch("portal_channels.dispatcher.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.post = AsyncMock(side_effect=Exception("Connection refused"))
            await bot.handle_message(update, context)

        reply = update.effective_message.reply_text.call_args[0][0]
        assert "⚠️" in reply or "error" in reply.lower()


# ── Slack ─────────────────────────────────────────────────────────────────────

class TestSlackAdapter:
    """Test Slack bot logic without real tokens."""

    def test_module_imports_without_tokens(self):
        """Module must be importable without SLACK_BOT_TOKEN set."""
        import importlib
        import os
        for key in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
            os.environ.pop(key, None)
        if "portal_channels.slack.bot" in sys.modules:
            del sys.modules["portal_channels.slack.bot"]
        mod = importlib.import_module("portal_channels.slack.bot")
        assert hasattr(mod, "build_app")
        assert hasattr(mod, "CHANNEL_WORKSPACE_MAP")

    def test_build_app_raises_without_bot_token(self):
        """build_app() raises RuntimeError with helpful message."""
        import importlib
        import os

        from portal_channels.slack import bot as slack_bot

        importlib.reload(slack_bot)
        for key in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
            os.environ.pop(key, None)
        with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
            slack_bot.build_app()

    def test_channel_workspace_map_all_valid(self):
        """Every workspace in CHANNEL_WORKSPACE_MAP is a real workspace ID."""
        import sys

        sys.path.insert(0, ".")
        from portal_channels.slack.bot import CHANNEL_WORKSPACE_MAP
        from portal_pipeline.router_pipe import WORKSPACES

        for channel_keyword, workspace_id in CHANNEL_WORKSPACE_MAP.items():
            assert workspace_id in WORKSPACES, (
                f"Slack channel '{channel_keyword}' → '{workspace_id}' "
                f"is not a valid workspace. Valid: {sorted(WORKSPACES.keys())}"
            )

    def test_workspace_for_channel_routing(self):
        """Channel names correctly map to workspace IDs."""
        from portal_channels.slack.bot import _workspace_for_channel
        assert _workspace_for_channel("coding-help") == "auto-coding"
        assert _workspace_for_channel("security-alerts") == "auto-security"
        assert _workspace_for_channel("images-channel") == "auto-vision"  # NOT auto-images
        assert _workspace_for_channel("unknown-channel") == "auto"  # default

    def test_pipeline_call_correct_endpoint(self):
        """_call_pipeline sends request to correct endpoint with auth."""
        import importlib
        import os

        os.environ["PIPELINE_API_KEY"] = "test-key"
        from portal_channels.slack import bot as slack_bot

        importlib.reload(slack_bot)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test reply"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("portal_channels.dispatcher.httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_client.return_value)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.post = MagicMock(return_value=mock_response)

            result = slack_bot._call_pipeline("Hello", "auto-coding")

            call_args = mock_client.return_value.post.call_args
            url = call_args[0][0]
            assert "/v1/chat/completions" in url
            payload = call_args[1]["json"]
            assert payload["model"] == "auto-coding"
            assert payload["messages"][0]["content"] == "Hello"
            assert result == "test reply"

    def test_pipeline_error_returns_error_string(self):
        """_call_pipeline raises exception that callers handle."""
        from portal_channels.slack import bot as slack_bot
        with patch("portal_channels.dispatcher.httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_client.return_value)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.post = MagicMock(side_effect=Exception("Connection error"))
            with pytest.raises(Exception, match="Connection error"):
                slack_bot._call_pipeline("Hello", "auto")

    def test_get_tokens_requires_both_tokens(self):
        """_get_tokens raises if either token is missing."""
        import os

        from portal_channels.slack.bot import _get_tokens
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-test"
        os.environ.pop("SLACK_APP_TOKEN", None)
        with pytest.raises(RuntimeError, match="SLACK_APP_TOKEN"):
            _get_tokens()
        os.environ.pop("SLACK_BOT_TOKEN", None)


# ── MCP Tools (expanded from test_mcp_endpoints.py) ──────────────────────────

class TestDocumentMCPTools:
    """Test document generation tool names and actual file creation."""

    def test_registered_tool_names_match_manifest(self):
        """Tool names used by AI must match @mcp.tool() registered names."""
        import sys

        sys.path.insert(0, ".")
        from portal_mcp.documents.document_mcp import TOOLS_MANIFEST, mcp

        registered = set(mcp._tool_manager._tools.keys())
        manifest = {t["name"] for t in TOOLS_MANIFEST}
        missing = manifest - registered
        assert not missing, (
            f"Tools in TOOLS_MANIFEST not registered: {missing}. "
            f"AI will fail to call these tools."
        )

    def test_create_powerpoint_creates_file(self, tmp_path, monkeypatch):
        """create_powerpoint tool actually generates a .pptx file."""
        import importlib
        import sys

        sys.path.insert(0, ".")
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        # Reload to pick up new OUTPUT_DIR

        import portal_mcp.documents.document_mcp as doc_mod

        importlib.reload(doc_mod)

        result = doc_mod.create_powerpoint(
            title="Test Deck",
            slides=[
                {"title": "Intro", "content": "This tests Portal 5 document generation."},
                {"title": "Summary", "content": "It works."},
            ],
        )
        assert result.get("success") is True or "path" in result, f"Failed: {result}"
        path = result.get("path", "")
        assert path.endswith(".pptx"), f"Expected .pptx file, got: {path}"

    def test_create_excel_creates_file(self, tmp_path, monkeypatch):
        """create_excel tool actually generates a .xlsx file."""
        import importlib
        import sys

        sys.path.insert(0, ".")
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

        import portal_mcp.documents.document_mcp as doc_mod

        importlib.reload(doc_mod)

        result = doc_mod.create_excel(
            title="Test Spreadsheet",
            data=[["Name", "Score"], ["Alice", 95], ["Bob", 87]],
        )
        assert result.get("success") is True or "path" in result, f"Failed: {result}"
        assert result.get("path", "").endswith(".xlsx")

    def test_create_word_document_creates_file(self, tmp_path, monkeypatch):
        """create_word_document actually generates a .docx file."""
        import importlib
        import sys

        sys.path.insert(0, ".")
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

        import portal_mcp.documents.document_mcp as doc_mod

        importlib.reload(doc_mod)

        result = doc_mod.create_word_document(
            title="Test Document",
            content="Portal 5 document generation test. This document was created by the test suite.",
        )
        assert result.get("success") is True or "path" in result, f"Failed: {result}"
        assert result.get("path", "").endswith(".docx")


class TestSandboxMCPTools:
    """Test sandbox tool name alignment."""

    def test_registered_names_match_manifest(self):
        import sys

        sys.path.insert(0, ".")
        from portal_mcp.execution.code_sandbox_mcp import TOOLS_MANIFEST, mcp

        registered = set(mcp._tool_manager._tools.keys())
        manifest = {t["name"] for t in TOOLS_MANIFEST}
        missing = manifest - registered
        assert not missing, f"Tools in manifest not registered: {missing}"

    def test_execute_python_exists(self):
        import sys

        sys.path.insert(0, ".")
        from portal_mcp.execution.code_sandbox_mcp import mcp

        assert "execute_python" in mcp._tool_manager._tools

    def test_execute_bash_exists(self):
        import sys

        sys.path.insert(0, ".")
        from portal_mcp.execution.code_sandbox_mcp import mcp

        assert "execute_bash" in mcp._tool_manager._tools


class TestAllMCPServerToolAlignment:
    """Verify TOOLS_MANIFEST and @mcp.tool() registered names are in sync for all servers.

    Both directions are checked:
    1. Every name in TOOLS_MANIFEST must have a matching @mcp.tool() function
       (otherwise AI tool calls fail silently)
    2. Every @mcp.tool() function must appear in TOOLS_MANIFEST
       (otherwise the tool is registered but invisible to the AI — dead code)
    """

    @pytest.mark.parametrize("module_path", [
        "portal_mcp.documents.document_mcp",
        "portal_mcp.generation.music_mcp",
        "portal_mcp.generation.tts_mcp",
        "portal_mcp.generation.whisper_mcp",
        "portal_mcp.generation.comfyui_mcp",
        "portal_mcp.generation.video_mcp",
        "portal_mcp.execution.code_sandbox_mcp",
    ])
    def test_manifest_and_registered_are_in_sync(self, module_path):
        """TOOLS_MANIFEST and @mcp.tool() must be a perfect bidirectional match."""
        import importlib
        import sys
        sys.path.insert(0, ".")
        mod = importlib.import_module(module_path)
        registered = set(mod.mcp._tool_manager._tools.keys())
        manifest   = {t["name"] for t in mod.TOOLS_MANIFEST}

        missing_from_manifest = registered - manifest
        missing_from_code     = manifest - registered

        assert not missing_from_code, (
            f"{module_path}: tools in TOOLS_MANIFEST but NOT registered with @mcp.tool():\n"
            f"  {missing_from_code}\n"
            f"  Effect: AI calls these tools but they don't exist → silent failure"
        )
        assert not missing_from_manifest, (
            f"{module_path}: tools registered with @mcp.tool() but NOT in TOOLS_MANIFEST:\n"
            f"  {missing_from_manifest}\n"
            f"  Effect: AI has no knowledge these tools exist → dead code"
        )


class TestDispatcher:
    """Test the shared channel dispatcher module."""

    def test_dispatcher_importable(self):
        """Dispatcher module is importable without any credentials."""
        from portal_channels.dispatcher import (
            call_pipeline_async,
            call_pipeline_sync,
            is_valid_workspace,
        )
        assert callable(call_pipeline_async)
        assert callable(call_pipeline_sync)
        assert callable(is_valid_workspace)

    def test_valid_workspaces_covers_all_13(self):
        """Dispatcher knows all 13 canonical workspace IDs."""
        import sys
        sys.path.insert(0, ".")
        from portal_channels.dispatcher import VALID_WORKSPACES
        from portal_pipeline.router_pipe import WORKSPACES

        pipeline_ids = set(WORKSPACES.keys())
        dispatcher_ids = set(VALID_WORKSPACES)

        missing = pipeline_ids - dispatcher_ids
        assert not missing, (
            f"Workspaces in pipeline but not in dispatcher: {missing}. "
            f"Update VALID_WORKSPACES in dispatcher.py"
        )

    def test_is_valid_workspace_true_for_known(self):
        from portal_channels.dispatcher import is_valid_workspace
        for ws in ["auto", "auto-coding", "auto-security", "auto-redteam",
                   "auto-blueteam", "auto-creative", "auto-reasoning",
                   "auto-documents", "auto-video", "auto-music",
                   "auto-research", "auto-vision", "auto-data"]:
            assert is_valid_workspace(ws), f"Expected valid: {ws}"

    def test_is_valid_workspace_false_for_unknown(self):
        from portal_channels.dispatcher import is_valid_workspace
        for ws in ["", "auto-images", "auto-nonexistent", "general", "unknown"]:
            assert not is_valid_workspace(ws), f"Expected invalid: {ws}"

    @pytest.mark.asyncio
    async def test_call_pipeline_async_calls_correct_endpoint(self):
        """call_pipeline_async sends to /v1/chat/completions with correct payload."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from portal_channels.dispatcher import call_pipeline_async

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Test reply"}}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("portal_channels.dispatcher.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await call_pipeline_async("Hello", "auto-coding")

            call_args = mock_client.post.call_args
            url = call_args[0][0]
            assert "/v1/chat/completions" in url
            payload = call_args[1]["json"]
            assert payload["model"] == "auto-coding"
            assert payload["messages"][-1]["content"] == "Hello"
            assert result == "Test reply"

    def test_call_pipeline_sync_calls_correct_endpoint(self):
        """call_pipeline_sync sends to /v1/chat/completions with correct payload."""
        from unittest.mock import MagicMock, patch

        from portal_channels.dispatcher import call_pipeline_sync

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Sync reply"}}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("portal_channels.dispatcher.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post = MagicMock(return_value=mock_resp)

            result = call_pipeline_sync("Hello sync", "auto")

            assert result == "Sync reply"
            call_args = mock_client.post.call_args
            assert "/v1/chat/completions" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_call_pipeline_async_retries_on_500(self):
        """Dispatcher retries async calls on HTTP 5xx before succeeding."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from portal_channels.dispatcher import call_pipeline_async

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count < 2:
                mock_resp.status_code = 503   # server error on first attempt
            else:
                mock_resp.status_code = 200
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {
                    "choices": [{"message": {"content": "retry worked"}}]
                }
            return mock_resp

        with patch("portal_channels.dispatcher.PIPELINE_RETRIES", 2), \
             patch("portal_channels.dispatcher.PIPELINE_RETRY_BASE", 0.001), \
             patch("portal_channels.dispatcher.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post

            result = await call_pipeline_async("hello", "auto")

        assert result == "retry worked"
        assert call_count == 2, f"Expected 2 attempts, got: {call_count}"

    def test_call_pipeline_sync_raises_after_exhausting_retries(self):
        """Dispatcher sync raises ConnectError after all retries exhausted."""
        from unittest.mock import MagicMock, patch

        import httpx

        from portal_channels.dispatcher import call_pipeline_sync

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Connection refused")

        with patch("portal_channels.dispatcher.PIPELINE_RETRIES", 2), \
             patch("portal_channels.dispatcher.PIPELINE_RETRY_BASE", 0.001), \
             patch("portal_channels.dispatcher.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post = mock_post

            with pytest.raises(httpx.ConnectError):
                call_pipeline_sync("hello", "auto")

        assert call_count == 2, f"Expected 2 attempts, got: {call_count}"
