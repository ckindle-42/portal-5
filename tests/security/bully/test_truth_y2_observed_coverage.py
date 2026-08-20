"""Y.2 -- an alignment must explain the OBSERVED series, not merely be
findable inside it. Reproduction of D3 (TASK_BULLY_TRUTH_ACCEPTANCE_V1):
scoring the alignment only against the KNOWN side let a long, mostly-noise
timeline "contain" a short technique, and an absolute distinct-class gate let
`auth + Nx execute` clear trivially. See docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md.
"""

from __future__ import annotations

from portal.modules.security.core.bully.series_cousin import (
    BehaviouralSeries,
    decide_cousin,
)


def _series(sid, spine, technique=None):
    return BehaviouralSeries(
        series_id=sid, spine=tuple(spine), n_logs=len(spine), technique=technique
    )


KNOWN = _series("known-1", ["auth", "enumerate", "execute"], technique="T1078")

# 14-step timeline, 71% noise (10 of 14 steps), with the known technique's
# classes appearing in order but diluted -- D3's reproduction shape.
NOISY_BACKGROUND = _series(
    "obs-noisy",
    [
        "collect",
        "persist",
        "collect",
        "persist",
        "auth",
        "collect",
        "persist",
        "execute",
        "collect",
        "persist",
        "execute",
        "collect",
        "persist",
        "collect",
    ],
)

EXEC_X14 = _series("obs-exec14", ["execute"] * 14)
AUTH_PLUS_EXEC_X13 = _series("obs-ae13", ["auth"] + ["execute"] * 13)


def test_noisy_background_timeline_grades_novel_not_cousin() -> None:
    result = decide_cousin(NOISY_BACKGROUND, [KNOWN])
    assert result.relation != "COUSIN"


def test_execute_repeated_grades_novel() -> None:
    result = decide_cousin(EXEC_X14, [KNOWN])
    assert result.relation != "COUSIN"


def test_auth_plus_execute_x13_grades_novel_not_cousin() -> None:
    """Old absolute `distinct_aligned >= 2` gate cleared trivially on 2
    distinct classes diluted across 14 aligned steps; the ratio gate must
    catch it."""
    result = decide_cousin(AUTH_PLUS_EXEC_X13, [KNOWN])
    assert result.relation != "COUSIN"


def test_genuine_matches_preserved() -> None:
    exact_observed = _series("obs-exact", ["auth", "enumerate", "execute"])
    assert decide_cousin(exact_observed, [KNOWN]).relation == "EXACT"

    one_swap = _series("obs-swap", ["auth", "persist", "execute"])
    assert decide_cousin(one_swap, [KNOWN]).relation == "COUSIN"

    one_insert = _series("obs-insert", ["auth", "enumerate", "collect", "execute"])
    assert decide_cousin(one_insert, [KNOWN]).relation == "COUSIN"


def test_seeded_violation_reverting_coverage_gate_reintroduces_false_cousin() -> None:
    """Seeded regression: with `min_observed_coverage=0.0` (D3's original
    bug -- scoring only against the KNOWN side), the noisy background
    timeline grades COUSIN again."""
    reverted = decide_cousin(
        AUTH_PLUS_EXEC_X13, [KNOWN], min_observed_coverage=0.0, min_distinct_ratio=0.0
    )
    assert reverted.relation == "COUSIN"


def test_seeded_violation_reverting_distinct_ratio_gate_reintroduces_false_cousin() -> None:
    """Isolates the distinct-ratio gate: high observed coverage (0.78) but a
    diluted 2-distinct-class backbone (0.29 ratio) grades NOVEL by default and
    COUSIN with the ratio gate reverted -- the old absolute `>=2` gate would
    have cleared this trivially."""
    known_repeats = _series("known-repeats", ["auth"] + ["execute"] * 6, technique="T1078")
    observed = _series("obs-repeats", ["auth"] + ["execute"] * 8)
    assert decide_cousin(observed, [known_repeats]).relation != "COUSIN"
    reverted = decide_cousin(observed, [known_repeats], min_distinct_ratio=0.0)
    assert reverted.relation == "COUSIN"
