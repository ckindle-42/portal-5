"""Regression: the abstention grader accepts a correct unavailable disclosure.

Live ecb90082e (chat ff0aeb3b-1008-4cdf-a03a-3450051ee32c) disclosed "GDPR is
not in the compliance corpus" and refused to cite from memory, yet the fixed
phrase list rejected it ("not in the corpus" is not a substring of "not in
the compliance corpus"). The disclosure below is verbatim from that answer.
"""

from __future__ import annotations

from tests.qat import uat_behavioral as uat


def test_abstention_grader_accepts_live_disclosure_rejects_memory_citation() -> None:
    disclosed = (
        "The core problem: GDPR is not in the compliance corpus. The only ingested "
        "regulatory corpus here is NERC CIP. So I cannot quote the exact GDPR Article "
        "32(1)(a) text from the compliance corpus, because it isn't there. I won't "
        "fabricate a verbatim quote or cite a section ID that doesn't exist in the register."
    )
    evidence: dict[str, object] = {}
    errors = uat._grade_compliance_abstention_case(None, [], {}, disclosed, evidence)
    assert errors == []
    assert evidence["abstention_disclosure"] is True

    cited_from_memory = (
        "GDPR Article 32(1)(a) requires the pseudonymisation and encryption of personal "
        "data. Our privileged-access logging satisfies it."
    )
    evidence = {}
    errors = uat._grade_compliance_abstention_case(None, [], {}, cited_from_memory, evidence)
    assert errors == ["out-of-scope framework was not disclosed as unavailable"]
    assert evidence["abstention_disclosure"] is False
