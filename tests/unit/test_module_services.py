"""Module → service map: config derivation, up plan, enable/disable lists."""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.inference.cli.module_services import (
    iter_services,
    services_for_module,
    start_argv,
    status_rows,
    stop_argv,
    up_plan,
)
from portal.platform.inference.config import load_portal_config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_eval_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)


_STOPPED = (
    "com.portal5.mflux",
    "com.portal5.video-mlx",
    "com.portal5.music-minimax",
    "com.portal5.music-ace-mcp",
    "com.portal5.acestep-server",
)


def _ids(refs) -> set[str]:
    return {ref.ident for ref in refs}


def test_every_ported_fleet_entry_is_host_or_compose() -> None:
    cfg = load_portal_config()
    for server in cfg.mcp_fleet:
        if server.port is None:
            assert not server.host_native
            assert server.compose_service is None
            continue
        assert server.host_native or server.compose_service
        if server.host_native:
            assert server.launchd_label
            assert server.launchd_label.startswith("com.portal5.")


def test_stdio_servers_are_not_launch_services() -> None:
    fleet_ids = {ref.fleet_id for ref in iter_services(load_portal_config())}
    assert "filesystem" not in fleet_ids
    assert "context7" not in fleet_ids


def test_current_config_stops_image_video_and_music() -> None:
    start, stop = up_plan(load_portal_config())
    start_ids, stop_ids = _ids(start), _ids(stop)
    for ident in _STOPPED:
        assert ident in stop_ids
        assert ident not in start_ids
    assert "mcp-documents" in start_ids
    assert "com.portal5.pipeline-mcp" in start_ids
    assert "com.portal5.ollama" not in start_ids | stop_ids
    assert start_ids.isdisjoint(stop_ids)


def test_up_plan_respects_an_enabled_set() -> None:
    start, stop = up_plan(load_portal_config(), enabled=["documents", "video"])
    start_ids, stop_ids = _ids(start), _ids(stop)
    assert "mcp-documents" in start_ids
    assert "com.portal5.video-mlx" in start_ids
    assert "mcp-sandbox" in stop_ids
    assert "com.portal5.mflux" in stop_ids
    assert "com.portal5.pipeline-mcp" in start_ids
    assert "com.portal5.eg2-embedding" in start_ids
    assert "com.portal5.mlx-speech" in stop_ids
    assert start_ids.isdisjoint(stop_ids)


def test_jobs_without_fleet_entries_follow_their_module() -> None:
    start, stop = up_plan(load_portal_config())
    start_ids, stop_ids = _ids(start), _ids(stop)
    assert "com.portal5.compliance-mcp-eval" in start_ids  # runs with compliance (WFE eval store)
    assert start_ids.isdisjoint(stop_ids)
    assert "com.portal5.mlx-speech" in start_ids
    assert "com.portal5.vl-retrieval" in start_ids
    assert "com.portal5.eg2-embedding" in start_ids


def test_disable_video_stops_only_its_label() -> None:
    refs = services_for_module(load_portal_config(), "video")
    assert [ref.ident for ref in refs] == ["com.portal5.video-mlx"]
    assert stop_argv(refs[0], uid=1) == [["launchctl", "bootout", "gui/1/com.portal5.video-mlx"]]


def test_enable_video_starts_only_its_label() -> None:
    refs = services_for_module(load_portal_config(), "video")
    plist = Path("/tmp/com.portal5.video-mlx.plist")
    flat = [arg for argv in start_argv(refs[0], uid=1, plist=plist) for arg in argv]
    assert "bootstrap" in flat
    assert "kickstart" in flat
    assert str(plist) in flat
    assert "com.portal5.mflux" not in flat


def test_stop_never_drops_volumes_or_plists() -> None:
    for ref in iter_services(load_portal_config()):
        for argv in stop_argv(ref, uid=1):
            assert "down" not in argv
            assert "-v" not in argv
            assert "rm" not in argv
            if ref.kind == "host":
                assert argv[:2] == ["launchctl", "bootout"]
            else:
                assert argv == ["docker", "compose", "stop", ref.ident]


def test_music_disable_lists_fleet_and_extra_jobs() -> None:
    idents = [ref.ident for ref in services_for_module(load_portal_config(), "music")]
    assert idents == [
        "com.portal5.acestep-server",
        "com.portal5.music-ace-mcp",
        "com.portal5.music-minimax",
    ]


def test_status_rows_show_module_and_state_without_probing() -> None:
    rows = status_rows(load_portal_config(), runtime={"com.portal5.video-mlx": "down"})
    video = next(row for row in rows if "com.portal5.video-mlx" in row)
    assert video.startswith("video")
    assert "disabled" in video
    assert "down" in video


def test_launch_does_not_hardcode_module_launchd_starts() -> None:
    util = (ROOT / "scripts" / "lib" / "util.sh").read_text(encoding="utf-8")
    launch = (ROOT / "launch.sh").read_text(encoding="utf-8")
    assert "_portal_module_services --apply --kind host" in util
    assert "launchctl start com.portal5.mflux" not in util
    assert "launchctl start com.portal5.video-mlx" not in util
    assert "launchctl start com.portal5.music-minimax" not in util
    assert "_compose_up_enabled" in launch
    assert "_portal_module_services --status" in util
