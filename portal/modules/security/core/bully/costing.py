"""bully.costing -- COST, typed cost metering (P4.1, I-13).

Pure compute over injected data (MASTER SS3): no SQL, no network. Callers
(`orchestrator.py`, CLI) collect raw resource observations, hand them to
`build_record`, then persist the returned `CostRecord` via
`store.cost_ledger_put` -- this module never touches `hunt_state.db` itself
(same documented split as `drift_engine.py`: the pure function computes, the
caller persists).

I-13 FAILURE SEMANTICS: "material missing measurement -> null + quality flag
-> blocks ROI claims; never zero-fills." A component is *material* unless the
caller explicitly marks its meter non-material (`immaterial_meters`) --
default is that every meter counted matters to the ROI claim.

I-13 IDEMPOTENCY: "one cost component per source key." `build_record`
de-duplicates by `source_key`, keeping the first observation seen for a
given key -- a caller that (re)submits the same source key twice never
produces two components for it.
"""

from __future__ import annotations

import uuid
from typing import Any

from .contracts import CostComponent, CostRecord

__all__ = ["observation", "build_record", "CostView", "cost_view_for"]

DEFAULT_PRICING_PROFILE_VERSION = "v1"

# Default per-meter unit price for the comparable "computed_units" figure.
# Config-overridable (I-13 OPERATOR BOUNDARY: "pricing profile is config").
DEFAULT_PRICING_PROFILE: dict[str, float] = {
    "lab_minutes": 1.0,
    "inference_calls": 0.01,
    "inference_tokens": 0.00001,
    "inference_latency_ms": 0.0001,
    "analyst_minutes": 2.0,
    "replay_work": 0.5,
    "storage_bytes": 0.0000001,
    "training_allocation": 5.0,
}


def observation(
    meter: str,
    source_key: str,
    value: float | None,
    *,
    quality: str = "measured",
) -> CostComponent:
    """Build one typed resource observation. `quality="missing"` requires
    `value=None` (enforced by `CostComponent.__post_init__`)."""
    return CostComponent(meter=meter, source_key=source_key, value=value, quality=quality)


def build_record(
    hunt_id: str,
    iteration_id: str | None,
    components: list[CostComponent],
    *,
    pricing_profile: dict[str, float] | None = None,
    pricing_profile_version: str = DEFAULT_PRICING_PROFILE_VERSION,
    immaterial_meters: frozenset[str] = frozenset(),
) -> CostRecord:
    """I-13: fold typed observations into one `CostRecord`.

    Idempotent on `source_key` (first observation for a key wins; later
    duplicates for the same key are dropped, never summed twice). Any
    *material* component with `quality="missing"` sets `quality_flag=True`
    and forces `computed_units=None` -- a missing measurement is never
    zero-filled into the ROI figure.
    """
    pricing_profile = pricing_profile or DEFAULT_PRICING_PROFILE

    deduped: dict[str, CostComponent] = {}
    for comp in components:
        deduped.setdefault(comp.source_key, comp)
    ordered = tuple(deduped[k] for k in sorted(deduped))

    material_missing = any(
        c.quality == "missing" and c.meter not in immaterial_meters for c in ordered
    )

    computed_units: float | None
    if material_missing:
        computed_units = None
    else:
        computed_units = 0.0
        for comp in ordered:
            if comp.value is None:
                continue
            unit_price = pricing_profile.get(comp.meter, 0.0)
            computed_units += comp.value * unit_price
        computed_units = round(computed_units, 6)

    return CostRecord(
        record_id=f"cr-{uuid.uuid4().hex[:12]}",
        hunt_id=hunt_id,
        iteration_id=iteration_id,
        components=ordered,
        pricing_profile_version=pricing_profile_version,
        computed_units=computed_units,
        quality_flag=material_missing,
    )


class CostView:
    """Read-only view over a hunt's cost ledger, handed to `targeting.select`
    (I-11 INPUT: "cost ledger"). Pure -- built from rows the caller already
    fetched via `store.py`; never queries SQL itself."""

    def __init__(self, records: list[dict[str, Any]] | list[CostRecord]):
        self._by_hunt: dict[str, list[Any]] = {}
        for rec in records:
            hunt_id = rec["hunt_id"] if isinstance(rec, dict) else rec.hunt_id
            self._by_hunt.setdefault(hunt_id, []).append(rec)

    def units_for(self, hunt_id: str) -> tuple[float | None, bool]:
        """Returns `(total_computed_units, has_unrankable_gap)`.

        `has_unrankable_gap=True` whenever *any* ledger row for this hunt
        has `computed_units=None` (a material missing measurement) --
        callers must treat that hunt/cell as cost-unrankable, never
        zero-cost."""
        rows = self._by_hunt.get(hunt_id, [])
        if not rows:
            return None, True  # no cost data at all -- unrankable, not free
        total = 0.0
        gap = False
        for rec in rows:
            units = rec["computed_units"] if isinstance(rec, dict) else rec.computed_units
            if units is None:
                gap = True
                continue
            total += units
        return (None if gap else round(total, 6)), gap


def cost_view_for(records: list[dict[str, Any]]) -> CostView:
    """Convenience constructor mirroring `CostView(records)` (kept as its own
    name so callers/tests can name intent: 'build a CostView for targeting')."""
    return CostView(records)
