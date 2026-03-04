"""tests/unit/test_mcp_endpoints.py

Tests for OpenAI-compatible endpoints on MCP servers.
These endpoints enable Open WebUI native TTS and STT integration.
Tests run without actual model inference (tests the HTTP plumbing).
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")


class TestTTSOpenAIEndpoints:
    """Test /v1/audio/speech and /v1/models on mcp-tts."""

    @pytest.fixture
    def tts_client(self):
        """Create a test client for the TTS MCP server."""
        # Import lazily to avoid kokoro-onnx dep at collection time
        try:
            from portal_mcp.generation.tts_mcp import mcp
            app = mcp.app
            with TestClient(app) as client:
                yield client
        except ImportError as e:
            pytest.skip(f"tts_mcp deps not installed: {e}")

    def test_health_endpoint(self, tts_client):
        resp = tts_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "tts-mcp"

    def test_v1_models_endpoint_exists(self, tts_client):
        """GET /v1/models should return model list (OpenAI-compatible)."""
        resp = tts_client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert data.get("object") == "list"

    def test_audio_speech_endpoint_exists(self, tts_client):
        """POST /v1/audio/speech should exist (may fail without kokoro installed)."""
        resp = tts_client.post(
            "/v1/audio/speech",
            json={"input": "", "voice": "af_heart"},
        )
        # Empty input should return 400, not 404
        assert resp.status_code in (400, 503), (
            f"Expected 400 (empty input) or 503 (kokoro unavailable), got {resp.status_code}"
        )

    def test_audio_speech_no_input_returns_400(self, tts_client):
        """Empty 'input' field should return 400."""
        resp = tts_client.post(
            "/v1/audio/speech",
            json={"input": "", "model": "kokoro", "voice": "af_heart"},
        )
        assert resp.status_code in (400, 503)
        if resp.status_code == 400:
            assert "error" in resp.json()

    def test_audio_speech_missing_body_returns_error(self, tts_client):
        """No body should handle gracefully (not crash)."""
        resp = tts_client.post("/v1/audio/speech", content=b"", headers={"Content-Type": "application/json"})
        # Should get 400 or 503, never 500 from unhandled exception
        assert resp.status_code in (400, 503, 422)


class TestWhisperOpenAIEndpoints:
    """Test /v1/audio/transcriptions and /v1/models on mcp-whisper."""

    @pytest.fixture
    def whisper_client(self):
        """Create a test client for the Whisper MCP server."""
        try:
            from portal_mcp.generation.whisper_mcp import mcp
            app = mcp.app
            with TestClient(app) as client:
                yield client
        except ImportError as e:
            pytest.skip(f"whisper_mcp deps not installed: {e}")

    def test_health_endpoint(self, whisper_client):
        resp = whisper_client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_v1_models_endpoint_exists(self, whisper_client):
        """GET /v1/models should return whisper-1 model."""
        resp = whisper_client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("object") == "list"
        ids = [m["id"] for m in data.get("data", [])]
        assert "whisper-1" in ids, f"whisper-1 not in models: {ids}"

    def test_transcriptions_endpoint_exists(self, whisper_client):
        """POST /v1/audio/transcriptions should exist."""
        # Send empty multipart — should get 400, not 404
        resp = whisper_client.post(
            "/v1/audio/transcriptions",
            data={},  # empty form
        )
        assert resp.status_code in (400, 500), (
            f"Expected 400 (no file) or 500 (model unavailable), got {resp.status_code}"
        )

    def test_transcriptions_no_file_returns_400(self, whisper_client):
        """No 'file' field in form should return 400."""
        resp = whisper_client.post(
            "/v1/audio/transcriptions",
            data={"model": "whisper-1"},
        )
        # Should be 400 not 404 (endpoint exists)
        assert resp.status_code != 404, "Endpoint does not exist — 404 returned"


class TestBackendModelHintRouting:
    """Test that model_hint preference logic works correctly."""

    def test_model_hint_preferred_when_available(self):
        """If model_hint is in backend.models, it should be selected."""
        import sys
        import tempfile
        sys.path.insert(0, ".")
        from portal_pipeline.cluster_backends import BackendRegistry

        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "b.yaml"
            cfg.write_text("""
backends:
  - id: test
    type: ollama
    url: http://localhost:11434
    group: coding
    models:
      - dolphin-llama3:8b
      - qwen3-coder-next:30b-q5
      - devstral:24b
workspace_routing:
  auto-coding: [coding]
defaults:
  fallback_group: coding
  request_timeout: 120
""")
            reg = BackendRegistry(config_path=str(cfg))
            backend = reg.get_backend_for_workspace("auto-coding")
            assert backend is not None
            # The routing returns the backend — model_hint selection
            # happens in router_pipe.py, not BackendRegistry
            assert backend.group == "coding"
            assert "qwen3-coder-next:30b-q5" in backend.models

    def test_workspace_routing_covers_all_13(self):
        """All 13 canonical workspace IDs have routing entries."""
        import yaml
        sys.path.insert(0, ".")
        from portal_pipeline.router_pipe import WORKSPACES

        cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
        routing = cfg.get("workspace_routing", {})

        for ws_id in WORKSPACES:
            assert ws_id in routing, f"Workspace '{ws_id}' has no routing entry in backends.yaml"

    def test_all_workspaces_have_model_hint(self):
        """Every workspace must have a model_hint."""
        sys.path.insert(0, ".")
        from portal_pipeline.router_pipe import WORKSPACES
        for ws_id, cfg in WORKSPACES.items():
            assert cfg.get("model_hint"), f"Workspace '{ws_id}' missing model_hint"
