"""mlx-transcribe :8924 serves OWUI's OpenAI-compatible STT endpoint.

Live defect this covers: the model is fetched by HF_HUB_OFFLINE-blocked services,
so an absent Parakeet turned the endpoint into a blind 500 and nothing could tell
"no model" from "bad audio". Hermetic: fake HF cache in tmp_path, no MLX, no
network, no server started.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

REPO = Path(__file__).resolve().parents[2]
TRANSCRIBE = REPO / "scripts" / "mlx-transcribe.py"

_spec = importlib.util.spec_from_file_location("mlx_transcribe_stt_test", TRANSCRIBE)
assert _spec is not None and _spec.loader is not None
transcribe = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("mlx_transcribe_stt_test", transcribe)
_spec.loader.exec_module(transcribe)


def _empty_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    hub = tmp_path / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    return hub


def _cached_snapshot(hub: Path, model_id: str) -> Path:
    snap = hub / f"models--{model_id.replace('/', '--')}" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_bytes(b"\0" * 32)
    return snap


def _upload(name: str = "clip.webm") -> UploadFile:
    return UploadFile(file=io.BytesIO(b"not audio"), filename=name)


@pytest.fixture(scope="module")
def client():
    # One TestClient per module: the MCP session manager's lifespan runs once only.
    with TestClient(transcribe.app) as c:
        yield c


def test_model_cached_false_on_empty_cache(monkeypatch, tmp_path):
    _empty_cache(monkeypatch, tmp_path)
    assert transcribe._model_cached(transcribe.PARAKEET_MODEL) is False


def test_model_cached_true_with_snapshot(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    _cached_snapshot(hub, transcribe.PARAKEET_MODEL)
    assert transcribe._model_cached(transcribe.PARAKEET_MODEL) is True


def test_model_cached_false_for_a_snapshot_without_weights(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    snap = _cached_snapshot(hub, transcribe.PARAKEET_MODEL)
    (snap / "model.safetensors").unlink()
    assert transcribe._model_cached(transcribe.PARAKEET_MODEL) is False


async def test_transcriptions_503_with_model_and_reason(monkeypatch, tmp_path):
    _empty_cache(monkeypatch, tmp_path)
    resp = await transcribe.openai_audio_transcriptions(_upload(), language="auto")
    assert resp.status_code == 503
    body = json.loads(resp.body)
    assert body["model"] == transcribe.PARAKEET_MODEL
    assert body["reason"] == "asr_model_not_cached"
    assert "pull-asr-models" in body["error"]


async def test_transcriptions_returns_openai_text(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    _cached_snapshot(hub, transcribe.PARAKEET_MODEL)
    monkeypatch.setattr(
        transcribe,
        "_transcribe",
        lambda path, language: {"text": "hello from parakeet", "language": "en", "duration": 1.0},
    )
    resp = await transcribe.openai_audio_transcriptions(_upload(), language="en")
    assert resp.status_code == 200
    assert json.loads(resp.body) == {"text": "hello from parakeet"}


async def test_transcriptions_rejects_an_empty_upload(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    _cached_snapshot(hub, transcribe.PARAKEET_MODEL)

    class _Boom:
        filename = "clip.wav"

        async def read(self) -> bytes:
            raise OSError("socket closed")

    resp = await transcribe.openai_audio_transcriptions(_Boom(), language="auto")  # type: ignore[arg-type]
    assert resp.status_code == 400
    assert "upload failed" in json.loads(resp.body)["error"]


async def test_health_reports_asr_availability(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    body = json.loads((await transcribe.health()).body)
    assert body["asr_model"] == transcribe.PARAKEET_MODEL
    assert body["asr_available"] is False
    _cached_snapshot(hub, transcribe.PARAKEET_MODEL)
    body = json.loads((await transcribe.health()).body)
    assert body["asr_available"] is True


def test_owui_multipart_request_is_503_not_500(monkeypatch, tmp_path, client):
    """OWUI's exact request shape (multipart file + model field) over real HTTP."""
    _empty_cache(monkeypatch, tmp_path)
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("clip.webm", b"not audio", "audio/webm")},
        data={"model": "parakeet-tdt-0.6b-v3"},
    )
    assert r.status_code == 503
    assert r.json()["reason"] == "asr_model_not_cached"


def test_owui_multipart_request_returns_text(monkeypatch, tmp_path, client):
    hub = _empty_cache(monkeypatch, tmp_path)
    _cached_snapshot(hub, transcribe.PARAKEET_MODEL)
    seen: dict[str, str | None] = {}

    def _fake(path: str, language: str | None) -> dict:
        seen["language"] = language
        return {"text": "open webui hears this", "language": "en", "duration": 0.5}

    monkeypatch.setattr(transcribe, "_transcribe", _fake)
    r = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("clip.webm", b"not audio", "audio/webm")},
        data={"model": "parakeet-tdt-0.6b-v3", "language": "en"},
    )
    assert r.status_code == 200
    assert r.json() == {"text": "open webui hears this"}
    assert seen["language"] == "en"
