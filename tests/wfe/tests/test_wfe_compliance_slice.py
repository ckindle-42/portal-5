"""The compliance slice's harness pieces: the tool_grounded checker, controls that carry a
tool trace, suite-schema validation (N-24), the planted corpus staged without its answer
keys (N-32), and the production suite itself."""

from __future__ import annotations

import json
from pathlib import Path

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome

SUITE = Path(__file__).resolve().parents[1] / "suites" / "compliance_production.jsonl"
GROUNDED = {
    "type": "tool_grounded",
    "tools": ["nerc_cip_requirement"],
    "evidence": ["35 calendar days"],
}


def _call(name="nerc_cip_requirement", output="every 35 calendar days", error=None):
    return {"name": name, "args": {}, "output": output, "error": error}


def _grade(task, answer, calls=None):
    return apply_checkers(
        task, CheckContext(final_text=answer, task=task, tool_calls=calls)
    ).outcome


def test_tool_grounded_needs_a_successful_call_showing_the_evidence():
    task = {"checkers": [GROUNDED]}
    assert _grade(task, "35 days", [_call()]) == Outcome.PASS
    assert _grade(task, "35 days", []) == Outcome.FAIL  # recalled, not retrieved
    assert _grade(task, "35 days", [_call(output="every 90 days")]) == Outcome.FAIL
    assert (
        _grade(task, "35 days", [_call(name="search_controls")]) == Outcome.FAIL
    )  # not an allowed tool
    assert _grade(task, "35 days", [_call(error="boom")]) == Outcome.FAIL
    assert _grade(task, "35 days", [_call(output="ERROR: not found")]) == Outcome.FAIL


def test_a_control_can_carry_a_trace():
    task = {"id": "t", "checkers": [{"type": "answer_contains", "patterns": ["35"]}, GROUNDED]}
    task["controls"] = {
        "pass": [{"answer": "35 calendar days", "tool_calls": [_call()]}],
        "fail": ["35 calendar days", {"answer": "90 days", "tool_calls": [_call()]}],
    }
    assert controls.check_task(task) == []
    task["controls"]["pass"] = ["35 calendar days"]  # no trace: the gold cannot pass
    assert [f.control for f in controls.check_task(task)] == ["pass[0]"]


def test_the_schema_refuses_tasks_the_harness_cannot_grade():
    base = {
        "id": "t",
        "instruction": "x",
        "checkers": [{"type": "answer_contains", "patterns": ["a"]}],
    }
    assert controls.schema_failures(base) == []
    cases = {
        "no checkers": {**base, "checkers": []},
        "unknown checker type": {
            **base,
            "checkers": [{"type": "answer_contain", "patterns": ["a"]}],
        },
        "missing or empty": {**base, "checkers": [{"type": "answer_contains", "pattern": ["a"]}]},
        "unknown task keys": {**base, "checker": {"type": "answer_contains"}},
    }
    for why, task in cases.items():
        notes = [f.notes for f in controls.schema_failures(task)]
        assert any(why in n for n in notes), (why, notes)
        assert controls.check_task(task), why  # the gate refuses it


def test_every_existing_suite_passes_the_schema():
    suites = sorted((SUITE.parent).glob("*.jsonl"))
    bad = [f for s in suites for f in controls.check_suite(s) if f.control == "schema"]
    assert bad == []


def test_the_production_suite_is_sound():
    tasks = [json.loads(line) for line in SUITE.read_text().splitlines()]
    assert len(tasks) >= 34 and len({t["id"] for t in tasks}) == len(tasks)
    assert sum(t["screen"] for t in tasks) >= 10 and all(t["screen"] for t in tasks[:10])
    assert controls.check_suite(SUITE) == []
    for t in tasks:
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds == ["answer_contains", "tool_grounded"], t["id"]
        if "-det-" in t["id"]:
            assert "expected_coverage" in t["checkers"][0]["forbid_in_tool_output"]


def test_the_planted_corpus_is_staged_without_its_answer_keys(tmp_path):
    from portal.modules.compliance.core import eval_instance

    staged = eval_instance._stage_planted(tmp_path)
    files = sorted(staged.glob("*.md"))
    assert len(files) == len(list(eval_instance.PLANTED.glob("*.md"))) == 12
    for f in files:
        text = f.read_text()
        assert "PLANT" not in text and "expected_coverage" not in text, f.name
        assert text.strip(), f.name


def test_a_planted_answer_key_in_tool_output_is_a_harness_error():
    t = json.loads(SUITE.read_text().splitlines()[0])
    leak = [_call(name="compliance_read", output='<!-- PLANT {"expected_coverage":"FULL"} -->')]
    gold = t["controls"]["pass"][0]["answer"]
    assert _grade(t, gold, leak) == Outcome.HARNESS_ERROR
