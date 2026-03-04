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
        assert "baronllm" in ws.get("model_hint", "").lower() or \
               "baron" in ws.get("model_hint", "").lower() or \
               "xploiter" in ws.get("model_hint", "").lower(), \
               "Security workspace should use a dedicated security model"

    def test_coding_uses_qwen_or_glm(self):
        ws = WORKSPACES.get("auto-coding", {})
        hint = ws.get("model_hint", "").lower()
        assert "qwen" in hint or "glm" in hint or "deepseek" in hint, \
               "Coding workspace should use a specialized coding model"

    def test_reasoning_uses_deepseek_or_tongyi(self):
        ws = WORKSPACES.get("auto-reasoning", {})
        hint = ws.get("model_hint", "").lower()
        assert "deepseek" in hint or "tongyi" in hint or "r1" in hint, \
               "Reasoning workspace should use a deep reasoning model"
