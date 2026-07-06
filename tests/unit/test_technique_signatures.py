"""Unit tests for M4 — sub-technique distinguishing signatures.

Verifies that technique signatures include distinguishing features
that help the harness differentiate sibling sub-techniques.
"""

from __future__ import annotations

from tests.benchmarks.bench_security.siem.spl_detections import (
    technique_reference,
    technique_signature_full,
)


class TestTechniqueSignatureFull:
    def test_kerberoast_has_distinguishing_features(self):
        full = technique_signature_full("T1558.003")
        assert full["description"] != ""
        diff = full.get("distinguishing_features", {})
        assert diff.get("event_code") == 4769
        assert diff.get("sibling_diff") != ""

    def test_asrep_has_distinguishing_features(self):
        full = technique_signature_full("T1558.004")
        diff = full.get("distinguishing_features", {})
        assert diff.get("event_code") == 4768
        assert diff.get("preauth") == "PreAuthType=0 (disabled)"

    def test_dcsync_has_distinguishing_features(self):
        full = technique_signature_full("T1003.006")
        diff = full.get("distinguishing_features", {})
        assert diff.get("event_code") == 4662
        assert "replication" in diff.get("sibling_diff", "").lower()

    def test_sibling_diff_differentiates(self):
        """The sibling_diff for T1558.003 and T1558.004 should be complementary."""
        k3 = technique_signature_full("T1558.003")
        k4 = technique_signature_full("T1558.004")
        diff3 = k3["distinguishing_features"]["sibling_diff"]
        diff4 = k4["distinguishing_features"]["sibling_diff"]
        # They should reference each other
        assert "T1558.004" in diff3
        assert "T1558.003" in diff4
        # They should mention different event codes
        assert "4769" in diff3
        assert "4768" in diff4

    def test_technique_reference_includes_distinguishing_info(self):
        """technique_reference() should embed distinguishing features in description."""
        ref = technique_reference()
        # T1558.003 should have [DISTINGUISH: ...] in its description
        assert "[DISTINGUISH:" in ref.get("T1558.003", "")
        assert "[KEY:" in ref.get("T1558.003", "")
        # T1558.004 should also
        assert "[DISTINGUISH:" in ref.get("T1558.004", "")

    def test_unknown_technique_returns_empty(self):
        full = technique_signature_full("T9999.999")
        assert full == {}

    def test_password_spray_distinguishing(self):
        full = technique_signature_full("T1110.003")
        diff = full.get("distinguishing_features", {})
        assert "many accounts" in diff.get("sibling_diff", "").lower()
