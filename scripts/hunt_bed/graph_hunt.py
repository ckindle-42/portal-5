#!/usr/bin/env python3
"""Read-only live hunt: layer-1 observations choose cells, cell samples build the entity graph."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from portal.modules.security.core.hunt import graph as _graph  # noqa: E402
from portal.modules.security.core.hunt.baselines import BASELINES  # noqa: E402
from portal.modules.security.core.hunt.engine import HOUR  # noqa: E402
from portal.modules.security.core.hunt.executor import HuntBudgetExceededError  # noqa: E402
from portal.modules.security.core.hunt.observations import (  # noqa: E402
    Observation,
    ObservationRun,
    budgeted_search,
    literal_query,
    load_observations,
    observe,
    reorder,
)
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402

_executor: Any = None  # the run's HuntExecutor: observations and cell reads share one budget


def _reader() -> Any:
    """The run's executor, switched to the evidence phase so cell reads spend `events`."""
    global _executor
    if _executor is None:
        window = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
        _executor = budgeted_search(window).executor
    budget = getattr(_executor, "budget", None)
    if budget is not None:
        budget.phase = "investigating"
    return _executor


CELL_BUDGET = 24  # effort budget: host-hours read, 24 x 200 events stays inside one hunt budget
EVENTS_PER_CELL = 200  # effort budget: md5-ordered events sampled from one host-hour
BASELINE_HOURS = 2  # effort budget: a chosen cell's own prior hours, nearest first
READ_KIND = "events"  # executor budget kind for one raw evidence read
ORDER = (
    "observations in their total order (-score, kind, host, entity, signal, hour); for each, "
    "its own cell first and then its prior hours nearest first; a (host, hour) is read once, "
    "with the literal of the first observation that chose it"
)


@dataclass(frozen=True)
class Cell:
    host: str
    hour: int
    kind: str
    entity: str
    literal: str
    rank: int
    baseline: bool


@dataclass(frozen=True)
class CellRead:
    cell: Cell
    query: str
    rows: list[dict[str, Any]]
    censored: bool
    reason: str | None
    seconds: float
    stopped: bool = False  # the shared budget or job deadline ended reading here


def _prior_hours(obs: Observation) -> list[int]:
    prior = obs.evidence.get("prior") or []
    hours = sorted((int(row["hour"]) for row in prior if row.get("hour") is not None), reverse=True)
    return hours[:BASELINE_HOURS]


def cell_plan(index: str, observations: Iterable[Observation]) -> list[Cell]:
    """The cells to read, in the one documented total order, cut at the cell budget."""
    plan: list[Cell] = []
    seen: set[tuple[str, int]] = set()
    for rank, obs in enumerate(observations):
        if len(plan) >= CELL_BUDGET:
            break
        literal = literal_query(obs.kind, index, obs.host, obs.entity)
        wanted = [(obs.hour, False), *((hour, True) for hour in _prior_hours(obs))]
        for hour, baseline in wanted:
            if len(plan) >= CELL_BUDGET:
                break
            if (obs.host, hour) in seen:
                continue
            seen.add((obs.host, hour))
            plan.append(Cell(obs.host, hour, obs.kind, obs.entity, literal, rank, baseline))
    return plan


def _sample_query(literal: str) -> str:
    # md5 order makes the sample deterministic; any learned value is already a literal where.
    return (
        f"{literal} | eval _k=md5(_raw) | sort {EVENTS_PER_CELL} _k _time _raw "
        f"| head {EVENTS_PER_CELL} | table _time host source _raw"
    )


def read_cell(cell: Cell) -> CellRead:
    query = _sample_query(cell.literal)
    began = time.monotonic()
    try:
        result = _reader().read(
            query,
            float(cell.hour),
            float(cell.hour + HOUR),
            kind=READ_KIND,
            row_cap=EVENTS_PER_CELL,
        )
    except HuntBudgetExceededError as exc:  # shared budget or job deadline spent: stop reading
        return CellRead(cell, query, [], True, str(exc) or "budget", 0.0, stopped=True)
    return CellRead(
        cell=cell,
        query=query,
        rows=[dict(row) for row in result.rows],
        censored=bool(result.censored),
        reason=None if result.reason is None else str(result.reason),
        seconds=round(time.monotonic() - began, 3),
    )


def _flat(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (value[0] if isinstance(value, list) and value else value)
        for key, value in row.items()
    }


def samples(reads: Iterable[CellRead]) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    """Cell event samples keyed (host, source, hour), each event {_time, host, source, _raw}."""
    found: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, float, str]] = set()
    for read in reads:
        for raw in read.rows:
            row = _flat(raw)
            key = (
                str(row.get("host", "")),
                str(row.get("source", "")),
                float(row.get("_time") or 0.0),
                str(row.get("_raw", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            host, source, moment, body = key
            hour = int(moment) // HOUR * HOUR
            found.setdefault((host, source, hour), []).append(
                {"_time": moment, "host": host, "source": source, "_raw": body}
            )
    return found


def _slot(reads: list[CellRead]) -> dict[str, Any]:
    return {
        "requests": len(reads),
        "seconds": round(sum(read.seconds for read in reads), 3),
        "censored": sum(1 for read in reads if read.censored),
    }


def progress_payload(
    meta: Mapping[str, Any],
    run: ObservationRun,
    plan: list[Cell],
    reads: list[CellRead],
    wall_seconds: float,
) -> dict[str, Any]:
    censored = sum(1 for read in reads if read.censored)
    complete = run.coverage_complete and censored == 0 and len(reads) == len(plan)
    return {
        **meta,
        "wall_seconds": wall_seconds,
        "budgets": {
            "cells": CELL_BUDGET,
            "events_per_cell": EVENTS_PER_CELL,
            "baseline_hours": BASELINE_HOURS,
        },
        "order": ORDER,
        "coverage_complete": complete,
        "coverage": {
            "observation_complete": run.coverage_complete,
            "cells_planned": len(plan),
            "cells_read": len(reads),
            "cells_censored": censored,
            "reasons": sorted({str(read.reason) for read in reads if read.reason}),
        },
        "request_kinds": {READ_KIND: _slot(reads)},
        "observation_request_kinds": run.request_kinds,
        "observation_coverage": run.coverage,
        "observation_count": len(run.observations),
        "cell_count": len(reads),
        "event_count": sum(len(read.rows) for read in reads),
        "modules": {"graph": _graph.__name__, "executor": type(_executor).__name__},
    }


def cell_row(read: CellRead) -> dict[str, Any]:
    return {
        "host": read.cell.host,
        "hour": read.cell.hour,
        "kind": read.cell.kind,
        "entity": read.cell.entity,
        "rank": read.cell.rank,
        "baseline": read.cell.baseline,
        "events": len(read.rows),
        "censored": read.censored,
        "reason": read.reason,
        "seconds": read.seconds,
        "query": read.query,
    }


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return str(value)


def _lead_row(notable: Any) -> dict[str, Any]:
    lead = notable.as_lead()
    if isinstance(lead, Mapping):
        return dict(lead)
    return asdict(lead) if is_dataclass(lead) and not isinstance(lead, type) else dict(vars(lead))


def notable_row(notable: Any) -> dict[str, Any]:
    to_dict = getattr(notable, "as_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {"lead": _lead_row(notable), "evidence": getattr(notable, "evidence", None)}


def _lines(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    body = "".join(json.dumps(dict(row), sort_keys=True, default=_jsonable) + "\n" for row in rows)
    path.write_text(body)


def write_run(
    out: Path,
    leads: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    progress: dict[str, Any],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "leads.json").write_text(
        json.dumps({"leads": leads}, indent=1, default=_jsonable) + "\n"
    )
    _lines(out / "notables.jsonl", rows)
    _lines(out / "cells.jsonl", cells)
    (out / "progress.json").write_text(json.dumps(progress, indent=1, sort_keys=True) + "\n")


def observation_run(args: argparse.Namespace) -> tuple[ObservationRun, dict[str, Any]]:
    """Layer 1 live, or a saved observations.jsonl reordered onto --baseline."""
    if args.from_grids:
        saved_dir = Path(args.from_grids)
        saved = json.loads((saved_dir / "progress.json").read_text())
        if saved.get("index") not in (None, args.index):
            raise SystemExit(f"--index {args.index} does not match saved index {saved['index']}")
        run = reorder(
            load_observations(saved_dir),
            args.baseline,
            saved.get("coverage"),
            saved.get("request_kinds"),
        )
        meta = {
            "index": args.index,
            "start": saved.get("start"),
            "end": saved.get("end"),
            "baseline": run.baseline,
            "from_grids": str(saved_dir),
        }
        return run, meta
    end = time.time() if args.end is None else args.end
    window = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
    global _executor
    search = budgeted_search(window)
    if _executor is None:
        _executor = search.executor
    run = observe(search, args.index, args.start, end, baseline=args.baseline)
    meta = {
        "index": args.index,
        "start": args.start,
        "end": end,
        "baseline": run.baseline,
        "from_grids": "",
    }
    return run, meta


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--out", required=True, help="directory for leads/notables/cells/progress")
    parser.add_argument(
        "--from-grids", default=None, help="reuse a saved observations.jsonl; does not re-observe"
    )
    parser.add_argument("--baseline", default="current", choices=BASELINES)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse()
    started = time.monotonic()
    run, meta = observation_run(args)
    plan = cell_plan(args.index, run.observations)
    reads: list[CellRead] = []
    for cell in plan:
        reads.append(read_cell(cell))
        if reads[-1].stopped:
            break
    graph = _graph.build(samples(reads))
    notables = list(_graph.notables(graph, run.observations))
    leads = [_lead_row(notable) for notable in notables]
    rows = [notable_row(notable) for notable in notables]
    progress = progress_payload(meta, run, plan, reads, round(time.monotonic() - started, 1))
    progress["lead_count"] = len(leads)
    progress["notable_count"] = len(rows)
    write_run(Path(args.out), leads, rows, [cell_row(read) for read in reads], progress)
    print(
        f"{len(leads)} leads from {len(reads)}/{len(plan)} cells "
        f"({progress['coverage']['cells_censored']} censored), "
        f"coverage_complete={progress['coverage_complete']} in {progress['wall_seconds']}s "
        f"-> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
