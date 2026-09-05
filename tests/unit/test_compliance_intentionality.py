"""TASK_COMPLIANCE_REASONING_V2 — Q08/Q09 (intentionality, flexibility)."""

from __future__ import annotations

from portal.modules.compliance.core.constraints import infer_constraint_kind
from portal.modules.compliance.core.intentionality import (
    assess_intentionality,
    find_flexibility,
)


def test_infer_constraint_kind_retention_cue():
    assert infer_constraint_kind("retain records for at least 90 calendar days") == "min_retention"


def test_infer_constraint_kind_interval_cue():
    assert (
        infer_constraint_kind("evaluate patches at least once every 35 calendar days")
        == "max_interval"
    )


def test_infer_constraint_kind_no_cue_returns_none():
    assert infer_constraint_kind("the number 42 appears here for no reason") is None


def test_assess_intentionality_stricter_interval_is_more_restrictive():
    governing = "At least once every 35 calendar days, evaluate security patches."
    internal = "We evaluate security patches at least once every 21 calendar days."
    result = assess_intentionality(governing, internal)
    assert len(result["comparisons"]) == 1
    comp = result["comparisons"][0]
    assert comp["result"] == "MORE_RESTRICTIVE"
    assert comp["kind"] == "max_interval"


def test_assess_intentionality_looser_retention_is_less_restrictive():
    governing = "Retain records for at least 90 calendar days."
    internal = "We retain records for at least 60 calendar days."
    result = assess_intentionality(governing, internal)
    comp = result["comparisons"][0]
    assert comp["result"] == "LESS_RESTRICTIVE"
    assert comp["kind"] == "min_retention"


def test_assess_intentionality_different_units_are_incomparable():
    governing = "Retain records for at least 90 calendar days."
    internal = "We retain records for at least 3 calendar months."
    result = assess_intentionality(governing, internal)
    comp = result["comparisons"][0]
    assert comp["result"] == "no_comparable_governing_claim"


def test_assess_intentionality_never_defaults_kind():
    governing = "The count is 90 calendar days as stated here."
    internal = "The count is 60 calendar days as stated here too."
    result = assess_intentionality(governing, internal)
    comp = result["comparisons"][0]
    assert comp["result"] == "kind_undetermined"


def test_find_flexibility_detects_may_alternative():
    governing = "The entity shall evaluate patches. Alternatively, the entity may use a compensating measure."
    result = find_flexibility(governing)
    assert len(result["candidate_alternatives"]) == 1
    assert "may use a compensating measure" in result["candidate_alternatives"][0]


def test_find_flexibility_no_alternative_found():
    governing = "The entity shall evaluate patches within 35 calendar days."
    result = find_flexibility(governing)
    assert result["candidate_alternatives"] == []
