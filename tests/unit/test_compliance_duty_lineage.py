"""Semantic duty identity and cross-revision lineage (foundation P3).

Lineage is computed from duty-text correspondence, never from matching Part
numbers. These tests pin: the terminology-fold normalizer, the 0.75
discrimination threshold against same-duty and different-duty text, concept
stability as the lineage grows, and the conflict guard on reassignment.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.duty_lineage import (
    DERIVATION,
    DutyHandle,
    assign_concepts,
    normalize_duty_text,
    pair_duties,
    similarity,
)


def _duty(node_id: str, text: str, standard: str = "CIP-007") -> DutyHandle:
    return DutyHandle(node_id=node_id, standard=standard, text=text)


# CIP-007-6 R2 Part 2.2 vs its 7.1 counterpart — same duty, drifted terminology
V6_22 = (
    "At least once every 35 calendar days, evaluate security patches for "
    "applicability that have been released since the last evaluation from the "
    "source or sources identified in Part 2.1."
)
V71_22 = (
    "At least once every 35 calendar days, evaluate cyber security patches for "
    "applicability that have been released since the last evaluation from the "
    "source or sources identified in Part 2.1."
)
V71_13 = (
    "The Responsible Entity has not prevented the sharing of the CPU and "
    "memory resources between VCAs that are, or are associated with, a Medium "
    "or High Impact BCS, and VCAs that are not, or are not associated with a "
    "Medium or High Impact BCS."
)
DIFFERENT_DUTY = (
    "Each Responsible Entity shall retain logs for at least 90 calendar days "
    "in an internal clock-synchronized time source."
)


def test_normalizer_folds_terminology_drift():
    a = normalize_duty_text(V6_22)
    b = normalize_duty_text(V71_22)
    assert a == b


def test_same_duty_scores_far_above_the_threshold():
    assert similarity(V6_22, V71_22) >= 0.75


def test_different_duties_score_below_the_threshold():
    assert similarity(V6_22, DIFFERENT_DUTY) < 0.5
    assert similarity(V71_22, V71_13) < 0.5


def test_part_numbers_are_never_the_matching_feature():
    """Two duties with swapped numbering still pair by their text."""
    pairs, un_a, un_b = pair_duties(
        [_duty("CIP-007-6 R2 Part 9.9", V6_22)],
        [_duty("CIP-007-7.1 R2 Part 1.1", V71_22)],
    )
    assert len(pairs) == 1 and not un_a and not un_b


def test_revision_new_duty_stays_unpaired():
    pairs, un_a, un_b = pair_duties(
        [_duty("CIP-007-6 R2 Part 2.2", V6_22)],
        [_duty("CIP-007-7.1 R2 Part 2.2", V71_22), _duty("CIP-007-7.1 R1 Part 1.3", V71_13)],
    )
    assert len(pairs) == 1
    assert [d.node_id for d in un_b] == ["CIP-007-7.1 R1 Part 1.3"]
    assert not un_a


def test_concepts_rooted_at_the_older_revision():
    pairs, _, un_b = pair_duties(
        [_duty("CIP-007-6 R2 Part 2.2", V6_22)],
        [_duty("CIP-007-7.1 R2 Part 2.2", V71_22), _duty("CIP-007-7.1 R1 Part 1.3", V71_13)],
    )
    concepts = assign_concepts(pairs, un_b)
    by_member = {m: c for c in concepts for m in c.members}
    same = by_member["CIP-007-6 R2 Part 2.2"]
    assert by_member["CIP-007-7.1 R2 Part 2.2"] is same
    assert "CIP-007-6 R2 Part 2.2" in same.label  # rooted at the -6 duty
    new_concept = by_member["CIP-007-7.1 R1 Part 1.3"]
    assert new_concept.concept_id != same.concept_id
    assert len(new_concept.members) == 1  # a genuinely new duty


def test_concept_id_stable_as_lineage_grows():
    """A future -8 pairing with the 7.1 duty joins the existing concept."""
    pairs1, _, _ = pair_duties(
        [_duty("CIP-007-6 R2 Part 2.2", V6_22)],
        [_duty("CIP-007-7.1 R2 Part 2.2", V71_22)],
    )
    first = assign_concepts(pairs1, [])
    prior = {m: c.concept_id for c in first for m in c.members}

    v8 = V71_22.replace("cyber security patches", "cyber security patches (v8)")
    pairs2, _, _ = pair_duties(
        [_duty("CIP-007-7.1 R2 Part 2.2", V71_22)],
        [_duty("CIP-007-8 R2 Part 2.2", v8)],
    )
    second = assign_concepts(pairs2, [], prior_concepts=prior)
    joined = next(c for c in second if "CIP-007-8 R2 Part 2.2" in c.members)
    assert joined.concept_id == prior["CIP-007-7.1 R2 Part 2.2"]
    assert joined.members == ["CIP-007-7.1 R2 Part 2.2", "CIP-007-8 R2 Part 2.2"]


def test_reassignment_conflict_raises():
    pairs, _, _ = pair_duties(
        [_duty("CIP-007-6 R2 Part 2.2", V6_22)],
        [_duty("CIP-007-7.1 R2 Part 2.2", V71_22)],
    )
    prior = {"CIP-007-7.1 R2 Part 2.2": "concept-from-somewhere-else"}
    with pytest.raises(ValueError, match="lineage conflict"):
        assign_concepts(pairs, [], prior_concepts=prior)


def test_derivation_recorded_on_every_concept():
    pairs, un_a, un_b = pair_duties(
        [_duty("CIP-007-6 R2 Part 2.2", V6_22)],
        [_duty("CIP-007-7.1 R1 Part 1.3", V71_13)],
    )
    assert len(pairs) == 0
    for concept in assign_concepts(pairs, un_a + un_b):
        assert concept.derivation == DERIVATION
        assert "threshold=0.75" in concept.derivation
