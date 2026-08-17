from __future__ import annotations

from portal.modules.security.core.bully.advisories import LiveAdvisoryConnector
from portal.modules.security.core.bully.connectors import QueryInPlaceConnector
from portal.modules.security.core.bully.coverage import register_coverage_source
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.live_profiles import derive_live_profiles
from portal.modules.security.core.bully.phase0_gate import evaluate_phase0_gate
from portal.modules.security.core.bully.planner_proof import planner_proof


def test_phase0_gate_requires_real_profile_and_audit_evidence(tmp_path):
    plane = DataPlane()
    plane.connect(
        "lab-splunk",
        QueryInPlaceConnector(
            "lab-splunk", lambda _: [{"timestamp": "2026-08-17", "host": "srv01", "actor": "alice"}]
        ),
        [{"timestamp": "2026-08-17", "host": "srv01", "actor": "alice"}],
    )
    plane.connect(
        "live-advisories",
        LiveAdvisoryConnector(
            lambda: {"vulnerabilities": [{"cveID": "CVE-1", "vendorProject": "V", "product": "P"}]},
            source_url="https://example.test/kev.json",
        ),
        [
            {
                "record_class": "threat_advisory",
                "attack_mappings": [{"external_id": "CVE-1"}],
                "artifacts": [{"type": "cve", "value": "CVE-1"}],
                "context_topology": {"vendor": "V"},
                "source": "https://example.test/kev.json",
                "retrieved_at": 1,
                "licence": "test",
            }
        ],
    )
    plane.connect(
        "case-history",
        QueryInPlaceConnector(
            "case-history", lambda _: [{"timestamp": "2026-08-17", "actor": "alice"}]
        ),
        [{"timestamp": "2026-08-17", "actor": "alice"}],
        source_meta={"label_basis": True},
    )
    plane.connect(
        "asset-identity-context",
        QueryInPlaceConnector(
            "asset-identity-context",
            lambda _: [{"timestamp": "2026-08-17", "host": "srv01", "actor": "alice"}],
        ),
        [{"timestamp": "2026-08-17", "host": "srv01", "actor": "alice"}],
    )
    coverage_path = tmp_path / "coverage.yaml"
    coverage_path.write_text("T1059:\n  description: shell\n", encoding="utf-8")
    register_coverage_source(plane, path=coverage_path)
    derive_live_profiles(plane, sample_limit=8)
    proof = planner_proof(plane)
    census = {"census": plane.census()}
    result = evaluate_phase0_gate(plane, census, proof)

    assert result["passed"] is True
    assert not result["blockers"]
    assert result["checks"]["entity_resolution_confidence_provenance"] is True
    assert result["checks"]["complete_query_audit"] is True
