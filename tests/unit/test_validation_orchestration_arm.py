"""Orchestration-arm principle checks (HR-HW): PASS on HEAD, FAIL when seeded."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from scripts.validation import orchestration_arm as arm

ROOT = Path(__file__).resolve().parents[2]
CHECKS = (
    arm.check_arm_reading_bites_hold_no_write_tools,
    arm.check_arm_thinking_stays_on,
    arm.check_arm_discipline_suites,
    arm.check_arm_gate_c_threshold,
    arm.check_arm_least_agency,
    arm.check_arm_pull_not_prepack,
)


def _real_config() -> dict[str, Any]:
    raw = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write_config(root: Path, config: dict[str, Any]) -> None:
    path = root / "config" / "orchestration_arm.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _copy_arm_module(root: Path) -> None:
    shutil.copytree(
        ROOT / "portal" / "modules" / "orchestration",
        root / "portal" / "modules" / "orchestration",
    )


def _copy_suites(root: Path, config: dict[str, Any]) -> None:
    for key in ("bite_suite", "planner_suite", "checker_suite"):
        relative = config["disciplines"]["test_fixing"][key]
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def test_all_arm_checks_pass_on_head() -> None:
    for check in CHECKS:
        status, detail, _subs = check()
        assert status == "PASS", f"{check.__name__}: {detail}"


def test_arm_checks_are_registered() -> None:
    from scripts.validation import all_checks

    slugs = {slug for slug, _label, _fn in all_checks()}
    assert {
        "arm_reading_no_write",
        "arm_thinking_on",
        "arm_discipline_suites",
        "arm_gate_c_threshold",
        "arm_least_agency",
        "arm_pull_notes",
    } <= slugs


def test_reading_no_write_fails_when_action_class_overlaps(tmp_path, monkeypatch) -> None:
    config = _real_config()
    config["disciplines"]["test_fixing"]["action_tools"].append("file_read")
    _write_config(tmp_path, config)
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, subs = arm.check_arm_reading_bites_hold_no_write_tools()

    assert status == "FAIL"
    assert "read/action overlap" in detail
    assert any(sub["status"] == "FAIL" for sub in subs)


def test_reading_no_write_fails_when_a_tool_is_unclassified(tmp_path, monkeypatch) -> None:
    config = _real_config()
    config["disciplines"]["test_fixing"]["tool_allowlist"].append("send_message")
    _write_config(tmp_path, config)
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, _subs = arm.check_arm_reading_bites_hold_no_write_tools()

    assert status == "FAIL"
    assert "unclassified tools ['send_message']" in detail


def test_thinking_on_fails_when_a_request_suppresses_thinking(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, _real_config())
    module = tmp_path / "portal" / "modules" / "orchestration"
    module.mkdir(parents=True)
    (module / "bad_request.py").write_text(
        "def body(engine):\n"
        "    return {\n"
        '        "model": engine.tag,\n'
        '        "messages": [],\n'
        '        "chat_template_kwargs": {"enable_thinking": False},\n'
        "    }\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, subs = arm.check_arm_thinking_stays_on()

    assert status == "FAIL"
    assert "enable_thinking=False" in detail
    assert subs[1]["status"] == "FAIL"


def test_thinking_on_fails_on_a_request_body_in_a_subdirectory(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, _real_config())
    helpers = tmp_path / "portal" / "modules" / "orchestration" / "helpers"
    helpers.mkdir(parents=True)
    (helpers / "bad_request.py").write_text(
        "def body(engine):\n"
        "    return {\n"
        '        "model": engine.tag,\n'
        '        "messages": [],\n'
        '        "chat_template_kwargs": {"enable_thinking": False},\n'
        "    }\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, subs = arm.check_arm_thinking_stays_on()

    assert status == "FAIL"
    assert "helpers/bad_request.py: enable_thinking=False" in detail
    assert subs[1]["status"] == "FAIL"


def test_thinking_on_fails_when_arm_config_disables_thinking(tmp_path, monkeypatch) -> None:
    config = _real_config()
    config["disciplines"]["test_fixing"]["thinking"] = "off"
    _write_config(tmp_path, config)
    _copy_arm_module(tmp_path)
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, _subs = arm.check_arm_thinking_stays_on()

    assert status == "FAIL"
    assert "thinking='off'" in detail


def test_discipline_suites_fail_when_planner_suite_is_missing(tmp_path, monkeypatch) -> None:
    config = _real_config()
    _copy_suites(tmp_path, config)
    del config["disciplines"]["test_fixing"]["planner_suite"]
    _write_config(tmp_path, config)
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, _subs = arm.check_arm_discipline_suites()

    assert status == "FAIL"
    assert "planner_suite missing" in detail


def test_discipline_suites_fail_when_pass_criteria_are_empty(tmp_path, monkeypatch) -> None:
    config = _real_config()
    _copy_suites(tmp_path, config)
    config["disciplines"]["test_fixing"]["pass_criteria"] = {}
    _write_config(tmp_path, config)
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, _subs = arm.check_arm_discipline_suites()

    assert status == "FAIL"
    assert "pass_criteria missing or empty" in detail


def test_gate_c_threshold_fails_on_a_non_probability(tmp_path, monkeypatch) -> None:
    config = _real_config()
    config["calibration"]["minimum_pass_probability"] = "high"
    _write_config(tmp_path, config)
    monkeypatch.setattr(arm, "REPO_ROOT", tmp_path)

    status, detail, _subs = arm.check_arm_gate_c_threshold()

    assert status == "FAIL"
    assert "minimum_pass_probability='high'" in detail


def test_gate_c_threshold_fails_when_unattended_is_not_refused(monkeypatch) -> None:
    from portal.modules.orchestration import service

    monkeypatch.setattr(service, "_require_calibration", lambda *_a, **_k: None)

    status, detail, _subs = arm.check_arm_gate_c_threshold()

    assert status == "FAIL"
    assert "did not refuse unattended" in detail


def test_least_agency_fails_when_the_request_widens_the_tool_set(monkeypatch) -> None:
    from portal.modules.orchestration import worker

    real = worker._request_body

    def widened(bite, engine, messages):
        body = real(bite, engine, messages)
        body["portal_bite_tools"] = [*body["portal_bite_tools"], "file_write"]
        return body

    monkeypatch.setattr(worker, "_request_body", widened)

    status, detail, subs = arm.check_arm_least_agency()

    assert status == "FAIL"
    assert "per-bite tool mounting is not enforced" in detail
    assert subs[0]["status"] == "FAIL"


def test_least_agency_checks_every_allowlisted_tool(monkeypatch) -> None:
    from portal.modules.orchestration import worker

    real = worker._request_body
    allowed = _real_config()["disciplines"]["test_fixing"]["tool_allowlist"]
    assert len(allowed) > 1
    delayed = allowed[-1]

    def drops_a_later_tool(bite, engine, messages):
        body = real(bite, engine, messages)
        if delayed in bite.tools:
            body["portal_bite_tools"] = [
                tool for tool in body["portal_bite_tools"] if tool != delayed
            ]
        return body

    monkeypatch.setattr(worker, "_request_body", drops_a_later_tool)

    status, _detail, subs = arm.check_arm_least_agency()

    assert status == "FAIL"
    assert subs[0]["status"] == "FAIL"
    assert f"{delayed}: mounted=" in subs[0]["detail"]


def test_pull_notes_fail_when_input_contents_are_pre_packed(monkeypatch) -> None:
    from portal.modules.orchestration import worker

    def prepacked(bite, input_paths):
        path = next(iter(input_paths.values()))
        return [{"role": "system", "content": path.read_text(encoding="utf-8")}]

    monkeypatch.setattr(worker, "_messages", prepacked)

    status, detail, subs = arm.check_arm_pull_not_prepack()

    assert status == "FAIL"
    assert "pull-don't-pre-pack" in detail
    assert subs[0]["status"] == "FAIL"


def test_pull_notes_fail_when_the_procedure_is_missing(monkeypatch) -> None:
    from portal.modules.orchestration import worker

    def no_procedure(bite, input_paths):
        return [{"role": "system", "content": "x"}]

    monkeypatch.setattr(worker, "_messages", no_procedure)

    status, detail, _subs = arm.check_arm_pull_not_prepack()

    assert status == "FAIL"
    assert "procedure-in-context" in detail


def test_seeded_plan_fixture_still_matches_the_real_validator() -> None:
    """Keep the check's plan fixture honest against the real validator."""
    from portal.modules.orchestration.planner import validate_planned_plan

    validate_planned_plan(
        arm._seeded_plan("test_fixing", ["file_read"]), _real_config(), "test_fixing"
    )
