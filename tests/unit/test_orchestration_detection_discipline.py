"""Offline contract tests for the detection-engineering discipline and WFE suite."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from portal.modules.orchestration.disciplines.detection_engineering import CHECKERS, run_checker
from portal.modules.orchestration.planner import instantiate_plan_template, validate_planned_plan

ROOT = Path(__file__).resolve().parents[2]
DISCIPLINE_ROOT = ROOT / "portal/modules/orchestration/disciplines/detection_engineering"


def _yaml(name: str) -> dict[str, Any]:
    value = yaml.safe_load((DISCIPLINE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _manifest_names(path: Path) -> set[str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {str(item.get("name") or (item.get("function") or {}).get("name")) for item in manifest}


def _arm_config() -> dict[str, Any]:
    value = yaml.safe_load((ROOT / "config/orchestration_arm.yaml").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _template_plan(tmp_path: Path) -> dict[str, Any]:
    reference = tmp_path / "reference.spl"
    reference.write_text("index=portal5_lab EventCode=4769\n", encoding="utf-8")
    return instantiate_plan_template(
        _arm_config(),
        template_key="author_and_validate_detection",
        discipline_key="detection-engineering",
        task_id="detection-plan-contract",
        parameters={
            "reference_file": reference.name,
            "technique": "T1110.001",
            "expected_behavior": "finds repeated authentication failures",
        },
        source_dir=tmp_path,
    ).as_dict()


def test_discipline_is_unseated_and_retains_fixed_criteria() -> None:
    discipline = _yaml("discipline.yaml")
    assert discipline["persona"]["slug"] == "splunkdetectionauthor"
    assert (ROOT / discipline["persona"]["source"]).is_file()
    assert discipline["seating"]["status"] == "unseated"
    assert "seats" not in discipline
    assert discipline["data_class"] == "local-only"
    assert discipline["write_scope"] == {
        "root": "task_directory",
        "allow": ["**/*"],
        "deny_outside_root": True,
    }
    manifests = {
        "detection": ROOT / "config/inference/tools_manifest_detection_mcp.json",
        "detections": ROOT / "config/security/tools_manifest_detections_mcp.json",
        "mitre": ROOT / "config/security/tools_manifest_mitre_mcp.json",
    }
    for source, allowed in discipline["tool_allowlist"].items():
        assert set(allowed) <= _manifest_names(manifests[source])
    criteria = discipline["pass_criteria"]
    assert criteria["frozen_before_first_run"] is True
    assert criteria["checker_controls"] == {"false_passes": 0, "false_failures": 0}
    assert criteria["live_lab"]["required_cases_must_run"] is True
    arm_discipline = _arm_config()["disciplines"]["detection-engineering"]
    assert arm_discipline["seating_status"] == "unseated"
    assert "seated_models" not in arm_discipline
    assert "detection-engineering" not in _arm_config()["calibration"]["rates_by_discipline"]


def test_bite_suite_declares_each_hard_checker_and_live_lab_boundary() -> None:
    discipline = _yaml("discipline.yaml")
    suite = _yaml(discipline["wfe"]["bite_suite"])
    cases = suite["cases"]
    assert {case["checker"]["type"] for case in cases} == set(CHECKERS)
    allowed = {tool for tools in discipline["tool_allowlist"].values() for tool in tools}
    for case in cases:
        assert set(case["tools"]) <= allowed
        is_lab_checker = case["checker"]["type"] == "lab_spl_results"
        assert case["requires_live_lab"] is is_lab_checker
        if is_lab_checker:
            assert case["checker"]["requires_live_lab"] is True
            assert case["checker"]["expected_rows"]


def test_every_checker_accepts_known_good_and_rejects_known_bad() -> None:
    discipline = _yaml("discipline.yaml")
    suite = _yaml(discipline["wfe"]["checker_suite"])
    controls_suite = _yaml(discipline["wfe"]["checker_controls"])
    controls = {control["id"]: control for control in controls_suite["controls"]}
    assert {case["checker"] for case in suite["cases"]} == set(CHECKERS)
    assert {case["control_id"] for case in suite["cases"]} == set(controls)
    assert suite["controls_file"] == (
        "portal/modules/orchestration/disciplines/detection_engineering/wfe_checker_controls.yaml"
    )
    for control in controls:
        definition = controls[control]
        checker = definition["checker"]
        good = definition["pass"]
        bad = definition["fail"]
        good_result = run_checker(checker, good["artifact"], good["calls"])
        bad_result = run_checker(checker, bad["artifact"], bad["calls"])
        assert good_result.passed, f"{checker['type']}: {good_result.detail}"
        assert not bad_result.passed, checker["type"]


def test_detection_planner_suite_is_backed_by_the_arm_validator(tmp_path: Path) -> None:
    discipline = _yaml("discipline.yaml")
    suite = _yaml(discipline["wfe"]["planner_suite"])
    base = _template_plan(tmp_path)
    mutations = {
        "mixed-read-action": lambda plan: plan["bites"][1].update(
            tools=["file_read", "file_write"]
        ),
        "untrusted-read-action": lambda plan: plan["bites"][0].update(
            tools=["file_read", "file_write"]
        ),
        "context-budget": lambda plan: plan["bites"][0]["budget"].update(context_tokens=16385),
        "plan-closure": lambda plan: plan["bites"][-2].update(stage="work"),
    }
    config = _arm_config()
    for case in suite["cases"]:
        candidate = copy.deepcopy(base)
        mutation = mutations.get(case["rule"])
        if mutation:
            mutation(candidate)
        if case["expected"] == "pass":
            validate_planned_plan(candidate, config, "detection-engineering", tmp_path)
        else:
            with pytest.raises(ValueError):
                validate_planned_plan(candidate, config, "detection-engineering", tmp_path)


def test_unknown_checker_cannot_fail_open() -> None:
    result = run_checker({"type": "looks_plausible"}, {}, [])
    assert not result.passed
    assert "unknown" in result.detail
