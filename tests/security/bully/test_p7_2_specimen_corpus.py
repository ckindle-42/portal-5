"""P7.2 real specimen corpus, sealed truth, and blind baseline contracts."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from portal.modules.security.core.bully.contracts import MutationOperatorSpec
from portal.modules.security.core.bully.cousin_calibration_bench import (
    BASELINE_CALIBRATION_V1,
    corpus_parent_reference_record,
    grade_corpus_blind,
    load_specimen_corpus,
    run_baseline_bench,
)
from portal.modules.security.core.bully.cousin_forge import forge
from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger, SpecimenRecord
from scripts.build_specimen_corpus import SPECIMEN_CORPUS_V1, build_corpus
from scripts.corpus_ingest import windows_xml_kv
from scripts.defensive_bully_specimen_e2e import run_proof

REPO_ROOT = Path(__file__).resolve().parents[3]
BULLY_DIR = REPO_ROOT / "portal" / "modules" / "security" / "core" / "bully"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def test_specimen_ledger_is_idempotent_hash_sealed_and_separate(tmp_path):
    ledger = SpecimenLedger(tmp_path / "specimens")
    specimen = SpecimenRecord(
        specimen_id="specimen-1",
        parent_id="parent-1",
        source_lane="replay_mutation",
        transform_ops=({"operator": "VARY_PARAMETER", "weight": 0.08},),
        construction_distance=0.08,
        data_yml_techniques=("T1059.001",),
        created_at=0.0,
        provenance={"class": "derived_variant"},
    )
    assert ledger.record(specimen)["parent_id"] == "parent-1"
    assert ledger.record(specimen)["parent_id"] == "parent-1"
    assert len(ledger.records()) == 1
    assert len(ledger.snapshot_hash()) == 64
    assert ledger.path.name == "specimen_ledger.jsonl"
    assert ledger.path.parent.name == "specimens"

    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text(lines[0].replace("parent-1", "parent-X") + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="seal broken"):
        ledger.truth_for("specimen-1")


def test_engine_modules_cannot_import_specimen_truth_or_forge_lane():
    engine_modules = {
        "signatures",
        "cousin_engine",
        "organ",
        "orchestrator",
        "investigation",
    }
    forbidden = {"specimen_ledger", "cousin_forge"}
    for module in engine_modules:
        imports = _imports(BULLY_DIR / f"{module}.py")
        leaves = {name.rsplit(".", 1)[-1] for name in imports}
        assert not leaves & forbidden, f"{module} crosses the sealed grading wall"


def _parent() -> dict:
    return {
        "specimen_id": "attack-data-parent-1",
        "target_host": "corpus-attack-data",
        "data_yml_techniques": ["T1059.001"],
        "telemetry": {"windows:security": ["EventCode=4688 Host=$TARGET_HOST"]},
        "telemetry_view": {
            "action_sequence": ["spawn", "connect"],
            "event_graph": {"ordered": ["spawn", "connect"]},
            "parameter_families": {"host": "$TARGET_HOST"},
            "context_topology": {"host_class": "windows"},
            "artifacts": {"process": "powershell.exe"},
            "attack_mappings": [{"technique_id": "T1059.001"}],
            "telemetry_shape": {"sourcetype": "windows:security"},
            "detector_outcomes": {"process_creation": "fired"},
        },
    }


def test_forge_rejects_relabel_only_and_records_clean_replayed_evidence(tmp_path):
    ledger = SpecimenLedger(tmp_path / "sealed")
    replayed = []

    def replay(path, **kwargs):
        replayed.append((path, kwargs))
        return {"ok": True, "shipped": 1}

    with pytest.raises(ValueError, match="relabel-only"):
        forge(
            _parent(),
            [MutationOperatorSpec("SUBSTITUTE_TECHNIQUE", {"from": "absent", "to": "x"})],
            ledger=ledger,
            evidence_dir=tmp_path / "evidence",
            replay_fn=replay,
        )

    result = forge(
        _parent(),
        [
            MutationOperatorSpec(
                "VARY_PARAMETER", {"placeholder": "$TARGET_HOST", "value": "alias.local"}
            )
        ],
        ledger=ledger,
        evidence_dir=tmp_path / "evidence",
        replay_fn=replay,
    )
    assert result.construction_distance == 0.08
    assert replayed and replayed[-1][1] == {"dry_run": False}
    evidence = __import__("json").loads(Path(result.capture_path).read_text())
    serialized = __import__("json").dumps(evidence, sort_keys=True)
    assert "attack-data-parent-1" not in serialized
    assert "T1059.001" not in serialized
    assert evidence["telemetry_origins"] == {"windows:security": "imported_observed"}
    assert evidence["telemetry_provenance"] == {"windows:security": "derived_variant"}
    engine_payload = __import__("json").dumps(result.engine_view, sort_keys=True)
    assert "attack-data-parent-1" not in engine_payload
    assert "T1059.001" in engine_payload
    assert ledger.truth_for(result.specimen_id)["parent_id"] == "attack-data-parent-1"


def test_forge_distance_is_monotonic_by_applied_operator_weight(tmp_path):
    ledger = SpecimenLedger(tmp_path / "sealed")

    def replay(path, **kwargs):
        return {"ok": True, "shipped": 1}

    near = forge(
        _parent(),
        [MutationOperatorSpec("REORDER_STEPS", {})],
        ledger=ledger,
        evidence_dir=tmp_path / "evidence",
        replay_fn=replay,
    )
    farther = forge(
        _parent(),
        [
            MutationOperatorSpec("REORDER_STEPS", {}),
            MutationOperatorSpec("OFF_SCRIPT_SUPPLY", {"technique_ids": ["T9999.001"]}),
        ],
        ledger=ledger,
        evidence_dir=tmp_path / "evidence",
        replay_fn=replay,
    )
    assert near.construction_distance < farther.construction_distance


def _write_attack_data_fixture(root: Path) -> None:
    admitted = root / "datasets" / "attack_techniques" / "T1558.003" / "fixture"
    admitted.mkdir(parents=True)
    (admitted / "windows.log").write_text(
        "EventCode=4769 TicketEncryptionType=0x17 Account=svc\n"
        "EventCode=4769 TicketEncryptionType=0x17 Account=backup\n",
        encoding="utf-8",
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
    excluded = root / "datasets" / "attack_techniques" / "T9999" / "fixture"
    excluded.mkdir(parents=True)
    (excluded / "sysmon.log").write_text("EventCode=1 Image=cmd.exe\n", encoding="utf-8")
    (excluded / "data.yml").write_text(
        """date: '2026-01-01'
mitre_technique: [T9999]
datasets:
  - path: /datasets/attack_techniques/T9999/fixture/sysmon.log
    sourcetype: XmlWinEventLog
    source: XmlWinEventLog:Microsoft-Windows-Sysmon/Operational
""",
        encoding="utf-8",
    )


def test_attack_data_windows_xml_is_flattened_for_existing_spl_fields():
    event = (
        "<Event><System><EventID>4769</EventID></System><EventData>"
        "<Data Name='TargetUserName'>svc</Data>"
        "<Data Name='TicketEncryptionType'>0x17</Data></EventData></Event>"
    )
    assert windows_xml_kv(event) == (
        "EventCode=4769 Account=svc TargetUserName=svc TicketEncryptionType=0x17"
    )


def _write_live_fixture(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": "external-live-cousin",
                "target_host": "authorized-lab",
                "episode_id": "specimen-live-1",
                "specimen_parent_id": "specimen-parent-live",
                "telemetry": {
                    "web:access": [
                        "GET /first HTTP/1.1 200",
                        "POST /second HTTP/1.1 403",
                    ]
                },
                "validity": {"checked": True, "valid": True, "coverage": 1.0},
                "mutation_operators": [
                    {"operator": "VARY_PARAMETER", "params": {"placeholder": "x", "value": "y"}}
                ],
            }
        ),
        encoding="utf-8",
    )


def test_three_lane_corpus_is_coverage_gated_truth_sealed_and_deterministic(tmp_path):
    root = tmp_path / "attack_data"
    _write_attack_data_fixture(root)
    live = tmp_path / "live.json"
    _write_live_fixture(live)

    first = build_corpus(
        attack_data_root=root,
        output_dir=tmp_path / "out-1",
        ledger_root=tmp_path / "ledger-1",
        live_lab_captures=(live,),
    )
    second = build_corpus(
        attack_data_root=root,
        output_dir=tmp_path / "out-2",
        ledger_root=tmp_path / "ledger-2",
        live_lab_captures=(live,),
    )
    assert first["schema"] == SPECIMEN_CORPUS_V1
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert first["ledger_snapshot_hash"] == second["ledger_snapshot_hash"]
    assert first["per_lane_counts"] == {
        "attack_data": 1,
        "replay_mutation": 8,
        "live_lab": 1,
    }
    assert first["complete"] is True
    assert first["coverage_report"]["admitted_parents"] == 1
    census = first["admission_census"]
    assert census["reconciled"] is True
    assert sum(census["counts"].values()) == census["catalog_size"] == 2
    assert census["counts"]["admitted"] == 1
    assert census["counts"]["no_ingested_sourcetype_technique_coverage"] == 1
    assert any(
        item["reason"] == "no_ingested_sourcetype_technique_coverage"
        for item in first["coverage_report"]["excluded"]
    )
    visible = json.dumps(first, sort_keys=True)
    assert "T1558.003" in visible
    assert "specimen_parent_id" not in visible

    truth = SpecimenLedger(tmp_path / "ledger-1").records()
    assert any(item["data_yml_techniques"] == ["T1558.003"] for item in truth)


class _ReadOnlySnapshot:
    def __init__(self, records):
        self.records = list(records)

    def knn(self, query, k, filters=None):
        return [(record, 0.08 + index * 0.01) for index, record in enumerate(self.records[:k])]

    def stats(self):
        return {"row_count": len(self.records)}


def test_cold_baseline_grades_before_truth_join_and_is_deterministic(tmp_path):
    root = tmp_path / "attack_data"
    _write_attack_data_fixture(root)
    live = tmp_path / "live.json"
    _write_live_fixture(live)
    output = tmp_path / "corpus"
    ledger_root = tmp_path / "ledger"
    built = build_corpus(
        attack_data_root=root,
        output_dir=output,
        ledger_root=ledger_root,
        live_lab_captures=(live,),
    )
    corpus_path = output / "specimen_corpus_v1.json"
    corpus = load_specimen_corpus(corpus_path)
    records = [
        corpus_parent_reference_record(item)
        for item in corpus["specimens"]
        if item["source_lane"] == "attack_data"
    ]
    source = inspect.getsource(grade_corpus_blind)
    assert "ledger" not in source
    assert "truth_for" not in source

    first = run_baseline_bench(
        _ReadOnlySnapshot(records),
        corpus_path=corpus_path,
        ledger=SpecimenLedger(ledger_root),
        output_dir=tmp_path / "baseline-1",
    )
    second = run_baseline_bench(
        _ReadOnlySnapshot(records),
        corpus_path=corpus_path,
        ledger=SpecimenLedger(ledger_root),
        output_dir=tmp_path / "baseline-2",
    )
    assert first.to_dict() == second.to_dict()
    assert first.schema == BASELINE_CALIBRATION_V1
    assert first.corpus_snapshot_hash == built["snapshot_hash"]
    assert first.cold_untuned is True
    assert first.training_applied is False
    assert first.threshold_tuning_applied is False
    assert first.calibration_proposal is None
    assert first.indeterminate
    assert set(first.failures) >= {
        "mid_distance_new_blind_spot",
        "real_same_overclaim",
        "non_monotonic",
    }
    assert all(row["oracle_response"] == "INDETERMINATE" for row in first.curve)
    assert (tmp_path / "baseline-1" / "baseline_calibration_v1.json").exists()
    assert (tmp_path / "baseline-1" / "baseline_calibration_curve.csv").exists()

    proof = run_proof(
        corpus_path=corpus_path,
        ledger=SpecimenLedger(ledger_root),
        baseline_path=tmp_path / "baseline-1" / "baseline_calibration_v1.json",
        output_dir=tmp_path / "p7-proof",
    )
    assert proof["passed"] is True
    assert proof["execution_mode"] == "offline_integrity"
    assert proof["checks"]["live_indexed_replay"] is True
    assert all(proof["checks"].values())
    assert len(proof["decision_impact_ids"]) == 6
