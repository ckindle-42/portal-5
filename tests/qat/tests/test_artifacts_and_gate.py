"""Offline tests: artifact byte validators and the inter-phase gate."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from tests.qat import artifacts as art
from tests.qat import gate
from tests.qat.models import Status
from tests.qat.owui_client import OWUIClient

from .test_config_and_scenarios import make_settings

# ---------------------------------------------------------------- artifacts


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)
    return buf.getvalue()


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 13 + b"\x00" * 12
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
MP3_ID3 = b"ID3\x03\x00" + b"\x00" * 32
MP3_SYNC = b"\xff\xfb\x90\x44" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
STL_BIN = b"binary stl".ljust(80, b"\x00") + (1).to_bytes(4, "little") + b"\x00" * 50
STL_ASCII = b"solid cube\nfacet normal 0 0 0\nendsolid cube\n"
PDF = b"%PDF-1.7\n" + b"x" * 32
DOCX = _zip_bytes({"word/document.xml": b"<doc/>", "[Content_Types].xml": b"<t/>"})
XLSX = _zip_bytes({"xl/workbook.xml": b"<wb/>"})
PPTX = _zip_bytes({"ppt/presentation.xml": b"<ppt/>"})


class TestArtifactValidators:
    def test_png(self) -> None:
        assert art.validate_png(PNG) is None
        assert art.validate_png(b"\x89PNG") is not None  # truncated
        assert art.validate_png(b"GIF89a" + b"\x00" * 40) is not None

    def test_mp4(self) -> None:
        assert art.validate_mp4(MP4) is None
        assert art.validate_mp4(b"\x00\x00\x00\x18XXXpmp42") is not None
        assert art.validate_mp4(b"ftyp") is not None

    def test_mp4_minimum_duration_rejects_one_second_clip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/ffprobe")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="1.0\n", stderr=""),
        )
        error = art.validate_mp4_duration(MP4, min_duration_s=3.0)
        assert error is not None and "1.00s" in error and "3.00s" in error

    def test_wav_mp3_audio(self) -> None:
        assert art.validate_wav(WAV) is None
        assert art.validate_mp3(MP3_ID3) is None
        assert art.validate_mp3(MP3_SYNC) is None
        assert art.validate_mp3(b"not audio at all") is not None
        assert art.validate_audio(WAV) is None
        assert art.validate_audio(MP3_ID3) is None
        assert art.validate_audio(PNG) is not None

    def test_stl_binary_and_ascii(self) -> None:
        assert art.validate_stl(STL_BIN) is None
        assert art.validate_stl(STL_ASCII) is None
        assert art.validate_stl(b"solid broken no end") is not None
        assert art.validate_stl(b"") is not None

    def test_office_documents(self) -> None:
        assert art.validate_docx(DOCX) is None
        assert art.validate_xlsx(XLSX) is None
        assert art.validate_pptx(PPTX) is None
        assert art.validate_docx(_zip_bytes({"wrong.xml": b"<x/>"})) is not None
        assert art.validate_docx(b"not a zip at all") is not None

    def test_pdf(self) -> None:
        assert art.validate_pdf(PDF) is None
        assert art.validate_pdf(b"<html>") is not None

    def test_validate_artifact_dispatch_and_empty(self) -> None:
        assert art.validate_artifact("png", PNG) is None
        assert art.validate_artifact("png", WAV) is not None
        assert art.validate_artifact("png", b"") == "empty artifact"
        assert art.validate_artifact("tiff", PNG) is not None

    def test_raw_tool_error_leak(self) -> None:
        assert art.raw_tool_error_leak("Traceback (most recent call last):\n ...") is not None
        assert art.raw_tool_error_leak("clean answer about cubes") is None
        assert art.raw_tool_error_leak('{"code": -32603}') is not None


# ---------------------------------------------------------------- gate

SETTINGS = make_settings(Path("/tmp"))


def _router(
    pipeline: dict | None = None,
    ollama_ps: list | None = None,
    omlx_loaded: list | None = None,
    unload_status: int = 200,
    unload_calls: list | None = None,
    media: bool = True,
):
    """Stateful mock: eviction actually empties residency, like the engines."""
    state = {"ollama_ps": list(ollama_ps or ()), "omlx_loaded": list(omlx_loaded or ())}

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "backends_checked": True,
                    "backends_healthy": 2,
                    "backends_total": 2,
                },
            )
        if url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "q:9b"}]})
        if url.path == "/api/ps":
            return httpx.Response(200, json={"models": state["ollama_ps"]})
        if request.method == "POST" and url.path == "/api/generate":
            state["ollama_ps"] = []
            return httpx.Response(200, json={})
        if url.path == "/v1/models/status":
            models = [
                {"id": str(m.get("name") or m.get("id")), "loaded": True}
                for m in state["omlx_loaded"]
            ]
            return httpx.Response(200, json={"models": models})
        if url.path == "/v1/models/loaded":
            return httpx.Response(200, json={"models": state["omlx_loaded"]})
        if url.path == "/v1/models":
            return httpx.Response(200, json={"data": state["omlx_loaded"]})
        if request.method == "POST" and url.path.startswith("/admin/api/models/"):
            if unload_calls is not None:
                unload_calls.append(request.url.raw_path.decode())
            if unload_status == 400:
                return httpx.Response(400, json={"error": "model not loaded"})
            state["omlx_loaded"] = []
            return httpx.Response(unload_status, json={})
        if any(f":{port}" in str(url) for port in (8918, 8933, 8935)):
            return httpx.Response(200, json={"status": "ok"}) if media else httpx.Response(500)
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


class TestResidency:
    def test_ollama_residency_lists_resident(self) -> None:
        transport = _router(ollama_ps=[{"name": "q:9b"}])
        with httpx.Client(transport=transport) as client:
            result, names = gate.ollama_residency(client, SETTINGS)
        assert names == ["q:9b"]
        assert result.status is Status.WARN  # resident models are a pressure note

    def test_omlx_residency_reads_loaded_flags_from_status_endpoint(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/v1/models/status":
                return httpx.Response(
                    200,
                    json={
                        "loaded_count": 1,
                        "models": [
                            {"id": "cold-model", "loaded": False},
                            {"id": "resident-model", "loaded": True},
                            {"name": "resident-named", "loaded": True},
                        ],
                    },
                )
            return httpx.Response(500)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result, names = gate.omlx_residency(client, SETTINGS)
        assert result.status is Status.WARN
        assert names == ["resident-model", "resident-named"]
        assert calls == ["/v1/models/status"]

    def test_omlx_cold_status_passes_with_no_resident_models(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/v1/models/status":
                return httpx.Response(
                    200,
                    json={"loaded_count": 0, "models": [{"id": "cold-model", "loaded": False}]},
                )
            return httpx.Response(200, json={"data": [{"id": "installed-cold-model"}]})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result, names = gate.omlx_residency(client, SETTINGS)
        assert result.status is Status.PASS
        assert names == []
        assert calls == ["/v1/models/status"]

    def test_omlx_residency_falls_back_to_loaded_endpoint_only(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/v1/models/status":
                return httpx.Response(404)
            if request.url.path == "/v1/models/loaded":
                return httpx.Response(200, json={"models": [{"id": "resident-model"}]})
            return httpx.Response(200, json={"data": [{"id": "installed-cold-model"}]})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result, names = gate.omlx_residency(client, SETTINGS)
        assert result.status is Status.WARN
        assert names == ["resident-model"]
        assert calls == ["/v1/models/status", "/v1/models/loaded"]

    def test_omlx_residency_fails_without_residency_endpoint(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(404)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result, names = gate.omlx_residency(client, SETTINGS)
        assert result.status is Status.FAIL
        assert names == []
        assert calls == ["/v1/models/status", "/v1/models/loaded"]


class TestOWUIAuthentication:
    def test_signin_returns_configured_api_key_without_request(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(500)

        settings = make_settings(Path("/tmp"), OWUI_API_KEY="provided-token")
        client = OWUIClient(settings, httpx.MockTransport(handler))
        assert client.signin() == "provided-token"
        assert calls == []

    def test_signin_uses_password_endpoint_without_api_key(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/auths/signin"
            assert json.loads(request.read()) == {
                "email": "admin@portal.local",
                "password": "pw",
            }
            return httpx.Response(200, json={"token": "signin-token"})

        client = OWUIClient(SETTINGS, httpx.MockTransport(handler))
        assert client.signin() == "signin-token"

    def test_evict_omlx_only_resident_and_tolerates_400(self) -> None:
        unload_calls: list = []
        transport = _router(unload_status=400, unload_calls=unload_calls)
        with httpx.Client(transport=transport) as client:
            result = gate.evict_omlx(client, SETTINGS, ["mlx-4bit"])
        assert result.status is Status.PASS
        assert unload_calls == ["/admin/api/models/mlx-4bit/unload"]

    def test_evict_omlx_fails_on_500(self) -> None:
        transport = _router(unload_status=500)
        with httpx.Client(transport=transport) as client:
            result = gate.evict_omlx(client, SETTINGS, ["mlx-4bit"])
        assert result.status is Status.FAIL

    def test_evict_omlx_noop_when_cold(self) -> None:
        unload_calls: list = []
        transport = _router(unload_calls=unload_calls)
        with httpx.Client(transport=transport) as client:
            result = gate.evict_omlx(client, SETTINGS, [])
        assert result.status is Status.PASS
        assert unload_calls == []


class TestPipelineHealth:
    def test_requires_backends_checked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok", "backends_checked": False})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = gate.pipeline_health(client, SETTINGS)
        assert result.status is Status.FAIL
        assert "backends_checked" in result.detail

    def test_ok_when_registry_ready(self) -> None:
        transport = _router()
        with httpx.Client(transport=transport) as client:
            result = gate.pipeline_health(client, SETTINGS)
        assert result.status is Status.PASS

    def test_down_is_fail(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(503))
        with httpx.Client(transport=transport) as client:
            result = gate.pipeline_health(client, SETTINGS)
        assert result.status is Status.FAIL


class TestVmStat:
    FIXTURE = (
        "Mach Virtual Memory Statistics (page size of 16384 bytes)\n"
        "Pages free: 812543.\nPages active: 1739745.\nPages inactive: 654321.\n"
        "Pages speculative: 112233.\nPages wired down: 987654.\n"
        "Pages purgeable: 5254.\nPages stored in compressor: 1108125.\n"
        "Pages occupied by compressor: 456789.\n"
    )

    def test_parse_vm_stat_counts_compressor_pages_in_the_total(self) -> None:
        used_pct, free_gb = gate.parse_vm_stat(self.FIXTURE)
        total = 812543 + 1739745 + 654321 + 112233 + 987654 + 456789
        expected = (1739745 + 987654) / total * 100
        assert used_pct == pytest.approx(expected, abs=0.01)
        assert free_gb == pytest.approx(812543 * 16384 / 1024**3, abs=0.01)

    def test_parse_vm_stat_empty_is_unreadable_not_99(self) -> None:
        used_pct, free_gb = gate.parse_vm_stat("no data")
        assert used_pct == -1.0
        assert free_gb == 0.0

    def test_vm_memory_skips_when_pages_are_unreadable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gate.sys, "platform", "darwin")
        monkeypatch.setattr(
            gate.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="no data", stderr=""),
        )
        result = gate.vm_memory()
        assert result.status is Status.SKIP
        assert "%" not in result.detail


class TestRunGate:
    def test_gate_passes_when_clean_and_cold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            gate,
            "vm_memory",
            lambda: gate.QATResult("gate-memory", Status.PASS, "used 42.0% (cap 80%)"),
        )
        transport = _router()
        report = gate.run_gate(SETTINGS, "media_heavy", transport=transport, wait=False)
        assert report.ok is True
        assert report.blocked is False
        assert {c.scenario_id for c in report.checks} >= {
            "gate-pipeline",
            "gate-ollama",
            "gate-omlx",
            "gate-memory",
            "gate-media-pressure",
        }

    def test_gate_evicts_resident_then_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            gate,
            "vm_memory",
            lambda: gate.QATResult("gate-memory", Status.PASS, "used 42.0% (cap 80%)"),
        )
        transport = _router(ollama_ps=[{"name": "q:9b"}], omlx_loaded=[{"name": "mlx-4bit"}])
        report = gate.run_gate(SETTINGS, "media_heavy", transport=transport, wait=False)
        assert report.ok is True
        ids = [c.scenario_id for c in report.checks]
        assert "gate-evict" in ids and "gate-evict-omlx" in ids

    def test_gate_blocks_when_pipeline_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            gate,
            "vm_memory",
            lambda: gate.QATResult("gate-memory", Status.PASS, "used 42.0% (cap 80%)"),
        )
        transport = httpx.MockTransport(lambda request: httpx.Response(503))
        report = gate.run_gate(SETTINGS, "next_phase", transport=transport, wait=False)
        assert report.blocked is True
        assert report.ok is False

    def test_gate_warns_at_memory_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            gate,
            "vm_memory",
            lambda: gate.QATResult("gate-memory", Status.WARN, "used 91.0% (cap 80%)"),
        )
        transport = _router()
        report = gate.run_gate(SETTINGS, "next_phase", transport=transport, wait=False)
        assert report.blocked is True
        assert report.ok is False
        assert report.memory_used_pct == pytest.approx(91.0)

    def test_gate_does_not_spin_when_over_cap_and_nothing_is_resident(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gate,
            "vm_memory",
            lambda: gate.QATResult("gate-memory", Status.WARN, "used 91.0% (cap 80%)"),
        )
        base = _router()
        calls = {"residency": 0}

        def counting(request: httpx.Request) -> httpx.Response:
            if request.url.path in ("/api/tags", "/v1/models/status", "/v1/models/loaded"):
                calls["residency"] += 1
            return base.handle_request(request)

        transport = httpx.MockTransport(counting)
        start = time.monotonic()
        report = gate.run_gate(SETTINGS, "next_phase", transport=transport, wait=True)
        elapsed = time.monotonic() - start
        # POLL_S is 15: the old loop slept at least one poll per pass to the 600s budget.
        assert elapsed < 10.0
        assert calls["residency"] <= 6
        assert report.blocked is True and report.ok is False

    def test_media_pressure_reported_never_killed(self) -> None:
        transport = _router(media=True)
        with httpx.Client(transport=transport) as client:
            result = gate.media_pressure(client)
        assert result.status is Status.PASS
        assert "mlx-speech(:8918)" in result.detail
        assert "mflux(:8933)" in result.detail
        assert "video-mlx(:8935)" in result.detail


def test_settings_load_env_fallback(tmp_path: Path) -> None:
    s = make_settings(tmp_path)
    assert s.pipeline_url == "http://localhost:9099"
    assert s.auth_headers() == {"Authorization": "Bearer test-key"}
