"""P7.2 real specimen corpus, sealed truth, and blind baseline contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

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
