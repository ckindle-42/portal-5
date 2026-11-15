"""scripts/fetch_mlx_asr_models.py — the one-time, idempotent ASR fetch step.

The ASR services run with HF_HUB_OFFLINE=1, so this script is the only way their
weights can appear; if it silently "succeeds" without files, OWUI's STT stays a
503 forever. Hermetic: fake HF cache trees in tmp_path, no network, no downloads.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FETCH = REPO / "scripts" / "fetch_mlx_asr_models.py"

_spec = importlib.util.spec_from_file_location("fetch_mlx_asr_models_test", FETCH)
assert _spec is not None and _spec.loader is not None
fetch = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("fetch_mlx_asr_models_test", fetch)
_spec.loader.exec_module(fetch)

MODEL = "mlx-community/parakeet-tdt-0.6b-v3"


def _snapshot(hub: Path, model_id: str, *, sha: str = "abc123", weights: bool = True) -> Path:
    snap = hub / f"models--{model_id.replace('/', '--')}" / "snapshots" / sha
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")
    if weights:
        (snap / "model.safetensors").write_bytes(b"\0" * 64)
    return snap


def test_cache_dir_prefers_hf_hub_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "home"))
    assert fetch.cache_dir() == tmp_path / "hub"


def test_cache_dir_falls_back_to_hf_home_hub(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "home"))
    assert fetch.cache_dir() == tmp_path / "home" / "hub"


def test_cache_dir_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    assert fetch.cache_dir(str(tmp_path / "other")) == tmp_path / "other"


def test_verify_rejects_a_snapshot_without_weights(tmp_path):
    snap = _snapshot(tmp_path / "hub", MODEL, weights=False)
    ok, detail = fetch.verify_snapshot(snap)
    assert ok is False
    assert "no weights" in detail


def test_verify_accepts_a_snapshot_with_weights(tmp_path):
    snap = _snapshot(tmp_path / "hub", MODEL)
    ok, detail = fetch.verify_snapshot(snap)
    assert ok is True
    assert "2 files" in detail


def test_cached_snapshot_none_on_empty_cache(tmp_path):
    snap, detail = fetch.cached_snapshot(MODEL, tmp_path / "hub")
    assert snap is None
    assert "not in" in detail


def test_cached_snapshot_skips_an_unverifiable_newer_snapshot(tmp_path):
    hub = tmp_path / "hub"
    good = _snapshot(hub, MODEL, sha="good")
    broken = _snapshot(hub, MODEL, sha="broken", weights=False)
    os.utime(broken, (broken.stat().st_atime + 60, broken.stat().st_mtime + 60))
    snap, _ = fetch.cached_snapshot(MODEL, hub)
    assert snap == good


def test_check_mode_fails_when_a_model_is_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.setattr(fetch, "CATALOG", (("mlx-transcribe :8924", "MLX_PARAKEET_MODEL", MODEL),))
    monkeypatch.delenv("MLX_PARAKEET_MODEL", raising=False)
    assert fetch.main(["--check"]) == 1
    assert "MISSING" in capsys.readouterr().out


def test_check_mode_passes_when_every_model_is_cached(monkeypatch, tmp_path, capsys):
    hub = tmp_path / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setattr(fetch, "CATALOG", (("mlx-transcribe :8924", "MLX_PARAKEET_MODEL", MODEL),))
    monkeypatch.delenv("MLX_PARAKEET_MODEL", raising=False)
    _snapshot(hub, MODEL)
    assert fetch.main(["--check"]) == 0
    assert "all ASR models cached" in capsys.readouterr().out


def test_catalog_covers_both_services():
    models = {default for _, _, default in fetch.CATALOG}
    services = {service for service, _, _ in fetch.CATALOG}
    assert services == {"mlx-transcribe :8924", "mlx-speech :8918"}
    assert "mlx-community/parakeet-tdt-0.6b-v3" in models
    assert "mlx-community/diar_sortformer_4spk-v1-fp32" in models
    assert "mlx-community/Qwen3-ASR-1.7B-8bit" in models


def test_catalog_defaults_match_the_service_code():
    """The fetch must name the ids the services actually load."""
    transcribe_src = (REPO / "scripts" / "mlx-transcribe.py").read_text()
    speech_src = (REPO / "scripts" / "mlx-speech.py").read_text()
    assert 'os.getenv("MLX_PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v3")' in transcribe_src
    assert (
        'os.getenv("MLX_DIARIZE_MODEL", "mlx-community/diar_sortformer_4spk-v1-fp32")'
        in transcribe_src
    )
    assert 'os.getenv("MLX_QWEN3_ASR", "mlx-community/Qwen3-ASR-1.7B-8bit")' in speech_src


@pytest.mark.parametrize("explicit", [None, []])
def test_resolve_models_defaults_to_the_catalog(monkeypatch, explicit):
    monkeypatch.delenv("MLX_PARAKEET_MODEL", raising=False)
    rows = fetch.resolve_models(explicit or [])
    assert rows == [(service, default) for service, _, default in fetch.CATALOG]


def test_resolve_models_honours_the_service_env_override(monkeypatch):
    monkeypatch.setenv("MLX_QWEN3_ASR", "mlx-community/local-asr")
    rows = dict(fetch.resolve_models([]))
    assert rows["mlx-speech :8918"] == "mlx-community/local-asr"


def test_resolve_models_passes_explicit_ids_through():
    assert fetch.resolve_models(["org/one", "org/two"]) == [
        ("explicit", "org/one"),
        ("explicit", "org/two"),
    ]
