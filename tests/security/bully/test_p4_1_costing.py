"""P4.1 -- COST typed cost metering (I-13, DATA_MODEL SS1.12).

Hermetic (no network, no lab). FINAL_VALIDATION C10 COST: typed quantities
recorded separately; pricing-profile conversion; missing measurement = null
+ quality flag, blocking ROI claims.
"""

from __future__ import annotations

import pathlib

import pytest

from portal.modules.security.core.bully import costing
from portal.modules.security.core.bully.contracts import CostComponent
from portal.modules.security.core.bully.store import Store


@pytest.fixture
def store(tmp_path: pathlib.Path) -> Store:
    s = Store(tmp_path / "hunt.db")
    yield s
    s.close()


def test_missing_measurement_blocks_roi_never_zero_fills():
    """I-13 FAILURE SEMANTICS: material missing measurement -> null +
    quality flag, never zero-filled into computed_units."""
    comps = [
        costing.observation("lab_minutes", "sk-lab", 10.0),
        costing.observation("inference_calls", "sk-inf", None, quality="missing"),
    ]
    record = costing.build_record("hunt-1", "iter-1", comps)
    assert record.computed_units is None
    assert record.quality_flag is True


def test_full_measurement_computes_nonzero_units():
    comps = [
        costing.observation("lab_minutes", "sk-lab", 10.0),
        costing.observation("analyst_minutes", "sk-an", 2.0),
    ]
    record = costing.build_record("hunt-1", "iter-1", comps)
    assert record.quality_flag is False
    assert record.computed_units is not None
    assert record.computed_units > 0.0


def test_missing_component_cannot_carry_a_value():
    with pytest.raises(ValueError):
        CostComponent(meter="lab_minutes", source_key="sk", value=1.0, quality="missing")


def test_non_missing_component_requires_a_value():
    with pytest.raises(ValueError):
        CostComponent(meter="lab_minutes", source_key="sk", value=None, quality="measured")


def test_per_source_key_idempotency_drops_duplicates_never_double_counts():
    """I-13 IDEMPOTENCY: 'one cost component per source key.'"""
    comps = [
        costing.observation("lab_minutes", "sk-1", 5.0),
        costing.observation("lab_minutes", "sk-1", 500.0),  # duplicate key, dropped
    ]
    record = costing.build_record("hunt-1", None, comps)
    assert len(record.components) == 1
    assert record.components[0].value == 5.0


def test_pricing_profile_version_recorded():
    comps = [costing.observation("lab_minutes", "sk-1", 5.0)]
    record = costing.build_record("hunt-1", None, comps, pricing_profile_version="v2-experimental")
    assert record.pricing_profile_version == "v2-experimental"


def test_cost_ledger_persists_and_reloads(store: Store):
    comps = [costing.observation("lab_minutes", "sk-1", 5.0)]
    record = costing.build_record("hunt-1", "iter-1", comps)
    store.cost_ledger_put(record)
    rows = store.cost_ledger_for_hunt("hunt-1")
    assert len(rows) == 1
    assert rows[0]["computed_units"] == record.computed_units
    assert rows[0]["quality_flag"] is False


def test_cost_view_reports_unrankable_gap_on_missing_measurement(store: Store):
    comps_ok = [costing.observation("lab_minutes", "sk-1", 5.0)]
    comps_gap = [
        costing.observation("lab_minutes", "sk-2", None, quality="missing"),
    ]
    store.cost_ledger_put(costing.build_record("hunt-A", None, comps_ok))
    store.cost_ledger_put(costing.build_record("hunt-B", None, comps_gap))

    rows = store.cost_ledger_for_hunt("hunt-A") + store.cost_ledger_for_hunt("hunt-B")
    view = costing.CostView(rows)

    units_a, gap_a = view.units_for("hunt-A")
    assert units_a is not None and gap_a is False

    units_b, gap_b = view.units_for("hunt-B")
    assert units_b is None and gap_b is True


def test_cost_view_no_data_is_unrankable_not_free():
    view = costing.CostView([])
    units, gap = view.units_for("no-such-hunt")
    assert units is None
    assert gap is True
