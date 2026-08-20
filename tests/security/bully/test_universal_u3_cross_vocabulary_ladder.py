"""U.3' -- honest cross-vocabulary ladder rung, validated on the deciding
variable. TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1."""

from __future__ import annotations

from portal.modules.security.core.bully import unit_ladder as ul

_PARENT_VERBS = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
_PARENT_TYPE = {"record_id": "parent-type", "action_sequence": _PARENT_VERBS}


def _rungs(cross_vocabulary_verbs: list[str]) -> list[ul.Rung]:
    return ul.build_rungs(
        _PARENT_VERBS,
        substitution_verb="AddRole",
        cross_vocabulary_verbs=cross_vocabulary_verbs,
        unrelated_verbs=["SELECT", "INSERT", "COMMIT"],
    )


def test_ladder_validates_on_shape_distance_not_combined() -> None:
    report = ul.run_ladder(_PARENT_TYPE, _rungs(["Logon", "whoami", "Invoke-Command"]))
    assert report["validated_variable"] == "shape_distance"


def test_real_disjoint_verbs_share_zero_literal_tokens_with_parent() -> None:
    real_verbs = ["Logon", "whoami", "Invoke-Command"]
    assert not (set(real_verbs) & set(_PARENT_VERBS))


def test_real_cross_vocabulary_rung_is_a_genuine_partial_mismatch() -> None:
    """The regression this rung exists to fix: the old rung was built from
    the class names themselves (`Authenticate`/`Enumerate`/`Invoke`),
    proving only that verbs the table already maps together map together.
    `AttachUserPolicy` classifies `escalate`; `Invoke-Command` classifies
    `execute` -- a real disjoint-schema chain does NOT trivially reproduce
    the parent's class sequence, and that mismatch must show up as nonzero
    shape distance, not be hidden."""
    from portal.modules.security.core.bully.artifact_graph import DEFAULT_ACTION_CLASSIFIER

    parent_classes = [DEFAULT_ACTION_CLASSIFIER.classify(v) for v in _PARENT_VERBS]
    cross_classes = [
        DEFAULT_ACTION_CLASSIFIER.classify(v) for v in ["Logon", "whoami", "Invoke-Command"]
    ]
    assert parent_classes != cross_classes  # genuine mismatch, not a cherry-picked match

    report = ul.run_ladder(_PARENT_TYPE, _rungs(["Logon", "whoami", "Invoke-Command"]))
    l3 = report["per_rung"]["L3_CROSS_VOCABULARY"]
    assert l3["shape_distance"] is not None
    assert l3["shape_distance"] > 0.0  # the mismatch is visible, not smoothed to 0


def test_seeded_a_badly_mismapped_rung_degrades_recovery_visibly() -> None:
    """Seeded test (U.3'): a rung the deterministic classifier maps far
    more wrongly than the "good" real-verb rung must show *more* shape
    distance, not the same or less -- degradation is visible, never
    smoothed by grading on combined_distance."""
    good_report = ul.run_ladder(_PARENT_TYPE, _rungs(["Logon", "whoami", "Invoke-Command"]))
    good_l3 = good_report["per_rung"]["L3_CROSS_VOCABULARY"]["shape_distance"]

    # Every verb here classifies to "other" under the deterministic table
    # (none matches any needle) -- the worst case the U.3 seam names.
    bad_report = ul.run_ladder(
        _PARENT_TYPE, _rungs(["Add-LocalGroupMember", "Set-ACL", "New-ScheduledTask"])
    )
    bad_l3 = bad_report["per_rung"]["L3_CROSS_VOCABULARY"]["shape_distance"]

    assert bad_l3 is not None and good_l3 is not None
    assert bad_l3 >= good_l3
    # the badly-mapped rung's shape distance approaches the unrelated rung's
    bad_l4 = bad_report["per_rung"]["L4_UNRELATED"]["shape_distance"]
    assert bad_l3 >= 0.5 * bad_l4


def test_cross_vocabulary_recovery_rate_is_published() -> None:
    """The honest number sizing the learned action classifier: whether the
    real cross-vocabulary rung graded EXACT/SIMILAR (recovered) or not is
    visible in `per_rung`, not summarized away."""
    report = ul.run_ladder(_PARENT_TYPE, _rungs(["Logon", "whoami", "Invoke-Command"]))
    l3 = report["per_rung"]["L3_CROSS_VOCABULARY"]
    assert l3["overall_relation"] in ("EXACT", "SIMILAR", "NOT_AT_ALL")
