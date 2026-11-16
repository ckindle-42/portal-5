from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt.notables import stage2
from portal.modules.security.core.hunt.notables.scoreboard import ScoreboardError
from portal.modules.security.core.hunt.notables.stage2 import (
    Stage2Error,
    evaluate_family,
    judge_council,
    parse_council,
)

FIRST = 1616529600.0  # 2021-03-23T20:00:00Z
SOURCE = "/apache2/access.log.4"


def _stamp(moment: float) -> str:
    return stage2.time.strftime("%d/%b/%Y:%H:%M:%S", stage2.time.gmtime(moment))


def _line(term: str, moment: float = FIRST + 60.0) -> str:
    return f'10.0.0.5 - - [{_stamp(moment)} +0000] "GET /{term} HTTP/1.1" 200 12 "-" "curl"'


def _notable(key: str, term: str, generator: str, value: float) -> dict[str, Any]:
    query = f'search index="hb_kyoushi_s1" (source="{SOURCE}") TERM("{term}")'
    return {
        "notable_id": key,
        "generator": generator,
        "basis": "behaviour_share",
        "what": f"actor 10.0.0.5 did {term}",
        "why": "on 1/20 hosts",
        "content_key": key,
        "source_id": f"hb_kyoushi_s1:{SOURCE.rsplit('/', 1)[-1]}",
        "entities": [{"role": "actor", "value": "10.0.0.5"}],
        "measure": {"name": "similarity", "value": value},
        "evidence": [
            {"line": _line(term), "query": query, "earliest": FIRST, "latest": FIRST + 3600.0}
        ],
    }


def _run(tmp_path: Path, *, index: str = "hb_kyoushi_s1", excluded: str = "kyoushi") -> Path:
    run = tmp_path / "kyoushi"
    run.mkdir(parents=True, exist_ok=True)
    rows = [
        _notable("kb", "badterm", "similar_to_known", 0.9),
        _notable("kg", "goodterm", "peer_rare", 0.0),
    ]
    (run / "notables.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    progress = {
        "stages": {
            "cards": {"start": FIRST},
            "notables": {
                "seconds": {"total": 1.0},
                "similar_to_known": {
                    "excluded_family": excluded,
                    "loaded_families": ["santos", "russell"],
                    "knowledge_items": 5,
                    "embedding_model": "unit-embed",
                    "reliability": {"auc": 0.8},
                },
            },
        }
    }
    (run / "progress.json").write_text(json.dumps(progress))
    (run / "sources.json").write_text(
        json.dumps({"index": index, "cards": [{"facts": {"sources": [SOURCE]}}]})
    )
    keys = [{"host": "h", "source": SOURCE, "line": 1, "labels": ["step1"]}]
    (run / "keys.jsonl").write_text("".join(json.dumps(row) + "\n" for row in keys))
    logs = tmp_path / "gather"
    path = logs / "h" / "logs" / SOURCE.lstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_line("badterm") + "\n" + _line("goodterm") + "\n")
    return run


def _wrapped(word: str, p_yes: float) -> dict[str, Any]:
    return {
        "model": "gemma-seat",
        "choices": [
            {
                "message": {"content": f"**{word}**"},
                "logprobs": {
                    "content": [
                        {"token": "**", "top_logprobs": [{"token": "**", "logprob": -0.02}]},
                        {
                            "token": word,
                            "top_logprobs": [
                                {"token": "yes", "logprob": math.log(p_yes)},
                                {"token": "no", "logprob": math.log(1.0 - p_yes)},
                            ],
                        },
                    ]
                },
            }
        ],
    }


class _Judge:
    def complete(self, **request: Any) -> dict[str, Any]:
        bad = "badterm" in request["messages"][0]["content"]
        return _wrapped("yes" if bad else "no", 0.9 if bad else 0.1)


def _council_response(bad: bool) -> dict[str, Any]:
    recommendation = "SUPPORT" if bad else "REJECT"
    votes = (
        {"SUPPORT": 3, "REVISE": 0, "REJECT": 0}
        if bad
        else {
            "SUPPORT": 0,
            "REVISE": 0,
            "REJECT": 3,
        }
    )
    return {
        "choices": [{"message": {"content": f"**Code-determined decision: {recommendation}**"}}],
        "portal_council": {
            "aggregate": {
                "decision": recommendation,
                "votes": votes,
                "participating": 3,
                "roster": 3,
            },
            "reviewers": [
                {
                    "member_id": f"seat{index}",
                    "recommendation": recommendation,
                    "confidence": 0.9,
                    "valid": True,
                    "error": "",
                }
                for index in range(3)
            ],
        },
    }


class _Council:
    def complete(self, **request: Any) -> dict[str, Any]:
        return _council_response("badterm" in request["messages"][0]["content"])


def _evaluate(run: Path, tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "judge_target": (_Judge(), "hunt-reasoning"),
        "council_client": _Council(),
        "deadline": 60.0,
        "probe": 1,
        "concurrency": 1,
    }
    defaults.update(kwargs)
    return evaluate_family(
        "kyoushi", run, run / "keys.jsonl", tmp_path / "gather", 2021, **defaults
    )


def test_parse_council_scores_the_vote_fraction_and_keeps_the_decision():
    result = parse_council(_council_response(True), 1.5)
    assert result.p_yes == pytest.approx(1.0)
    assert result.decision == "SUPPORT"
    assert result.votes == {"SUPPORT": 3, "REVISE": 0, "REJECT": 0}
    assert result.participating == 3 and result.roster == 3
    assert len(result.seats) == 3
    assert result.reason is None
    mixed = parse_council(
        {
            "portal_council": {
                "aggregate": {
                    "decision": "ESCALATE",
                    "votes": {"SUPPORT": 1, "REVISE": 1, "REJECT": 1},
                    "participating": 3,
                    "roster": 3,
                }
            }
        },
        0.5,
    )
    assert mixed.p_yes == pytest.approx(0.5)
    assert mixed.decision == "ESCALATE"


def test_parse_council_without_decisive_votes_or_block_is_unjudged():
    abstain = parse_council(
        {
            "portal_council": {
                "aggregate": {
                    "decision": "ESCALATE",
                    "votes": {"SUPPORT": 0, "REVISE": 0, "REJECT": 0},
                    "participating": 0,
                    "roster": 3,
                }
            }
        },
        0.5,
    )
    assert abstain.p_yes is None and abstain.reason == "no_decisive_votes"
    missing = parse_council({"choices": [{"message": {"content": "plain answer"}}]}, 0.5)
    assert missing.p_yes is None and missing.reason == "missing_council_block"


def test_judge_council_transport_failure_is_unjudged():
    class _Down:
        def complete(self, **request: Any) -> dict[str, Any]:
            raise RuntimeError("down")

    result = judge_council(_Down(), "auto-council", _notable("kb", "badterm", "peer_rare", 0.0))
    assert result.p_yes is None and result.reason == "request_failed"


def test_evaluate_family_scores_both_arms_on_the_labelled_notables(tmp_path):
    run = _run(tmp_path)
    report = _evaluate(run, tmp_path)
    assert report["notables"] == {"total": 2, "distinct": 2, "bad": 1, "good": 1}
    assert report["common_notables"] == 2
    assert report["honesty"]["excluded_family"] == "kyoushi"
    single = report["single_judge"]
    assert single["model"] == "hunt-reasoning"
    assert single["judged"] == 2
    assert single["auc"] == pytest.approx(1.0)
    assert single["yes_rate_bad"] == pytest.approx(1.0)
    assert single["yes_rate_good"] == pytest.approx(0.0)
    assert single["wrapped_answers"] == 2
    council = report["council"]
    assert council["workspace"] == "auto-council"
    assert council["auc"] == pytest.approx(1.0)
    assert council["decision_yes_rate_bad"] == pytest.approx(1.0)
    assert council["decision_yes_rate_good"] == pytest.approx(0.0)
    assert council["decisions"] == {"SUPPORT": 1, "REJECT": 1}
    assert report["stage1_judge"]["judged"] == 0
    calls = [json.loads(line) for line in (run / "stage2_calls.jsonl").read_text().splitlines()]
    assert len(calls) == 4
    assert {call["arm"] for call in calls} == {"single_judge", "council"}
    assert (run / "stage2.json").is_file()
    assert all(call["common"] for call in calls)


def test_stage1_baseline_scores_the_runs_own_recorded_p_yes(tmp_path):
    run = _run(tmp_path)
    rows = [json.loads(line) for line in (run / "notables.jsonl").read_text().splitlines()]
    rows[0]["p_yes"] = 0.99
    rows[1]["p_yes"] = 0.99
    (run / "notables.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = _evaluate(run, tmp_path)
    baseline = report["stage1_judge"]
    assert baseline["judged"] == 2
    assert baseline["yes_rate_bad"] == pytest.approx(1.0)
    assert baseline["yes_rate_good"] == pytest.approx(1.0)
    assert baseline["auc"] == pytest.approx(0.5)


def test_proof_and_non_training_indexes_are_refused(tmp_path):
    run = _run(tmp_path, index="hb_ait_wheeler")
    with pytest.raises(ScoreboardError, match="proof"):
        _evaluate(run, tmp_path)
    run = _run(tmp_path, index="botsv2")
    with pytest.raises(Stage2Error, match="training"):
        _evaluate(run, tmp_path)


def test_leave_one_family_out_violation_is_refused(tmp_path):
    run = _run(tmp_path, excluded="santos")
    with pytest.raises(ScoreboardError, match="learned from its own family"):
        _evaluate(run, tmp_path)


def test_limit_caps_the_common_notable_set(tmp_path):
    run = _run(tmp_path)
    report = _evaluate(run, tmp_path, limit=1)
    assert report["common_notables"] == 1
    assert report["single_judge"]["judged"] == 1
    calls = [json.loads(line) for line in (run / "stage2_calls.jsonl").read_text().splitlines()]
    assert sum(1 for call in calls if call["common"]) == 2


def test_run_arm_budget_comes_from_the_measured_rate(tmp_path, monkeypatch):
    clock = [0.0]

    def call(item: dict[str, Any]) -> float:
        clock[0] += 1.0
        return item["value"]

    monkeypatch.setattr(stage2.time, "monotonic", lambda: clock[0])
    candidates = [{"value": index} for index in range(10)]
    results, basis = stage2._run_arm(candidates, call, deadline=6.0, probe=2, concurrency=1)
    assert basis["probe_calls"] == 2
    assert basis["seconds_per_call"] == pytest.approx(1.0)
    assert basis["derived_budget"] == 6
    assert results == [0, 1, 2, 3, 4, 5]
