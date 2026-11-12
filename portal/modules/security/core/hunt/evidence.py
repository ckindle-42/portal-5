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
CANDIDATE_OBSERVATIONS = (
    48  # effort budget: observations named in the one read, above the number shown
)
EVENTS_PER_OBSERVATION = 2  # effort budget: matching events retained for one observation
# Rows one cell read may return. 160 judged cells stay inside the 5,000-event budget.
ROW_BUDGET = MAX_OBSERVATIONS_PER_CELL * EVENTS_PER_OBSERVATION
MAX_EVENT_CHARACTERS = 300  # effort budget: raw characters retained per event
READ_CONCURRENCY = 6  # effort budget: evidence reads inside the shared executor
EVIDENCE_KIND = "evidence"


@dataclass(frozen=True)
class EvidenceCell:
    host: str
    hour: int
    l1_rank: int
    observations: tuple[Observation, ...]
    budget_rank: int = 0


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
            if observation.evidence.get("literal") and observation.kind != "volume"
        ]
        cells.append(EvidenceCell(host, hour, rank, tuple(selected)))
    return cells


def _searchmatch_term(entity: str) -> str:
    quoted = _search_literal(entity)
    embedded = quoted.replace("\\", "\\\\").replace('"', '\\"')
    return f'searchmatch("TERM({embedded})")'


def _observation_tests(observation: Observation) -> tuple[str, str] | None:
    """Search predicate and eval equality. Both quote through `_search_literal`."""
    entity = observation.entity
    if observation.kind == "shape":
        test = f"punct={_search_literal(entity)}"
        return test, test
    if observation.kind == "source" and "\t" in entity:
        source, sourcetype = entity.split("\t", 1)
        search = f"source={_search_literal(source)} sourcetype={_search_literal(sourcetype)}"
        eval_test = f"source={_search_literal(source)} AND sourcetype={_search_literal(sourcetype)}"
        return search, eval_test
    if observation.kind == "stream" and "\t" in entity:
        sourcetype, punct = entity.split("\t", 1)
        search = f"sourcetype={_search_literal(sourcetype)} punct={_search_literal(punct)}"
        eval_test = f"sourcetype={_search_literal(sourcetype)} AND punct={_search_literal(punct)}"
        return search, eval_test
    if observation.kind == "value" and entity:
        return f"TERM({_search_literal(entity)})", _searchmatch_term(entity)
    return None


def _cell_query(index: str, cell: EvidenceCell) -> str | None:
    """One read of the candidate observations, capped at the rows the judge can show."""
    searches: list[str] = []
    cases: list[str] = []
    for observation_index, observation in enumerate(cell.observations[:CANDIDATE_OBSERVATIONS]):
        built = _observation_tests(observation)
        if built is None:
            continue
        search, eval_test = built
        searches.append(f"({search})")
        cases.append(f"({eval_test}),{observation_index}")
    if not searches:
        return None
    return (
        f"search index={_search_literal(index)} host={_search_literal(cell.host)} "
        f"({' OR '.join(searches)}) "
        f"| eval _hunt_observation=case({', '.join(cases)}) "
        f"| where isnotnull(_hunt_observation) "
        f"| sort 0 _hunt_observation _time _raw "
        f"| dedup _hunt_observation _raw "
        f"| dedup {EVENTS_PER_OBSERVATION} _hunt_observation "
        f"| head {ROW_BUDGET} "
        f"| table _time source sourcetype punct _hunt_observation _raw"
    )


def _event_line(row: Mapping[str, Any], event_chars: int) -> str:
    source = str(row.get("source", "")).replace("\r", " ").replace("\n", " ")
    raw = str(row.get("_raw", "")).replace("\r", " ").replace("\n", " ")
    raw = raw[:event_chars]
    return f"{source} | {raw}"


def _row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    try:
        stamp = float(row.get("_time", 0))
    except (TypeError, ValueError):
        stamp = 0.0
    return (
        stamp,
        str(row.get("_raw", "")),
        str(row.get("source", "")),
        str(row.get("punct", "")),
        str(row.get("sourcetype", "")),
    )


def _owns(row: Mapping[str, Any], observation_index: int, query: str) -> bool:
    marker = row.get("_hunt_observation")
    if marker is not None and marker != "":
        try:
            return int(float(marker)) == observation_index
        except (TypeError, ValueError):
            return False
    return literal_matches(row, query)


def _select_evidence(
    rows: Iterable[Mapping[str, Any]],
    observations: tuple[Observation, ...],
    earliest: float,
    latest: float,
    event_chars: int,
) -> list[dict[str, Any]]:
    """First matching observation owns each event. A repeat spends no observation slot."""
    ordered = sorted(rows, key=_row_sort_key)
    used: set[int] = set()
    evidence: list[dict[str, Any]] = []
    shown = 0
    for observation_index, observation in enumerate(observations):
        if shown >= MAX_OBSERVATIONS_PER_CELL:
            break
        query = observation.evidence.get("literal")
        if not query:
            continue
        picked = [
            index
            for index, row in enumerate(ordered)
            if index not in used and _owns(row, observation_index, str(query))
        ][:EVENTS_PER_OBSERVATION]
        if not picked:
            continue
        shown += 1
        for index in picked:
            used.add(index)
            evidence.append(
                {
                    "line": _event_line(ordered[index], event_chars),
                    "query": str(query),
                    "earliest": earliest,
                    "latest": latest,
                }
            )
    return evidence


def read_cell(
    executor: HuntExecutor,
    index: str,
    cell: EvidenceCell,
    start: float,
    end: float,
    *,
    event_chars: int = MAX_EVENT_CHARACTERS,
) -> EvidenceRead:
    """Read a cell once. Each event is kept for the first observation it matches."""
    began = time.monotonic()
    earliest, latest = max(start, float(cell.hour)), min(end, float(cell.hour + HOUR))
    if latest <= earliest:
        return EvidenceRead(cell, [], False, "outside_window", 0.0)
    if not cell.observations:
        return EvidenceRead(cell, [], False, "no_narrowing_observations", 0.0)
    query = _cell_query(index, cell)
    if query is None:
        return EvidenceRead(cell, [], False, "no_narrowing_observations", 0.0)
    try:
        result = executor.read(query, earliest, latest, kind=EVIDENCE_KIND, row_cap=None)
    except HuntBudgetExceededError as exc:
        return EvidenceRead(cell, [], True, str(exc), round(time.monotonic() - began, 3))
    except Exception as exc:  # noqa: BLE001 -- record failed coverage for this cell
        return EvidenceRead(
            cell, [], True, f"read_failed:{type(exc).__name__}", round(time.monotonic() - began, 3)
        )
    seconds = round(time.monotonic() - began, 3)
    reason = getattr(result, "reason", None)
    evidence = _select_evidence(
        list(getattr(result, "rows", [])),
        cell.observations,
        earliest,
        latest,
        event_chars,
    )
    if not evidence:
        return EvidenceRead(cell, [], bool(reason), str(reason or "empty_evidence"), seconds)
    return EvidenceRead(cell, evidence, bool(reason), str(reason) if reason else None, seconds)


def read_cells(
    executor: HuntExecutor,
    index: str,
    cells: Iterable[EvidenceCell],
    start: float,
    end: float,
    *,
    event_chars: int = MAX_EVENT_CHARACTERS,
) -> list[EvidenceRead]:
    """Read cells concurrently under the executor's existing shared budget and deadline."""
    ordered = list(cells)
    with ThreadPoolExecutor(max_workers=READ_CONCURRENCY) as pool:
        futures = [
            pool.submit(read_cell, executor, index, cell, start, end, event_chars=event_chars)
            for cell in ordered
        ]
        return [future.result() for future in futures]
