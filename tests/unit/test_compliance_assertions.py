"""Unit tests for tests/lib/compliance_assertions.py.

Pure-Python, no Docker, no network. Validates each assertion against
hand-crafted fixture responses representing the intended pass/fail shapes.
"""

from __future__ import annotations

import pytest

from tests.lib import compliance_assertions as ca

# ── Structural ────────────────────────────────────────────────────────────


class TestStructuralTableColumns:
    def test_passes_with_all_columns_in_markdown_table(self):
        resp = """
        Here is the gap analysis:

        | Requirement | Part | Coverage | Finding | Evidence Needed | Priority |
        |-------------|------|----------|---------|-----------------|----------|
        | CIP-007-6   | R2.2 | Partial  | review  | log retention   | P2       |
        """
        r = ca.assert_table_columns(resp)
        assert r.passed, r.detail

    def test_fails_when_missing_columns(self):
        resp = """
        | Requirement | Coverage | Finding |
        |-------------|----------|---------|
        | X | Full | none |
        """
        r = ca.assert_table_columns(resp)
        assert not r.passed
        assert "missing" in r.detail.lower()

    def test_fails_when_no_table(self):
        r = ca.assert_table_columns("Just some prose, no table at all.")
        assert not r.passed


# ── Classification ────────────────────────────────────────────────────────


class TestClassificationToken:
    def test_passes_with_token_in_table_cell(self):
        resp = "| CIP-007-6 | R2 | Partial | needs work | logs | P2 |"
        r = ca.assert_classification_token(resp)
        assert r.passed, r.detail

    def test_passes_with_coverage_colon_form(self):
        r = ca.assert_classification_token("Coverage: Full. Justification follows.")
        assert r.passed, r.detail

    def test_fails_when_only_synonyms_used(self):
        resp = "The control is fully compliant and addresses the requirement completely."
        r = ca.assert_classification_token(resp)
        assert not r.passed


# ── Anti-fabrication ──────────────────────────────────────────────────────


class TestAntiFabrication:
    def test_passes_with_refusal_phrase(self):
        resp = "I cannot reproduce the verbatim requirement text — see nerc.com/pa/Stand."
        r = ca.assert_no_fabrication_when_asked(resp)
        assert r.passed, r.detail

    def test_passes_with_authoritative_source_redirect(self):
        resp = "For the literal language, refer to the official source at hhs.gov/hipaa."
        r = ca.assert_no_fabrication_when_asked(resp)
        assert r.passed, r.detail

    def test_fails_with_long_quoted_block_no_refusal(self):
        long_quote = '"' + "X" * 130 + '"'
        resp = f"The exact text reads as follows: {long_quote}. This is the requirement."
        r = ca.assert_no_fabrication_when_asked(resp)
        assert not r.passed
        assert "fabrication" in r.detail.lower()


# ── Refuse to certify ─────────────────────────────────────────────────────


class TestRefuseToCertify:
    def test_passes_with_hedge(self):
        resp = (
            "Based on the evidence shown, the controls satisfy the requirement on "
            "the evidence presented. Final compliance determination requires SME review."
        )
        r = ca.assert_refuses_to_certify(resp)
        assert r.passed, r.detail

    def test_fails_with_certification_phrase(self):
        resp = "Yes, you are compliant with the standard. No further action needed."
        r = ca.assert_refuses_to_certify(resp)
        assert not r.passed
        assert "forbidden" in r.detail.lower()


# ── Insufficient context ──────────────────────────────────────────────────


class TestInsufficientContext:
    def test_passes_with_exact_phrase(self):
        resp = "Insufficient context — needed: framework, scope, control inventory."
        r = ca.assert_insufficient_context_pattern(resp)
        assert r.passed, r.detail

    def test_passes_with_loose_variant(self):
        resp = "I need more information before I can answer this."
        r = ca.assert_insufficient_context_pattern(resp)
        assert r.passed  # loose variants now accepted as PASS

    def test_fails_when_model_proceeds_anyway(self):
        resp = "Yes, you are likely compliant based on what I can infer."
        r = ca.assert_insufficient_context_pattern(resp)
        assert not r.passed
        assert r.severity == "SHOULD"


# ── Modal verbs ───────────────────────────────────────────────────────────


class TestModalVerbs:
    def test_passes_with_shall_and_no_aspirational(self):
        resp = (
            "[ENTITY NAME] SHALL review and document access privileges quarterly "
            "for [SYSTEM NAME]. Reviews SHOULD include role-based justification."
        )
        r = ca.assert_uses_modal_verbs(resp)
        assert r.passed, r.detail

    def test_fails_when_aspirational_present(self):
        resp = "We SHALL strive to ensure that access reviews are conducted."
        r = ca.assert_uses_modal_verbs(resp)
        assert not r.passed
        assert "aspirational" in r.detail.lower()

    def test_fails_with_no_modal_verbs(self):
        resp = "The team will conduct quarterly reviews of access privileges."
        r = ca.assert_uses_modal_verbs(resp)
        assert not r.passed


# ── Citation patterns ─────────────────────────────────────────────────────


class TestCitationPatterns:
    @pytest.mark.parametrize(
        "framework,sample",
        [
            ("NERC_CIP", "Per CIP-007-6 R2 Part 2.2, the entity shall..."),
            ("HIPAA", "45 CFR §164.312(a)(1) requires access controls."),
            ("GDPR", "GDPR Article 32(1)(a) requires security measures."),
            ("SOC2", "TSC CC6.1 covers logical access controls."),
            ("PCI_DSS", "PCI-DSS 4.0.1 Req 8.3.1 mandates MFA."),
            ("NIST_800_53", "NIST SP 800-53 Rev. 5 AC-2 covers account management."),
            ("ISO_27001", "ISO/IEC 27001:2022 A.5.15 addresses access control."),
        ],
    )
    def test_citation_format_recognized(self, framework, sample):
        r = ca.assert_citation_present(sample, framework)
        assert r.passed, f"{framework}: {r.detail}"

    def test_citation_missing_fails(self):
        r = ca.assert_citation_present("This response cites nothing.", "GDPR")
        assert not r.passed


# ── Aggregate outcome ─────────────────────────────────────────────────────


class TestScenarioOutcome:
    def test_all_must_pass_means_pass(self):
        oc = ca.ScenarioOutcome(
            scenario_id="x",
            framework="GDPR",
            results=(
                ca.AssertionResult("a", True, "ok", "MUST"),
                ca.AssertionResult("b", True, "ok", "SHOULD"),
            ),
        )
        assert oc.status == "PASS"

    def test_must_pass_should_fail_is_warn(self):
        oc = ca.ScenarioOutcome(
            scenario_id="x",
            framework="GDPR",
            results=(
                ca.AssertionResult("a", True, "ok", "MUST"),
                ca.AssertionResult("b", False, "x", "SHOULD"),
            ),
        )
        assert oc.status == "WARN"

    def test_must_fail_is_fail(self):
        oc = ca.ScenarioOutcome(
            scenario_id="x",
            framework="GDPR",
            results=(ca.AssertionResult("a", False, "x", "MUST"),),
        )
        assert oc.status == "FAIL"
