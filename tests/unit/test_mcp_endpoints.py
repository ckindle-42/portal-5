"""tests/unit/test_mcp_endpoints.py

Tests for OpenAI-compatible HTTP endpoints on MCP servers.
These are the endpoints Open WebUI uses for native TTS and STT.

Requires: mcp>=2.0.0 (in pyproject.toml [dev] group)
All tests should PASS after 'pip install -e .[dev,mcp]'
Tests SKIP (not ERROR) when mcp/kokoro/faster-whisper are not installed.
"""

import sys

import pytest

sys.path.insert(0, ".")


class TestBackendModelHintRouting:
    """Test backend routing and workspace configuration completeness."""

    def test_exec_workspaces_have_execute_bash_tool(self):
        """auto-security's purpleteam-exec/pentest variants must declare
        execute_bash in their tool list (BUILD_PROGRAM_COLLAPSE_V1.md Phase 6
        folded auto-purpleteam-exec/auto-pentest into these variants)."""
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import WORKSPACES

        for canonical_id in ["auto-security::purpleteam-exec", "auto-security::pentest"]:
            base, variant = _unpack_synthetic_workspace(canonical_id)
            resolved_id = _resolve_workspace_variant(canonical_id, base, variant)
            tools = WORKSPACES[resolved_id].get("tools", [])
            assert "execute_bash" in tools, (
                f"Exec workspace '{canonical_id}' must include execute_bash in tools list"
            )

    def test_purpleteam_exec_has_chain_hops(self):
        """auto-security's purpleteam-exec variant must define at least 3
        follow-on chain hops (was auto-purpleteam-exec, Phase 6).

        The variant belongs to the `security_redteam` module, which ships
        disabled — offensive-generation variants are enabled for a lab
        generation run, not for everyday traffic. The contract still holds
        whenever the module is on, so the assertion is on the config, which is
        present either way, and the served-id check is conditional.
        """
        from portal.platform.inference.config import load_portal_config
        from portal.platform.wiki.adapters.modules import is_workspace_disabled

        variants = load_portal_config().workspaces["auto-security"].variants
        chain = variants["purpleteam-exec"].get("chain", [])
        assert len(chain) >= 3, (
            f"auto-purpleteam-exec chain must have ≥3 hops (blue/detect/IR), got {len(chain)}"
        )
        if is_workspace_disabled("auto-security::purpleteam-exec"):
            return

        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import WORKSPACES

        base, variant = _unpack_synthetic_workspace("auto-security::purpleteam-exec")
        resolved_id = _resolve_workspace_variant("auto-security::purpleteam-exec", base, variant)
        assert len(WORKSPACES[resolved_id].get("chain", [])) >= 3

    def test_backend_registry_loads_all_groups(self):
        """All core backend groups (general, coding, security, etc.) must load."""
        from portal.platform.inference.cluster_backends import BackendRegistry

        reg = BackendRegistry(config_path="config/backends.yaml")
        groups = {b.group for b in reg.list_backends()}
        expected = {"general", "coding", "security", "reasoning", "vision", "creative"}
        assert groups >= expected, f"Missing backend groups: {expected - groups}"
        assert "mlx" not in groups, (
            "MLX backend group must not be present — MLX inference has been retired"
        )


class TestWhisperToolSchema:
    """The old manifest advertised `audio_path`; the native schema must name the parameter the
    function actually takes, or a model transcribes the latest upload instead of the named file."""

    def test_schema_names_the_parameter_the_function_takes(self):
        import asyncio

        pytest.importorskip("faster_whisper")
        from portal.modules.media.tools import whisper_mcp

        tools = {tool.name: tool for tool in asyncio.run(whisper_mcp.mcp.list_tools())}
        props = set(tools["transcribe_audio"].input_schema["properties"])
        assert props == {"file_path", "language"}
        assert "audio_path" not in props
