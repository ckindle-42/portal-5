"""Tests for the eval-only V5A recall-attribution instrument."""

from __future__ import annotations

import inspect

from portal.modules.security.core import recall_attribution as ra


def _cell(
    *,
    expected: str = "T1558.004",
    verdict: str = "RULED_OUT",
    reported: list[str] | None = None,
    telemetry: str = "",
) -> dict:
    return {
        "label": "synthetic",
        "technique_expected": expected,
        "mode": "orchestrated",
        "model_arm": "test",
        "status": "done",
        "verdict": verdict,
        "technique_ids": reported or [],
        "scoring_recall": 0.0,
        "trace": [{"section": "tool", "content": telemetry}],
    }


class TestEvidenceOracle:
    def test_present_for_own_declared_discriminator(self):
        result = ra.attribute_cell(_cell(telemetry="EventCode=4768 Account=user PreAuthType=0"))
        assert result["oracle_result"] == ra.PRESENT
        assert result["matched_discriminators"] == ["PreAuthType=0"]

    def test_absent_when_only_sibling_discriminator_is_present(self):
        result = ra.attribute_cell(_cell(telemetry="EventCode=4769 TicketEncryptionType=0x17"))
        assert result["oracle_result"] == ra.ABSENT

    def test_indeterminate_without_machine_checkable_discriminator(self):
        result = ra.attribute_cell(_cell(expected="T1610", telemetry="container event"))
        assert result["oracle_result"] == ra.INDETERMINATE
        assert result["oracle_reason"] == "no_declared_discriminator"

    def test_spl_field_value_fallback_is_read_from_detection(self):
        info = ra.technique_discriminators("T1053.005")
        assert info["source"] == "spl_field_value_clauses"
        assert "EventCode=4698" in info["tokens"]

    def test_r1_spl_derived_literal_coverage(self):
        cases = {
            "T1190": "GET /index.php?cmd=whoami",
            "T1611": "exe=nsenter target=/proc/1/ns/mnt",
            "T1552.005": "GET http://169.254.169.254/latest/meta-data",
            "T1083": "GET /../../etc/passwd",
            "T1189": "GET /?q=%3Cscript%3Ealert(1)",
            "T1552": "GET /.git/config",
        }
        for technique_id, telemetry in cases.items():
            info = ra.technique_discriminators(technique_id)
            assert info["source"] == "declared_discriminator_tokens"
            assert ra.evidence_presence(telemetry, info["tokens"])[0] == ra.PRESENT

    def test_presence_function_is_label_blind(self):
        assert list(inspect.signature(ra.evidence_presence).parameters) == [
            "telemetry",
            "technique_discriminators",
        ]


class TestAttributionTruthTable:
    def test_true_positive(self):
        result = ra.attribute_cell(
            _cell(verdict="CONFIRMED", reported=["T1558.004"], telemetry="PreAuthType=0")
        )
        assert result["attribution"] == ra.TRUE_POSITIVE

    def test_misattribution(self):
        result = ra.attribute_cell(
            _cell(verdict="CONFIRMED", reported=["T1558.003"], telemetry="PreAuthType=0")
        )
        assert result["attribution"] == ra.MISATTRIBUTION

    def test_evidence_present_miss(self):
        result = ra.attribute_cell(
            _cell(verdict="ANOMALOUS_UNCLASSIFIED", telemetry="PreAuthType=0")
        )
        assert result["attribution"] == ra.EVIDENCE_PRESENT_MISS

    def test_honest_anomaly(self):
        result = ra.attribute_cell(
            _cell(verdict="ANOMALOUS_UNCLASSIFIED", telemetry="TicketEncryptionType=0x17")
        )
        assert result["attribution"] == ra.HONEST_ANOMALY

    def test_false_negative(self):
        result = ra.attribute_cell(_cell(verdict="RULED_OUT", telemetry="PreAuthType=0"))
        assert result["attribution"] == ra.FALSE_NEGATIVE

    def test_honest_negative(self):
        result = ra.attribute_cell(
            _cell(verdict="RULED_OUT", telemetry="TicketEncryptionType=0x17")
        )
        assert result["attribution"] == ra.HONEST_NEGATIVE

    def test_unscorable_by_oracle(self):
        result = ra.attribute_cell(
            _cell(expected="T1610", verdict="RULED_OUT", telemetry="generic container event")
        )
        assert result["attribution"] == ra.UNSCORABLE_BY_ORACLE


def test_oracle_uses_cell_trace_not_broader_corpus_data():
    cell = _cell(verdict="RULED_OUT", telemetry="TicketEncryptionType=0x17")
    cell["broader_corpus_telemetry"] = "PreAuthType=0"
    result = ra.attribute_cell(cell)
    assert result["oracle_result"] == ra.ABSENT
    assert result["attribution"] == ra.HONEST_NEGATIVE


def test_missing_model_visible_capture_is_indeterminate_not_absent():
    cell = _cell()
    cell["trace"] = [{"section": "reasoning", "raw": "PreAuthType=0"}]
    result = ra.attribute_cell(cell)
    assert result["oracle_result"] == ra.INDETERMINATE
    assert result["oracle_reason"] == "model_visible_telemetry_not_captured"


def test_deterministic_for_same_input():
    cell = _cell(verdict="ANOMALOUS_UNCLASSIFIED", telemetry="PreAuthType=0")
    assert ra.attribute_cell(cell) == ra.attribute_cell(cell)
