"""TASK_COMPLIANCE_REASONING_V2 P3 §8 — four-state applicability (F07).

``applicability_state`` is new additive capability alongside the unchanged
legacy ``applicable()`` two-state gate (see that function's docstring for why
it is deliberately NOT rewired onto this yet). These tests cover both: the
new four-state semantics, and that ``applicable()``'s live-gate behavior is
provably unchanged for every case it already handled.
"""

from __future__ import annotations

from portal.modules.compliance.core.applicability import (
    AssetScope,
    applicability_state,
    applicable,
)

_CONFIRMED_HIGH = AssetScope(
    impact_present={"high"},
    associated_present={"bcs", "eacms"},
    declared_by="op",
    declared_at="2026-01-01",
)
_CONFIRMED_MEDIUM_ERC_UNKNOWN = AssetScope(
    impact_present={"medium"},
    associated_present={"bcs"},
    has_erc=None,
    has_control_center=None,
    declared_by="op",
    declared_at="2026-01-01",
)
_DERIVED_CANDIDATE = AssetScope(
    impact_present={"high"},
    associated_present={"bcs"},
    has_erc=None,
    has_control_center=None,
    declared_by="derived:corpus",
    declared_at="2026-01-01",
)
_UNDECLARED = AssetScope()
_CONFLICTED = AssetScope(
    impact_present={"high"}, declared_by="op", declared_at="2026-01-01", conflicted=True
)


def test_undeclared_scope_is_unknown_not_excluded():
    state, _ = applicability_state("High Impact BES Cyber Systems", _UNDECLARED)
    assert state == "UNKNOWN"


def test_conflicted_scope_is_its_own_state():
    state, reason = applicability_state("High Impact BES Cyber Systems", _CONFLICTED)
    assert state == "CONFLICTED"
    assert "contradictory" in reason


def test_corpus_derived_candidate_is_unknown_not_promoted_to_applies():
    """The exact F07 fix: a scope the system inferred from corpus mentions is
    a CANDIDATE, never an approved declaration — it must not silently become
    APPLIES."""
    state, reason = applicability_state("High Impact BES Cyber Systems", _DERIVED_CANDIDATE)
    assert state == "UNKNOWN"
    assert "CANDIDATE" in reason


def test_confirmed_operator_scope_applies_normally():
    state, _ = applicability_state("High Impact BES Cyber Systems", _CONFIRMED_HIGH)
    assert state == "APPLIES"


def test_confirmed_scope_out_of_impact_range_does_not_apply():
    state, reason = applicability_state("Low Impact BES Cyber Systems", _CONFIRMED_HIGH)
    assert state == "DOES_NOT_APPLY"
    assert "high" in reason


def test_blank_applicable_systems_text_is_unknown_not_defaulted():
    """F07's second half: a blank cell must not silently become "applies to
    high+medium" — that is unparsed extraction, not a scope fact."""
    state, reason = applicability_state("", _CONFIRMED_HIGH)
    assert state == "UNKNOWN"
    assert "blank" in reason.lower()


def test_unconfirmed_erc_on_medium_only_part_is_unknown_not_excluded_or_included():
    state, reason = applicability_state(
        "Medium Impact BES Cyber Systems with External Routable Connectivity",
        _CONFIRMED_MEDIUM_ERC_UNKNOWN,
    )
    assert state == "UNKNOWN"
    assert "ERC" in reason


def test_confirmed_no_erc_on_medium_only_part_does_not_apply():
    scope = AssetScope(
        impact_present={"medium"}, has_erc=False, declared_by="op", declared_at="2026-01-01"
    )
    state, _ = applicability_state(
        "Medium Impact BES Cyber Systems with External Routable Connectivity", scope
    )
    assert state == "DOES_NOT_APPLY"


def test_high_impact_entity_applies_to_high_and_medium_part_regardless_of_erc():
    """An entity with a High Impact system is in scope for a High+Medium Part
    regardless of Medium-only ERC qualifiers (the qualifier only gates the
    Medium-only path)."""
    scope = AssetScope(
        impact_present={"high"}, has_erc=None, declared_by="op", declared_at="2026-01-01"
    )
    state, _ = applicability_state(
        "High Impact and Medium Impact BES Cyber Systems with External Routable Connectivity",
        scope,
    )
    assert state == "APPLIES"


# ── legacy `applicable()` is provably unchanged ─────────────────────────────
def test_legacy_applicable_still_true_for_ordinary_confirmed_scope():
    applies, _ = applicable("High Impact BES Cyber Systems", _CONFIRMED_HIGH)
    assert applies is True


def test_legacy_applicable_still_false_for_out_of_range_impact():
    applies, _ = applicable("Low Impact BES Cyber Systems", _CONFIRMED_HIGH)
    assert applies is False


def test_legacy_applicable_treats_unconfirmed_erc_as_inclusive_not_excluding():
    """`applicable()` documents "absence of evidence never excludes"; an
    unconfirmed (``None``) ERC status must stay inclusive there, unlike the
    new four-state function which correctly reports it as UNKNOWN."""
    applies, _ = applicable(
        "Medium Impact BES Cyber Systems with External Routable Connectivity",
        _CONFIRMED_MEDIUM_ERC_UNKNOWN,
    )
    assert applies is True


def test_legacy_applicable_derived_candidate_still_applies_unchanged():
    """The pre-existing production gate is deliberately NOT rewired onto the
    four-state confirmation check yet (see applicable()'s docstring) — a
    corpus-derived scope still passes it exactly as before."""
    applies, _ = applicable("High Impact BES Cyber Systems", _DERIVED_CANDIDATE)
    assert applies is True
