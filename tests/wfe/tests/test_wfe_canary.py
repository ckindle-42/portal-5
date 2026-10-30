"""Canary gate: SETUP/MODEL classification, row selection, and the offline run.

Fake rows only — the canary's live path is exercised by the job that gates on it.
"""

from __future__ import annotations

import json

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

    def test_one_setup_row_exits_one(self, harness, monkeypatch, capsys):
        plan, _ = harness
        rows = _rows_for(
            plan,
            {
                "auto-general": _row(outcome="HARNESS_ERROR", notes="runner raised: TypeError: x"),
                "ws-b": _row(outcome="PASS"),
            },
        )
        monkeypatch.setattr(camp, "execute_arm", _fake_execute(rows))
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 1
        out = capsys.readouterr().out
        assert "CANARY c1_canary: SETUP (1 setup row(s) of 2)" in out
        assert "HARNESS_ERROR" in out and "SETUP" in out and "MODEL" in out

    def test_a_zero_second_block_is_caught_end_to_end(self, harness, monkeypatch):
        plan, _ = harness
        rows = _rows_for(
            plan,
            {
                "auto-general": _row(outcome="BLOCKED", turns=0, economics={"wall_s": None}),
                "ws-b": _row(outcome="PASS"),
            },
        )
        monkeypatch.setattr(camp, "execute_arm", _fake_execute(rows))
        assert run_canary(["--campaign-id", "c1", "--plan", str(plan)]) == 1

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
