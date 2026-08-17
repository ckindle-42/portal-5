"""SA3.2 -- Arm A: MLX-native embedding server tests
(TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1).

These tests verify the OpenAI-compatible /v1/embeddings contract of
`scripts/embedding-server-mlx.py` fully offline: FastAPI TestClient exercises
the HTTP layer while the `mlx_embeddings` runtime (MLX/Metal) is mocked, exactly
as `tests/unit/test_reranker_mcp.py` mocks the reranker's runtime. Determinism
is verified against the mock's fixed text_embeds, not against a live GPU.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _stub(value):
    stub = MagicMock()
    stub.tolist.return_value = list(value)
    return stub


@pytest.fixture
def arm_a_client(monkeypatch, tmp_path):
    import importlib
    import sys

    sys.modules.pop("scripts.embedding-server-mlx", None)
    monkeypatch.setattr(
        sys, "argv", ["embedding-server-mlx.py", "--port", "8941", "--model", "mock-model"]
    )
    spec = importlib.util.spec_from_file_location(
        "embedding_server_mlx_test",
        "scripts/embedding-server-mlx.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with (
        patch("mlx_embeddings.load", return_value=(MagicMock(), MagicMock())) as mock_load,
        patch("mlx_embeddings.generate") as mock_generate,
        patch("mlx.core.array", side_effect=lambda value, *a, **k: _stub(value)) as mock_array,
    ):

        def _fake_generate(model, processor, texts, **kwargs):
            if isinstance(texts, str):
                texts = [texts]
            output = MagicMock()
            # Echo one vector per requested text (deterministic by index).
            output.text_embeds = [
                [float(i + 1) * 0.1, float(i + 1) * 0.2] for i in range(len(texts))
            ]
            return output

        mock_generate.side_effect = _fake_generate

        client = TestClient(module.app)
        client._module = module  # type: ignore[attr-defined]
        client._mock_load = mock_load  # type: ignore[attr-defined]
        client._mock_generate = mock_generate  # type: ignore[attr-defined]
        client._mock_array = mock_array  # type: ignore[attr-defined]
        yield client


def test_health_reports_model_and_backend(arm_a_client):
    resp = arm_a_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model"] == "mock-model"
    assert body["backend"] == "mlx"


def test_v1_models_contract(arm_a_client):
    resp = arm_a_client.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == "mock-model"


def test_embeddings_single_string_input(arm_a_client):
    resp = arm_a_client.post("/v1/embeddings", json={"input": "behavior: unclassified telemetry"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 1
    assert body["data"][0]["index"] == 0
    assert body["data"][0]["embedding"] == [0.1, 0.2]
    arm_a_client._mock_generate.assert_called_once()
    _args, kwargs = arm_a_client._mock_generate.call_args
    assert kwargs["texts"] == ["behavior: unclassified telemetry"]


def test_embeddings_list_input_returns_indexed_vectors(arm_a_client):
    resp = arm_a_client.post("/v1/embeddings", json={"input": ["text-a", "text-b"]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["index"] == 0
    assert body["data"][1]["index"] == 1
    assert body["data"][0]["embedding"] == [0.1, 0.2]
    assert body["data"][1]["embedding"] == [0.2, 0.4]
    assert body["usage"]["total_tokens"] == 2


def test_embeddings_empty_input_returns_400(arm_a_client):
    resp = arm_a_client.post("/v1/embeddings", json={"input": []})
    assert resp.status_code == 400


def test_generate_error_returns_500(arm_a_client):
    arm_a_client._mock_generate.side_effect = RuntimeError("mlx exploded")
    resp = arm_a_client.post("/v1/embeddings", json={"input": ["x"]})
    assert resp.status_code == 500


def test_model_loaded_lazily_on_first_request(arm_a_client):
    assert arm_a_client._mock_load.call_count == 0
    arm_a_client.get("/health")
    assert arm_a_client._mock_load.call_count == 0
    arm_a_client.post("/v1/embeddings", json={"input": ["warm"]})
    assert arm_a_client._mock_load.call_count == 1


def test_no_run_in_executor_pattern_in_source():
    """SA3.2: the MLX server must never reintroduce the `run_in_executor`
    pattern that crashed MPS in the CPU path -- MLX generate() is called
    directly on the event loop (reranker pattern)."""
    source = open("scripts/embedding-server-mlx.py", encoding="utf-8").read()
    assert "run_in_executor(" not in source
    assert ".run_in_executor" not in source
    assert "SentenceTransformer" not in source
