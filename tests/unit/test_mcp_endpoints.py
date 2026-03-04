"""tests/unit/test_mcp_endpoints.py

Tests for OpenAI-compatible HTTP endpoints on MCP servers.
These are the endpoints Open WebUI uses for native TTS and STT.

Requires: mcp>=1.0.0 (in pyproject.toml [dev] group)
All tests should PASS after 'pip install -e .[dev,mcp]'
"""
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")


def get_tts_app():
    """Get the TTS MCP server's Starlette ASGI app."""
    from portal_mcp.generation.tts_mcp import mcp
    return mcp.streamable_http_app()


def get_whisper_app():
    """Get the Whisper MCP server's Starlette ASGI app."""
    from portal_mcp.generation.whisper_mcp import mcp
    return mcp.streamable_http_app()


class TestTTSOpenAIEndpoints:
    """Test /v1/audio/speech and /v1/models on mcp-tts.

    These endpoints make Open WebUI's native TTS work without any
    user configuration — it just works out of the box.
    """

    @pytest.fixture(scope="class")
    def client(self):
        with TestClient(get_tts_app()) as c:
            yield c

    def test_health_endpoint(self, client):
        """TTS server health check."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "tts-mcp"
        # Verify backend info is returned
        assert "backend" in data

    def test_v1_models_returns_list(self, client):
        """GET /v1/models — required by Open WebUI to discover TTS models."""
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("object") == "list"
        assert "data" in data
        # May be empty if kokoro not installed, but endpoint must exist and return 200

    def test_audio_speech_endpoint_exists(self, client):
        """POST /v1/audio/speech must exist (Open WebUI calls this for TTS)."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "test", "voice": "af_heart", "model": "kokoro"},
        )
        # 503 = kokoro not installed (graceful), 200 = works, never 404
        assert resp.status_code != 404, "CRITICAL: /v1/audio/speech endpoint missing"
        assert resp.status_code in (200, 400, 503), f"Unexpected status: {resp.status_code}"

    def test_audio_speech_empty_input_returns_400(self, client):
        """Empty input should return 400, not crash."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "", "voice": "af_heart"},
        )
        assert resp.status_code in (400, 503)
        if resp.status_code == 400:
            assert "error" in resp.json()

    def test_audio_speech_missing_body_handled_gracefully(self, client):
        """Malformed request should return an error, not 500."""
        resp = client.post(
            "/v1/audio/speech",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        # Should degrade to 400 (empty input) after body parse failure
        assert resp.status_code in (400, 422, 503), (
            f"Expected 400/422/503 for malformed body, got {resp.status_code}"
        )


class TestWhisperOpenAIEndpoints:
    """Test /v1/audio/transcriptions and /v1/models on mcp-whisper.

    These endpoints make Open WebUI's native STT (mic input) work.
    """

    @pytest.fixture(scope="class")
    def client(self):
        with TestClient(get_whisper_app()) as c:
            yield c

    def test_health_endpoint(self, client):
        """Whisper server health check."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_v1_models_returns_whisper_1(self, client):
        """GET /v1/models must return whisper-1 for Open WebUI compatibility."""
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("object") == "list"
        model_ids = [m["id"] for m in data.get("data", [])]
        assert "whisper-1" in model_ids, (
            f"whisper-1 must be in models list, got: {model_ids}"
        )

    def test_transcriptions_endpoint_exists(self, client):
        """POST /v1/audio/transcriptions must exist (never return 404)."""
        resp = client.post("/v1/audio/transcriptions", data={})
        assert resp.status_code != 404, (
            "CRITICAL: /v1/audio/transcriptions endpoint missing"
        )

    def test_transcriptions_no_file_returns_400(self, client):
        """Missing 'file' field in multipart should return 400."""
        resp = client.post(
            "/v1/audio/transcriptions",
            data={"model": "whisper-1"},  # no file
        )
        assert resp.status_code == 400
        assert "error" in resp.json()


class TestBackendModelHintRouting:
    """Test backend routing and workspace configuration completeness."""

    def test_all_13_workspaces_have_routing_entries(self):
        """Every workspace ID must have a routing entry in backends.yaml."""
        from pathlib import Path

        import yaml

        from portal_pipeline.router_pipe import WORKSPACES

        cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
        routing = cfg.get("workspace_routing", {})

        for ws_id in WORKSPACES:
            assert ws_id in routing, (
                f"Workspace '{ws_id}' has no routing entry in config/backends.yaml"
            )

    def test_all_workspaces_have_model_hint(self):
        """Every workspace must specify a model_hint for routing."""
        from portal_pipeline.router_pipe import WORKSPACES
        for ws_id, cfg in WORKSPACES.items():
            assert cfg.get("model_hint"), (
                f"Workspace '{ws_id}' missing model_hint — routing will use backend.models[0]"
            )

    def test_security_workspaces_use_security_models(self):
        """Security-focused workspaces must route to security-group backends."""
        from pathlib import Path

        import yaml


        cfg = yaml.safe_load(Path("config/backends.yaml").read_text())
        routing = cfg.get("workspace_routing", {})

        for ws_id in ["auto-security", "auto-redteam", "auto-blueteam"]:
            groups = routing.get(ws_id, [])
            assert "security" in groups, (
                f"Workspace '{ws_id}' should prefer security group, got: {groups}"
            )

    def test_backend_registry_loads_all_groups(self):
        """All 6 backend groups (general, coding, security, etc.) must load."""
        from portal_pipeline.cluster_backends import BackendRegistry

        reg = BackendRegistry(config_path="config/backends.yaml")
        groups = {b.group for b in reg.list_backends()}
        expected = {"general", "coding", "security", "reasoning", "vision", "creative"}
        assert groups >= expected, (
            f"Missing backend groups: {expected - groups}"
        )
