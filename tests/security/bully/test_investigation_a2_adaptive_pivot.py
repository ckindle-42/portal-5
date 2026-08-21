"""TASK_BULLY_ADAPTIVE_REACH_V1 (A.2): the investigation engine uses
adaptive scoping and a per-depth budget instead of a flat event cap.

Seeded against I.6's exact live failure: a busy real entity where the
opening 24h window returns far more rows than a flat `MAX_EVENTS` cap, so
query one consumes the whole budget and the recursive pivot -- the
investigation model's entire substance -- never runs (`pivots: 0`,
`n_queries: 1` on all five live investigations).
"""

from __future__ import annotations

from portal.modules.security.core.bully import investigation_pivot as ip

# A three-hop chain, each stage sharing no identifier with the one before.
_CHAIN = {
    "busy-host": [("user", "stage-1-user")],
    "stage-1-user": [("resource", "stage-2-resource")],
    "stage-2-resource": [("host", "stage-3-host")],
}

_ANCHOR = ip.Anchor(
    anchor_id="a-i6-density",
    at=1534737600.0 + 15 * 3600,
    entity="busy-host",
    entity_kind="host",
    sourcetype="WinEventLog",
    why="i6_density_profile",
    index="botsv3",
)


def _i6_density_execute(query: ip.PivotQuery) -> list[dict]:
    """I.6's shape: a busy entity returns ~900 rows/hour of window span,
    scaled so a full-day (24h) opening window returns well over 20,000 rows
    -- exactly the profile that consumed I.6's flat MAX_EVENTS on query one.
    A narrow window (as adaptive scoping opens with) returns proportionally
    fewer, real rows -- always including one row that carries the pivot to
    the next stage."""
    span_hours = max(query.latest - query.earliest, 1.0) / 3600.0
    n = max(1, int(span_hours * 900))
    rows = [
        {"_time": query.earliest + 1, "sourcetype": "WinEventLog", "entity": query.entity}
        for _ in range(n)
    ]
    return rows


def _extract(row: dict) -> list[tuple[str, str]]:
    return _CHAIN.get(row.get("entity"), [])


def test_i6_density_profile_now_reaches_depth_2_with_pivot_ran_true():
    inv = ip.investigate(_ANCHOR, ["botsv3"], _i6_density_execute, _extract)
    assert inv.saturation_report is not None
    assert inv.saturation_report.pivot_ran is True
    assert max(inv.saturation_report.depths_reached, default=-1) >= 2
    assert "stage-1-user" in inv.entities_seen
    assert "stage-2-resource" in inv.entities_seen


def test_same_density_profile_under_old_flat_cap_does_not_pivot():
    """Reproduces I.6 directly: a flat MAX_EVENTS with no adaptive re-scoping
    and no per-depth reservation lets one 24h-opening query consume the
    entire budget before any pivot can run."""

    def flat_cap_investigate(anchor: ip.Anchor, max_events: int = 20_000) -> tuple[int, int]:
        earliest, latest = anchor.at - 24 * 3600, anchor.at + 3600  # I.6's fixed 24h/1h window
        query = ip.PivotQuery(
            query_id="q0-0",
            index="botsv3",
            entity=anchor.entity,
            entity_kind=anchor.entity_kind,
            earliest=earliest,
            latest=latest,
            depth=0,
            parent_query_id=None,
            reason="anchor_expansion",
        )
        rows = _i6_density_execute(query)
        events = rows[:max_events]
        n_queries = 1
        pivots = 0
        if len(events) < max_events:  # old code's implicit gate: only pivots if budget remained
            for row in events:
                pivots += len(_extract(row))
        return n_queries, pivots

    n_queries, pivots = flat_cap_investigate(_ANCHOR)
    assert n_queries == 1
    assert pivots == 0, "flat-cap density profile must reproduce I.6's pivots:0"
