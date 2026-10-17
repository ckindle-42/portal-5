"""The arm supervisor registers the real stoppable process, and every failure surfaces."""

from __future__ import annotations

import json
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


def test_pipeline_preflight_asks_the_pipeline_for_each_arms_workspaces(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    rows = [
        {**ROW, "run_id": "w1|m|s|t|r0", "workspace": "auto-compliance", "model": "m"},
        {**ROW, "run_id": "w2|m|s|t|r0", "workspace": "auto-coding", "model": "m"},
    ]
    d = campaign.open_campaign("c", plan, rows, append=False)
    seen = []
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(campaign, "drain_others", lambda *a: [])
    monkeypatch.setattr(campaign, "drain_model", lambda *a: True)
    monkeypatch.setattr(campaign, "model_sizes", lambda: {})
    monkeypatch.setattr(campaign, "row_model", lambda r: "m")
    monkeypatch.setattr(
        campaign, "preflight_pipeline", lambda ws, m: seen.append((ws, m)) or {"verdict": "OK"}
    )

    def wrong(*a, **k):
        raise AssertionError("the raw-transport preflight must not run in pipeline mode")

    monkeypatch.setattr(campaign, "preflight_arm", wrong)
    assert campaign._cmd_preflight(d, False) == 0
    assert seen == [(["auto-coding", "auto-compliance"], "m")]


def test_a_gate_refusal_exits_4_with_its_reason(tmp_path, monkeypatch, capsys):
    plan = _cli_env(tmp_path, monkeypatch, [ROW])
    monkeypatch.setattr(campaign, "instrument_dirty", lambda: ["tests/wfe/runner.py"])
    monkeypatch.delenv("WFE_ALLOW_DIRTY_INSTRUMENT", raising=False)
    monkeypatch.setattr(sys, "argv", ["campaign", "--plan", str(plan), "--campaign-id", "c"])
    assert campaign._cli() == campaign.EXIT_GATE
    assert "uncommitted changes" in capsys.readouterr().err


# --- auto-halt and repeats policy (WFE master plan S3) ---------------------------------


def _row(outcome="PASS", tools=1, hop=False):
    return {
        "outcome": outcome,
        "tool_calls": tools,
        "transcript": [{"exhausted_turns": "x"}] if hop else [],
    }


def _halt(rows, arm="a", kind="k"):
    campaign._KIND_ROWS.clear()
    return [campaign.kind_halt_reason(arm, kind, r) for r in rows]


def test_task_kind_is_explicit_or_the_id_without_its_index():
    assert campaign.task_kind({"id": "doc-read-03"}) == "doc-read"
    assert campaign.task_kind({"id": "data-prod-sales-12"}) == "data-prod-sales"
    assert campaign.task_kind({"id": "x-01", "kind": "lookup"}) == "lookup"


def test_no_halt_before_n_rows_of_a_kind():
    assert _halt([_row("FAIL"), _row("FAIL"), _row("FAIL")]) == [None, None, None]


def test_halt_on_pass_rate_at_most_one_in_n():
    out = _halt([_row("FAIL"), _row("PASS"), _row("FAIL"), _row("FAIL")])
    assert out[:3] == [None] * 3 and "1/4 <= 1/4" in out[3]


def test_a_kind_above_the_pass_floor_keeps_running():
    assert _halt([_row("PASS"), _row("PASS"), _row("FAIL"), _row("FAIL")])[3] is None


def test_halt_when_every_row_made_zero_tool_calls():
    out = _halt([_row("PASS", 0)] * 3 + [_row("FAIL", 0)] * 0 + [_row("PASS", 0)])
    assert out[3] == "0 tool calls on all 4 rows"


def test_halt_on_a_harness_error_row_once_the_kind_has_n_rows():
    rows = [_row(), _row("HARNESS_ERROR"), _row(), _row()]
    assert _halt(rows)[3] == "HARNESS_ERROR row"


def test_halt_on_a_hop_limit_row():
    rows = [_row(), _row("BUDGET_EXHAUSTED", hop=True), _row(), _row()]
    assert _halt(rows)[3] == "hop-limit row"


def test_kinds_and_arms_are_counted_apart():
    campaign._KIND_ROWS.clear()
    for _ in range(3):
        assert campaign.kind_halt_reason("a", "k1", _row("FAIL")) is None
        assert campaign.kind_halt_reason("b", "k1", _row("FAIL")) is None
        assert campaign.kind_halt_reason("a", "k2", _row("FAIL")) is None


def test_halt_is_written_to_the_exit_log_and_exits_9(tmp_path, monkeypatch):
    log = tmp_path / "x" / "arm_exits.log"
    monkeypatch.setenv("WFE_EXIT_LOG", str(log))
    campaign.log_halt(tmp_path, "armA", "doc-read", "pass rate 0/4 <= 1/4")
    assert log.read_text() == "HALT armA doc-read pass rate 0/4 <= 1/4\n"
    monkeypatch.delenv("WFE_EXIT_LOG")
    campaign.log_halt(tmp_path, "armA", "k", "r")
    assert (tmp_path / "arm_exits.log").read_text() == "HALT armA k r\n"
    assert campaign.EXIT_HALT == 9
    assert campaign.exit_status([{"halted": "k: r", "stopped": "s"}], ["a"]) == 9
    assert campaign.exit_status([{"stopped": "s"}], ["a"]) == campaign.EXIT_STOPPED


def test_supervisor_gives_the_child_the_exit_log_path(tmp_path):
    pid, log = tmp_path / "pids", tmp_path / "exits.log"
    pid.write_text("")
    code = "import os,sys; sys.exit(0 if os.environ['WFE_EXIT_LOG']==sys.argv[1] else 1)"
    assert run_arm.supervise([sys.executable, "-c", code, str(log)], pid, log, "a") == 0


def _halting_arm(tmp_path, monkeypatch, halt):
    """execute_arm over four failing doc-read rows, with every live call faked."""
    d = tmp_path / "c"
    ids = [f"doc-read-0{i}" for i in range(4)]
    stubs = [{"run_id": i, "workspace": "w", "suite_path": "s", "task_id": i} for i in ids]
    monkeypatch.setattr(campaign, "load_manifest", lambda _d: {"rows": stubs})
    monkeypatch.setattr(campaign, "save_manifest", lambda *_: None)
    monkeypatch.setattr(campaign, "_rows_to_run", lambda *a: (list(stubs), None))
    monkeypatch.setattr(campaign, "row_model", lambda r: "m")
    monkeypatch.setattr(campaign, "seat_primary", lambda *a: "m")
    monkeypatch.setattr(campaign, "drain_others", lambda *a: [])
    monkeypatch.setattr(campaign, "drain_model", lambda m: True)
    monkeypatch.setattr(campaign, "workspace_context", lambda *a: {})
    monkeypatch.setattr(campaign, "load_suite", lambda p: [{"id": i} for i in ids])
    monkeypatch.setattr(campaign, "arm_stop_reason", lambda *a, **k: None)
    monkeypatch.setattr(campaign, "ENGINE", "ollama")
    ran = []

    def fake_row(_d, _m, r, *a, **k):
        ran.append(r["run_id"])
        return {"outcome": "FAIL", "turns": 1, "tool_calls": 1, "tool_errors": 0, "economics": {}}

    monkeypatch.setattr(campaign, "run_row", fake_row)
    campaign._KIND_ROWS.clear()
    monkeypatch.delenv("WFE_EXIT_LOG", raising=False)
    out = campaign.execute_arm(d, "a", 4, 60, None, False, False, halt=halt)
    return out, ran, d


def test_execute_arm_halts_on_a_failing_kind_and_no_halt_overrides(tmp_path, monkeypatch):
    out, ran, d = _halting_arm(tmp_path, monkeypatch, True)
    assert out["halted"] == "doc-read: pass rate 0/4 <= 1/4" and len(ran) == 4
    assert (d / "arm_exits.log").read_text() == "HALT a doc-read pass rate 0/4 <= 1/4\n"
    out, _, d = _halting_arm(tmp_path / "n", monkeypatch, False)
    assert out["halted"] is None and not (d / "arm_exits.log").exists()


def test_the_cli_exits_9_on_a_halted_arm_and_accepts_no_halt(tmp_path, monkeypatch):
    plan = _cli_env(tmp_path, monkeypatch, [ROW])
    seen = []
    monkeypatch.setattr(
        campaign, "execute_arm", lambda *a, **k: seen.append(a[-1]) or {"halted": "k: r"}
    )
    for extra, want_halt_arg in (([], True), (["--no-halt"], False)):
        monkeypatch.setattr(
            sys, "argv", ["campaign", "--plan", str(plan), "--campaign-id", "c", *extra]
        )
        assert campaign.main() == campaign.EXIT_HALT
        assert seen[-1] is want_halt_arg


def _served(temp):
    return [{"served": {"options": {"temperature": temp}}}] if temp is not None else [{}]


def test_served_temperature_comes_from_the_applied_options():
    assert campaign.served_temperature(_served(0.0)) == 0.0
    assert campaign.served_temperature(_served(0.6)) == 0.6
    assert campaign.served_temperature(_served(None)) is None


def _screen_rows(tmp_path, arm, temps):
    (tmp_path / "rows").mkdir(exist_ok=True)
    for i, t in enumerate(temps):
        (tmp_path / "rows" / f"{arm}{i}.json").write_text(
            json.dumps({"arm": arm, "served_temperature": t})
        )


def test_repeats_policy_is_one_only_when_every_arm_in_the_cell_served_zero(tmp_path):
    _screen_rows(tmp_path, "cold", [0.0, 0.0])
    _screen_rows(tmp_path, "cold2", [0.0])
    _screen_rows(tmp_path, "warm", [0.6, 0.6])
    _screen_rows(tmp_path, "mixed", [0.0, 0.3])
    _screen_rows(tmp_path, "unknown", [None])

    def m(ws, *arms):
        return [{"workspace": ws, "arm": a} for a in arms]

    matrix = (
        m("allzero", "cold", "cold2")
        + m("mixedcell", "cold", "warm")
        + m("rowmix", "cold", "mixed")
        + m("unrecorded", "cold", "unknown", "new")
    )
    assert campaign.repeats_policy(tmp_path, m("allzero", "cold", "cold2"), 3) == {
        "cold": 1,
        "cold2": 1,
    }
    assert campaign.repeats_policy(tmp_path, m("mixedcell", "cold", "warm"), 3) == {
        "cold": 3,
        "warm": 3,
    }
    assert set(campaign.repeats_policy(tmp_path, m("rowmix", "cold", "mixed"), 3).values()) == {3}
    assert set(campaign.repeats_policy(tmp_path, matrix[-3:], 3).values()) == {3}
    # an arm shared by a 1-repeat and a 3-repeat workspace keeps the larger count
    assert campaign.repeats_policy(tmp_path, matrix, 3)["cold"] == 3


def test_expand_matrix_applies_repeats_per_arm(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "SUITE_DIR", tmp_path)
    monkeypatch.setattr(campaign, "_with_card_sampling", lambda entry, role, ws: entry)
    (tmp_path / "s.jsonl").write_text(json.dumps({"id": "t-1", "screen": True}) + "\n")
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "workloads:\n  w:\n    home: s\n    arms:\n      incumbent: cold\n"
        "      challengers: [warm]\n"
    )
    rows = campaign.expand_matrix(plan, {"cold": 1, "warm": 3}, tier="confirm")
    assert sorted((r["arm"], r["repeat"]) for r in rows) == [
        ("cold", 0),
        ("warm", 0),
        ("warm", 1),
        ("warm", 2),
    ]
    assert len(campaign.expand_matrix(plan, 2, tier="confirm")) == 4


def test_the_draws_recorded_per_arm_reach_the_fitness_cells():
    from tests.wfe import report

    rows = [
        {"repeat": 0, "served_temperature": 0.0},
        {"repeat": 0, "served_temperature": 0.0},
    ]
    assert report._draws(rows) == {"repeats": 1, "served_temperature": [0.0]}
    assert report._draws([{"repeat": r} for r in range(3)]) == {
        "repeats": 3,
        "served_temperature": [],
    }


def test_every_production_suite_has_at_least_halt_after_rows_tasks_per_kind():
    """The auto-halt judges a kind after HALT_AFTER_ROWS rows; a smaller kind could never halt."""
    import collections

    # the generated decision suites; rig_production is a 4-task rig with one task per kind
    suites = [
        p
        for p in sorted(campaign.SUITE_DIR.glob("*_production.jsonl"))
        if (campaign.SUITE_DIR / f"build_{p.stem}.py").exists()
    ]
    assert len(suites) >= 3
    for path in suites:
        kinds = collections.Counter(campaign.task_kind(t) for t in campaign.load_suite(path))
        small = {k: n for k, n in kinds.items() if n < campaign.HALT_AFTER_ROWS}
        assert not small, f"{path.name}: kinds under {campaign.HALT_AFTER_ROWS} tasks: {small}"


def test_the_production_suite_generators_are_reproducible():
    """Regenerating in place twice leaves the committed file byte-identical."""
    from tests.wfe.suites import build_compliance_production as comp
    from tests.wfe.suites import build_data_production as data

    for mod in (comp, data):
        committed = mod.OUT.read_text()
        try:
            for _ in range(2):
                mod.main()
                assert mod.OUT.read_text() == committed
        finally:
            mod.OUT.write_text(committed)
