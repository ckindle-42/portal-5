"""P3 vocabulary bridge (TASK_COMPLIANCE_REASONING_V6, check Y07)."""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.vocabulary_bridge import (
    align_actor,
    derive_vocabulary,
    propose_hypernyms,
)


@pytest.fixture(scope="module")
def vocab():
    return derive_vocabulary()


def test_vocabulary_has_core_defined_terms_marked_strong(vocab):
    for term in ("BES Cyber System", "EACMS", "PACS", "Protected Cyber Asset"):
        assert term in vocab.terms, term
    assert vocab.terms["BES Cyber System"].strength == "STRONG"
    # every term keeps at least one supporting fragment
    assert all(t.supporting_fragments for t in vocab.terms.values())


def test_hypernym_proposal_keeps_supporting_fragment(vocab):
    props = propose_hypernyms("OT BES Cyber System", vocab)
    assert props
    top = props[0]
    assert top.target_term == "BES Cyber System"
    assert top.rule == "containment"
    assert top.strength == "STRONG"
    assert top.supporting_fragment.get("node_id")


def test_internal_role_aligns_within_functional_entity(vocab):
    a = align_actor("OT Security Manager", "Each Responsible Entity", vocab)
    assert a.aligned
    assert a.proposal_chain and a.proposal_chain[0].rule == "role_within_functional_entity"
    assert "Responsible Entity" in a.note


def test_unrelated_actor_does_not_align(vocab):
    a = align_actor("Accounts Payable", "Responsible Entity", vocab)
    assert not a.aligned
    assert a.confidence == 0.0


def test_assessment_module_has_no_org_or_role_literal():
    src = __import__("pathlib").Path("portal/modules/compliance/core/assessment.py").read_text()
    for banned in ("LSPG", "Responsible Entity", "CIP Senior Manager", '"Manager"', "'Owner'"):
        assert banned not in src, banned


def test_actor_alignment_wired_into_compare():
    from portal.modules.compliance.core.assessment import _compare

    status, comparator, _ = _compare(
        "actor",
        "Each Responsible Entity",
        "OT Security Team",
        {"source_text": "The OT Security Team shall evaluate patches."},
    )
    assert status == "SUPPORTED"
    assert comparator == "vocabulary_bridge"
