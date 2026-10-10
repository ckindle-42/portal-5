"""The pairing arms of scripts/review_eval_truth.py, offline.

The point of these tests is the arithmetic that blocked T1: a benign window as long as the whole
answer-key hull cannot exist inside an index that holds roughly the hull's worth of telemetry.
The control arm must reproduce that, and the candidate arms must not inherit it for free.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.review_eval.truth import EntryReceipt, TruthDerivation

REPO = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "review_eval_truth", REPO / "scripts" / "review_eval_truth.py"
)
assert _SPEC is not None and _SPEC.loader is not None
runner: Any = importlib.util.module_from_spec(_SPEC)
sys.modules["review_eval_truth"] = runner
_SPEC.loader.exec_module(runner)

DAY = 86_400.0


class _FixedExtentSource:
    """``pair_index`` takes an ``ExtentSource``; nothing here reaches Splunk."""

    def __init__(self, first: float | None, end_exclusive: float | None) -> None:
        self._extent = (first, end_exclusive)

    def index_extent(self, index: str) -> tuple[float | None, float | None]:
        return self._extent


def _receipt(index: str, start: float, end: float, *, status: str = "derived") -> EntryReceipt:
    return EntryReceipt(
        item_id=f"{index}:T1059:{start:.0f}",
        index=index,
        technique="T1059",
        sourcetypes=("stream:http",),
        expected_entity_count=1,
        located_entity_count=1,
        event_count=3,
        start_epoch=start,
        end_exclusive_epoch=end,
        status=status,
        reason="all_answer_key_entities_located",
        entity_tokens=("tok",),
        event_ids=("botsv1:stream:http:abc",),
    )


def _derivation(*receipts: EntryReceipt) -> TruthDerivation:
    return TruthDerivation((), receipts)


def _pair(derivation: TruthDerivation, source: Any, arm: str) -> Any:
    return runner.pair_index(
        "botsv1",
        derivation,
        source,
        arm=arm,
        margin_seconds=DAY,
        benign_index="portal5_lab",
    )


def test_hull_arm_reproduces_the_t1_exclusion() -> None:
    # 28 answer-key days inside a 28-day index: a same-size benign window cannot exist.
    derivation = _derivation(_receipt("botsv1", 0.0, 28 * DAY))
    pairing = _pair(derivation, _FixedExtentSource(0.0, 28 * DAY), "hull")
    assert not pairing.paired
    assert pairing.reason == runner.HULL_NO_CANDIDATE
    assert pairing.target_duration_seconds == pytest.approx(28 * DAY)


def test_hull_arm_pairs_when_the_index_is_twice_the_hull() -> None:
    derivation = _derivation(_receipt("botsv1", 0.0, 10 * DAY))
    pairing = _pair(derivation, _FixedExtentSource(0.0, 40 * DAY), "hull")
    assert pairing.paired
    assert pairing.reason == runner.HULL_CANDIDATE


def test_per_entry_arm_finds_windows_the_hull_arm_cannot() -> None:
    # Two 1-day scenarios 20 days apart: the hull spans the index, the entries do not.
    derivation = _derivation(
        _receipt("botsv1", 2 * DAY, 3 * DAY),
        _receipt("botsv1", 22 * DAY, 23 * DAY),
    )
    source = _FixedExtentSource(0.0, 24 * DAY)
    assert not _pair(derivation, source, "hull").paired
    per_entry = _pair(derivation, source, "per_entry")
    assert per_entry.paired
    assert per_entry.reason == runner.PER_ENTRY_CANDIDATE
    for start, end in per_entry.candidates:
        assert start % DAY == 0
        assert end - start == pytest.approx(DAY)
        assert not 1 * DAY <= start < 4 * DAY
        assert not 21 * DAY <= start < 24 * DAY


def test_matched_set_reaches_the_attack_duration_or_fails_loudly() -> None:
    picked = runner.matched_set_candidates(
        0.0, 28 * DAY, [(10 * DAY, 11 * DAY)], margin_seconds=DAY, target_duration_seconds=5 * DAY
    )
    assert len(picked) == 5
    assert sum(end - start for start, end in picked) == pytest.approx(5 * DAY)
    assert all(not 9 * DAY <= start < 12 * DAY for start, _ in picked)

    short = runner.matched_set_candidates(
        0.0, 6 * DAY, [(0.0, 5 * DAY)], margin_seconds=DAY, target_duration_seconds=5 * DAY
    )
    assert short == ()


def test_cross_index_arm_declares_the_benign_index() -> None:
    derivation = _derivation(_receipt("botsv1", 0.0, 2 * DAY))
    pairing = _pair(derivation, _FixedExtentSource(0.0, 10 * DAY), "cross_index")
    assert pairing.paired
    assert "portal5_lab" in pairing.reason


def test_no_derived_entry_is_not_a_pairing_failure() -> None:
    derivation = _derivation(_receipt("botsv1", 0.0, DAY, status="dropped"))
    pairing = _pair(derivation, _FixedExtentSource(0.0, 28 * DAY), "hull")
    assert pairing.reason == runner.NO_DERIVED_INTERVAL
    assert pairing.derived_entry_count == 0


def test_metrics_recompute_from_the_rows_they_report() -> None:
    derivation = _derivation(
        _receipt("botsv1", 0.0, DAY),
        _receipt("botsv1", 5 * DAY, 6 * DAY, status="dropped"),
    )
    pairings = [_pair(derivation, _FixedExtentSource(0.0, 28 * DAY), "hull")]
    rows = runner.build_rows(derivation, pairings)
    assert runner._entry_yield(rows) == pytest.approx(0.5)
    assert runner._slice_yield(rows) == pytest.approx(1.0)
    assert sum(row["kind"] == "answer_key_entry" for row in rows) == 2
    assert sum(row["kind"] == "index_slice" for row in rows) == 1


def test_entity_clause_quotes_every_entity() -> None:
    assert runner._entity_clause(()) == ""
    assert runner._entity_clause(("10.0.0.1", 'we"ird')) == ' ("10.0.0.1" OR "we\\"ird")'


def test_fetch_census_reports_id_collisions() -> None:
    census = runner.FetchCensus(rows=10, rows_without_cd=2, distinct_ids=8)
    assert census.to_dict()["id_collisions"] == 2


def _pair_benign(derivation: TruthDerivation, daily: dict[float, dict[str, int]]) -> Any:
    return runner.pair_index(
        "botsv1",
        derivation,
        _FixedExtentSource(0.0, 400 * DAY),
        arm="cross_index_benign",
        margin_seconds=DAY,
        benign_index="portal5_lab",
        benign_daily=daily,
    )


def test_portal_written_sources_are_never_benign() -> None:
    for denied in (
        "portal5:corpus:mordor:compound/apt29/day1/apt29_evals_day1_manual",
        "portal5:corpus:attack_data:malware/trickbot/infection/windows-sysmon",
        "portal5:imported_observed",
        "portal5:observed_packet",
        "http:portal5_hec",
    ):
        assert not runner.benign_source_eligible(denied), denied
    assert runner.benign_source_eligible("WinEventLog:Security")


def test_occupied_window_skips_a_window_with_an_empty_day() -> None:
    daily = {d * DAY: 5 for d in range(10) if d != 1}
    assert runner.occupied_window(daily, 3 * DAY) == (2 * DAY, 5 * DAY)
    assert runner.occupied_window({0.0: 1, DAY: 1}, 3 * DAY) is None


def test_cross_index_control_still_pairs_on_an_empty_window() -> None:
    # D-T8's defect, kept as the control: extent alone, no occupancy, no provenance.
    derivation = _derivation(_receipt("botsv1", 0.0, 2 * DAY))
    assert _pair(derivation, _FixedExtentSource(0.0, 10 * DAY), "cross_index").paired


def test_cross_index_benign_refuses_an_attack_only_index() -> None:
    derivation = _derivation(_receipt("botsv1", 0.0, 2 * DAY))
    daily = {d * DAY: {"portal5:corpus:attack_data:x": 100} for d in range(30)}
    pairing = _pair_benign(derivation, daily)
    assert not pairing.paired
    assert pairing.reason == "no_window_in_portal5_lab_with_eligible_events_on_every_utc_day"
    assert pairing.covariates["denied_source_event_count"] == 3000
    assert pairing.covariates["eligible_event_count"] == 0


def test_cross_index_benign_pairs_only_on_eligible_occupied_days() -> None:
    derivation = _derivation(_receipt("botsv1", 0.0, 2 * DAY))
    daily: dict[float, dict[str, int]] = {
        0.0: {"WinEventLog:Security": 4},
        DAY: {"portal5:imported_observed": 9},
        5 * DAY: {"WinEventLog:Security": 2, "portal5:observed_packet": 7},
        6 * DAY: {"stream:dns": 3},
    }
    pairing = _pair_benign(derivation, daily)
    assert pairing.paired
    assert pairing.candidates == ((5 * DAY, 7 * DAY),)
    assert pairing.covariates["window_eligible_event_count"] == 5
    assert pairing.covariates["window_min_daily_eligible_count"] == 2
    assert pairing.covariates["window_eligible_sources"] == {
        "WinEventLog:Security": 2,
        "stream:dns": 3,
    }


def test_cross_index_benign_needs_the_daily_counts() -> None:
    derivation = _derivation(_receipt("botsv1", 0.0, 2 * DAY))
    with pytest.raises(ValueError, match="daily source counts"):
        _pair(derivation, _FixedExtentSource(0.0, 10 * DAY), "cross_index_benign")


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.searches: list[str] = []

    def iter_post(self, search: str, start: float, end: float) -> Any:
        self.searches.append(search)
        return iter(self.rows)


def test_day_counts_use_the_entity_filter_and_keep_the_final_row() -> None:
    rows = _Rows([{"day": "864000", "count": "3"}, {"day": "864000", "count": "7"}, {"day": None}])
    source = runner.SplunkTruthSource(rows, partition_seconds=600.0)
    assert source.query_day_counts("botsv1", "stream:http", ("a.example",)) == {864000.0: 7}
    assert '("a.example")' in rows.searches[0]
    assert "floor(_time/86400)*86400" in rows.searches[0]
