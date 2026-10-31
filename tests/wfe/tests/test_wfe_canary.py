"""Canary gate: SETUP/MODEL classification, row selection, and the offline run.

Fake rows only — the canary's live path is exercised by the job that gates on it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.wfe import campaign as camp
from tests.wfe.canary import MODEL, SETUP, canary_campaign_id, classify_row, run_canary, select_rows


def _row(**kw):
    base: dict = {
        "outcome": "PASS",
        "notes": "answer contains 'done'",
        "turns": 3,
        "economics": {"wall_s": 12.0},
        "tool_call_log": [],
    }
    base.update(kw)
    return base


class TestClassification:
    def test_model_quality_outcomes_are_model(self):
        for outcome in ("PASS", "FAIL", "REFUSED", "TRUNCATED", "BUDGET_EXHAUSTED", "TOOL_ERROR"):
            assert classify_row(_row(outcome=outcome)) == MODEL

    def test_a_blocked_row_that_reached_the_model_is_model(self):
        row = _row(outcome="BLOCKED", notes="not seat evidence: pipeline served x", turns=4)
        assert classify_row(row) == MODEL

    def test_zero_second_blocked_is_setup(self):
        assert classify_row(_row(outcome="BLOCKED", turns=0, economics={"wall_s": None})) == SETUP

    def test_a_blocked_stub_without_a_row_file_is_setup(self):
        assert classify_row({"state": "BLOCKED", "note": "pipeline refused"}) == SETUP

    def test_a_missing_tool_note_is_setup(self):
        row = _row(
            outcome="BLOCKED", notes="requires tools the harness does not offer: ['run_sql']"
        )
        assert classify_row(row) == SETUP

    @pytest.mark.parametrize("note", ["fixture file not found: x.csv", "data: FILE NOT FOUND"])
    def test_a_file_not_found_note_is_setup(self, note):
        assert classify_row(_row(notes=note)) == SETUP

    def test_enoent_in_a_tool_output_is_setup(self):
        row = _row(
            tool_call_log=[{"output": "read failed: [Errno 2] ENOENT: no such file or directory"}]
        )
        assert classify_row(row) == SETUP

    @pytest.mark.parametrize(
        "output",
        [
            '{"stderr": "docker: Error response from daemon: failed to create task for container:'
            ' failed to create shim task: OCI runtime create failed"}',
            '{"error_type": "docker_unavailable"}',
            "Tool 'read_pdf' returned an MCP tool error",
        ],
    )
    def test_a_tool_that_could_not_run_is_setup(self, output):
        # realuse autocoding canary 10-30: seven sandbox OCI failures were classed MODEL.
        assert classify_row(_row(outcome="REFUSED", tool_call_log=[{"output": output}])) == SETUP

    def test_a_scope_refusal_of_a_prompt_path_is_setup(self):
        path = "/workspace/uploads/final_invoice.pdf"
        row = _row(
            outcome="REFUSED",
            tool_call_log=[{"output": f"path outside the evaluation namespace: {path}"}],
            turn_results=[{"turn": 1, "user": f"Read the invoice at {path} and total it."}],
        )
        assert classify_row(row) == SETUP

    def test_a_scope_refusal_of_a_model_invented_path_is_model(self):
        # rest-8: the prompt names the staged path; '/final_invoice.pdf' is the model's.
        row = _row(
            outcome="REFUSED",
            tool_call_log=[
                {"output": "ScopeError: path outside the evaluation namespace: /final_invoice.pdf"}
            ],
            turn_results=[
                {"turn": 1, "user": "Read /workspace/uploads/final_invoice.pdf and total it."}
            ],
        )
        assert classify_row(row) == MODEL

    def test_a_reused_row_is_setup(self):
        assert classify_row(_row(reused_from="earlier/row")) == SETUP

    @pytest.mark.parametrize("mark", ["rescore", "original_outcome", "regraded_outcome"])
    def test_a_regraded_row_is_setup(self, mark):
        assert classify_row(_row(**{mark: {"outcome": "PASS"}})) == SETUP

    def test_a_preflight_abort_is_setup(self):
        row = _row(outcome="BLOCKED", notes="preflight REVIEW: tag not installed")
        assert classify_row(row) == SETUP

    def test_a_harness_error_is_setup(self):
        assert classify_row(_row(outcome="HARNESS_ERROR")) == SETUP

    @pytest.mark.parametrize("state", ["PENDING", "MISSING", "SKIPPED_DECIDED", "NO_ROW"])
    def test_a_row_that_never_ran_is_setup(self, state):
        assert classify_row({"state": state}) == SETUP

    def test_first_note_is_the_first_line_collapsed(self):
        from tests.wfe.canary import _first_note

        note = _first_note(_row(notes="one  two\nthree\nfour", outcome="X"))
        assert note == "one two"


class TestSelection:
    @pytest.fixture
    def suites(self, tmp_path, monkeypatch):
        dir_ = tmp_path / "suites"
        dir_.mkdir()

        def write(name, tasks):
            (dir_ / f"{name}.jsonl").write_text("".join(json.dumps(t) + "\n" for t in tasks))

        write(
            "home",
            [
                {"id": "t00", "instruction": "x", "checkers": []},
                {"id": "t01", "instruction": "x", "checkers": [], "requires_tools": ["run_sql"]},
                {
                    "id": "t02",
                    "instruction": "x",
                    "checkers": [],
                    "requires_tools": ["run_sql"],
                    "fixtures": ["tests/fixtures/realuse_v1/case1/input.csv"],
                },
            ],
        )
        write(
            "home2",
            [
                {"id": "p00", "instruction": "x", "checkers": []},
                {"id": "p01", "instruction": "x", "checkers": []},
            ],
        )
        # Every task declares another workspace, so ws-c has no eligible row.
        write(
            "home3",
            [{"id": "q00", "instruction": "x", "checkers": [], "workspace": "ws-other"}],
        )
        monkeypatch.setattr(camp, "SUITE_DIR", dir_)
        # A challenger lane resolves the lane's think policy; keep it offline.
        monkeypatch.setattr(camp, "workspace_context", lambda *a, **k: {})
        return dir_

    @pytest.fixture
    def plan(self, tmp_path, suites):
        p = tmp_path / "plan.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "workloads": {
                        "auto-general": {
                            "home": "home",
                            "tool_mode": "sandbox",
                            "arms": {"incumbent": "inc-a", "challengers": ["ch-a"]},
                        },
                        "ws-b": {
                            "home": "home2",
                            "tool_mode": "sandbox",
                            "arms": {"incumbent": "inc-b"},
                        },
                        "ws-c": {
                            "home": "home3",
                            "tool_mode": "sandbox",
                            "arms": {"incumbent": "inc-c"},
                        },
                    }
                }
            )
        )
        return p

    def test_one_incumbent_row_per_workload(self, plan):
        rows = select_rows(plan, "confirm")
        assert [r["workspace"] for r in rows] == ["auto-general", "ws-b", "ws-c"]
        assert all(r["arm_role"] == "incumbent" for r in rows)
        assert [r["arm"] for r in rows] == ["inc-a", "inc-b", "inc-c"]

    def test_prefers_a_task_that_exercises_fixtures_and_tools(self, plan):
        rows = select_rows(plan, "confirm")
        by_ws = {r["workspace"]: r for r in rows}
        assert by_ws["auto-general"]["task_id"] == "t02"
        assert by_ws["ws-b"]["task_id"] == "p00"

    def test_a_workload_with_no_eligible_row_gets_a_no_row_stub(self, plan):
        rows = select_rows(plan, "confirm")
        stub = rows[-1]
        assert stub["state"] == "NO_ROW"
        assert stub["task_id"] == "-"
        assert stub["run_id"].startswith("ws-c|inc-c|")

    def test_tier_is_carried(self, plan):
        rows = select_rows(plan, "realuse")
        assert {r["tier"] for r in rows if r["state"] != "NO_ROW"} == {"realuse"}
        assert {r["tier"] for r in rows if r["state"] == "NO_ROW"} == {"canary"}


def _suite(path, n=2):
    path.write_text(
        "".join(
            json.dumps({"id": f"t{i:02d}", "instruction": "x", "checkers": []}) + "\n"
            for i in range(n)
        )
    )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Offline canary inputs: fake suites, a plan, and stubbed live gates."""
    suites = tmp_path / "suites"
    suites.mkdir()
    _suite(suites / "home.jsonl")
    monkeypatch.setattr(camp, "SUITE_DIR", suites)
    monkeypatch.setattr(camp, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
    monkeypatch.setattr(
        camp, "gate_controls", lambda rows, where: {"suites": {}, "tasks": 0, "failures": []}
    )
    monkeypatch.setattr(camp, "gate_execution", lambda cd: None)
    import tests.wfe.canary as canary

    monkeypatch.setattr(canary, "_fixture_failures", lambda selected: [])
    monkeypatch.setattr(canary, "_conformance_findings", lambda arms, spaces: [])
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        yaml.safe_dump(
            {
                "workloads": {
                    "auto-general": {"home": "home", "arms": {"incumbent": "inc-a"}},
                    "ws-b": {"home": "home", "arms": {"incumbent": "inc-b"}},
                }
            }
        )
    )
    return plan, tmp_path


def _fake_execute(outcomes: dict):
    """execute_arm stand-in: writes the mapped row file, marks the stub."""

    def fake(cd, arm, *args, **kwargs):
        assert kwargs.get("fresh_incumbent") is True
        assert kwargs.get("curtail") is False
        manifest = camp.load_manifest(cd)
        ran = 0
        for stub in manifest["rows"]:
            if stub["arm"] != arm or stub.get("state") == "NO_ROW":
                continue
            row = outcomes[stub["run_id"]]
            camp._row_path(cd, stub["run_id"]).write_text(json.dumps(row))
            stub["state"] = row.get("outcome")
            ran += 1
        camp.save_manifest(cd, manifest)
        return {"arm": arm, "ran": ran}

    return fake


def _rows_for(plan, outcomes):
    selected = select_rows(plan, "confirm")
    return {r["run_id"]: outcomes[r["workspace"]] for r in selected}


class TestRunCanary:
    def test_all_model_rows_exit_zero(self, harness, monkeypatch, capsys):
        plan, tmp = harness
        rows = _rows_for(plan, {"auto-general": _row(outcome="PASS"), "ws-b": _row(outcome="FAIL")})
        monkeypatch.setattr(camp, "execute_arm", _fake_execute(rows))
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 0
        out = capsys.readouterr().out
        assert "CANARY c1_canary: PASS (0 setup row(s) of 2)" in out
        assert (tmp / "campaigns" / "c1_canary" / "manifest.json").is_file()
        assert not (tmp / "campaigns" / "c1_canary" / "excluded.json").exists()

    def test_one_setup_row_excludes_that_workspace_and_exits_zero(
        self, harness, monkeypatch, capsys
    ):
        plan, tmp = harness
        rows = _rows_for(
            plan,
            {
                "auto-general": _row(outcome="HARNESS_ERROR", notes="runner raised: TypeError: x"),
                "ws-b": _row(outcome="PASS"),
            },
        )
        monkeypatch.setattr(camp, "execute_arm", _fake_execute(rows))
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 0
        out = capsys.readouterr().out
        assert "CANARY c1_canary: PASS (1 setup row(s) excluded of 2)" in out
        assert "EXCLUDED auto-general:" in out
        assert "HARNESS_ERROR" in out and "SETUP" in out and "MODEL" in out
        excluded = json.loads((tmp / "campaigns" / "c1_canary" / "excluded.json").read_text())
        assert excluded == [{"workspace": "auto-general", "reason": "runner raised: TypeError: x"}]

    def test_a_zero_second_block_excludes_that_workspace(self, harness, monkeypatch):
        plan, tmp = harness
        rows = _rows_for(
            plan,
            {
                "auto-general": _row(outcome="BLOCKED", turns=0, economics={"wall_s": None}),
                "ws-b": _row(outcome="PASS"),
            },
        )
        monkeypatch.setattr(camp, "execute_arm", _fake_execute(rows))
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 0
        excluded = json.loads((tmp / "campaigns" / "c1_canary" / "excluded.json").read_text())
        assert [item["workspace"] for item in excluded] == ["auto-general"]

    def test_an_unreachable_engine_aborts_before_anything_is_written(
        self, harness, monkeypatch, capsys
    ):
        plan, tmp = harness
        monkeypatch.setattr(camp, "ollama_reachable", lambda: False)
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 1
        assert "chat engine unreachable" in capsys.readouterr().out
        assert not (tmp / "campaigns").exists()

    def test_a_gate_refusal_is_setup(self, harness, monkeypatch, capsys):
        plan, _ = harness
        monkeypatch.setattr(
            camp, "open_campaign", lambda *a, **k: (_ for _ in ()).throw(camp.GateRefused("drift"))
        )
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 1
        assert "gate refused: drift" in capsys.readouterr().out

    def test_a_fixture_failure_aborts(self, harness, monkeypatch, capsys):
        import tests.wfe.canary as canary

        plan, _ = harness
        monkeypatch.setattr(canary, "_fixture_failures", lambda selected: ["unreadable: x.csv"])
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 1
        out = capsys.readouterr().out
        assert "FIXTURES" in out and "unreadable: x.csv" in out

    def test_a_conformance_finding_aborts(self, harness, monkeypatch, capsys):
        import tests.wfe.canary as canary

        plan, _ = harness
        monkeypatch.setattr(
            canary, "_conformance_findings", lambda arms, spaces: ["FAIL ws: tag — dirty stops"]
        )
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 1
        out = capsys.readouterr().out
        assert "CONFORMANCE" in out and "dirty stops" in out

    def test_dry_run_selects_without_running(self, harness, tmp_path, capsys):
        plan, tmp = harness
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan), "--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "auto-general" in out and "dry run" in out
        assert not (tmp / "campaigns").exists()

    def test_a_judge_flag_is_tolerated(self, harness, monkeypatch):
        plan, _ = harness
        rows = _rows_for(plan, {"auto-general": _row(), "ws-b": _row()})
        monkeypatch.setattr(camp, "execute_arm", _fake_execute(rows))
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan), "--judge"]) == 0

    def test_an_unknown_flag_is_rejected(self, harness):
        plan, _ = harness
        with pytest.raises(SystemExit):
            run_canary(["--campaign-id", "c1", "--plan", str(plan), "--frobnicate"])

    def test_a_plan_with_no_workloads_fails(self, harness, tmp_path):
        plan, _ = harness
        empty = tmp_path / "empty.yaml"
        empty.write_text("workloads: {}\n")
        assert run_canary(["--campaign-id", "c1", "--plan", str(empty)]) == 1

    def test_the_canary_suffix_is_idempotent(self):
        assert canary_campaign_id("c1") == "c1_canary"
        assert canary_campaign_id("c1_canary") == "c1_canary"


class TestSetupFaultLedger:
    def test_record_fault_appends_only_the_env_path(self, tmp_path, monkeypatch):
        real = Path.home() / "AI_Output" / "portal-data" / "tests" / "wfe" / "setup_faults.jsonl"
        before = real.read_text() if real.exists() else None
        dest = tmp_path / "ledger" / "setup_faults.jsonl"
        monkeypatch.setenv("WFE_SETUP_FAULTS", str(dest))
        assert (
            run_canary(
                [
                    "--record-fault",
                    "synthetic fault xyz",
                    "--cause",
                    "unit test",
                    "--fix",
                    "abc123",
                    "--campaign",
                    "unit",
                ]
            )
            == 0
        )
        line = json.loads(dest.read_text().splitlines()[0])
        assert line == {
            "signature": "synthetic fault xyz",
            "first_seen": line["first_seen"],
            "campaign": "unit",
            "cause": "unit test",
            "fix_commit": "abc123",
        }
        assert line["first_seen"]
        assert (
            run_canary(
                ["--record-fault", "synthetic fault xyz", "--cause", "again", "--fix", "abc123"]
            )
            == 0
        )
        assert len(dest.read_text().splitlines()) == 1
        after = real.read_text() if real.exists() else None
        assert after == before

    def test_record_fault_requires_cause_and_fix(self):
        with pytest.raises(SystemExit):
            run_canary(["--record-fault", "sig"])

    def test_a_ledger_signature_in_the_reply_is_setup(self, tmp_path, monkeypatch):
        dest = tmp_path / "setup_faults.jsonl"
        monkeypatch.setenv("WFE_SETUP_FAULTS", str(dest))
        row = _row(final_text="request exceeds the available context size (98304 tokens)")
        assert classify_row(row) == MODEL
        dest.write_text(
            json.dumps(
                {
                    "signature": "Exceeds The Available Context Size",
                    "first_seen": "2026-10-30",
                    "campaign": "t",
                    "cause": "http 400",
                    "fix_commit": "abc",
                }
            )
            + "\n"
        )
        assert classify_row(row) == SETUP

    def test_a_ledger_copy_of_a_constant_does_not_widen_it_to_the_reply(
        self, tmp_path, monkeypatch
    ):
        dest = tmp_path / "setup_faults.jsonl"
        monkeypatch.setenv("WFE_SETUP_FAULTS", str(dest))
        dest.write_text(
            json.dumps({"signature": "file not found", "cause": "c", "fix_commit": "x"}) + "\n"
        )
        row = _row(final_text='The script prints "File not found" when the path is missing.')
        assert classify_row(row) == MODEL

    def test_a_pipeline_stream_error_is_not_setup_until_it_is_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WFE_SETUP_FAULTS", str(tmp_path / "missing.jsonl"))
        row = _row(final_text="[Pipeline stream error — the reply ended early]")
        assert classify_row(row) == MODEL


def test_the_main_campaign_skips_a_workspace_the_canary_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(camp, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(
        camp, "gate_controls", lambda rows, where: {"suites": {}, "tasks": 0, "failures": []}
    )
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    canary = tmp_path / "campaigns" / "c1_canary"
    canary.mkdir(parents=True)
    reason = "runner raised: TypeError: x"
    (canary / "excluded.json").write_text(
        json.dumps([{"workspace": "ws-b", "reason": reason}]) + "\n"
    )

    def row(ws, tid):
        return {
            "run_id": f"{ws}|arm|{tid}",
            "workspace": ws,
            "arm": "arm",
            "arm_role": "incumbent",
            "suite": "home",
            "suite_path": "",
            "task_id": tid,
            "repeat": 0,
            "state": "PENDING",
        }

    rows = [row("auto-general", "t0"), row("ws-b", "t1"), row("ws-b", "t2")]
    campaign_dir = camp.open_campaign("c1", plan, rows, append=False)
    manifest = camp.load_manifest(campaign_dir)
    by_ws: dict[str, set[str]] = {}
    for item in manifest["rows"]:
        by_ws.setdefault(item["workspace"], set()).add(item["state"])
        if item["workspace"] == "ws-b":
            assert item["note"] == reason
    assert by_ws == {"auto-general": {"PENDING"}, "ws-b": {"EXCLUDED_SETUP"}}
    problems = camp.completion_problems(campaign_dir)
    assert any("auto-general" in problem for problem in problems)
    assert not any("ws-b" in problem for problem in problems)

    for item in manifest["rows"]:
        if item["workspace"] == "ws-b":
            item["state"] = "PENDING"
            item.pop("note", None)
    camp.save_manifest(campaign_dir, manifest)
    seen: dict[str, list[tuple[str, str]]] = {}

    def fake_todo(cd, live, arm, *args, **kwargs):
        seen["states"] = [(r["workspace"], r["state"]) for r in live["rows"]]
        return [], {"arm": arm, "ran": 0}, []

    monkeypatch.setattr(camp, "_arm_todo", fake_todo)
    assert camp.execute_arm(campaign_dir, "arm", 1, 1, None, False, False)["ran"] == 0
    assert seen["states"] == [
        ("auto-general", "PENDING"),
        ("ws-b", "EXCLUDED_SETUP"),
        ("ws-b", "EXCLUDED_SETUP"),
    ]
    # The canary campaign does not exclude its own rows.
    canary_rows = [row("ws-b", "t1")]
    canary_dir = camp.open_campaign("c1_canary", plan, canary_rows, append=False)
    assert camp.load_manifest(canary_dir)["rows"][0]["state"] == "PENDING"


def test_the_report_lists_excluded_workspaces_and_does_not_score_them(tmp_path):
    from tests.wfe.report import build, render_markdown

    directory = tmp_path / "c1"
    (directory / "rows").mkdir(parents=True)
    (directory / "preflight").mkdir()
    env = {"fingerprint": "abc", "git_sha": "deadbeef", "ollama_version": "0.33"}
    manifest_rows = []
    for workspace, outcome, state in (
        ("auto-general", "PASS", "PASS"),
        ("ws-b", "PASS", "EXCLUDED_SETUP"),
        ("ws-b", "FAIL", "EXCLUDED_SETUP"),
    ):
        run_id = f"{workspace}|inc|coding|{outcome}"
        manifest_rows.append(
            {
                "run_id": run_id,
                "workspace": workspace,
                "arm": "inc",
                "arm_role": "incumbent",
                "suite": "coding",
                "task_id": outcome.lower(),
                "repeat": 0,
                "is_home": True,
                "state": state,
                "note": "fixture missing" if state == "EXCLUDED_SETUP" else "",
            }
        )
        (directory / "rows" / f"{workspace}_{outcome}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "workspace": workspace,
                    "arm": "inc",
                    "suite": "coding",
                    "task_id": outcome.lower(),
                    "repeat": 0,
                    "outcome": outcome,
                    "economics": {"total_tokens": 100, "wall_s": 1.0},
                    "env": env,
                }
            )
        )
    (directory / "manifest.json").write_text(
        json.dumps({"campaign_id": "c1", "env": env, "rows": manifest_rows})
    )
    report = build(directory)
    assert [cell["workspace"] for cell in report["matrix"]] == ["auto-general"]
    assert report["matrix"][0]["n"] == 1 and report["matrix"][0]["passes"] == 1
    assert report["excluded_setup"] == [
        {"workspace": "ws-b", "count": 2, "reason": "fixture missing"}
    ]
    text = render_markdown(report)
    assert "| `ws-b` | 2 | fixture missing |" in text
    assert "2/2" not in text
