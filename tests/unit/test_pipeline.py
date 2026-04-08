"""Portal 5.2.1 Pipeline unit tests — no live backends required."""

import pytest
from fastapi.testclient import TestClient

from portal_pipeline.cluster_backends import BackendRegistry
from portal_pipeline.router_pipe import WORKSPACES, app


# Use TestClient with context manager to trigger lifespan
# Or set up registry before tests
@pytest.fixture(scope="session", autouse=True)
def setup_registry():
    """Initialize registry before tests run."""
    # Manually create registry for tests
    reg = BackendRegistry()
    # Replace module-level registry
    import portal_pipeline.router_pipe as pipe_module

    pipe_module.registry = reg
    yield
    pipe_module.registry = None


@pytest.fixture
def client():
    """Create a test client with proper lifespan."""
    with TestClient(app) as test_client:
        yield test_client


HEADERS = {"Authorization": "Bearer portal-pipeline"}


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
        assert len(ids) == len(WORKSPACES)

    def test_chat_requires_auth(self, client):
        resp = client.post("/v1/chat/completions", json={})
        assert resp.status_code == 401

    def test_chat_no_backends_returns_503_or_502(self, client):
        # Pipeline has no backends in test env — should return 503 or 502
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
        ws = WORKSPACES.get("auto-security", {})
        assert (
            "baronllm" in ws.get("model_hint", "").lower()
            or "baron" in ws.get("model_hint", "").lower()
            or "xploiter" in ws.get("model_hint", "").lower()
        ), "Security workspace should use a dedicated security model"

    def test_coding_uses_qwen_or_glm(self):
        ws = WORKSPACES.get("auto-coding", {})
        hint = ws.get("model_hint", "").lower()
        assert "qwen" in hint or "glm" in hint or "deepseek" in hint, (
            "Coding workspace should use a specialized coding model"
        )

    def test_reasoning_uses_deepseek_or_tongyi(self):
        ws = WORKSPACES.get("auto-reasoning", {})
        hint = ws.get("model_hint", "").lower()
        assert "deepseek" in hint or "tongyi" in hint or "r1" in hint, (
            "Reasoning workspace should use a deep reasoning model"
        )


class TestComplianceWorkspace:
    """Verify auto-compliance workspace is correctly wired — MLX-first."""

    def test_compliance_workspace_exists_in_router(self):
        from portal_pipeline.router_pipe import WORKSPACES

        assert "auto-compliance" in WORKSPACES, (
            "auto-compliance workspace missing from WORKSPACES dict in router_pipe.py"
        )

    def test_compliance_workspace_uses_mlx_model_hint(self):
        """auto-compliance must use MLX Qwen3.5-35B as primary — not an Ollama GGUF tag."""
        from portal_pipeline.router_pipe import WORKSPACES

        hint = WORKSPACES["auto-compliance"].get("mlx_model_hint", "")
        assert hint, "auto-compliance workspace missing mlx_model_hint"
        assert "Qwen3.5-35B-A3B" in hint, (
            f"auto-compliance should use Qwen3.5-35B-A3B Claude-distilled for long-context policy analysis, "
            f"got: {hint}"
        )

    def test_compliance_workspace_in_backends_yaml(self):
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        assert "auto-compliance" in routing, (
            "auto-compliance missing from workspace_routing in backends.yaml"
        )
        groups = routing["auto-compliance"]
        assert groups[0] == "mlx", (
            f"auto-compliance first routing group must be 'mlx' (Apple Silicon primary), got: {groups}"
        )
        assert "reasoning" in groups, (
            f"auto-compliance must include reasoning group for Ollama fallback, got: {groups}"
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

    def test_compliance_mlx_model_in_mlx_backend(self):
        """Qwen3.5-35B-A3B Claude-distilled must be in an MLX backend — it's the primary routing target."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
        assert mlx_backends, "No MLX backend in backends.yaml"
        all_models = []
        for b in mlx_backends:
            all_models.extend(b.get("models", []))
        assert any("Qwen3.5-35B-A3B" in m for m in all_models), (
            f"Qwen3.5-35B-A3B Claude-distilled not in any MLX backend models: {all_models}\n"
            "This is the primary model for auto-compliance — must be present."
        )

    def test_compliance_personas_exist_with_mlx_model(self):
        from pathlib import Path

        import yaml

        for slug in ["nerccipcomplianceanalyst", "cippolicywriter"]:
            p = Path(f"config/personas/{slug}.yaml")
            assert p.exists(), f"Persona file not found: {p}"
            d = yaml.safe_load(p.read_text())
            assert d.get("workspace_model"), f"{slug}: workspace_model missing"
            assert "Qwen3.5-35B-A3B" in d["workspace_model"], (
                f"{slug}: should use Qwen3.5-35B-A3B Claude-distilled, got: {d['workspace_model']}"
            )

    def test_workspace_count_is_14(self):
        """Total workspace count is now 17 (was 14 after auto-compliance, 15 with auto-mistral, 16 with auto-spl, 17 with auto-agentic)."""
        from portal_pipeline.router_pipe import WORKSPACES

        assert len(WORKSPACES) == 17, (
            f"Expected 17 workspaces after adding auto-agentic, got {len(WORKSPACES)}"
        )

    def test_compliance_routing_matches_reasoning_pattern(self):
        """auto-compliance routing must follow the same pattern as other reasoning workspaces."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg["workspace_routing"]
        # All reasoning-class workspaces start with mlx
        for ws in ["auto-reasoning", "auto-research", "auto-data", "auto-compliance"]:
            groups = routing.get(ws, [])
            assert groups and groups[0] == "mlx", (
                f"{ws} must prefer mlx group first (Apple Silicon primary), got: {groups}"
            )


class TestR17bModelExpansion:
    """Verify R17b model expansion: all recs.md models wired."""

    def test_new_llm_models_in_backends_yaml(self):
        """All recs.md LLM models are present in backends.yaml."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        all_models = []
        for b in cfg["backends"]:
            all_models.extend(b.get("models", []))

        required = [
            # R23: dolphin-3-llama3-70b-GGUF → imported as dolphin-llama3:70b-q4_k_m
            "dolphin-llama3:70b",
            # R23: meta-llama → imported as llama3.3:70b-q4_k_m (bartowski rehost)
            "llama3.3:70b",
            # R23: MiniMax-M2.1 removed (138 GB, won't fit in 48 GB RAM)
        ]
        for model in required:
            assert any(model in m for m in all_models), (
                f"FAIL: {model} not found in any backend group in backends.yaml"
            )

    def test_documents_workspace_uses_fast_coding_model(self):
        """auto-documents workspace model_hint is qwen3.5:9b (MiniMax removed due to 138 GB size)."""
        hint = WORKSPACES["auto-documents"]["model_hint"]
        assert "qwen3.5:9b" in hint, f"Expected auto-documents to use qwen3.5:9b, got: {hint}"

    def test_comfyui_download_script_has_all_image_models(self):
        """download_comfyui_models.py covers all recs.md image models."""
        src = open("scripts/download_comfyui_models.py").read()
        required = ["flux-uncensored", "juggernaut-xl", "pony-diffusion", "epicrealism-xl"]
        for key in required:
            assert f'"{key}"' in src, f"FAIL: image model key '{key}' not in download script"

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
        all_models = [m for b in cfg["backends"] for m in b.get("models", [])]

        required = [
            # Security
            "baronllm:q6_k",  # R23: BaronLLM_Offensive now imported as baronllm:q6_k
            "lily-cybersecurity:7b-q4_k_m",  # R23: exact import name
            "dolphin3-r1-mistral:24b-q4_k_m",  # R23: updated to bartowski rehost
            "whiterabbitneo:33b-v1.5",  # R23: updated from 33b to 33b-v1.5
            "dolphin-llama3:70b",  # R23: dolphin-2.9.1-llama-3-70b
            # Coding
            # R20: Qwen3-Coder-Next-GGUF replaced with MLX (sharded GGUF incompatible with Ollama)
            "Qwen3-Coder-Next-4bit",
            "GLM-4.7-Flash",
            "deepseek-coder-v2-lite",  # R23: updated to bartowski rehost
            # R23: MiniMax-M2.1 removed (138 GB, won't fit in 48 GB RAM)
            "llama3.3:70b-q4_k_m",  # R23: updated to bartowski rehost
            # Reasoning
            "deepseek-r1:32b-q4_k_m",  # R23: DeepSeek-R1-Distill-Qwen-32B
        ]
        for frag in required:
            found = any(frag.lower() in m.lower() for m in all_models)
            assert found, (
                f"Model fragment '{frag}' not found in any backend group.\n"
                f"  All models: {all_models}"
            )

    def test_router_hints_use_best_models(self):
        """Key workspaces use the recommended primary model hints."""
        # R20: Qwen3-Coder-Next-GGUF replaced with MLX backend
        assert "qwen3-coder-next" in WORKSPACES["auto-coding"]["model_hint"].lower(), (
            "auto-coding should prefer Qwen3-Coder-Next MLX"
        )
        # R23: MiniMax-M2.1 removed (138 GB, won't fit in 48 GB); use qwen3.5:9b
        assert "qwen3.5:9b" in WORKSPACES["auto-documents"]["model_hint"], (
            "auto-documents should use qwen3.5:9b (MiniMax removed)"
        )
        # R23: baronllm:q6_k is the imported GGUF model
        assert "baronllm" in WORKSPACES["auto-security"]["model_hint"].lower(), (
            "auto-security should use baronllm as primary"
        )
        assert "lily" in WORKSPACES["auto-blueteam"]["model_hint"].lower(), (
            "auto-blueteam should use lily-cybersecurity"
        )
        assert "deepseek-r1" in WORKSPACES["auto-reasoning"]["model_hint"].lower(), (
            "auto-reasoning should use deepseek-r1"
        )

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
        assert "brew install ollama" in content, "install-ollama must use brew install ollama"

    def test_pull_models_supports_native_ollama(self):
        """pull-models detects native Ollama, not just docker exec portal5-ollama."""
        content = open("launch.sh").read()
        assert "command -v ollama" in content, "pull-models must detect native ollama binary"
        # R23: Uses _pull_model with _ollama_cmd helper for native/Docker detection
        assert "_pull_model" in content, (
            "pull-models must use _pull_model() that handles both native and Docker via _ollama_cmd"
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
        assert "comfyanonymous/ComfyUI" in content, (
            "install-comfyui must clone from comfyanonymous/ComfyUI"
        )

    def test_launch_sh_has_download_comfyui_models(self):
        """launch.sh has download-comfyui-models command."""
        content = open("launch.sh").read()
        assert "download-comfyui-models" in content, (
            "launch.sh must have download-comfyui-models command"
        )
        assert "download_comfyui_models.py" in content, (
            "download-comfyui-models must call scripts/download_comfyui_models.py"
        )


class TestR22CodingModelUpdates:
    """Verify R22: Coding model updates from models2.md review."""

    def test_coding_model_updates_r22(self):
        """R22 coding model updates: Llama 3.3 replaces 3.1, Qwen3.5-9B added."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        coding = next(b for b in cfg["backends"] if b["id"] == "ollama-coding")
        models = coding["models"]

        # Llama 3.3 should be present (upgraded from 3.1)
        assert any("llama3.3" in m.lower() for m in models), (
            "Llama 3.3-70B missing from coding group — should have replaced 3.1"
        )

        # Llama 3.1 should be gone
        assert not any("Meta-Llama-3.1-70B" in m for m in models), (
            "Llama 3.1-70B still in coding group — should be replaced by 3.3"
        )

        # Qwen3.5-9B should be present
        assert any("qwen3.5" in m.lower() or "Qwen3.5" in m for m in models), (
            "qwen3.5:9b missing from coding group — fast coding slot"
        )

    def test_launch_sh_pull_models_has_r22_updates(self):
        """launch.sh pull-models includes Llama 3.3 and Qwen3.5-9B."""
        content = open("launch.sh").read()
        # Qwen3.5-9B in standard list
        assert "qwen3.5:9b" in content, "launch.sh should pull qwen3.5:9b in standard models"
        # Llama 3.3 in PULL_HEAVY list
        assert "Meta-Llama-3.3-70B-GGUF" in content, (
            "launch.sh should pull Meta-Llama-3.3-70B-GGUF in PULL_HEAVY"
        )
        # Llama 3.1 should be gone
        assert "Meta-Llama-3.1-70B-GGUF" not in content, (
            "launch.sh should not pull Meta-Llama-3.1-70B-GGUF anymore"
        )


class TestR23MLXSupport:
    """Verify R23: MLX-first inference for Apple Silicon."""

    def test_mlx_backend_type_health_url(self):
        """MLX backend uses /v1/models health endpoint."""
        from portal_pipeline.cluster_backends import Backend

        b = Backend(
            id="test-mlx",
            type="mlx",
            url="http://localhost:8080",
            group="mlx",
            models=["mlx-community/Qwen3-Coder-Next-4bit"],
        )
        assert "/v1/models" in b.health_url, (
            "MLX backend health_url must use /v1/models (OpenAI-compatible)"
        )

    def test_backends_yaml_has_mlx_group(self):
        """backends.yaml contains an MLX backend group."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
        assert len(mlx_backends) >= 1, "No MLX backend in backends.yaml"
        models = mlx_backends[0]["models"]
        assert any("Qwen3-Coder-Next" in m for m in models), (
            "MLX primary model (Qwen3-Coder-Next-4bit) not in mlx backend"
        )

    def test_mlx_workspace_routing_priority(self):
        """Key workspaces prefer MLX group first."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        for ws in ["auto-coding", "auto-reasoning", "auto-research"]:
            groups = routing.get(ws, [])
            assert groups and groups[0] == "mlx", (
                f"{ws} must prefer 'mlx' group first, got: {groups}"
            )

    def test_security_workspaces_skip_mlx(self):
        """Security workspaces use Ollama only — no MLX for BaronLLM/WhiteRabbitNeo."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        for ws in ["auto-security", "auto-redteam", "auto-blueteam"]:
            groups = routing.get(ws, [])
            assert "mlx" not in groups, (
                f"{ws} should not include mlx — security models have no MLX versions"
            )

    def test_minimax_not_in_mlx_group(self):
        """MiniMax-M2 MLX is 129GB — must not be in mlx backend (too large for 64GB)."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        mlx_backends = [b for b in cfg["backends"] if b.get("type") == "mlx"]
        if mlx_backends:
            models = mlx_backends[0].get("models", [])
            assert not any("MiniMax-M2-4bit" in m for m in models), (
                "MiniMax-M2-4bit is 129GB and must not be in the MLX backend for 64GB systems"
            )

    def test_launch_sh_has_mlx_commands(self):
        """launch.sh has install-mlx, pull-mlx-models, and proxy references."""
        content = open("launch.sh").read()
        assert "install-mlx" in content
        assert "pull-mlx-models" in content
        assert "mlx_lm" in content  # text-only server (port 18081)
        assert "mlx_vlm" in content  # VLM server (port 18082)
        assert "mlx-proxy" in content  # auto-switching proxy
        assert "Qwen3-Coder-Next-4bit" in content

    def test_mlx_proxy_script_exists(self):
        """scripts/mlx-proxy.py exists and has the expected structure."""
        content = open("scripts/mlx-proxy.py").read()
        assert "LM_PORT" in content
        assert "VLM_PORT" in content
        assert "PROXY_PORT" in content
        assert "detect_server" in content
        assert "ensure_server" in content
        assert "Qwen3.5-35B-A3B" in content or "Qwen3.5-35B-A3B-Claude" in content


class TestRecordUsageMetrics:
    """Verify _record_usage correctly parses Ollama response fields."""

    def test_record_usage_full_response(self):
        """Standard Ollama response with all usage fields."""
        from portal_pipeline.router_pipe import _record_usage

        # Should not raise
        _record_usage(
            model="baronllm:q6_k",
            workspace="auto-security",
            data={
                "eval_count": 312,
                "eval_duration": 6638000000,  # ~47 tok/s
                "prompt_eval_count": 48,
            },
        )

    def test_record_usage_missing_fields(self):
        """Incomplete response dict — should not raise."""
        from portal_pipeline.router_pipe import _record_usage

        _record_usage(model="test-model", workspace="auto", data={})
        _record_usage(model="test-model", workspace="auto", data={"eval_count": 0})
        _record_usage(model="test-model", workspace="auto", data={"eval_duration": 0})

    def test_record_usage_none_values(self):
        """None values in response fields — should not raise."""
        from portal_pipeline.router_pipe import _record_usage

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

        from portal_pipeline import router_pipe

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
        from portal_pipeline import router_pipe

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
        from portal_pipeline.router_pipe import WORKSPACES

        assert "auto-spl" in WORKSPACES, (
            "auto-spl missing from WORKSPACES in router_pipe.py — "
            "add it with model_hint and mlx_model_hint"
        )

    def test_auto_spl_uses_deepseek_coder_model_hint(self):
        """auto-spl model_hint must be deepseek-coder-v2 (Ollama fallback)."""
        from portal_pipeline.router_pipe import WORKSPACES

        hint = WORKSPACES["auto-spl"]["model_hint"]
        assert "deepseek-coder-v2" in hint.lower(), (
            f"auto-spl model_hint should be deepseek-coder-v2 variant, got: {hint}"
        )

    def test_auto_spl_uses_qwen3_coder_mlx_hint(self):
        """auto-spl mlx_model_hint must point to Qwen3-Coder-30B MLX."""
        from portal_pipeline.router_pipe import WORKSPACES

        hint = WORKSPACES["auto-spl"].get("mlx_model_hint", "")
        assert "Qwen3-Coder-30B" in hint, (
            f"auto-spl mlx_model_hint should be Qwen3-Coder-30B-A3B-Instruct-8bit, got: {hint}"
        )

    def test_auto_spl_in_backends_yaml(self):
        """auto-spl must exist in workspace_routing in backends.yaml."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        assert "auto-spl" in routing, "auto-spl missing from workspace_routing in backends.yaml"

    def test_auto_spl_routing_starts_with_mlx(self):
        """auto-spl routing must prefer mlx group first (Apple Silicon primary)."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        groups = cfg["workspace_routing"].get("auto-spl", [])
        assert groups and groups[0] == "mlx", f"auto-spl must prefer mlx group first, got: {groups}"

    def test_workspace_count_is_16(self):
        """Total workspace count must be 17 after adding auto-agentic (was 16)."""
        from portal_pipeline.router_pipe import WORKSPACES

        assert len(WORKSPACES) == 17, (
            f"Expected 17 workspaces after adding auto-agentic, got {len(WORKSPACES)}. "
            "Update this test if workspaces are intentional added or removed."
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

    def test_spl_persona_workspace_model_is_mlx_qwen3_coder(self):
        """Persona workspace_model must be the MLX Qwen3-Coder-30B model."""
        from pathlib import Path

        import yaml

        data = yaml.safe_load(Path("config/personas/splunksplgineer.yaml").read_text())
        wm = data.get("workspace_model", "")
        assert "Qwen3-Coder-30B" in wm, (
            f"SPL persona workspace_model should be Qwen3-Coder-30B-A3B-Instruct-8bit, got: {wm}"
        )

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
        from portal_pipeline.router_pipe import _CODING_KEYWORDS

        assert "splunk" not in _CODING_KEYWORDS, (
            "'splunk' must be removed from _CODING_KEYWORDS after adding _SPL_KEYWORDS. "
            "Leaving it causes SPL queries to route to auto-coding instead of auto-spl."
        )

    def test_spl_query_not_in_coding_keywords(self):
        """'spl query' must be removed from _CODING_KEYWORDS — SPL workspace owns it now."""
        from portal_pipeline.router_pipe import _CODING_KEYWORDS

        assert "spl query" not in _CODING_KEYWORDS, (
            "'spl query' must be removed from _CODING_KEYWORDS after adding _SPL_KEYWORDS."
        )

    def test_spl_keywords_weighted_dict_exists(self):
        """_SPL_KEYWORDS must be a weighted dict in router_pipe."""
        from portal_pipeline.router_pipe import _SPL_KEYWORDS

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
        from portal_pipeline.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "Write a splunk query to count failed logins by host"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-spl", (
            f"_detect_workspace should return 'auto-spl' for SPL content, got: {result!r}"
        )

    def test_spl_detect_workspace_routes_tstats_query(self):
        """_detect_workspace must return 'auto-spl' when user asks about tstats."""
        from portal_pipeline.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "How do I use tstats with a data model acceleration?"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-spl", (
            f"_detect_workspace should return 'auto-spl' for tstats content, got: {result!r}"
        )

    def test_spl_does_not_route_generic_coding(self):
        """Generic Python/code requests must NOT route to auto-spl."""
        from portal_pipeline.router_pipe import _detect_workspace

        messages = [{"role": "user", "content": "Write a Python function to parse JSON logs"}]
        result = _detect_workspace(messages)
        assert result != "auto-spl", (
            f"Python-only request should not route to auto-spl, got: {result!r}"
        )

    def test_auto_spl_routing_consistent_across_files(self):
        """auto-spl key must exist in both WORKSPACES and backends.yaml workspace_routing."""
        import yaml

        from portal_pipeline.router_pipe import WORKSPACES

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
