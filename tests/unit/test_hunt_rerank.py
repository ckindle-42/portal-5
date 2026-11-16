from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt.notables import rerank
from portal.modules.security.core.hunt.notables.rerank import (
    Family,
    _council_adjust,
    _fusion_order,
    _recall,
    _rule_name,
    _select_weight,
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
    assert (krun / "rerank.json").is_file()


def test_score_offline_replays_stored_council_calls(tmp_path):
    krun, kkeys = _fixture(tmp_path, "kyoushi", "hb_kyoushi_s1")
    (krun / "stage2_calls.jsonl").write_text(
        json.dumps({"arm": "council", "content_key": "good", "decision": "REJECT"}) + "\n"
    )
    srun, skeys = _fixture(tmp_path, "santos", "hb_ait_santos")
    report = score(
        {"kyoushi": krun, "santos": srun},
        {"kyoushi": kkeys, "santos": skeys},
        offline=True,
    )
    kyoushi = next(f for f in report["families"] if f["family"] == "kyoushi")
    assert kyoushi["council"]["source"] == "stored_calls"
    assert kyoushi["council"]["decisions"] == {"REJECT": 1}


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
