"""P6 the six operations — typed contracts, thin judge adapter, proposal re-judgment.

Hermetic: every model call is an injected ``seat_fn``; retrieval is bypassed by
injecting a pre-built :class:`AssessmentRequest`; no network or real Ollama.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.operations import (
    diff,
    norms,
    resolve,
    trace,
)
from portal.modules.compliance.core.policy_graph import build_policy_graph


@pytest.fixture(scope="module")
def g():
    return build_policy_graph()


def _scope():
    return AssetScope(
        impact_present={"high", "medium"},
        associated_present={"eacms", "pacs", "pca"},
        declared_by="operator:test",
    )


def test_resolve_current_attaches_premises_and_reference_closure(g):
    gs = resolve("CIP-007-6 R2 Part 2.2", valid_at="2026-09-06", scope=_scope(), policy_graph=g)
    assert gs.label == "current"
    assert gs.enforceable
    assert gs.actor_cus and gs.actor_cus[0]["cu"]
    assert "CIP-007-6 R2 Part 2.1" in gs.reference_closure
    assert any(p["id"] == "CIP-007-6 R2 Part 2.1" for p in gs.premises)


def test_resolve_before_effective_date_is_labelled_not_current(g):
    gs = resolve("CIP-003-9 R1", valid_at="2021-01-01", scope=_scope(), policy_graph=g)
    assert gs.label in {"future", "historical"}
    assert not gs.enforceable


def test_trace_discloses_frontier_at_budget(g):
    meta = next(n.id for n in g.nodes if n.node_type == "meta_cu")
    p = trace(meta, direction="both", depth=3, policy_graph=g, max_edges=3)
    assert p.budget_hit
    assert p.frontier
    assert set(p.frontier).isdisjoint(set(p.nodes) - set(p.frontier))


def test_diff_rows_carry_a_taxonomy_type():
    rows = diff("CIP-003-8", "CIP-003-9")
    assert rows
    assert all(r["taxonomy_type"] for r in rows)
    assert any(r["creates_review_work"] for r in rows)


def test_norms_direction_and_intent(g):
    prof = norms(
        "CIP-007-6 R2 Part 2.2",
        internal_quantities=[{"value": 21, "unit": "day"}],
        policy_graph=g,
        policy_decisions={},
    )
    assert prof.direction == "max_interval"
    assert prof.classification == "MORE_RESTRICTIVE"
    assert prof.intent["code"] == "U07_INTENT_UNKNOWN"
