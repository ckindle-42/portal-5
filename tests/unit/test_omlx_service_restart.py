"""oMLX restart helpers target the live service (venv LaunchAgent or brew)."""

import os
import subprocess

import scripts.omlx_memory_tier as memory_tier
import scripts.omlx_seat_defaults as seat_defaults
import scripts.omlx_venv_install as venv_install
import tests.wfe.campaign as campaign
from scripts.omlx_venv_install import (
    OMLX_BREW_SERVICE,
    OMLX_VENV_LABEL,
    omlx_restart_command,
    venv_service_active,
)


def _fake_run(returncode: int, calls: list[list[str]]):
    def run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, returncode)

    return run


def test_venv_service_active_requires_a_venv_python(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(venv_install.subprocess, "run", _fake_run(0, calls))
    assert venv_service_active(tmp_path) is False
    assert calls == []


def test_venv_service_active_probes_the_venv_launchagent(tmp_path, monkeypatch):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").write_text("")
    calls: list[list[str]] = []
    monkeypatch.setattr(venv_install.subprocess, "run", _fake_run(0, calls))
    assert venv_service_active(tmp_path) is True
    assert calls == [["launchctl", "print", f"gui/{os.getuid()}/{OMLX_VENV_LABEL}"]]

    calls.clear()
    monkeypatch.setattr(venv_install.subprocess, "run", _fake_run(1, calls))
    assert venv_service_active(tmp_path) is False


def test_restart_command_kickstarts_the_venv_agent(monkeypatch):
    monkeypatch.setattr(venv_install, "venv_service_active", lambda venv=None: True)
    assert omlx_restart_command() == [
        "launchctl",
        "kickstart",
        "-k",
        f"gui/{os.getuid()}/{OMLX_VENV_LABEL}",
    ]


def test_restart_command_falls_back_to_brew(monkeypatch):
    monkeypatch.setattr(venv_install, "venv_service_active", lambda venv=None: False)
    assert omlx_restart_command() == ["brew", "services", "restart", OMLX_BREW_SERVICE]


def test_seat_defaults_restart_targets_omlx_restart_command(monkeypatch, capsys):
    sent: list[list[str]] = []
    monkeypatch.setattr(seat_defaults, "apply", lambda defaults, dry: True)
    monkeypatch.setattr(seat_defaults, "omlx_restart_command", lambda: ["echo", "restarted"])
    monkeypatch.setattr(seat_defaults.subprocess, "run", _fake_run(0, sent))
    assert seat_defaults.main([]) == 0
    assert sent == [["echo", "restarted"]]
    assert "oMLX restarted" in capsys.readouterr().out


def test_seat_defaults_dry_run_does_not_restart(monkeypatch):
    sent: list[list[str]] = []
    monkeypatch.setattr(seat_defaults, "apply", lambda defaults, dry: True)
    monkeypatch.setattr(seat_defaults, "omlx_restart_command", lambda: ["echo", "restarted"])
    monkeypatch.setattr(seat_defaults.subprocess, "run", _fake_run(0, sent))
    assert seat_defaults.main(["--dry-run"]) == 0
    assert sent == []


def test_memory_tier_restart_targets_omlx_restart_command(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text('{"memory": {"memory_guard_tier": "safe"}}')
    sent: list[list[str]] = []
    real_set_tier = memory_tier.set_tier
    monkeypatch.setattr(memory_tier, "set_tier", lambda tier: real_set_tier(tier, settings))
    monkeypatch.setattr(memory_tier, "omlx_restart_command", lambda: ["echo", "restarted"])
    monkeypatch.setattr(memory_tier.subprocess, "run", _fake_run(0, sent))

    assert memory_tier.main(["balanced"]) == 0
    assert sent == [["echo", "restarted"]]
    assert '"memory_guard_tier": "balanced"' in settings.read_text()

    sent.clear()
    assert memory_tier.main(["balanced"]) == 0
    assert sent == []


def test_wfe_drain_restarts_the_active_service(monkeypatch):
    sent: list[list[str]] = []
    pools = iter([{"loaded_count": 2}, {"loaded_count": 0}])
    monkeypatch.setattr(campaign, "_omlx_pool", lambda: next(pools))
    monkeypatch.setattr(campaign.subprocess, "run", _fake_run(0, sent))
    monkeypatch.setattr(venv_install, "omlx_restart_command", lambda: ["echo", "drain-restart"])

    assert "release 2 resident model(s)" in campaign.drain_omlx(timeout_s=1)
    assert sent == [["echo", "drain-restart"]]


def test_wfe_drain_skips_an_empty_pool(monkeypatch):
    sent: list[list[str]] = []
    monkeypatch.setattr(campaign, "_omlx_pool", lambda: {"loaded_count": 0})
    monkeypatch.setattr(campaign.subprocess, "run", _fake_run(0, sent))

    assert campaign.drain_omlx(timeout_s=1) == "oMLX pool empty"
    assert sent == []
