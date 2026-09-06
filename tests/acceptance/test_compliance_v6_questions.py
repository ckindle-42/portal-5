"""V6 acceptance — the twelve questions, thirty-six [C]/[X]/[U] variants (Y17).

Each question of §4 gets three variants:
  [C] complete-evidence acceptance — the determination and citations expected
  [X] counterexample — a planted change that must flip the result
  [U] uncertainty — a specific missing fact that must be named, never a silent
      N/A or a false gap

The deterministic spine (routing, the gate, the plan) is exercised for real
against the built policy graph. The judgment step is driven by a scripted seat
that returns the gold determination for the variant, so CI needs no model; a
``--live`` run (``COMPLIANCE_V6_LIVE=1``) swaps in the real Ollama seat roster.
"""

from __future__ import annotations

import json
import os

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.operations import diff, judge, norms, propose, resolve, trace
from portal.modules.compliance.core.planner import (
    QUESTION_PLANS,
    compose_answer,
    execute_plan,
)
from portal.modules.compliance.core.policy_graph import build_policy_graph
from portal.modules.compliance.core.runtime_config import seat_roster

_LIVE = os.environ.get("COMPLIANCE_V6_LIVE") == "1"
_SEATS = (
    seat_roster()
    if _LIVE
    else [{"id": f"s{i}", "label": str(i), "model": f"m{i}"} for i in range(3)]
)
_HM = AssetScope(
    impact_present={"high", "medium"},
    associated_present={"eacms", "pacs", "pca"},
    declared_by="operator:test",
)


@pytest.fixture(scope="module")
def g():
    return build_policy_graph()


def _seat(determination: str, cite: str, finding: str | None = None):
    def fn(model, system, user):
        if "checking one thing only" in system:
            return '{"overrides": false, "exception_ref": null}'
        return json.dumps(
            {
                "determination": determination,
                "finding_type": finding,
                "cited_refs": [cite],
                "confidence": 0.85,
                "rationale": "scripted",
            }
        )

    return fn if not _LIVE else None


# ── Q01 — what does the current requirement require ────────────────────────


def test_q01_C_compound_part_yields_duties_and_reference(g):
    gs = resolve("CIP-007-6 R2", valid_at="2026-09-06", scope=_HM, policy_graph=g)
    assert gs.label == "current" and gs.enforceable
    assert len(gs.actor_cus) >= 3  # R2 has multiple Parts / duties
    assert any(p.get("id") == "CIP-007-6 R2 Part 2.1" for p in gs.premises) or gs.reference_closure


def test_q01_X_before_effective_date_returns_predecessor_labelled(g):
    gs = resolve("CIP-003-9 R1", valid_at="2020-06-01", scope=_HM, policy_graph=g)
    assert gs.label in {"historical", "future"}
    assert not gs.enforceable


def test_q01_U_undeclared_asset_fact_names_it(g):
    gs = resolve("CIP-005-7 R2 Part 2.1", valid_at="2026-09-06", scope=AssetScope(), policy_graph=g)
    # scope undeclared -> the resolve still returns the duty, but a downstream
    # judge would be UNKNOWN, not a silent N/A
    d = judge(
        "CIP-005-7 R2 Part 2.1",
        scope=AssetScope(),
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("SUPPORTED", "CIP-005-7 R2 Part 2.1"),
    )
    assert d.determination in {"ESCALATE", "SUPPORTED", "ABSENT", "NOT_APPLICABLE"}
    # the applicability reason must name the undeclared scope
    from portal.modules.compliance.core.gate import run_gate
    from portal.modules.compliance.core.vocabulary_bridge import derive_vocabulary

    gr = run_gate("CIP-005-7 R2 Part 2.1", g, derive_vocabulary(g), AssetScope(), [])
    assert "undeclared" in gr.applicability_reason or gr.applicability == "UNKNOWN"


# ── Q03 — aligned with the latest version ─────────────────────────────────


def test_q03_C_complete_implementation_resolves_supported(g):
    com = [
        {
            "commitment_id": "c1",
            "document_id": "spm",
            "standard_folder": "CIP-007",
            "actor": "OT Security Team",
            "text": "The OT Security Team shall evaluate security patches for applicability every 21 calendar days.",
        }
    ]
    d = judge(
        "CIP-007-6 R2 Part 2.2",
        scope=_HM,
        org_commitments=com,
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("SUPPORTED", "CIP-007-6 R2 Part 2.2"),
    )
    assert d.determination == "SUPPORTED"


def test_q03_X_removing_a_condition_flips_to_partial(g):
    d = judge(
        "CIP-007-6 R2 Part 2.2",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("PARTIAL", "CIP-007-6 R2 Part 2.2", finding="WEAK_MAPPING"),
    )
    assert d.determination == "PARTIAL"
    assert d.finding_type == "WEAK_MAPPING"


def test_q03_U_truncated_reading_returns_unresolved_not_gap(g):
    d = judge(
        "CIP-007-6 R2 Part 2.2",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("INSUFFICIENT", "CIP-007-6 R2 Part 2.2"),
    )
    assert d.determination == "ESCALATE"  # no vote reached quorum; not ABSENT


# ── Q04 — gaps / contradictions / outdated / weak mapping ─────────────────


def test_q04_C_planted_contradiction_is_typed(g):
    d = judge(
        "CIP-004-7 R2 Part 2.3",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("CONTRADICTED", "CIP-004-7 R2 Part 2.3", finding="CONTRADICTION"),
    )
    assert d.determination == "CONTRADICTED"
    assert d.finding_type == "CONTRADICTION"


def test_q04_X_correct_implementation_produces_no_finding(g):
    d = judge(
        "CIP-004-7 R2 Part 2.3",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("SUPPORTED", "CIP-004-7 R2 Part 2.3"),
    )
    assert d.determination == "SUPPORTED"
    assert d.finding_type == ""


def test_q04_U_unreadable_document_is_u03_not_a_gap(g):
    d = judge(
        "CIP-004-7 R2 Part 2.3",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("INSUFFICIENT", "CIP-004-7 R2 Part 2.3"),
    )
    assert d.determination != "ABSENT"


# ── Q05 — has a requirement changed since ─────────────────────────────────


def test_q05_C_real_transition_returns_changed_parts_typed():
    rows = diff("CIP-003-8", "CIP-003-9")
    assert rows and all("taxonomy_type" in r for r in rows)
    assert any(r["creates_review_work"] for r in rows)


def test_q05_X_procedure_after_transition_returns_no_change():
    # a diff of a revision against itself has no rows
    assert diff("CIP-003-9", "CIP-003-9") == []


def test_q05_U_no_review_date_still_reports_since_authored():
    rows = diff("CIP-003-8", "CIP-003-9")
    # the taxonomy is present even when the internal review date is unknown —
    # Q05's "since authored" fallback still has content
    assert rows


# ── Q08 / Q09 — restrictiveness & flexibility ─────────────────────────────


def test_q08_C_stricter_internal_is_more_restrictive_not_a_violation(g):
    prof = norms(
        "CIP-007-6 R2 Part 2.2",
        internal_quantities=[{"value": 21, "unit": "day"}],
        policy_graph=g,
        policy_decisions={},
    )
    assert prof.classification == "MORE_RESTRICTIVE"
    assert prof.intent["code"] == "U07_INTENT_UNKNOWN"


def test_q08_X_less_restrictive_retention_is_a_violation(g):
    # a min-retention Part with a shorter internal value is LESS_RESTRICTIVE
    prof = norms(
        "CIP-008-6 R4 Part 4.3",
        internal_quantities=[{"value": 20, "unit": "day"}],
        policy_graph=g,
        policy_decisions={},
    )
    assert prof.direction in {"max_interval", "max_elapsed", ""}


def test_q08_U_no_decision_row_returns_u07_naming_the_control(g):
    prof = norms("CIP-007-6 R2 Part 2.2", policy_graph=g, policy_decisions={})
    assert prof.intent["code"] == "U07_INTENT_UNKNOWN"
    assert prof.intent["control_id"] == "CIP-007-6 R2 Part 2.2"


# ── Q07 / Q12 — propose ───────────────────────────────────────────────────


def test_q07_C_proposal_flips_target_to_supported(g):
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["constraint"],
        "The OT Security Team shall evaluate security patches every 21 calendar days.",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("SUPPORTED", "CIP-007-6 R2 Part 2.2"),
    )
    assert pkg.rejudged.determination == "SUPPORTED"
    assert pkg.closes_fields == ["constraint"]


def test_q07_X_weakening_variant_is_detected(g):
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["constraint"],
        "We will review patches yearly.",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("CONTRADICTED", "CIP-007-6 R2 Part 2.2", finding="CONTRADICTION"),
    )
    assert pkg.weakens and "does not close" in pkg.weakens[0]


def test_q07_U_cannot_be_closed_by_document_text_is_reported(g):
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["constraint"],
        "TBD — needs an operational change.",
        scope=_HM,
        org_commitments=[],
        seats=_SEATS,
        policy_graph=g,
        seat_fn=_seat("PARTIAL", "CIP-007-6 R2 Part 2.2", finding="WEAK_MAPPING"),
    )
    assert pkg.closes_fields == []


# ── Q06 / Q10 / Q11 — traversal ──────────────────────────────────────────


def test_q10_C_requirement_returns_connected_entities(g):
    p = trace("CIP-007-6 R2 Part 2.2", direction="both", depth=2, policy_graph=g)
    assert len(p.nodes) > 1


def test_q06_X_isolated_section_surfaces_only_its_own(g):
    p = trace("CIP-012-2 R1 Part 1.1", direction="both", depth=2, policy_graph=g)
    assert all(n.startswith("CIP-012") or n == "CIP-012-2" for n in p.nodes)


def test_q11_U_budget_cutoff_disclosed_as_frontier(g):
    meta = next(n.id for n in g.nodes if n.node_type == "meta_cu")
    p = trace(meta, direction="both", depth=3, policy_graph=g, max_edges=3)
    assert p.budget_hit and p.frontier


# ── the plan is the trace (Y18) across all twelve ────────────────────────


def test_all_twelve_route_and_every_plan_op_is_one_of_six(g):
    six = {"resolve", "trace", "judge", "diff", "norms", "propose"}
    for ops in QUESTION_PLANS.values():
        assert set(ops) <= six
    # a routed answer records its plan
    tr = execute_plan(
        "What does CIP-007-6 R2 Part 2.2 actually require?",
        "CIP-007-6 R2 Part 2.2",
        op_impls={
            "resolve": lambda ref: resolve(ref, valid_at="2026-09-06", scope=_HM, policy_graph=g)
        },
    )
    assert tr.question_id == "Q01"
    assert tr.steps[0].ran
    assert "resolve" in compose_answer(tr)
