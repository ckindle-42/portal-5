#!/usr/bin/env python3
"""Rank every layer-one host-hour by a Pipeline workspace judgement of its evidence."""

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
from portal.modules.security.core.hunt.evidence import (  # noqa: E402
    EVENTS_PER_OBSERVATION,
    EVIDENCE_REQUESTS,
    JUDGE_CELLS,
    MAX_EVENT_CHARACTERS,
    MAX_OBSERVATIONS_PER_CELL,
)
from portal.modules.security.core.hunt.judge import (  # noqa: E402
    DEFAULT_KEY_ENV,
    OpenAICompatibleClient,
    chat_completions_endpoint,
)
from portal.modules.security.core.hunt.observations import (  # noqa: E402
    ObservationRun,
    budgeted_search,
    load_observations,
    observe,
    reorder,
)
from portal.modules.security.core.hunt.order import (  # noqa: E402
    ORDER_STATEMENT,
    coverage_complete,
    rank_from_observations,
)
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402


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


def _option(args: argparse.Namespace, name: str, default: Any) -> Any:
    value = getattr(args, name, None)
    return default if value is None else value


def _hunt_progress(
    args: argparse.Namespace,
    meta: Mapping[str, Any],
    *,
    began: float,
    judge_cells: int,
    budget_order: str,
    order_mode: str,
    evidence_mode: str,
    event_chars: int,
    served_models: set[str],
    executor: Any,
    coverage: Mapping[str, Any],
    complete: bool,
    run: ObservationRun,
    before: Mapping[str, Mapping[str, Any]],
    judged_cost: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **meta,
        "requested_model_id": args.judge_model,
        "model_id_as_served": sorted(served_models),
        "options": {
            "baseline": args.baseline,
            "budget_order": budget_order,
            "order": order_mode,
            "evidence": evidence_mode,
            "judge_cells": judge_cells,
            "event_chars": event_chars,
            "judge_key_env": args.judge_key_env,
        },
        "budgets": {
            "judge_cells": judge_cells,
            "evidence_requests": EVIDENCE_REQUESTS,
            "observations_per_cell": MAX_OBSERVATIONS_PER_CELL,
            "events_per_observation": EVENTS_PER_OBSERVATION,
            "characters_per_event": event_chars,
            "executor": dict(executor.budget.limits),
        },
        "order": order_mode,
        "order_statement": ORDER_STATEMENT[order_mode],
        "budget_order": budget_order,
        "evidence": evidence_mode,
        "coverage": coverage,
        "request_kinds": {
            "observe": _observation_cost(run, bool(args.from_grids)),
            "evidence": _executor_delta(before, executor.stats()),
            "judge": judged_cost,
        },
        "wall_seconds": round(time.monotonic() - began, 1),
        "coverage_complete": complete,
    }


def _write_receipts(
    out: Path,
    leads: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    progress: dict[str, Any],
    judged_rows: list[dict[str, Any]],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "leads.json").write_text(json.dumps({"leads": leads}, indent=1) + "\n")
    (out / "cases.json").write_text(json.dumps({"cases": cases}, indent=1) + "\n")
    (out / "progress.json").write_text(json.dumps(progress, indent=1, sort_keys=True) + "\n")
    (out / "cells.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in judged_rows)
    )


def run_judged_hunt(
    args: argparse.Namespace,
    *,
    prepare: Callable[[argparse.Namespace], tuple[ObservationRun, dict[str, Any], Any]] = _window,
    client: Any = None,
) -> dict[str, Any]:
    """Compose observation, evidence and judgement stages and write bounded receipts."""
    began = time.monotonic()
    judge_cells, budget_order, order_mode, evidence_mode, event_chars = (
        int(_option(args, "judge_cells", JUDGE_CELLS)),
        str(_option(args, "budget_order", "accumulated")),
        str(_option(args, "order", "fused")),
        str(_option(args, "evidence", "rarest")),
        int(_option(args, "event_chars", MAX_EVENT_CHARACTERS)),
    )
    run, meta, executor = prepare(args)
    if client is None:
        api_key = os.environ.get(args.judge_key_env) if args.judge_key_env else None
        client = OpenAICompatibleClient(chat_completions_endpoint(args.judge_url), api_key)
    before = executor.stats()
    ranked = rank_from_observations(
        run.observations,
        executor,
        args.index,
        float(meta["start"]),
        float(meta["end"]),
        client,
        args.judge_model,
        budget_order=budget_order,
        judge_cells=judge_cells,
        order_mode=order_mode,
        evidence_mode=evidence_mode,
        event_chars=event_chars,
    )
    progress = _hunt_progress(
        args,
        meta,
        began=began,
        judge_cells=judge_cells,
        budget_order=budget_order,
        order_mode=order_mode,
        evidence_mode=evidence_mode,
        event_chars=event_chars,
        served_models=set(ranked["served_models"]),
        executor=executor,
        coverage=ranked["coverage"],
        complete=coverage_complete(run, ranked["coverage"], ranked["leads"], ranked["beyond"]),
        run=run,
        before=before,
        judged_cost=ranked["judge_cost"],
    )
    _write_receipts(
        Path(args.out), ranked["leads"], ranked["cases"], progress, ranked["judged_rows"]
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
    parser.add_argument(
        "--judge-url",
        default=os.environ.get("PORTAL_HUNT_JUDGE_URL"),
        help="Portal Pipeline chat-completions URL (PORTAL_HUNT_JUDGE_URL)",
    )
    parser.add_argument(
        "--judge-model",
        default=os.environ.get("PORTAL_HUNT_JUDGE_MODEL"),
        help="Portal Pipeline workspace id (PORTAL_HUNT_JUDGE_MODEL)",
    )
    parser.add_argument(
        "--judge-key-env",
        default=os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", DEFAULT_KEY_ENV),
        help="Environment variable name that holds the Pipeline API key",
    )
    parser.add_argument(
        "--budget-order",
        choices=("accumulated", "round_robin", "layer1"),
        default="accumulated",
        help="How host-hours are chosen for the judge budget (default: accumulated)",
    )
    parser.add_argument(
        "--judge-cells",
        type=int,
        default=JUDGE_CELLS,
        help="How many host-hours to judge (default: the judge-cell budget)",
    )
    parser.add_argument(
        "--order",
        choices=("fused", "judged", "budget"),
        default="fused",
        help="Lead order: fused rank-sum, P(yes) only, or budget order only",
    )
    parser.add_argument(
        "--evidence",
        choices=("rarest", "strongest"),
        default="rarest",
        help="Evidence read: rarest shapes first, or strongest deviation (default: rarest)",
    )
    parser.add_argument(
        "--event-chars",
        type=int,
        default=MAX_EVENT_CHARACTERS,
        help="Raw characters kept per evidence event",
    )
    args = parser.parse_args()
    if not args.judge_url or not args.judge_model:
        parser.error(
            "--judge-url and --judge-model are required: the Portal Pipeline URL and a "
            "workspace id (PORTAL_HUNT_JUDGE_URL, PORTAL_HUNT_JUDGE_MODEL)"
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
