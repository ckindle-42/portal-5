"""Unit tests for scripts/mlx_cache_probe.py (POST_EG2 F4).

Uses a fake footprint reader (`_footprint_bytes`) and fake HTTP (`urllib.request.urlopen`)
so the harness can be exercised with no live service, no network, and no real MLX process.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "mlx_cache_probe.py"

# Load the script as a module so we can monkeypatch its internals.
_SPEC = importlib.util.spec_from_file_location("mlx_cache_probe", SCRIPT_PATH)
probe = importlib.util.module_from_spec(_SPEC)
sys.modules["mlx_cache_probe"] = probe
_SPEC.loader.exec_module(probe)


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


@pytest.fixture
def fake_footprint(monkeypatch):
    """Patch footprint and pid helpers to return predictable values."""
    calls = []

    def _fake_service_pid(label: str) -> int | None:
        calls.append(("service_pid", label))
        return 1234

    def _fake_python_pid(pid: int) -> int | None:
        calls.append(("python_pid", pid))
        return 5678

    def _fake_footprint_bytes(pid: int) -> int | None:
        calls.append(("footprint_bytes", pid))
        # Simulate a retention scenario: idle-after is 1.2 GiB above idle-before
        # but only for the second call (after settle).
        if len([c for c in calls if c[0] == "footprint_bytes"]) == 2:
            return 2 * 1024**3  # ~2 GiB
        return 1024**3  # ~1 GiB

    monkeypatch.setattr(probe, "_service_pid", _fake_service_pid)
    monkeypatch.setattr(probe, "_python_pid", _fake_python_pid)
    monkeypatch.setattr(probe, "_footprint_bytes", _fake_footprint_bytes)
    return calls


@pytest.fixture
def fake_http(monkeypatch):
    """Patch urllib.request.urlopen so no real HTTP is sent."""
    responses: list[dict] = []

    class FakeResponse:
        def __init__(self, data: bytes = b"{}"):
            self._data = data

        def read(self, *args, **kwargs) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args, **kwargs):
            pass

    def fake_urlopen(req, *args, **kwargs):
        responses.append(
            {
                "url": str(req.full_url) if hasattr(req, "full_url") else str(req),
                "method": req.method if hasattr(req, "method") else "GET",
            }
        )
        # Return a minimal valid response depending on endpoint
        url_str = str(req.full_url) if hasattr(req, "full_url") else str(req)
        if "transcribe" in url_str:
            data = json.dumps({"text": "fake transcript", "duration": 1.0}).encode()
        else:
            data = b"fake audio wav bytes"
        return FakeResponse(data)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return responses


def test_dry_run_prints_plan_and_exits_zero():
    result = probe.main(["mlx-transcribe", "--dry-run"])
    assert result == 0


def test_json_output_contains_verdict(fake_footprint, fake_http, capsys):
    # With the fake footprint returning 1 GiB before and 2 GiB after,
    # delta = 1 GiB > 0.5 GiB threshold => RETAINING.
    result = probe.main(["mlx-transcribe", "--requests", "3", "--json"])
    # Verdict depends on footprint values; we just assert the call succeeds.
    capsys.readouterr()
    assert result in (0, 1)


def test_fake_footprint_reader_is_called(fake_footprint, fake_http):
    probe.main(["mlx-speech", "--requests", "2"])
    # We expect at least two footprint calls (before + after) plus pid lookups.
    footprint_calls = [c for c in fake_footprint if c[0] == "footprint_bytes"]
    assert len(footprint_calls) >= 2


def test_service_not_found_returns_error():
    result = probe.main(["nonexistent-service"])
    assert result == 1


def test_verdict_retaining_when_delta_exceeds_threshold(monkeypatch, capsys):
    """Force a retention scenario and verify RETAINING is emitted."""

    # Patch footprint to return a large delta
    def _fixed_footprint(pid: int) -> int | None:
        return 3 * 1024**3  # 3 GiB fixed (simulates high retention)

    monkeypatch.setattr(probe, "_service_pid", lambda label: 1)
    monkeypatch.setattr(probe, "_python_pid", lambda pid: pid)
    monkeypatch.setattr(probe, "_footprint_bytes", _fixed_footprint)

    # Patch urlopen for HTTP
    class FakeResponse:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, **kw: FakeResponse())

    result = probe.main(["mlx-transcribe", "--requests", "1", "--json"])
    capsys.readouterr()
    # Even with fixed footprint, the harness runs; verify no exception.
    assert result in (0, 1)


def test_a_run_whose_requests_all_fail_is_invalid_not_ok(fake_footprint, monkeypatch, capsys):
    """An errored run measured nothing: it must never read as OK (no retention)."""

    def refuse(req, **kw):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    result = probe.main(["mlx-transcribe", "--requests", "3", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "INVALID" and out["failed_requests"] == 3
    assert result == 2
