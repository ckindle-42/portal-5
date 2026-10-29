"""Module → service map: config derivation, up plan, enable/disable lists."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from portal.platform.inference.cli.module_services import (
    format_native_mcp_target,
    iter_services,
    native_mcp_targets,
    run_services_cli,
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


def test_omlx_probe_auth_expansion_handles_empty_bash_array() -> None:
    util = (ROOT / "scripts" / "lib" / "util.sh").read_text(encoding="utf-8")
    command = next(
        line.strip() for line in util.splitlines() if line.strip().startswith("if curl -fsS -m 5")
    )
    auth_argument = command.split("-m 5 ", 1)[1].split(' "http://127.0.0.1:8085/v1/models"', 1)[0]
    script = f'_omlx_auth=(); set -- {auth_argument}; test "$#" -eq 0'

    result = subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_native_mcp_targets_are_enabled_wrapper_services() -> None:
    cfg = load_portal_config()
    targets = native_mcp_targets(cfg)
    idents = {ref.ident for ref in targets}
    assert "com.portal5.data-mcp" in idents
    assert "com.portal5.compliance-mcp" in idents
    assert "com.portal5.compliance-mcp-eval" in idents
    assert "com.portal5.pipeline-mcp" in idents
    assert "com.portal5.mlx-transcribe" in idents
    assert "mcp-documents" not in idents
    assert "com.portal5.video-mlx" not in idents
    assert "com.portal5.mflux" not in idents
    assert "com.portal5.ollama" not in idents
    assert "com.portal5.eg2-embedding" not in idents
    assert "com.portal5.vl-retrieval" not in idents
    assert "com.portal5.mlx-speech" not in idents
    assert all(ref.kind == "host" and ref.native_service and ref.port for ref in targets)
    assert format_native_mcp_target(
        next(ref for ref in targets if ref.ident == "com.portal5.data-mcp")
    ) == ("com.portal5.data-mcp 8939")


def test_native_mcp_cli_prints_label_and_port(capsys: pytest.CaptureFixture[str]) -> None:
    run_services_cli(
        enabled=False,
        disabled=False,
        kind=None,
        module=None,
        apply=False,
        stop_only=False,
        status=False,
        native_mcp=True,
    )
    out = capsys.readouterr().out.splitlines()
    assert "com.portal5.data-mcp 8939" in out
    assert "com.portal5.compliance-mcp 8937" in out
    assert "com.portal5.compliance-mcp-eval 8948" in out
    assert all(not line.startswith("mcp-") for line in out)
    assert "com.portal5.video-mlx" not in "\n".join(out)


def test_rebuild_restarts_native_mcps_after_containers() -> None:
    launch = (ROOT / "launch.sh").read_text(encoding="utf-8")
    rebuild = launch.split("  rebuild)", 1)[1].split("  rebuild-mcp)", 1)[0]
    assert "_restart_native_mcps" in rebuild
    assert rebuild.index("docker compose up -d") < rebuild.index("_restart_native_mcps")
    assert "com.portal5.data-mcp" not in rebuild
    assert "com.portal5.compliance-mcp" not in rebuild


def _stub_bin(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_restart_native_mcps_kickstarts_and_waits_with_stubs(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"
    _stub_bin(
        bin_dir / "uname",
        '#!/bin/bash\nif [ "${1:-}" = "-s" ]; then echo Darwin; else /usr/bin/uname "$@"; fi\n',
    )
    _stub_bin(
        bin_dir / "launchctl",
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'if [ -n "${FAIL_LABEL:-}" ] && [[ "$*" == *"$FAIL_LABEL"* ]]; then exit 1; fi\n'
        "exit 0\n",
    )
    _stub_bin(
        bin_dir / "curl",
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'if [ "${FAIL_HEALTH:-}" = "1" ]; then exit 1; fi\n'
        "exit 0\n",
    )
    script = f"""
set -euo pipefail
export PATH="{bin_dir}:$PATH"
export CALL_LOG="{log}"
export PORTAL_NATIVE_MCP_HEALTH_TRIES=1
source "{ROOT}/scripts/lib/util.sh"
_portal_module_services() {{
  printf '%s\\n' "com.portal5.data-mcp 8939" "com.portal5.compliance-mcp-eval 8948"
}}
_restart_native_mcps
"""
    result = subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "[portal-5]   com.portal5.data-mcp: healthy :8939" in result.stdout
    assert "[portal-5]   com.portal5.compliance-mcp-eval: healthy :8948" in result.stdout
    calls = log.read_text(encoding="utf-8")
    uid = os.getuid()
    assert f"kickstart -k gui/{uid}/com.portal5.data-mcp" in calls
    assert f"kickstart -k gui/{uid}/com.portal5.compliance-mcp-eval" in calls
    assert "http://127.0.0.1:8939/health" in calls
    assert "http://127.0.0.1:8948/health" in calls


def test_restart_native_mcps_records_kickstart_failure_and_continues(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"
    _stub_bin(
        bin_dir / "uname",
        '#!/bin/bash\nif [ "${1:-}" = "-s" ]; then echo Darwin; else /usr/bin/uname "$@"; fi\n',
    )
    _stub_bin(
        bin_dir / "launchctl",
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'if [[ "$*" == *data-mcp* ]]; then exit 1; fi\n'
        "exit 0\n",
    )
    _stub_bin(
        bin_dir / "curl",
        '#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit 0\n',
    )
    script = f"""
set -euo pipefail
export PATH="{bin_dir}:$PATH"
export CALL_LOG="{log}"
source "{ROOT}/scripts/lib/util.sh"
_portal_module_services() {{
  printf '%s\\n' "com.portal5.data-mcp 8939" "com.portal5.compliance-mcp 8937"
}}
_restart_native_mcps
"""
    result = subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    assert "[portal-5]   com.portal5.data-mcp: kickstart failed" in result.stdout
    assert "[portal-5]   com.portal5.compliance-mcp: healthy :8937" in result.stdout
    calls = log.read_text(encoding="utf-8")
    assert "http://127.0.0.1:8939/health" not in calls
    assert "http://127.0.0.1:8937/health" in calls


def test_restart_native_mcps_health_timeout(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_bin(
        bin_dir / "uname",
        '#!/bin/bash\nif [ "${1:-}" = "-s" ]; then echo Darwin; else /usr/bin/uname "$@"; fi\n',
    )
    _stub_bin(bin_dir / "launchctl", "#!/bin/bash\nexit 0\n")
    _stub_bin(bin_dir / "curl", "#!/bin/bash\nexit 1\n")
    script = f"""
set -euo pipefail
export PATH="{bin_dir}:$PATH"
export PORTAL_NATIVE_MCP_HEALTH_TRIES=1
source "{ROOT}/scripts/lib/util.sh"
_portal_module_services() {{ printf '%s\\n' "com.portal5.data-mcp 8939"; }}
_restart_native_mcps
"""
    result = subprocess.run(["/bin/bash", "-uc", script], capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    assert "[portal-5]   com.portal5.data-mcp: health timeout :8939" in result.stdout
