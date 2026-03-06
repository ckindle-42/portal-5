"""Portal 5.0 Pipeline unit tests — no live backends required."""

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
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_contains_required_gauges(self, client):
        resp = client.get("/metrics")
        content = resp.text
        assert "portal_backends_healthy" in content
        assert "portal_workspaces_total" in content
        assert "portal_uptime_seconds" in content

    def test_metrics_workspace_count_correct(self, client):
        resp = client.get("/metrics")
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
            "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF",
            "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF",
            "hf.co/MiniMaxAI/MiniMax-M2.1-GGUF",
        ]
        for model in required:
            assert any(model in m for m in all_models), (
                f"FAIL: {model} not found in any backend group in backends.yaml"
            )

    def test_documents_workspace_uses_minimax(self):
        """auto-documents workspace model_hint is MiniMax-M2.1."""
        hint = WORKSPACES["auto-documents"]["model_hint"]
        assert "MiniMax-M2.1" in hint, f"Expected auto-documents to use MiniMax-M2.1, got: {hint}"

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
            "BaronLLM_Offensive",
            "Lily-Cybersecurity-7B",
            "Dolphin3.0-R1-Mistral-24B",
            "WhiteRabbitNeo-33B",
            "dolphin-3-llama3-70b",
            # Coding
            # R20: Qwen3-Coder-Next-GGUF replaced with MLX (sharded GGUF incompatible with Ollama)
            "Qwen3-Coder-Next-4bit",
            "GLM-4.7-Flash",
            "DeepSeek-Coder-V2",
            "MiniMax-M2.1",
            "Meta-Llama-3.3-70B",
            # Reasoning
            "DeepSeek-R1-32B",
        ]
        for frag in required:
            found = any(frag in m for m in all_models)
            assert found, (
                f"Model fragment '{frag}' not found in any backend group.\n"
                f"  All models: {all_models}"
            )

    def test_router_hints_use_best_models(self):
        """Key workspaces use the recommended primary model hints."""
        # R20: Qwen3-Coder-Next-GGUF replaced with MLX backend
        assert "mlx-community/Qwen3-Coder-Next-4bit" in WORKSPACES["auto-coding"]["model_hint"], (
            "auto-coding should prefer Qwen3-Coder-Next MLX"
        )
        assert "MiniMax-M2.1" in WORKSPACES["auto-documents"]["model_hint"], (
            "auto-documents should use MiniMax-M2.1"
        )
        assert "BaronLLM" in WORKSPACES["auto-security"]["model_hint"], (
            "auto-security should use BaronLLM as primary"
        )
        assert "Lily" in WORKSPACES["auto-blueteam"]["model_hint"], (
            "auto-blueteam should use Lily-Cybersecurity"
        )
        assert "DeepSeek-R1" in WORKSPACES["auto-reasoning"]["model_hint"], (
            "auto-reasoning should use DeepSeek-R1"
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
        assert "_do_pull" in content, (
            "pull-models must use _do_pull() helper that handles both native and Docker"
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
        assert any("3.3-70B" in m or "Llama-3.3" in m for m in models), (
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
        """launch.sh has install-mlx and pull-mlx-models commands."""
        content = open("launch.sh").read()
        assert "install-mlx" in content
        assert "pull-mlx-models" in content
        assert "mlx_lm" in content
        assert "mlx-community/Qwen3-Coder-Next-4bit" in content
