"""TASK_BULLY_ADAPTIVE_REACH_V1 (A.1): budgets that respond to what a query
actually returned instead of a fixed constant guessed in advance.

Each test is seeded to fail against the pre-A.1 behaviour it replaces:
I.6's flat `MAX_EVENTS = 20_000` let one query spend the whole budget and
the recursive pivot never ran (`pivots: 0`, `n_queries: 1` on all five live
investigations).
"""

from __future__ import annotations

from portal.modules.security.core.bully import adaptive_scope as asc


def test_saturating_source_narrows_into_band_within_rescope_budget():
    # I.6's shape: a busy entity, 24h window, ~22500 rows against a 20000 cap.
    # Adaptive scoping opens tight and narrows until the result lands in band.
    backward, forward = asc.OPENING_BACKWARD_SECONDS, asc.OPENING_FORWARD_SECONDS
    rows_by_window = {1800.0: 600, 450.0: 150}  # 30m -> 600 rows; 7.5m -> 150

    rescopes = 0
    decision = asc.ScopeDecision("WIDEN", backward, forward, "start")
    for _ in range(asc.MAX_RESCOPES + 1):
        rows = rows_by_window.get(
            decision.backward if decision.action != "WIDEN" else backward,
            rows_by_window.get(backward, 600),
        )
        decision = asc.next_window(rows, backward, forward, rescopes_used=rescopes)
        if decision.action == "ACCEPT":
            break
        backward, forward = decision.backward, decision.forward
        rescopes += 1

    assert decision.action == "ACCEPT"
    assert decision.reason.startswith("in_band")
    assert rescopes < asc.MAX_RESCOPES
    assert backward < asc.OPENING_BACKWARD_SECONDS  # it actually narrowed


def test_narrow_decision_shrinks_window():
    decision = asc.next_window(600, asc.OPENING_BACKWARD_SECONDS, asc.OPENING_FORWARD_SECONDS)
    assert decision.action == "NARROW"
    assert decision.backward < asc.OPENING_BACKWARD_SECONDS
    assert decision.reason.startswith("saturated")


def test_sparse_source_widens():
    decision = asc.next_window(4, asc.OPENING_BACKWARD_SECONDS, asc.OPENING_FORWARD_SECONDS)
    assert decision.action == "WIDEN"
    assert decision.backward > asc.OPENING_BACKWARD_SECONDS
    assert decision.reason.startswith("sparse")


def test_dense_at_minimum_window_accepts_rather_than_looping():
    # Already at the floor and still saturating: accept, don't spin forever.
    decision = asc.next_window(10_000, asc.MIN_BACKWARD_SECONDS, asc.MIN_BACKWARD_SECONDS)
    assert decision.action == "ACCEPT"
    assert decision.reason == "already_at_minimum_window:dense_source"


def test_sparse_at_maximum_window_accepts_rather_than_looping():
    decision = asc.next_window(1, asc.MAX_BACKWARD_SECONDS, asc.MAX_BACKWARD_SECONDS)
    assert decision.action == "ACCEPT"
    assert decision.reason == "already_at_maximum_window:sparse_source"


def test_rescope_budget_exhausted_forces_accept():
    decision = asc.next_window(50_000, 1800.0, 600.0, rescopes_used=asc.MAX_RESCOPES)
    assert decision.action == "ACCEPT"
    assert "rescope_budget_exhausted" in decision.reason


def test_depth_budget_never_lets_depth_zero_exceed_its_allowance():
    budget = asc.DepthBudget(total_events=20_000, max_depth=3, per_query_cap=500)
    assert budget.allowance_per_depth == 5_000
    # Depth 0 can never spend more than its reserved allowance, however large
    # a single query's own result is -- this is the fix for I.6's "one query
    # returned 26k+ rows in one round trip" defect.
    # Even offered a result the size of I.6's real query-one row count, depth
    # 0 can never spend past its reserved allowance -- exhaust it query by
    # query and confirm the total never crosses 5000.
    for _ in range(20):
        spend = budget.may_spend(depth=0)
        assert spend <= budget.allowance_per_depth
        if spend == 0:
            break
        budget.record(depth=0, rows=spend)
    assert budget.spent[0] == budget.allowance_per_depth
    assert budget.may_spend(depth=0) == 0
    # Depth 1 is untouched by depth 0's spend: breadth of the chain survives.
    assert budget.may_spend(depth=1) == budget.per_query_cap


def test_depth_budget_reaches_depths_one_through_three_over_many_queries():
    budget = asc.DepthBudget(total_events=20_000, max_depth=3, per_query_cap=500)
    # 12 queries, 3 per depth, each spending the full per-query cap.
    for depth in range(4):
        for _ in range(3):
            spend = budget.may_spend(depth)
            assert spend > 0, f"depth {depth} should still be reachable"
            budget.record(depth, spend)
    assert budget.spent == {0: 1500, 1: 1500, 2: 1500, 3: 1500}
    assert budget.total_spent == 6000


def test_seeded_violation_flat_cap_starves_depths_one_through_three():
    """Reproduces `pivots: 0`: a flat cap with no per-depth reservation lets
    depth 0 alone consume the entire allowance, so depths 1-3 never run."""
    total_events = 20_000

    class FlatCap:
        def __init__(self, total: int) -> None:
            self.total = total
            self.spent = 0

        def may_spend(self, depth: int) -> int:  # noqa: ARG002
            return max(0, self.total - self.spent)

        def record(self, depth: int, rows: int) -> None:  # noqa: ARG002
            self.spent += rows

    flat = FlatCap(total_events)
    depth0_spend = flat.may_spend(depth=0)
    # One query at depth 0 (I.6's shape: 22,500 rows offered) can exhaust it.
    flat.record(depth=0, rows=min(depth0_spend, 22_500))
    reachable = [d for d in range(1, 4) if flat.may_spend(d) > 0]
    assert reachable == [], "flat cap must reproduce pivots:0 -- depths 1-3 unreachable"

    # The fix: DepthBudget reserves per-depth, so depths 1-3 stay reachable
    # even after depth 0 is offered the same oversized result.
    adaptive = asc.DepthBudget(total_events=total_events, max_depth=3, per_query_cap=500)
    adaptive.record(depth=0, rows=min(adaptive.may_spend(0), 22_500))
    reachable_adaptive = [d for d in range(1, 4) if adaptive.may_spend(d) > 0]
    assert reachable_adaptive == [1, 2, 3]


def test_saturation_report_pivot_ran_reflects_depths_reached():
    report_no_pivot = asc.SaturationReport(
        queries_issued=1,
        rescopes=0,
        narrowed=0,
        widened=0,
        depths_reached=(0,),
        budget={},
        saturated_queries=1,
        starved_queries=0,
    )
    assert report_no_pivot.pivot_ran is False

    report_pivoted = asc.SaturationReport(
        queries_issued=12,
        rescopes=2,
        narrowed=1,
        widened=0,
        depths_reached=(0, 1, 2),
        budget={},
        saturated_queries=1,
        starved_queries=0,
    )
    assert report_pivoted.pivot_ran is True
    assert report_pivoted.to_dict()["pivot_ran"] is True


def test_distance_recovery_flags_zero_hop_only_on_i6_planting_shape():
    # I.6's actual shape: 20 cousins, all planted at 0 hops (under the
    # anchor's own entity), all recovered.
    planted = [(f"cousin-{i}", 0) for i in range(20)]
    reached = {f"cousin-{i}" for i in range(20)}
    rec = asc.distance_recovery(planted, reached)
    d = rec.to_dict()
    assert d["zero_hop_only"] is True
    assert d["max_reached_distance"] == 0
    assert rec.recall_at(0) == 1.0
    assert rec.recall_at(1) is None


def test_distance_recovery_falling_curve_is_not_zero_hop_only():
    planted = [
        ("c0", 0),
        ("c0b", 0),
        ("c1a", 1),
        ("c1b", 1),
        ("c1c", 1),
        ("c1d", 1),
        ("c1e", 1),
        ("c2a", 2),
        ("c2b", 2),
        ("c2c", 2),
        ("c2d", 2),
        ("c2e", 2),
        ("c3a", 3),
        ("c3b", 3),
    ]
    reached = {"c0", "c0b", "c1a", "c1b", "c1c", "c1d", "c2a", "c2b"}
    rec = asc.distance_recovery(planted, reached)
    assert rec.recall_at(0) == 1.0
    assert rec.recall_at(1) == 0.8
    assert rec.recall_at(2) == 0.4
    assert rec.recall_at(3) == 0.0
    assert rec.max_reached_distance == 2
    assert rec.to_dict()["zero_hop_only"] is False
