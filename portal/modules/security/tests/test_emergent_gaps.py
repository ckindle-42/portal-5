"""Slice 3.1: emergent miss -> RED_ONLY Gap; synthetic misses excluded."""

from __future__ import annotations

from portal.modules.security.core.capability_graph import CapabilityGraph
from portal.modules.security.core.emergent_gaps import feed_emergent_gaps, gaps_from_trajectory
from portal.modules.security.core.growth_loop import run_growth_loop
from portal.modules.security.core.trajectory_score import StepRecord, TrajectoryVerdict


def _v(steps):
    return TrajectoryVerdict(
        objective_class="da_equivalent",
        verdict="FAILED",
        objective_reached=False,
        synthetic_present=any(s.used_synthetic for s in steps),
        landed_steps=len(steps),
        steps=steps,
    )


def test_landed_undetected_becomes_red_only_gap():
    steps = [StepRecord("s1", "kerberoast", "RED_LANDED", "DETECTION_NO_HIT")]
    gaps = gaps_from_trajectory(_v(steps), trajectory_id="t1")
    assert len(gaps) == 1
    assert gaps[0].summary == "RED_ONLY"
    assert gaps[0].axes["detection"] == "DETECTION_NO_HIT"


def test_detected_step_yields_no_gap():
    steps = [StepRecord("s1", "kerberoast", "RED_LANDED", "DETECTION_CONFIRMED")]
    assert gaps_from_trajectory(_v(steps), trajectory_id="t1") == []


def test_synthetic_miss_excluded():
    steps = [StepRecord("s1", "kerberoast", "RED_LANDED", "DETECTION_MISSING", used_synthetic=True)]
    assert gaps_from_trajectory(_v(steps), trajectory_id="t1") == []


def test_gap_ids_unique_per_step():
    steps = [
        StepRecord("s1", "capA", "RED_LANDED", "DETECTION_NO_HIT"),
        StepRecord("s2", "capB", "RED_LANDED", "DETECTION_MISSING"),
    ]
    gaps = gaps_from_trajectory(_v(steps), trajectory_id="t7")
    assert len({g.gap_id for g in gaps}) == 2


def test_feed_emergent_gaps_makes_run_growth_loop_see_them():
    """The wiring: feed_emergent_gaps populates graph.gaps the same way the
    scripted RED_ONLY feed does, so run_growth_loop (unchanged, no gap-list
    param) picks emergent misses up as a first-class gap source."""
    graph = CapabilityGraph()
    steps = [StepRecord("s1", "kerberoast", "RED_LANDED", "DETECTION_NO_HIT")]
    fed = feed_emergent_gaps(graph, _v(steps), trajectory_id="t1")

    assert len(fed) == 1
    assert fed[0].gap_id in graph.gaps

    result = run_growth_loop(graph, dry_run=True)
    assert result.gaps_found == 1
    assert result.drafts_proposed == 1
