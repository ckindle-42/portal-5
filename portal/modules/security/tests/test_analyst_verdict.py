"""Tests for analyst_verdict.py — BUILD_PROGRAM_SEC_BLUE_ORCHESTRATION_V2 Slice 1."""

from __future__ import annotations

from portal.modules.security.core.analyst_verdict import (
    ANALYST_REACHABLE,
    ANALYST_VERDICTS,
    MATCH_GRADES,
    ORCHESTRATOR_ONLY,
    SectionOutput,
    is_terminal,
    validate_output,
)
from portal.modules.security.core.episode import CAPABILITY_VERDICTS
from portal.modules.security.core.unknown_defense import MatchGrade


def test_verdict_axis_disjoint_from_capability_verdicts():
    assert set(ANALYST_VERDICTS).isdisjoint(set(CAPABILITY_VERDICTS))


def test_match_grades_mirrors_unknown_defense_matchgrade():
    assert set(MATCH_GRADES) == {MatchGrade.EXACT, MatchGrade.SIMILAR, MatchGrade.NONE}


def test_reachable_and_orchestrator_only_partition_all_verdicts():
    assert set(ANALYST_REACHABLE) | set(ORCHESTRATOR_ONLY) == set(ANALYST_VERDICTS)
    assert set(ANALYST_REACHABLE).isdisjoint(set(ORCHESTRATOR_ONLY))


def test_similar_match_grade_requires_similar_to():
    out = SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        reasoning="looks like a variant",
        match_grade="SIMILAR",
        similar_to=[],
    )
    ok, msg = validate_output(out)
    assert not ok
    assert "similar_to" in msg


def test_similar_variant_maps_to_anomalous_unclassified_not_confirmed():
    out = SectionOutput(
        verdict="ANOMALOUS_UNCLASSIFIED",
        reasoning="closest known technique is T1558.003 but timing/host pattern differs",
        match_grade="SIMILAR",
        similar_to=["T1558.003"],
    )
    ok, msg = validate_output(out)
    assert ok, msg
    assert out.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert out.is_conclusion()


def test_confirmed_requires_technique_ids():
    out = SectionOutput(verdict="CONFIRMED", evidence=["log line 1"])
    ok, msg = validate_output(out)
    assert not ok
    assert "technique_id" in msg


def test_confirmed_with_technique_ids_and_evidence_is_valid():
    out = SectionOutput(verdict="CONFIRMED", technique_ids=["T1558.003"], evidence=["log line 1"])
    ok, msg = validate_output(out)
    assert ok, msg


def test_request_more_without_verdict_is_valid_and_wants_more():
    out = SectionOutput(request_more="need auth logs for host X in last 15m")
    ok, msg = validate_output(out)
    assert ok, msg
    assert out.wants_more()
    assert not out.is_conclusion()


def test_neither_verdict_nor_request_more_is_invalid():
    out = SectionOutput()
    ok, msg = validate_output(out)
    assert not ok


def test_bad_match_grade_rejected():
    out = SectionOutput(request_more="x", match_grade="MAYBE")
    ok, msg = validate_output(out)
    assert not ok
    assert "match_grade" in msg


def test_unresolved_is_orchestrator_only_not_analyst_reachable():
    assert "UNRESOLVED" in ORCHESTRATOR_ONLY
    assert "UNRESOLVED" not in ANALYST_REACHABLE
    assert is_terminal("UNRESOLVED")
