"""mlx-speech ASR gate — :8918 must not advertise an uncacheable ASR model.

Live 2026-11-07: HF_HUB_OFFLINE plus the uncached Qwen3-ASR default turned
every /v1/audio/transcriptions call into a bare 500. Hermetic: fake HF cache
in tmp_path, no MLX, no network, no server started.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SPEECH = REPO / "scripts" / "mlx-speech.py"

_spec = importlib.util.spec_from_file_location("mlx_speech_gate_test", SPEECH)
assert _spec is not None and _spec.loader is not None
speech = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("mlx_speech_gate_test", speech)
_spec.loader.exec_module(speech)


def _empty_cache(monkeypatch, tmp_path) -> Path:
    hub = tmp_path / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    return hub


def _cached_snapshot(hub: Path) -> Path:
    snap = hub / "models--mlx-community--Qwen3-ASR-1.7B-8bit" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")
    return snap


def test_asr_unavailable_when_cache_empty(monkeypatch, tmp_path):
    _empty_cache(monkeypatch, tmp_path)
    assert speech._asr_model_cached(speech.QWEN3_ASR_MODEL) is False


def test_asr_available_when_snapshot_cached(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    _cached_snapshot(hub)
    assert speech._asr_model_cached(speech.QWEN3_ASR_MODEL) is True


def test_asr_available_for_local_dir(monkeypatch, tmp_path):
    _empty_cache(monkeypatch, tmp_path)
    local = tmp_path / "local-asr"
    local.mkdir()
    assert speech._asr_model_cached(str(local)) is True


def test_transcriptions_is_503_not_500_with_model_and_reason(monkeypatch, tmp_path):
    _empty_cache(monkeypatch, tmp_path)
    with TestClient(speech.app) as client:
        r = client.post("/v1/audio/transcriptions", files={"file": ("clip.wav", b"not audio")})
    assert r.status_code == 503
    body = r.json()
    assert speech.QWEN3_ASR_MODEL in body["error"]
    assert "cache" in body["error"]
    assert body["model"] == speech.QWEN3_ASR_MODEL
    assert body["reason"] == "asr_model_not_cached"


def test_health_reports_asr_availability(monkeypatch, tmp_path):
    hub = _empty_cache(monkeypatch, tmp_path)
    with TestClient(speech.app) as client:
        health = client.get("/health").json()
        assert health["asr_model"] == speech.QWEN3_ASR_MODEL
        assert health["asr_available"] is False
        _cached_snapshot(hub)
        health = client.get("/health").json()
        assert health["asr_available"] is True
