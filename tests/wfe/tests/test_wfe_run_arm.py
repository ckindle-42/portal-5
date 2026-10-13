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


def _cli_env(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    monkeypatch.setattr(campaign, "expand_matrix", lambda *a, **k: list(rows))
    for name, fn in (
        ("_warn_prompt_surface", lambda m: None),
        ("_ready", lambda d: True),
        ("ollama_reachable", lambda: True),
        ("build_review_queue", lambda d: 0),
        ("config_dirty", lambda: []),
    ):
        monkeypatch.setattr(campaign, name, fn)
    return plan


ROW = {
    "run_id": "w|a|s|t|r0",
    "arm": "a",
    "workspace": "w",
    "suite": "s",
    "task_id": "t",
    "repeat": 0,
}


def test_cli_exit_codes_for_every_arm_outcome(tmp_path, monkeypatch):
    plan = _cli_env(tmp_path, monkeypatch, [ROW])
    cases = [
        ({"ran": 0, "blocked": 1}, 6),
        ({"stopped": "failover"}, 5),
        ({"ran": 1}, 0),
        ({"ran": 0}, 0),
    ]
    for i, (out, want) in enumerate(cases):
        monkeypatch.setattr(campaign, "execute_arm", lambda *a, o=out, **k: dict(o))
        monkeypatch.setattr(
            sys, "argv", ["campaign", "--plan", str(plan), "--campaign-id", f"c{i}"]
        )
        assert campaign.main() == want, out


def test_cli_exits_7_when_the_arm_selection_matches_nothing(tmp_path, monkeypatch):
    plan = _cli_env(tmp_path, monkeypatch, [ROW])
    monkeypatch.setattr(campaign, "execute_arm", lambda *a, **k: {"ran": 1})
    argv = ["campaign", "--plan", str(plan), "--campaign-id", "c", "--arm", "no-such-arm"]
    monkeypatch.setattr(sys, "argv", argv)
    assert campaign.main() == campaign.EXIT_NO_SELECTION


def test_supervisor_records_a_blocked_arm_from_the_real_cli(tmp_path):
    """The real CLI in a child process, preflight faked as blocked: the supervisor logs 6."""
    child = f"""
import sys
from pathlib import Path
from tests.wfe import campaign as c
c.CAMPAIGNS = Path({str(tmp_path / "campaigns")!r})
c.expand_matrix = lambda *a, **k: [{ROW!r}]
c._warn_prompt_surface = lambda m: None
c._ready = lambda d: True
c.ollama_reachable = lambda: True
c.instrument_dirty = lambda: []
c.env_fingerprint = lambda *a, **k: {{}}
c.build_review_queue = lambda d: 0
c.config_dirty = lambda: []
c.execute_arm = lambda *a, **k: {{"arm": "a", "ran": 0, "blocked": 1}}
sys.argv = ["campaign", "--plan", {str(tmp_path / "plan.yaml")!r}, "--campaign-id", "c"]
sys.exit(c.main())
"""
    (tmp_path / "plan.yaml").write_text("workloads: {}\n")
    pid, log = tmp_path / "pids", tmp_path / "exits.log"
    pid.write_text("")
    rc = run_arm.supervise([sys.executable, "-c", child], pid, log, "a")
    assert rc == campaign.EXIT_BLOCKED and f"exit={campaign.EXIT_BLOCKED}" in log.read_text()


def test_completion_requires_a_model_quality_result_for_every_expected_row(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    rows = [{**ROW, "run_id": f"w|a|s|t{i}|r0", "task_id": f"t{i}"} for i in range(3)]
    d = campaign.open_campaign("c", plan, rows, append=False)
    base = campaign.load_manifest(d)["instrument"]
    write = lambda rid, outcome, fp=base: campaign._row_path(d, rid).write_text(  # noqa: E731
        json.dumps({"outcome": outcome, "instrument": fp})
    )
    write(rows[0]["run_id"], "PASS")
    write(rows[1]["run_id"], "BLOCKED")
    probs = campaign.completion_problems(d)
    assert (
        len(probs) == 2
        and any("BLOCKED" in p for p in probs)
        and any("no result" in p for p in probs)
    )
    write(rows[1]["run_id"], "FAIL")
    write(rows[2]["run_id"], "PASS", {"fingerprint": "other"})
    assert campaign.completion_problems(d) == [
        f"{rows[2]['run_id']}: measured under another instrument"
    ]
    write(rows[2]["run_id"], "PASS")
    assert campaign.completion_problems(d) == [] and campaign._cmd_verify_complete(d) == 0
