"""Negative-corpus and alert-fatigue scoring tests."""

from __future__ import annotations

from portal.modules.security.core import benign_corpus_bench as bench
from portal.modules.security.core import notify_scoreboard as ns


def _attack(verdict: str = "CONFIRMED") -> dict:
    return {
        "label": "attack",
        "status": "done",
        "technique_expected": "T1078",
        "model_arm": "arm",
        "verdict": verdict,
        "technique_ids": ["T1078"] if verdict == "CONFIRMED" else [],
        "oracle_result": "PRESENT",
        "cell_kind": "attack",
    }


def _benign(label: str, verdict: str) -> dict:
    return {
        "label": label,
        "status": "done",
        "ground_truth": "benign",
        "technique_expected": "",
        "model_arm": "arm",
        "verdict": verdict,
        "technique_ids": ["T1078"] if verdict == "CONFIRMED" else [],
    }


def test_benign_label_joined_without_attack_oracle() -> None:
    joined = ns.join_oracle([_benign("quiet", "RULED_OUT")])
    assert joined[0]["cell_kind"] == "benign"
    assert joined[0]["oracle_result"] == "ABSENT"


def test_precision_false_flag_rate_and_kind_breakdown() -> None:
    rows = ns.join_oracle(
        [
            _benign("quiet", "RULED_OUT"),
            _benign("wrong", "CONFIRMED"),
            _benign("anomaly", "ANOMALOUS_UNCLASSIFIED"),
        ]
    )
    scored = ns.score_arm(rows)
    fatigue = scored["axis_4_alert_fatigue_on_benign"]
    assert fatigue["notification_precision"] == 0.333
    assert fatigue["false_flag_rate"] == 0.667
    assert fatigue["false_flag_kinds"][ns.CONFIRMED_ON_BENIGN] == 1
    assert fatigue["false_flag_kinds"][ns.ANOMALY_ON_BENIGN] == 1


def test_combined_scoreboard_populates_recall_and_precision() -> None:
    rows = [_attack(), *ns.join_oracle([_benign("quiet", "RULED_OUT")])]
    scored = ns.score_arm(rows)
    assert scored["axis_1_notify_recall"]["raw"]["rate"] == 1.0
    assert scored["axis_4_alert_fatigue_on_benign"]["status"] == "MEASURED"
    assert not scored["measurement_gaps"]


def test_benign_and_attack_use_same_provenance_field_shape() -> None:
    assert bench.provenance_fields(bench.BENIGN_CELLS[0]) == {
        "evidence_origin",
        "source",
        "sourcetype",
        "host",
    }
