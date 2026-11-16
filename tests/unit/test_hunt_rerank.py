from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt.notables import rerank
from portal.modules.security.core.hunt.notables.rerank import (
    Family,
    _council_adjust,
    _council_budget,
    _council_second_pass,
    _fusion_order,
    _recall,
    _rule_name,
    _select_weight,
    product_order,
    score,
)
from portal.modules.security.core.hunt.notables.scoreboard import Notable, ScoreboardError

FIRST = 1616529600.0


def _notable(index: int, p_yes: float | None, key: str = "") -> Notable:
    return Notable(index, "peer_rare", None, p_yes, key or f"k{index}")


def test_fusion_weight_zero_is_the_stage1_order():
    notables = [_notable(0, 0.1), _notable(1, 0.9), _notable(2, None)]
    assert _fusion_order(notables, 0.0) == [0, 1, 2]


def test_fusion_weight_one_is_p_yes_desc_with_unjudged_last():
    notables = [_notable(0, 0.1), _notable(1, 0.9), _notable(2, None), _notable(3, 0.5)]
    assert _fusion_order(notables, 1.0) == [1, 3, 0, 2]


def test_intermediate_fusion_pulls_high_p_yes_up_but_keeps_stage1_weight():
    notables = [_notable(i, 0.5) for i in range(4)]
    notables[3].p_yes = 0.99
    order = _fusion_order(notables, 0.5)
    assert order.index(3) < 3
    assert _rule_name(0.0) == "stage1" and _rule_name(1.0) == "p_yes"
    assert _rule_name(0.25) == "fusion_w0.25"


def test_recall_counts_steps_under_the_new_rank():
    cmap = {"stepA": {0, 5}, "stepB": {40}}
    rank_of = {0: 60, 5: 10, 40: 20}
    recall = _recall(cmap, rank_of)
    assert recall[50] == 2  # stepA via 5@10, stepB via 40@20
    assert recall[100] == 2
    rank_of = {0: 0, 5: 10, 40: 200}
    assert _recall(cmap, rank_of)[50] == 1


def _family(name: str, scores: dict[float, tuple[int, int]]) -> Family:
    return Family(
        name,
        Path("."),
        [],
        [],
        {},
        12,
        scores={w: {50: a, 100: b, None: a} for w, (a, b) in scores.items()},
    )


def test_lofo_chooses_the_weight_on_the_other_families():
    # kyoushi best at w=0.25; santos best at w=0.0
    families = {
        "kyoushi": _family(
            "kyoushi", {0.0: (7, 10), 0.25: (9, 9), 0.5: (7, 9), 0.75: (6, 7), 1.0: (4, 4)}
        ),
        "santos": _family(
            "santos", {0.0: (3, 3), 0.25: (3, 3), 0.5: (3, 3), 0.75: (0, 3), 1.0: (0, 3)}
        ),
    }
    global_weight, folds = _select_weight(families)
    # held kyoushi trains on santos (tie 0/0.25/0.5 -> smallest 0.0)
    assert folds["kyoushi"] == 0.0
    # held santos trains on kyoushi (w0.25 wins 18)
    assert folds["santos"] == 0.25
    assert global_weight in rerank.FUSION_WEIGHTS


def test_lofo_single_family_falls_back_to_the_global_weight():
    families = {
        "kyoushi": _family(
            "kyoushi", {0.0: (7, 10), 0.25: (9, 9), 0.5: (7, 9), 0.75: (6, 7), 1.0: (4, 4)}
        )
    }
    global_weight, folds = _select_weight(families)
    assert folds["kyoushi"] == global_weight == 0.25


def test_council_adjust_support_rises_reject_sinks_within_k_only():
    notables = [_notable(i, 0.5, key=f"k{i}") for i in range(5)]
    order = [0, 1, 2, 3, 4]
    decisions = {"k0": "REJECT", "k1": "SUPPORT", "k2": "REVISE", "k3": "SUPPORT"}
    final, moved = _council_adjust(order, notables, decisions, 4)
    # within top4: SUPPORT (1,3) first, abstain (2) next, REJECT (0) last; index4 untouched
    assert final == [1, 3, 2, 0, 4]
    assert moved > 0
    assert final[4] == 4


def test_council_adjust_without_decisions_keeps_order():
    notables = [_notable(i, 0.5, key=f"k{i}") for i in range(3)]
    final, moved = _council_adjust([0, 1, 2], notables, {}, 3)
    assert final == [0, 1, 2] and moved == 0


def test_council_budget_is_what_the_deadline_buys_at_the_measured_rate():
    # 720 s at the live council rate (22.89 s/call, concurrency 2) buys 31 reviews
    assert _council_budget(100, 720.0, 22.8922) == 31
    assert _council_budget(5, 720.0, 22.8922) == 5
    assert _council_budget(100, 720.0, None) == 0
    assert _council_budget(100, 720.0, 0.0) == 0


def _council_family(tmp_path: Path, count: int) -> Family:
    notables = [_notable(i, 0.5, key=f"k{i}") for i in range(count)]
    return Family("kyoushi", tmp_path, [], notables, {}, 3)


def _calls(path: Path, decisions: dict[str, str]) -> None:
    path.write_text(
        "".join(
            json.dumps({"arm": "council", "content_key": key, "decision": decision}) + "\n"
            for key, decision in decisions.items()
        )
    )


def test_offline_council_replays_only_inside_the_derived_k(tmp_path):
    family = _council_family(tmp_path, 10)
    _calls(
        tmp_path / "stage2_calls.jsonl",
        {"k0": "REJECT", "k1": "SUPPORT", "k2": "SUPPORT", "k9": "SUPPORT"},
    )
    (tmp_path / "stage2.json").write_text(
        json.dumps({"council": {"budget_basis": {"seconds_per_call": 100.0}}})
    )
    final, receipt = _council_second_pass(
        family,
        list(range(10)),
        offline=True,
        council_client=None,
        council_workspace="auto-council",
        deadline=300.0,
        concurrency=2,
        probe=4,
    )
    assert receipt["top_k"] == 3  # 300 s // 100 s per call
    assert receipt["decisions_in_k"] == 3
    assert receipt["budget_basis"]["seconds_per_call"] == 100.0
    # k9's SUPPORT is outside K: it stays where the re-rank put it
    assert final == [1, 2, 0, 3, 4, 5, 6, 7, 8, 9]


def test_offline_council_without_a_measured_rate_changes_nothing(tmp_path):
    family = _council_family(tmp_path, 3)
    _calls(tmp_path / "stage2_calls.jsonl", {"k0": "REJECT"})
    final, receipt = _council_second_pass(
        family,
        [0, 1, 2],
        offline=True,
        council_client=None,
        council_workspace="auto-council",
        deadline=300.0,
        concurrency=2,
        probe=4,
    )
    assert receipt["top_k"] == 0 and receipt["moved_within_k"] == 0
    assert final == [0, 1, 2]


class _StubCouncil:
    """A Pipeline stand-in: reads the notable's statement, returns a coded council result."""

    def __init__(self, decisions: dict[int, str], count: int) -> None:
        self._decisions = decisions
        self._count = count

    def complete(self, **request: Any) -> dict[str, Any]:
        prompt = request["messages"][0]["content"]
        index = next(i for i in range(self._count) if f"statement-{i}" in prompt)
        decision = self._decisions.get(index, "SUPPORT")
        return {
            "choices": [{"message": {"content": f"**Code-determined decision: {decision}**"}}],
            "portal_council": {
                "aggregate": {
                    "decision": decision,
                    "votes": {
                        "SUPPORT": 2 if decision == "SUPPORT" else 0,
                        "REVISE": 0,
                        "REJECT": 2 if decision == "REJECT" else 0,
                    },
                    "participating": 2,
                    "roster": 3,
                },
                "reviewers": [],
            },
        }


def test_live_council_second_pass_calls_the_pipeline_on_the_top_k(tmp_path):
    rows = [
        {
            "what": f"statement-{i}",
            "generator": "similar_to_known",
            "content_key": f"k{i}",
        }
        for i in range(5)
    ]
    notables = [_notable(i, 0.5, key=f"k{i}") for i in range(5)]
    family = Family("kyoushi", tmp_path, rows, notables, {}, 3)
    final, receipt = _council_second_pass(
        family,
        list(range(5)),
        offline=False,
        council_client=_StubCouncil({0: "REJECT"}, 5),
        council_workspace="auto-council",
        deadline=720.0,
        concurrency=1,
        probe=1,
    )
    assert receipt["source"] == "live"
    assert receipt["top_k"] == 5
    assert receipt["decisions"] == {"SUPPORT": 4, "REJECT": 1}
    assert final == [1, 2, 3, 4, 0]
    records = [json.loads(line) for line in (tmp_path / rerank.CALLS_FILE).read_text().splitlines()]
    assert len(records) == 5
    assert {record["content_key"]: record["decision"] for record in records}["k0"] == "REJECT"


def test_product_order_fuses_p_yes_then_applies_measured_council(tmp_path):
    rows = [
        {
            "what": f"statement-{i}",
            "generator": "similar_to_known",
            "content_key": f"k{i}",
            "p_yes": score,
        }
        for i, score in enumerate((0.1, 0.9))
    ]

    order, receipt = product_order(
        rows,
        run=tmp_path,
        council_client=_StubCouncil({1: "REJECT"}, 2),
        deadline=720.0,
        concurrency=1,
        probe=1,
    )

    assert order == [0, 1]
    assert receipt["weight"] == 1.0
    assert receipt["weight_basis"] == "p_yes_signal_without_product_label_keys"
    assert receipt["council"]["top_k"] == 2
    assert receipt["council"]["budget_basis"]["seconds_per_call"] > 0
    assert (tmp_path / rerank.CALLS_FILE).is_file()


def _stamp(moment: float) -> str:
    return rerank.time.strftime("%d/%b/%Y:%H:%M:%S", rerank.time.gmtime(moment))


def _line(term: str) -> str:
    return f'10.0.0.5 - - [{_stamp(FIRST + 60)} +0000] "GET /{term} HTTP/1.1" 200 12 "-" "curl"'


def _row(key: str, term: str, p_yes: float | None, index: str) -> dict[str, Any]:
    query = f'search index="{index}" (source="/apache2/access.log.4") TERM("{term}")'
    row: dict[str, Any] = {
        "notable_id": key,
        "generator": "similar_to_known",
        "what": f"actor did {term}",
        "content_key": key,
        "source_id": f"{index}:access.log.4",
        "measure": {"name": "similarity", "value": 0.9},
        "evidence": [
            {"line": _line(term), "query": query, "earliest": FIRST, "latest": FIRST + 3600}
        ],
        "judge": {"decision_index": 0, "answer": "yes"},
    }
    if p_yes is not None:
        row["p_yes"] = p_yes
    return row


def _fixture(tmp_path: Path, name: str, index: str) -> tuple[Path, Path]:
    run = tmp_path / name
    run.mkdir(parents=True, exist_ok=True)
    rows = [
        _row("bad", "badterm", 0.9, index),
        _row("good", "goodterm", 0.8, index),
    ]
    (run / "notables.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run / "progress.json").write_text(
        json.dumps(
            {
                "stages": {
                    "cards": {"start": FIRST},
                    "notables": {
                        "similar_to_known": {
                            "excluded_family": name,
                            "loaded_families": ["other"],
                            "knowledge_items": 3,
                        }
                    },
                }
            }
        )
    )
    (run / "sources.json").write_text(
        json.dumps({"index": index, "cards": [{"facts": {"sources": ["/apache2/access.log.4"]}}]})
    )
    ingest = tmp_path / "corpus" / f"{name}_ingest"
    ingest.mkdir(parents=True, exist_ok=True)
    keys = ingest / "keys.jsonl"
    keys.write_text(
        json.dumps({"host": "h", "source": "/apache2/access.log.4", "line": 1, "labels": ["s1"]})
        + "\n"
    )
    gather = tmp_path / "corpus" / name / "gather" / "h" / "logs" / "apache2"
    gather.mkdir(parents=True, exist_ok=True)
    (gather / "access.log.4").write_text(_line("badterm") + "\n" + _line("goodterm") + "\n")
    return run, keys


def test_score_offline_reports_before_after_and_lofo(tmp_path):
    krun, kkeys = _fixture(tmp_path, "kyoushi", "hb_kyoushi_s1")
    srun, skeys = _fixture(tmp_path, "santos", "hb_ait_santos")
    report = score(
        {"kyoushi": krun, "santos": srun},
        {"kyoushi": kkeys, "santos": skeys},
        council=False,
    )
    assert len(report["families"]) == 2
    for fam in report["families"]:
        assert fam["steps"] == 1
        assert fam["recall"]["before"]["50"] == 1
        assert fam["answer_shape"] == {"wrapped_answers": 0, "bare_answers": 2}
        assert "bias" in fam["finding"]
        assert fam["chosen_weight"] in rerank.FUSION_WEIGHTS
        assert fam["weight_basis"] == "lofo"
        assert set(fam["lofo"]) == {
            "stage1",
            "fusion_w0.25",
            "fusion_w0.5",
            "fusion_w0.75",
            "p_yes",
        }
        assert fam["lofo"]["stage1"] == fam["recall"]["before"]
    assert (krun / "rerank.json").is_file()


def test_score_single_family_records_that_the_weight_is_not_lofo(tmp_path):
    krun, kkeys = _fixture(tmp_path, "kyoushi", "hb_kyoushi_s1")
    report = score({"kyoushi": krun}, {"kyoushi": kkeys}, council=False)
    assert report["families"][0]["weight_basis"] == "self"


def test_score_offline_replays_stored_council_calls(tmp_path):
    krun, kkeys = _fixture(tmp_path, "kyoushi", "hb_kyoushi_s1")
    (krun / "stage2_calls.jsonl").write_text(
        json.dumps({"arm": "council", "content_key": "bad", "decision": "REJECT"}) + "\n"
    )
    (krun / "stage2.json").write_text(
        json.dumps({"council": {"budget_basis": {"seconds_per_call": 100.0}}})
    )
    srun, skeys = _fixture(tmp_path, "santos", "hb_ait_santos")
    report = score(
        {"kyoushi": krun, "santos": srun},
        {"kyoushi": kkeys, "santos": skeys},
        offline=True,
    )
    kyoushi = next(f for f in report["families"] if f["family"] == "kyoushi")
    assert kyoushi["council"]["source"] == "stored_calls"
    assert kyoushi["council"]["top_k"] == 2  # 720 s deadline // 100 s per call, capped at 2
    assert kyoushi["council"]["decisions"] == {"REJECT": 1}
    assert kyoushi["council"]["moved_within_k"] == 2


def test_proof_index_and_lofo_violation_are_refused(tmp_path):
    krun, kkeys = _fixture(tmp_path, "kyoushi", "hb_ait_wheeler")
    with pytest.raises(ScoreboardError, match="proof"):
        score({"kyoushi": krun}, {"kyoushi": kkeys}, council=False)
    krun, kkeys = _fixture(tmp_path, "kyoushi", "hb_kyoushi_s1")
    progress = json.loads((krun / "progress.json").read_text())
    progress["stages"]["notables"]["similar_to_known"]["excluded_family"] = "santos"
    (krun / "progress.json").write_text(json.dumps(progress))
    with pytest.raises(ScoreboardError, match="own family"):
        score({"kyoushi": krun}, {"kyoushi": kkeys}, council=False)
