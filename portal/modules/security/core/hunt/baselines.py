"""Pure baselines over a saved count grid. No dataset thresholds and no fixed period."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from portal.modules.security.core.hunt.engine import HOUR, _burst

BASELINES = ("current", "seasonal", "peer", "stream", "left")
# Effort budget: densified hours in one episode. A longer episode is not scanned.
CYCLE_HOURS = 65536


def _above(value: float, other: float) -> bool:
    return value > other and not math.isclose(value, other)


def _correlations(samples: list[int]) -> dict[int, float]:
    """Pearson autocorrelation at every lag. One FFT, so the cost follows the series length."""
    width = len(samples)
    if width < 4:
        return {}
    values = np.asarray(samples, dtype=np.float64)
    transformed = np.fft.rfft(values, 1 << (2 * width - 1).bit_length())
    convolved = np.fft.irfft(transformed * np.conjugate(transformed))
    prefix = np.cumsum(values)
    squares = np.cumsum(values * values)
    found: dict[int, float] = {}
    for lag in range(1, width // 2 + 1):
        overlap = width - lag
        sum_left = float(prefix[overlap - 1])
        sum_right = float(prefix[width - 1] - prefix[lag - 1])
        sum_left_sq = float(squares[overlap - 1])
        sum_right_sq = float(squares[width - 1] - squares[lag - 1])
        var_left = sum_left_sq - (sum_left * sum_left) / overlap
        var_right = sum_right_sq - (sum_right * sum_right) / overlap
        if var_left <= 0 or var_right <= 0:
            continue
        covariance = float(convolved[lag]) - (sum_left * sum_right) / overlap
        found[lag] = covariance / math.sqrt(var_left * var_right)
    return found


def _is_peak(lag: int, value: float, corr: Mapping[int, float], max_lag: int) -> bool:
    # A cycle repeats, so the lag is at least two buckets.
    if lag < 2 or value <= 0:
        return False
    earlier = corr.get(lag - 1)
    if earlier is None or not _above(value, earlier):
        return False
    later = corr.get(lag + 1)
    if later is None:
        return lag == max_lag
    return _above(value, later)


def cycle_lag(samples: list[int]) -> int | None:
    """Shortest lag tied for the strongest positive autocorrelation peak."""
    corr = _correlations(samples)
    if not corr:
        return None
    max_lag = max(corr)
    peaks = [lag for lag, value in corr.items() if _is_peak(lag, value, corr, max_lag)]
    if not peaks:
        return None
    best = max(corr[lag] for lag in peaks)
    tied = [lag for lag in peaks if math.isclose(corr[lag], best)]
    return min(tied)


def _split_at_majority(hours: list[int]) -> list[list[int]]:
    """Split where one unoccupied stretch is strictly more of this series' timeline than the rest."""
    if len(hours) < 2:
        return [hours] if hours else []
    cut: int | None = None
    widest = -1
    last = len(hours) - 1
    for index in range(last):
        gap = hours[index + 1] - hours[index] - HOUR
        others = (hours[index] - hours[0]) + (hours[last] - hours[index + 1])
        if gap > others and gap > widest:
            widest = gap
            cut = index
    if cut is None:
        return [hours]
    return _split_at_majority(hours[: cut + 1]) + _split_at_majority(hours[cut + 1 :])


def episodes(series: Mapping[int, int]) -> list[list[int]]:
    """Observed hours split into episodes. Empty hours are not points on the timeline."""
    hours = sorted(hour for hour, count in series.items() if count > 0)
    return _split_at_majority(hours)


def _primary(groups: list[list[int]]) -> list[int]:
    return max(groups, key=lambda group: (len(group), -group[0]))


def dense_counts(series: Mapping[int, int]) -> list[int]:
    """Hourly counts across the primary episode, with its own missing hours as zeros."""
    groups = episodes(series)
    if not groups:
        return []
    chosen = _primary(groups)
    start, stop = chosen[0], chosen[-1]
    width = (stop - start) // HOUR + 1
    if width > CYCLE_HOURS:
        return []
    return [int(series.get(start + step * HOUR, 0)) for step in range(width)]


def cycle_seconds(series: Mapping[int, int]) -> int | None:
    """Measured host cycle in seconds, or None when the primary episode has no peak."""
    lag = cycle_lag(dense_counts(series))
    if lag is None:
        return None
    return lag * HOUR


def peer_proportion(
    now: int, host: str, counts: Mapping[str, int], active: Iterable[str]
) -> float | None:
    """Fraction of other hosts active this hour whose count is strictly lower."""
    others = [name for name in active if name != host]
    if not others:
        return None
    lower = sum(1 for name in others if int(counts.get(name, 0)) < now)
    return lower / len(others)


def phase_counts(series: Mapping[int, int], hour: int, period: int) -> dict[int, int] | None:
    """Positive counts at this hour's phase. None when that phase has no history."""
    picked: dict[int, int] = {hour: int(series[hour])}
    cursor = hour - period
    floor = min(series)
    while cursor >= floor:
        count = int(series.get(cursor, 0))
        if count > 0:
            picked[cursor] = count
        cursor -= period
    if len(picked) < 2:
        return None
    return picked


def phase_burst(entity: str, hour: int, series: Mapping[int, int], period: int) -> float | None:
    """Burst z against the same phase of a measured cycle. None when the phase is empty."""
    phased = phase_counts(series, hour, period)
    if phased is None:
        return None
    burst = _burst(entity, hour, phased)
    if burst is None:
        return None
    return burst.z


def index_volume(rows: list[dict[str, Any]]) -> dict[str, dict[int, int]]:
    grouped: dict[str, dict[int, int]] = {}
    for row in rows:
        host = str(row["host"])
        hour = int(float(row["_time"])) // HOUR * HOUR
        bucket = grouped.setdefault(host, {})
        bucket[hour] = bucket.get(hour, 0) + int(float(row["count"]))
    return grouped


def _entity(kind: str, row: Mapping[str, Any], key: str) -> str:
    if kind == "volume":
        return ""
    if kind == "source":
        return f"{row['source']}\t{row['sourcetype']}"
    if kind == "shape":
        return str(row["punct"])
    if kind == "stream":
        return f"{row['sourcetype']}\t{row['punct']}"
    value = row.get("v", row.get(f"{key}=", ""))
    return f"{key}={value}"


def index_entities(
    kind: str, rows: list[dict[str, Any]], key: str = ""
) -> dict[tuple[str, str], dict[int, int]]:
    grouped: dict[tuple[str, str], dict[int, int]] = {}
    for row in rows:
        ident = (str(row["host"]), _entity(kind, row, key))
        hour = int(float(row["_time"])) // HOUR * HOUR
        bucket = grouped.setdefault(ident, {})
        bucket[hour] = bucket.get(hour, 0) + int(float(row["count"]))
    return grouped


def active_hosts(volume: Mapping[str, Mapping[int, int]]) -> dict[int, set[str]]:
    found: dict[int, set[str]] = {}
    for host, series in volume.items():
        for hour, count in series.items():
            if count > 0:
                found.setdefault(hour, set()).add(host)
    return found


def counts_by_hour(
    grouped: Mapping[tuple[str, str], Mapping[int, int]],
) -> dict[tuple[str, int], dict[str, int]]:
    found: dict[tuple[str, int], dict[str, int]] = {}
    for (host, entity), series in grouped.items():
        for hour, count in series.items():
            found.setdefault((entity, hour), {})[host] = count
    return found
