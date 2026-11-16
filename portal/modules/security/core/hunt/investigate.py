"""Investigation -- dig from a lead the way an analyst does, until the picture assembles.

An analyst does not know the vector up front. From something odd they pivot on its values,
look at every *kind* of event each value shows up in (not every event), notice the new odd
values those events carry, and keep pulling. Cases that turn out to share values are one story.

Generic only: a value is a token from the raw event; a "kind" of event is (host, source, punct);
a good pivot is rare in the environment yet recurs across several places (a value seen once is
a dead end, a value seen everywhere is background). Depth and breadth are effort budgets, not
decision thresholds -- they bound how long the analyst digs, never what counts as suspicious.
"""

from __future__ import annotations

import contextlib
import math
import re
import time
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .engine import (
    HOUR,
    Lead,
    Search,
    SearchBudgetExceededError,
    SearchCoverageCensoredError,
    _is_time_token,
    _literal_term_segments,
    _search_literal,
)

_TOKEN = re.compile(r"[A-Za-z0-9_.:/@%\-]{4,}")
# A value has at least one letter or digit; a run of punctuation ("........") is formatting.
# Found live on BOTS v1: such a pivot became a full-index plain search (>20 min).
_HAS_VALUE = re.compile(r"[A-Za-z0-9]")
_TERM_UNSAFE = re.compile(r"[\"\\=\[\]()|,;']")
CORE_EVENTS = 200  # effort budget: how many events the focused case core may hold
PER_KIND = 3  # effort budget: examples of any one kind of event shown in the core
TIMELINE_DAYS = 5  # effort budget: how many other days of a value's timeline are read
DAY = 86400
MAX_PLAN_CELLS = 500  # effort budget: indexed locations planned for one pivot
MAX_EVIDENCE_EVENTS = 500  # effort budget: raw examples retained for one pivot
CELL_QUERY_SIZE = 40  # effort budget: indexed cells represented in one raw request
SEED_SAMPLE = 400  # effort budget: events sampled per novel template when seeding tokens


@dataclass(frozen=True)
class RetrievalCell:
    host: str
    source: str
    start: int
    end: int
    indexed_count: int | None


@dataclass
class RetrievalPlan:
    token: str
    cells: tuple[RetrievalCell, ...]
    indexed_count: int | None
    verified_count: int | None = None
    count_semantics: str = "unknown"
    reason: str | None = None
    elapsed_s: float = 0.0
    work: dict[str, int] = field(default_factory=dict)
    censored: bool = False
    coverage_complete: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    events_loaded: bool = False


@dataclass
class Pivot:
    token: str
    count: int
    hosts: int
    sources: int
    depth: int
    weight: float
    indexed_count: int | None = None
    verified_count: int | None = None
    count_semantics: str = "unknown"
    coverage_reason: str | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)


def _via_pivot(via: Any, pivots: set[str]) -> str | None:
    token = str(via) if via else ""
    while token and token not in pivots:
        if token.startswith("timeline:"):
            token = token[len("timeline:") :]
        elif token.startswith("near:"):
            token = token[len("near:") :]
        else:
            break
    return token or None


def _take_core_event(
    queues: list[list[dict[str, Any]]],
    positions: list[int],
    active: list[int],
    taken: Counter[str],
) -> dict[str, Any] | None:
    while active:
        route_index = active.pop(0)
        queue = queues[route_index]
        while positions[route_index] < len(queue):
            event = queue[positions[route_index]]
            positions[route_index] += 1
            kind = event.get("kind") or f"{event['host']}|{event['source']}|{event['raw']}"
            if taken[kind] >= PER_KIND:
                continue
            taken[kind] += 1
            if positions[route_index] < len(queue):
                active.append(route_index)
            return event
    return None


@dataclass
class Case:
    seed: str
    seed_hour: int
    pivots: list[Pivot] = field(default_factory=list)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    merged_from: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    coverage: list[dict[str, Any]] = field(default_factory=list)
    # the seed leads' own windows: (host, bucket start, bucket end)
    seed_windows: list[tuple[str, int, int]] = field(default_factory=list)
    partial: bool = False  # evidence gathered before work ran out; never a whole-case claim

    @property
    def pivot_tokens(self) -> set[str]:
        return {p.token for p in self.pivots}

    def summary(self) -> dict[str, Any]:
        hosts = Counter(e["host"] for e in self.events.values())
        hours = sorted({int(e["time"]) // HOUR * HOUR for e in self.events.values()})
        core = self.core()
        return {
            "seed": self.seed,
            "merged_from": self.merged_from,
            "events": len(self.events),
            "core_events": len(core),
            "core_hosts": len({e["host"] for e in core}),
            "hosts": dict(hosts.most_common()),
            "sources": len({(e["host"], e["source"]) for e in self.events.values()}),
            "span_hours": (hours[-1] - hours[0]) // HOUR + 1 if hours else 0,
            "pivot_depths": dict(sorted(Counter(p.depth for p in self.pivots).items())),
            "degraded": self.degraded,
            "coverage": self.coverage,
            "partial": self.partial,
            "pivots": [p.__dict__ for p in self.pivots],
            "core": core,
            "picture": self.picture(),
        }

    def core(self, cap: int = CORE_EVENTS) -> list[dict[str, Any]]:
        """The case read outward from its seed leads, diversified by kind, in time order."""
        if cap <= 0:
            return []
        events = list(self.events.values())
        if not events:
            return []
        depth = {p.token: p.depth for p in self.pivots}
        pivot_tokens = set(depth)

        def in_seed(e: dict[str, Any]) -> bool:
            return any(h == e["host"] and lo <= e["time"] < hi for h, lo, hi in self.seed_windows)

        def order(e: dict[str, Any]) -> tuple[int, int, int, float]:
            token = _via_pivot(e.get("via"), pivot_tokens)
            # outward from the lead, as an analyst reads a case: what happened in the lead's own
            # window on its host first, then the closest pivots, then rarer kinds and specificity
            return (
                0 if in_seed(e) else 1,
                depth.get(token, 99) if token is not None else 99,
                int(e.get("kind_count") or 1),
                -float(e.get("weight", 0.0)),
            )

        routes: dict[int, dict[tuple[str, str | int], list[dict[str, Any]]]] = {0: {}, 1: {}}
        for index, event in enumerate(sorted(events, key=order)):
            priority = int(not in_seed(event))
            token = _via_pivot(event.get("via"), pivot_tokens)
            route = ("pivot", token) if token is not None else ("event", index)
            routes[priority].setdefault(route, []).append(event)

        queues = {priority: list(routes[priority].values()) for priority in (0, 1)}
        positions = {priority: [0] * len(queues[priority]) for priority in (0, 1)}
        active = {priority: list(range(len(queues[priority]))) for priority in (0, 1)}
        taken: Counter[str] = Counter()
        focused: list[dict[str, Any]] = []
        while len(focused) < cap:
            progressed = False
            for priority in (0, 1):
                picked = _take_core_event(
                    queues[priority], positions[priority], active[priority], taken
                )
                if picked is not None:
                    focused.append(picked)
                    progressed = True
                if len(focused) >= cap:
                    break
            if not progressed:
                break
        return sorted(focused, key=lambda e: e["time"])

    def picture(self, n: int = 25) -> list[dict[str, Any]]:
        """The analyst's view: the core's most specific events, in time order."""
        focused = sorted(
            ((float(e.get("weight", 0.0)), e) for e in self.core()), key=lambda we: -we[0]
        )
        return [e for _w, e in sorted(focused[:n], key=lambda we: we[1]["time"])]


_PART = re.compile(r"[:/=@]+")


def _tokens(raw: str) -> set[str]:
    """Whole tokens plus their parts: `www-data:msperl` is also `www-data` and `msperl`."""
    out: set[str] = set()
    for t in _TOKEN.findall(raw):
        for piece in (t, *_PART.split(t)):
            if (
                len(piece) >= 4
                and _HAS_VALUE.search(piece)
                and not _is_time_token(piece)
                and not _TERM_UNSAFE.search(piece)
            ):
                out.add(piece)
    return out


def _token_parts(raw: str) -> list[tuple[str, str, int]]:
    """Retain the whole observed value beside lexical parts and their slot position."""
    out = []
    for position, match in enumerate(_TOKEN.finditer(raw)):
        compound = match.group()
        for piece in (compound, *_PART.split(compound)):
            if (
                len(piece) >= 4
                and _HAS_VALUE.search(piece)
                and not _is_time_token(piece)
                and not _TERM_UNSAFE.search(piece)
            ):
                out.append((piece, compound, position))
    return out


def _raw_contains_token(raw: str, token: str) -> bool:
    return any(candidate == token for candidate, _compound, _position in _token_parts(raw))


def _rank_evidence_candidates(counts: Counter[str], n: int) -> list[str]:
    """Rank by observed recurrence while leaving selection to the explicit effort budget."""
    return [token for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]]


def _slot_variability(events: list[dict[str, Any]]) -> dict[str, float]:
    slots: dict[tuple[str, str, int], Counter[str]] = {}
    for event in events:
        shape = (str(event.get("source", "")), str(event.get("punct", "")))
        for token, _compound, position in _token_parts(str(event.get("_raw", ""))):
            slots.setdefault((*shape, position), Counter())[token] += 1
    return {
        token: max(
            (len(values) / sum(values.values()) for values in slots.values() if token in values),
            default=1.0,
        )
        for token in {token for values in slots.values() for token in values}
    }


def _where_literal(value: str) -> str:
    """A where-expression string literal: exact comparison, immune to * wildcard search."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _exhausted_reason(search: Search) -> str | None:
    """The shared hunt budget's exhaustion reason, when this search is budgeted."""
    reason = getattr(getattr(search, "budget", None), "exhausted", None)
    return str(reason) if reason else None


class Investigator:
    def __init__(self, search: Search, index: str, start: float, end: float) -> None:
        self.search, self.index, self.start, self.end = search, index, start, end
        index_q = _search_literal(index)
        rows = list(search.iter_post(f"| tstats count where index={index_q}", start, end))
        self.total = int(rows[0]["count"]) if rows else 1
        # Populated hours, not min..max span: a handful of events stamped with their ingest time
        # (no timestamp in their file) stretched Kyoushi's span from 6 days to ~5 years, shrank
        # this scale to ~550 and capped nearly every pivot to one identical weight (found live, P2).
        populated = list(
            search.iter_post(
                f"| tstats count where index={index_q} by _time span=1h | stats count",
                start,
                end,
            )
        )
        hours = max(1.0, float(populated[0]["count"])) if populated else 1.0
        # A value seen more often than an average populated hour of this environment is
        # background-scale; exact counting stops there (its weight is already low).
        self.background_scale = max(2, int(self.total / hours))
        self.degraded: list[str] = []
        self._plans: dict[tuple[str, float, float, str, str], RetrievalPlan] = {}
        self._footprints: dict[tuple[str, bool], tuple[int, int, int]] = {}
        self._handle_cells: dict[str, dict[tuple[str, str, int, int], RetrievalCell]] = {}
        self._observed: dict[str, set[RetrievalCell]] = {}
        self._compound_handles: dict[str, set[str]] = {}
        self._provenance: dict[str, list[dict[str, Any]]] = {}
        self.completed_cases: list[Case] = []
        self._stalled: Case | None = None
        q = f"| tstats count where index={index_q} by host source punct"
        self.template_count = {
            (r["host"], r["source"], r.get("punct", "")): int(r["count"])
            for r in self._rows(q, start, end)
        }

    def _rows(self, q: str, start: float, end: float) -> list[dict[str, Any]]:
        """Splunk returns multivalue fields as lists (found live on BOTS v1: the investigation
        crashed with `unhashable type: list`); a row is flattened to its first value per field."""
        return [
            {k: (v[0] if isinstance(v, list) and v else v) for k, v in r.items()}
            for r in self.search.iter_post(q, start, end)
        ]

    def _rows_many(self, requests: list[tuple[str, float, float]]) -> list[list[dict[str, Any]]]:
        """Read independent reproduction checks concurrently without changing their order."""
        if not requests:
            return []
        budget = getattr(getattr(self.search, "executor", None), "budget", None)
        concurrency = int(getattr(budget, "concurrency", 1))
        with ThreadPoolExecutor(max_workers=min(len(requests), concurrency)) as pool:
            return list(pool.map(lambda request: self._rows(*request), requests))

    def _rows_many_captured(
        self, requests: list[tuple[str, float, float]]
    ) -> list[tuple[list[dict[str, Any]] | None, Exception | None]]:
        """Keep independent query failures paired with their stable position."""

        def capture(
            request: tuple[str, float, float],
        ) -> tuple[list[dict[str, Any]] | None, Exception | None]:
            try:
                return self._rows(*request), None
            except Exception as exc:  # noqa: BLE001 -- the caller classifies each result
                return None, exc

        budget = getattr(getattr(self.search, "executor", None), "budget", None)
        concurrency = int(getattr(budget, "concurrency", 1))
        with ThreadPoolExecutor(max_workers=min(len(requests) or 1, concurrency)) as pool:
            return list(pool.map(capture, requests))

    @staticmethod
    def _cell_key(cell: RetrievalCell) -> tuple[str, str, int, int]:
        return cell.host, cell.source, cell.start, cell.end

    @staticmethod
    def _merge_cells(
        cells: dict[tuple[str, str, int, int], RetrievalCell],
        incoming: dict[tuple[str, str, int, int], RetrievalCell],
    ) -> None:
        for key, cell in incoming.items():
            prior = cells.get(key)
            count = max(cell.indexed_count or 0, (prior.indexed_count or 0) if prior else 0)
            cells[key] = RetrievalCell(cell.host, cell.source, cell.start, cell.end, count)

    def _term_cells(
        self, token: str, handles: set[str]
    ) -> tuple[dict[tuple[str, str, int, int], RetrievalCell], int]:
        index_q = _search_literal(self.index)
        cells: dict[tuple[str, str, int, int], RetrievalCell] = {}
        scans = 0
        pending: list[tuple[str, tuple[str, ...]]] = []
        for handle in sorted(handles):
            terms = _literal_term_segments(handle)
            if not terms:
                continue
            if self._handle_cells.get(handle) is None:
                pending.append((handle, terms))
        requests = [
            (
                f"| tstats count where index={index_q} "
                f"{' '.join(_search_literal(term) for term in terms)} "
                "by host source _time span=3600s",
                self.start,
                self.end,
            )
            for _handle, terms in pending
        ]
        for (handle, _terms), rows in zip(pending, self._rows_many(requests), strict=True):
            scans += 1
            scan: dict[tuple[str, str, int, int], RetrievalCell] = {}
            for row in rows:
                cell = self._cell(row)
                if cell is None:
                    continue
                key = self._cell_key(cell)
                prior = scan.get(key)
                count = max(cell.indexed_count or 0, (prior.indexed_count or 0) if prior else 0)
                scan[key] = RetrievalCell(cell.host, cell.source, cell.start, cell.end, count)
            self._handle_cells[handle] = scan
        for handle in sorted(handles):
            cached = self._handle_cells.get(handle)
            if cached is None:
                continue
            self._merge_cells(cells, cached)
        return cells, scans

    def _source_neighbors(
        self, sources: set[str]
    ) -> dict[tuple[str, str, int, int], RetrievalCell]:
        index_q = _search_literal(self.index)
        ordered = sorted(sources)
        requests = [
            (
                f"| tstats count where index={index_q} "
                f"source={_search_literal(source)} by host source _time span=3600s",
                self.start,
                self.end,
            )
            for source in ordered
        ]
        cells = {}
        for rows in self._rows_many(requests):
            for row in rows:
                cell = self._cell(row)
                if cell is not None:
                    cells[self._cell_key(cell)] = RetrievalCell(
                        cell.host, cell.source, cell.start, cell.end, None
                    )
        return cells

    def _host_neighbors(
        self, observed: set[RetrievalCell]
    ) -> dict[tuple[str, str, int, int], RetrievalCell]:
        index_q = _search_literal(self.index)
        cells = {}
        requests: list[tuple[str, float, float]] = []
        for host in sorted({cell.host for cell in observed}):
            for origin in sorted(
                (cell for cell in observed if cell.host == host), key=lambda cell: cell.start
            ):
                lo = max(int(self.start), origin.start - DAY)
                hi = min(int(self.end), origin.end + DAY)
                q = (
                    f"| tstats count where index={index_q} "
                    f"host={_search_literal(host)} _time>={lo} _time<{hi} "
                    "by host source _time span=3600s"
                )
                requests.append((q, lo, hi))
        for rows in self._rows_many(requests):
            for row in rows:
                cell = self._cell(row)
                if cell is not None:
                    cells[self._cell_key(cell)] = RetrievalCell(
                        cell.host, cell.source, cell.start, cell.end, None
                    )
        return cells

    def _expand_observed(
        self,
        token: str,
        observed: set[RetrievalCell],
        cells: dict[tuple[str, str, int, int], RetrievalCell],
        queries: int,
    ) -> tuple[int, str, bool]:
        """Seed a term miss from observed cells. Budget errors propagate; any other failure censors."""
        reason = "term_miss_seeded_from_observation"
        try:
            expanded = self._source_neighbors({cell.source for cell in observed})
            expanded.update(self._host_neighbors(observed))
            for cell_key, cell in expanded.items():
                cells.setdefault(cell_key, cell)
            queries += len({cell.source for cell in observed}) + len(observed)
        except SearchBudgetExceededError:
            raise  # shared effort ends the case; a censored lookup censors only itself
        except Exception as exc:  # noqa: BLE001 -- retain observed cells on failure
            self.degraded.append(f"neighborhood {token}: {type(exc).__name__}")
            return queries, "neighborhood_expansion_failed", True
        return queries, reason, False

    def _plan(self, token: str) -> RetrievalPlan:
        key = (self.index, self.start, self.end, token, "term-host-source-hour-v1")
        if key in self._plans:
            return self._plans[key]
        began = time.monotonic()
        handles = {token, *self._compound_handles.get(token, set())}
        try:
            term_cells, queries = self._term_cells(token, handles)
        except (SearchBudgetExceededError, SearchCoverageCensoredError):
            raise  # spent effort or censored coverage must surface, not degrade
        except Exception as exc:  # noqa: BLE001 -- failed discovery stays unknown
            term_cells, queries = {}, len(handles)
            self.degraded.append(f"indexed {token}: {type(exc).__name__}")
        observed = self._observed.get(token, set())
        cells = dict(term_cells)
        for cell in observed:
            cells.setdefault(self._cell_key(cell), cell)
        reason = None
        censored = False
        if not term_cells and observed:
            queries, reason, censored = self._expand_observed(token, observed, cells, queries)
        if not term_cells and not observed:
            reason = "no_indexed_or_observed_location"
        ordered = sorted(cells.values(), key=lambda cell: (cell.start, cell.host, cell.source))
        if len(ordered) > MAX_PLAN_CELLS:
            ordered = ordered[:MAX_PLAN_CELLS]
            reason = "cell_budget_exhausted"
            censored = True
        plan = RetrievalPlan(
            token=token,
            cells=tuple(ordered),
            indexed_count=sum(cell.indexed_count or 0 for cell in term_cells.values())
            if term_cells
            else None,
            count_semantics="indexed_estimate" if term_cells else "unknown",
            reason=reason or ("indexed_cells_have_unknown_raw_coverage" if term_cells else None),
            elapsed_s=round(time.monotonic() - began, 4),
            work={"queries": queries, "cells": len(ordered), "events": 0},
            censored=censored,
        )
        self._plans[key] = plan
        checkpoint = getattr(self.search, "checkpoint", None)
        if callable(checkpoint):
            checkpoint("investigating", pivot_delta=1)
        return plan

    @staticmethod
    def _cell(row: dict[str, Any]) -> RetrievalCell | None:
        if not row.get("host") or not row.get("source") or row.get("_time") is None:
            return None
        start = int(float(row["_time"])) // HOUR * HOUR
        return RetrievalCell(
            str(row["host"]),
            str(row["source"]),
            start,
            start + HOUR,
            int(row.get("count") or 0),
        )

    def _remember(
        self,
        token: str,
        event: dict[str, Any],
        compound: str,
        shape: tuple[str, str],
        slot: int,
    ) -> None:
        start = int(float(event.get("_time", self.start))) // HOUR * HOUR
        cell = RetrievalCell(
            str(event.get("host", "")), str(event.get("source", "")), start, start + HOUR, None
        )
        locations = self._observed.setdefault(token, set())
        new_location = bool(cell.host and cell.source and cell not in locations)
        if cell.host and cell.source:
            locations.add(cell)
        handles = self._compound_handles.setdefault(token, set())
        new_handle = compound != token and compound not in handles
        if compound != token:
            handles.add(compound)
        if new_location or new_handle:
            self._plans.pop(
                (self.index, self.start, self.end, token, "term-host-source-hour-v1"), None
            )
            self._footprints.pop((token, False), None)
            self._footprints.pop((token, True), None)
        self._provenance.setdefault(token, []).append(
            {
                "host": cell.host,
                "source": cell.source,
                "time": start,
                "shape": shape,
                "slot": slot,
                "compound": compound,
            }
        )

    def _events_for_plan(self, plan: RetrievalPlan) -> list[dict[str, Any]]:
        if plan.events_loaded:
            return plan.events
        plan.events_loaded = True
        if not plan.cells:
            return plan.events
        index_q = _search_literal(self.index)
        found: dict[tuple[str, str, float, str], dict[str, Any]] = {}
        requests: list[tuple[str, float, float]] = []
        for offset in range(0, len(plan.cells), CELL_QUERY_SIZE):
            group = plan.cells[offset : offset + CELL_QUERY_SIZE]
            scopes = " OR ".join(
                f"(host={_search_literal(cell.host)} source={_search_literal(cell.source)} "
                f"_time>={cell.start} _time<{cell.end})"
                for cell in group
            )
            q = (
                f"search index={index_q} ({scopes}) {_search_literal(plan.token)} "
                f"| head {MAX_EVIDENCE_EVENTS + 1} | table _time host source punct _raw"
            )
            lo = min(cell.start for cell in group)
            hi = max(cell.end for cell in group)
            requests.append((q, lo, hi))
        budget = getattr(getattr(self.search, "executor", None), "budget", None)
        concurrency = int(getattr(budget, "concurrency", 1))
        for offset in range(0, len(requests), concurrency):
            results = self._rows_many_captured(requests[offset : offset + concurrency])
            failed = False
            reached_cap = False
            for rows, error in results:
                if error is not None:
                    if isinstance(error, SearchBudgetExceededError):
                        raise error
                    plan.reason = f"raw_verification_failed:{type(error).__name__}"
                    plan.censored = True
                    self.degraded.append(f"evidence {plan.token}: {type(error).__name__}")
                    failed = True
                    break
                assert rows is not None
                reached_cap = self._remember_verified_rows(plan, rows, found)
                if reached_cap:
                    break
            if failed or reached_cap:
                break
        plan.events = list(found.values())[:MAX_EVIDENCE_EVENTS]
        plan.verified_count = len(plan.events)
        plan.work["events"] = len(plan.events)
        if plan.verified_count:
            plan.count_semantics = (
                "indexed_estimate_and_verified_sample"
                if plan.indexed_count is not None
                else "verified_local_sample_global_unknown"
            )
        return plan.events

    @staticmethod
    def _remember_verified_rows(
        plan: RetrievalPlan,
        rows: list[dict[str, Any]],
        found: dict[tuple[str, str, float, str], dict[str, Any]],
    ) -> bool:
        if len(rows) > MAX_EVIDENCE_EVENTS:
            plan.censored = True
            plan.reason = "event_budget_exhausted"
            rows = rows[:MAX_EVIDENCE_EVENTS]
        for row in rows:
            if not _raw_contains_token(str(row.get("_raw", "")), plan.token):
                continue
            key = (
                str(row.get("host", "")),
                str(row.get("source", "")),
                float(row.get("_time", 0.0)),
                str(row.get("_raw", "")),
            )
            found.setdefault(key, dict(row))
        if len(found) <= MAX_EVIDENCE_EVENTS:
            return False
        plan.censored = True
        plan.reason = "event_budget_exhausted"
        return True

    def _footprint_rows(self, token: str, exact: bool) -> list[dict[str, Any]]:
        plan = self._plan(token)
        if exact:
            events = self._events_for_plan(plan)
            counts = Counter((r["host"], r["source"]) for r in events)
        else:
            counts = Counter()
            for cell in plan.cells:
                if cell.indexed_count is not None:
                    counts[(cell.host, cell.source)] += cell.indexed_count
        return [
            {"host": host, "source": source, "count": count}
            for (host, source), count in counts.items()
        ]

    def footprint(self, token: str, *, exact: bool = False) -> tuple[int, int, int]:
        """Return an indexed estimate or verified local sample with its observed spread."""
        key = (token, exact)
        if key not in self._footprints:
            try:
                rows = self._footprint_rows(token, exact)
            except SearchBudgetExceededError:
                raise  # shared effort ends the case; a censored lookup censors only itself
            except Exception as exc:  # noqa: BLE001 -- one failed lookup degrades one pivot
                self.degraded.append(f"{token}: {type(exc).__name__}")
                rows = []
            self._footprints[key] = (
                sum(int(r["count"]) for r in rows),
                len({r["host"] for r in rows}),
                len({(r["host"], r["source"]) for r in rows}),
            )
        return self._footprints[key]

    def pivot_weight(self, token: str, *, exact: bool = False) -> float:
        """Rank from indexed estimates only; local samples never imply global rarity."""
        plan = self._plan(token)
        if exact:
            self._events_for_plan(plan)
        count = plan.indexed_count
        sources = len(
            {(cell.host, cell.source) for cell in plan.cells if cell.indexed_count is not None}
        )
        if count is None or count <= 0 or sources == 0 or plan.censored:
            return 0.0
        return math.log((self.total + 1) / (count + 1)) * math.log1p(sources)

    def kinds(self, token: str, per_kind: int = 2) -> list[dict[str, Any]]:
        """Return cached literal matches from indexed or observed cells only."""
        seen: Counter[tuple[str, str, str]] = Counter()
        out = []
        for row in self._events_for_plan(self._plan(token)):
            key = (str(row["host"]), str(row["source"]), str(row.get("punct", "")))
            if seen[key] < per_kind:
                seen[key] += 1
                out.append(row)
        return out

    def timeline(
        self, token: str, *, seed_day: int, days: int = TIMELINE_DAYS
    ) -> list[dict[str, Any]]:
        """Read other-day examples from the cached, localized evidence."""
        rows = self._events_for_plan(self._plan(token))
        per_hour: Counter[int] = Counter()
        for row in rows:
            t = int(float(row["_time"]))
            if t // 86400 != seed_day:
                per_hour[t // HOUR * HOUR] += 1
        blocks: list[tuple[int, int, int]] = []
        for hour in sorted(per_hour):
            if blocks and blocks[-1][1] == hour:
                lo, _hi, count = blocks[-1]
                blocks[-1] = (lo, hour + HOUR, count + per_hour[hour])
            else:
                blocks.append((hour, hour + HOUR, per_hour[hour]))
        out: list[dict[str, Any]] = []
        for lo, hi, _count in sorted(blocks, key=lambda block: -block[2])[:days]:
            self._timeline_kinds(token, lo, hi, out)
        return out

    def _token_evidence(
        self, case: Case, token: str, plan: RetrievalPlan, lead: Lead, weight: float
    ) -> tuple[Counter[str], list[dict[str, Any]], list[tuple[float, dict[str, Any]]]]:
        seen: Counter[str] = Counter()
        events: list[dict[str, Any]] = []
        reached: list[tuple[float, dict[str, Any]]] = []
        sources = [(self.kinds(token), token, True)] if plan.cells else []
        if weight > 0 or (plan.reason or "").startswith("term_miss_seeded"):
            sources.append(
                (self.timeline(token, seed_day=lead.hour // 86400), f"timeline:{token}", False)
            )
        for rows, via, is_reached in sources:
            for event in rows:
                self._remember_event(event)
                added = self._add(case, event, via=via, weight=weight)
                if is_reached:
                    reached.append((weight, added))
                events.append(event)
                seen.update(_tokens(str(event["_raw"])))
        return seen, events, reached

    def _remember_event(self, event: dict[str, Any]) -> None:
        for token, compound, position in _token_parts(str(event.get("_raw", ""))):
            shape = (str(event.get("source", "")), str(event.get("punct", "")))
            self._remember(token, event, compound, shape, position)

    def _timeline_kinds(self, token: str, lo: int, hi: int, out: list[dict[str, Any]]) -> None:
        out.extend(
            row
            for row in self._events_for_plan(self._plan(token))
            if lo <= float(row["_time"]) < hi
        )

    def neighborhood(
        self, event: dict[str, Any], *, minutes: int, kinds: int
    ) -> list[dict[str, Any]]:
        """What else happened on this host around this moment -- rarest kinds of event first.

        `minutes` is how far the analyst looks around, not a judgement of what is odd."""
        t = float(event["time"])
        q = (
            f"search index={_search_literal(self.index)} "
            f"host={_search_literal(str(event['host']))} "
            f"| dedup 2 source punct | head {MAX_EVIDENCE_EVENTS} "
            "| table _time host source punct _raw"
        )
        try:
            rows = [dict(r) for r in self._rows(q, t - 60 * minutes, t + 60 * minutes)]
        except SearchBudgetExceededError:
            raise  # shared effort ends the case; a censored lookup censors only itself
        except Exception as exc:  # noqa: BLE001 -- one failed look-around degrades, not fails
            self.degraded.append(f"near {event['host']}@{t:.0f}: {type(exc).__name__}")
            return []
        rows.sort(
            key=lambda r: self.template_count.get((r["host"], r["source"], r.get("punct", "")), 0)
        )
        return rows[:kinds]

    def score_candidates(
        self,
        tokens: Iterable[str],
        variability: dict[str, float] | None = None,
        recurrence: dict[str, int] | None = None,
    ) -> dict[str, float]:
        chosen = list(tokens)
        with ThreadPoolExecutor(max_workers=8) as pool:
            weights = list(pool.map(self.pivot_weight, chosen))
        return {
            token: weight
            * (variability.get(token, 1.0) if variability is not None else 1.0)
            * (math.log1p(recurrence.get(token, 0)) if recurrence is not None else 1.0)
            for token, weight in zip(chosen, weights, strict=True)
        }

    def seed_tokens(self, lead: Lead, examine: int) -> list[str]:
        """The lead's bursting values plus values from its never-before-seen kinds of event."""
        seeds = [b.token for b in lead.bursts if b.z > 0]
        if seeds:
            q = (
                f"| tstats count where index={_search_literal(self.index)} "
                f"host={_search_literal(lead.host)} _time>={lead.hour} "
                f"_time<{lead.hour + lead.span} by host source _time span=3600s"
            )
            for row in self._rows(q, lead.hour, lead.hour + lead.span):
                cell = self._cell(row)
                if cell is None:
                    continue
                location = {"host": cell.host, "source": cell.source, "_time": cell.start}
                for token in seeds:
                    self._remember(token, location, token, ("", ""), 0)
        events: list[dict[str, Any]] = []
        for source, punct, _ in lead.novel_templates[:10]:
            # Shape seeds have no source: restrict on host and the literal punct.
            where_source = f" source={_search_literal(source)}" if source else ""
            q = (
                f"search index={_search_literal(self.index)} "
                f"host={_search_literal(lead.host)}{where_source} "
                f"| where punct={_where_literal(str(punct))} "
                f"| head {SEED_SAMPLE + 1} "
                "| table _time host source punct _raw"
            )
            rows = self._rows(q, lead.hour, lead.hour + lead.span)
            if len(rows) > SEED_SAMPLE:
                self.degraded.append(f"seed sample truncated {lead.host}@{lead.hour} {source}")
                rows = rows[:SEED_SAMPLE]
            for row in rows:
                if str(row.get("punct", "")) != punct:
                    continue
                event = {**row, "host": lead.host, "source": source or str(row.get("source") or "")}
                events.append(event)
                for token, compound, position in _token_parts(str(row.get("_raw", ""))):
                    self._remember(token, event, compound, (source, str(punct)), position)
            if len(events) > 400:
                break
        candidates = Counter(t for e in events[:400] for t in _tokens(str(e.get("_raw", ""))))
        variability = _slot_variability(events[:400])
        considered = sorted(
            candidates,
            key=lambda token: (
                -variability.get(token, 1.0) * math.log1p(candidates[token]),
                token,
            ),
        )[:examine]
        scored = self.score_candidates(considered, variability, dict(candidates))
        seeds += [t for t, w in sorted(scored.items(), key=lambda kv: -kv[1]) if w > 0]
        return list(dict.fromkeys(seeds))

    def investigate(
        self,
        lead: Lead,
        *,
        depth: int = 3,
        breadth: int = 6,
        examine: int = 120,
        minutes: int = 15,
    ) -> Case:
        case = Case(
            seed=f"{lead.host}@{lead.hour}",
            seed_hour=lead.hour,
            seed_windows=[(lead.host, lead.hour, lead.hour + lead.span)],
            partial=True,  # in progress; reset only after the whole case is investigated
        )
        mark = len(self.degraded)
        self._stalled = None
        try:
            self._investigate_into(case, lead, depth, breadth, examine, minutes)
        except Exception:
            case.degraded = self.degraded[mark:]
            if case.pivots or case.events:
                self._stalled = case
            raise
        case.degraded = self.degraded[mark:]
        spent = _exhausted_reason(self.search)
        if spent:
            if case.pivots or case.events:
                self._stalled = case
            from .jobs import HuntBudgetExceededError  # jobs imports Investigator at module scope

            raise HuntBudgetExceededError(spent)
        case.partial = False
        return case

    def _investigate_into(
        self,
        case: Case,
        lead: Lead,
        depth: int,
        breadth: int,
        examine: int,
        minutes: int,
    ) -> None:
        frontier = self.seed_tokens(lead, examine)[:breadth]
        visited: set[str] = set()
        looked_around: set[tuple[str, float]] = set()
        for level in range(depth):
            seen_here: Counter[str] = Counter()
            seen_events: list[dict[str, Any]] = []
            reached: list[tuple[float, dict[str, Any]]] = []
            for token in frontier:
                if token in visited:
                    continue
                visited.add(token)
                count, hosts, sources = self.footprint(token, exact=True)
                weight = round(self.pivot_weight(token, exact=True), 2)
                plan = self._plan(token)
                case.pivots.append(
                    Pivot(
                        token,
                        count,
                        hosts,
                        sources,
                        level,
                        weight,
                        indexed_count=plan.indexed_count,
                        verified_count=plan.verified_count,
                        count_semantics=plan.count_semantics,
                        coverage_reason=plan.reason,
                        provenance=self._provenance.get(token, [])[:5],
                    )
                )
                case.coverage.append(self._coverage_row(plan))
                seen, events, token_reached = self._token_evidence(case, token, plan, lead, weight)
                seen_here.update({key: count for key, count in seen.items() if key not in visited})
                seen_events.extend(events)
                reached.extend(token_reached)
                checkpoint = getattr(self.search, "checkpoint", None)
                if callable(checkpoint):
                    # Persist at pivot boundaries AFTER evidence integration, carrying prior
                    # completed cases plus the in-progress one, so mid-run views never erase
                    # earlier cases or drop the newest events.
                    checkpoint("investigating", cases=[*self.completed_cases, case])
            # time/place pivot: around the most specific events this round, on their host
            for weight, ev in sorted(reached, key=lambda we: -we[0])[:breadth]:
                spot = (ev["host"], float(ev["time"]) // 60)
                if spot in looked_around:
                    continue
                looked_around.add(spot)
                for e in self.neighborhood(ev, minutes=minutes, kinds=breadth):
                    self._remember_event(e)
                    self._add(case, e, via=f"near:{ev['via']}", weight=weight)
                    seen_events.append(e)
                    seen_here.update(_tokens(str(e["_raw"])) - visited)
            candidates = _rank_evidence_candidates(seen_here, examine)
            scored = self.score_candidates(
                candidates, _slot_variability(seen_events), dict(seen_here)
            )
            frontier = [t for t, w in sorted(scored.items(), key=lambda kv: -kv[1]) if w > 0][
                :breadth
            ]
            if not frontier:
                break

    @staticmethod
    def _coverage_row(plan: RetrievalPlan) -> dict[str, Any]:
        return {
            "token": plan.token,
            "cells": len(plan.cells),
            "indexed_count": plan.indexed_count,
            "verified_count": plan.verified_count,
            "count_semantics": plan.count_semantics,
            "reason": plan.reason,
            "elapsed_s": plan.elapsed_s,
            "work": dict(plan.work),
            "censored": plan.censored,
            "coverage_complete": plan.coverage_complete,
        }

    def investigate_all(self, leads: list[Lead], *, dig: int) -> list[Case]:
        """Spend the explicit dig budget in the order already supplied by the ranker."""
        self.completed_cases = []
        checkpoint = getattr(self.search, "checkpoint", None)
        for rank, lead in enumerate(leads[: max(0, dig)], start=1):
            if callable(checkpoint):
                checkpoint("investigating", seed_rank=rank)
            self._stalled = None
            try:
                case = self.investigate(lead)
            except Exception:
                # Work ran out mid-case: persist the usable evidence gathered so far as an
                # explicitly partial case, then let the original exhaustion surface. The
                # checkpoint itself may raise on the spent wall clock -- it persists first,
                # and the terminal handler below also falls back to completed_cases.
                stalled = self._stalled
                if stalled is None:
                    raise
                stalled.partial = True
                self.completed_cases.append(stalled)
                if callable(checkpoint):
                    # A spent wall clock raises after the case is persisted; keep the original error.
                    with contextlib.suppress(Exception):
                        checkpoint("investigating", seed_rank=rank, cases=self.completed_cases)
                raise
            self.completed_cases.append(case)
            if callable(checkpoint):
                checkpoint(
                    "investigating",
                    seed_rank=rank,
                    cases=self.completed_cases,
                )
        return merge_cases(self.completed_cases)

    def _add(self, case: Case, e: dict[str, Any], *, via: str, weight: float) -> dict[str, Any]:
        key = f"{e['host']}|{e['source']}|{e['_raw']}"
        kind = (e["host"], e["source"], e.get("punct", ""))
        return case.events.setdefault(
            key,
            {
                "host": e["host"],
                "source": e["source"],
                "time": float(e["_time"]),
                "raw": e["_raw"],
                "via": via,
                "weight": weight,
                "kind": "|".join(kind),
                # how common this kind of event is in the environment (0 = unknown)
                "kind_count": self.template_count.get(kind, 0),
            },
        )


def _shared_pivots(a: Case, b: Case) -> set[str]:
    """A value worth merging two cases on: no more common than the less-specific case's median
    pivot count (relative, not a constant), and reached near a seed in at least one of them."""

    def median_count(case: Case) -> float:
        counts = sorted(p.count for p in case.pivots)
        return counts[len(counts) // 2] if counts else 0.0

    bar = min(median_count(a), median_count(b))
    pa = {p.token: p for p in a.pivots}
    pb = {p.token: p for p in b.pivots}
    return {
        token
        for token in pa.keys() & pb.keys()
        if min(pa[token].count, pb[token].count) <= bar
        and min(pa[token].depth, pb[token].depth) <= 1
    }


def merge_cases(cases: list[Case]) -> list[Case]:
    """Cases that pivoted through the same specific value are one story."""
    merged: list[Case] = []
    for case in cases:
        home = next((m for m in merged if _shared_pivots(m, case)), None)
        if home is None:
            case.merged_from = [case.seed]
            merged.append(case)
            continue
        home.merged_from.append(case.seed)
        home.degraded.extend(case.degraded)
        home.seed_windows.extend(case.seed_windows)
        home.coverage.extend(case.coverage)
        known = home.pivot_tokens
        home.pivots += [p for p in case.pivots if p.token not in known]
        for key, ev in case.events.items():
            home.events.setdefault(key, ev)
    return merged
