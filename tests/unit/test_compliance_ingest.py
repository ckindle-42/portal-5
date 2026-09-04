"""Layer/tier derivation from a document's own self-description (P3). Cases
are drawn from the operator's real filenames (not committed — see
TASK_COMPLIANCE_ENGINE_LANDING_V1's "do not commit the operator's PDFs";
only the filename strings, which carry no document content, are used here)."""

from __future__ import annotations

from portal.modules.compliance.core.ingest import derive_tier


def test_prefix_signal_beats_word_signal():
    d = derive_tier("OT-POL-014 Something.pdf")
    assert d["layer"] == "policy" and d["confidence"] >= 0.9


def test_policy_by_title_word():
    d = derive_tier("LSPG CIP Cyber Security Policy V13.pdf")
    assert d["layer"] == "policy"


def test_procedure_by_title_word():
    d = derive_tier("LSPG Access Management Procedure v10.pdf")
    assert d["layer"] == "procedure"


def test_work_instruction_and_its_wi_abbreviation_both_read_as_procedure():
    assert derive_tier("LSPG Key Management Work Instruction v6.pdf")["layer"] == "procedure"
    assert derive_tier("OT Vulnerability Management WI v1.pdf")["layer"] == "procedure"


def test_plan_and_process_read_as_procedure():
    assert derive_tier("LSPG CIP-006 Physical Security Plan V14.pdf")["layer"] == "procedure"
    assert derive_tier("BES Cyber System Categorization Process V9.pdf")["layer"] == "procedure"


def test_form_and_report_and_contact_list_read_as_evidence():
    assert derive_tier("LSPG CIP-004 PRA Attestation Form v6.pdf")["layer"] == "evidence"
    assert derive_tier("LSPG CIP-009 Recovery Summary Report Form v3.pdf")["layer"] == "evidence"
    assert derive_tier("SIRT Contact List v4.pdf")["layer"] == "evidence"


def test_no_signal_defaults_low_confidence_not_dropped():
    d = derive_tier("Untitled.pdf")
    assert d["layer"]  # a guess is returned, never empty/None
    assert d["confidence"] < 0.5
    assert "defaulted" in d["evidence"]


def test_first_page_text_signal_used_at_a_discount_when_filename_is_silent():
    silent_name = derive_tier("Untitled.pdf")
    with_body = derive_tier("Untitled.pdf", first_page_text="This Procedure describes...")
    assert with_body["layer"] == "procedure"
    assert with_body["confidence"] > silent_name["confidence"]
