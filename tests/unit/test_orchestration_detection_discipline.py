"""Offline contract tests for the detection-engineering discipline and WFE suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from portal.modules.orchestration.disciplines.detection_engineering import CHECKERS, run_checker

ROOT = Path(__file__).resolve().parents[2]
DISCIPLINE_ROOT = ROOT / "portal/modules/orchestration/disciplines/detection_engineering"


def _yaml(name: str) -> dict[str, Any]:
    value = yaml.safe_load((DISCIPLINE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _manifest_names(path: Path) -> set[str]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {str(item.get("name") or (item.get("function") or {}).get("name")) for item in manifest}


def test_discipline_binds_existing_persona_seats_tools_and_fixed_criteria() -> None:
    discipline = _yaml("discipline.yaml")
    assert discipline["persona"]["slug"] == "splunkdetectionauthor"
    assert (ROOT / discipline["persona"]["source"]).is_file()
    assert discipline["seats"]["fast"]["workspace"] == "auto-daily::fast"
    assert discipline["seats"]["deep"]["workspace"] == "auto-daily::deep"
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
    controls = suite["controls"]
    assert {control["checker"]["type"] for control in controls} == set(CHECKERS)
    for control in controls:
        checker = control["checker"]
        good = control["pass"]
        bad = control["fail"]
        good_result = run_checker(checker, good["artifact"], good["calls"])
        bad_result = run_checker(checker, bad["artifact"], bad["calls"])
        assert good_result.passed, f"{checker['type']}: {good_result.detail}"
        assert not bad_result.passed, checker["type"]


def test_unknown_checker_cannot_fail_open() -> None:
    result = run_checker({"type": "looks_plausible"}, {}, [])
    assert not result.passed
    assert "unknown" in result.detail
