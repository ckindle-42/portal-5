"""Disagreement-only council. Every judge transport is mocked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.wfe import judge
from tests.wfe import judge_council as council
from tests.wfe.schema import sha12

WS, TASK = "auto-general", "t1"
ARM_A, ARM_B = "inc:tag", "cand:tag"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, tmp_path):
    monkeypatch.setenv("WFE_SETUP_FAULTS", str(tmp_path / "no-ledger.jsonl"))
    monkeypatch.delenv("WFE_JUDGE_COUNCIL_MODEL", raising=False)
    monkeypatch.delenv("WFE_JUDGE_COUNCIL_URL", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("judge council test opened a socket")

    monkeypatch.setattr("urllib.request.urlopen", boom)


def _ask(pref="B", calls=None, boom=False):
    def ask(messages, model, url, api_key):
        if calls is not None:
            calls.append({"messages": messages, "model": model, "url": url, "api_key": api_key})
        if boom:
            raise RuntimeError("judge down")
        return json.dumps({"preference": pref, "reason": "third reason"})

    return ask


def _build(
    tmp_path,
    *,
    local_pref="A",
    cloud_pref="B",
    text_a="alpha answer",
    text_b="beta answer",
    suite="realuse",
    same_sha=True,
    same_arms=True,
    outcome_a="FAIL",
    outcome_b="PASS",
    tool_a="",
):
    suite_path = tmp_path / "suite.jsonl"
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    task = {"id": TASK, "workspace": WS, "rubric": ["answers the question"]}
    suite_path.write_text(json.dumps(task) + "\n")
    rubric_sha = sha12(judge._rubric_text(task))
    campaign = tmp_path / "c1"
    (campaign / "rows").mkdir(parents=True)
    manifest = []
    for name, arm, text, outcome, tool in (
        ("a", ARM_A, text_a, outcome_a, tool_a),
        ("b", ARM_B, text_b, outcome_b, ""),
    ):
        (campaign / "rows" / f"{name}.json").write_text(
            json.dumps(
                {
                    "workspace": WS,
                    "suite": suite,
                    "task_id": TASK,
                    "repeat": 0,
                    "arm": arm,
                    "outcome": outcome,
                    "final_text": text,
                    "tool_call_log": [{"output": tool}] if tool else [],
                }
            )
        )
        manifest.append(
            {
                "workspace": WS,
                "suite": suite,
                "suite_path": str(suite_path),
                "task_id": TASK,
                "arm": arm,
            }
        )
    (campaign / "manifest.json").write_text(json.dumps({"rows": manifest}))
    arms = {"A": ARM_A, "B": ARM_B}
    _put(campaign, "local", local_pref, rubric_sha, arms, suite)
    _put(
        campaign,
        "cloud",
        cloud_pref,
        rubric_sha if same_sha else "deadbeefdead",
        arms if same_arms else {"A": ARM_B, "B": ARM_A},
        suite,
    )
    return campaign


def _put(campaign, profile, pref, rubric_sha, arms, suite):
    key = judge.pair_key(WS, suite, TASK, 0, ARM_A, ARM_B)
    path = judge._judgement_path(campaign, key, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "wfe-judge-1",
                "key": key,
                "workspace": WS,
                "suite": suite,
                "task_id": TASK,
                "repeat": 0,
                "arms": arms,
                "order_flipped": False,
                "rubric_sha": rubric_sha,
                "judge_model": f"{profile}-model",
                "judge_url": "http://127.0.0.1:9",
                "judge_profile": profile,
                "preference": pref,
                "winner": None if pref == "tie" else arms.get(pref),
                "reason": f"{profile} reason",
            }
        )
    )


def _council_records(campaign):
    return judge.load(campaign, "council")


def test_agreement_asks_nothing(tmp_path):
    campaign = _build(tmp_path, local_pref="A", cloud_pref="A")
    calls = []
    res = council.council_campaign(campaign, ask=_ask(calls=calls))
    assert res["disagreements"] == 0
    assert calls == []
    assert _council_records(campaign) == []


def test_a_disagreement_records_the_majority_once(tmp_path):
    campaign = _build(tmp_path, local_pref="A", cloud_pref="B", outcome_a="PASS", outcome_b="FAIL")
    calls = []
    res = council.council_campaign(campaign, ask=_ask("A", calls))
    assert res["judged"] == 1 and res["errors"] == 0 and res["excluded_setup"] == 0
    assert len(calls) == 1
    assert "alpha answer" in calls[0]["messages"][1]["content"]
    assert "beta answer" in calls[0]["messages"][1]["content"]
    rec = _council_records(campaign)[0]
    assert rec["preference"] == "A"
    assert rec["winner"] == ARM_A
    assert rec["excluded"] is None
    assert [m["profile"] for m in rec["members"]] == ["local", "cloud", "third"]
    assert "synthesis" not in rec
    assert council.checker_agreement(campaign) == (1, 1)
    again = council.council_campaign(campaign, ask=_ask("B", calls))
    assert again["skipped"] == 1 and again["judged"] == 0
    assert len(calls) == 1


def test_a_1_1_1_split_is_a_tie(tmp_path):
    campaign = _build(tmp_path)
    council.council_campaign(campaign, ask=_ask("tie"))
    rec = _council_records(campaign)[0]
    assert rec["preference"] == "tie"
    assert rec["winner"] is None
    assert "error" not in rec


def test_a_third_judge_error_is_recorded_and_retried(tmp_path):
    campaign = _build(tmp_path)
    calls = []
    res = council.council_campaign(campaign, ask=_ask(calls=calls, boom=True))
    assert res["errors"] == 1
    rec = _council_records(campaign)[0]
    assert rec["winner"] is None and rec["preference"] is None
    assert "RuntimeError" in rec["error"]
    assert len(rec["members"]) == 2
    council.council_campaign(campaign, ask=_ask("B", calls))
    assert len(calls) == 2
    assert _council_records(campaign)[0]["preference"] == "B"


def test_a_pipeline_or_tool_reply_is_excluded_and_not_judged(tmp_path):
    campaign = _build(tmp_path, text_a="Backend returned HTTP 400: request too long")
    calls = []
    res = council.council_campaign(campaign, ask=_ask(calls=calls))
    assert res["excluded_setup"] == 1 and res["judged"] == 0
    assert calls == []
    rec = _council_records(campaign)[0]
    assert rec["excluded"] == "setup"
    assert rec["preference"] is None
    assert [m["profile"] for m in rec["members"]] == ["local", "cloud"]
    summary = judge.summary(campaign, "council")
    assert summary["cells"] == {}
    screen = council.disagreement_screen(campaign)
    assert screen["disagreements"] == 1 and screen["excluded_setup"] == 1


def test_tool_infra_and_a_ledger_signature_are_setup(tmp_path, monkeypatch):
    tool = _build(tmp_path / "tool", tool_a="OCI runtime create failed: shim")
    assert council.council_campaign(tool, ask=_ask())["excluded_setup"] == 1
    ledger = tmp_path / "setup_faults.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "signature": "synthetic ledger fault",
                "first_seen": "2026-10-30",
                "campaign": "t",
                "cause": "c",
                "fix_commit": "abc",
            }
        )
        + "\n"
    )
    monkeypatch.setenv("WFE_SETUP_FAULTS", str(ledger))
    signed = _build(tmp_path / "signed", text_b="hit a synthetic ledger fault mid reply")
    calls = []
    assert council.council_campaign(signed, ask=_ask(calls=calls))["excluded_setup"] == 1
    assert calls == []


def test_a_mismatched_rubric_or_arm_map_is_not_a_disagreement(tmp_path):
    calls = []
    ask = _ask(calls=calls)
    assert (
        council.council_campaign(_build(tmp_path / "sha", same_sha=False), ask=ask)["disagreements"]
        == 0
    )
    assert (
        council.council_campaign(_build(tmp_path / "arms", same_arms=False), ask=ask)[
            "disagreements"
        ]
        == 0
    )
    assert calls == []


def test_a_sensitive_suite_stays_on_the_local_judge(tmp_path, monkeypatch):
    monkeypatch.setattr(
        council,
        "third_config",
        lambda: {
            "url": "https://api.deepseek.com/v1",
            "model": "deepseek-flash",
            "api_key_env": "DEEPSEEK_API_KEY",
        },
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-token")
    campaign = _build(tmp_path, suite="realuse_security")
    calls = []
    council.council_campaign(campaign, ask=_ask("A", calls))
    assert len(calls) == 1
    assert calls[0]["api_key"] is None
    assert calls[0]["url"] == judge.judge_url()
    assert calls[0]["model"] == judge.judge_model()
    assert "deepseek" not in calls[0]["url"]


def test_a_cloud_third_is_used_outside_sensitive_suites(tmp_path, monkeypatch):
    monkeypatch.setattr(
        council,
        "third_config",
        lambda: {
            "url": "https://api.deepseek.com/v1",
            "model": "deepseek-flash",
            "api_key_env": "DEEPSEEK_API_KEY",
        },
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-token")
    calls = []
    council.council_campaign(_build(tmp_path), ask=_ask("B", calls))
    assert calls[0]["api_key"] == "secret-token"
    assert calls[0]["url"] == "https://api.deepseek.com/v1"
    assert calls[0]["model"] == "deepseek-flash"


def test_screen_only_writes_nothing(tmp_path, capsys):
    campaign = _build(tmp_path, text_a="[Pipeline stream error — ended early]")
    assert (
        council.main(
            ["--campaign", campaign.name, "--campaigns-root", str(tmp_path), "--screen-only"]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "local/cloud disagreements: 1" in text
    assert "setup screen excludes: 1" in text
    assert _council_records(campaign) == []


def test_the_committed_third_is_local():
    cfg = council.third_config()
    assert judge.endpoint_is_local(cfg["url"])
    assert cfg["model"]
    assert "api_key_env" not in cfg


def test_the_decision_rule_does_not_read_the_council():
    text = (Path(__file__).resolve().parents[3] / "tests" / "wfe" / "decision.py").read_text()
    assert "judge_council" not in text
