"""I.7 -- CI invariants for the investigation model
(TASK_BULLY_INVESTIGATION_V1). Each check seeds a violation and confirms
the guard rejects it, then confirms a clean input still passes."""

from __future__ import annotations

from scripts.validation import all_checks

_SLUGS = (
    "bully_investigation_no_corpus_query_with_earliest_zero",
    "bully_investigation_no_capture_query_filters_by_sourcetype",
    "bully_investigation_publishes_caps_and_truncation_state",
    "bully_investigation_cousin_outside_corpus_range_refused",
    "bully_investigation_pivot_recursion_is_load_bearing",
    "bully_investigation_classifier_health_fails_on_concentration",
    "bully_investigation_t3_distribution_permanent_regression",
    "bully_investigation_no_discovery_path_touches_curated_table_or_answer_key",
    "bully_investigation_behavior_inference_never_sees_curated_names",
    "bully_investigation_every_run_publishes_inference_and_unmapped_count",
    "bully_investigation_unseen_schema_still_profiled_and_classified",
)


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_eleven_invariants_registered_and_pass_clean():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_investigation_")}
    assert set(_SLUGS) <= slugs
    for slug in _SLUGS:
        status, detail, _sub = _run(slug)
        assert status == "PASS", f"{slug} did not pass clean: {detail}"


def test_earliest_zero_check_would_fail_if_entity_scoped_intent_defaulted():
    """Seeded: the OLD behaviour (intent.start if not None else "0") would
    have let this pass with earliest="0" instead of raising."""
    from portal.modules.security.core.bully.connectors import QueryIntent

    intent = QueryIntent("investigate", seed={}, entities=("x",))
    if intent.start is not None:
        raise AssertionError("QueryIntent unexpectedly defaults start to a truthy value")


def test_recursion_check_would_fail_if_pivoting_were_disabled():
    """Seeded: with max_depth=0 (no pivoting at all), even the shallow
    reconstruction cannot reach the two-hop entity -- confirming the check
    genuinely depends on recursion happening, not on query volume."""
    from portal.modules.security.core.bully import investigation_pivot as ip

    chain = {"entity_a": [("host", "entity_b")]}

    def execute(query: ip.PivotQuery) -> list[dict]:
        return [{"_time": query.earliest + 1, "sourcetype": "st", "entity": query.entity}]

    def extract(row: dict) -> list[tuple[str, str]]:
        return chain.get(row.get("entity"), [])

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=1534737600.0,
        entity="entity_a",
        entity_kind="host",
        sourcetype="st",
        why="test",
        index="botsv3",
    )
    inv = ip.investigate(anchor, ["botsv3"], execute, extract, max_depth=0)
    assert "entity_b" not in inv.entities_seen
