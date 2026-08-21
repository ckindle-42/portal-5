"""TASK_BULLY_ADAPTIVE_REACH_V1 (A.3): `reach_report` must test a CHAIN.

I.6 scored every truth-targeted anchor against a single-entity expectation
-- the anchor's own entity -- and published `reach_recall 1.0` on all four.
That confirms the anchor query found its own entity; it is not evidence a
pivot reached anything. A degenerate expectation is now refused.
"""

from __future__ import annotations

from portal.modules.security.core.bully import investigation_pivot as ip


def _investigation_with(entities_seen: dict[str, str], anchor_entity: str) -> ip.Investigation:
    anchor = ip.Anchor(
        anchor_id="a-truth-T1558.004",
        at=1534737600.0,
        entity=anchor_entity,
        entity_kind="host",
        sourcetype="WinEventLog",
        why="answer_key:T1558.004",
        index="botsv3",
    )
    inv = ip.Investigation(anchor=anchor)
    inv.entities_seen.update(entities_seen)
    return inv


def test_i6_single_entity_expectation_yields_none_and_reason():
    """I.6's exact shape: expected_stage_entities=(anchor's own entity,)."""
    inv = _investigation_with({"BGIST-L": "host"}, anchor_entity="BGIST-L")
    report = ip.reach_report(inv, ["BGIST-L"])
    assert report.reach_recall is None
    assert report.degenerate_expectation == "fewer_than_two_expected_stage_entities:1"


def test_single_entity_that_is_not_even_the_anchor_is_still_degenerate():
    inv = _investigation_with({"BGIST-L": "host", "web_admin": "user"}, anchor_entity="BGIST-L")
    report = ip.reach_report(inv, ["web_admin"])
    assert report.reach_recall is None
    assert report.degenerate_expectation == "fewer_than_two_expected_stage_entities:1"


def test_empty_expectation_is_degenerate():
    inv = _investigation_with({"BGIST-L": "host"}, anchor_entity="BGIST-L")
    report = ip.reach_report(inv, [])
    assert report.reach_recall is None
    assert report.degenerate_expectation == "fewer_than_two_expected_stage_entities:0"


def test_multi_entity_chain_scores_normally_and_is_not_degenerate():
    inv = _investigation_with(
        {"BSTOLL-L": "host", "bstoll": "user", "web_admin": "user"},
        anchor_entity="BSTOLL-L",
    )
    report = ip.reach_report(inv, ["BSTOLL-L", "bstoll", "web_admin", "null_admin"])
    assert report.degenerate_expectation is None
    assert report.reach_recall == 0.75
    assert report.missed == ("null_admin",)


def test_multi_entity_expectation_that_is_entirely_the_anchor_repeated_is_still_degenerate():
    # set(expected) collapses to {anchor.entity} even if the tuple has len>=2
    inv = _investigation_with({"BGIST-L": "host"}, anchor_entity="BGIST-L")
    report = ip.reach_report(inv, ["BGIST-L", "BGIST-L"])
    assert report.reach_recall is None
    assert report.degenerate_expectation == "expectation_is_anchor_only:BGIST-L"
