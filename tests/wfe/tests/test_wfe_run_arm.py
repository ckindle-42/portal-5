"""The arm supervisor registers the real stoppable process, and every failure surfaces."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time

from tests.wfe import campaign, run_arm


def test_child_exit_status_is_returned_and_logged(tmp_path):
    pid, log = tmp_path / "pids", tmp_path / "exits.log"
    pid.write_text("")
    rc = run_arm.supervise([sys.executable, "-c", "import sys; sys.exit(23)"], pid, log, "armA")
    assert rc == 23 and "arm=armA" in log.read_text() and "exit=23" in log.read_text()
    assert pid.read_text().strip().isdigit()


def test_watchdog_kill_of_the_registered_pid_is_a_failure(tmp_path):
    pid, log = tmp_path / "pids", tmp_path / "exits.log"
    pid.write_text("")

    def watchdog():
        for _ in range(200):
            if pid.read_text().strip():
                os.kill(int(pid.read_text().split()[0]), signal.SIGTERM)
                return
            time.sleep(0.02)

    threading.Thread(target=watchdog, daemon=True).start()
    rc = run_arm.supervise([sys.executable, "-c", "import time; time.sleep(30)"], pid, log, "armB")
    assert rc == 128 + signal.SIGTERM and "exit=143" in log.read_text()


def test_main_runs_the_campaign_module_with_the_given_arguments(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(run_arm, "supervise", lambda cmd, p, log, label: seen.update(cmd=cmd) or 0)
    run_arm.main(
        ["--exit-log", str(tmp_path / "x"), "--label", "a", "--", "--arm", "m", "--tier", "screen"]
    )
    assert seen["cmd"][1:] == ["-m", "tests.wfe.campaign", "--arm", "m", "--tier", "screen"]


def test_cli_returns_nonzero_when_an_arm_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    row = {"run_id": "r", "arm": "a", "workspace": "w", "suite": "s", "task_id": "t", "repeat": 0}
    monkeypatch.setattr(campaign, "expand_matrix", lambda *a, **k: [row])
    monkeypatch.setattr(campaign, "_warn_prompt_surface", lambda m: None)
    monkeypatch.setattr(campaign, "_ready", lambda d: True)
    monkeypatch.setattr(campaign, "ollama_reachable", lambda: True)
    monkeypatch.setattr(campaign, "build_review_queue", lambda d: 0)
    monkeypatch.setattr(campaign, "config_dirty", lambda: [])
    argv = ["campaign", "--plan", str(plan), "--campaign-id", "c"]
    for stopped, want in (("failover", 5), (None, 0)):
        monkeypatch.setattr(campaign, "execute_arm", lambda *a, s=stopped, **k: {"stopped": s})
        monkeypatch.setattr(sys, "argv", argv)
        assert campaign.main() == want
