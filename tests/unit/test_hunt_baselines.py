"""Baselines over a grid: measured cycle, peers, stream identity, left-censor, cheap keys."""

from __future__ import annotations

import random
import time
from typing import Any

from portal.modules.security.core.hunt.baselines import (
    cycle_lag,
    cycle_seconds,
    episodes,
    peer_proportion,
)
from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.observations import (
    KEY_SLICES,
    Observation,
    load_observations,
    load_receipts,
    observe,
    reorder,
    rescore,
    write_receipts,
)
from tests.unit.test_hunt_observations import (
    END,
    INDEX,
    START,
    GridSearch,
    _event,
    _ref_burst,
    _universe,
)


def _volume(run_obs: list[Observation], host: str, hour: int) -> Observation:
    return next(
        obs for obs in run_obs if obs.kind == "volume" and obs.host == host and obs.hour == hour
    )


def test_cycle_lag_is_the_fundamental_of_the_series_itself() -> None:
    assert cycle_lag([1, 0, 0, 5] * 8) == 4
    assert cycle_lag([9, 1, 1, 1, 1, 1] * 8) == 6
    assert cycle_lag(([5] * 8 + [0] * 16) * 4) == 24
    assert cycle_lag(list(range(40))) is None
    assert cycle_lag([3] * 40) is None
    gapped = {index * HOUR: count for index, count in enumerate([1, 0, 0, 5] * 8) if count}
    assert cycle_seconds(gapped) == 4 * HOUR
    day = {index * HOUR: count for index, count in enumerate(([5] * 8 + [0] * 16) * 4) if count}
    assert cycle_seconds(day) == 24 * HOUR


def _identity(obs: Observation) -> tuple[str, str, str, int, str]:
    return (obs.kind, obs.host, obs.entity, obs.hour, str(obs.evidence["signal"]))


def _same_shared(plain_obs: list[Observation], contaminated_obs: list[Observation]) -> None:
    plain_by = {_identity(obs): obs for obs in plain_obs}
    seen = {_identity(obs) for obs in contaminated_obs}
    assert plain_by.keys() <= seen
    for obs in contaminated_obs:
        key = _identity(obs)
        if key in plain_by:
            assert obs == plain_by[key]


def test_a_far_hour_does_not_change_the_cycle_or_the_other_scores() -> None:
    rows: list[dict[str, Any]] = []
    for index in range(48):
        hour = START + index * HOUR
        rows += _event(hour, "h", "uid=a", n=(5 if index % 4 == 0 else 1))
    plain = observe(GridSearch(rows), INDEX, float(START), float(START + 48 * HOUR))
    series = {START + index * HOUR: (5 if index % 4 == 0 else 1) for index in range(48)}
    # One isolated hour on either side of the same periodic host.
    for far_hour in (START + 100_000 * HOUR, START - 100_000 * HOUR):
        with_far = rows + _event(far_hour, "h", "uid=a", n=7)
        window_start = min(START, far_hour)
        window_end = max(START + 48 * HOUR, far_hour + HOUR)
        contaminated = observe(GridSearch(with_far), INDEX, float(window_start), float(window_end))
        _same_shared(plain.observations, contaminated.observations)
        stray = dict(series)
        stray[far_hour] = 7
        primary = max(episodes(stray), key=lambda group: (len(group), -group[0]))
        assert primary == sorted(series)
        started = time.perf_counter()
        assert cycle_seconds(series) == cycle_seconds(stray) == 4 * HOUR
        assert time.perf_counter() - started < 1
    assert episodes({**series, START + 100_000 * HOUR: 7})[0] == sorted(series)
    assert episodes({START: 1, START + HOUR: 5}) == [[START, START + HOUR]]
    assert any(
        obs.evidence["seasonal_period"] == 4 * HOUR
        for obs in plain.observations
        if obs.kind == "volume"
    )


def test_cycle_span_over_the_effort_budget_is_not_densified(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.baselines.CYCLE_HOURS",
        8,
    )
    series = {index * HOUR: (5 if index % 4 == 0 else 1) for index in range(10)}

    assert cycle_seconds(series) is None


def test_reorder_uses_the_stored_scores(tmp_path: Any, monkeypatch: Any) -> None:
    rows: list[dict[str, Any]] = []
    for index in range(16):
        rows += _event(START + index * HOUR, "h", "uid=a", n=(1 if index % 2 == 0 else 100))
    end = float(START + 16 * HOUR)
    current = observe(GridSearch(rows), INDEX, float(START), end)
    seasonal = observe(GridSearch(rows), INDEX, float(START), end, baseline="seasonal")
    write_receipts(tmp_path, current, {"index": INDEX, "start": START, "end": end, "elapsed_s": 0})
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.observations.cycle_seconds",
        lambda _series: (_ for _ in ()).throw(AssertionError("recomputed")),
    )
    ordered = reorder(
        load_observations(tmp_path), "seasonal", current.coverage, current.request_kinds
    )

    assert [obs.score for obs in ordered.observations] == [
        obs.score for obs in seasonal.observations
    ]
    assert [obs.hour for obs in ordered.observations] == [obs.hour for obs in seasonal.observations]
    assert ordered.baseline == "seasonal"
    assert ordered.grids == {}


def test_peer_proportion_is_the_share_of_hosts_strictly_lower() -> None:
    hosts = ["h1", "h2", "h3"]
    assert peer_proportion(10, "h1", {"h1": 10, "h2": 1, "h3": 1}, hosts) == 1.0
    assert peer_proportion(10, "h1", {"h1": 10, "h2": 10, "h3": 10}, hosts) == 0.0
    assert peer_proportion(10, "h1", {"h1": 10}, ["h1"]) is None


def test_seasonal_uses_the_measured_phase_and_aperiodic_falls_back() -> None:
    alternating: list[dict[str, Any]] = []
    for index in range(16):
        count = 1 if index % 2 == 0 else 100
        hour = START + index * HOUR
        alternating += _event(hour, "h", "uid=a", n=count)
    end = float(START + 16 * HOUR)
    current = observe(GridSearch(alternating), INDEX, float(START), end)
    seasonal = observe(GridSearch(alternating), INDEX, float(START), end, baseline="seasonal")
    last = START + 15 * HOUR
    series = {START + index * HOUR: (1 if index % 2 == 0 else 100) for index in range(16)}
    phase = {hour: count for hour, count in series.items() if (last - hour) % (2 * HOUR) == 0}
    picked = _volume(seasonal.observations, "h", last)
    saved = _volume(current.observations, "h", last)

    assert saved.evidence["seasonal_period"] == 2 * HOUR
    assert saved.evidence["scores"]["seasonal"] == _ref_burst(phase, last)[0]
    assert saved.evidence["scores"]["current"] > saved.evidence["scores"]["seasonal"]
    assert picked.score == saved.evidence["scores"]["seasonal"]
    assert set(saved.evidence["scores"]) == {"current", "seasonal", "peer", "left"}

    ramp: list[dict[str, Any]] = []
    for index in range(10):
        hour = START + index * HOUR
        if index == 2:
            ramp += _event(hour, "h", "uid=a", punct=".", n=index)
            ramp += _event(hour, "h", "uid=a", punct="late", n=1)
        else:
            ramp += _event(hour, "h", "uid=a", n=index + 1)
    ramp_end = float(START + 10 * HOUR)
    fallen = observe(GridSearch(ramp), INDEX, float(START), ramp_end)
    held = observe(GridSearch(ramp), INDEX, float(START), ramp_end, baseline="left")
    first = _volume(fallen.observations, "h", START)
    late = next(obs for obs in fallen.observations if obs.entity == "late")

    assert first.evidence["seasonal_fallback"] == "no_cycle"
    assert first.evidence["scores"]["seasonal"] is None
    assert first.score == first.evidence["scores"]["current"]
    assert first.evidence["left_censored"] is True
    assert first.evidence["left_period_source"] == "one_bucket"
    assert first.evidence["mark"] == "first-seen at retention start"
    assert first.evidence["now"] != 0
    assert late.evidence["left_censored"] is False
    assert late.score == late.evidence["scores"]["current"]
    assert late.score is not None and late.score > 0
    withheld = _volume(held.observations, "h", START)
    assert withheld.score is None
    assert withheld.evidence["scores"]["current"] == first.evidence["scores"]["current"]


def test_measured_period_left_censors_only_the_opening_cycle() -> None:
    pattern = [8, 1, 1, 1] * 10
    rows: list[dict[str, Any]] = []
    for index, count in enumerate(pattern):
        hour = START + index * HOUR
        if index == 1:
            rows += _event(hour, "h", "uid=a", punct="early", n=count)
        elif index == 4:
            rows += _event(hour, "h", "uid=a", punct="late", n=1)
            rows += _event(hour, "h", "uid=a", punct=".", n=count - 1)
        else:
            rows += _event(hour, "h", "uid=a", punct=".", n=count)
    end = float(START + len(pattern) * HOUR)
    run = observe(GridSearch(rows), INDEX, float(START), end, baseline="left")
    early = next(obs for obs in run.observations if obs.entity == "early")
    late = next(obs for obs in run.observations if obs.entity == "late")
    bursts = [
        obs
        for obs in run.observations
        if obs.kind == "volume" and obs.evidence["signal"] == "burst"
    ]

    assert early.evidence["left_period"] == 4 * HOUR
    assert early.evidence["left_period_source"] == "cycle"
    assert early.evidence["left_censored"] is True
    assert early.score is None
    assert early.evidence["now"] != 0
    assert early.evidence["scores"]["current"] is not None
    assert late.evidence["left_censored"] is False
    assert late.score == late.evidence["scores"]["current"]
    assert late.score is not None and late.score > 0
    assert bursts
    assert all(obs.score is not None for obs in bursts)


def test_peer_scores_a_single_host_above_the_same_move_on_every_host() -> None:
    rows: list[dict[str, Any]] = []
    rows += _event(START, "h1", "uid=a", punct="P", n=9)
    rows += _event(START, "h2", "uid=a", punct="P", n=9)
    rows += _event(START, "h3", "uid=a", punct="P", n=1)
    rows += _event(START + HOUR, "h4", "uid=a", punct="P", n=4)
    lone = START + 2 * HOUR
    rows += _event(lone, "h1", "uid=a", punct="P", n=5)
    rows += _event(lone, "h2", "uid=a", punct="Q", n=5)
    rows += _event(lone, "h3", "uid=a", punct="Q", n=5)
    fleet = START + 3 * HOUR
    for host in ("h1", "h2", "h3"):
        rows += _event(fleet, host, "uid=a", punct="P", n=5)
    run = observe(GridSearch(rows), INDEX, float(START), float(START + 4 * HOUR))

    def shape(host: str, hour: int, entity: str) -> Observation:
        return next(
            obs
            for obs in run.observations
            if obs.kind == "shape"
            and obs.host == host
            and obs.hour == hour
            and obs.entity == entity
        )

    assert shape("h1", START, "P").evidence["scores"]["peer"] == 0.5
    assert shape("h3", START, "P").evidence["scores"]["peer"] == 0.0
    assert shape("h1", lone, "P").evidence["scores"]["peer"] == 1.0
    assert shape("h1", fleet, "P").evidence["scores"]["peer"] == 0.0
    alone = shape("h4", START + HOUR, "P")
    assert alone.evidence["scores"]["peer"] is None
    assert alone.evidence["peer_fallback"] == "no_peers"
    chosen = observe(
        GridSearch(rows), INDEX, float(START), float(START + 4 * HOUR), baseline="peer"
    )
    picked = next(
        obs
        for obs in chosen.observations
        if obs.kind == "shape" and obs.host == "h1" and obs.hour == lone
    )
    assert picked.score == 1.0


def test_stream_identity_joins_sourcetype_and_shape_not_the_file_name() -> None:
    rows: list[dict[str, Any]] = []
    rows += _event(START, "h", "uid=a", source="access.log", sourcetype="web", punct="::", n=2)
    rows += _event(
        START + HOUR, "h", "uid=a", source="access.log.1", sourcetype="web", punct="::", n=3
    )
    rows += _event(START + HOUR, "h", "uid=a", source="other", sourcetype="web", punct="xx", n=1)
    run = observe(GridSearch(rows), INDEX, float(START), float(START + 2 * HOUR))
    streams = [obs for obs in run.observations if obs.kind == "stream" and obs.entity == "web\t::"]
    sources = {obs.entity for obs in run.observations if obs.kind == "source"}

    assert {obs.hour: obs.evidence["now"] for obs in streams} == {START: 2, START + HOUR: 3}
    assert "access.log\tweb" in sources
    assert "access.log.1\tweb" in sources
    assert all("access.log" not in obs.entity for obs in run.observations if obs.kind == "stream")
    literal = streams[0].evidence["literal"]
    assert "sourcetype=" in literal
    assert "punct=" in literal
    assert "source=" not in literal
    streamed = observe(
        GridSearch(rows), INDEX, float(START), float(START + 2 * HOUR), baseline="stream"
    )
    assert [obs.score for obs in streamed.observations] == [obs.score for obs in run.observations]
    assert streamed.baseline == "stream"


def test_key_sample_is_deterministic_and_bounded_by_slices() -> None:
    def hours(per_hour: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index in range(9):
            hour = START + index * HOUR
            for copy in range(per_hour):
                rows += _event(hour, "h", f"p{index}=v uid=u{copy}")
        return rows

    base = hours(1)
    shuffled = list(base)
    random.Random(1).shuffle(shuffled)
    end = float(START + 9 * HOUR)
    first = observe(GridSearch(base), INDEX, float(START), end)
    second = observe(GridSearch(shuffled), INDEX, float(START), end)
    wider = observe(GridSearch(hours(5)), INDEX, float(START), end)
    indexes = [round(step * 8 / (KEY_SLICES - 1)) for step in range(KEY_SLICES)]
    seen = {obs.entity.split("=", 1)[0] for obs in first.observations if obs.kind == "value"}

    assert first.observations == second.observations
    assert first.request_kinds["key_sample"]["requests"] == KEY_SLICES
    assert (
        wider.request_kinds["key_sample"]["requests"]
        == first.request_kinds["key_sample"]["requests"]
    )
    assert seen == {f"p{index}" for index in indexes} | {"uid"}
    assert "p1" not in seen
    assert "slice_budget" in first.coverage["value"]["reasons"]
    assert first.coverage["value"]["complete"] is False
    censored = observe(GridSearch(base, censored="md5(_raw)"), INDEX, float(START), end)
    assert "censored" in censored.coverage["value"]["reasons"]
    assert censored.coverage["value"]["complete"] is False
    assert [obs for obs in censored.observations if obs.kind == "value"] == []


def test_raw_grids_round_trip_and_rescore_matches(tmp_path: Any) -> None:
    events = _universe()
    run = observe(GridSearch(events), INDEX, float(START), float(END))
    write_receipts(tmp_path, run, {"index": INDEX, "start": START, "end": END, "elapsed_s": 0})
    loaded, progress = load_receipts(tmp_path)
    volume_counts = sum(int(row["count"]) for row in loaded["volume"])

    assert loaded.keys() == run.grids.keys()
    assert "volume" not in {name for name, slot in run.coverage.items() if not slot["complete"]}
    assert volume_counts == len(events)
    assert "source" in loaded["source"][0]
    assert progress["grids"]["stream"] == "grids/stream.jsonl"
    assert rescore(loaded, progress["coverage"], INDEX, "current").observations == run.observations

    truncated = observe(
        GridSearch(events, truncate="by host _time"), INDEX, float(START), float(END)
    )
    assert "volume" not in truncated.grids
    assert "source" in truncated.grids
    assert truncated.coverage["value"]["reasons"] == ["volume_incomplete"]
    assert [obs for obs in truncated.observations if obs.kind == "value"] == []
