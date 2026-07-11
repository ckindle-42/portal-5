"""Unit tests for named-oracle verification (Gap 3)."""

from __future__ import annotations

import pytest

from portal.modules.security.core.oracles import (
    ORACLES,
    Oracle,
    register_oracle,
    verify_finding,
)


class TestOracleCheck:
    def test_reflection_matches_payload(self):
        oracle = ORACLES["reflection"]
        assert oracle.check({"payload": "XSS"}, "output with XSS", {}) is True
        assert oracle.check({"payload": "XSS"}, "clean output", {}) is False

    def test_rce_shell_matches_markers(self):
        oracle = ORACLES["rce_shell"]
        assert oracle.check({}, "got uid=1000 shell obtained", {}) is True
        assert oracle.check({}, "no shell here", {}) is False

    def test_sqli_error_matches_signatures(self):
        oracle = ORACLES["sqli_error"]
        assert oracle.check({}, "SQL syntax error near", {}) is True
        assert oracle.check({}, "all clear", {}) is False

    def test_cve_confirmed_matches_id(self):
        oracle = ORACLES["cve_confirmed"]
        assert oracle.check({"cve_id": "CVE-2021-44228"}, "found CVE-2021-44228", {}) is True
        assert oracle.check({"cve_id": "CVE-X"}, "found CVE-2021-44228", {}) is False

    def test_lfi_confirm_matches_root(self):
        oracle = ORACLES["lfi_confirm"]
        assert oracle.check({}, "root:x:0:0:root", {}) is True
        assert oracle.check({}, "no inclusion here", {}) is False

    def test_oast_callback_matches_id(self):
        oracle = ORACLES["oast_callback"]
        assert oracle.check({"callback_id": "abc123"}, "got abc123", {}) is True
        assert oracle.check({}, "nothing", {}) is False

    def test_idor_bola_not_implemented(self):
        oracle = ORACLES["idor_bola"]
        with pytest.raises(NotImplementedError):
            oracle.check({}, "", {})


class TestVerifyFinding:
    def test_missing_oracle_rejected(self):
        verdict = verify_finding({"no_oracle": "field"}, "some output", {}, required=2)
        assert verdict.verified is False
        assert "REJECTION" in verdict.evidence
        assert "no oracle named" in verdict.evidence

    def test_unknown_oracle_rejected(self):
        verdict = verify_finding({"oracle": "nonexistent_xyz"}, "output", {}, required=2)
        assert verdict.verified is False
        assert "REJECTION" in verdict.evidence
        assert "unknown oracle" in verdict.evidence

    def test_n_n_gating_passes(self):
        verdict = verify_finding(
            {"oracle": "reflection", "payload": "XSS"},
            "output with XSS that has XSS",
            {},
            required=2,
        )
        assert verdict.verified is True
        assert verdict.reproductions == 2

    def test_n_n_gating_fails_partial(self):
        verdict = verify_finding(
            {"oracle": "reflection", "payload": "XSS"},
            "clean output with no match",
            {},
            required=2,
        )
        assert verdict.verified is False
        assert verdict.reproductions == 0

    def test_experimental_tier_not_verified(self):
        # oast_callback is experimental — never counts as verified
        verdict = verify_finding(
            {"oracle": "oast_callback", "callback_id": "abc123"},
            "got abc123 and abc123",
            {},
            required=2,
        )
        assert verdict.verified is False  # tier=experimental excluded

    def test_verdict_copies_honesty_claim(self):
        verdict = verify_finding(
            {"oracle": "reflection", "payload": "XSS"},
            "output with XSS that has XSS",
            {},
            required=2,
        )
        assert verdict.honesty_claim == ORACLES["reflection"].honesty_claim


class TestRegistryExtensible:
    def test_register_oracle_adds_to_registry(self):
        new = Oracle(id="test_o", kind="test_kind", honesty_claim="test claim")
        register_oracle(new)
        assert "test_o" in ORACLES
        # Clean up
        ORACLES.pop("test_o")
