"""P7.2 real specimen corpus, sealed truth, and blind baseline contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from portal.modules.security.core.bully.contracts import MutationOperatorSpec
from portal.modules.security.core.bully.cousin_forge import forge
from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger, SpecimenRecord

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
    assert "T1059.001" not in engine_payload
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
