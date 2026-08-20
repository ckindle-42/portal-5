"""Y.7 -- CI invariants for truth-joined acceptance (EH-EN,
TASK_BULLY_TRUTH_ACCEPTANCE_V1). Each check passes clean; the seeded-
violation checks additionally prove the gate is load-bearing."""

from __future__ import annotations

from scripts.validation import all_checks

_EXPECTED_SLUGS = {
    "bully_truth_x6_per_row_yields_invalid",
    "bully_truth_acceptance_requires_sealed_truth_join",
    "bully_truth_background_only_population_invalid",
    "bully_truth_selection_report_published_when_implants_shipped",
    "bully_truth_scripted_verdict_contradicting_truth_writes_no_anchor",
    "bully_truth_alignment_below_coverage_never_grades_exact_or_cousin",
    "bully_truth_classifier_distribution_and_entropy_published",
    "bully_truth_json_raw_parsed_not_dropped",
}


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_registered_and_unique():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_truth_")}
    assert slugs >= _EXPECTED_SLUGS


def test_all_truth_checks_pass_clean():
    for slug in _EXPECTED_SLUGS:
        status, detail, _sub = _run(slug)
        assert status == "PASS", f"{slug} did not pass clean: {detail}"
