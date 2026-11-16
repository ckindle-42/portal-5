"""Bounded event evidence for the highest-ranked layer-one host-hour cells."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .engine import HOUR, _literal_term_segments, _search_literal
from .executor import HuntBudgetExceededError, HuntExecutor
from .identity import host_filter
from .observations import Observation, literal_matches

EVIDENCE_REQUESTS = 100  # effort budget: evidence reads issued through the shared executor
JUDGE_CELLS = 50  # effort budget: host-hours judged from the accumulated order
MAX_OBSERVATIONS_PER_CELL = 12  # effort budget: top literal observations shown for one cell
CANDIDATE_OBSERVATIONS = (
    48  # effort budget: observations named in the one read, above the number shown
)
EVENTS_PER_OBSERVATION = 2  # effort budget: matching events retained for one observation
# Rows one cell read may return. 160 judged cells stay inside the 5,000-event budget.
ROW_BUDGET = MAX_OBSERVATIONS_PER_CELL * EVENTS_PER_OBSERVATION
MAX_EVENT_CHARACTERS = 300  # effort budget: raw characters retained per event
EVIDENCE_KIND = "evidence"


@dataclass(frozen=True)
class EvidenceCell:
    host: str
    hour: int
    l1_rank: int
    observations: tuple[Observation, ...]
    budget_rank: int = 0
    risk: float = 0.0
    acc_rank: int = 0
    host_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceRead:
    cell: EvidenceCell
    evidence: list[dict[str, Any]]
    censored: bool
    reason: str | None
    seconds: float
    evidence_selection: str = "strongest"


@dataclass(frozen=True)
class _ReadPlan:
    named: tuple[Observation, ...]
    shape_count: int
    selection: str
    breadth: bool


def evidence_cells(observations: Iterable[Observation]) -> list[EvidenceCell]:
    """Collapse the layer-one total order to one bounded record per host-hour."""
    grouped: dict[tuple[str, int], list[Observation]] = {}
    for observation in observations:
        grouped.setdefault((observation.host, observation.hour), []).append(observation)
    cells = []
    for rank, ((host, hour), rows) in enumerate(grouped.items(), 1):
        aliases = sorted(
            {
                str(name)
                for observation in rows
                for name in observation.evidence.get("host_aliases", [])
            }
        )
        selected = [
            observation
            for observation in rows
            if observation.evidence.get("literal") and observation.kind != "volume"
        ]
        cells.append(
            EvidenceCell(
                host,
                hour,
                rank,
                tuple(selected),
                host_aliases=tuple(aliases) if len(aliases) > 1 else (),
            )
        )
    return cells


def _positive_score(score: float | None) -> float:
    if score is None or score <= 0:
        return 0.0
    return float(score)


def accumulated_host_hours(observations: Iterable[Observation]) -> list[EvidenceCell]:
    """One host-hour: risk is the sum of positive scores, ties keep layer-1 rank."""
    rows = list(observations)
    base = evidence_cells(rows)
    totals: dict[tuple[str, int], float] = {}
    for observation in rows:
        key = (observation.host, observation.hour)
        totals[key] = totals.get(key, 0.0) + _positive_score(observation.score)
    ranked = sorted(base, key=lambda cell: (-totals[(cell.host, cell.hour)], cell.l1_rank))
    place = {(cell.host, cell.hour): rank for rank, cell in enumerate(ranked, 1)}
    return [
        EvidenceCell(
            cell.host,
            cell.hour,
            cell.l1_rank,
            cell.observations,
            risk=totals[(cell.host, cell.hour)],
            acc_rank=place[(cell.host, cell.hour)],
            host_aliases=cell.host_aliases,
        )
        for cell in ranked
    ]


def _searchmatch_term(entity: str) -> str:
    predicates = []
    for segment in _literal_term_segments(entity):
        quoted = _search_literal(segment)
        embedded = quoted.replace("\\", "\\\\").replace('"', '\\"')
        predicates.append(f'searchmatch("{embedded}")')
    return " AND ".join(predicates)


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
        terms = _literal_term_segments(entity)
        if not terms:
            return None
        return " ".join(_search_literal(term) for term in terms), _searchmatch_term(entity)
    return None


def _query_tail(breadth_first: bool) -> str:
    """Row cap is unchanged. Breadth keeps one event of each shape before a second."""
    table = "| table _time source sourcetype punct _hunt_observation _raw"
    if not breadth_first:
        return (
            "| sort 0 _hunt_observation _time _raw "
            "| dedup _hunt_observation _raw "
            f"| dedup {EVENTS_PER_OBSERVATION} _hunt_observation "
            f"| head {ROW_BUDGET} "
            f"{table}"
        )
    return (
        "| sort 0 _hunt_observation _time _raw "
        "| dedup _hunt_observation _raw "
        "| streamstats count as _hunt_nth by _hunt_observation "
        f"| where _hunt_nth<={EVENTS_PER_OBSERVATION} "
        "| sort 0 _hunt_nth _hunt_observation _time _raw "
        f"| head {ROW_BUDGET} "
        f"{table}"
    )


def _cell_query(
    index: str,
    host: str,
    observations: Sequence[Observation],
    *,
    breadth_first: bool,
    host_aliases: Sequence[str] = (),
) -> str | None:
    """One read of the candidate observations, capped at the rows the judge can show."""
    searches: list[str] = []
    cases: list[str] = []
    for observation_index, observation in enumerate(observations):
        built = _observation_tests(observation)
        if built is None:
            continue
        search, eval_test = built
        searches.append(f"({search})")
        cases.append(f"({eval_test}),{observation_index}")
    if not searches:
        return None
    return (
        f"search index={_search_literal(index)} {host_filter(host, host_aliases, _search_literal)} "
        f"({' OR '.join(searches)}) "
        f"| eval _hunt_observation=case({', '.join(cases)}) "
        f"| where isnotnull(_hunt_observation) "
        f"{_query_tail(breadth_first)}"
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


def _owns(row: Mapping[str, Any], observation_index: int, query: str, *, marker: bool) -> bool:
    if marker:
        found = row.get("_hunt_observation")
        if found is not None and found != "":
            try:
                return int(float(found)) == observation_index
            except (TypeError, ValueError):
                return False
    return literal_matches(row, query)


def _matching_indexes(
    ordered: Sequence[Mapping[str, Any]],
    used: set[int],
    observation_index: int,
    query: str,
    *,
    marker: bool,
) -> list[int]:
    return [
        index
        for index, row in enumerate(ordered)
        if index not in used and _owns(row, observation_index, query, marker=marker)
    ]


def _emit_lines(
    evidence: list[dict[str, Any]],
    ordered: Sequence[Mapping[str, Any]],
    indexes: Iterable[int],
    query: str,
    earliest: float,
    latest: float,
    event_chars: int,
    used: set[int],
) -> None:
    for index in indexes:
        used.add(index)
        evidence.append(
            {
                "line": _event_line(ordered[index], event_chars),
                "query": query,
                "earliest": earliest,
                "latest": latest,
            }
        )


def _select_evidence(
    rows: Iterable[Mapping[str, Any]],
    observations: Sequence[Observation],
    earliest: float,
    latest: float,
    event_chars: int,
    *,
    marker: bool = True,
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
        picked = _matching_indexes(ordered, used, observation_index, str(query), marker=marker)[
            :EVENTS_PER_OBSERVATION
        ]
        if not picked:
            continue
        shown += 1
        _emit_lines(evidence, ordered, picked, str(query), earliest, latest, event_chars, used)
    return evidence


def _select_breadth(
    rows: Iterable[Mapping[str, Any]],
    observations: Sequence[Observation],
    earliest: float,
    latest: float,
    event_chars: int,
) -> list[dict[str, Any]]:
    """One event for each shape before any shape contributes a second."""
    ordered = sorted(rows, key=_row_sort_key)
    used: set[int] = set()
    evidence: list[dict[str, Any]] = []
    kept: list[tuple[int, str]] = []
    for observation_index, observation in enumerate(observations):
        if len(kept) >= MAX_OBSERVATIONS_PER_CELL:
            break
        query = observation.evidence.get("literal")
        if not query:
            continue
        picked = _matching_indexes(ordered, used, observation_index, str(query), marker=True)[:1]
        if not picked:
            continue
        kept.append((observation_index, str(query)))
        _emit_lines(evidence, ordered, picked, str(query), earliest, latest, event_chars, used)
    for _extra in range(max(0, EVENTS_PER_OBSERVATION - 1)):
        for observation_index, query in kept:
            picked = _matching_indexes(ordered, used, observation_index, query, marker=True)[:1]
            if picked:
                _emit_lines(evidence, ordered, picked, query, earliest, latest, event_chars, used)
    return evidence


def _prior_count(evidence: Mapping[str, Any]) -> int:
    prior = evidence.get("prior")
    return len(prior) if isinstance(prior, list) else 0


def _active_share(evidence: Mapping[str, Any]) -> float:
    count = _prior_count(evidence)
    active = evidence.get("prior_hours_active")
    if active is None or count == 0:
        return 0.0
    return float(active) / float(count)


def _rarity_key(item: tuple[int, Observation]) -> tuple[int, float, int]:
    index, observation = item
    evidence = observation.evidence
    novelty = 0 if evidence.get("signal") == "novelty" else 1
    return (novelty, _active_share(evidence), index)


def _shape_observations(observations: Sequence[Observation]) -> tuple[Observation, ...]:
    indexed = [
        (index, observation)
        for index, observation in enumerate(observations)
        if observation.kind == "shape" and _observation_tests(observation) is not None
    ]
    indexed.sort(key=_rarity_key)
    return tuple(observation for _index, observation in indexed)


def _with_fillers(cell: EvidenceCell, shapes: Sequence[Observation]) -> tuple[Observation, ...]:
    chosen: list[Observation] = list(shapes)
    seen = {id(item) for item in chosen}
    for observation in cell.observations:
        if len(chosen) >= CANDIDATE_OBSERVATIONS:
            break
        if id(observation) in seen:
            continue
        chosen.append(observation)
        seen.add(id(observation))
    return tuple(chosen)


def _plan(cell: EvidenceCell, mode: str) -> _ReadPlan:
    if mode != "rarest":
        return _ReadPlan(cell.observations[:CANDIDATE_OBSERVATIONS], 0, "strongest", False)
    shapes = _shape_observations(cell.observations)[:CANDIDATE_OBSERVATIONS]
    if not shapes:
        return _ReadPlan(cell.observations[:CANDIDATE_OBSERVATIONS], 0, "strongest", False)
    return _ReadPlan(_with_fillers(cell, shapes), len(shapes), "rarest", True)


def _empty_read(
    cell: EvidenceCell, reason: str, censored: bool, seconds: float, selection: str
) -> EvidenceRead:
    return EvidenceRead(cell, [], censored, reason, seconds, selection)


def _chosen_read(
    cell: EvidenceCell,
    found: list[dict[str, Any]],
    reason: str | None,
    seconds: float,
    selection: str,
) -> EvidenceRead:
    if not found:
        return _empty_read(cell, str(reason or "empty_evidence"), bool(reason), seconds, selection)
    return EvidenceRead(
        cell, found, bool(reason), str(reason) if reason else None, seconds, selection
    )


def _from_rows(
    cell: EvidenceCell,
    plan: _ReadPlan,
    rows: Iterable[Mapping[str, Any]],
    earliest: float,
    latest: float,
    event_chars: int,
    reason: str | None,
    seconds: float,
) -> EvidenceRead:
    if plan.selection == "rarest":
        found = _select_breadth(rows, plan.named[: plan.shape_count], earliest, latest, event_chars)
        if found:
            return _chosen_read(cell, found, reason, seconds, "rarest")
        found = _select_evidence(
            rows, cell.observations, earliest, latest, event_chars, marker=False
        )
        return _chosen_read(cell, found, reason, seconds, "strongest")
    found = _select_evidence(rows, plan.named, earliest, latest, event_chars)
    return _chosen_read(cell, found, reason, seconds, "strongest")


def read_cell(
    executor: HuntExecutor,
    index: str,
    cell: EvidenceCell,
    start: float,
    end: float,
    *,
    event_chars: int = MAX_EVENT_CHARACTERS,
    evidence_mode: str = "rarest",
) -> EvidenceRead:
    """Read a cell once. Each event is kept for the first observation it matches."""
    began = time.monotonic()
    earliest, latest = max(start, float(cell.hour)), min(end, float(cell.hour + HOUR))
    plan = _plan(cell, evidence_mode)
    if latest <= earliest:
        return _empty_read(cell, "outside_window", False, 0.0, plan.selection)
    if not plan.named:
        return _empty_read(cell, "no_narrowing_observations", False, 0.0, plan.selection)
    query = _cell_query(
        index,
        cell.host,
        plan.named,
        breadth_first=plan.breadth,
        host_aliases=cell.host_aliases,
    )
    if query is None:
        return _empty_read(cell, "no_narrowing_observations", False, 0.0, plan.selection)
    try:
        result = executor.read(query, earliest, latest, kind=EVIDENCE_KIND, row_cap=None)
    except HuntBudgetExceededError as exc:
        return _empty_read(cell, str(exc), True, round(time.monotonic() - began, 3), plan.selection)
    except Exception as exc:  # noqa: BLE001 -- record failed coverage for this cell
        return _empty_read(
            cell,
            f"read_failed:{type(exc).__name__}",
            True,
            round(time.monotonic() - began, 3),
            plan.selection,
        )
    return _from_rows(
        cell,
        plan,
        list(getattr(result, "rows", [])),
        earliest,
        latest,
        event_chars,
        getattr(result, "reason", None),
        round(time.monotonic() - began, 3),
    )


def read_cells(
    executor: HuntExecutor,
    index: str,
    cells: Iterable[EvidenceCell],
    start: float,
    end: float,
    *,
    event_chars: int = MAX_EVENT_CHARACTERS,
    evidence_mode: str = "rarest",
) -> list[EvidenceRead]:
    """Read cells concurrently under the executor's existing shared budget and deadline."""
    ordered = list(cells)
    concurrency = getattr(getattr(executor, "budget", None), "concurrency", 1)
    with ThreadPoolExecutor(max_workers=min(len(ordered) or 1, concurrency)) as pool:
        futures = [
            pool.submit(
                read_cell,
                executor,
                index,
                cell,
                start,
                end,
                event_chars=event_chars,
                evidence_mode=evidence_mode,
            )
            for cell in ordered
        ]
        return [future.result() for future in futures]
