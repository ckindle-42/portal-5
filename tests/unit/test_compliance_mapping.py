"""Tests for the compliance_mapping + matrix schema dimension — Phase 4 of
TASK-SEC-DESIGN-GAP-DELIVERY-V1 (confirmed here per its own Phase 4 instruction:
"CHECK whether TASK_SEC_COMPLIANCE_REPORT_V1 Phase 1 landed the compliance_mapping
+ matrix dimension. If not -> add it here"). Also satisfies
TASK_SEC_COMPLIANCE_REPORT_GENERATOR_V1's own Phase 1 gate.

Validates:
- every spl_detections.yaml entry carries matrix + compliance_mapping
- every compliance_mapping entry cites a source (provenance rule — no uncited
  claim, same discipline as the wiki)
- back-compat: a technique with no matrix declared is treated as
  matrix: [enterprise] by the Navigator layer, never silently ICS
- the Navigator layer now emits BOTH enterprise-attack and ics-attack domains
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

import yaml

_YAML_PATH = (
    Path(__file__).resolve().parent.parent
    / "benchmarks"
    / "bench_security"
    / "siem"
    / "spl_detections.yaml"
)


def _load_detections() -> dict:
    return yaml.safe_load(_YAML_PATH.read_text())


class TestComplianceMappingSchema:
    def test_every_detection_has_matrix(self):
        d = _load_detections()
        missing = [tid for tid, v in d.items() if isinstance(v, dict) and not v.get("matrix")]
        assert not missing, f"detections missing matrix: {missing}"

    def test_every_detection_has_compliance_mapping(self):
        d = _load_detections()
        missing = [
            tid for tid, v in d.items() if isinstance(v, dict) and not v.get("compliance_mapping")
        ]
        assert not missing, f"detections missing compliance_mapping: {missing}"

    def test_every_mapping_cites_a_source(self):
        """Provenance rule: a mapping without a source is invalid."""
        d = _load_detections()
        for tid, v in d.items():
            if not isinstance(v, dict):
                continue
            for mapping in v.get("compliance_mapping", []):
                assert mapping.get("source"), (
                    f"{tid} has an uncited compliance_mapping entry: {mapping}"
                )
                assert mapping.get("framework"), f"{tid} mapping missing framework: {mapping}"

    def test_mitre_tactic_present_for_every_technique(self):
        d = _load_detections()
        for tid, v in d.items():
            if not isinstance(v, dict):
                continue
            frameworks = {m["framework"] for m in v.get("compliance_mapping", [])}
            assert "mitre-attack" in frameworks, f"{tid} has no mitre-attack tactic mapping"

    def test_nist_800_53_present_for_every_technique(self):
        d = _load_detections()
        for tid, v in d.items():
            if not isinstance(v, dict):
                continue
            frameworks = {m["framework"] for m in v.get("compliance_mapping", [])}
            assert "nist-800-53" in frameworks, f"{tid} has no NIST 800-53 mapping"

    def test_matrix_values_are_known(self):
        d = _load_detections()
        for tid, v in d.items():
            if not isinstance(v, dict):
                continue
            for mx in v["matrix"]:
                assert mx in ("enterprise", "ics"), f"{tid} has unknown matrix value: {mx}"


class TestNavigatorDomains:
    def test_navigator_layer_defaults_enterprise_backcompat(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))
        from bench_security.capability_graph import generate_navigator_layer, seed_graph_from_assets

        graph = seed_graph_from_assets()
        layer = generate_navigator_layer(graph)
        assert layer["domain"] == "enterprise-attack"
        assert len(layer["techniques"]) > 0

    def test_navigator_layers_emits_both_domains(self):
        from bench_security.capability_graph import (
            generate_navigator_layers,
            seed_graph_from_assets,
        )

        graph = seed_graph_from_assets()
        layers = generate_navigator_layers(graph)
        assert set(layers.keys()) == {"enterprise-attack", "ics-attack"}
        assert layers["enterprise-attack"]["domain"] == "enterprise-attack"
        assert layers["ics-attack"]["domain"] == "ics-attack"
        # Honest state today: no technique is verified ICS-tagged yet (Phase 4
        # populated NIST/tactic/NERC-CIP but did not fabricate ATT&CK-for-ICS
        # technique IDs without an authoritative offline source) — the ICS
        # layer legitimately has zero techniques, not a bug.
        assert layers["ics-attack"]["techniques"] == []
        assert len(layers["enterprise-attack"]["techniques"]) > 0

    def test_missing_matrix_technique_treated_as_enterprise_only(self):
        """Back-compat: a technique absent from spl_detections.yaml entirely
        (e.g. exercised-only, no detection rule) must default to enterprise,
        never silently appear in the ICS layer."""
        from bench_security.capability_graph import (
            CapabilityGraph,
            Procedure,
            generate_navigator_layers,
        )

        graph = CapabilityGraph()
        graph.add_procedure(
            Procedure(procedure_id="proc-x", scenario="x", technique_ids=frozenset({"T9999.999"}))
        )
        layers = generate_navigator_layers(graph)
        ent_ids = {t["techniqueID"] for t in layers["enterprise-attack"]["techniques"]}
        ics_ids = {t["techniqueID"] for t in layers["ics-attack"]["techniques"]}
        assert "T9999.999" in ent_ids
        assert "T9999.999" not in ics_ids
