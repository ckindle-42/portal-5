#!/usr/bin/env python3
"""Rank every layer-one host-hour by a fixed local-model judgement of its evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from portal.modules.security.core.hunt.baselines import BASELINES  # noqa: E402
from portal.modules.security.core.hunt.engine import HOUR  # noqa: E402
from portal.modules.security.core.hunt.evidence import (  # noqa: E402
    EVENTS_PER_OBSERVATION,
    EVIDENCE_REQUESTS,
    JUDGE_CELLS,
    MAX_EVENT_CHARACTERS,
    MAX_OBSERVATIONS_PER_CELL,
    evidence_cells,
    read_cells,
)
from portal.modules.security.core.hunt.judge import (  # noqa: E402
    OpenAICompatibleClient,
    judge_cell,
)
from portal.modules.security.core.hunt.observations import (  # noqa: E402
    ObservationRun,
    budgeted_search,
    load_observations,
    observe,
    reorder,
)
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402

ORDER = (
    "judged cells by descending P(yes), ties by layer-one rank; then unjudged and "
    "beyond-budget cells by layer-one rank"
)


def _window(args: argparse.Namespace) -> tuple[ObservationRun, dict[str, Any], Any]:
    """Observe live or load saved layer-one output, then return its shared executor."""
    window = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
    search = budgeted_search(window)
    if args.from_grids:
        directory = Path(args.from_grids)
        saved = json.loads((directory / "progress.json").read_text())
        if saved.get("index") not in (None, args.index):
            raise SystemExit(f"--index {args.index} does not match saved index {saved['index']}")
        run = reorder(
            load_observations(directory),
            args.baseline,
            saved.get("coverage"),
            saved.get("request_kinds"),
        )
        start = args.start if args.start is not None else saved.get("start")
        end = args.end if args.end is not None else saved.get("end")
        if start is None or end is None:
            raise SystemExit("saved observations need --start and --end for bounded evidence reads")
        meta = {
            "index": args.index,
            "start": float(start),
            "end": float(end),
            "baseline": run.baseline,
            "from_grids": str(directory),
        }
    else:
        start = 0.0 if args.start is None else float(args.start)
        end = time.time() if args.end is None else float(args.end)
        run = observe(search, args.index, start, end, baseline=args.baseline)
        meta = {
            "index": args.index,
            "start": start,
            "end": end,
            "baseline": run.baseline,
            "from_grids": "",
        }
    search.executor.budget.phase = "investigating"
    return run, meta, search.executor


def _endpoint(url: str) -> str:
    suffix = "/v1/chat/completions"
    return url.rstrip("/") if url.rstrip("/").endswith(suffix) else url.rstrip("/") + suffix


def _compact_observations(cell: Any) -> list[dict[str, Any]]:
    return [
        {
            "kind": observation.kind,
            "entity": observation.entity,
            "hour": observation.hour,
            "score": observation.score,
            "signal": observation.evidence.get("signal"),
            "literal": observation.evidence.get("literal"),
        }
        for observation in cell.observations
    ]


def _executor_delta(
    before: Mapping[str, Mapping[str, Any]], after: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for kind, slot in after.items():
        old = before.get(kind, {})
        requests = int(slot.get("requests", 0)) - int(old.get("requests", 0))
        if requests:
            found[kind] = {
                "requests": requests,
                "seconds": round(
                    float(slot.get("seconds", 0.0)) - float(old.get("seconds", 0.0)), 3
                ),
                "censored": int(slot.get("censored", 0)) - int(old.get("censored", 0)),
            }
    return found


def _observation_cost(run: ObservationRun, saved: bool) -> dict[str, Any]:
    kinds = run.request_kinds
    return {
        "requests": sum(int(slot.get("requests", 0)) for slot in kinds.values()),
        "seconds": round(sum(float(slot.get("seconds", 0.0)) for slot in kinds.values()), 3),
        "request_kinds": kinds,
        "source": "saved_receipt" if saved else "live_run",
    }


def _lead(
    cell: Any,
    *,
    result: Any = None,
    evidence: list[dict[str, Any]] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "host": cell.host,
        "hour": cell.hour,
        "span": HOUR,
        "p_yes": result.p_yes if result is not None else None,
        "l1_rank": cell.l1_rank,
        "judged": bool(result is not None and result.p_yes is not None),
        "reason": reason if result is None or result.p_yes is None else None,
        "evidence": evidence or [],
        "observations": _compact_observations(cell),
    }


def _coverage(
    leads: list[dict[str, Any]], total: int, beyond: list[dict[str, Any]]
) -> dict[str, Any]:
    unjudged = [
        {key: lead[key] for key in ("host", "hour", "l1_rank", "reason")}
        for lead in leads
        if not lead["judged"] and lead["reason"] != "beyond_judge_cell_budget"
    ]
    return {
        "cells_total": total,
        "cells_judged": sum(bool(lead["judged"]) for lead in leads),
        "cells_unjudged": len(unjudged),
        "unjudged": unjudged,
        "cells_beyond_budget": len(beyond),
        "beyond_budget": beyond,
    }


def _judge_selected(
    client: Any,
    model: str,
    selected: list[Any],
    reads_by_cell: Mapping[tuple[str, int], Any],
) -> tuple[dict[tuple[str, int], tuple[Any, Any]], dict[str, Any], set[str]]:
    judged: dict[tuple[str, int], tuple[Any, Any]] = {}
    seconds = 0.0
    attempts = 0
    served: set[str] = set()
    for cell in selected:
        read = reads_by_cell[(cell.host, cell.hour)]
        if read.reason is not None:
            continue
        verdict = judge_cell(client, model=model, evidence=read.evidence)
        attempts += 1
        seconds += verdict.seconds
        if verdict.served_model:
            served.add(verdict.served_model)
        judged[(cell.host, cell.hour)] = (read, verdict)
    return judged, {"requests": attempts, "seconds": round(seconds, 3)}, served


def _ordered_leads(
    cells: list[Any],
    reads_by_cell: Mapping[tuple[str, int], Any],
    judged: Mapping[tuple[str, int], tuple[Any, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    leads_by_cell: dict[tuple[str, int], dict[str, Any]] = {}
    for cell in cells:
        key = (cell.host, cell.hour)
        if key not in reads_by_cell:
            leads_by_cell[key] = _lead(cell, reason="beyond_judge_cell_budget")
            continue
        read = reads_by_cell[key]
        if read.reason is not None:
            leads_by_cell[key] = _lead(cell, reason=read.reason)
            continue
        evidence_read, verdict = judged[key]
        leads_by_cell[key] = _lead(
            cell,
            result=verdict,
            evidence=evidence_read.evidence if verdict.p_yes is not None else [],
            reason=verdict.reason,
        )
    scored = sorted(
        (lead for lead in leads_by_cell.values() if lead["judged"]),
        key=lambda lead: (-float(lead["p_yes"]), int(lead["l1_rank"])),
    )
    unresolved = sorted(
        (lead for lead in leads_by_cell.values() if not lead["judged"]),
        key=lambda lead: int(lead["l1_rank"]),
    )
    beyond = [
        {
            "host": lead["host"],
            "hour": lead["hour"],
            "l1_rank": lead["l1_rank"],
            "reason": lead["reason"],
        }
        for lead in unresolved
        if lead["reason"] == "beyond_judge_cell_budget"
    ]
    return scored + unresolved, scored, beyond


def run_judged_hunt(
    args: argparse.Namespace,
    *,
    prepare: Callable[[argparse.Namespace], tuple[ObservationRun, dict[str, Any], Any]] = _window,
    client: Any = None,
) -> dict[str, Any]:
    """Compose observation, evidence and judgement stages and write bounded receipts."""
    began = time.monotonic()
    run, meta, executor = prepare(args)
    cells = evidence_cells(run.observations)
    selected = cells[: min(JUDGE_CELLS, EVIDENCE_REQUESTS)]
    if client is None:
        api_key = os.environ.get(args.judge_key_env) if args.judge_key_env else None
        client = OpenAICompatibleClient(_endpoint(args.judge_url), api_key)
    before = executor.stats()
    reads = read_cells(executor, args.index, selected, float(meta["start"]), float(meta["end"]))
    after = executor.stats()
    evidence_cost = _executor_delta(before, after)
    reads_by_cell = {(read.cell.host, read.cell.hour): read for read in reads}
    judged, judged_cost, served_models = _judge_selected(
        client, args.judge_model, selected, reads_by_cell
    )
    leads, scored, beyond = _ordered_leads(cells, reads_by_cell, judged)
    coverage = _coverage(leads, len(cells), beyond)
    observe_cost = _observation_cost(run, bool(args.from_grids))
    request_kinds = {
        "observe": observe_cost,
        "evidence": evidence_cost,
        "judge": judged_cost,
    }
    complete = (
        bool(run.coverage_complete)
        and coverage["cells_judged"] == coverage["cells_total"]
        and not coverage["unjudged"]
        and not beyond
    )
    progress = {
        **meta,
        "requested_model_id": args.judge_model,
        "model_id_as_served": sorted(served_models),
        "budgets": {
            "judge_cells": JUDGE_CELLS,
            "evidence_requests": EVIDENCE_REQUESTS,
            "observations_per_cell": MAX_OBSERVATIONS_PER_CELL,
            "events_per_observation": EVENTS_PER_OBSERVATION,
            "characters_per_event": MAX_EVENT_CHARACTERS,
            "executor": dict(executor.budget.limits),
        },
        "order": ORDER,
        "coverage": coverage,
        "request_kinds": request_kinds,
        "wall_seconds": round(time.monotonic() - began, 1),
        "coverage_complete": complete,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leads.json").write_text(json.dumps({"leads": leads}, indent=1) + "\n")
    (out / "progress.json").write_text(json.dumps(progress, indent=1, sort_keys=True) + "\n")
    judged_rows = [
        {
            "host": lead["host"],
            "hour": lead["hour"],
            "l1_rank": lead["l1_rank"],
            "p_yes": lead["p_yes"],
            "prompt_tokens": judged[(lead["host"], lead["hour"])][1].prompt_tokens,
            "seconds": judged[(lead["host"], lead["hour"])][1].seconds,
        }
        for lead in scored
    ]
    (out / "cells.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in judged_rows)
    )
    return progress


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--from-grids", default=None)
    parser.add_argument("--baseline", default="current", choices=BASELINES)
    parser.add_argument("--start", type=float, default=None)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--judge-url", default=os.environ.get("PORTAL_HUNT_JUDGE_URL"))
    parser.add_argument("--judge-model", default=os.environ.get("PORTAL_HUNT_JUDGE_MODEL"))
    parser.add_argument(
        "--judge-key-env", default=os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", "PIPELINE_API_KEY")
    )
    args = parser.parse_args()
    if not args.judge_url or not args.judge_model:
        parser.error(
            "--judge-url and --judge-model (or their PORTAL_HUNT_JUDGE_* environment values) are required"
        )
    return args


def main() -> int:
    args = _parse()
    progress = run_judged_hunt(args)
    coverage = progress["coverage"]
    print(
        f"judged {coverage['cells_judged']}/{coverage['cells_total']} host-hours; "
        f"beyond budget={len(coverage['beyond_budget'])}; "
        f"coverage_complete={progress['coverage_complete']} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
