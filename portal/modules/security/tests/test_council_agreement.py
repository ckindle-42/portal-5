"""Tests for council_agreement.py — Part II-A (GATE-D ablation -> Council of Agreement)."""

from __future__ import annotations

from portal.modules.security.core.analyst_verdict import SectionOutput
from portal.modules.security.core.council_agreement import compute_agreement, to_section_output


def _member(verdict, technique_ids=None, similar_to=None):
    return SectionOutput(
        verdict=verdict,
        technique_ids=technique_ids or [],
        similar_to=similar_to or [],
        section="expert",
    )


def test_unanimous_confirmed():
    members = [
        _member("CONFIRMED", ["T1078"]),
        _member("CONFIRMED", ["T1078"]),
        _member("CONFIRMED", ["T1078"]),
    ]
    r = compute_agreement(members)
    assert r.verdict == "CONFIRMED"
    assert r.technique_ids == ["T1078"]
    assert r.agreement == 1.0
    assert not r.needs_arbiter


def test_quorum_met_subset_still_confirmed_with_correct_agreement():
    # 2 of 3 vote T1078 (>= 0.5 quorum); the 3rd votes something else entirely.
    members = [
        _member("CONFIRMED", ["T1078"]),
        _member("CONFIRMED", ["T1078"]),
        _member("CONFIRMED", ["T1055"]),
    ]
    r = compute_agreement(members, quorum=0.5)
    assert r.verdict == "CONFIRMED"
    assert r.technique_ids == ["T1078"]
    assert r.agreement == round(2 / 3, 3)
    assert r.dissent == {"T1078": 2, "T1055": 1}


def test_split_no_quorum_becomes_anomalous_unclassified_with_similar_to_union():
    # 3 concluders, 3 different techniques -> nobody reaches 0.5 quorum.
    members = [
        _member("CONFIRMED", ["T1078"], similar_to=["T1078.002"]),
        _member("CONFIRMED", ["T1055"], similar_to=["T1055.001"]),
        _member("ANOMALOUS_UNCLASSIFIED", ["T1548"], similar_to=["T1548.002"]),
    ]
    r = compute_agreement(members, quorum=0.5)
    assert r.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert r.needs_arbiter is True
    # I8: disagreement-as-novelty carries the union of near-miss neighbours, not nothing.
    assert r.similar_to == ["T1055.001", "T1078.002", "T1548.002"]
    assert set(r.dissent) == {"T1078", "T1055", "T1548"}


def test_unanimous_benign_ruled_out():
    members = [
        _member("RULED_OUT"),
        _member("RULED_OUT"),
        _member("RULED_OUT"),
    ]
    r = compute_agreement(members)
    assert r.verdict == "RULED_OUT"
    assert r.agreement == 1.0
    assert not r.needs_arbiter


def test_no_member_concludes_escalates_never_benign():
    """2026-07-23 design review: no member concluding is a budget/convergence
    FAILURE — it previously returned RULED_OUT, telling the SOC 'all clear'
    because the investigation never completed (the exact bug multichain's
    no-concluder branch escalates). Must surface as anomalous/escalate, with
    the arbiter (if configured) given a shot at a real conclusion."""
    members = [
        SectionOutput(verdict=None, request_more="need more data"),
        SectionOutput(verdict=None, request_more="need more data"),
    ]
    r = compute_agreement(members)
    assert r.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert r.needs_arbiter is True
    assert r.agreement == 0.0
    assert "no member reached a conclusion" in r.rationale


def test_mixed_benign_and_anomalous_without_technique_votes():
    members = [
        _member("RULED_OUT"),
        _member("ANOMALOUS_UNCLASSIFIED", similar_to=["T1548.002"]),
    ]
    r = compute_agreement(members)
    assert r.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert r.needs_arbiter is True
    assert r.similar_to == ["T1548.002"]


def test_confirmed_carries_technique_ids_for_downstream_cite_or_drop_gate():
    members = [_member("CONFIRMED", ["T1078", "T1055"]), _member("CONFIRMED", ["T1078", "T1055"])]
    r = compute_agreement(members)
    so = to_section_output(r)
    assert so.verdict == "CONFIRMED"
    assert so.technique_ids == ["T1055", "T1078"]  # sorted
    assert so.section == "agreement"


def test_anomalous_unclassified_section_output_carries_match_grade_similar():
    members = [
        _member("CONFIRMED", ["T1078"], similar_to=["T1078.002"]),
        _member("CONFIRMED", ["T1055"], similar_to=["T1055.001"]),
        _member("ANOMALOUS_UNCLASSIFIED", ["T1548"], similar_to=["T1548.002"]),
    ]
    r = compute_agreement(members, quorum=0.5)
    so = to_section_output(r)
    assert so.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert so.match_grade == "SIMILAR"
    assert so.similar_to


def test_ruled_out_section_output_has_none_match_grade():
    r = compute_agreement([_member("RULED_OUT"), _member("RULED_OUT")])
    so = to_section_output(r)
    assert so.verdict == "RULED_OUT"
    assert so.match_grade == "NONE"


def test_custom_quorum_threshold():
    # 1 of 3 (0.333) fails a 0.5 quorum but would pass a 0.3 quorum.
    members = [
        _member("CONFIRMED", ["T1078"]),
        _member("CONFIRMED", ["T1055"]),
        _member("CONFIRMED", ["T1548"]),
    ]
    r_strict = compute_agreement(members, quorum=0.5)
    assert r_strict.verdict == "ANOMALOUS_UNCLASSIFIED"
    r_loose = compute_agreement(members, quorum=0.3)
    assert r_loose.verdict == "CONFIRMED"
    assert set(r_loose.technique_ids) == {"T1078", "T1055", "T1548"}
