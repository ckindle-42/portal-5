"""Unit tests for scripts/mlx_cache_probe.py (POST_EG2 F4).

Fake footprint reads and a fake urlopen exercise the harness with no live service.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "mlx_cache_probe.py"

_SPEC = importlib.util.spec_from_file_location("mlx_cache_probe", SCRIPT_PATH)
probe = importlib.util.module_from_spec(_SPEC)
sys.modules["mlx_cache_probe"] = probe
_SPEC.loader.exec_module(probe)

GIB = 1024**3
MIB = 1024**2


class _FakeResponse:
    def read(self, *args, **kwargs) -> bytes:
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


@pytest.fixture(autouse=True)
def _fake_config_exists(tmp_path, monkeypatch):
    """Point the harness at a fake config file so it never reads the live one."""
    fake_config = tmp_path / "portal.yaml"
    fake_config.write_text(
        "mcp_fleet:\n"
        "  - id: mlx-transcribe\n"
        "    port: 9999\n"
        "    host_native: true\n"
        "    launchd_label: com.portal5.mlx-transcribe\n"
        "  - id: mlx-speech\n"
        "    port: 9998\n"
        "    host_native: true\n"
        "    launchd_label: com.portal5.mlx-speech\n"
        "host_jobs: []\n"
    )
    monkeypatch.setattr(probe, "CONFIG_PATH", fake_config)
    monkeypatch.setattr(probe, "SETTLE_WAIT_S", 0)


def _patch_runtime(monkeypatch, footprints: list[int] | int, *, fail: bool = False) -> None:
    monkeypatch.setattr(probe, "_service_pid", lambda label: 1234)
    monkeypatch.setattr(probe, "_python_pid", lambda pid: 5678)
    if isinstance(footprints, int):

        def reader(pid: int) -> int:
            return footprints

    else:
        seq = iter(footprints)

        def reader(pid: int) -> int:
            return next(seq)

    monkeypatch.setattr(probe, "_footprint_bytes", reader)

    def fake_urlopen(req, *args, **kwargs):
        if fail:
            raise urllib.error.URLError("connection refused")
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _run_json(
    monkeypatch, capsys, argv: list[str], footprints: list[int] | int, *, fail: bool = False
):
    _patch_runtime(monkeypatch, footprints, fail=fail)
    code = probe.main(argv)
    out = json.loads(capsys.readouterr().out)
    return code, out


def test_dry_run_prints_warm_plan(capsys):
    code = probe.main(["mlx-transcribe", "--dry-run"])
    text = capsys.readouterr().out
    assert code == 0
    assert "port=9999" in text
    assert "measured_requests=20" in text
    assert "warm=2" in text
    assert "tolerance=<3% or <150 MiB" in text


def test_service_not_found_returns_error():
    assert probe.main(["nonexistent-service"]) == 1


def test_cold_load_then_flat_is_flat(monkeypatch, capsys):
    """A model-load jump during warm-up, then a flat series, is not retention."""
    cold, warm = GIB, 6 * GIB
    samples = [warm, warm, warm]
    code, out = _run_json(
        monkeypatch,
        capsys,
        ["mlx-transcribe", "--requests", "3", "--json"],
        [cold, warm, *samples],
    )
    assert out["verdict"] == "FLAT"
    assert out["baseline_bytes"] == cold
    assert out["warm_baseline_bytes"] == warm
    assert out["per_request_bytes"] == samples
    assert out["growth_bytes"] == 0
    assert out["python_pid"] == 5678
    assert code == 0


def test_steady_climb_is_retaining(monkeypatch, capsys):
    """200 MiB of warm-series growth is over both tolerances (old 0.5 GiB gate was not)."""
    base = GIB
    step = 50 * MIB
    samples = [base + step * i for i in range(1, 5)]
    code, out = _run_json(
        monkeypatch,
        capsys,
        ["mlx-transcribe", "--requests", "4", "--warm", "2", "--json"],
        [base // 2, base, *samples],
    )
    assert out["verdict"] == "RETAINING"
    assert out["baseline_bytes"] == base // 2
    assert out["warm_baseline_bytes"] == base
    assert out["per_request_bytes"] == samples
    assert out["growth_bytes"] == 4 * step
    assert code == 1


def test_growth_under_abs_tolerance_is_flat(monkeypatch, capsys):
    base = GIB
    samples = [base + 50 * MIB, base + 100 * MIB]
    code, out = _run_json(
        monkeypatch,
        capsys,
        ["mlx-speech", "--requests", "2", "--json"],
        [base, base, *samples],
    )
    assert out["growth_bytes"] == 100 * MIB
    assert out["verdict"] == "FLAT"
    assert code == 0


def test_growth_under_rel_tolerance_is_flat(monkeypatch, capsys):
    """200 MiB on a 10 GiB baseline is over 150 MiB and still under 3%."""
    base = 10 * GIB
    samples = [base + 100 * MIB, base + 200 * MIB]
    code, out = _run_json(
        monkeypatch,
        capsys,
        ["mlx-speech", "--requests", "2", "--json"],
        [base, base, *samples],
    )
    assert out["growth_bytes"] == 200 * MIB
    assert out["verdict"] == "FLAT"
    assert code == 0


def test_failed_requests_are_invalid(monkeypatch, capsys):
    code, out = _run_json(
        monkeypatch,
        capsys,
        ["mlx-transcribe", "--requests", "3", "--json"],
        GIB,
        fail=True,
    )
    assert out["verdict"] == "INVALID"
    assert out["failed_requests"] == 5  # 2 warm-up + 3 measured
    assert out["growth_bytes"] is None
    assert len(out["per_request_bytes"]) == 3
    assert code == 2


def test_missing_pid_is_invalid(monkeypatch, capsys):
    monkeypatch.setattr(probe, "_service_pid", lambda label: None)

    def boom(pid: int) -> int:
        raise AssertionError(pid)

    monkeypatch.setattr(probe, "_footprint_bytes", boom)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, *a, **k: _FakeResponse())
    code = probe.main(["mlx-speech", "--requests", "1", "--warm", "1", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "INVALID"
    assert out["python_pid"] is None
    assert out["baseline_bytes"] is None
    assert code == 2


def test_default_transcribe_durations_stay_short(monkeypatch, capsys):
    seen: list[float] = []
    urls: list[str] = []

    def fake_wav(path: Path, duration_s: float, sr: int = 24000) -> None:
        seen.append(duration_s)
        path.write_bytes(b"RIFF")

    def fake_urlopen(req, *args, **kwargs):
        urls.append(req.full_url)
        return _FakeResponse()

    monkeypatch.setattr(probe, "_generate_synthetic_wav", fake_wav)
    _patch_runtime(monkeypatch, GIB)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    code = probe.main(["mlx-transcribe", "--requests", "3", "--warm", "2", "--json"])
    capsys.readouterr()
    assert code == 0
    assert seen == [0.5, 0.5, 0.5, 1.0, 1.5]
    assert urls
    assert all(url.endswith("/v1/audio/transcribe-with-speakers") for url in urls)


def test_input_seconds_applies_to_measured_requests_only(monkeypatch, capsys):
    seen: list[float] = []

    def fake_wav(path: Path, duration_s: float, sr: int = 24000) -> None:
        seen.append(duration_s)
        path.write_bytes(b"RIFF")

    monkeypatch.setattr(probe, "_generate_synthetic_wav", fake_wav)
    code, out = _run_json(
        monkeypatch,
        capsys,
        ["mlx-transcribe", "--requests", "2", "--warm", "2", "--input-seconds", "8", "--json"],
        GIB,
    )
    assert code == 0
    assert out["input_seconds"] == 8.0
    assert seen == [0.5, 0.5, 8.0, 8.0]


def test_default_speech_texts_stay_short(monkeypatch, capsys):
    texts: list[str] = []
    urls: list[str] = []

    def fake_urlopen(req, *args, **kwargs):
        texts.append(json.loads(req.data.decode())["input"])
        urls.append(req.full_url)
        return _FakeResponse()

    _patch_runtime(monkeypatch, GIB)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    code = probe.main(["mlx-speech", "--requests", "2", "--warm", "2", "--json"])
    capsys.readouterr()
    assert code == 0
    assert texts == ["Hello. ", "Hello. ", "Hello. ", "Hello. " * 2]
    assert urls
    assert all(url.endswith("/v1/audio/speech") for url in urls)


def test_chars_applies_to_measured_requests_only(monkeypatch, capsys):
    texts: list[str] = []
    urls: list[str] = []

    def fake_urlopen(req, *args, **kwargs):
        texts.append(json.loads(req.data.decode())["input"])
        urls.append(req.full_url)
        return _FakeResponse()

    _patch_runtime(monkeypatch, GIB)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    code = probe.main(["mlx-speech", "--requests", "2", "--warm", "2", "--chars", "20", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["chars"] == 20
    assert out["verdict"] == "FLAT"
    assert texts[:2] == ["Hello. ", "Hello. "]
    assert texts[2:] == ["Hello. Hello. Hello.", "Hello. Hello. Hello."]
    assert all(url.endswith("/v1/audio/speech") for url in urls)


def test_chars_rejected_for_transcribe(capsys):
    assert probe.main(["mlx-transcribe", "--chars", "10"]) == 1
    assert "mlx-speech" in capsys.readouterr().err


def test_input_seconds_rejected_for_speech(capsys):
    assert probe.main(["mlx-speech", "--input-seconds", "5"]) == 1
    assert "mlx-transcribe" in capsys.readouterr().err


def test_warm_must_be_positive():
    assert probe.main(["mlx-transcribe", "--warm", "0", "--dry-run"]) == 1
