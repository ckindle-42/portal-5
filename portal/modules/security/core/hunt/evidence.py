"""Bounded event evidence for the highest-ranked layer-one host-hour cells."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .engine import HOUR, _search_literal
from .executor import HuntBudgetExceededError, HuntExecutor
from .observations import Observation, literal_matches

EVIDENCE_REQUESTS = 100  # effort budget: evidence reads issued through the shared executor
JUDGE_CELLS = EVIDENCE_REQUESTS  # effort budget: at most one read for each judged host-hour
MAX_OBSERVATIONS_PER_CELL = 12  # effort budget: top literal observations shown for one cell
EVENTS_PER_OBSERVATION = 2  # effort budget: matching events retained for one observation
MAX_EVENT_CHARACTERS = 300  # effort budget: raw characters retained per event
READ_CONCURRENCY = 6  # effort budget: evidence reads inside the shared executor
EVIDENCE_KIND = "evidence"
_ROW_CAP = MAX_OBSERVATIONS_PER_CELL * EVENTS_PER_OBSERVATION  # effort budget: rows per cell read


@dataclass(frozen=True)
class EvidenceCell:
    host: str
    hour: int
    l1_rank: int
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class EvidenceRead:
    cell: EvidenceCell
    evidence: list[dict[str, Any]]
    censored: bool
    reason: str | None
    seconds: float


def evidence_cells(observations: Iterable[Observation]) -> list[EvidenceCell]:
    """Collapse the layer-one total order to one bounded record per host-hour."""
    grouped: dict[tuple[str, int], list[Observation]] = {}
    for observation in observations:
        grouped.setdefault((observation.host, observation.hour), []).append(observation)
    cells = []
    for rank, ((host, hour), rows) in enumerate(grouped.items(), 1):
        selected = [
            observation
            for observation in rows
            if observation.evidence.get("literal") and _condition(observation) is not None
        ]
        cells.append(EvidenceCell(host, hour, rank, tuple(selected[:MAX_OBSERVATIONS_PER_CELL])))
    return cells


def _condition(observation: Observation) -> str | None:
    entity = observation.entity
    if observation.kind == "volume":
        return None
    if observation.kind == "shape":
        return f"punct={_search_literal(entity)}"
    if observation.kind == "source":
        source, sourcetype = entity.split("\t", 1)
        return f"source={_search_literal(source)} sourcetype={_search_literal(sourcetype)}"
    if observation.kind == "stream":
        sourcetype, punct = entity.split("\t", 1)
        return f"sourcetype={_search_literal(sourcetype)} punct={_search_literal(punct)}"
    if observation.kind == "value":
        return f"TERM({_search_literal(entity)})"
    return None


def _query(index: str, cell: EvidenceCell) -> str:
    branches = []
    for observation_index, observation in enumerate(cell.observations):
        condition = _condition(observation)
        if condition is None:
            continue
        base = (
            f"search index={_search_literal(index)} host={_search_literal(cell.host)} {condition}"
        )
        branches.append(
            f"{base} | sort 0 _time _raw source punct sourcetype "
            f"| head {EVENTS_PER_OBSERVATION} | eval _hunt_observation={observation_index}"
        )
    query = branches[0]
    for branch in branches[1:]:
        query += f" | append [ {branch} ]"
    return query + " | sort 0 _hunt_observation _time _raw source punct sourcetype"


def _event_line(row: Mapping[str, Any]) -> str:
    source = str(row.get("source", "")).replace("\r", " ").replace("\n", " ")
    raw = str(row.get("_raw", "")).replace("\r", " ").replace("\n", " ")
    raw = raw[:MAX_EVENT_CHARACTERS]
    return f"{source} | {raw}"


def read_cell(
    executor: HuntExecutor,
    index: str,
    cell: EvidenceCell,
    start: float,
    end: float,
) -> EvidenceRead:
    """Read a cell once and preserve only lines that match its selected observations."""
    began = time.monotonic()
    earliest, latest = max(start, float(cell.hour)), min(end, float(cell.hour + HOUR))
    if latest <= earliest:
        return EvidenceRead(cell, [], False, "outside_window", 0.0)
    if not cell.observations:
        return EvidenceRead(cell, [], False, "no_narrowing_observations", 0.0)
    try:
        result = executor.read(
            _query(index, cell), earliest, latest, kind=EVIDENCE_KIND, row_cap=_ROW_CAP
        )
    except HuntBudgetExceededError as exc:
        return EvidenceRead(cell, [], True, str(exc), round(time.monotonic() - began, 3))
    except Exception as exc:  # noqa: BLE001 -- record failed coverage for this cell
        return EvidenceRead(
            cell, [], True, f"read_failed:{type(exc).__name__}", round(time.monotonic() - began, 3)
        )
    seconds = round(time.monotonic() - began, 3)
    reason = getattr(result, "reason", None)
    rows = list(getattr(result, "rows", []))
    evidence: list[dict[str, Any]] = []
    for observation_index, observation in enumerate(cell.observations):
        query = str(observation.evidence["literal"])
        matched = [row for row in rows if _matches_observation(row, observation_index, query)]
        for row in matched[:EVENTS_PER_OBSERVATION]:
            evidence.append(
                {
                    "line": _event_line(row),
                    "query": query,
                    "earliest": earliest,
                    "latest": latest,
                }
            )
    if not evidence:
        return EvidenceRead(cell, [], bool(reason), str(reason or "empty_evidence"), seconds)
    return EvidenceRead(cell, evidence, bool(reason), str(reason) if reason else None, seconds)


def _matches_observation(row: Mapping[str, Any], index: int, query: str) -> bool:
    marker = row.get("_hunt_observation")
    if marker is None:
        return literal_matches(row, query)
    try:
        return int(marker) == index
    except (TypeError, ValueError):
        return False


def read_cells(
    executor: HuntExecutor,
    index: str,
    cells: Iterable[EvidenceCell],
    start: float,
    end: float,
) -> list[EvidenceRead]:
    """Read cells concurrently under the executor's existing shared budget and deadline."""
    ordered = list(cells)
    with ThreadPoolExecutor(max_workers=READ_CONCURRENCY) as pool:
        futures = [pool.submit(read_cell, executor, index, cell, start, end) for cell in ordered]
        return [future.result() for future in futures]
