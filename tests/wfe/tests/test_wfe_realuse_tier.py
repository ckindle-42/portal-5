"""--tier realuse: every task once, a second draw only where the arm can differ."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import yaml

from tests.wfe import campaign as camp

WS = "auto-general"
INC = "inc:tag"


def _suite(path, n=6, screen=2, checker=None):
    checker = checker or {"type": "answer_contains", "patterns": ["done"]}
    path.write_text(
        "".join(
            json.dumps(
                {
                    "id": f"t{i:02d}",
                    "instruction": "do it",
                    "checkers": [checker],
                    **({"screen": True} if i < screen else {}),
                }
            )
            + "\n"
            for i in range(n)
        )
    )


@pytest.fixture
def plan(tmp_path, monkeypatch):
    suites = tmp_path / "suites"
    suites.mkdir()
    _suite(suites / "home.jsonl")
    monkeypatch.setattr(camp, "SUITE_DIR", suites)
    p = tmp_path / "plan.yaml"
    p.write_text(
        yaml.safe_dump(
            {"workloads": {WS: {"home": "home", "discovery": [], "arms": {"incumbent": INC}}}}
        )
    )
    return p


def _matrix(plan, repeats=1):
    return camp.expand_matrix(plan, repeats, tier="realuse")


class TestExpansion:
    def test_every_task_runs_once_and_the_screen_flag_is_ignored(self, plan):
        rows = _matrix(plan)
        assert {r["tier"] for r in rows} == {"realuse"}
        assert {r["task_id"] for r in rows} == {f"t{i:02d}" for i in range(6)}
        assert {r["repeat"] for r in rows} == {0}
        assert len(rows) == 6

    def test_the_run_id_does_not_move_between_tiers(self, plan):
        realuse = _matrix(plan)
        confirm = camp.expand_matrix(plan, 1, tier="confirm")
        assert {r["run_id"] for r in realuse} <= {r["run_id"] for r in confirm}

    def test_an_explicit_repeat_count_still_wins(self, plan):
        rows = _matrix(plan, repeats=2)
        assert {r["repeat"] for r in rows} == {0, 1}
        assert len(rows) == 12


class TestRepeatsPolicy:
    def _rows(self, d, arm, temps):
        (d / "rows").mkdir(parents=True, exist_ok=True)
        for i, t in enumerate(temps):
            (d / "rows" / f"{arm}{i}.json").write_text(
                json.dumps({"arm": arm, "served_temperature": t})
            )

    def _m(self, ws=WS, suite="home"):
        return [{"workspace": ws, "arm": INC, "suite": suite, "suite_path": f"/x/{suite}.jsonl"}]

    def test_a_warm_arm_on_an_objective_suite_gets_two_draws(self, plan, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
        self._rows(tmp_path, INC, [0.7, 0.7])
        assert camp.realuse_repeats(tmp_path, self._m()) == {INC: 2}

    def test_a_cold_arm_gets_one_draw(self, plan, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
        self._rows(tmp_path, INC, [0.0, 0.0])
        assert camp.realuse_repeats(tmp_path, self._m()) == {INC: 1}

    def test_a_mixed_recorded_temperature_gets_two_draws(self, plan, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
        self._rows(tmp_path, INC, [0.0, 0.7])
        assert camp.realuse_repeats(tmp_path, self._m()) == {INC: 2}

    def test_an_unrecorded_temperature_is_never_assumed_deterministic(
        self, plan, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
        monkeypatch.setattr(
            camp, "workspace_context", lambda *a, **k: {"declared_temperature": None}
        )
        assert camp.realuse_repeats(tmp_path, self._m()) == {INC: 2}

    def test_the_workspace_declared_temperature_decides_before_a_row_exists(
        self, plan, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
        monkeypatch.setattr(
            camp, "workspace_context", lambda *a, **k: {"declared_temperature": 0.0}
        )
        assert camp.realuse_repeats(tmp_path, self._m()) == {INC: 1}

    def test_an_arm_override_temperature_wins_over_the_workspace(self, plan, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
        monkeypatch.setattr(
            camp, "workspace_context", lambda *a, **k: {"declared_temperature": 0.0}
        )
        rows = [{**self._m()[0], "overrides": {"sampling": {"temperature": 0.8}}}]
        assert camp.realuse_repeats(tmp_path, rows) == {INC: 2}

    def test_a_non_objective_suite_never_gets_a_second_draw(self, plan, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: False)
        self._rows(tmp_path, INC, [0.9])
        assert camp.realuse_repeats(tmp_path, self._m()) == {INC: 1}

    def test_a_human_review_suite_is_not_objective(self, tmp_path):
        path = tmp_path / "creative.jsonl"
        _suite(path, n=2, checker={"type": "human_review", "rubric": ["good"]})
        assert camp.suite_is_objective(path) is False

    def test_an_objective_suite_is_objective(self, tmp_path):
        path = tmp_path / "home.jsonl"
        _suite(path)
        assert camp.suite_is_objective(path) is True


def test_a_task_naming_another_workspace_is_not_run_here(tmp_path, monkeypatch):
    suites = tmp_path / "suites"
    suites.mkdir()
    (suites / "home.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "id": tid,
                    "workspace": ws,
                    "instruction": "do it",
                    "checkers": [{"type": "answer_contains", "patterns": ["done"]}],
                }
            )
            + "\n"
            for tid, ws in (("a", WS), ("b", "auto-coding"), ("c", "auto-general"))
        )
    )
    monkeypatch.setattr(camp, "SUITE_DIR", suites)
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        yaml.safe_dump(
            {"workloads": {WS: {"home": "home", "discovery": [], "arms": {"incumbent": INC}}}}
        )
    )
    rows = camp.expand_matrix(plan, 1, tier="realuse")
    # `c` names the base workspace, so a variant lane still runs it.
    assert {r["task_id"] for r in rows} == {"a", "c"}
    variant = f"{WS}::fast"
    plan.write_text(
        yaml.safe_dump(
            {"workloads": {variant: {"home": "home", "discovery": [], "arms": {"incumbent": INC}}}}
        )
    )
    rows = camp.expand_matrix(plan, 1, tier="realuse")
    assert {r["task_id"] for r in rows} == {"a", "c"}


def test_home_task_filter_restricts_the_home_suite(plan):
    document = yaml.safe_load(plan.read_text())
    document["workloads"][WS]["home_tasks"] = ["t02"]
    plan.write_text(yaml.safe_dump(document))

    assert {row["task_id"] for row in _matrix(plan)} == {"t02"}


def test_tool_surface_report_names_the_workload_task_and_missing_tools(plan):
    suite = camp.SUITE_DIR / "home.jsonl"
    tasks = [json.loads(line) for line in suite.read_text().splitlines()]
    tasks[2]["requires_tools"] = ["execute_python"]
    suite.write_text("".join(json.dumps(task) + "\n" for task in tasks))

    _checked, failures = camp.realuse_tool_surface_report(plan)

    assert failures == ["workload auto-general task t02 missing tools: ['execute_python']"]


def test_committed_realuse_plans_offer_every_selected_home_task_tool():
    plans = sorted((camp.REPO / "tests/wfe/plans").glob("realuse_*.yaml"))
    assert plans
    failures = [
        f"{plan.name}: {failure}"
        for plan in plans
        for _checked, gaps in [camp.realuse_tool_surface_report(plan)]
        for failure in gaps
    ]
    assert not failures, "\n".join(failures)


def test_the_realuse_tier_is_a_cli_choice(monkeypatch):
    _ap, args = camp._parse_args(["--campaign-id", "c", "--tier", "realuse"])
    assert args.tier == "realuse"


def test_planned_matrix_applies_the_policy(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(camp, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(camp, "suite_is_objective", lambda p, c=None: True)
    d = tmp_path / "campaigns" / "c"
    (d / "rows").mkdir(parents=True)
    (d / "rows" / "x.json").write_text(json.dumps({"arm": INC, "served_temperature": 0.5}))
    args = SimpleNamespace(
        campaign_id="c",
        all_suites=False,
        arm=None,
        suite=None,
        task=None,
        workspace=None,
        tier="realuse",
        advance=None,
        repeats=None,
    )
    repeats, matrix = camp._planned_matrix(plan, args)
    assert repeats == {INC: 2}
    assert len(matrix) == 12


def test_tool_preflight_keeps_stdout_clean_for_list_arms(capsys):
    # wfe_campaign.sh reads `--list-arms` stdout line by line as arm tags.
    camp._realuse_tool_preflight(camp.REPO / "tests" / "wfe" / "plans" / "realuse_v1_s8.yaml")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "tool surface preflight: PASS" in captured.err
