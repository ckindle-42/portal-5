"""P4.3 -- TGT eligibility + posteriors + recall-influenced ROI (I-11).

Hermetic (no network, no store I/O -- pure compute over injected data).
FINAL_VALIDATION C10 TGT: a known-benign cell is declined with logged
reasons; known-state adjusts the posterior (never a second multiplier);
hard eligibility excludes unauthorized/unready/unhealthy/locked cells;
missing material cost -> unrankable; deterministic tie-break; empty
eligible -> honest stop.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully import costing, targeting


def _context(cells, known_state=None, hunt_id="hunt-1"):
    return SimpleNamespace(
        hunt_id=hunt_id,
        open_cells=cells,
        known_state_view=known_state or [],
        config_version="cfg-1",
    )


def _recall(selected_context=None, recall_id="rr-1"):
    return SimpleNamespace(recall_id=recall_id, selected_context=selected_context or [])


def _ledger_with(hunt_ids_with_cost: dict[str, float]) -> costing.CostView:
    rows = []
    for hunt_id, units in hunt_ids_with_cost.items():
        comps = [costing.observation("lab_minutes", f"{hunt_id}:sk", units)]
        rows.append(costing.build_record(hunt_id, None, comps).to_dict())
    return costing.CostView(rows)


def test_known_benign_cell_declined_with_logged_reason():
    cells = [{"cell_id": "cell-1", "subject": "subj-1", "cost_ref": "hunt-1"}]
    known_state = [{"subject": "subj-1", "kind": "known_benign", "trust_tier": "VALIDATED"}]
    decision = targeting.select(
        _context(cells, known_state), _recall(), _ledger_with({"hunt-1": 1.0})
    )
    assert decision.status == "no_eligible_target"
    assert len(decision.declined) == 1
    assert decision.declined[0].reason == "KNOWN_BENIGN"
    assert decision.declined[0].cell_id == "cell-1"


@pytest.mark.parametrize(
    "flag,reason",
    [
        ({"authorized": False}, "UNAUTHORIZED"),
        ({"ready": False}, "NOT_READY"),
        ({"healthy": False}, "UNHEALTHY"),
        ({"locked": True}, "LOCKED"),
    ],
)
def test_hard_eligibility_excludes_each_gate(flag, reason):
    cells = [{"cell_id": "cell-1", "subject": "subj-1", "cost_ref": "hunt-1", **flag}]
    decision = targeting.select(_context(cells), _recall(), _ledger_with({"hunt-1": 1.0}))
    assert decision.status == "no_eligible_target"
    assert decision.declined[0].reason == reason


def test_missing_material_cost_is_unrankable_never_zero_cost():
    cells = [{"cell_id": "cell-1", "subject": "subj-1", "cost_ref": "hunt-no-cost"}]
    decision = targeting.select(_context(cells), _recall(), _ledger_with({}))
    assert decision.status == "unrankable"
    assert decision.declined[0].reason == "MISSING_COST"
    assert decision.selected_cell_id is None


def test_partial_missing_cost_declines_only_that_cell_and_still_ranks_others():
    cells = [
        {"cell_id": "cell-ok", "subject": "subj-ok", "cost_ref": "hunt-A"},
        {"cell_id": "cell-gap", "subject": "subj-gap", "cost_ref": "hunt-B"},
    ]
    decision = targeting.select(_context(cells), _recall(), _ledger_with({"hunt-A": 2.0}))
    assert decision.status == "selected"
    assert decision.selected_cell_id == "cell-ok"
    reasons = {d.cell_id: d.reason for d in decision.declined}
    assert reasons["cell-gap"] == "MISSING_COST"


def test_empty_open_cells_is_an_honest_no_eligible_target_stop():
    decision = targeting.select(_context([]), _recall(), _ledger_with({}))
    assert decision.status == "no_eligible_target"
    assert decision.declined == ()


def test_known_state_adjusts_posterior_never_a_second_multiplier():
    cells_plain = [{"cell_id": "c1", "subject": "s1", "cost_ref": "h", "prior": 0.8}]
    cells_adjusted = [{"cell_id": "c1", "subject": "s1", "cost_ref": "h", "prior": 0.8}]
    known_state_two_hits = [
        {"subject": "s1", "kind": "known_covered", "trust_tier": "VALIDATED"},
        {"subject": "s1", "kind": "dead_end", "trust_tier": "VALIDATED"},
    ]
    ledger = _ledger_with({"h": 1.0})

    plain = targeting.select(_context(cells_plain), _recall(), ledger)
    adjusted = targeting.select(_context(cells_adjusted, known_state_two_hits), _recall(), ledger)

    assert plain.ordered_targets[0]["posterior"] == 0.8
    # Two matching adjustments both apply their factor to the SAME base
    # (0.8), never compounded (0.8*0.3*0.05) -- the last-applied factor
    # alone determines the result.
    assert adjusted.ordered_targets[0]["posterior"] == round(0.8 * 0.05, 4)
    assert adjusted.ordered_targets[0]["posterior"] != round(0.8 * 0.3 * 0.05, 4)


def test_unvalidated_known_state_never_adjusts_posterior():
    cells = [{"cell_id": "c1", "subject": "s1", "cost_ref": "h", "prior": 0.8}]
    known_state = [{"subject": "s1", "kind": "dead_end", "trust_tier": "SUSPECT"}]
    decision = targeting.select(_context(cells, known_state), _recall(), _ledger_with({"h": 1.0}))
    assert decision.ordered_targets[0]["posterior"] == 0.8


def test_recall_receipt_influence_changes_ordering():
    cells = [
        {"cell_id": "cell-a", "subject": "subj-a", "cost_ref": "h", "prior": 0.6},
        {"cell_id": "cell-b", "subject": "subj-b", "cost_ref": "h", "prior": 0.6},
    ]
    ledger = _ledger_with({"h": 1.0})

    no_recall = targeting.select(_context(cells), _recall(), ledger)
    # Tied priority -- deterministic tie-break by cell_id.
    assert no_recall.selected_cell_id == "cell-a"

    recall_toward_b = _recall(selected_context=[{"record": {"subject": "subj-b"}}])
    with_recall = targeting.select(_context(cells), recall_toward_b, ledger)
    assert with_recall.selected_cell_id == "cell-b"
    assert "cell-b" in with_recall.recall_influence["influenced_cells"]


def test_deterministic_tie_break_is_priority_desc_then_cell_id_asc():
    cells = [
        {"cell_id": "cell-z", "subject": "subj-z", "cost_ref": "h", "prior": 0.5},
        {"cell_id": "cell-a", "subject": "subj-a", "cost_ref": "h", "prior": 0.5},
    ]
    decision = targeting.select(_context(cells), _recall(), _ledger_with({"h": 1.0}))
    assert decision.selected_cell_id == "cell-a"
    assert decision.tie_break == "priority_desc_then_cell_id_asc"


def test_declined_cell_reasons_are_recorded_for_every_decline():
    cells = [
        {"cell_id": "c-unauth", "subject": "s1", "cost_ref": "h", "authorized": False},
        {"cell_id": "c-locked", "subject": "s2", "cost_ref": "h", "locked": True},
    ]
    decision = targeting.select(_context(cells), _recall(), _ledger_with({"h": 1.0}))
    reasons = {d.cell_id: d.reason for d in decision.declined}
    assert reasons == {"c-unauth": "UNAUTHORIZED", "c-locked": "LOCKED"}
    for d in decision.declined:
        assert d.detail  # never a silent/empty reason


def test_override_cannot_bypass_authorization_readiness_health_gates():
    cells = [{"cell_id": "c1", "subject": "s1", "cost_ref": "h", "authorized": False}]
    with pytest.raises(targeting.OverrideRejectedError):
        targeting.select(
            _context(cells),
            _recall(),
            _ledger_with({"h": 1.0}),
            override={"cell_id": "c1", "reason": "operator insists"},
        )


def test_override_can_rescue_a_known_benign_decline_with_a_reason():
    cells = [{"cell_id": "c1", "subject": "s1", "cost_ref": "h", "prior": 0.5}]
    known_state = [{"subject": "s1", "kind": "known_benign", "trust_tier": "VALIDATED"}]
    decision = targeting.select(
        _context(cells, known_state),
        _recall(),
        _ledger_with({"h": 1.0}),
        override={"cell_id": "c1", "reason": "operator re-verifying after config change"},
    )
    assert decision.status == "selected"
    assert decision.selected_cell_id == "c1"
    # The override is still recorded in the audit trail.
    assert any(d.cell_id == "c1" and d.reason == "KNOWN_BENIGN" for d in decision.declined)


def test_override_requires_a_reason():
    cells = [{"cell_id": "c1", "subject": "s1", "cost_ref": "h"}]
    with pytest.raises(ValueError):
        targeting.select(
            _context(cells), _recall(), _ledger_with({"h": 1.0}), override={"cell_id": "c1"}
        )
