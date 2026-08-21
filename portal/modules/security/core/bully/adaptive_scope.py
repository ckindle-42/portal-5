"""bully.adaptive_scope -- budgets that respond to what was found, not guesses
made before looking.

Every fixed constant in this workstream has become the finding:

    --capture-limit 2000   decided which records were ever seen
    --max-timelines 25     decided the entire outcome distribution
    head 20000             truncated 226M events to 20k
    MIN_CONFIDENCE 0.35    gated on the class prior, so unseen verbs took the
                           majority class
    MAX_EVENTS 20000       consumed by query ONE in I.6, so the recursive pivot
                           -- the whole substance of the investigation model --
                           executed zero times across five investigations

That last one is the pattern in its purest form. The cap was sized against a
probe where a query returned a handful of rows. On a real index a 24-hour
window scoped to a busy entity returns more than the entire budget, so the
first query spends everything and the investigation stops before it pivots.
`pivots: 0` on all five, `n_queries: 1` on all five -- and the run still
published `reach_recall 1.0` and `20/20` cousin recovery.

**You do not know what a query will return until you run it.** So a budget
fixed in advance is a guess that silently becomes the answer. The correction
is to make scoping respond to observed volume, the way an analyst does: a
query returning 20,000 rows does not mean stop, it means the filter is too
wide -- narrow it. A query returning four rows means widen.

Three mechanisms:

  * `next_window` -- multiplicative narrow on saturation, widen on sparsity,
    accept in band. The opening move is deliberately TIGHT and widens only if
    the data is thin, which is the opposite of the 24h-first default that
    saturated I.6.
  * `DepthBudget` -- reserves budget per depth so no single query can consume
    the whole allowance. Breadth of the chain is what an investigation is
    for; events from one query are not.
  * `saturation_report` -- publishes what the budget DID to the result, so a
    truncated reconstruction is never read as a complete one.

Pure compute (COLD). No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "adaptive-scope-v1"

# The band a query result should land in to be useful. Below it the window is
# too tight to see context; above it the analyst would narrow rather than read.
TARGET_MIN_ROWS = 20
TARGET_MAX_ROWS = 500

# Opening window: tight on purpose. I.6 opened at 24h backward and saturated on
# query one; an analyst opens near the anchor and widens outward.
OPENING_BACKWARD_SECONDS = 30 * 60
OPENING_FORWARD_SECONDS = 10 * 60

# How far a window may widen or narrow per step, and the outer bound. The outer
# bound is a corpus property (BOTS scenarios are single-day; a real environment
# with 14-day median dwell needs far more), so it is a parameter, never a
# constant baked into a call site.
WIDEN_FACTOR = 4.0
NARROW_FACTOR = 0.25
MAX_BACKWARD_SECONDS = 24 * 3600
MIN_BACKWARD_SECONDS = 60.0

# Retries per scope before accepting whatever it returns. Bounded so adaptation
# cannot loop.
MAX_RESCOPES = 4


@dataclass(frozen=True)
class ScopeDecision:
    action: str  # NARROW | WIDEN | ACCEPT | ABANDON
    backward: float
    forward: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "backward": self.backward,
            "forward": self.forward,
            "reason": self.reason,
        }


def next_window(
    rows_returned: int,
    backward: float,
    forward: float,
    *,
    rescopes_used: int = 0,
    target_min: int = TARGET_MIN_ROWS,
    target_max: int = TARGET_MAX_ROWS,
    max_backward: float = MAX_BACKWARD_SECONDS,
    min_backward: float = MIN_BACKWARD_SECONDS,
    max_rescopes: int = MAX_RESCOPES,
) -> ScopeDecision:
    """Decide what to do with a window given what it actually returned.

    Saturation is a signal to narrow, not to stop. That single inversion is
    what lets the pivot run: I.6's fixed cap treated a large result as budget
    spent, so the investigation ended where it should have tightened.
    """
    if rescopes_used >= max_rescopes:
        return ScopeDecision(
            "ACCEPT", backward, forward, f"rescope_budget_exhausted:{rescopes_used}"
        )
    if rows_returned > target_max:
        nb = max(min_backward, backward * NARROW_FACTOR)
        nf = max(min_backward, forward * NARROW_FACTOR)
        if nb <= min_backward and backward <= min_backward:
            return ScopeDecision(
                "ACCEPT", backward, forward, "already_at_minimum_window:dense_source"
            )
        return ScopeDecision("NARROW", nb, nf, f"saturated:{rows_returned}>{target_max}")
    if rows_returned < target_min:
        nb = min(max_backward, backward * WIDEN_FACTOR)
        nf = min(max_backward, forward * WIDEN_FACTOR)
        if nb >= max_backward and backward >= max_backward:
            return ScopeDecision(
                "ACCEPT", backward, forward, "already_at_maximum_window:sparse_source"
            )
        return ScopeDecision("WIDEN", nb, nf, f"sparse:{rows_returned}<{target_min}")
    return ScopeDecision(
        "ACCEPT", backward, forward, f"in_band:{target_min}<={rows_returned}<={target_max}"
    )


@dataclass
class DepthBudget:
    """Budget reserved per pivot depth, so no single query can spend it all.

    An investigation's value is the BREADTH of the chain it reconstructs, not
    the volume of one query's results. I.6 proved the alternative: one query
    took the whole allowance and four investigations reached a single entity.
    """

    total_events: int
    max_depth: int
    per_query_cap: int
    spent: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.spent:
            self.spent = dict.fromkeys(range(self.max_depth + 1), 0)

    @property
    def allowance_per_depth(self) -> int:
        return max(1, self.total_events // (self.max_depth + 1))

    def may_spend(self, depth: int) -> int:
        """How many events this depth may still take. A depth cannot borrow
        from a deeper one it has not reached yet."""
        used = self.spent.get(depth, 0)
        remaining_here = max(0, self.allowance_per_depth - used)
        return min(self.per_query_cap, remaining_here)

    def record(self, depth: int, rows: int) -> None:
        self.spent[depth] = self.spent.get(depth, 0) + rows

    @property
    def total_spent(self) -> int:
        return sum(self.spent.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "max_depth": self.max_depth,
            "per_query_cap": self.per_query_cap,
            "allowance_per_depth": self.allowance_per_depth,
            "spent_by_depth": dict(self.spent),
            "total_spent": self.total_spent,
        }


@dataclass(frozen=True)
class SaturationReport:
    """What the budget did to the result. Published so a truncated
    reconstruction is never mistaken for a complete one."""

    queries_issued: int
    rescopes: int
    narrowed: int
    widened: int
    depths_reached: tuple[int, ...]
    budget: dict[str, Any]
    saturated_queries: int
    starved_queries: int

    @property
    def pivot_ran(self) -> bool:
        return max(self.depths_reached, default=0) >= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "queries_issued": self.queries_issued,
            "rescopes": self.rescopes,
            "narrowed": self.narrowed,
            "widened": self.widened,
            "depths_reached": list(self.depths_reached),
            "budget": self.budget,
            "saturated_queries": self.saturated_queries,
            "starved_queries": self.starved_queries,
            "pivot_ran": self.pivot_ran,
        }


# ── measuring reach by pivot distance ──────────────────────────────────────


@dataclass(frozen=True)
class DistanceRecovery:
    """Recovery broken out by how many pivot HOPS from the anchor a thing sat.

    I.6 recovered 20/20 cousins because each was injected under its own anchor
    entity: query the anchor, find the cousin. That measures the starting
    position, not the investigation. Injecting at a known hop distance makes
    recovery a measurement of REACH -- and a 0-hop recovery is explicitly
    labelled as not evidence of investigative capability.
    """

    by_distance: dict[int, dict[str, int]]

    def recall_at(self, hops: int) -> float | None:
        d = self.by_distance.get(hops)
        if not d or not d.get("total"):
            return None
        return d["reached"] / d["total"]

    @property
    def max_reached_distance(self) -> int:
        return max((h for h, d in self.by_distance.items() if d.get("reached")), default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_distance": {
                str(h): {**d, "recall": self.recall_at(h)}
                for h, d in sorted(self.by_distance.items())
            },
            "max_reached_distance": self.max_reached_distance,
            "zero_hop_only": self.max_reached_distance == 0,
        }


def distance_recovery(
    planted: list[tuple[str, int]], reached_entities: set[str]
) -> DistanceRecovery:
    """`planted` is [(entity, hops_from_anchor)]."""
    by: dict[int, dict[str, int]] = {}
    for entity, hops in planted:
        slot = by.setdefault(hops, {"total": 0, "reached": 0})
        slot["total"] += 1
        if entity in reached_entities:
            slot["reached"] += 1
    return DistanceRecovery(by_distance=by)
