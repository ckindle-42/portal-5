"""tests/unit/test_channels.py

Tests for Telegram and Slack channel adapters.

These tests verify the adapter logic — message routing, workspace selection,
history management, auth, and error handling — using a mock Pipeline server.

No real Telegram/Slack tokens required. The adapters are now importable without
tokens set (tokens are read inside build_app(), not at module level).
"""

import sys

import pytest


class TestSlackAdapter:
    """Test Slack bot logic without real tokens."""

    def test_channel_workspace_map_all_valid(self):
        """Every channel target is a workspace or a time-boxed alias."""
        from portal.platform.inference.config import load_portal_config
        from portal_channels.slack.bot import CHANNEL_WORKSPACE_MAP

        config = load_portal_config()
        catalog = set(config.workspaces) | set(config.aliases)
        for channel_keyword, (workspace_id, _variant) in CHANNEL_WORKSPACE_MAP.items():
            assert workspace_id in catalog, (
                f"Slack channel '{channel_keyword}' → '{workspace_id}' "
                f"is not a declared workspace. Valid: {sorted(catalog)}"
            )


class TestDocumentMCPTools:
    """Test document generation tool names and actual file creation."""

    def test_registered_tool_names_match_manifest(self):
        """Tool names used by AI must match @mcp.tool() registered names."""

        sys.path.insert(0, ".")
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST, mcp

        registered = set(mcp._tool_manager._tools.keys())
        manifest = {t["name"] for t in TOOLS_MANIFEST}
        missing = manifest - registered
        assert not missing, (
            f"Tools in TOOLS_MANIFEST not registered: {missing}. AI will fail to call these tools."
        )


class TestSandboxMCPTools:
    """Test sandbox tool name alignment."""

    def test_registered_names_match_manifest(self):

        sys.path.insert(0, ".")
        from portal.modules.coding.tools.code_sandbox_mcp import TOOLS_MANIFEST, mcp

        registered = set(mcp._tool_manager._tools.keys())
        manifest = {t["name"] for t in TOOLS_MANIFEST}
        missing = manifest - registered
        assert not missing, f"Tools in manifest not registered: {missing}"

    def test_execute_python_exists(self):

        sys.path.insert(0, ".")
        from portal.modules.coding.tools.code_sandbox_mcp import mcp

        assert "execute_python" in mcp._tool_manager._tools

    def test_execute_bash_exists(self):

        sys.path.insert(0, ".")
        from portal.modules.coding.tools.code_sandbox_mcp import mcp

        assert "execute_bash" in mcp._tool_manager._tools

    @pytest.mark.asyncio
    async def test_execute_bash_accepts_manifest_command_and_code(self, monkeypatch):
        """Native MCP callers follow TOOLS_MANIFEST (`command`); internal callers may pass `code`."""
        import json
        from types import SimpleNamespace

        sys.path.insert(0, ".")
        from portal.modules.coding.tools import code_sandbox_mcp as sandbox_mcp

        listed = {t.name: t for t in await sandbox_mcp.mcp.list_tools()}
        assert "command" in listed["execute_bash"].input_schema.get("properties", {})

        seen: list[str] = []

        async def _fake_docker(*, code: str, **_kwargs):
            seen.append(code)
            return {
                "success": True,
                "stdout": code,
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "artifacts": [],
            }

        monkeypatch.setattr(sandbox_mcp, "_run_in_docker", _fake_docker)
        ctx = SimpleNamespace(request_context=None)

        await sandbox_mcp.mcp.call_tool("execute_bash", {"command": "echo via_command"}, ctx)
        await sandbox_mcp.mcp.call_tool("execute_bash", {"code": "echo via_code"}, ctx)
        assert seen == ["echo via_command", "echo via_code"]

        empty_res = await sandbox_mcp.mcp.call_tool("execute_bash", {}, ctx)
        payload = json.loads(empty_res.content[0].text)
        assert payload["success"] is False
        assert payload["error_type"] == "invalid_arguments"


class TestAllMCPServerToolAlignment:
    """Verify TOOLS_MANIFEST and @mcp.tool() registered names are in sync for all servers.

    Both directions are checked:
    1. Every name in TOOLS_MANIFEST must have a matching @mcp.tool() function
       (otherwise AI tool calls fail silently)
    2. Every @mcp.tool() function must appear in TOOLS_MANIFEST
       (otherwise the tool is registered but invisible to the AI — dead code)
    """

    @pytest.mark.parametrize(
        "module_path",
        [
            "portal.modules.documents.tools.document_mcp",
            "portal.modules.coding.tools.code_sandbox_mcp",
        ],
    )
    def test_manifest_and_registered_are_in_sync(self, module_path):
        """TOOLS_MANIFEST and @mcp.tool() must be a perfect bidirectional match.

        Only servers that still serve a REST manifest are listed; the native-only servers'
        registered tool sets are asserted in tests/unit/test_mcp_fleet_single_source.py.
        """
        import importlib

        sys.path.insert(0, ".")
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            # Only skip for genuinely missing optional packages (kokoro, faster-whisper,
            # docx, audiocraft, etc.). Internal typos, renamed symbols, or broken
            # internal imports should FAIL — not silently become skips.
            exc_lower = str(exc).lower()
            optional_pkgs = (
                "kokoro_onnx",
                "kokoro-onnx",
                "faster_whisper",
                "faster-whisper",
                "docx",
                "openpyxl",
                "pptx",
                "audiocraft",
                "stable_audio_tools",
                "stable-audio-tools",
                "torch",
            )
            if any(pkg in exc_lower for pkg in optional_pkgs):
                pytest.skip(f"Optional dep missing for {module_path}: {exc}")
            else:
                raise  # re-raise — not an optional-package gap, a real breakage
        registered = set(mod.mcp._tool_manager._tools.keys())
        manifest = {t["name"] for t in mod.TOOLS_MANIFEST}

        missing_from_manifest = registered - manifest
        missing_from_code = manifest - registered

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

    def test_valid_workspaces_covers_pipeline_workspaces(self):
        """Dispatcher knows all canonical workspace IDs."""

        sys.path.insert(0, ".")
        from portal.platform.inference.router_pipe import WORKSPACES
        from portal_channels.dispatcher import VALID_WORKSPACES

        pipeline_ids = set(WORKSPACES.keys())
        dispatcher_ids = set(VALID_WORKSPACES)

        missing = pipeline_ids - dispatcher_ids
        assert not missing, (
            f"Workspaces in pipeline but not in dispatcher: {missing}. "
            f"Update VALID_WORKSPACES in dispatcher.py"
        )
