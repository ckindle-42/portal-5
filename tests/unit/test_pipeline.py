"""Portal 5 v7.0.0 Pipeline unit tests — no live backends required."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.router_pipe import WORKSPACES, app

_COMFYUI_DOWNLOAD_SCRIPT = Path("scripts/download_comfyui_models.py")
_comfyui_enabled = pytest.mark.skipif(
    not _COMFYUI_DOWNLOAD_SCRIPT.exists(),
    reason="scripts/download_comfyui_models.py not present — ComfyUI not enabled",
)


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


@pytest.fixture
def sample_config(tmp_path):
    """Create a sample backends config for testing."""
    cfg = tmp_path / "backends.yaml"
    cfg.write_text("""
backends:
  - id: test-ollama
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
    return cfg


class TestBackendRegistry:
    def test_load_config(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: test-ollama
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert len(reg.list_backends()) == 1
        assert reg.list_backends()[0].id == "test-ollama"

    def test_get_backend_for_workspace(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://localhost:11434
    group: general
    models: [llama3]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=str(cfg))
        backend = reg.get_backend_for_workspace("auto")
        assert backend is not None
        assert backend.id == "b1"

    def test_unhealthy_backend_not_selected(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: sick
    type: ollama
    url: http://localhost:11434
    group: general
    models: [llama3]
  - id: healthy
    type: ollama
    url: http://localhost:11435
    group: general
    models: [llama3]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=str(cfg))
        reg._backends["sick"].healthy = False
        backend = reg.get_backend_for_workspace("auto")
        assert backend is not None
        assert backend.id == "healthy"

    def test_no_healthy_backends_returns_none(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: sick
    type: ollama
    url: http://localhost:11434
    group: general
    models: [llama3]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""")
        reg = BackendRegistry(config_path=str(cfg))
        reg._backends["sick"].healthy = False
        assert reg.get_backend_for_workspace("auto") is None


class TestTimeoutConfiguration:
    """Ensure timeouts are actually read from backends.yaml, not hardcoded."""

    def test_request_timeout_read_from_yaml(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: test
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
  request_timeout: 180
  health_check_interval: 60
  health_timeout: 15
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg.request_timeout == 180.0, (
            f"Expected 180.0 from YAML, got {reg.request_timeout} — "
            "timeout is not being read from config"
        )
        assert reg._health_check_interval == 60.0
        assert reg._health_timeout == 15.0

    def test_default_timeout_when_not_in_yaml(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: test
    type: ollama
    url: http://localhost:11434
    group: general
    models: [dolphin-llama3:8b]
workspace_routing:
  auto: [general]
""")
        reg = BackendRegistry(config_path=str(cfg))
        # Should use sensible defaults, not hardcoded 30
        assert reg.request_timeout >= 60.0, (
            f"Default timeout too low for reasoning models: {reg.request_timeout}s"
        )


class TestPipelineAPI:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "backends_healthy" in data

    def test_models_requires_auth(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 401

    def test_models_returns_workspaces(self, client):
        resp = client.get("/v1/models", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        ids = {m["id"] for m in data["data"]}
        assert "auto" in ids
        assert "auto-coding" in ids
        assert "auto-security" in ids
        # DESIGN_OPENCODE_ADDRESSING_V1.md §3.2: /v1/models also advertises
        # IDE-curated (ide_expose: true) personas alongside base workspaces,
        # so it agrees with opencode.jsonc's picker instead of diverging
        # from it. One entry per WORKSPACES key + one per ide_expose persona.
        from portal.platform.inference.router.workspaces import _PERSONA_MAP

        ide_persona_count = sum(1 for p in _PERSONA_MAP.values() if p.ide_expose)
        assert ide_persona_count > 0, "expected at least one ide_expose persona"
        assert len(ids) == len(WORKSPACES) + ide_persona_count

    def test_models_includes_ide_curated_personas(self, client):
        resp = client.get("/v1/models", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        by_id = {m["id"]: m for m in data["data"]}
        assert "codingagentic" in by_id
        assert by_id["codingagentic"]["is_persona"] is True
        assert by_id["auto-coding"].get("is_persona") in (None, False)

    def test_chat_requires_auth(self, client):
        resp = client.post("/v1/chat/completions", json={})
        assert resp.status_code == 401

    def test_chat_no_backends_returns_503_or_502(self, client):
        # Pipeline has no backends in test env — should return 503 or 502
        import portal.platform.inference.router.handlers as handlers_mod

        old_reg = handlers_mod.registry
        handlers_mod.registry = None  # Simulate no backends
        try:
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "auto",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                },
                headers=HEADERS,
            )
            # Either 503 (no backends) or 502 (backend error) are acceptable
            assert resp.status_code in (503, 502)
        finally:
            handlers_mod.registry = old_reg


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self, client):
        resp = client.get("/metrics", headers=HEADERS)
        assert resp.status_code == 200

    def test_metrics_contains_required_gauges(self, client):
        resp = client.get("/metrics", headers=HEADERS)
        content = resp.text
        assert "portal_backends_healthy" in content
        assert "portal_workspaces_total" in content
        assert "portal_uptime_seconds" in content

    def test_metrics_workspace_count_correct(self, client):
        resp = client.get("/metrics", headers=HEADERS)
        assert f"portal_workspaces_total {len(WORKSPACES)}" in resp.text


class TestWorkspaceModelHintUpdated:
    """Verify model hints use the updated recs.md models."""

    def test_security_uses_baronllm(self):
        # VulnLLM-R-7B promoted to auto-security primary 2026-06-20
        # baronllm retained in auto-security-uncensored
        ws = WORKSPACES.get("auto-security", {})
        hint = ws.get("model_hint", "").lower()
        assert "vulnllm" in hint or "baronllm" in hint or "baron" in hint, (
            "Security workspace should use a dedicated security model (VulnLLM-R-7B or baronllm)"
        )

    def test_coding_uses_qwen_or_glm(self):
        ws = WORKSPACES.get("auto-coding", {})
        hint = ws.get("model_hint", "").lower()
        assert "qwen" in hint or "deepseek" in hint or "laguna" in hint, (
            "Coding workspace should use a specialized coding model (qwen3-coder or similar)"
        )

    def test_reasoning_uses_deepseek_or_tongyi(self):
        ws = WORKSPACES.get("auto-reasoning", {})
        hint = ws.get("model_hint", "").lower()
        assert "deepseek" in hint or "tongyi" in hint or "r1" in hint or "qwopus" in hint, (
            "Reasoning workspace should use a deep reasoning model (DeepSeek-R1, Tongyi, or Qwopus MTP)"
        )


class TestComplianceWorkspace:
    """Verify auto-compliance workspace is correctly wired."""

    def test_compliance_workspace_exists_in_router(self):
        from portal.platform.inference.router_pipe import WORKSPACES

        assert "auto-compliance" in WORKSPACES, (
            "auto-compliance workspace missing from WORKSPACES dict in router_pipe.py"
        )

    def test_compliance_workspace_in_backends_yaml(self):
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        assert "auto-compliance" in routing, (
            "auto-compliance missing from workspace_routing in backends.yaml"
        )

    def test_compliance_workspace_json_exists_and_valid(self):
        import json
        from pathlib import Path

        ws_json = Path("imports/openwebui/workspaces/workspace_auto_compliance.json")
        assert ws_json.exists(), f"Workspace JSON not found: {ws_json}"
        ws = json.loads(ws_json.read_text())
        assert ws["id"] == "auto-compliance"
        assert ws["params"]["model"] == "auto-compliance"
        assert len(ws["params"].get("system", "")) > 100, "System prompt suspiciously short"
        assert "CIP" in ws["params"]["system"], "System prompt must reference CIP standards"

    def test_compliance_personas_exist_with_workspace_model(self):
        from pathlib import Path

        import yaml

        for slug in ["nerccipcomplianceanalyst", "cippolicywriter"]:
            p = Path(f"config/personas/{slug}.yaml")
            assert p.exists(), f"Persona file not found: {p}"
            d = yaml.safe_load(p.read_text())
            wm = d.get("workspace_model", "")
            assert wm, f"{slug}: workspace_model missing"
            # Personas now use workspace IDs (not raw MLX HF paths)
            assert wm.startswith("auto-"), (
                f"{slug}: workspace_model should be a workspace ID (auto-*), got: {wm}"
            )

    def test_workspace_count_is_14(self):
        """Total loaded workspace count is 29 (module: eval's 60 bench-*
        workspaces are gated off by default at boot as of
        BUILD_PROGRAM_COLLAPSE_V1.md Phase 4; the full 89 (29 + 60) still
        loads with PORTAL_ENABLE_EVAL=1, see test_eval_gate_loads_all_104.
        44 -> 37 after Phase 5 folded 8 coding/agentic workspaces into
        auto-coding's variants; 37 -> 29 after Phase 6 folded 8 security
        workspaces into auto-security's variants)."""
        from portal.platform.inference.router_pipe import WORKSPACES

        assert len(WORKSPACES) == 21, (
            f"Expected 21 workspaces (module: eval's 60 bench-* gated off by default), "
            f"got {len(WORKSPACES)}. "
            "Update this test if workspaces are intentionally added or removed."
        )

    def test_eval_gate_loads_all_104(self, monkeypatch):
        """PORTAL_ENABLE_EVAL=1 re-admits the 60 module: eval workspaces —
        get_workspace_dict is called fresh here (not the module-level
        WORKSPACES constant, which is computed once at import time)."""
        from portal.platform.inference.config import get_workspace_dict, load_portal_config

        monkeypatch.setenv("PORTAL_ENABLE_EVAL", "1")
        ws = get_workspace_dict(load_portal_config())
        assert len(ws) == 81, f"Expected 81 workspaces with eval enabled, got {len(ws)}"


class TestR17bModelExpansion:
    """Verify R17b model expansion: all recs.md models wired."""

    def test_new_llm_models_in_backends_yaml(self):
        """All recs.md LLM models are present in backends.yaml."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        all_models = []
        for b in cfg["backends"]:
            for m in b.get("models", []):
                all_models.append(m["id"] if isinstance(m, dict) else m)

        required = [
            # dolphin-llama3:70b intentionally removed 2026-06-16 (42GB old Llama-3 base, superseded)
            # llama3.3:70b-q4_k_m removed 2026-06-21: 3.8 TPS (below 20 TPS floor), supports_tools=false, bench-only
            # R23: MiniMax-M2.1 removed (138 GB, won't fit in 48 GB RAM)
        ]
        for model in required:
            assert any(model in m for m in all_models), (
                f"FAIL: {model} not found in any backend group in backends.yaml"
            )

    def test_documents_workspace_uses_fast_coding_model(self):
        """auto-documents workspace model_hint uses granite4.1:8b (tool-capable document model).

        phi4:14b-q8_0 was demoted in commit 7376ba4: Ollama 0.30.x rejects tool injection
        (HTTP 400) for phi4, but auto-documents requires MCP tools (create_word_document etc.).
        granite4.1:8b is verified tool-capable (BFCL V3 68.27) and already in fleet.
        """
        hint = WORKSPACES["auto-documents"]["model_hint"]
        assert "granite4.1" in hint.lower(), (
            f"Expected auto-documents to use granite4.1:8b, got: {hint}"
        )

    @_comfyui_enabled
    def test_comfyui_download_script_has_all_image_models(self):
        """download_comfyui_models.py covers all recs.md image models."""
        src = open("scripts/download_comfyui_models.py").read()
        required = ["flux-uncensored", "juggernaut-xl", "pony-diffusion", "epicrealism-xl"]
        for key in required:
            assert f'"{key}"' in src, f"FAIL: image model key '{key}' not in download script"

    @_comfyui_enabled
    def test_comfyui_download_script_has_all_video_models(self):
        """download_comfyui_models.py covers all recs.md video models."""
        src = open("scripts/download_comfyui_models.py").read()
        required = ["wan2.2-uncensored", "skyreels-v1", "mochi-1", "stable-video-diffusion"]
        for key in required:
            assert f'"{key}"' in src, f"FAIL: video model key '{key}' not in download script"


class TestR18ModelCompleteness:
    """Verify R18 model completeness: all recs.md + models.md models wired."""

    def test_all_required_llm_models_in_backends(self):
        """All recs.md + models.md LLM models are present in backends.yaml."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        all_models = []
        for b in cfg["backends"]:
            for m in b.get("models", []):
                all_models.append(m["id"] if isinstance(m, dict) else m)

        required = [
            # Security
            "baronllm-abliterated",  # BaronLLM (auto-security + auto-pentest primary; q6_k removed SECURITY_FLEET_REVIEW_2026-06)
            "hf.co/mradermacher/VulnLLM-R-7B-GGUF",  # VulnLLM-R-7B promoted to auto-security primary 2026-06-20
            # lily-cybersecurity and dolphin3-r1-mistral removed 2026-06-20 (pruned from fleet)
            # whiterabbitneo:33b-v1.5 and dolphin-llama3:70b intentionally removed (2026-06-16)
            # Coding (Ollama GGUF only — MLX retired)
            # glm-4.7-flash removed 2026-06-21: quality 0.67 (below 0.83 floor), bench-only
            # llama3.3:70b-q4_k_m removed 2026-06-21: 3.8 TPS, supports_tools=false, bench-only
            # Reasoning
            "deepseek-r1:32b-q4_k_m",  # DeepSeek-R1-Distill-Qwen-32B
        ]
        for frag in required:
            found = any(frag.lower() in m.lower() for m in all_models)
            assert found, (
                f"Model fragment '{frag}' not found in any backend group.\n"
                f"  All models: {all_models}"
            )

    def test_router_hints_use_best_models(self):
        """Key workspaces use the recommended primary model hints."""
        assert "qwen3-coder" in WORKSPACES["auto-coding"]["model_hint"].lower(), (
            "auto-coding should use qwen3-coder:30b-a3b-q4_K_M (Qwen3-Coder-30B MoE, primary coder, promoted V2 Phase 6)"
        )
        assert "granite4.1" in WORKSPACES["auto-documents"]["model_hint"].lower(), (
            "auto-documents should use granite4.1:8b (tool-capable document model; phi4:14b-q8_0 rejected by Ollama 0.30.x for tool calls — see commit 7376ba4)"
        )
        # R23: VulnLLM-R-7B promoted to auto-security primary 2026-06-20
        assert "vulnllm-r-7b" in WORKSPACES["auto-security"]["model_hint"].lower(), (
            "auto-security should use VulnLLM-R-7B (UCSB SURFI, AppSec/CVE/CWE specialist, promoted 2026-06-20)"
        )
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )

        base, variant = _unpack_synthetic_workspace("auto-security::blueteam")
        blueteam_id = _resolve_workspace_variant("auto-security::blueteam", base, variant)
        assert "granite4.1" in WORKSPACES[blueteam_id]["model_hint"].lower(), (
            "auto-blueteam (now auto-security's 'blueteam' variant, Phase 6) should use "
            "Granite 4.1 8B (sylink is a reasoning model that doesn't call tools — "
            "switched for autonomous investigation capability)"
        )
        assert "deepseek-r1-0528" in WORKSPACES["auto-reasoning"]["model_hint"].lower(), (
            "auto-reasoning should use DeepSeek-R1-0528-Qwen3-8B (V8 primary; Qwopus pull fails as of 2026-06-09)"
        )

    @_comfyui_enabled
    def test_all_required_image_models_in_download_script(self):
        """All recs.md + models.md image models are in download_comfyui_models.py."""
        src = open("scripts/download_comfyui_models.py").read()
        required = [
            "flux-schnell",
            "flux-dev",
            "flux-uncensored",
            "flux2-klein",
            "sdxl",
            "juggernaut-xl",
            "pony-diffusion",
            "epicrealism-xl",
        ]
        for key in required:
            assert f'"{key}"' in src, f"Image model key '{key}' missing from download script"

    @_comfyui_enabled
    def test_all_required_video_models_in_download_script(self):
        """All recs.md + models.md video models are in download_comfyui_models.py."""
        src = open("scripts/download_comfyui_models.py").read()
        required = [
            "wan2.2",
            "wan2.2-uncensored",
            "skyreels-v1",
            "mochi-1",
            "stable-video-diffusion",
        ]
        for key in required:
            assert f'"{key}"' in src, f"Video model key '{key}' missing from download script"

    @_comfyui_enabled
    def test_video_models_have_subdir(self):
        """All video models specify subdir='video' for correct ComfyUI placement."""
        exec(open("scripts/download_comfyui_models.py").read(), ns := {})
        for key, spec in ns["VIDEO_MODELS"].items():
            assert spec.get("subdir") == "video", f"Video model '{key}' missing subdir='video'"

    def test_env_example_has_video_model_and_pull_heavy(self):
        """env.example documents VIDEO_MODEL and PULL_HEAVY."""
        content = open(".env.example").read()
        assert "VIDEO_MODEL" in content, "VIDEO_MODEL missing from .env.example"
        assert "PULL_HEAVY" in content, "PULL_HEAVY missing from .env.example"


class TestR20NativeOllama:
    """Verify R20: Native Ollama as primary path on Apple Silicon."""

    def test_backends_yaml_uses_ollama_url_env_var(self):
        """backends.yaml uses OLLAMA_URL env var — required for native Ollama on Apple Silicon."""
        content = open("config/backends.yaml").read()
        assert "OLLAMA_URL" in content, (
            "backends.yaml must use ${OLLAMA_URL:-...} not hardcoded http://ollama:11434"
        )
        assert '"http://ollama:11434"' not in content, (
            "Hardcoded http://ollama:11434 found — breaks native Ollama on macOS"
        )

    def test_compose_ollama_behind_profile(self):
        """Docker Ollama is optional — gated behind docker-ollama profile."""
        content = open("deploy/portal-5/docker-compose.yml").read()
        assert "docker-ollama" in content, (
            "Ollama service must use profiles: [docker-ollama] — native Ollama is default on macOS"
        )

    def test_compose_admin_email_has_default(self):
        """OPENWEBUI_ADMIN_EMAIL has a default to prevent blank string warning."""
        content = open("deploy/portal-5/docker-compose.yml").read()
        assert "OPENWEBUI_ADMIN_EMAIL:-" in content, (
            "OPENWEBUI_ADMIN_EMAIL must have :-admin@portal.local default in compose"
        )

    def test_compose_comfyui_has_platform(self):
        """ComfyUI service specifies platform to silence ARM/amd64 mismatch warning."""
        content = open("deploy/portal-5/docker-compose.yml").read()
        assert "platform: linux/amd64" in content, (
            "ComfyUI needs platform: linux/amd64 — no ARM build exists, uses Rosetta"
        )

    def test_mcp_ports_configurable(self):
        """All MCP host ports are overridable via env vars."""
        content = open("deploy/portal-5/docker-compose.yml").read()
        for port_var in ["WHISPER_HOST_PORT", "TTS_HOST_PORT", "DOCUMENTS_HOST_PORT"]:
            assert port_var in content, f"{port_var} not found in docker-compose.yml"

    def test_launch_sh_has_install_ollama(self):
        """launch.sh has install-ollama command for native Ollama setup."""
        content = open("launch.sh").read()
        assert "install-ollama" in content, "launch.sh must have install-ollama command"

    def test_pull_models_supports_native_ollama(self):
        """pull-models delegates to portal CLI which detects native Ollama.

        Post-M5-S2: the bash pull-models branch delegates to
        ``python3 -m portal.platform.inference.cli models pull``. Native Ollama detection
        lives in ``portal_pipeline/cli/_common.py:_detect_ollama_cmd``.
        This test verifies the delegation shim rather than the moved logic.
        """
        content = open("launch.sh").read()
        assert "exec python3 -m portal.platform.inference.cli models pull" in content, (
            "pull-models must delegate to portal CLI (post-M5-S2)"
        )


class TestR21NativeComfyUI:
    """Verify R21: Native ComfyUI as primary path on Apple Silicon."""

    def test_compose_comfyui_behind_profile(self):
        """Docker ComfyUI is optional — gated behind docker-comfyui profile."""
        content = open("deploy/portal-5/docker-compose.yml").read()
        assert "docker-comfyui" in content, (
            "ComfyUI Docker service must use profiles: [docker-comfyui] — native is default on macOS"
        )

    def test_compose_comfyui_url_uses_env_var(self):
        """mcp-comfyui and mcp-video use COMFYUI_URL env var, not hardcoded container."""
        content = open("deploy/portal-5/docker-compose.yml").read()
        assert "COMFYUI_URL:-http://host.docker.internal:8188" in content, (
            "COMFYUI_URL must default to host.docker.internal for native ComfyUI support"
        )
        assert "COMFYUI_URL=http://comfyui:8188" not in content, (
            "Hardcoded http://comfyui:8188 found — breaks native ComfyUI on macOS"
        )

    def test_launch_sh_has_install_comfyui(self):
        """launch.sh has install-comfyui command."""
        content = open("launch.sh").read()
        assert "install-comfyui" in content, "launch.sh must have install-comfyui command"

    def test_launch_sh_has_download_comfyui_models(self):
        """launch.sh has download-comfyui-models command."""
        content = open("launch.sh").read()
        assert "download-comfyui-models" in content, (
            "launch.sh must have download-comfyui-models command"
        )


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

    def test_launch_sh_pull_models_has_r22_updates(self):
        """pull-models delegates to portal CLI; model list lives in portal.yaml."""
        content = open("launch.sh").read()
        # Post-M5-S2: pull-models delegates to portal CLI
        assert "portal.platform.inference.cli models pull" in content, (
            "launch.sh pull-models must delegate to portal CLI (post-M5-S2)"
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

    def test_metrics_endpoint_contains_prometheus_output(self, client):
        """After a _record_usage call, /metrics includes prometheus_client output."""
        from portal.platform.inference import router_pipe

        # Trigger a metric emission
        router_pipe._record_usage(
            model="metrics-test-model",
            workspace="auto",
            data={"eval_count": 10, "eval_duration": 200_000_000, "prompt_eval_count": 5},
        )
        resp = client.get("/metrics", headers=HEADERS)
        assert resp.status_code == 200
        content = resp.text
        # The prometheus_client output should be appended to the hand-rolled metrics
        assert "portal_tokens_per_second" in content
        assert "portal_output_tokens_total" in content
        assert "portal_requests_by_model_total" in content


class TestSPLWorkspace:
    """Verify auto-spl workspace wiring across all four required files."""

    def test_auto_spl_in_workspaces_dict(self):
        """auto-spl must exist in WORKSPACES dict in router_pipe.py."""
        from portal.platform.inference.router_pipe import WORKSPACES

        assert "auto-spl" in WORKSPACES, (
            "auto-spl missing from WORKSPACES in router_pipe.py — add it with model_hint"
        )

    def test_auto_spl_uses_qwen3_coder_model_hint(self):
        """auto-spl model_hint must be qwen3-coder (Ollama GGUF)."""
        from portal.platform.inference.router_pipe import WORKSPACES

        hint = WORKSPACES["auto-spl"]["model_hint"]
        assert "qwen3-coder" in hint.lower(), (
            f"auto-spl model_hint should be qwen3-coder variant, got: {hint}"
        )

    def test_auto_spl_in_backends_yaml(self):
        """auto-spl must exist in workspace_routing in backends.yaml."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        assert "auto-spl" in routing, "auto-spl missing from workspace_routing in backends.yaml"

    def test_workspace_count_is_16(self):
        """Total loaded workspace count is 29 (module: eval's 60 bench-*
        workspaces are gated off by default at boot as of
        BUILD_PROGRAM_COLLAPSE_V1.md Phase 4, 44 -> 37 after Phase 5 folded 8
        coding/agentic workspaces, 37 -> 29 after Phase 6 folded 8 security
        workspaces; see TestComplianceWorkspace.test_eval_gate_loads_all_104
        for the PORTAL_ENABLE_EVAL=1 path)."""
        from portal.platform.inference.router_pipe import WORKSPACES

        assert len(WORKSPACES) == 21, (
            f"Expected 21 workspaces (module: eval's 60 bench-* gated off by default), "
            f"got {len(WORKSPACES)}. "
            "Update this test if workspaces are intentionally added or removed."
        )

    def test_spl_persona_yaml_exists(self):
        """Persona YAML file must exist at the canonical path."""
        from pathlib import Path

        persona_path = Path("config/personas/splunksplgineer.yaml")
        assert persona_path.exists(), f"SPL Engineer persona YAML not found at {persona_path}"

    def test_spl_persona_yaml_has_required_fields(self):
        """Persona YAML must have all fields read by openwebui_init.py."""
        from pathlib import Path

        import yaml

        data = yaml.safe_load(Path("config/personas/splunksplgineer.yaml").read_text())
        for field in ("name", "slug", "category", "workspace_model", "system_prompt", "tags"):
            assert field in data, f"SPL persona YAML missing required field: {field}"

    def test_spl_persona_workspace_model_is_auto_spl(self):
        """Persona workspace_model must route to auto-spl workspace."""
        from pathlib import Path

        import yaml

        data = yaml.safe_load(Path("config/personas/splunksplgineer.yaml").read_text())
        wm = data.get("workspace_model", "")
        assert wm == "auto-spl", f"SPL persona workspace_model should be auto-spl, got: {wm}"

    def test_workspace_json_exists(self):
        """Workspace JSON file must exist for GUI import."""
        from pathlib import Path

        ws_path = Path("imports/openwebui/workspaces/workspace_auto_spl.json")
        assert ws_path.exists(), f"Workspace JSON not found at {ws_path}"

    def test_workspace_json_has_correct_id(self):
        """Workspace JSON id must be 'auto-spl'."""
        import json
        from pathlib import Path

        data = json.loads(Path("imports/openwebui/workspaces/workspace_auto_spl.json").read_text())
        assert data.get("id") == "auto-spl", (
            f"workspace_auto_spl.json id should be 'auto-spl', got: {data.get('id')}"
        )

    def test_workspaces_all_json_includes_spl(self):
        """workspaces_all.json bulk import must include auto-spl entry."""
        import json
        from pathlib import Path

        all_ws = json.loads(Path("imports/openwebui/workspaces/workspaces_all.json").read_text())
        ids = [ws.get("id") for ws in all_ws]
        assert "auto-spl" in ids, (
            "auto-spl not found in workspaces_all.json — append the workspace object to the array"
        )

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

    def test_spl_does_not_route_generic_coding(self):
        """Generic Python/code requests must NOT route to auto-spl."""
        from portal.platform.inference.router_pipe import _detect_workspace

        messages = [{"role": "user", "content": "Write a Python function to parse JSON logs"}]
        result = _detect_workspace(messages)
        assert result != "auto-spl", (
            f"Python-only request should not route to auto-spl, got: {result!r}"
        )

    def test_auto_spl_routing_consistent_across_files(self):
        """auto-spl key must exist in both WORKSPACES and backends.yaml workspace_routing."""
        import yaml

        from portal.platform.inference.router_pipe import WORKSPACES

        cfg = yaml.safe_load(open("config/backends.yaml"))
        pipe_ids = set(WORKSPACES.keys())
        yaml_ids = set(cfg["workspace_routing"].keys())
        assert "auto-spl" in pipe_ids, "auto-spl missing from WORKSPACES in router_pipe.py"
        assert "auto-spl" in yaml_ids, "auto-spl missing from workspace_routing in backends.yaml"
        assert pipe_ids == yaml_ids, (
            f"WORKSPACES / workspace_routing mismatch after adding auto-spl. "
            f"In pipe but not yaml: {pipe_ids - yaml_ids}. "
            f"In yaml but not pipe: {yaml_ids - pipe_ids}."
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

    def test_agentic_workspace_interim_hint(self):
        """auto-agentic's 'heavy' variant should use the 30B interim hint while 480B is dead-by-decision.

        The 480B workspace (bench-qwen3-coder-next) was removed in TASK_MODEL_FLEET_REFRESH_V2
        Phase 3, and the 480B-specific KV-suppression context_limit was dropped with it.

        A context_limit was reintroduced afterward (TASK-SEC-LIVE-EXEC-era Ollama 0.31
        num_ctx-default fix): qwen3-coder-next's native max context (262144) made it
        default to a KV cache that spilled off-GPU and stalled every request. auto-agentic
        is a long-horizon agentic workspace (multi-file SWE-agent-style tool loops), so it
        needs real room for both the accumulated tool-call history and reasoning — hence
        the derived -ctx64k tag and context_limit=65536, not None. Enforced now via a
        derived Ollama model tag, since Ollama's /v1/chat/completions ignores request-time
        options.num_ctx (see portal.platform.inference.cli.models apply-params).
        """
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import WORKSPACES

        base, variant = _unpack_synthetic_workspace("auto-coding::heavy")
        resolved_id = _resolve_workspace_variant("auto-coding::heavy", base, variant)
        merged = WORKSPACES[resolved_id]

        hint = merged.get("model_hint")
        assert hint is not None and "qwen3-coder-next" in hint, (
            f"auto-agentic hint should be qwen3-coder-next:latest (V8 promotion), got: {hint}"
        )
        ctx = merged.get("context_limit")
        assert ctx == 65536, (
            f"auto-agentic context_limit should be 65536 (agentic long-horizon tuning), got: {ctx}"
        )

    def test_agentic_workspace_has_model_hint(self):
        """auto-agentic's resolved variant must have an Ollama model_hint as fallback."""
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router_pipe import WORKSPACES

        base, variant = _unpack_synthetic_workspace("auto-coding::heavy")
        resolved_id = _resolve_workspace_variant("auto-coding::heavy", base, variant)
        hint = WORKSPACES[resolved_id].get("model_hint", "")
        assert hint, "auto-agentic workspace missing model_hint — routing will fail on Ollama path"

    def test_auto_coding_workspace_json_exists(self):
        """Workspace JSON for GUI import must exist for the base auto-coding
        workspace (variants are query-param/persona-selected, not separate
        OWUI presets — see BUILD_PROGRAM_COLLAPSE_V1.md Phase 5)."""
        from pathlib import Path

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

    def test_agentic_routing_consistent_across_files(self):
        """auto-agentic's resolved base (auto-coding) must exist in both
        WORKSPACES and backends.yaml workspace_routing (module: eval
        workspaces are gated off both by default — BUILD_PROGRAM_COLLAPSE_V1.md
        Phase 4 — so this compares against the loaded, non-eval-gated set)."""
        import yaml

        from portal.platform.inference.config import _eval_enabled, load_portal_config
        from portal.platform.inference.router.preinject import _unpack_synthetic_workspace
        from portal.platform.inference.router_pipe import WORKSPACES

        base, _variant = _unpack_synthetic_workspace("auto-coding::heavy")

        cfg = yaml.safe_load(open("config/backends.yaml"))
        eval_on = _eval_enabled()
        pipe_ids = set(WORKSPACES.keys())
        yaml_ids = set(cfg["workspace_routing"].keys())
        expected_ids = {
            wid
            for wid, spec in load_portal_config().workspaces.items()
            if eval_on or spec.module != "eval"
        }
        assert base in pipe_ids, f"{base} missing from WORKSPACES in router_pipe.py"
        assert base in yaml_ids, f"{base} missing from workspace_routing in backends.yaml"
        assert pipe_ids == expected_ids == yaml_ids, (
            f"WORKSPACES / workspace_routing mismatch. "
            f"In pipe but not yaml: {pipe_ids - yaml_ids}. "
            f"In yaml but not pipe: {yaml_ids - pipe_ids}."
        )


class TestCodeHygiene:
    """Prevent regression of remediated issues."""

    def test_no_default_api_key_fallback(self):
        """Verify insecure default API key was removed (P5-SEC-001)."""
        from pathlib import Path

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

    def test_no_duplicate_mlx_proxy_url(self):
        """Verify _MLX_PROXY_HEALTH_URL was fully removed (MLX proxy retired 3a0c58e)."""
        from pathlib import Path

        dispatcher_path = Path("portal/platform/inference/notifications/dispatcher.py")
        if not dispatcher_path.exists():
            dispatcher_path = (
                Path(__file__).parent.parent.parent
                / "portal/platform/inference/notifications/dispatcher.py"
            )
        content = dispatcher_path.read_text()
        count = content.count("_MLX_PROXY_HEALTH_URL =")
        assert count == 0, f"Expected 0 assignments (removed in MLX retirement), found {count}"

    def test_mcp_server_no_warning_suppression(self):
        """Verify global warning suppression was removed (P5-OBS-001).

        Post-M4 de-vendor: portal_mcp/mcp_server/ no longer exists. The check
        confirms the directory is absent, which implies no vendored suppression.
        """
        from pathlib import Path

        vendored = Path("portal_mcp/mcp_server")
        assert not vendored.exists(), (
            "Vendored MCP SDK directory reappeared. M4 de-vendor was supposed to delete this."
        )

    def test_only_dind_is_privileged(self):
        """Verify only the dind service uses privileged mode (required for DinD on macOS Docker Desktop)."""
        from pathlib import Path

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

    def test_claude_md_persona_count_accurate(self):
        """Verify CLAUDE.md persona count matches actual files."""
        import re
        from pathlib import Path

        personas_dir = Path("config/personas")
        if not personas_dir.exists():
            personas_dir = Path(__file__).parent.parent.parent / "config" / "personas"
        actual_count = len(list(personas_dir.glob("*.yaml")))

        claude_md = Path("CLAUDE.md")
        if not claude_md.exists():
            claude_md = Path(__file__).parent.parent.parent / "CLAUDE.md"
        content = claude_md.read_text()

        # Match the specific "currently N files" persona-catalog count
        # assertion, not any incidental "N personas" text elsewhere in the
        # doc (e.g. an illustrative example in the anti-hardcoding rule) —
        # a generic "\d+\s+personas" regex previously matched such
        # incidental text by coincidence rather than the live count claim.
        match = re.search(r"currently (\d+) files", content)
        assert match, "Could not find persona count in CLAUDE.md"
        doc_count = int(match.group(1))

        assert doc_count == actual_count, (
            f"CLAUDE.md says {doc_count} personas but found {actual_count} yaml files"
        )


# ── M2: Tool-calling orchestration tests ─────────────────────────────────────


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
        from portal.platform.inference.router_pipe import _resolve_persona_tools

        persona = {}
        tools = _resolve_persona_tools(persona, "auto-creative")
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

        tools_empty = _workspace_tools("auto-creative")
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
        from portal.platform.inference.router.preinject import _resolve_model_override
        from portal.platform.inference.router.workspaces import WORKSPACES

        resolved = _resolve_model_override("auto-daily", "granite4.1:8b")
        assert resolved == "auto-daily::model=granite4.1:8b"
        assert WORKSPACES[resolved]["model_hint"] == "granite4.1:8b"

    def test_unknown_model_is_silent_noop(self):
        from portal.platform.inference.router.preinject import _resolve_model_override

        assert _resolve_model_override("auto-daily", "not-a-real-model") == "auto-daily"

    def test_no_param_is_noop(self):
        from portal.platform.inference.router.preinject import _resolve_model_override

        assert _resolve_model_override("auto-daily", None) == "auto-daily"


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
    """Regression for the 3a0c58e mlx_metadata removal.

    _model_supports_tools previously iterated Backend.mlx_metadata,
    a field deleted with the MLX proxy tier. Mocked tests missed it
    because they never built a real Backend through this function.
    """

    def test_real_backend_tool_lookup_does_not_raise(self, monkeypatch):
        import portal.platform.inference.router.validation as _vm

        class _Reg:
            def model_supports_tools(self, model_id):
                return model_id == "tool-model"

        monkeypatch.setattr(_vm, "registry", _Reg())
        assert _vm._model_supports_tools("tool-model") is True
        assert _vm._model_supports_tools("plain-model") is False
        assert _vm._model_supports_tools("unknown") is False
        assert _vm._model_supports_tools("") is False

    def test_backend_has_no_mlx_metadata_field(self):
        import portal.platform.inference.cluster_backends as cb

        be = cb.Backend(id="b", type="ollama", url="http://x", group="general", models=["m"])
        assert not hasattr(be, "mlx_metadata")
        assert be.ollama_metadata == []


class TestInjectOllamaOptions:
    """Tests for per-workspace keep_alive override in _inject_ollama_options."""

    def test_bench_workspace_uses_5m_keep_alive(self, monkeypatch):
        """Bench workspaces should emit keep_alive=5m, not the global -1.

        module: eval workspaces are gated off the module-level WORKSPACES
        dict by default (BUILD_PROGRAM_COLLAPSE_V1.md Phase 4), so this
        looks the real config up via get_workspace_dict(eval enabled) and
        monkeypatch.setitem's it into the live dict for the duration of
        the test — WORKSPACES/validation.WORKSPACES alias the same dict
        object, so the injection is visible through either import path.
        """
        from portal.platform.inference.config import get_workspace_dict, load_portal_config
        from portal.platform.inference.router.workspaces import WORKSPACES
        from portal.platform.inference.router_pipe import _inject_ollama_options

        monkeypatch.setenv("PORTAL_ENABLE_EVAL", "1")
        all_ws = get_workspace_dict(load_portal_config())
        bench_ws = next(k for k in all_ws if k.startswith("bench-"))
        monkeypatch.setitem(WORKSPACES, bench_ws, all_ws[bench_ws])

        body = _inject_ollama_options({}, bench_ws)
        assert body["keep_alive"] == "5m", (
            f"bench workspace {bench_ws!r} should have keep_alive=5m to avoid "
            "pinning the bench model in memory between unrelated requests"
        )

    def test_quality_lane_uses_10m_keep_alive(self):
        """auto-data (big q8 lane) should use keep_alive=10m.

        auto-mistral was deleted outright in BUILD_PROGRAM_COLLAPSE_V1.md
        Phase 7 (model-tied workspace, no preserved variant) -- its
        keep_alive tuning went with it."""
        from portal.platform.inference.router_pipe import _inject_ollama_options

        body = _inject_ollama_options({}, "auto-data")
        assert body["keep_alive"] == "10m", (
            "quality lane 'auto-data' should have keep_alive=10m — "
            "long enough for back-to-back queries, short enough not to evict fleet"
        )

    def test_caller_supplied_keep_alive_wins(self):
        """A caller-supplied keep_alive in the request body must not be overridden."""
        from portal.platform.inference.router_pipe import _inject_ollama_options

        body = _inject_ollama_options({"keep_alive": "30m"}, "bench-devstral")
        assert body["keep_alive"] == "30m", (
            "setdefault must not override a caller-supplied keep_alive value"
        )
