"""Host-hour order for a hunt: budget sequence, judgement, fused rank, cases.

No environment reads, no files, and no argument parser. Callers supply observations,
evidence reads, and a judge client.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from portal.modules.security.core.hunt.engine import HOUR
from portal.modules.security.core.hunt.evidence import (
    EVENTS_PER_OBSERVATION,
    MAX_OBSERVATIONS_PER_CELL,
    EvidenceCell,
    accumulated_host_hours,
    read_cells,
)
from portal.modules.security.core.hunt.judge import JudgeClient, JudgeResult, judge_cell
from portal.modules.security.core.hunt.observations import Observation, ObservationRun, _sort_key

HOST_DAY_SPAN = 86400  # grouping granularity: one host's UTC day, not a time filter
ORDER_STATEMENT = {
    "fused": (
        "judged cells by ascending sum of P(yes) rank (ties by acc_rank) and budget position, "
        "ties by budget position; remaining cells by accumulated risk"
    ),
    "judged": "judged cells by descending P(yes); remaining cells by accumulated risk",
    "budget": "budget sequence",
}


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


def lead_row(
    cell: EvidenceCell,
    *,
    result: JudgeResult | None = None,
    evidence: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    evidence_selection: str | None = None,
) -> dict[str, Any]:
    """One host-hour row. Unjudged cells keep p_yes null and an explicit reason."""
    shown = evidence or []
    return {
        "host": cell.host,
        "hour": cell.hour,
        "span": HOUR,
        "p_yes": result.p_yes if result is not None else None,
        "risk": cell.risk,
        "l1_rank": cell.l1_rank,
        "acc_rank": cell.acc_rank,
        "budget_rank": cell.budget_rank,
        "judged": bool(result is not None and result.p_yes is not None),
        "reason": reason,
        "evidence_selection": evidence_selection,
        "evidence": shown,
        "observations": _shown_observations(cell, shown),
    }


def _shown_observations(cell: EvidenceCell, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def coverage_report(
    leads: list[dict[str, Any]], total: int, beyond: list[dict[str, Any]]
) -> dict[str, Any]:
    """Judged, unjudged, and beyond-budget counts. A reason is never dropped."""
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


def judge_selected(
    client: JudgeClient,
    model: str,
    selected: list[EvidenceCell],
    reads_by_cell: Mapping[tuple[str, int], Any],
    stop: Callable[[], bool] | None = None,
) -> tuple[dict[tuple[str, int], tuple[Any, JudgeResult]], dict[str, Any], set[str], bool]:
    """Judge cells that have evidence. A stop leaves the rest unjudged."""
    judged: dict[tuple[str, int], tuple[Any, JudgeResult]] = {}
    seconds = 0.0
    attempts = 0
    served: set[str] = set()
    stopped = False
    for cell in selected:
        if stop is not None and stop():
            stopped = True
            break
        read = reads_by_cell[(cell.host, cell.hour)]
        if not read.evidence:
            continue
        verdict = judge_cell(client, model=model, evidence=read.evidence)
        attempts += 1
        seconds += verdict.seconds
        if verdict.served_model:
            served.add(verdict.served_model)
        judged[(cell.host, cell.hour)] = (read, verdict)
    return judged, {"requests": attempts, "seconds": round(seconds, 3)}, served, stopped


def _by_accumulated(cells: list[EvidenceCell]) -> list[EvidenceCell]:
    return sorted(cells, key=lambda cell: cell.acc_rank)


def _interleave(groups: list[list[EvidenceCell]]) -> list[EvidenceCell]:
    sequence: list[EvidenceCell] = []
    depth = 0
    while True:
        progressed = False
        for group in groups:
            if depth < len(group):
                sequence.append(group[depth])
                progressed = True
        if not progressed:
            return sequence
        depth += 1


def _round_robin(cells: list[EvidenceCell]) -> list[EvidenceCell]:
    groups: dict[tuple[str, int], list[EvidenceCell]] = {}
    for cell in _by_accumulated(cells):
        groups.setdefault((cell.host, int(cell.hour) // HOST_DAY_SPAN), []).append(cell)
    ordered = sorted(groups.values(), key=lambda group: group[0].acc_rank)
    return _interleave(ordered)


def budget_sequence(cells: list[EvidenceCell], budget_order: str) -> list[EvidenceCell]:
    """Host-hours in the order the judge budget spends them."""
    if budget_order == "layer1":
        return sorted(cells, key=lambda cell: cell.l1_rank)
    if budget_order == "round_robin":
        return _round_robin(cells)
    return _by_accumulated(cells)


def with_budget_ranks(cells: list[EvidenceCell], budget_order: str) -> list[EvidenceCell]:
    """Stamp budget_rank from the budget sequence. Cells themselves are not dropped."""
    ranks = {
        (cell.host, cell.hour): rank
        for rank, cell in enumerate(budget_sequence(cells, budget_order), 1)
    }
    return [replace(cell, budget_rank=ranks[(cell.host, cell.hour)]) for cell in cells]


def _p_yes_order(judged_leads: list[dict[str, Any]], tie: str) -> list[dict[str, Any]]:
    return sorted(judged_leads, key=lambda lead: (-float(lead["p_yes"]), int(lead[tie])))


def _fuse(judged_leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranks = {
        (lead["host"], lead["hour"]): rank
        for rank, lead in enumerate(_p_yes_order(judged_leads, "acc_rank"), 1)
    }
    return sorted(
        judged_leads,
        key=lambda lead: (
            ranks[(lead["host"], lead["hour"])] + int(lead["budget_rank"]),
            int(lead["budget_rank"]),
        ),
    )


def _accumulated_tail(leads: list[dict[str, Any]], beyond: bool) -> list[dict[str, Any]]:
    chosen = [
        lead
        for lead in leads
        if not lead["judged"] and (lead["reason"] == "beyond_judge_cell_budget") is beyond
    ]
    chosen.sort(key=lambda lead: int(lead["acc_rank"]))
    return chosen


def arrange(leads: list[dict[str, Any]], order_mode: str) -> list[dict[str, Any]]:
    """Fused or P(yes) put judged cells first. Budget order is the budget sequence alone."""
    if order_mode == "budget":
        return sorted(leads, key=lambda lead: (int(lead["budget_rank"]), int(lead["l1_rank"])))
    judged_leads = [lead for lead in leads if lead["judged"]]
    head = (
        _p_yes_order(judged_leads, "budget_rank") if order_mode == "judged" else _fuse(judged_leads)
    )
    return head + _accumulated_tail(leads, False) + _accumulated_tail(leads, True)


def _case_member(rank: int, lead: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hour": int(lead["hour"]),
        "risk": lead["risk"],
        "p_yes": lead["p_yes"],
        "acc_rank": lead["acc_rank"],
        "l1_rank": lead["l1_rank"],
        "lead_rank": rank,
    }


def _case_evidence(members: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    judged = [item for item in members if item[1]["judged"]]
    if not judged:
        return []
    best = min(judged, key=lambda item: item[0])
    return list(best[1]["evidence"])


def host_day_cases(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One case per host-day, members in lead order, ordered by the best lead."""
    grouped: dict[tuple[str, int], list[tuple[int, dict[str, Any]]]] = {}
    for lead_rank, lead in enumerate(leads, 1):
        grouped.setdefault((str(lead["host"]), int(lead["hour"]) // HOST_DAY_SPAN), []).append(
            (lead_rank, lead)
        )
    cases: list[dict[str, Any]] = []
    for (host, _day), members in grouped.items():
        hours = [int(lead["hour"]) for _rank, lead in members]
        cases.append(
            {
                "host": host,
                "start": min(hours),
                "end": max(hours) + HOUR,
                "risk": sum(float(lead["risk"]) for _rank, lead in members),
                "members": [_case_member(rank, lead) for rank, lead in members],
                "evidence": _case_evidence(members),
            }
        )
    cases.sort(key=lambda case: min(int(member["lead_rank"]) for member in case["members"]))
    return cases


def coverage_complete(
    run: ObservationRun,
    coverage: Mapping[str, Any],
    leads: list[dict[str, Any]],
    beyond: list[dict[str, Any]],
) -> bool:
    """Complete only when every cell was judged and layer 1 itself finished."""
    return bool(
        run.coverage_complete
        and coverage["cells_judged"] == coverage["cells_total"]
        and not coverage["unjudged"]
        and not beyond
        and not any(lead["reason"] for lead in leads)
    )


def lead_for(
    cell: EvidenceCell,
    reads_by_cell: Mapping[tuple[str, int], Any],
    judged: Mapping[tuple[str, int], tuple[Any, JudgeResult]],
    *,
    missing_reason: str,
) -> dict[str, Any]:
    """One cell's row. A missing verdict stays unjudged with the caller's reason."""
    key = (cell.host, cell.hour)
    if key not in reads_by_cell:
        return lead_row(cell, reason="beyond_judge_cell_budget")
    read = reads_by_cell[key]
    if not read.evidence:
        return lead_row(cell, reason=read.reason, evidence_selection=read.evidence_selection)
    found = judged.get(key)
    if found is None:
        return lead_row(cell, reason=missing_reason, evidence_selection=read.evidence_selection)
    evidence_read, verdict = found
    return lead_row(
        cell,
        result=verdict,
        evidence=evidence_read.evidence if verdict.p_yes is not None else [],
        reason=evidence_read.reason or verdict.reason,
        evidence_selection=evidence_read.evidence_selection,
    )


def ordered_leads(
    cells: list[EvidenceCell],
    reads_by_cell: Mapping[tuple[str, int], Any],
    judged: Mapping[tuple[str, int], tuple[Any, JudgeResult]],
    order_mode: str,
    *,
    missing_reason: str = "unjudged",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Arrange every cell. Beyond-budget rows stay in the list with their reason."""
    leads = arrange(
        [lead_for(cell, reads_by_cell, judged, missing_reason=missing_reason) for cell in cells],
        order_mode,
    )
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


def judged_rows(
    leads: list[dict[str, Any]], judged: Mapping[tuple[str, int], tuple[Any, JudgeResult]]
) -> list[dict[str, Any]]:
    """One jsonl record per judged cell, in lead order."""
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


def compose_order(
    cells: list[EvidenceCell],
    reads_by_cell: Mapping[tuple[str, int], Any],
    judged: Mapping[tuple[str, int], tuple[Any, JudgeResult]],
    order_mode: str,
    *,
    missing_reason: str = "unjudged",
) -> dict[str, Any]:
    """Leads, cases, coverage, and judged rows for one prepared cell list."""
    leads, beyond = ordered_leads(
        cells, reads_by_cell, judged, order_mode, missing_reason=missing_reason
    )
    return {
        "leads": leads,
        "beyond": beyond,
        "coverage": coverage_report(leads, len(cells), beyond),
        "cases": host_day_cases(leads),
        "judged_rows": judged_rows(leads, judged),
    }


def rank_from_observations(
    observations: Iterable[Observation],
    executor: Any,
    index: str,
    start: float,
    end: float,
    client: JudgeClient,
    model: str,
    *,
    budget_order: str,
    judge_cells: int,
    order_mode: str,
    evidence_mode: str,
    event_chars: int,
    stop: Callable[[], bool] | None = None,
    renames: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read and judge the budgeted prefix, then arrange every host-hour."""
    cells = with_budget_ranks(accumulated_host_hours(observations), budget_order)
    selected = sorted(cells, key=lambda cell: cell.budget_rank)[: max(0, judge_cells)]
    reads = read_cells(
        executor,
        index,
        selected,
        start,
        end,
        event_chars=event_chars,
        evidence_mode=evidence_mode,
        renames=renames,
    )
    reads_by = {(item.cell.host, item.cell.hour): item for item in reads}
    judged, cost, served, stopped = judge_selected(client, model, selected, reads_by, stop)
    missing = "job_deadline_exceeded" if stopped else "unjudged"
    composed = compose_order(cells, reads_by, judged, order_mode, missing_reason=missing)
    composed["judge_cost"] = cost
    composed["served_models"] = served
    return composed


def accumulated_rows(observations: Iterable[Observation], reason: str) -> list[dict[str, Any]]:
    """Every host-hour in accumulated order, each carrying the same explicit reason."""
    cells = with_budget_ranks(accumulated_host_hours(observations), "accumulated")
    return arrange([lead_row(cell, reason=reason) for cell in cells], "fused")


def host_hour_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Scalar host-hour fields persisted on a job. Evidence stays off this row."""
    return {
        "host": row["host"],
        "hour": row["hour"],
        "risk": row["risk"],
        "acc_rank": row["acc_rank"],
        "l1_rank": row["l1_rank"],
        "p_yes": row["p_yes"],
        "reason": row["reason"],
    }


def best_host_hour(
    hours: Sequence[tuple[str, int]], rows: Sequence[Mapping[str, Any]]
) -> tuple[str, int] | None:
    """The hour with the best place in the final order. Ties break by host, then hour."""
    if not hours:
        return None
    position = {(str(row["host"]), int(row["hour"])): index for index, row in enumerate(rows)}
    limit = len(position)
    return min(hours, key=lambda key: (position.get(key, limit), key[0], key[1]))


def order_group_indexes(
    groups: Sequence[Sequence[tuple[str, int]]], rows: Sequence[Mapping[str, Any]]
) -> list[int]:
    """Group indexes by best host-hour position. Equal positions keep input order."""
    position = {(str(row["host"]), int(row["hour"])): index for index, row in enumerate(rows)}
    limit = len(position)

    def place(index: int) -> int:
        hours = groups[index]
        if not hours:
            return limit
        return min(position.get(key, limit) for key in hours)

    return sorted(range(len(groups)), key=place)


def positive_seeds(
    observations: Sequence[Observation],
    rows: Sequence[Mapping[str, Any]],
    candidates: int,
    per_hour: int,
) -> list[Observation]:
    """Positive-scored observations of the first `candidates` host-hours, strongest first."""
    grouped: dict[tuple[str, int], list[Observation]] = {}
    for obs in observations:
        grouped.setdefault((obs.host, obs.hour), []).append(obs)
    chosen: list[Observation] = []
    for row in rows[: max(0, candidates)]:
        hour_rows = [
            obs
            for obs in grouped.get((str(row["host"]), int(row["hour"])), [])
            if obs.score is not None and obs.score > 0
        ]
        hour_rows.sort(key=_sort_key)
        chosen.extend(hour_rows[: max(0, per_hour)])
    return chosen
