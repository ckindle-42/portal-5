"""TASK_BULLY_INVESTIGATION_V1 (I.2): time-bounded, entity-scoped SPL.

A `PivotQuery`-shaped intent (the only kind that ever sets `entities`) must
produce SPL containing both bounds and the entity, and never `sourcetype=`.
An entity-scoped intent with no window is a defect, not a default.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully.connectors import QueryIntent
from portal.modules.security.core.bully.investigation_pivot import PivotQuery
from portal.modules.security.core.bully.live_connect import _search_from_intent


def _pivot_query(**overrides) -> PivotQuery:
    defaults = {
        "query_id": "q0-0",
        "index": "botsv3",
        "entity": "BSTOLL-L",
        "entity_kind": "host",
        "earliest": 1534737600.0,
        "latest": 1534824000.0,
        "depth": 0,
        "parent_query_id": None,
        "reason": "anchor_expansion:test",
    }
    defaults.update(overrides)
    return PivotQuery(**defaults)


def test_pivot_query_produces_bounded_entity_scoped_spl_with_no_sourcetype():
    q = _pivot_query()
    intent = QueryIntent(
        "investigate",
        seed={},
        start=q.earliest,
        end=q.latest,
        entities=(q.entity,),
    )
    expr = _search_from_intent(intent, index=q.index)
    assert expr["earliest"] == q.earliest
    assert expr["latest"] == q.latest
    assert q.entity in expr["search"]
    assert "sourcetype=" not in expr["search"].lower()
    assert "| head" not in expr["search"].lower()


def test_entity_scoped_intent_with_no_window_raises():
    intent = QueryIntent("investigate", seed={}, entities=("BSTOLL-L",))
    with pytest.raises(ValueError, match="earliest=0 is forbidden"):
        _search_from_intent(intent, index="botsv3")


def test_eventcount_pipe_command_remains_exempt_and_unbounded():
    intent = QueryIntent(
        "count telemetry for bed assessment",
        seed={"spl": "| eventcount summarize=false index=botsv3"},
        limit=1,
    )
    expr = _search_from_intent(intent, index="botsv3")
    assert expr["search"].startswith("|")
    assert expr["earliest"] == "0"
    assert expr["latest"] == "now"


def test_non_entity_intent_keeps_prior_default_unaffected():
    """Census/profile probes that predate the investigation engine (no
    `entities`) are out of this task's scope and must keep working."""
    intent = QueryIntent(
        "profile live indexed telemetry",
        seed={"spl": "search index=portal5_lab sourcetype=aws:cloudtrail"},
    )
    expr = _search_from_intent(intent, index="portal5_lab")
    assert expr["earliest"] == "0"
    assert expr["latest"] == "now"
