from __future__ import annotations

import json
from pathlib import Path

from portal.modules.security.core.bully.cousin_calibration_bench import (
    BASELINE_CALIBRATION_V3,
    corpus_parent_reference_record,
    load_specimen_corpus,
    run_baseline_bench,
)
from portal.modules.security.core.bully.organ import _canonical_record_text
from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger
from scripts.build_specimen_corpus import SPECIMEN_CORPUS_V2, _read_parent, build_corpus_v2
from scripts.corpus_ingest import ManifestDataset, coerce


def _write_attack_data_fixture(root: Path) -> None:
    admitted = root / "datasets" / "attack_techniques" / "T1558.003" / "fixture"
    admitted.mkdir(parents=True)
    (admitted / "windows.log").write_text(
        "EventCode=4769 TicketEncryptionType=0x17 Account=svc\n", encoding="utf-8"
    )
    (admitted / "data.yml").write_text(
        """date: '2026-01-01'
mitre_technique: [T1558.003]
datasets:
  - path: /datasets/attack_techniques/T1558.003/fixture/windows.log
    sourcetype: XmlWinEventLog
    source: XmlWinEventLog:Security
""",
        encoding="utf-8",
    )


def test_non_object_json_is_preserved_as_real_raw_telemetry():
    raw = '[{"EventCode": 4769}]'
    assert coerce(raw) == raw
    assert coerce("null") == "null"


def test_windows_object_without_event_id_is_preserved_not_replaced_by_none(tmp_path):
    root = tmp_path / "attack_data"
    path = root / "datasets" / "fixture.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"Image":"cmd.exe"}\n', encoding="utf-8")
    parent = _read_parent(
        ManifestDataset(
            path=path,
            sourcetype="XmlWinEventLog",
            source="XmlWinEventLog:Security",
            dataset_epoch=0.0,
            techniques=("T1059",),
            mapped_sourcetype="windows:security",
        ),
        event_limit=32,
        attack_data_root=root,
    )
    assert parent["telemetry"] == {"windows:security": [{"Image": "cmd.exe"}]}


def _write_live_fixture(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": "external-live-cousin",
                "target_host": "authorized-lab",
                "episode_id": "specimen-live-v2",
                "specimen_parent_id": "specimen-parent-live-v2",
                "telemetry": {"web:access": ["GET /first HTTP/1.1 200"]},
                "validity": {"checked": True, "valid": True, "coverage": 1.0},
                "mutation_operators": [
                    {
                        "operator": "VARY_PARAMETER",
                        "params": {"placeholder": "x", "value": "y"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class _RealQueryFixture:
    def __init__(self) -> None:
        self.episodes: list[str] = []

    def query_episode(self, window, *, episode_id, host=None, limit=500):
        self.episodes.append(episode_id)
        return {
            "rows": [{"fields": {}, "raw": "TicketEncryptionType=0x17"}],
            "telemetry": "TicketEncryptionType=0x17",
            "source": "observed",
            "backend": "fixture-siem",
            "error": None,
            "detector_outcomes": {"production-kerberoast-rule": "fired"},
        }

    def query_freeform(self, spl, window, *, episode_id, host=None):
        return {
            "rows": [{"fields": {}, "raw": "TicketEncryptionType=0x17"}],
            "telemetry": "TicketEncryptionType=0x17",
            "source": "observed",
            "backend": "fixture-siem",
            "error": None,
        }


def test_v2_populates_real_opaque_outcomes_and_preserves_truth_wall(tmp_path):
    attack_data = tmp_path / "attack_data"
    _write_attack_data_fixture(attack_data)
    live = tmp_path / "live.json"
    _write_live_fixture(live)
    backend = _RealQueryFixture()
    corpus = build_corpus_v2(
        attack_data_root=attack_data,
        output_dir=tmp_path / "corpus",
        ledger_root=tmp_path / "ledger",
        live_lab_captures=(live,),
        ship=False,
        detector_backend=backend,
    )

    assert corpus["schema"] == SPECIMEN_CORPUS_V2
    assert corpus["execution_mode"] == "live_indexed"
    assert len(backend.episodes) == len(corpus["specimens"]) - 1
    assert corpus["response_observation_counts"] == {
        "fired": len(corpus["specimens"]) - 1,
        "partial": 0,
        "missed": 0,
        "indeterminate": 1,
    }
    for specimen in corpus["specimens"]:
        assert specimen["execution_mode"] == "live_indexed"
        view = specimen["engine_view"]["telemetry_view"]
        assert set(view["detector_outcomes"].values()) <= {"fired", "partial", "missed"}
        assert all(key.startswith("detector-") for key in view["detector_outcomes"])
        if specimen["source_lane"] != "live_lab":
            assert view["attack_mappings"] == [{"technique_id": "T1558.003"}]

    engine_payload = json.dumps(
        [specimen["engine_view"] for specimen in corpus["specimens"]], sort_keys=True
    )
    assert "T1558.003" in engine_payload
    assert "specimen_parent_id" not in engine_payload
    assert SpecimenLedger(tmp_path / "ledger").records()


class _EmptyDetectionFixture:
    def query_episode(self, window, *, episode_id, host=None, limit=500):
        return {
            "rows": [{"fields": {}, "raw": "EventCode=1 Image=benign.exe"}],
            "telemetry": "EventCode=1 Image=benign.exe",
            "source": "observed",
            "backend": "fixture-siem",
            "error": None,
        }

    def query_freeform(self, spl, window, *, episode_id, host=None):
        return {
            "rows": [],
            "telemetry": "",
            "source": "empty",
            "backend": "fixture-siem",
            "error": None,
        }


def test_real_empty_detection_result_is_an_honest_miss(tmp_path):
    attack_data = tmp_path / "attack_data"
    _write_attack_data_fixture(attack_data)
    corpus = build_corpus_v2(
        attack_data_root=attack_data,
        output_dir=tmp_path / "corpus",
        ledger_root=tmp_path / "ledger",
        ship=False,
        detector_backend=_EmptyDetectionFixture(),
    )
    assert corpus["response_observation_counts"] == {
        "fired": 0,
        "partial": 0,
        "missed": len(corpus["specimens"]),
        "indeterminate": 0,
    }
    assert all(
        set(specimen["engine_view"]["telemetry_view"]["detector_outcomes"].values()) == {"missed"}
        for specimen in corpus["specimens"]
    )


def test_identical_dataset_bytes_remain_distinct_admitted_parents(tmp_path):
    attack_data = tmp_path / "attack_data"
    _write_attack_data_fixture(attack_data)
    duplicate = attack_data / "datasets" / "attack_techniques" / "T1003.006" / "fixture"
    duplicate.mkdir(parents=True)
    (duplicate / "windows.log").write_text(
        "EventCode=4769 TicketEncryptionType=0x17 Account=svc\n", encoding="utf-8"
    )
    (duplicate / "data.yml").write_text(
        """date: '2026-01-01'
mitre_technique: [T1003.006]
datasets:
  - path: /datasets/attack_techniques/T1003.006/fixture/windows.log
    sourcetype: XmlWinEventLog
    source: XmlWinEventLog:Security
""",
        encoding="utf-8",
    )
    corpus = build_corpus_v2(
        attack_data_root=attack_data,
        output_dir=tmp_path / "corpus",
        ledger_root=tmp_path / "ledger",
        ship=False,
        detector_backend=_RealQueryFixture(),
    )
    parent_ids = {
        item["specimen_id"] for item in corpus["specimens"] if item["source_lane"] == "attack_data"
    }
    assert len(parent_ids) == 2
    assert corpus["admission_census"]["counts"]["admitted"] == 2


class _ReadOnlySnapshot:
    def __init__(self, records):
        self.records = list(records)

    def knn(self, query, k, filters=None):
        return [(record, 0.08 + index * 0.01) for index, record in enumerate(self.records[:k])]

    def stats(self):
        return {"row_count": len(self.records)}


def test_v2_baseline_is_hashed_and_characterizes_curve_lanes_and_response(tmp_path):
    attack_data = tmp_path / "attack_data"
    _write_attack_data_fixture(attack_data)
    live = tmp_path / "live.json"
    _write_live_fixture(live)
    output = tmp_path / "corpus"
    ledger_root = tmp_path / "ledger"
    built = build_corpus_v2(
        attack_data_root=attack_data,
        output_dir=output,
        ledger_root=ledger_root,
        live_lab_captures=(live,),
        ship=False,
        detector_backend=_RealQueryFixture(),
    )
    corpus_path = output / "specimen_corpus_v2.json"
    corpus = load_specimen_corpus(corpus_path)
    records = [
        corpus_parent_reference_record(item)
        for item in corpus["specimens"]
        if item["source_lane"] == "attack_data"
    ]
    assert all(record["behavior_sequence"] for record in records)
    assert all(record["semantic_query"] in _canonical_record_text(record) for record in records)
    assert all(
        record["field_signature"] not in _canonical_record_text(record) for record in records
    )
    report = run_baseline_bench(
        _ReadOnlySnapshot(records),
        corpus_path=corpus_path,
        ledger=SpecimenLedger(ledger_root),
        output_dir=tmp_path / "baseline",
    )

    assert report.schema == BASELINE_CALIBRATION_V3
    assert report.corpus_snapshot_hash == built["snapshot_hash"]
    assert report.snapshot_hash and len(report.snapshot_hash) == 64
    assert report.reference_guard["immutable"] is True
    assert report.reference_guard["acceptance"] == "match_or_beat"
    assert report.status == "VALID"
    assert report.controls["passed"] is True
    characterization = report.characterization
    assert characterization["band_crossing"]["rows"] == len(corpus["specimens"]) - 1
    assert characterization["instrument_health"]["measurement_invalid_rows"] == 1
    assert characterization["monotonicity"]["comparable_pairs"] > 0
    assert set(characterization["per_lane"]) == {
        "attack_data",
        "replay_mutation",
        "live_lab",
    }
    assert characterization["response_axis"]["distribution"] == {
        "COVERED": len(corpus["specimens"]) - 1,
    }
    assert "replay_mutation_vs_live_lab" in characterization["lane_comparison"]
    assert (tmp_path / "baseline" / "baseline_calibration_v3.json").exists()
