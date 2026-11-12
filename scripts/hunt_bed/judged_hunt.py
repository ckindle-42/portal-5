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
from portal.modules.security.core.hunt.engine import HOUR  # noqa: E402
from portal.modules.security.core.hunt.evidence import (  # noqa: E402
    EVENTS_PER_OBSERVATION,
    EVIDENCE_REQUESTS,
    JUDGE_CELLS,
    MAX_EVENT_CHARACTERS,
    MAX_OBSERVATIONS_PER_CELL,
    EvidenceCell,
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

HOST_DAY_SPAN = 86400  # grouping granularity: one host's UTC day, not a time filter


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


def _compact_observations(observations: Any) -> list[dict[str, Any]]:
    return [
        {
            "kind": observation.kind,
            "entity": observation.entity,
            "hour": observation.hour,
            "score": observation.score,
            "signal": observation.evidence.get("signal"),
            "literal": observation.evidence.get("literal"),
        }
        for observation in observations
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
    shown = evidence or []
    return {
        "host": cell.host,
        "hour": cell.hour,
        "span": HOUR,
        "p_yes": result.p_yes if result is not None else None,
        "l1_rank": cell.l1_rank,
        "budget_rank": cell.budget_rank,
        "judged": bool(result is not None and result.p_yes is not None),
        "reason": reason,
        "evidence": shown,
        "observations": _shown_observations(cell, shown),
    }


def _shown_observations(cell: Any, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Contributing observations when the cell was read; otherwise the bounded prefix."""
    if not evidence:
        return _compact_observations(cell.observations)[:MAX_OBSERVATIONS_PER_CELL]
    remaining = list(evidence)
    chosen: list[Any] = []
    for observation in cell.observations:
        literal = str(observation.evidence.get("literal") or "")
        take = [item for item in remaining if item["query"] == literal][:EVENTS_PER_OBSERVATION]
        if not take:
            continue
        chosen.append(observation)
        for item in take:
            remaining.remove(item)
        if len(chosen) == MAX_OBSERVATIONS_PER_CELL:
            break
    return _compact_observations(chosen)


def _coverage(
    leads: list[dict[str, Any]], total: int, beyond: list[dict[str, Any]]
) -> dict[str, Any]:
    unjudged = [
        {key: lead[key] for key in ("host", "hour", "l1_rank", "budget_rank", "reason")}
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
        if not read.evidence:
            continue
        verdict = judge_cell(client, model=model, evidence=read.evidence)
        attempts += 1
        seconds += verdict.seconds
        if verdict.served_model:
            served.add(verdict.served_model)
        judged[(cell.host, cell.hour)] = (read, verdict)
    return judged, {"requests": attempts, "seconds": round(seconds, 3)}, served


def _budget_sequence(cells: list[EvidenceCell], budget_order: str) -> list[EvidenceCell]:
    ordered = sorted(cells, key=lambda cell: cell.l1_rank)
    if budget_order == "layer1":
        return ordered
    groups: dict[tuple[str, int], list[EvidenceCell]] = {}
    for cell in ordered:
        groups.setdefault((cell.host, int(cell.hour) // HOST_DAY_SPAN), []).append(cell)
    ordered_groups = sorted(groups.values(), key=lambda group: group[0].l1_rank)
    sequence: list[EvidenceCell] = []
    depth = 0
    while True:
        progressed = False
        for group in ordered_groups:
            if depth < len(group):
                sequence.append(group[depth])
                progressed = True
        if not progressed:
            return sequence
        depth += 1


def _with_budget_ranks(cells: list[EvidenceCell], budget_order: str) -> list[EvidenceCell]:
    ranks = {
        (cell.host, cell.hour): rank
        for rank, cell in enumerate(_budget_sequence(cells, budget_order), 1)
    }
    return [
        EvidenceCell(
            cell.host,
            cell.hour,
            cell.l1_rank,
            cell.observations,
            ranks[(cell.host, cell.hour)],
        )
        for cell in cells
    ]


def _p_yes_order(judged_leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(judged_leads, key=lambda lead: (-float(lead["p_yes"]), int(lead["budget_rank"])))


def _fuse(judged_leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranks = {
        (lead["host"], lead["hour"]): rank
        for rank, lead in enumerate(_p_yes_order(judged_leads), 1)
    }
    return sorted(
        judged_leads,
        key=lambda lead: (
            ranks[(lead["host"], lead["hour"])] + int(lead["budget_rank"]),
            int(lead["budget_rank"]),
        ),
    )


def _arrange(leads: list[dict[str, Any]], order_mode: str) -> list[dict[str, Any]]:
    """Fused or P(yes) put judged cells first. Budget order is the budget sequence alone."""
    if order_mode == "budget":
        return sorted(leads, key=lambda lead: (int(lead["budget_rank"]), int(lead["l1_rank"])))
    judged_leads = [lead for lead in leads if lead["judged"]]
    unjudged = [
        lead
        for lead in leads
        if not lead["judged"] and lead["reason"] != "beyond_judge_cell_budget"
    ]
    beyond_leads = [lead for lead in leads if lead["reason"] == "beyond_judge_cell_budget"]
    unjudged.sort(key=lambda lead: int(lead["l1_rank"]))
    beyond_leads.sort(key=lambda lead: int(lead["l1_rank"]))
    head = _p_yes_order(judged_leads) if order_mode == "judged" else _fuse(judged_leads)
    return head + unjudged + beyond_leads


def _cases(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One case per host-day that has a judged cell, ordered by its best lead."""
    grouped: dict[tuple[str, int], list[tuple[int, dict[str, Any]]]] = {}
    for lead_rank, lead in enumerate(leads, 1):
        if not lead["judged"]:
            continue
        grouped.setdefault((str(lead["host"]), int(lead["hour"]) // HOST_DAY_SPAN), []).append(
            (lead_rank, lead)
        )
    cases: list[dict[str, Any]] = []
    for (host, _day), members in grouped.items():
        by_hour = sorted(members, key=lambda item: int(item[1]["hour"]))
        best = min(members, key=lambda item: item[0])
        first_hour = int(by_hour[0][1]["hour"])
        last_hour = int(by_hour[-1][1]["hour"])
        cases.append(
            {
                "host": host,
                "start": first_hour,
                "end": last_hour + HOUR,
                "members": [
                    {
                        "hour": int(lead["hour"]),
                        "p_yes": lead["p_yes"],
                        "l1_rank": lead["l1_rank"],
                        "lead_rank": rank,
                    }
                    for rank, lead in by_hour
                ],
                "evidence": list(best[1]["evidence"]),
            }
        )
    cases.sort(key=lambda case: min(int(member["lead_rank"]) for member in case["members"]))
    return cases


def _coverage_complete(
    run: ObservationRun,
    coverage: Mapping[str, Any],
    leads: list[dict[str, Any]],
    beyond: list[dict[str, Any]],
) -> bool:
    return bool(
        run.coverage_complete
        and coverage["cells_judged"] == coverage["cells_total"]
        and not coverage["unjudged"]
        and not beyond
        and not any(lead["reason"] for lead in leads)
    )


def _option(args: argparse.Namespace, name: str, default: Any) -> Any:
    value = getattr(args, name, None)
    return default if value is None else value


def _lead_for(
    cell: EvidenceCell,
    reads_by_cell: Mapping[tuple[str, int], Any],
    judged: Mapping[tuple[str, int], tuple[Any, Any]],
) -> dict[str, Any]:
    key = (cell.host, cell.hour)
    if key not in reads_by_cell:
        return _lead(cell, reason="beyond_judge_cell_budget")
    read = reads_by_cell[key]
    if not read.evidence:
        return _lead(cell, reason=read.reason)
    evidence_read, verdict = judged[key]
    return _lead(
        cell,
        result=verdict,
        evidence=evidence_read.evidence if verdict.p_yes is not None else [],
        reason=evidence_read.reason or verdict.reason,
    )


def _ordered_leads(
    cells: list[EvidenceCell],
    reads_by_cell: Mapping[tuple[str, int], Any],
    judged: Mapping[tuple[str, int], tuple[Any, Any]],
    order_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    leads = _arrange([_lead_for(cell, reads_by_cell, judged) for cell in cells], order_mode)
    beyond = [
        {
            "host": lead["host"],
            "hour": lead["hour"],
            "l1_rank": lead["l1_rank"],
            "budget_rank": lead["budget_rank"],
            "reason": lead["reason"],
        }
        for lead in leads
        if lead["reason"] == "beyond_judge_cell_budget"
    ]
    return leads, beyond


def _hunt_progress(
    args: argparse.Namespace,
    meta: Mapping[str, Any],
    *,
    began: float,
    judge_cells: int,
    budget_order: str,
    order_mode: str,
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
        "budget_order": budget_order,
        "coverage": coverage,
        "request_kinds": {
            "observe": _observation_cost(run, bool(args.from_grids)),
            "evidence": _executor_delta(before, executor.stats()),
            "judge": judged_cost,
        },
        "wall_seconds": round(time.monotonic() - began, 1),
        "coverage_complete": complete,
    }


def _judged_rows(
    leads: list[dict[str, Any]], judged: Mapping[tuple[str, int], tuple[Any, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "host": lead["host"],
            "hour": lead["hour"],
            "l1_rank": lead["l1_rank"],
            "budget_rank": lead["budget_rank"],
            "p_yes": lead["p_yes"],
            "prompt_tokens": judged[(lead["host"], lead["hour"])][1].prompt_tokens,
            "seconds": judged[(lead["host"], lead["hour"])][1].seconds,
        }
        for lead in leads
        if lead["judged"]
    ]


def _write_receipts(
    out: Path,
    leads: list[dict[str, Any]],
    progress: dict[str, Any],
    judged_rows: list[dict[str, Any]],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "leads.json").write_text(json.dumps({"leads": leads}, indent=1) + "\n")
    (out / "cases.json").write_text(json.dumps({"cases": _cases(leads)}, indent=1) + "\n")
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
    judge_cells, budget_order, order_mode, event_chars = (
        int(_option(args, "judge_cells", JUDGE_CELLS)),
        str(_option(args, "budget_order", "round_robin")),
        str(_option(args, "order", "fused")),
        int(_option(args, "event_chars", MAX_EVENT_CHARACTERS)),
    )
    run, meta, executor = prepare(args)
    cells = _with_budget_ranks(evidence_cells(run.observations), budget_order)
    selected = sorted(cells, key=lambda cell: cell.budget_rank)[: max(0, judge_cells)]
    if client is None:
        api_key = os.environ.get(args.judge_key_env) if args.judge_key_env else None
        client = OpenAICompatibleClient(_endpoint(args.judge_url), api_key)
    before = executor.stats()
    reads = read_cells(
        executor,
        args.index,
        selected,
        float(meta["start"]),
        float(meta["end"]),
        event_chars=event_chars,
    )
    judged, judged_cost, served_models = _judge_selected(
        client,
        args.judge_model,
        selected,
        {(read.cell.host, read.cell.hour): read for read in reads},
    )
    reads_by_cell = {(read.cell.host, read.cell.hour): read for read in reads}
    leads, beyond = _ordered_leads(cells, reads_by_cell, judged, order_mode)
    coverage = _coverage(leads, len(cells), beyond)
    progress = _hunt_progress(
        args,
        meta,
        began=began,
        judge_cells=judge_cells,
        budget_order=budget_order,
        order_mode=order_mode,
        event_chars=event_chars,
        served_models=served_models,
        executor=executor,
        coverage=coverage,
        complete=_coverage_complete(run, coverage, leads, beyond),
        run=run,
        before=before,
        judged_cost=judged_cost,
    )
    _write_receipts(Path(args.out), leads, progress, _judged_rows(leads, judged))
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
        default=os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", "PIPELINE_API_KEY"),
        help="Environment variable name that holds the Pipeline API key",
    )
    parser.add_argument(
        "--budget-order",
        choices=("round_robin", "layer1"),
        default="round_robin",
        help="How host-hours are chosen for the judge budget (default: round_robin)",
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
