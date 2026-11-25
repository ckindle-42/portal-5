"""The LoadGuard's container settings handoff (2026-11-24 live finding).

Inside portal5-pipeline, ``OMLX_PREFILL_SAFE_ZONE_RATIO`` and
``OMLX_MEMORY_GUARD_TIER`` were both empty whenever the container started via
bare ``docker compose up``, and ``~/.omlx/settings.json`` was not mounted, so
the guard ran blind: oMLX cold loads were admitted past the prefill safe zone
(mid-prefill 507 aborts) and cross-engine evictions missed the balanced tier's
reclaim share. The fix is three-sided — compose defaults, the read-only
``/host_omlx/settings.json`` mount as the guard's file fallback, and a
``backend.failed`` span that names model, status and error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml

from portal.platform.inference import load_guard as lg
from portal.platform.inference.router import streaming
from portal.platform.inference.router import trace as trace_mod
from tests.qat import preflight
from tests.qat.config import Settings
from tests.qat.models import Status

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "deploy" / "portal-5" / "docker-compose.yml"
GIB = 1024**3


def _blind(monkeypatch, tmp_path: Path) -> None:
    """No env vars, no host settings file: only the container mount can answer."""
    for name in (
        "OMLX_PREFILL_SAFE_ZONE_RATIO",
        "OMLX_OTHER_APP_RECLAIM_RATIO",
        "OMLX_MEMORY_GUARD_TIER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(lg, "OMLX_SERVER_SETTINGS", tmp_path / "absent-host-settings.json")


def test_prefill_zone_falls_back_to_the_container_mount(tmp_path, monkeypatch):
    mount = tmp_path / "host_omlx-settings.json"
    mount.write_text(json.dumps({"memory": {"prefill_safe_zone_ratio": 0.7}}))
    _blind(monkeypatch, tmp_path)
    monkeypatch.setattr(lg, "_CONTAINER_OMLX_SETTINGS", mount)

    assert lg._omlx_prefill_zone() == 0.7


def test_reclaim_ratio_falls_back_to_the_container_mount(tmp_path, monkeypatch):
    mount = tmp_path / "host_omlx-settings.json"
    mount.write_text(json.dumps({"memory": {"memory_guard_tier": "aggressive"}}))
    _blind(monkeypatch, tmp_path)
    monkeypatch.setattr(lg, "_CONTAINER_OMLX_SETTINGS", mount)

    assert lg._omlx_reclaim_ratio() == 0.5


def test_custom_tier_on_the_container_mount_means_no_cross_engine_reclaim(tmp_path, monkeypatch):
    mount = tmp_path / "host_omlx-settings.json"
    mount.write_text(json.dumps({"memory": {"memory_guard_tier": "custom"}}))
    _blind(monkeypatch, tmp_path)
    monkeypatch.setattr(lg, "_CONTAINER_OMLX_SETTINGS", mount)

    assert lg._omlx_reclaim_ratio() == 1.0


def test_both_shares_stay_none_when_no_settings_source_is_readable(tmp_path, monkeypatch):
    _blind(monkeypatch, tmp_path)
    monkeypatch.setattr(lg, "_CONTAINER_OMLX_SETTINGS", tmp_path / "absent-container.json")

    assert lg._omlx_prefill_zone() is None
    assert lg._omlx_reclaim_ratio() is None


def test_the_env_tier_still_wins_over_the_mounted_file(tmp_path, monkeypatch):
    mount = tmp_path / "host_omlx-settings.json"
    mount.write_text(json.dumps({"memory": {"memory_guard_tier": "aggressive"}}))
    _blind(monkeypatch, tmp_path)
    monkeypatch.setattr(lg, "_CONTAINER_OMLX_SETTINGS", mount)
    monkeypatch.setenv("OMLX_MEMORY_GUARD_TIER", "balanced")

    assert lg._omlx_reclaim_ratio() == 0.25


def test_compose_mounts_the_host_settings_and_defaults_both_vars():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    service = compose["services"]["portal-pipeline"]

    assert "${HOME}/.omlx/settings.json:/host_omlx/settings.json:ro" in service["volumes"]
    env = service["environment"]
    assert "OMLX_PREFILL_SAFE_ZONE_RATIO=${OMLX_PREFILL_SAFE_ZONE_RATIO:-0.8}" in env
    assert "OMLX_MEMORY_GUARD_TIER=${OMLX_MEMORY_GUARD_TIER:-balanced}" in env


def test_settle_window_default_covers_the_083_async_reclaim():
    assert lg._OMLX_SETTLE_S == 12.0


def test_startup_summary_reports_the_active_handoff(caplog, monkeypatch):
    monkeypatch.setattr(lg, "_OMLX_PREFILL_ZONE", 0.8)
    monkeypatch.setattr(lg, "_OMLX_RECLAIM_RATIO", 0.25)
    monkeypatch.setattr(lg, "_OMLX_SETTLE_S", 12.0)
    monkeypatch.setattr(lg, "_MARGIN", 2 * GIB)
    monkeypatch.setattr(lg, "_startup_summary_done", False)
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        lg._log_startup_summary()

    assert any(
        "prefill_zone=0.8 reclaim_ratio=0.25 margin_gib=2.0 omlx_settle_s=12" in r.getMessage()
        for r in caplog.records
    )
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_startup_summary_warns_loudly_when_the_guard_is_blind(caplog, monkeypatch):
    monkeypatch.setattr(lg, "_OMLX_PREFILL_ZONE", None)
    monkeypatch.setattr(lg, "_OMLX_RECLAIM_RATIO", None)
    monkeypatch.setattr(lg, "_startup_summary_done", False)
    with caplog.at_level(logging.WARNING, logger=lg.logger.name):
        lg._log_startup_summary()

    assert any(
        "running blind" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    )


def test_the_summary_fires_once_at_first_guard_construction(caplog, monkeypatch):
    monkeypatch.setattr(lg, "_OMLX_PREFILL_ZONE", 0.8)
    monkeypatch.setattr(lg, "_OMLX_RECLAIM_RATIO", 0.25)
    monkeypatch.setattr(lg, "_startup_summary_done", False)
    with caplog.at_level(logging.INFO, logger=lg.logger.name):
        lg.LoadGuard(omlx_url=lambda: None)
        lg.LoadGuard(omlx_url=lambda: None)

    summaries = [r for r in caplog.records if "active memory handoff" in r.getMessage()]
    assert len(summaries) == 1


# ── the enriched backend.failed span ─────────────────────────────────────────


def test_streaming_backend_failed_span_names_model_status_and_error(monkeypatch, tmp_path):
    error_chunk = (
        b'data: {"error": "Cannot load seat-model: projected memory 24.6 GiB would '
        b'exceed host headroom 12.1 GiB", "status": 507}\n\n'
    )

    def fake_select(*_args, **_kwargs):
        async def frames():
            yield error_chunk

        return frames()

    async def fake_exhausted(*_args, **_kwargs):
        return [b"data: [DONE]\n\n"]

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(streaming, "make_room_for_omlx", noop)
    monkeypatch.setattr(streaming, "_select_stream_fn", fake_select)
    monkeypatch.setattr(streaming, "_exhausted_frames", fake_exhausted)
    monkeypatch.setattr(trace_mod, "ENABLED", True)
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path))
    trace_mod.start_trace("p5-loadguard01")

    backend = SimpleNamespace(
        id="ollama-primary", type="ollama", chat_url="http://ollama.test/v1/chat/completions"
    )
    body = {"model": "seat-model", "messages": []}

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._stream_with_fallback(
            backend,
            body,
            "auto-coding",
            "seat-model",
            "",
            [],
            time.monotonic(),
            False,
            [],
            False,
            "",
            "",
            [],
            SimpleNamespace(),
            body,
        ):
            out += chunk
        return out

    asyncio.run(run())
    trace_mod.finalize_trace()

    record = trace_mod.read_trace("p5-loadguard01")
    assert record is not None
    span = next(s for s in record["spans"] if s["name"] == "backend.failed")
    assert span["backend"] == "ollama-primary"
    assert span["model"] == "seat-model"
    assert span["status_code"] == 507
    assert span["error"].startswith("Cannot load seat-model")
    assert len(span["error"]) <= 200


# ── the QAT preflight probe ──────────────────────────────────────────────────


def _settings(pipeline_url: str) -> Settings:
    return Settings.load(
        env_file=Path("/nonexistent/.env"),
        environ={
            "PIPELINE_URL": pipeline_url,
            "PIPELINE_API_KEY": "test-key",
            "OPENWEBUI_ADMIN_PASSWORD": "pw",
        },
    )


def test_preflight_guard_probe_passes_on_a_live_ceiling():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            text=(
                "# HELP portal5_load_guard_ceiling_bytes oMLX ceiling\n"
                "# TYPE portal5_load_guard_ceiling_bytes gauge\n"
                "portal5_load_guard_ceiling_bytes 6.4e+10\n"
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = preflight.load_guard_probe(_settings("http://pipeline.test"), client)
    assert result.status is Status.PASS
    assert result.evidence["portal5_load_guard_ceiling_bytes"] == 6.4e10


def test_preflight_guard_probe_warns_when_the_gauge_is_absent():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="portal5_some_other_metric 1\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = preflight.load_guard_probe(_settings("http://pipeline.test"), client)
    assert result.status is Status.WARN
    assert "portal5_load_guard_ceiling_bytes absent" in result.detail


def test_preflight_guard_probe_warns_when_the_ceiling_reads_zero():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="portal5_load_guard_ceiling_bytes 0\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = preflight.load_guard_probe(_settings("http://pipeline.test"), client)
    assert result.status is Status.WARN
    assert "ceiling reads 0" in result.detail


def test_preflight_guard_probe_skips_when_the_pipeline_is_not_live():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = preflight.load_guard_probe(_settings("http://pipeline.test"), client)
    assert result.status is Status.SKIP
