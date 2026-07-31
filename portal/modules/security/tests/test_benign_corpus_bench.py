"""Negative-corpus and alert-fatigue scoring tests."""

from __future__ import annotations

import json

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


def test_expanded_benign_corpus_is_balanced_and_unique() -> None:
    assert len(bench.BENIGN_CELLS) == 12
    ids = [cell["cell_id"] for cell in bench.BENIGN_CELLS]
    assert len(ids) == len(set(ids))
    counts = {
        sourcetype: sum(cell["sourcetype"] == sourcetype for cell in bench.BENIGN_CELLS)
        for sourcetype in ("windows:security", "web:access", "linux:auditd")
    }
    assert counts == {
        "windows:security": 4,
        "web:access": 4,
        "linux:auditd": 4,
    }


def test_expansion_includes_plausibly_confusable_routine_activity() -> None:
    text = "\n".join(event for cell in bench.BENIGN_CELLS[6:] for event in cell["events"]).lower()
    assert "eventcode=4698" in text  # approved scheduled task
    assert "wmiprvse.exe" in text  # approved inventory
    assert "404" in text  # QA link checker
    assert "nsenter" in text  # Kubernetes CSI reconciliation


def test_targeted_rerun_replaces_only_selected_retained_cell(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "benign.json"
    checkpoint.write_text(
        json.dumps(
            [
                {"label": "p5n001", "status": "done", "verdict": "RULED_OUT"},
                {"label": "p5n002", "status": "done", "verdict": "CONFIRMED"},
            ]
        )
    )
    monkeypatch.setattr(bench, "OUT_PATH", checkpoint)
    monkeypatch.setattr(bench, "_wait_for_cell", lambda backend, cell: ["event"])
    monkeypatch.setattr(
        bench,
        "_run_cell",
        lambda cell, telemetry: {
            "label": cell["cell_id"],
            "status": "done",
            "verdict": "RULED_OUT",
        },
    )

    results = bench.run_bench(rerun_cells={"p5n002"})

    assert {record["label"] for record in results} == {"p5n001", "p5n002"}
    assert (
        next(record for record in results if record["label"] == "p5n002")["verdict"] == "RULED_OUT"
    )


def test_targeted_rerun_requires_retained_checkpoint() -> None:
    try:
        bench.run_bench(resume=False, rerun_cells={"p5n002"})
    except ValueError as exc:
        assert "retained checkpoint" in str(exc)
    else:
        raise AssertionError("targeted rerun without a checkpoint should fail")
