"""Cause C2: known-answer controls, and every execution path gated."""

from __future__ import annotations

import datetime as dt
import glob
import json
import sys
import types
from pathlib import Path

import pytest

from tests.wfe import campaign, controls

REPO = Path(__file__).resolve().parents[3]
DET = r'"?determination"?\s*[:=]\s*"?(?:%s)\b'
SHOTGUN = "determination: SUPPORTED\ndetermination: CONTRADICTED\ncited_refs: []"
GOLD = '{"determination": "SUPPORTED", "cited_refs": ["X"]}'
FORBID = [DET % "PARTIAL|CONTRADICTED|ABSENT|ABSTAIN"]


def _task(tid="t1", forbid=True, **extra) -> dict:
    ck = {
        "type": "answer_contains",
        "patterns": [DET % "SUPPORTED", "cited_refs"],
        "exact": DET % "SUPPORTED",
    }
    if forbid:
        ck["forbid"] = FORBID
    return {
        "id": tid,
        "instruction": "Decide.",
        "checkers": [ck],
        "controls": {"pass": [GOLD], "fail": [SHOTGUN]},
        **extra,
    }


def test_shotgun_answer_is_caught_without_class_exclusive_forbid():
    assert [f.control for f in controls.check_task(_task(forbid=False))] == ["fail[0]"]


def test_class_exclusive_forbid_clears_the_shotgun():
    assert controls.check_task(_task()) == []


def test_exact_key_without_gold_is_a_failure():
    t = _task()
    t.pop("controls")
    assert "pass" in [f.control for f in controls.check_task(t)]


def test_echo_of_readable_seed_is_caught():
    t = {
        "id": "leak",
        "instruction": "Answer from notes.md.",
        "seed": {"notes.md": "the answer is 42"},
        "checkers": [{"type": "answer_contains", "patterns": ["42"]}],
    }
    assert [f.control for f in controls.check_task(t)] == ["echo"]


def test_expired_time_sensitive_key_blocks():
    t = {
        "id": "fed",
        "instruction": "Who chairs the Fed?",
        "expires": "2026-05-31",
        "checkers": [{"type": "answer_contains", "patterns": ["Powell"]}],
    }
    assert "expires" in [f.control for f in controls.check_task(t, today=dt.date(2026, 9, 7))]


def _runnable_suites() -> list[str]:
    # *.draft.jsonl is the authoring input. It is not a runnable suite.
    return sorted(
        p
        for p in glob.glob(str(REPO / "tests/wfe/suites/*.jsonl"))
        if not p.endswith(".draft.jsonl")
    )


@pytest.mark.parametrize("suite", _runnable_suites())
def test_every_repo_suite_passes_its_controls(suite):
    fails = controls.check_suite(suite)
    assert not fails, "\n".join(map(str, fails))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(controls, "TODAY", lambda: dt.date(2026, 10, 13))
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    suite = tmp_path / "s.jsonl"

    def write(*tasks):
        suite.write_text("".join(json.dumps(t) + "\n" for t in tasks))

    def row(tid, rid=None):
        return {
            "run_id": rid or tid,
            "suite_path": str(suite),
            "task_id": tid,
            "arm": "a",
            "workspace": "w",
            "suite": "s",
            "repeat": 1,
        }

    return types.SimpleNamespace(plan=plan, write=write, row=row, tmp=tmp_path)


def _receipts(d: Path) -> list[dict]:
    return [json.loads(x) for x in (d / "controls_receipts.jsonl").read_text().splitlines()]


def test_open_refuses_and_writes_no_manifest(env):
    env.write(_task(forbid=False))
    with pytest.raises(SystemExit, match="open: 1 task control"):
        campaign.open_campaign("c", env.plan, [env.row("t1")], append=False)
    assert not (campaign.CAMPAIGNS / "c" / "manifest.json").exists()


def test_open_keeps_a_receipt_with_suite_digest(env):
    env.write(_task())
    d = campaign.open_campaign("c", env.plan, [env.row("t1")], append=False)
    (rec,) = _receipts(d)
    assert rec["where"] == "open" and rec["failures"] == [] and rec["tasks"] == 1
    assert list(rec["suites"].values()) == [controls.suite_digest(env.tmp / "s.jsonl")]


def test_append_refuses_a_failing_task_and_leaves_rows_unchanged(env):
    env.write(_task("t1"), _task("t2", forbid=False))
    d = campaign.open_campaign("c", env.plan, [env.row("t1")], append=False)
    with pytest.raises(SystemExit, match="append"):
        campaign.open_campaign("c", env.plan, [env.row("t2")], append=True)
    assert [r["task_id"] for r in campaign.load_manifest(d)["rows"]] == ["t1"]


def test_resume_does_not_write_so_read_only_views_stay_read_only(env):
    env.write(_task())
    d = campaign.open_campaign("c", env.plan, [env.row("t1")], append=False)
    before = (d / "manifest.json").read_bytes()
    campaign.open_campaign("c", env.plan, [env.row("t1")], append=False)
    assert (d / "manifest.json").read_bytes() == before and len(_receipts(d)) == 1


def test_execution_regates_and_catches_a_key_that_expired_since_open(env, monkeypatch):
    env.write(_task(expires="2026-10-20"))
    d = campaign.open_campaign("c", env.plan, [env.row("t1")], append=False)
    monkeypatch.setattr(controls, "TODAY", lambda: dt.date(2026, 11, 1))
    monkeypatch.setattr(campaign, "expand_matrix", lambda *a, **k: [env.row("t1")])
    monkeypatch.setattr(campaign, "_warn_prompt_surface", lambda m: None)
    monkeypatch.setattr(campaign, "_ready", lambda d: True)

    def no_run(*a, **k):
        raise AssertionError("a row executed past a failing gate")

    monkeypatch.setattr(campaign, "execute_arm", no_run)
    monkeypatch.setattr(campaign, "_cmd_preflight", no_run)
    monkeypatch.setattr(sys, "argv", ["campaign", "--plan", str(env.plan), "--campaign-id", "c"])
    with pytest.raises(SystemExit, match=r"(?s)execute: .*expires"):
        campaign.main()
    assert d.exists()


def test_smoke_is_gated_before_any_model_call(env, monkeypatch):
    env.write(_task(forbid=False))
    monkeypatch.setattr(campaign, "expand_matrix", lambda *a, **k: [env.row("t1")])

    def boom(*a, **k):
        raise AssertionError("smoke reached the model past a failing gate")

    monkeypatch.setattr(campaign, "preflight_pipeline", boom)
    monkeypatch.setattr(campaign, "preflight_arm", boom)
    monkeypatch.setattr(campaign, "run_row", boom)
    args = types.SimpleNamespace(
        all_suites=False,
        arm=None,
        suite=None,
        task=None,
        workspace=None,
        campaign_id=None,
        force=True,
        debug_dir=None,
        max_turns=1,
        budget_s=1,
    )
    with pytest.raises(SystemExit, match="smoke"):
        campaign._cmd_smoke(args, env.plan)


def test_dry_run_reports_failing_controls_with_nonzero_exit(env, capsys):
    env.write(_task(forbid=False))
    assert campaign._cmd_dry_run([env.row("t1")], 1) == 4
    assert "controls: FAIL" in capsys.readouterr().out


def test_dry_run_passes_clean_controls(env, capsys):
    env.write(_task())
    assert campaign._cmd_dry_run([env.row("t1")], 1) == 0
    assert "controls: PASS" in capsys.readouterr().out


def test_a_task_needing_tools_the_row_cannot_offer_is_refused(env):
    t = _task()
    t["requires_tools"] = ["compliance_requirement", "compliance_ask"]
    env.write(t)
    row = {**env.row("t1"), "workspace": "auto-compliance"}
    assert campaign.tool_gaps([row]) == [
        "s:t1 in auto-compliance: needs tools not offered ['compliance_ask', 'compliance_requirement']"
    ]
    with pytest.raises(SystemExit, match="needs tools not offered"):
        campaign.open_campaign("c", env.plan, [row], append=False)


def test_the_shipped_decision_plan_has_no_unrunnable_task():
    matrix = campaign.expand_matrix(REPO / "tests/wfe/plans/decision_run_v1.yaml", 1)
    assert matrix and campaign.tool_gaps(matrix) == []
