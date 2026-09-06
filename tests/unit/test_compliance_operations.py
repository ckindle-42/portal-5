"""P6 the six operations — typed contracts, gate-before-council, propose re-judges."""

from __future__ import annotations

import json

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.operations import (
    diff,
    judge,
    norms,
    propose,
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


_SEATS = [{"id": f"s{i}", "label": str(i), "model": f"m{i}"} for i in range(3)]


def _fake_support():
    def fn(model, system, user):
        if "checking one thing only" in system:
            return '{"overrides": false, "exception_ref": null}'
        return json.dumps(
            {
                "determination": "SUPPORTED",
                "cited_refs": ["CIP-007-6 R2 Part 2.2"],
                "rationale": "ok",
            }
        )

    return fn


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
    assert p.frontier  # nodes reached at the cutoff, disclosed not silently truncated
    assert set(p.frontier).isdisjoint(set(p.nodes) - set(p.frontier))


def test_judge_runs_gate_before_council(g):
    d = judge(
        "CIP-007-6 R2 Part 2.2",
        scope=_scope(),
        org_commitments=[
            {
                "commitment_id": "c1",
                "document_id": "spm",
                "standard_folder": "CIP-007",
                "actor": "OT Security Team",
                "text": "OT Security evaluates patches for applicability every 21 calendar days.",
            }
        ],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_fake_support(),
    )
    assert d.determination == "SUPPORTED"
    assert not d.gate_gated_out
    assert d.council_votes["SUPPORTED"] == 3


def test_judge_gates_out_of_scope_cu_without_calling_council(g):
    called = []

    def fn(model, system, user):
        called.append(model)
        return "{}"

    hm_only = next(
        n
        for n in g.nodes
        if n.node_type == "actor_cu"
        and "High Impact" in n.applicable_systems
        and "low impact" not in n.applicable_systems
    )
    d = judge(
        hm_only.id,
        scope=AssetScope(impact_present={"low"}, declared_by="operator:test"),
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=fn,
    )
    assert d.determination == "NOT_APPLICABLE"
    assert d.gate_gated_out
    assert called == []  # council never invoked on a gated-out CU


def test_propose_rejudges_its_own_output(g):
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["constraint"],
        "The OT Security Team shall evaluate security patches for applicability every 21 calendar days.",
        scope=_scope(),
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_fake_support(),
    )
    assert pkg.status == "proposed"
    assert pkg.rejudged is not None
    assert pkg.rejudged.determination == "SUPPORTED"
    assert pkg.closes_fields == ["constraint"]
    assert pkg.weakens == []


def test_propose_reports_a_non_closing_draft(g):
    def fn(model, system, user):
        if "checking one thing only" in system:
            return '{"overrides": false}'
        return json.dumps(
            {
                "determination": "PARTIAL",
                "finding_type": "WEAK_MAPPING",
                "cited_refs": ["CIP-007-6 R2 Part 2.2"],
                "rationale": "still short",
            }
        )

    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["constraint"],
        "We will look at patches sometimes.",
        scope=_scope(),
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=fn,
    )
    assert pkg.closes_fields == []
    assert pkg.weakens and "does not close" in pkg.weakens[0]


def test_diff_rows_carry_a_taxonomy_type():
    rows = diff("CIP-003-8", "CIP-003-9")
    assert rows
    assert all(
        r["taxonomy_type"]
        in {
            "NEW_DUTY",
            "TIGHTENED",
            "RELAXED",
            "SCOPE_CHANGE",
            "RECORDKEEPING_CHANGE",
            "EVIDENCE_CHANGE",
            "DEFINITION_CHANGE",
            "REFERENCE_CHANGE",
            "RENUMBER_ONLY",
            "EDITORIAL_ONLY",
        }
        for r in rows
    )
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
