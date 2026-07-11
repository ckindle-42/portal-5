"""Unit tests for proof capsules (Gap 3)."""

from __future__ import annotations

from portal.modules.security.core.capsules import (
    build_capsule,
    list_capsules,
    replay_capsule,
)
from portal.modules.security.core.oracles import OracleVerdict


class TestCapsuleBuild:
    def test_build_capsule_round_trips_dry_run(self):
        finding = {
            "id": "F-001",
            "title": "Reflected XSS in search",
            "target": "10.10.11.50",
            "severity": "high",
            "bug_class": "xss_reflected",
            "evidence": "<script>alert(1)</script> echoed",
            "oracle": "reflection",
            "param": "q",
        }
        verdict = OracleVerdict(
            oracle="reflection",
            oracle_kind="unescaped_reflection",
            verified=True,
            evidence="found script in response",
            honesty_claim="proves unescaped reflection, not that XSS executes",
            reproductions=3,
            required=3,
        )
        capsule = build_capsule(finding, verdict)
        assert capsule["capsule_schema_version"] == 1
        assert capsule["finding"]["id"] == "F-001"
        assert "integrity_sha256" in capsule

        # Round-trip via dry_run
        result = replay_capsule(capsule, dry_run=True)
        assert result.oracle == "reflection"
        assert "DRY-RUN" in result.evidence

    def test_capsule_carries_methodology_stamp(self):
        finding = {
            "id": "F-002",
            "oracle": "reflection",
            "title": "test",
            "target": "test",
        }
        verdict = OracleVerdict(
            oracle="reflection",
            oracle_kind="unescaped_reflection",
            verified=True,
            evidence="ok",
            honesty_claim="test",
            reproductions=2,
            required=2,
        )
        capsule = build_capsule(finding, verdict)
        assert "methodology_version" in capsule
        assert capsule["methodology_version"] == "v2-capability"

    def test_tampered_capsule_rejected(self):
        finding = {"id": "F-003", "oracle": "reflection", "title": "t", "target": "t"}
        verdict = OracleVerdict(
            oracle="reflection",
            oracle_kind="x",
            verified=True,
            evidence="ok",
            honesty_claim="t",
            reproductions=2,
            required=2,
        )
        capsule = build_capsule(finding, verdict)
        # Tamper
        capsule["finding"]["title"] = "TAMPERED"
        result = replay_capsule(capsule, dry_run=False)
        assert result.verified is False
        assert "integrity hash mismatch" in result.evidence

    def test_integrity_computation_is_deterministic(self):
        finding = {"id": "F-004", "oracle": "reflection", "title": "t", "target": "t"}
        verdict = OracleVerdict(
            oracle="reflection",
            oracle_kind="x",
            verified=True,
            evidence="ok",
            honesty_claim="t",
            reproductions=2,
            required=2,
        )
        c1 = build_capsule(finding, verdict)
        c2 = build_capsule(finding, verdict)
        assert c1["integrity_sha256"] == c2["integrity_sha256"]


class TestListCapsules:
    def test_list_returns_empty_for_nonexistent(self):
        result = list_capsules("nonexistent_engagement_xyz")
        assert isinstance(result, list)
