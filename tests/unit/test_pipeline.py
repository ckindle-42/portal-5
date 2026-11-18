"""Portal 5 v7.0.0 Pipeline unit tests — no live backends required."""

import re
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.router_pipe import WORKSPACES, app


def _seat_is_lane_served(ws: dict, ws_id: str, backends: dict) -> None:
    groups = set(backends["workspace_routing"][ws_id])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    hint = ws["model_hint"]
    assert hint in served, (ws_id, hint)
    match = re.search(r"ctx(\d+)k", hint)
    if match is None:
        # Raw oMLX id: no baked ctxNk tag exists; oMLX serves the model's native
        # window (both 27B seats are 262K, above their 131K context_limit).
        omlx_ids = {
            m["id"]
            for b in backends["backends"]
            if b.get("type") == "omlx"
            for m in b.get("models") or []
        }
        assert hint in omlx_ids, (ws_id, hint)
        return
    window = int(match.group(1)) * 1024
    assert window >= ws["context_limit"], (ws_id, hint, window)


def _make_fake_backend():
    """Build a mock BackendRegistry suitable for TestClient tests."""
    reg = MagicMock(spec=BackendRegistry)
    be = MagicMock()
    be.id = "test-backend"
    be.group = "general"
    be.models = ["test-model"]
    be.type = "ollama"
    reg.list_healthy_backends.return_value = [be]
    reg.list_backends.return_value = [be]
    reg.get_backend_candidates.return_value = [be]
    reg.workspace_routes = {}
    return reg


@pytest.fixture
def client():
    """Create a test client with proper lifespan + fake registry."""
    import portal.platform.inference.router.handlers as handlers_mod

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


import os as _os

HEADERS = {
    "Authorization": f"Bearer {_os.environ.get('PIPELINE_API_KEY', 'test-pipeline-key-for-unit-tests')}"
}


def test_workspace_aliases_have_not_passed_their_removal_date():
    from datetime import date

    from portal.platform.inference.config import load_portal_config

    expired = {
        alias_id: alias.remove_after.isoformat()
        for alias_id, alias in load_portal_config().aliases.items()
        if alias.remove_after < date.today()
    }
    assert not expired, f"Expired workspace aliases: {expired}"


def test_mathreasoner_presets_the_reasoning_math_variant():
    from portal.platform.inference.router.preinject import (
        _resolve_persona_workspace,
        _resolve_workspace_variant,
    )

    workspace = _resolve_persona_workspace("mathreasoner")
    assert workspace == "auto-reasoning"
    assert _resolve_workspace_variant("mathreasoner", workspace, None) == "auto-reasoning::math"


def test_synthetic_math_workspace_resolves_through_variant_merger():
    from portal.platform.inference.config import load_portal_config
    from portal.platform.inference.router.preinject import _resolve_workspace_variant
    from portal.platform.inference.router.workspaces import WORKSPACES

    resolved = _resolve_workspace_variant("auto-reasoning::math", "auto-reasoning", "math")
    expected = load_portal_config().workspaces["auto-reasoning"].variants["math"]

    assert resolved == "auto-reasoning::math"
    assert WORKSPACES[resolved]["model_hint"] == expected["model_hint"]


def test_math_alias_is_removed_from_router_labels():
    from portal.platform.inference.router.routing import _VALID_WORKSPACE_IDS

    assert "auto-math" not in _VALID_WORKSPACE_IDS
    assert (
        not {
            "auto-data",
            "auto-extract-uncensored",
            "auto-uncensored-throwaway",
            "auto-creative",
        }
        & _VALID_WORKSPACE_IDS
    )
    assert not {"general-fast", "general-deep", "auto-nemotron"} & _VALID_WORKSPACE_IDS
    assert "auto-reasoning" in _VALID_WORKSPACE_IDS


def test_nemotron_persona_presets_the_chat_variant():
    from portal.platform.inference.config import load_persona_map

    persona = load_persona_map()["nemotronlightning"]
    assert persona.workspace_model == "auto-daily"
    assert persona.variant == "nemotron"


class TestWorkspaceModelHintUpdated:
    """Each specialist lane seats a wired model and keeps its own tool/thinking settings."""

    def test_security_lane_keeps_its_toolset_and_gating(self):
        ws = WORKSPACES.get("auto-security", {})
        assert ws.get("model_hint") and ws.get("think") is False
        assert {"lookup_cve", "check_kev", "triage_cve"} <= set(ws.get("tools") or [])

    def test_coding_lane_keeps_its_sandbox_toolset(self):
        ws = WORKSPACES.get("auto-coding", {})
        assert ws.get("model_hint")
        assert {"execute_python", "execute_bash", "execute_nodejs", "sandbox_status"} <= set(
            ws.get("tools") or []
        )

    def test_reasoning_seats_a_thinking_model(self):
        ws = WORKSPACES.get("auto-reasoning", {})
        assert (
            ws.get("model_hint") and ws.get("think") is True and ws.get("emits_reasoning") is True
        )


class TestComplianceWorkspace:
    """Verify auto-compliance workspace is correctly wired."""

    def test_workspace_set_matches_enabled_modules(self):
        """WORKSPACES equals the module-enabled workspace set (module: eval's bench-*
        gated off by default; `video` follows its own per-deployment toggle.
        Derived from enabled_modules() so it stays correct across both."""
        from portal.platform.inference.config import load_portal_config
        from portal.platform.inference.router_pipe import WORKSPACES
        from portal.platform.wiki.adapters.modules import enabled_modules

        # Derived, not hardcoded, and leak-tolerant: WORKSPACES is built once at
        # import time, so another test's PORTAL_ENABLE_EVAL / wiki-toggle can
        # leave it either at the module-default set or the eval-on superset.
        # Assert the stable invariants: only-known ids, and every module-enabled
        # non-eval workspace is present.
        cfg = load_portal_config().workspaces
        _live = set(enabled_modules())
        must_have = {
            wid for wid, spec in cfg.items() if spec.module in _live and spec.module != "eval"
        }
        assert set(WORKSPACES) <= set(cfg), f"unknown ids: {set(WORKSPACES) - set(cfg)}"
        assert must_have <= set(WORKSPACES), f"missing: {must_have - set(WORKSPACES)}"
        assert "auto" in WORKSPACES


class TestR22CodingModelUpdates:
    """Verify R22: Coding model updates from models2.md review."""

    def test_coding_model_updates_r22(self):
        """R22 coding model updates (updated 2026-06-21: llama3.3 + qwen3.5:9b retired)."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        coding = next(b for b in cfg["backends"] if b["id"] == "ollama-coding")
        model_ids = [m["id"] if isinstance(m, dict) else m for m in coding["models"]]

        # Llama 3.1 should be gone (superseded)
        assert not any("Meta-Llama-3.1-70B" in m for m in model_ids), (
            "Llama 3.1-70B still in coding group — should be replaced"
        )

        # Llama 3.3 removed 2026-06-21: 3.8 TPS below floor, supports_tools=false
        assert not any("llama3.3" in m.lower() for m in model_ids), (
            "Llama 3.3-70B should have been removed (3.8 TPS, bench-only)"
        )

        # qwen3.5:9b removed 2026-06-21: quality 0.67 below floor
        assert not any("qwen3.5:9b" in m.lower() for m in model_ids), (
            "qwen3.5:9b should have been removed (quality 0.67, bench-only)"
        )

        # Primary coder should be qwen3-coder
        assert any("qwen3-coder" in m.lower() for m in model_ids), (
            "qwen3-coder missing from coding group"
        )


class TestRecordUsageMetrics:
    """Verify _record_usage correctly parses Ollama response fields."""

    def test_record_usage_full_response(self):
        """Standard Ollama response with all usage fields."""
        from portal.platform.inference.router_pipe import _record_usage

        # Should not raise
        _record_usage(
            model="huihui_ai/baronllm-abliterated",
            workspace="auto-security",
            data={
                "eval_count": 312,
                "eval_duration": 6638000000,  # ~47 tok/s
                "prompt_eval_count": 48,
            },
        )

    def test_record_usage_missing_fields(self):
        """Incomplete response dict — should not raise."""
        from portal.platform.inference.router_pipe import _record_usage

        _record_usage(model="test-model", workspace="auto", data={})
        _record_usage(model="test-model", workspace="auto", data={"eval_count": 0})
        _record_usage(model="test-model", workspace="auto", data={"eval_duration": 0})

    def test_record_usage_none_values(self):
        """None values in response fields — should not raise."""
        from portal.platform.inference.router_pipe import _record_usage

        _record_usage(
            model="test-model",
            workspace="auto",
            data={"eval_count": None, "eval_duration": None, "prompt_eval_count": None},
        )

    def test_record_usage_tps_calculation(self):
        """Tokens/sec is calculated correctly from eval_count and eval_duration."""
        import os

        # Skip if running in prometheus multiprocess mode — ._sum introspection
        # requires single-process mode (file-based metrics return 0 from ._sum)
        if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
            import pytest

            pytest.skip("TPS introspection requires single-process prometheus mode")

        from portal.platform.inference import router_pipe

        # Capture histogram before
        before = router_pipe._tokens_per_second.labels(
            model="tps-test-model", workspace="tps-test-ws"
        )._sum.get()
        router_pipe._record_usage(
            model="tps-test-model",
            workspace="tps-test-ws",
            data={
                "eval_count": 100,
                "eval_duration": 2_000_000_000,  # 2 seconds → 50 tok/s
                "prompt_eval_count": 20,
            },
        )
        after = router_pipe._tokens_per_second.labels(
            model="tps-test-model", workspace="tps-test-ws"
        )._sum.get()
        tps = after - before
        assert abs(tps - 50.0) < 0.1, f"Expected ~50 tok/s, got {tps}"


class TestSPLWorkspace:
    """Verify auto-spl workspace wiring across all four required files."""

    def test_splunk_not_in_coding_keywords(self):
        """'splunk' must be removed from _CODING_KEYWORDS — SPL workspace owns it now."""
        from portal.platform.inference.router_pipe import _CODING_KEYWORDS

        assert "splunk" not in _CODING_KEYWORDS, (
            "'splunk' must be removed from _CODING_KEYWORDS after adding _SPL_KEYWORDS. "
            "Leaving it causes SPL queries to route to auto-coding instead of auto-spl."
        )

    def test_spl_query_not_in_coding_keywords(self):
        """'spl query' must be removed from _CODING_KEYWORDS — SPL workspace owns it now."""
        from portal.platform.inference.router_pipe import _CODING_KEYWORDS

        assert "spl query" not in _CODING_KEYWORDS, (
            "'spl query' must be removed from _CODING_KEYWORDS after adding _SPL_KEYWORDS."
        )

    def test_spl_keywords_weighted_dict_exists(self):
        """_SPL_KEYWORDS must be a weighted dict in router_pipe."""
        from portal.platform.inference.router_pipe import _SPL_KEYWORDS

        assert isinstance(_SPL_KEYWORDS, dict), (
            "_SPL_KEYWORDS must be a dict[str, int] in router_pipe.py"
        )
        assert len(_SPL_KEYWORDS) >= 10, (
            f"_SPL_KEYWORDS seems too small ({len(_SPL_KEYWORDS)} entries) — check the definition"
        )
        assert "splunk" in _SPL_KEYWORDS, "'splunk' must be in _SPL_KEYWORDS"
        assert _SPL_KEYWORDS["splunk"] == 3, "'splunk' must have weight 3 (strong signal)"

    def test_spl_detect_workspace_routes_splunk_query(self):
        """_detect_workspace must return 'auto-spl' for an SPL-flavored message."""
        from portal.platform.inference.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "Write a splunk query to count failed logins by host"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-spl", (
            f"_detect_workspace should return 'auto-spl' for SPL content, got: {result!r}"
        )

    def test_spl_detect_workspace_routes_tstats_query(self):
        """_detect_workspace must return 'auto-spl' when user asks about tstats."""
        from portal.platform.inference.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "How do I use tstats with a data model acceleration?"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-spl", (
            f"_detect_workspace should return 'auto-spl' for tstats content, got: {result!r}"
        )


class TestAgenticWorkspace:
    """Verify auto-agentic (P5-BIG-001, big-model mode entry point) resolves
    correctly post-collapse. BUILD_PROGRAM_COLLAPSE_V1.md Phase 5 folded
    auto-agentic into auto-coding's "heavy" variant — it's no longer a
    top-level WORKSPACES key. As of alias-retirement Phase 7
    (DESIGN_ROUTER_CANONICALIZATION_V1.md), the keyword classifier
    (_WORKSPACE_ROUTING in routing.py) emits the canonical
    "auto-coding::heavy" synthetic form directly (the keyword set/threshold
    that used to live under the "auto-agentic" key is unchanged, byte-for-
    byte, at the "_coding_heavy" key — see _SCORER_VARIANT_MAP). The legacy
    alias shim that used to also resolve the bare literal string
    "auto-agentic" was removed once every live caller was proven migrated
    to canonical addressing (CLOSEOUT_ALIAS_REMOVAL.md) — these tests now
    exercise the canonical "auto-coding::heavy" form directly."""

    def test_agentic_workspace_not_a_top_level_key(self):
        """auto-agentic is no longer a WORKSPACES key directly."""
        from portal.platform.inference.router_pipe import WORKSPACES

        assert "auto-agentic" not in WORKSPACES, (
            "auto-agentic should be folded into auto-coding's 'heavy' variant "
            "(BUILD_PROGRAM_COLLAPSE_V1.md Phase 5) — if this now passes, the "
            "workspace was reintroduced as a top-level id; update this test "
            "and TestAgenticWorkspace's docstring."
        )

    def test_auto_coding_workspace_json_exists(self):
        """Workspace JSON for GUI import must exist for the base auto-coding
        workspace (variants are query-param/persona-selected, not separate
        OWUI presets — see BUILD_PROGRAM_COLLAPSE_V1.md Phase 5)."""

        ws_path = Path("imports/openwebui/workspaces/workspace_auto_coding.json")
        assert ws_path.exists(), f"Workspace JSON not found at {ws_path}"

    def test_agentic_detect_workspace_routes_agentic_query(self):
        """_detect_workspace must return the canonical 'auto-coding::heavy' synthetic
        form for agentic-flagged messages (was the bare 'auto-agentic' alias id
        pre-Phase-7 — see class docstring)."""
        from portal.platform.inference.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "Use an agentic workflow to refactor the full codebase"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-coding::heavy", (
            f"_detect_workspace should return 'auto-coding::heavy' for agentic content, got: {result!r}"
        )

    def test_agentic_detect_workspace_routes_swe_agent_query(self):
        """_detect_workspace must return the canonical 'auto-coding::heavy' synthetic
        form for SWE-agent-style queries."""
        from portal.platform.inference.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "Run a swe-agent workflow to fix the failing tests"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-coding::heavy", (
            f"_detect_workspace should return 'auto-coding::heavy' for swe-agent content, got: {result!r}"
        )

    def test_agentic_does_not_route_simple_code(self):
        """Simple coding requests must NOT route to the heavy agentic variant
        (route to base auto-coding instead)."""
        from portal.platform.inference.router_pipe import _detect_workspace

        messages = [{"role": "user", "content": "Write a Python function to parse JSON"}]
        result = _detect_workspace(messages)
        assert result != "auto-coding::heavy", (
            f"Simple code request should not route to the heavy agentic variant, got: {result!r}"
        )


class TestCodeHygiene:
    """Prevent regression of remediated issues."""

    def test_no_default_api_key_fallback(self):
        """Verify insecure default API key was removed (P5-SEC-001)."""

        router_path = Path("portal/platform/inference/router_pipe.py")
        if not router_path.exists():
            router_path = (
                Path(__file__).parent.parent.parent / "portal/platform/inference/router_pipe.py"
            )
        content = router_path.read_text()
        assert '_raw_api_key = "portal-pipeline"' not in content

    def test_no_unreferenced_complete_from_backend(self):
        """Verify _complete_from_backend was removed (P5-MAINT-001)."""
        from portal.platform.inference import router_pipe

        assert not hasattr(router_pipe, "_complete_from_backend")

    def test_mcp_server_no_warning_suppression(self):
        """Verify global warning suppression was removed (P5-OBS-001).

        Post-M4 de-vendor: portal_mcp/mcp_server/ no longer exists. The check
        confirms the directory is absent, which implies no vendored suppression.
        """

        vendored = Path("portal_mcp/mcp_server")
        assert not vendored.exists(), (
            "Vendored MCP SDK directory reappeared. M4 de-vendor was supposed to delete this."
        )

    def test_only_dind_is_privileged(self):
        """Verify only the dind service uses privileged mode (required for DinD on macOS Docker Desktop)."""

        import yaml

        compose_path = Path("deploy/portal-5/docker-compose.yml")
        if not compose_path.exists():
            compose_path = (
                Path(__file__).parent.parent.parent / "deploy/portal-5/docker-compose.yml"
            )
        data = yaml.safe_load(compose_path.read_text())
        privileged_services = [
            name for name, svc in data.get("services", {}).items() if svc.get("privileged") is True
        ]
        # Only dind may use privileged — required for Docker-in-Docker on macOS Docker Desktop
        # (rootless DinD is incompatible; see KNOWN_LIMITATIONS.md P5-ROAD-SEC-001)
        assert privileged_services == ["dind"], (
            f"Unexpected privileged services: {privileged_services}. Only 'dind' is permitted."
        )


class TestToolRegistry:
    """Tests for the tool registry module."""

    def test_tool_definition_to_openai(self):
        """ToolDefinition serialises to OpenAI tools format."""
        from portal.platform.inference.tool_registry import ToolDefinition

        td = ToolDefinition(
            name="execute_python",
            description="Run Python code",
            parameters={"type": "object", "properties": {"code": {"type": "string"}}},
            server_id="execution",
            server_url="http://localhost:8914",
        )
        oai = td.to_openai_tool()
        assert oai["type"] == "function"
        assert oai["function"]["name"] == "execute_python"
        assert oai["function"]["description"] == "Run Python code"
        assert "code" in oai["function"]["parameters"]["properties"]

    def test_tool_registry_list_names(self):
        """Registry lists tool names sorted."""
        from portal.platform.inference.tool_registry import ToolRegistry

        reg = ToolRegistry()
        assert reg.list_tool_names() == []
        assert reg.get("nonexistent") is None

    def test_tool_registry_get_openai_tools_filters(self):
        """get_openai_tools filters by name list and health/backoff."""
        import time

        from portal.platform.inference.tool_registry import ToolDefinition, ToolRegistry

        reg = ToolRegistry()
        reg._tools = {
            "a": ToolDefinition("a", "desc a", {}, "s1", "http://x:1", healthy=True),
            # "b" is unhealthy AND in active backoff window — should be excluded
            "b": ToolDefinition(
                "b",
                "desc b",
                {},
                "s1",
                "http://x:1",
                healthy=False,
                consecutive_failures=1,
                next_retry_at=time.time() + 999,
            ),
            "c": ToolDefinition("c", "desc c", {}, "s2", "http://x:2", healthy=True),
        }
        result = reg.get_openai_tools(["a", "b", "c"])
        names = [t["function"]["name"] for t in result]
        assert "a" in names
        assert "b" not in names  # unhealthy and in active backoff window
        assert "c" in names


class TestPersonaToolResolution:
    """Tests for _resolve_persona_tools."""

    def test_workspace_defaults(self):
        from portal.platform.inference.router_pipe import _resolve_persona_tools

        persona = {}
        tools = _resolve_persona_tools(persona, "auto-coding")
        assert "execute_python" in tools

    def test_persona_deny_strips_tool(self):
        from portal.platform.inference.router_pipe import _resolve_persona_tools

        persona = {"tools_deny": ["execute_python"]}
        tools = _resolve_persona_tools(persona, "auto-coding")
        assert "execute_python" not in tools

    def test_persona_allow_overrides_workspace(self):
        from portal.platform.inference.router_pipe import _resolve_persona_tools

        persona = {"tools_allow": ["generate_image"]}
        tools = _resolve_persona_tools(persona, "auto-coding")
        assert "generate_image" in tools

    def test_persona_deny_overrides_allow(self):
        from portal.platform.inference.router_pipe import _resolve_persona_tools

        persona = {
            "tools_allow": ["execute_python", "execute_bash"],
            "tools_deny": ["execute_python"],
        }
        tools = _resolve_persona_tools(persona, "auto-coding")
        assert "execute_bash" in tools
        assert "execute_python" not in tools

    def test_empty_workspace_no_tools(self):
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import _resolve_persona_tools

        base, variant = _unpack_synthetic_workspace("auto-general-uncensored::creative")
        resolved = _resolve_workspace_variant("creativewriter", base, variant)
        persona = {}
        tools = _resolve_persona_tools(persona, resolved)
        assert tools == []

    def test_workspace_tools_helper(self):
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import _workspace_tools

        # auto-agentic is now auto-coding's "heavy" variant (Phase 5) — _workspace_tools
        # is a raw WORKSPACES lookup, not alias-aware, so resolve first.
        base, variant = _unpack_synthetic_workspace("auto-coding::heavy")
        resolved_id = _resolve_workspace_variant("auto-coding::heavy", base, variant)
        tools = _workspace_tools(resolved_id)
        assert "execute_python" in tools
        assert "web_search" in tools

        base, variant = _unpack_synthetic_workspace("auto-general-uncensored::creative")
        creative_id = _resolve_workspace_variant("creativewriter", base, variant)
        tools_empty = _workspace_tools(creative_id)
        assert tools_empty == []

        tools_missing = _workspace_tools("nonexistent-workspace")
        assert tools_missing == []


class TestResolvePersonaWorkspace:
    """Regression test: _resolve_persona_workspace crashed on every real
    persona invocation (AttributeError: 'PersonaSpec' object has no
    attribute 'get' -- it called dict-style .get() on a typed PersonaSpec
    instance). Found live during BUILD_PROGRAM_COLLAPSE_V1.md Phase 5 work
    -- POST /v1/chat/completions with model="<any persona slug>" returned
    500 Internal Server Error on the running pipeline. Fixed by reading
    persona.workspace_model as an attribute."""

    def test_resolves_real_persona_slug_to_its_workspace(self):
        from portal.platform.inference.router.preinject import _resolve_persona_workspace

        assert _resolve_persona_workspace("adversarysimulator") == "auto-security"

    def test_passes_through_known_workspace_id_unchanged(self):
        from portal.platform.inference.router.preinject import _resolve_persona_workspace

        assert _resolve_persona_workspace("auto-coding") == "auto-coding"

    def test_passes_through_unknown_id_unchanged(self):
        from portal.platform.inference.router.preinject import _resolve_persona_workspace

        assert _resolve_persona_workspace("not-a-real-persona-or-workspace") == (
            "not-a-real-persona-or-workspace"
        )


class TestResolveModelOverride:
    """?model=<hint> query param override (BUILD_PROGRAM_COLLAPSE_V1.md
    Phase 8, DESIGN_COLLAPSE_V1.md §D5)."""

    def test_known_model_overrides_hint(self):
        from portal.platform.inference.router.preinject import (
            _known_backend_models,
            _resolve_model_override,
        )
        from portal.platform.inference.router.workspaces import WORKSPACES

        hint = sorted(_known_backend_models())[0]
        resolved = _resolve_model_override("auto-daily", hint)
        assert resolved == f"auto-daily::model={hint}"
        assert WORKSPACES[resolved]["model_hint"] == hint

    def test_unknown_model_is_silent_noop(self):
        from portal.platform.inference.router.preinject import _resolve_model_override

        assert _resolve_model_override("auto-daily", "not-a-real-model") == "auto-daily"

    def test_no_param_is_noop(self):
        from portal.platform.inference.router.preinject import _resolve_model_override

        assert _resolve_model_override("auto-daily", None) == "auto-daily"


class TestStreamingBackendHintPriority:
    """Streaming selects an eligible backend that actually owns the hint."""

    def test_hinted_backend_moves_ahead_of_group_default(self):
        from portal.platform.inference.cluster_backends import Backend
        from portal.platform.inference.router.handlers import _prioritize_hinted_backend

        coding = Backend(
            id="coding",
            type="ollama",
            url="http://coding",
            group="coding",
            models=["coding-default"],
        )
        general = Backend(
            id="general",
            type="ollama",
            url="http://general",
            group="general",
            models=["requested-model"],
        )

        ordered = _prioritize_hinted_backend([coding, general], "requested-model")

        assert [backend.id for backend in ordered] == ["general", "coding"]

    def test_unknown_hint_preserves_group_priority(self):
        from portal.platform.inference.cluster_backends import Backend
        from portal.platform.inference.router.handlers import _prioritize_hinted_backend

        coding = Backend(
            id="coding",
            type="ollama",
            url="http://coding",
            group="coding",
            models=["coding-default"],
        )
        general = Backend(
            id="general",
            type="ollama",
            url="http://general",
            group="general",
            models=["general-default"],
        )

        ordered = _prioritize_hinted_backend([coding, general], "missing-model")

        assert ordered == [coding, general]


class TestWorkspaceToolsConsistency:
    """Tests for workspace tool field integrity."""

    def test_all_workspaces_have_tools_field(self):
        """Every workspace dict must have a 'tools' key."""
        for ws_id, ws in WORKSPACES.items():
            assert "tools" in ws, f"Workspace '{ws_id}' missing 'tools' field"
            assert isinstance(ws["tools"], list), f"Workspace '{ws_id}' tools must be a list"

    def test_auto_agentic_has_comprehensive_tools(self):
        """auto-agentic's resolved 'heavy' variant should have the broadest tool set."""
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )

        base, variant = _unpack_synthetic_workspace("auto-coding::heavy")
        resolved_id = _resolve_workspace_variant("auto-coding::heavy", base, variant)
        tools = set(WORKSPACES[resolved_id]["tools"])
        for expected in ["execute_python", "execute_bash", "web_search", "remember", "kb_search"]:
            assert expected in tools, f"auto-agentic missing tool: {expected}"


class TestDispatchToolCall:
    """Tests for _dispatch_tool_call error handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_arguments(self):
        from portal.platform.inference.router_pipe import _dispatch_tool_call

        tc = {
            "id": "call_1",
            "function": {"name": "execute_python", "arguments": "not json"},
        }
        result = await _dispatch_tool_call(tc, {"execute_python"}, "auto-coding", "test", "req1")
        assert result["role"] == "tool"
        assert "Invalid JSON" in result["content"]

    @pytest.mark.asyncio
    async def test_tool_not_in_whitelist(self):
        from portal.platform.inference.router_pipe import _dispatch_tool_call

        tc = {
            "id": "call_2",
            "function": {"name": "execute_bash", "arguments": '{"command": "ls"}'},
        }
        result = await _dispatch_tool_call(tc, {"execute_python"}, "auto-coding", "test", "req1")
        assert result["role"] == "tool"
        assert "not available" in result["content"]


class TestExplicitRequiredToolSelection:
    """Explicit side-effect requests narrow multi-tool payloads deterministically."""

    @pytest.mark.parametrize(
        ("prompt", "expected"),
        [
            (
                "Run this code:\n\nfrom collections import Counter\nprint(Counter('aba'))",
                "execute_python",
            ),
            (
                'Run this bash command and show exact output: printf "ok\\n"',
                "execute_bash",
            ),
            (
                'Create a Word document named "Change Plan" and save as a .docx file.',
                "create_word_document",
            ),
            (
                'Create an Excel workbook named "Incident Tracker".',
                "create_excel",
            ),
            (
                'Create a 5-slide PowerPoint titled "Zero Trust".',
                "create_powerpoint",
            ),
        ],
    )
    def test_selects_single_explicit_tool(self, prompt, expected):
        from portal.platform.inference.router_pipe import _select_explicit_required_tool

        available = {
            "execute_python",
            "execute_bash",
            "execute_nodejs",
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "remember",
        }
        assert (
            _select_explicit_required_tool([{"role": "user", "content": prompt}], available)
            == expected
        )

    @pytest.mark.parametrize(
        "prompt",
        [
            "Write a Python function that validates an email address.",
            "Write a getting-started document for a junior developer.",
            "Read this Word document and summarize it.",
            # WFE doc-trip: the source's ".xlsx" used to narrow this to create_excel alone.
            'Read orders.xlsx, add up the Units column, then create a Word document titled "Units Report".',
            "Read plan.docx, add up the Hours column, then create a Word document with the total.",
            "Create an Excel workbook and a Word document from these notes.",
        ],
    )
    def test_leaves_non_side_effect_requests_on_auto(self, prompt):
        from portal.platform.inference.router_pipe import _select_explicit_required_tool

        available = {
            "execute_python",
            "create_word_document",
            "create_excel",
            "read_word_document",
            "read_excel",
        }
        assert (
            _select_explicit_required_tool([{"role": "user", "content": prompt}], available) is None
        )

    def test_never_selects_tool_outside_whitelist(self):
        from portal.platform.inference.router_pipe import _select_explicit_required_tool

        assert (
            _select_explicit_required_tool(
                [{"role": "user", "content": "Run this bash command: printf ok"}],
                {"execute_python"},
            )
            is None
        )

    @pytest.mark.parametrize(
        "prompt",
        [
            "What does CIP-007-6 R2 Part 2.2 actually require right now, as of today?",
            "What does CIP-003-9 Attachment 1 Part 6 say?",
            "What is the exact text of CIP-002-5.1a R1?",
            "Which of our procedures map to CIP-007-6 R2?",
        ],
    )
    def test_does_not_narrow_nerc_cip_requirement_lookups(self, prompt):
        """TASK_COMPLIANCE_PROVE_THE_MODULE_V1 §P4.1: nerc_cip_requirement was
        removed from the candidate list entirely. It used to be forced via
        tool_choice=required on any message naming a CIP id plus a word like
        "requirement" or "means" — but that word list is compliance-reading's
        own core vocabulary, so an analyst's ordinary question collapsed the
        curated 19-tool workspace to one tool, the model named a different
        one per its system prompt, and the turn died unanswered. A question
        is not a side effect."""
        from portal.platform.inference.router_pipe import _select_explicit_required_tool

        available = {
            "nerc_cip_requirement",
            "web_search",
            "browser_navigate",
            "compliance_gaps",
            "compliance_mappings",
        }
        assert (
            _select_explicit_required_tool([{"role": "user", "content": prompt}], available) is None
        )


class TestPersonasHaveToolFields:
    """Verify M2+M3 persona YAMLs have correct tool fields."""

    def test_agentorchestrator_has_tools(self):
        from portal.platform.inference.router_pipe import _PERSONA_MAP

        p = _PERSONA_MAP.get("agentorchestrator")
        assert p is not None
        assert p.tools_allow is not None
        assert "execute_python" in p.tools_allow

    def test_webresearcher_has_web_tools(self):
        from portal.platform.inference.router_pipe import _PERSONA_MAP

        p = _PERSONA_MAP.get("webresearcher")
        assert p is not None
        assert p.tools_allow is not None
        assert "web_search" in p.tools_allow
        assert "web_fetch" in p.tools_allow

    def test_personalassistant_has_memory_tools(self):
        from portal.platform.inference.router_pipe import _PERSONA_MAP

        p = _PERSONA_MAP.get("personalassistant")
        assert p is not None
        assert p.tools_allow is not None
        assert "remember" in p.tools_allow
        assert "recall" in p.tools_allow

    def test_kbnavigator_has_rag_tools(self):
        from portal.platform.inference.router_pipe import _PERSONA_MAP

        p = _PERSONA_MAP.get("kbnavigator")
        assert p is not None
        assert p.tools_allow is not None
        assert "kb_list" in p.tools_allow
        assert "kb_search" in p.tools_allow
        assert "kb_search_all" in p.tools_allow


class TestModelSupportsToolsRealBackend:
    """Regression for the 75c24a9 mlx_metadata removal.

    _model_supports_tools previously iterated Backend.mlx_metadata,
    a field deleted with the MLX proxy tier. Mocked tests missed it
    because they never built a real Backend through this function.
    """

    def test_backend_has_no_mlx_metadata_field(self):
        import portal.platform.inference.cluster_backends as cb

        be = cb.Backend(id="b", type="ollama", url="http://x", group="general", models=["m"])
        assert not hasattr(be, "mlx_metadata")
        assert be.ollama_metadata == []


class TestInjectOllamaOptions:
    """Tests for per-workspace keep_alive override in _inject_ollama_options."""

    def test_quality_lane_uses_10m_keep_alive(self):
        """The data variant should use keep_alive=10m.

        auto-mistral was deleted outright in BUILD_PROGRAM_COLLAPSE_V1.md
        Phase 7 (model-tied workspace, no preserved variant) -- its
        keep_alive tuning went with it."""
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import _inject_ollama_options

        base, variant = _unpack_synthetic_workspace("auto-research::data")
        data_id = _resolve_workspace_variant("dataanalyst", base, variant)
        body = _inject_ollama_options({}, data_id)
        assert body["keep_alive"] == "10m", (
            "quality lane 'auto-research::data' should have keep_alive=10m — "
            "long enough for back-to-back queries, short enough not to evict fleet"
        )

    def test_caller_supplied_keep_alive_wins(self):
        """A caller-supplied keep_alive in the request body must not be overridden."""
        from portal.platform.inference.router_pipe import _inject_ollama_options

        body = _inject_ollama_options({"keep_alive": "30m"}, "bench-devstral")
        assert body["keep_alive"] == "30m", (
            "setdefault must not override a caller-supplied keep_alive value"
        )


class TestRouterWarmupContext:
    """P5-ROUTER-EVICTION-001 regression: the startup warmup call for the LLM
    router must cap num_ctx the same way the real routing call does.

    Omitting num_ctx lets Ollama default the warmed runner to the model's
    full context window multiplied by OLLAMA_NUM_PARALLEL slots, reserving
    tens of GiB for a small router model and forcing the scheduler to evict
    it under normal memory pressure — reproduced live 2026-07-30.
    """

    @pytest.mark.asyncio
    async def test_warmup_sets_same_num_ctx_as_routing_call(self, monkeypatch):
        from unittest.mock import AsyncMock

        import portal.platform.inference.router.lifespan as lifespan_mod
        from portal.platform.inference.router.routing import _LLM_ROUTER_MODEL

        monkeypatch.setattr(lifespan_mod, "_LLM_ROUTER_ENABLED", True)
        fake_client = MagicMock()
        fake_response = MagicMock(status_code=200)
        fake_client.post = AsyncMock(return_value=fake_response)
        monkeypatch.setattr(lifespan_mod, "_http_client", fake_client)
        import portal.platform.inference.router.routing as routing_mod

        monkeypatch.setattr(routing_mod, "_http_client", fake_client)

        await lifespan_mod._warmup_llm_router()

        assert fake_client.post.await_count == 1
        _, kwargs = fake_client.post.await_args
        payload = kwargs["json"]
        assert payload["model"] == _LLM_ROUTER_MODEL
        # the warmup is the routing call itself, so its prefix is cached
        assert payload["prompt"] == routing_mod._build_router_prompt("warmup")
        assert payload["format"] == routing_mod._ROUTER_JSON_SCHEMA
        assert payload["options"]["num_ctx"] == 2048, (
            "warmup num_ctx must match the 2048 used by _route_with_llm in "
            "routing.py, or the warmed runner reserves the model's full "
            "context window and gets evicted under memory pressure"
        )

    @pytest.mark.asyncio
    async def test_auto_model_warmup_caps_num_ctx(self, monkeypatch):
        """Sibling bug: _warmup_auto_model pins backend.models[0] with
        keep_alive=-1. That model is picked for disk-cache warmth, not for
        having a baked -ctx tag (e.g. 'auto' resolves to baronllm:q6_k,
        max context 131072, no Modelfile cap) — so it needs the same
        num_ctx guard as the router warmup, or it reserves the model's
        full context forever.
        """
        from unittest.mock import AsyncMock

        import portal.platform.inference.router.lifespan as lifespan_mod

        fake_client = MagicMock()
        fake_response = MagicMock(status_code=200)
        fake_client.post = AsyncMock(return_value=fake_response)
        monkeypatch.setattr(lifespan_mod, "_http_client", fake_client)

        fake_backend = MagicMock(models=["baronllm:q6_k"], url="http://fake:11434")
        fake_registry = MagicMock()
        fake_registry.get_backend_for_workspace = MagicMock(return_value=fake_backend)

        await lifespan_mod._warmup_auto_model(fake_registry)

        assert fake_client.post.await_count == 1
        _, kwargs = fake_client.post.await_args
        payload = kwargs["json"]
        assert payload["model"] == "baronllm:q6_k"
        assert "num_ctx" in payload["options"], (
            "auto-model warmup must cap num_ctx — an unbaked model pinned "
            "with keep_alive=-1 and no cap reserves its full context window "
            "(possibly 131072+ tokens x OLLAMA_NUM_PARALLEL slots) forever"
        )


class TestPreferredResident:
    """Seat 3, 2026-11-16: `auto` routes ordinary chat to auto-daily, and a cold
    23.7 GiB daily driver is a 40 s first token. `defaults.preferred_residents`
    keeps it warm — loaded at up or the first idle moment, protected from eviction
    but never pinned (protected idle memory still yields to a seat's admission).
    """

    def _harness(self, monkeypatch, plan, candidates=None):
        from unittest.mock import AsyncMock

        import portal.platform.inference.router.lifespan as lifespan_mod

        hint = WORKSPACES["auto-daily"]["model_hint"]
        if candidates is None:
            candidates = [_candidate("ollama-general", "ollama", hint)]
        registry = MagicMock(preferred_residents=["auto-daily"])
        registry.get_backend_candidates = MagicMock(return_value=candidates)
        registry.list_backends = MagicMock(return_value=candidates)
        guard = MagicMock()
        guard.plan = AsyncMock(return_value=plan)
        guard.has_activity = MagicMock(return_value=False)
        guard.admit = AsyncMock(return_value=None)
        guard.admit_omlx = AsyncMock(return_value=None)
        guard.begin = MagicMock(return_value=lambda: None)
        client = MagicMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=200))
        monkeypatch.setattr(lifespan_mod, "_http_client", client)
        monkeypatch.setattr(lifespan_mod._load_guard_mod, "GUARD", guard)
        return lifespan_mod, registry, guard, client, hint

    @pytest.mark.asyncio
    async def test_queued_backend_stream_sends_progress_comments(self, monkeypatch):
        import asyncio

        import portal.platform.inference.router.streaming as streaming_mod

        async def _pending_load():
            await asyncio.sleep(0.04)
            yield b"data: model-ready\n\n"

        monkeypatch.setattr(streaming_mod, "_STREAM_HEARTBEAT_S", 0.005)
        chunks = [chunk async for chunk in streaming_mod._with_stream_heartbeats(_pending_load())]
        assert chunks[-1] == b"data: model-ready\n\n"
        assert b": waiting for model capacity\n\n" in chunks

    @pytest.mark.asyncio
    async def test_eviction_quiet_period_uses_the_measured_load_time(self, monkeypatch):
        from unittest.mock import AsyncMock

        import portal.platform.inference.router.lifespan as lifespan_mod

        class FakeClock:
            now = 10.0

            def monotonic(self):
                return self.now

        class FakeGuard:
            resident = False
            admission_waiting = False

            def has_activity(self):
                return self.admission_waiting

            async def plan(self, _base, _models):
                return {
                    "busy": self.admission_waiting,
                    "need_gib": 20.0,
                    "headroom_gib": 40.0,
                    "models": [{"resident": self.resident}],
                }

            async def admit(self, _base, _model):
                assert not self.admission_waiting
                return None

            def begin(self, *_args):
                return lambda: None

        clock = FakeClock()
        guard = FakeGuard()
        backend = _candidate("ollama-general", "ollama", "daily")
        client = MagicMock()

        async def _load(_url, **_kwargs):
            clock.now += 20.0
            guard.resident = True
            return MagicMock(status_code=200)

        client.post = AsyncMock(side_effect=_load)
        monkeypatch.setattr(lifespan_mod, "_http_client", client)
        state = lifespan_mod._PreferredResidentState()
        first = await lifespan_mod._warm_preferred_resident(
            backend, "ollama", "daily", {}, guard, "http://fake:11434", state, clock.monotonic
        )
        assert first == "loaded"
        assert state.load_duration_s == 20.0

        # A seat evicts the resident and spends five seconds waiting for capacity.
        guard.resident = False
        guard.admission_waiting = True
        clock.now += 5.0
        waiting = await lifespan_mod._warm_preferred_resident(
            backend, "ollama", "daily", {}, guard, "http://fake:11434", state, clock.monotonic
        )
        assert waiting == "waiting for in-flight work"

        # The next user seat starts as soon as that admission ends. The keeper must
        # honor one measured load duration after eviction instead of reloading first.
        guard.admission_waiting = False
        immediate = await lifespan_mod._warm_preferred_resident(
            backend, "ollama", "daily", {}, guard, "http://fake:11434", state, clock.monotonic
        )
        assert immediate.startswith("waiting: resident evicted")
        assert client.post.await_count == 1
        assert not guard.resident

        clock.now += 20.0
        resumed = await lifespan_mod._warm_preferred_resident(
            backend, "ollama", "daily", {}, guard, "http://fake:11434", state, clock.monotonic
        )
        assert resumed == "loaded"
        assert client.post.await_count == 2

    def test_four_pipeline_workers_elect_one_preferred_resident_keeper(self, tmp_path):
        import multiprocessing as mp

        lock_path = tmp_path / "keeper.lock"
        context = mp.get_context("spawn")
        barrier = context.Barrier(4)
        results = context.Queue()
        workers = [
            context.Process(
                target=_keeper_lock_worker,
                args=(str(lock_path), barrier, results),
            )
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        try:
            winners = [results.get(timeout=5) for _ in workers]
            for worker in workers:
                worker.join(timeout=5)
            assert all(worker.exitcode == 0 for worker in workers)
            assert sum(winners) == 1
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=2)

    @pytest.mark.asyncio
    async def test_the_daily_driver_loads_with_keep_alive_when_the_host_has_room(self, monkeypatch):
        plan = {
            "busy": False,
            "need_gib": 23.7,
            "headroom_gib": 37.2,
            "models": [{"resident": False}],
        }
        lifespan_mod, registry, guard, client, hint = self._harness(monkeypatch, plan)
        status = await lifespan_mod._warm_preferred_resident(
            registry.list_backends()[0],
            "ollama",
            hint,
            {"num_predict": 1},
            guard,
            "http://fake:11434",
        )
        assert status == "loaded"
        payload = client.post.await_args.kwargs["json"]
        assert payload["model"] == hint
        assert payload["keep_alive"] == -1
        assert "num_ctx" not in payload["options"], (
            "the -ctx derived tag bakes its own num_ctx; passing another would pin "
            "a runner with a context the seat never asked for"
        )
        guard.admit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_busy_host_is_never_made_to_wait_for_the_warm_up(self, monkeypatch):
        plan = {
            "busy": True,
            "need_gib": 23.7,
            "headroom_gib": 37.2,
            "models": [{"resident": False}],
        }
        lifespan_mod, registry, guard, client, hint = self._harness(monkeypatch, plan)
        status = await lifespan_mod._warm_preferred_resident(
            registry.list_backends()[0],
            "ollama",
            hint,
            {"num_predict": 1},
            guard,
            "http://fake:11434",
        )
        assert status == "waiting for in-flight work"
        client.post.assert_not_awaited()
        guard.admit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_model_that_does_not_fit_the_headroom_is_left_for_later(self, monkeypatch):
        plan = {
            "busy": False,
            "need_gib": 23.7,
            "headroom_gib": 4.0,
            "models": [{"resident": False}],
        }
        lifespan_mod, registry, guard, client, hint = self._harness(monkeypatch, plan)
        status = await lifespan_mod._warm_preferred_resident(
            registry.list_backends()[0],
            "ollama",
            hint,
            {"num_predict": 1},
            guard,
            "http://fake:11434",
        )
        assert status.startswith("waiting: needs 23.7 GiB")
        client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unbaked_hint_caps_num_ctx(self, monkeypatch):
        plan = {
            "busy": False,
            "need_gib": 8.0,
            "headroom_gib": 37.2,
            "models": [{"resident": False}],
        }
        lifespan_mod, registry, guard, client, _ = self._harness(monkeypatch, plan)
        await lifespan_mod._warm_preferred_resident(
            registry.list_backends()[0],
            "ollama",
            "some-model:q6_k",
            {"num_predict": 1, "num_ctx": 16384},
            guard,
            "http://fake:11434",
        )
        payload = client.post.await_args.kwargs["json"]
        assert payload["options"]["num_ctx"] == 16384

    @pytest.mark.asyncio
    async def test_an_omlx_preferred_resident_still_goes_through_admission(self, monkeypatch):
        plan = {
            "busy": False,
            "need_gib": 16.6,
            "headroom_gib": 41.0,
            "models": [{"resident": False}],
        }
        omlx = _candidate("omlx-general", "omlx", "Qwen3.8-27B-oQ4e-mtp")
        lifespan_mod, registry, guard, client, _ = self._harness(monkeypatch, plan, [omlx])
        status = await lifespan_mod._warm_preferred_resident(
            registry.list_backends()[0],
            "omlx",
            "Qwen3.8-27B-oQ4e-mtp",
            {"num_predict": 1},
            guard,
            "http://fake:11434",
        )
        assert status == "loaded"
        guard.admit_omlx.assert_awaited_once_with("Qwen3.8-27B-oQ4e-mtp")
        assert client.post.await_args.args[0].endswith("/v1/chat/completions")

    def test_the_target_is_the_backend_that_serves_the_hint_not_the_group_head(self):
        """2026-11-16 live: the keeper posted an Ollama tag to oMLX's group head and got
        404 58 times. `auto-daily` routes through group `general`, whose priority head is
        `omlx-general`, which does not serve that tag at all."""
        import portal.platform.inference.router.lifespan as lifespan_mod

        hint = WORKSPACES["auto-daily"]["model_hint"]
        head = _candidate("omlx-general", "omlx", None, url="http://fake:8085")
        serving = _candidate("ollama-general", "ollama", hint)
        registry = MagicMock(preferred_residents=["auto-daily"])
        registry.get_backend_candidates = MagicMock(return_value=[head, serving])
        ((backend, engine, model, options),) = lifespan_mod._preferred_resident_targets(registry)
        assert backend.id == "ollama-general" and engine == "ollama"
        assert model == hint
        assert "-ctx" in model and "num_ctx" not in options

    def test_the_shipped_config_resolves_the_daily_driver_to_ollama(self):
        """The real registry: the hint is served only by ollama-general."""
        import portal.platform.inference.router.lifespan as lifespan_mod
        from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH, BackendRegistry

        registry = BackendRegistry(config_path=str(DEFAULT_CONFIG_PATH))
        ((backend, engine, model, _),) = lifespan_mod._preferred_resident_targets(registry)
        assert (backend.id, engine) == ("ollama-general", "ollama")
        assert model == WORKSPACES["auto-daily"]["model_hint"]

    def test_a_workspace_whose_hint_no_backend_serves_is_skipped(self, caplog):
        import logging

        import portal.platform.inference.router.lifespan as lifespan_mod

        registry = MagicMock(preferred_residents=["auto-daily"])
        registry.get_backend_candidates = MagicMock(
            return_value=[_candidate("omlx-general", "omlx", None)]
        )
        with caplog.at_level(logging.WARNING, logger=lifespan_mod.logger.name):
            assert lifespan_mod._preferred_resident_targets(registry) == []
        assert "no healthy backend serves" in caplog.text

    @pytest.mark.asyncio
    async def test_the_keeper_protects_the_seat_and_stops_at_shutdown(self, monkeypatch):
        import asyncio

        plan = {
            "busy": False,
            "need_gib": 23.7,
            "headroom_gib": 37.2,
            "models": [{"resident": True}],
        }
        lifespan_mod, registry, guard, client, hint = self._harness(monkeypatch, plan)

        async def _stop(_seconds):
            raise asyncio.CancelledError

        monkeypatch.setattr(lifespan_mod.asyncio, "sleep", _stop)
        with pytest.raises(asyncio.CancelledError):
            await lifespan_mod._keep_preferred_residents(registry)
        guard.protect.assert_called_once_with(
            "ollama", hint, lifespan_mod._PREFERRED_RESIDENT_PROTECT_S
        )
        assert lifespan_mod._PREFERRED_RESIDENT_PROTECT_S > 0
        client.post.assert_not_awaited()  # resident already: protect, do not reload

    @pytest.mark.asyncio
    async def test_the_keeper_says_when_it_is_resident_and_logs_a_failure_once(
        self, monkeypatch, caplog
    ):
        import asyncio
        import logging

        plan = {
            "busy": False,
            "need_gib": 23.7,
            "headroom_gib": 37.2,
            "models": [{"resident": False}],
        }
        lifespan_mod, registry, guard, client, hint = self._harness(monkeypatch, plan)
        client.post = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value=MagicMock(status_code=404)
        )
        ticks = {"n": 0}

        async def _tick(_seconds):
            ticks["n"] += 1
            if ticks["n"] >= 2:
                raise asyncio.CancelledError

        monkeypatch.setattr(lifespan_mod.asyncio, "sleep", _tick)
        with (
            caplog.at_level(logging.WARNING, logger=lifespan_mod.logger.name),
            pytest.raises(asyncio.CancelledError),
        ):
            await lifespan_mod._keep_preferred_residents(registry)
        failures = [
            r.getMessage() for r in caplog.records if "Preferred resident" in r.getMessage()
        ]
        assert len(failures) == 1, failures  # two ticks, one line
        assert "HTTP 404 from http://fake:11434" in failures[0]
        assert "ollama-general" in failures[0]

    @pytest.mark.asyncio
    async def test_the_keeper_announces_residency(self, monkeypatch, caplog):
        import asyncio
        import logging

        plan = {
            "busy": False,
            "need_gib": 23.7,
            "headroom_gib": 37.2,
            "models": [{"resident": True}],
        }
        lifespan_mod, registry, guard, client, hint = self._harness(monkeypatch, plan)

        async def _stop(_seconds):
            raise asyncio.CancelledError

        monkeypatch.setattr(lifespan_mod.asyncio, "sleep", _stop)
        with (
            caplog.at_level(logging.INFO, logger=lifespan_mod.logger.name),
            pytest.raises(asyncio.CancelledError),
        ):
            await lifespan_mod._keep_preferred_residents(registry)
        assert "Preferred resident " + hint in caplog.text
        assert " on ollama-general (http://fake:11434): resident —" in caplog.text


def _candidate(
    backend_id: str, backend_type: str, resolved: str | None = None, url: str | None = None
):
    """A backend double whose `resolve_model` serves `resolved` (None = cannot serve)."""
    backend = MagicMock(id=backend_id, type=backend_type)
    backend.url = url or ("http://fake:8085" if backend_type == "omlx" else "http://fake:11434")
    backend.resolve_model = MagicMock(
        side_effect=lambda hint, r=resolved: r if r is not None else None
    )
    return backend


def _keeper_lock_worker(lock_path, barrier, results):
    import portal.platform.inference.router.lifespan as lifespan_mod

    barrier.wait(timeout=5)
    lease = lifespan_mod._try_acquire_preferred_resident_lock(Path(lock_path))
    results.put(lease is not None)
    if lease is not None:
        time.sleep(0.2)
        lifespan_mod._release_preferred_resident_lock(lease)
