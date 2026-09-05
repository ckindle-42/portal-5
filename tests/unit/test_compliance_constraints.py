"""TASK_COMPLIANCE_REASONING_V2 P5.3 — typed constraint comparison with
comparator direction (design §6.2: "A shorter maximum deadline can be
stricter, while a shorter minimum retention period can be weaker").
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.constraints import Quantity, compare_constraint


def test_max_interval_shorter_internal_is_more_restrictive():
    """ "review at least once every 15 calendar months" (governing) vs an
    internal procedure requiring it every 12 months — doing it MORE often is
    stricter for a maximum-interval obligation."""
    governing = Quantity(15, "month", "calendar")
    internal = Quantity(12, "month", "calendar")
    result, reason = compare_constraint("max_interval", governing, internal)
    assert result == "MORE_RESTRICTIVE"
    assert "stricter" in reason


def test_max_interval_longer_internal_is_less_restrictive():
    governing = Quantity(15, "month", "calendar")
    internal = Quantity(18, "month", "calendar")
    result, _ = compare_constraint("max_interval", governing, internal)
    assert result == "LESS_RESTRICTIVE"


def test_min_retention_longer_internal_is_more_restrictive():
    """ "retain records for at least 3 years" (governing) vs an internal
    policy retaining for 5 years — keeping it LONGER is stricter for a
    minimum-retention obligation (the OPPOSITE direction from max_interval)."""
    governing = Quantity(3, "year", "calendar")
    internal = Quantity(5, "year", "calendar")
    result, reason = compare_constraint("min_retention", governing, internal)
    assert result == "MORE_RESTRICTIVE"
    assert "stricter" in reason


def test_min_retention_shorter_internal_is_less_restrictive():
    governing = Quantity(3, "year", "calendar")
    internal = Quantity(1, "year", "calendar")
    result, _ = compare_constraint("min_retention", governing, internal)
    assert result == "LESS_RESTRICTIVE"


def test_equal_values_are_equivalent():
    governing = Quantity(30, "day", "calendar")
    internal = Quantity(30, "day", "calendar")
    result, _ = compare_constraint("max_interval", governing, internal)
    assert result == "EQUIVALENT"


def test_different_units_are_incomparable_never_converted():
    """F05: a calendar month is not a fixed day count — never silently
    converted to compare across units."""
    governing = Quantity(1, "month", "calendar")
    internal = Quantity(30, "day", "calendar")
    result, reason = compare_constraint("max_interval", governing, internal)
    assert result == "INCOMPARABLE"
    assert "no reviewed conversion rule" in reason


def test_different_qualifiers_are_incomparable():
    """A business-day count is not a calendar-day count (F05)."""
    governing = Quantity(30, "day", "calendar")
    internal = Quantity(30, "day", "business")
    result, _ = compare_constraint("max_interval", governing, internal)
    assert result == "INCOMPARABLE"


def test_bare_qualifier_none_is_treated_as_calendar():
    """An unstated qualifier is the ordinary calendar reading (same
    normalization tiers.py uses) — "18 months" and "15 calendar months" ARE
    comparable."""
    governing = Quantity(15, "month", "calendar")
    internal = Quantity(18, "month", None)
    result, _ = compare_constraint("max_interval", governing, internal)
    assert result == "LESS_RESTRICTIVE"


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="kind must be"):
        compare_constraint("not_a_kind", Quantity(1, "day"), Quantity(1, "day"))
