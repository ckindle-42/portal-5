"""Checker soundness (WFE dimension 20) and gameability (dimension 27).

Every test here corresponds to a way the pre-repair harness returned a PASS it
had not earned. They are regression locks: each one fails against the old
implementation and passes against the repaired one.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.wfe.checkers import (
    CheckContext,
    apply_checkers,
    check_answer_contains,
    check_cited_answer,
    check_file_contains,
    check_file_exists,
    check_hidden_pytest,
    check_immutable,
    detect_refusal,
    parse_pytest_summary,
)
from tests.wfe.schema import Outcome

MIXED = "collected 5 items\n\nF...\n=========== 1 failed, 4 passed in 0.31s ==========="
CLEAN = "collected 4 items\n\n....\n=========== 4 passed in 0.12s ==========="
NONE_RAN = "collected 0 items\n\n=========== no tests ran in 0.01s ==========="
ERRORS = "=========== 2 errors in 0.10s ==========="


class TestPytestSummary:
    def test_mixed_run_is_not_a_pass(self):
        """The original returned True whenever 'passed' appeared anywhere, so
        '1 failed, 4 passed' scored as success."""
        s = parse_pytest_summary(MIXED)
        assert s["passed"] == 4 and s["failed"] == 1

    def test_clean_run(self):
        s = parse_pytest_summary(CLEAN)
        assert s["passed"] == 4 and s["failed"] == 0 and s["errors"] == 0

    def test_no_tests_ran_flagged(self):
        assert parse_pytest_summary(NONE_RAN)["no_tests"] is True

    def test_errors_counted(self):
        assert parse_pytest_summary(ERRORS)["errors"] == 2

    def test_single_line_output_does_not_raise(self):
        """The original indexed split('\\n')[-2] and raised IndexError."""
        assert parse_pytest_summary("boom")["passed"] == 0

    def test_empty_output(self):
        assert parse_pytest_summary("")["passed"] == 0

    def test_internal_error_detected(self):
        assert parse_pytest_summary("INTERNALERROR> boom")["internal_error"] is True


class TestFileCheckersAreSandboxOnly:
    def test_file_exists_does_not_fall_back_to_repo(self, tmp_path):
        """The original resolver fell back to the real repository on a sandbox
        miss, so a checker could be satisfied by a file the model never wrote."""
        ctx = CheckContext(sandbox_root=tmp_path)
        r = check_file_exists({"path": "README.md"}, ctx)
        assert r.outcome == Outcome.FAIL

    def test_file_exists_true_when_written(self, tmp_path):
        (tmp_path / "out.txt").write_text("hello")
        r = check_file_exists({"path": "out.txt"}, CheckContext(sandbox_root=tmp_path))
        assert r.outcome == Outcome.PASS

    def test_empty_file_is_not_a_pass(self, tmp_path):
        (tmp_path / "out.txt").write_text("")
        r = check_file_exists({"path": "out.txt"}, CheckContext(sandbox_root=tmp_path))
        assert r.outcome == Outcome.FAIL

    def test_escape_attempt_is_refused(self, tmp_path):
        r = check_file_exists({"path": "../../etc/hosts"}, CheckContext(sandbox_root=tmp_path))
        assert r.outcome == Outcome.FAIL

    def test_file_contains(self, tmp_path):
        (tmp_path / "m.py").write_text("def summarize(rows):\n    return {}\n")
        ctx = CheckContext(sandbox_root=tmp_path)
        assert (
            check_file_contains({"path": "m.py", "patterns": ["def summarize"]}, ctx).outcome
            == Outcome.PASS
        )
        assert (
            check_file_contains({"path": "m.py", "patterns": ["def missing"]}, ctx).outcome
            == Outcome.FAIL
        )


class TestAnswerProvenance:
    def test_tool_argument_does_not_satisfy_the_checker(self, tmp_path):
        """The original matched final_text + json.dumps(transcript), and
        transcript rows carry tool-call ARGUMENTS — so a model that merely ran
        repo_search('CONTRADICTED') scored the task without deciding anything."""
        ctx = CheckContext(
            final_text="I could not determine this. DETERMINATION COMPLETE",
            tool_calls=[
                {
                    "name": "repo_search",
                    "args": {"pattern": "CONTRADICTED"},
                    "output": "(no matches)",
                }
            ],
            sandbox_root=tmp_path,
        )
        r = check_answer_contains({"patterns": ["CONTRADICTED"]}, ctx)
        assert r.outcome == Outcome.FAIL

    def test_answer_in_final_text_passes(self, tmp_path):
        ctx = CheckContext(
            final_text='{"determination": "CONTRADICTED", "cited_refs": ["CIP-003-8"]}',
            sandbox_root=tmp_path,
        )
        r = check_answer_contains(
            {"patterns": ['"?determination"?\\s*[:=]\\s*"?CONTRADICTED\\b', "cited_refs"]}, ctx
        )
        assert r.outcome == Outcome.PASS

    def test_leaked_answer_key_is_harness_error_not_a_model_result(self, tmp_path):
        """If the gold ever reaches the model through a tool result the task is
        contaminated; it must be quarantined, not scored either way."""
        ctx = CheckContext(
            final_text='{"determination": "CONTRADICTED", "cited_refs": []}',
            tool_calls=[
                {
                    "name": "file_read",
                    "args": {"path": "probe.jsonl"},
                    "output": '{"gold_label": "CONTRADICTED"}',
                }
            ],
            sandbox_root=tmp_path,
        )
        r = check_answer_contains(
            {"patterns": ["CONTRADICTED"], "forbid_in_tool_output": ["gold_label"]}, ctx
        )
        assert r.outcome == Outcome.HARNESS_ERROR


class TestCitationGrounding:
    def test_url_only_in_tool_args_is_not_a_citation(self, tmp_path):
        """The original searched the whole transcript for https?:// — the
        model's own http_get argument satisfied it, as did a failed fetch."""
        ctx = CheckContext(
            final_text="Granite 4.x supports a long context. RESEARCH COMPLETE",
            tool_calls=[
                {
                    "name": "http_get",
                    "args": {"url": "https://ibm.com/granite"},
                    "output": "ERROR: timeout",
                }
            ],
            sandbox_root=tmp_path,
        )
        assert check_cited_answer({"patterns": ["granite"]}, ctx).outcome == Outcome.FAIL

    def test_citation_to_an_unfetched_host_fails(self, tmp_path):
        ctx = CheckContext(
            final_text="See https://example.invalid/granite for details. granite",
            tool_calls=[
                {
                    "name": "http_get",
                    "args": {"url": "https://ibm.com/x"},
                    "output": "IBM Granite docs...",
                }
            ],
            sandbox_root=tmp_path,
        )
        assert check_cited_answer({"patterns": ["granite"]}, ctx).outcome == Outcome.FAIL

    def test_citation_to_a_successfully_fetched_host_passes(self, tmp_path):
        ctx = CheckContext(
            final_text="Granite 4.x documents 128K. Source: https://ibm.com/granite",
            tool_calls=[
                {
                    "name": "http_get",
                    "args": {"url": "https://ibm.com/granite"},
                    "output": "IBM Granite docs...",
                }
            ],
            sandbox_root=tmp_path,
        )
        assert check_cited_answer({"patterns": ["granite"]}, ctx).outcome == Outcome.PASS


class TestRewardHacking:
    def test_model_authored_trivial_tests_do_not_score(self, tmp_path):
        """code-kv previously let the model write both the implementation and
        its own grader. The hidden suite grades the implementation instead."""
        (tmp_path / "parse_kv.py").write_text("def parse_kv(s):\n    return {}\n")
        (tmp_path / "test_parse_kv.py").write_text("def test_ok():\n    assert True\n")
        r = check_hidden_pytest(
            {"graded": "code_kv", "impl_files": ["parse_kv.py"], "min_passed": 7},
            CheckContext(sandbox_root=tmp_path),
        )
        assert r.outcome == Outcome.FAIL

    def test_correct_implementation_passes_the_hidden_suite(self, tmp_path):
        (tmp_path / "parse_kv.py").write_text(
            "def parse_kv(s):\n"
            "    out = {}\n"
            "    if not s or not s.strip():\n"
            "        return out\n"
            "    parts, buf, i = [], '', 0\n"
            "    while i < len(s):\n"
            "        if s[i] == '\\\\' and i + 1 < len(s) and s[i+1] == ';':\n"
            "            buf += ';'; i += 2; continue\n"
            "        if s[i] == ';':\n"
            "            parts.append(buf); buf = ''; i += 1; continue\n"
            "        buf += s[i]; i += 1\n"
            "    parts.append(buf)\n"
            "    for p in parts:\n"
            "        if not p.strip():\n"
            "            continue\n"
            "        k, sep, v = p.partition('=')\n"
            "        out[k.strip()] = v.strip() if sep else ''\n"
            "    return out\n"
        )
        r = check_hidden_pytest(
            {"graded": "code_kv", "impl_files": ["parse_kv.py"], "min_passed": 7},
            CheckContext(sandbox_root=tmp_path),
        )
        assert r.outcome == Outcome.PASS, r.notes

    def test_missing_implementation_is_a_fail_not_an_error(self, tmp_path):
        r = check_hidden_pytest(
            {"graded": "code_kv", "impl_files": ["parse_kv.py"]},
            CheckContext(sandbox_root=tmp_path),
        )
        assert r.outcome == Outcome.FAIL

    def test_rewriting_the_graded_fixture_fails(self, tmp_path):
        body = "def test_x():\n    assert True\n"
        (tmp_path / "test_fizz.py").write_text(body)
        want = hashlib.sha256(b"ORIGINAL").hexdigest()[:16]
        r = check_immutable({"hashes": {"test_fizz.py": want}}, CheckContext(sandbox_root=tmp_path))
        assert r.outcome == Outcome.FAIL and "mutated" in r.notes

    def test_deleting_the_graded_fixture_fails(self, tmp_path):
        r = check_immutable(
            {"hashes": {"test_fizz.py": "deadbeefdeadbeef"}}, CheckContext(sandbox_root=tmp_path)
        )
        assert r.outcome == Outcome.FAIL and "deleted" in r.notes


class TestOutcomeClassification:
    def test_refusal_is_distinguished_from_a_wrong_answer(self, tmp_path):
        task = {"checkers": [{"type": "answer_contains", "patterns": ["FizzBuzz"]}]}
        ctx = CheckContext(
            final_text="I'm sorry, but I cannot help with that.", sandbox_root=tmp_path
        )
        assert apply_checkers(task, ctx).outcome == Outcome.REFUSED

    def test_truncation_is_distinguished_from_a_wrong_answer(self, tmp_path):
        task = {"checkers": [{"type": "answer_contains", "patterns": ["FizzBuzz"]}]}
        ctx = CheckContext(
            final_text="Here is the beginning of my ans",
            sandbox_root=tmp_path,
            finish_reason="length",
        )
        assert apply_checkers(task, ctx).outcome == Outcome.TRUNCATED

    def test_human_review_is_pending_not_a_failure(self, tmp_path):
        """The original counted the creative checker's None as not-completed,
        which scored every creative arm 0/n by construction."""
        task = {"checkers": [{"type": "human_review", "rubric": ["voice"]}]}
        ctx = CheckContext(final_text="A villain monologue of some length.", sandbox_root=tmp_path)
        assert apply_checkers(task, ctx).outcome == Outcome.PENDING_REVIEW

    def test_empty_creative_response_is_a_fail(self, tmp_path):
        task = {"checkers": [{"type": "human_review"}]}
        assert (
            apply_checkers(task, CheckContext(final_text="  ", sandbox_root=tmp_path)).outcome
            == Outcome.FAIL
        )

    def test_unknown_checker_is_harness_error(self, tmp_path):
        task = {"checkers": [{"type": "nope"}]}
        assert (
            apply_checkers(task, CheckContext(sandbox_root=tmp_path)).outcome
            == Outcome.HARNESS_ERROR
        )

    def test_harness_error_outranks_fail(self, tmp_path):
        task = {
            "checkers": [
                {"type": "answer_contains", "patterns": ["nothing-matches-this"]},
                {"type": "nope"},
            ]
        }
        assert (
            apply_checkers(task, CheckContext(final_text="x", sandbox_root=tmp_path)).outcome
            == Outcome.HARNESS_ERROR
        )

    def test_all_checkers_must_pass(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        task = {
            "checkers": [
                {"type": "file_exists", "path": "a.txt"},
                {"type": "file_exists", "path": "b.txt"},
            ]
        }
        assert apply_checkers(task, CheckContext(sandbox_root=tmp_path)).outcome == Outcome.FAIL

    @pytest.mark.parametrize(
        "text",
        ["I can't help with that", "I won't do this", "I am unable to comply", "I must decline"],
    )
    def test_refusal_patterns(self, text):
        assert detect_refusal(text)

    def test_normal_prose_is_not_a_refusal(self):
        assert not detect_refusal("The parser cannot handle nested quotes, so I escaped them.")


def test_suites_parse_and_reference_real_checkers():
    """Every shipped suite must be loadable and name a checker that exists."""
    from pathlib import Path

    from tests.wfe.checkers import CHECKERS

    root = Path(__file__).resolve().parents[1] / "suites"
    seen = 0
    for f in sorted(root.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            task = json.loads(line)
            assert task.get("id") and task.get("instruction")
            for spec in task.get("checkers") or [task.get("checker", {})]:
                assert spec.get("type") in CHECKERS, f"{f.name}:{task['id']} -> {spec}"
                seen += 1
    assert seen > 0


def test_compliance_suite_carries_no_answer_key():
    """Contamination lock: the gold label must never be reachable by the model."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "suites"
    for name in ("compliance_agentic.jsonl", "compliance_agentic_full.jsonl"):
        f = root / name
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            task = json.loads(line)
            blob = json.dumps(task.get("seed") or {}) + task["instruction"]
            for tok in ("gold_label", "gold_finding_type", "gold_citation"):
                assert tok not in blob, f"{name}:{task['id']} leaks {tok} to the model"


def test_agentic_task_that_never_answers_is_budget_exhausted_not_a_wrong_answer(tmp_path):
    """Sibling of the reachability audit: a model that burns every turn on tool
    calls and never delivers an answer ran out of TURN budget — it must not be
    graded FAIL against an empty string as if it had answered wrongly."""
    import json
    from unittest.mock import patch

    from tests.wfe import runner as rn

    task = {
        "id": "loop",
        "agentic": True,
        "instruction": "research forever",
        "checkers": [{"type": "answer_contains", "patterns": ["never appears"]}],
    }
    fake = {
        "message": {
            "content": "",
            "tool_calls": [{"id": "c", "function": {"name": "file_list", "arguments": "{}"}}],
        },
        "finish_reason": "tool_calls",
        "economics": rn.Economics(),
        "harness_caveats": [],
        "resolved_think": "default",
    }
    with patch.object(rn, "chat", return_value=fake):
        out = rn.run_task(
            "m", "sys", task, rn.Sandbox(tmp_path), max_turns=3, budget_s=120, use_tools=True
        )
    assert out["outcome"] == Outcome.BUDGET_EXHAUSTED.value
    assert "turns" in json.dumps(out["transcript"])
