"""An indexed event's own ``_time`` survives intake end to end.

Regression for the first live ``windows:security`` episode (run
``run-c966ec5292b3``): the exported rows carry both ``_indextime`` (constant
across a HEC batch) and ``_time`` (each event's own clock). The role map
inferred both as TIMESTAMP and ``_roled_time`` took the alphabetically first,
stamping all 613 artifacts with one instant -- ``span_seconds: 0.0`` on
305-event chains and cited evidence ``"time": null``. The fixture is
byte-shaped from that run's stored evidence. Hermetic: no Splunk, no engines.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.review import calibration as cal
from portal.modules.security.core.review import funnel, intake, pipeline
from portal.modules.security.core.review.pipeline import ReviewConfig

INDEX_TIME = 1794061765
DC_MIN, DC_MAX = 1794057391.0, 1794058143.0  # the Splunk-verified spreads
SRV_MIN, SRV_MAX = 1794057414.0, 1794058167.0


def _live_record(serial: int, host: str, code: str, event_time: float) -> dict[str, object]:
    """One exported row, field-identical to the stored evidence of the live run."""
    return {
        "_bkt": "portal5_lab~13~0949F81C-B1F6-46F5-81E8-1ED374D3F398",
        "_cd": f"13:{2353 - serial}",
        "_indextime": str(INDEX_TIME),
        "_kv": "1",
        "_raw": f"EventCode={code} TimeCreated=2026-11-07 07:26:06",
        "_serial": str(serial),
        "_si": "splunk|portal5_lab",
        "_sourcetype": "windows:security",
        "_subsecond": ".0",
        "_time": event_time,
        "host": host,
        "index": "portal5_lab",
        "linecount": "1",
        "source": "portal5:live:boot:proxmox",
        "sourcetype": "windows:security",
        "splunk_server": "splunk",
    }


def _host_events(
    host: str, n: int, first: float, last: float, *, serial_base: int = 0
) -> list[dict[str, object]]:
    step = (last - first) / (n - 1)
    return [
        _live_record(
            serial_base + i, host, ["4624", "4672", "4634", "4688"][i % 4], first + i * step
        )
        for i in range(n)
    ]


def _live_window() -> dict[str, list[dict[str, object]]]:
    return {
        "portal5_lab:windows:security": _host_events("10.10.11.21", 305, DC_MIN, DC_MAX)
        + _host_events("10.10.11.33", 308, SRV_MIN, SRV_MAX, serial_base=305)
    }


def test_artifacts_carry_each_events_own_time_not_the_index_time() -> None:
    result = intake.build_window_units(_live_window())
    assert len(result.events) == 613
    for view in result.events.values():
        assert view.time is not None
        assert view.time != INDEX_TIME
    assert len({view.time for view in result.events.values()}) == 613


def test_multi_event_chain_reports_true_span() -> None:
    result = intake.build_window_units(_live_window())
    chains = sorted(u.unit.span_seconds for u in result.units if u.unit.level == "L3_CHAIN")
    assert chains == pytest.approx([752.0, 753.0])


def test_l3_ordering_uses_real_times() -> None:
    window_dict = _live_window()
    records = window_dict["portal5_lab:windows:security"]
    result = intake.build_window_units(window_dict)
    chain = next(u.unit for u in result.units if u.unit.level == "L3_CHAIN")
    stamps = [records[int(aid.rsplit("#a", 1)[1])]["_time"] for aid in sorted(chain.artifact_ids)]
    assert len(set(stamps)) == len(stamps)  # per-event times, not one constant
    assert stamps == sorted(stamps)  # members order by real time (record order here)
    assert max(stamps) - min(stamps) == pytest.approx(chain.span_seconds)


def test_record_without_usable_time_is_receipted_not_silent() -> None:
    window_dict = _live_window()
    records = window_dict["portal5_lab:windows:security"]
    for record in records[:5]:
        del record["_time"]
        del record["_indextime"]
    result = intake.build_window_units(window_dict)
    receipt = next(r for r in result.receipts if r.name == "intake.timed_events")
    assert (receipt.examined, receipt.resolved) == (613, 608)
    assert receipt.note
    assert sum(1 for v in result.events.values() if v.time is None) == 5


def _flagging_reference(window: intake.IntakeResult) -> pipeline.Reference:
    """A reference whose unusual threshold everything clears, so concerns raise."""
    cset = cal.CalibrationSet()
    cset.put(
        cal.fit_calibration(
            funnel.CHANNEL_UNUSUAL, "L3_CHAIN", [-1.0] * 40, 0.2, basis="benign_slice"
        )
    )
    model = funnel.fit_baseline([u.unit for u in window.units], "portal5_lab")
    return pipeline.Reference(model, cset, "benign_slice")


def test_cited_evidence_time_is_populated_not_null() -> None:
    window = intake.build_window_units(_live_window())
    config = ReviewConfig(
        policy=funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=("L3_CHAIN",))
    )
    result = pipeline.review_window(
        window, reference=_flagging_reference(window), index=None, embedder=None, config=config
    )
    assert result.concerns
    for concern in result.concerns:
        assert concern.evidence
        for ref in concern.evidence:
            assert ref.time is not None
            assert ref.time != INDEX_TIME


def test_untimed_events_degrade_the_run() -> None:
    window_dict = _live_window()
    for record in window_dict["portal5_lab:windows:security"][:5]:
        del record["_time"]
        del record["_indextime"]
    window = intake.build_window_units(window_dict)
    config = ReviewConfig(
        policy=funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=("L3_CHAIN",))
    )
    result = pipeline.review_window(
        window, reference=_flagging_reference(window), index=None, embedder=None, config=config
    )
    assert any("no parseable timestamp" in line for line in result.degraded)


def test_existing_corpus_shapes_keep_working() -> None:
    from tests.security.review._fakes import three_source_window

    result = intake.build_window_units(three_source_window(seed=8, n=300, attacker="evil"))
    assert result.units
    timed = sum(1 for v in result.events.values() if v.time is not None)
    assert timed == len(result.events)
    spans = [u.unit.span_seconds for u in result.units if u.unit.level == "L4_WINDOW"]
    assert spans and spans[0] is not None and spans[0] > 0.0
