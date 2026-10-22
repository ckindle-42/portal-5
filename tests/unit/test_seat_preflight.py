"""Tests for the static checks that run before a WFE seat screen."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import seat_preflight as preflight


def test_container_environment_values_are_rejected() -> None:
    issues = preflight._container_environment_issues(
        {
            "PIPELINE_URL": "http://portal-pipeline:9099",
            "PROMETHEUS_MULTIPROC_DIR": "/dev/shm/portal_metrics",
        }
    )

    assert len(issues) == 2
    assert "PIPELINE_URL" in issues[0]
    assert "PROMETHEUS_MULTIPROC_DIR" in issues[1]


def test_host_environment_values_are_allowed() -> None:
    assert (
        preflight._container_environment_issues(
            {
                "PIPELINE_URL": "http://localhost:9099",
                "PROMETHEUS_MULTIPROC_DIR": "/tmp/host-metrics",
            }
        )
        == []
    )


def test_sidecar_keep_alive_must_be_known_and_nonzero() -> None:
    assert preflight._sidecar_issues("http://localhost:11434", None)
    assert "keep_alive is 0" in preflight._sidecar_issues("http://localhost:11434", "0s")[0]
    assert preflight._sidecar_issues("http://localhost:11434", "5m") == []
    assert preflight._sidecar_issues(None, "0") == []


def test_jsonc_parser_accepts_comments_and_trailing_commas() -> None:
    value = preflight._parse_jsonc(
        '{\n  // comment\n  "providers": {"portal": {"models": {"seat": {},},},},\n}'
    )

    assert value["providers"]["portal"]["models"] == {"seat": {}}


def test_default_screen_model_uses_the_variant_slug() -> None:
    assert preflight._default_screen_model("auto-coding") == "opencode:portal/auto-coding"
    assert (
        preflight._default_screen_model("auto-coding::qwen38coder-dflash")
        == "opencode:portal/qwen38coder-dflash"
    )


def test_committed_opencode_model_requires_a_clean_tracked_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    config = tmp_path / "opencode.jsonc"
    config.write_text(
        '{"providers":{"portal":{"settings":{"baseURL":"http://localhost:9099/v1"},'
        '"models":{"seat":{}}}}}'
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", "opencode.jsonc"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "add seat model"], check=True)

    assert preflight._committed_opencode_model(tmp_path, "opencode:portal/seat") == []
    config.write_text(config.read_text() + "\n")
    assert any(
        "not committed" in issue
        for issue in preflight._committed_opencode_model(tmp_path, "opencode:portal/seat")
    )


def test_omlx_alias_routed_to_ollama_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = "auto-coding::qwen38coder"
    workspace, _workspaces, _portal = preflight._load_seat(preflight.ROOT, workspace_id)
    monkeypatch.setattr(
        preflight.settings_audit,
        "_served_path",
        lambda *_args: ("ollama", "ollama-coding", "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M"),
    )

    reasons = preflight._served_engine(preflight.ROOT, workspace_id, workspace, None)

    assert any("should use omlx" in reason for reason in reasons)


def test_main_host_quiet_gate_records_snapshots_before_seat_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    context = {
        "allowed": False,
        "force_requested": False,
        "override_reason": None,
        "blockers": ["pytest/xdist is running (pid 42)"],
        "start": {"headroom_gib": 4.0},
    }
    monkeypatch.setattr(sys, "argv", ["seat_preflight.py", "--workspace", "seat"])
    monkeypatch.setattr(preflight, "preflight", lambda _args: [])
    monkeypatch.setattr(preflight.host_quiet, "begin_run", lambda *a, **k: context)
    monkeypatch.setattr(
        preflight.host_quiet,
        "finish_run",
        lambda record, *a: record.update(end={"headroom_gib": 3.0}),
    )

    assert preflight.main() == 1
    out = capsys.readouterr().out
    assert "pytest/xdist is running" in out
    assert '"end": {"headroom_gib": 3.0}' in out
