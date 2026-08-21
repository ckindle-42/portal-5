"""A.7 -- CI invariants for adaptive reach (TASK_BULLY_ADAPTIVE_REACH_V1).
Each check seeds the exact I.6 defect it closes and confirms the guard
rejects it, then confirms a clean/control input still passes."""

from __future__ import annotations

from scripts.validation import all_checks

_SLUGS = (
    "bully_adaptive_reach_no_flat_event_cap_a_depth_budget_is_required",
    "bully_adaptive_reach_saturation_narrows_rather_than_terminating",
    "bully_adaptive_reach_every_investigation_publishes_pivot_ran",
    "bully_adaptive_reach_reach_report_refuses_single_entity_expectation",
    "bully_adaptive_reach_recovery_published_by_distance_zero_hop_flagged",
    "bully_adaptive_reach_zero_scored_units_forces_is_haystack_false",
    "bully_adaptive_reach_i6_density_profile_permanent_regression",
)


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_seven_invariants_registered_and_pass_clean():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_adaptive_reach_")}
    assert set(_SLUGS) <= slugs
    for slug in _SLUGS:
        status, detail, _sub = _run(slug)
        assert status == "PASS", f"{slug} did not pass clean: {detail}"
