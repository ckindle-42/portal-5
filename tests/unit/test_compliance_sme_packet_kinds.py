"""The SME packet may only contain questions a human is the right answerer for.

V8 P7 / W17: "Every item carries a kind from SME_DECISION_KINDS, and zero items
are text-derivable — if the standard text and the procedure text settle it, the
module owes the answer, not the question."

Measured 2026-09-12: 1107 OPEN items, **0** carrying an SME kind, 812 of them
`low_confidence_extraction` — a retrieval stage reporting its own uncertainty,
which is precisely what the requirement forbids queueing. Root cause:
`SME_DECISION_KINDS` is defined and referenced nowhere else in the codebase.

These tests are hermetic — they assert the taxonomy and the classifier over
synthetic rows, never the live queue, so they run in CI without the operator's
private corpus. See `coding_task/v9_compliance/SME_PACKET_STATE_20260912.md`.
"""

from __future__ import annotations

import importlib

det = importlib.import_module("portal.modules.compliance.core.determination")

# Kinds the pipeline currently emits. Each is a CONFIDENCE signal about the
# module's own extraction, not a judgment only a compliance SME can make.
_PIPELINE_KINDS = {
    "low_confidence_extraction",
    "document_tier",
    "applicability_scope",
    "mapping_proposal",
}


def is_sme_kind(kind: str) -> bool:
    """The predicate the packet builder owes. Kept here (not in the module)
    deliberately: the module does not have one yet, and this test is what makes
    its absence visible rather than assumed."""
    return kind in det.SME_DECISION_KINDS


def test_the_five_sme_kinds_are_the_contract():
    """Pinned so a kind cannot be added or dropped without a decision."""
    assert set(det.SME_DECISION_KINDS) == {
        "S01_SCOPE_DECLARATION",
        "S02_INTENTIONAL_STRICTNESS",
        "S03_ACCEPT_PROPOSED_REDLINE",
        "S04_INTERPRETATION_DISPUTE",
        "S05_EVIDENCE_ATTESTATION",
    }


def test_every_sme_kind_describes_a_human_judgment():
    """Each kind must state what the human decides. A kind with no description
    is the same failure as OUTDATED_LANGUAGE with no trigger (Y21): a category
    nothing can route to."""
    for kind, desc in det.SME_DECISION_KINDS.items():
        assert desc and len(desc) > 15, f"{kind} has no usable description"


def test_pipeline_confidence_kinds_are_not_sme_kinds():
    """The distinction the packet rests on. A rerank score below a threshold is
    the module's problem; it is not a question for a compliance SME."""
    for kind in _PIPELINE_KINDS:
        assert not is_sme_kind(kind), (
            f"{kind!r} is a pipeline-confidence signal and must not reach the "
            "SME packet — the module owes the answer, not the question"
        )


def test_a_packet_of_pipeline_kinds_is_rejected():
    """The shape of the current failure, pinned as a regression case: a queue of
    1107 items none of which carries an SME kind is not an SME packet."""
    queue = [{"kind": k} for k in _PIPELINE_KINDS]
    accepted = [i for i in queue if is_sme_kind(i["kind"])]
    assert accepted == [], "pipeline kinds must not be accepted into the packet"


def test_a_well_formed_packet_passes_the_same_filter():
    """The positive case, so the filter is not trivially satisfied by rejecting
    everything — this is what the builder must eventually produce."""
    queue = [{"kind": k} for k in det.SME_DECISION_KINDS]
    accepted = [i for i in queue if is_sme_kind(i["kind"])]
    assert len(accepted) == len(det.SME_DECISION_KINDS)
