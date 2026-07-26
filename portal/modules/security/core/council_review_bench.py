"""Earn-your-place bench for the platform Council Review primitive.

The bench uses review material derived from real Portal 5 closeout decisions,
compares the three-seat council with one strong reviewer, and scores only
grounded behavior: known-flaw catch with evidence, honest abstention on thin
material, dissent preservation, seat participation, and cost.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from portal.platform.inference.router.council import CouncilOpinion, parse_opinion
from portal.platform.inference.router.workspaces import WORKSPACES

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline-key")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TIMEOUT_S = float(os.environ.get("COUNCIL_BENCH_TIMEOUT", "900"))

_SOLO_CONTRACT = """Review the supplied material independently.
Return exactly one JSON object and no Markdown:
{
  "recommendation": "SUPPORT|REVISE|REJECT|ABSTAIN",
  "confidence": 0.0,
  "findings": [{"claim": "specific finding", "severity": "high|medium|low",
                "evidence": ["exact reference from the material"],
                "action": "specific corrective action"}],
  "missing_evidence": ["information needed"],
  "strongest_objection": "best case against your recommendation",
  "conditions_to_change": ["what would change your recommendation"]
}
Use only the supplied material. Every substantive finding needs evidence.
ABSTAIN when the material is insufficient."""


@dataclass(frozen=True)
class ReviewTask:
    """One grounded review case and its deterministic scoring oracle."""

    task_id: str
    title: str
    source: str
    material: str
    expected_markers: tuple[str, ...] = ()
    thin_material: bool = False


TASKS = (
    ReviewTask(
        task_id="model-cleanup-safety",
        title="Model cleanup plan with a historical safety flaw",
        source="coding_task/TASK CLOSEOUT P5 MODEL CLEANUP 2.md",
        expected_markers=("dry-run", "reference", "keep"),
        material="""Review this proposed Portal 5 model cleanup:

Goal: reclaim Ollama disk after validation. The implementation will read only
config/portal.yaml, subtract those model names from `ollama list`, immediately
run `ollama rm` on everything left, and remove the same entries from
portal.yaml so the catalog matches disk. No dry-run or post-delete load check
is planned. Persona pins, backends.yaml, router/council rosters, tests, bench
drivers, and models exercised by validation are not part of the scan.

Constraints from the actual closeout: the catalog is additive-only; cleanup is
disk-only; KEEP is the union of every active reference; a reviewed dry-run and
post-delete KEEP verification are mandatory.""",
    ),
    ReviewTask(
        task_id="council-quorum-safety",
        title="Council quorum proposal with a historical denominator flaw",
        source="coding_task/TASK CLOSEOUT P1 COUNCIL RECONCILE.md",
        expected_markers=("roster", "non-voter", "participation"),
        material="""Review this proposed council simplification:

To make Council Review resilient, quorum will be computed only over reviewers
that return a valid non-ABSTAIN response. If one of three configured seats
returns valid SUPPORT and the other two fail or abstain, the result is 1/1
SUPPORT. No participation floor is needed because failed seats should not
penalize the surviving reviewer.

Known Portal invariant: quorum uses the full configured roster denominator;
non-voters count against participation and quorum; insufficient participation
must ESCALATE rather than manufacture a single-model decision.""",
    ),
    ReviewTask(
        task_id="thin-change-request",
        title="Insufficient change request",
        source="representative Portal operator request",
        thin_material=True,
        material="""Review the following production change request:

"Make the security system better and deploy it."

No affected component, current behavior, desired behavior, threat model,
acceptance criteria, patch, test result, rollout plan, or rollback evidence was
provided.""",
    ),
)


def _text_for_opinion(opinion: dict[str, Any] | CouncilOpinion) -> str:
    payload = asdict(opinion) if isinstance(opinion, CouncilOpinion) else opinion
    return json.dumps(
        {
            "findings": payload.get("findings") or [],
            "missing_evidence": payload.get("missing_evidence") or [],
            "strongest_objection": payload.get("strongest_objection") or "",
            "conditions_to_change": payload.get("conditions_to_change") or [],
        },
        sort_keys=True,
    ).lower()


def _participated(opinion: dict[str, Any]) -> bool:
    return bool(
        opinion.get("participated")
        if "participated" in opinion
        else opinion.get("valid") and opinion.get("recommendation") != "ABSTAIN"
    )


def catches_known_flaw(task: ReviewTask, opinions: list[dict[str, Any] | CouncilOpinion]) -> bool:
    """A flaw is caught only when a marker appears in an evidence-backed finding."""
    if not task.expected_markers:
        return False
    for opinion in opinions:
        payload = asdict(opinion) if isinstance(opinion, CouncilOpinion) else opinion
        for finding in payload.get("findings") or []:
            if not isinstance(finding, dict) or not finding.get("evidence"):
                continue
            text = json.dumps(finding, sort_keys=True).lower()
            if any(marker.lower() in text for marker in task.expected_markers):
                return True
    return False


def score_case(
    task: ReviewTask,
    *,
    council_payload: dict[str, Any],
    solo_opinion: CouncilOpinion,
    council_latency_s: float,
    solo_latency_s: float,
) -> dict[str, Any]:
    """Score one live or deterministic case without an LLM-as-judge."""
    portal_council = council_payload["portal_council"]
    aggregate = portal_council["aggregate"]
    reviewers = portal_council["reviewers"]
    synthesis = str(council_payload["choices"][0]["message"].get("content") or "")
    council_caught = catches_known_flaw(task, reviewers)
    solo_caught = catches_known_flaw(task, [solo_opinion])
    participating = [reviewer for reviewer in reviewers if _participated(reviewer)]
    council_honest_abstention = task.thin_material and aggregate["decision"] == "ESCALATE"
    solo_honest_abstention = task.thin_material and solo_opinion.recommendation == "ABSTAIN"
    dissent_ids = [str(member_id) for member_id in aggregate.get("dissent") or []]
    dissent_preserved = all(member_id in synthesis for member_id in dissent_ids)
    machine_decision_preserved = (
        f"Code-determined decision: {aggregate['decision']}" in synthesis
        or f"**{aggregate['decision']}**" in synthesis
    )

    council_output = json.dumps(reviewers, sort_keys=True) + synthesis
    solo_output = _text_for_opinion(solo_opinion)
    return {
        "task_id": task.task_id,
        "title": task.title,
        "source": task.source,
        "known_flaw": bool(task.expected_markers),
        "thin_material": task.thin_material,
        "council": {
            "decision": aggregate["decision"],
            "flaw_caught_with_evidence": council_caught,
            "honest_abstention": council_honest_abstention,
            "participating": len(participating),
            "roster": len(reviewers),
            "dissent": dissent_ids,
            "dissent_preserved_in_synthesis": dissent_preserved,
            "machine_decision_preserved": machine_decision_preserved,
            "latency_s": round(council_latency_s, 2),
            "estimated_output_tokens": max(1, len(council_output) // 4),
            "model_calls": len(reviewers) + 1,
        },
        "solo": {
            "recommendation": solo_opinion.recommendation,
            "valid": solo_opinion.valid,
            "flaw_caught_with_evidence": solo_caught,
            "honest_abstention": solo_honest_abstention,
            "latency_s": round(solo_latency_s, 2),
            "estimated_output_tokens": max(1, len(solo_output) // 4),
            "model_calls": 1,
        },
        "delta": {
            "flaw_catch": int(council_caught) - int(solo_caught),
            "latency_s": round(council_latency_s - solo_latency_s, 2),
        },
    }


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the honest council-vs-solo result and dead-seat report."""
    if not cases:
        raise ValueError("solo baseline is required; no cases were supplied")
    flawed = [case for case in cases if case["known_flaw"]]
    thin = [case for case in cases if case["thin_material"]]
    council_catches = sum(case["council"]["flaw_caught_with_evidence"] for case in flawed)
    solo_catches = sum(case["solo"]["flaw_caught_with_evidence"] for case in flawed)

    seat_counts: dict[str, dict[str, int]] = {}
    for case in cases:
        # The detailed records are attached by run_live_bench before summarize.
        for reviewer in case.pop("_reviewers", []):
            seat = seat_counts.setdefault(
                str(reviewer["member_id"]),
                {"participated": 0, "tasks": 0},
            )
            seat["tasks"] += 1
            seat["participated"] += int(_participated(reviewer))
    participation = {
        seat: {
            **counts,
            "rate": round(counts["participated"] / counts["tasks"], 3),
            "dead_seat": counts["participated"] == 0,
        }
        for seat, counts in sorted(seat_counts.items())
    }
    dead_seats = [seat for seat, counts in participation.items() if counts["dead_seat"]]
    latency_council = sum(case["council"]["latency_s"] for case in cases)
    latency_solo = sum(case["solo"]["latency_s"] for case in cases)
    output_council = sum(case["council"]["estimated_output_tokens"] for case in cases)
    output_solo = sum(case["solo"]["estimated_output_tokens"] for case in cases)
    improved = council_catches > solo_catches
    earned = improved and not dead_seats
    return {
        "schema_version": 1,
        "task_count": len(cases),
        "known_flaw_tasks": len(flawed),
        "council_flaw_catches": council_catches,
        "solo_flaw_catches": solo_catches,
        "flaw_catch_delta": council_catches - solo_catches,
        "thin_material_tasks": len(thin),
        "council_honest_abstentions": sum(case["council"]["honest_abstention"] for case in thin),
        "solo_honest_abstentions": sum(case["solo"]["honest_abstention"] for case in thin),
        "all_machine_decisions_preserved": all(
            case["council"]["machine_decision_preserved"] for case in cases
        ),
        "all_dissent_preserved": all(
            case["council"]["dissent_preserved_in_synthesis"] for case in cases
        ),
        "seat_participation": participation,
        "dead_seats": dead_seats,
        "cost": {
            "council_latency_s": round(latency_council, 2),
            "solo_latency_s": round(latency_solo, 2),
            "latency_multiple": round(latency_council / latency_solo, 2) if latency_solo else None,
            "council_estimated_output_tokens": output_council,
            "solo_estimated_output_tokens": output_solo,
            "output_token_multiple": round(output_council / output_solo, 2)
            if output_solo
            else None,
            "note": "Token counts are explicit character/4 estimates; model-call counts are exact.",
        },
        "earns_place_for_blue_borderline": earned,
        "recommendation": (
            "Council improves known-flaw catch over solo; consider scoped use."
            if earned
            else "Keep council platform-only: it did not beat solo enough to justify its cost."
        ),
        "cases": cases,
    }


def _call_council(client: httpx.Client, task: ReviewTask) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    response = client.post(
        f"{PIPELINE_URL.rstrip('/')}/v1/chat/completions",
        headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
        json={
            "model": "auto-council",
            "stream": False,
            "messages": [{"role": "user", "content": task.material}],
        },
    )
    elapsed = time.monotonic() - started
    response.raise_for_status()
    payload = response.json()
    if "portal_council" not in payload:
        raise RuntimeError("pipeline response did not contain portal_council evidence")
    return payload, elapsed


def _call_solo(client: httpx.Client, task: ReviewTask, model: str) -> tuple[CouncilOpinion, float]:
    started = time.monotonic()
    response = client.post(
        f"{OLLAMA_URL.rstrip('/')}/v1/chat/completions",
        json={
            "model": model,
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": _SOLO_CONTRACT},
                {"role": "user", "content": task.material},
            ],
        },
    )
    elapsed = time.monotonic() - started
    response.raise_for_status()
    content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return parse_opinion(
        {"id": "solo", "label": "Solo strong reviewer", "model": model},
        content,
    ), elapsed


def run_live_bench() -> dict[str, Any]:
    """Run the fixed real-review set against live Portal and Ollama."""
    council = WORKSPACES["auto-council"]["council"]
    solo_model = str(council["members"][0]["model"])
    cases: list[dict[str, Any]] = []
    with httpx.Client(timeout=TIMEOUT_S) as client:
        for task in TASKS:
            council_payload, council_latency = _call_council(client, task)
            solo_opinion, solo_latency = _call_solo(client, task, solo_model)
            case = score_case(
                task,
                council_payload=council_payload,
                solo_opinion=solo_opinion,
                council_latency_s=council_latency,
                solo_latency_s=solo_latency,
            )
            case["_reviewers"] = council_payload["portal_council"]["reviewers"]
            cases.append(case)
            print(
                f"{task.task_id}: council={case['council']['decision']} "
                f"caught={case['council']['flaw_caught_with_evidence']} "
                f"solo={case['solo']['recommendation']} "
                f"caught={case['solo']['flaw_caught_with_evidence']}",
                flush=True,
            )
    result = summarize(cases)
    result["run_kind"] = "live"
    result["isolation"] = {
        "status": "VERIFIED_BY_RUNTIME_CONTRACT",
        "detail": (
            "run_council_review fans out one immutable review_material string via "
            "asyncio.gather; reviewer calls receive no sibling records. "
            "tests/unit/test_council_review.py asserts this payload boundary."
        ),
    }
    return result


def render_markdown(result: dict[str, Any]) -> str:
    """Render a compact, auditable closeout report."""
    lines = [
        "# Platform Council Earn-Your-Place Bench — 2026-07-26",
        "",
        "## Verdict",
        "",
        result["recommendation"],
        "",
        f"Council caught {result['council_flaw_catches']}/{result['known_flaw_tasks']} "
        f"known flaws with cited evidence; solo caught "
        f"{result['solo_flaw_catches']}/{result['known_flaw_tasks']} "
        f"(delta {result['flaw_catch_delta']:+d}).",
        "",
        "## Live review matrix",
        "",
        "| Task | Council | Council caught | Solo | Solo caught | Council / solo latency |",
        "|---|---|---:|---|---:|---:|",
    ]
    for case in result["cases"]:
        lines.append(
            f"| `{case['task_id']}` | {case['council']['decision']} | "
            f"{'yes' if case['council']['flaw_caught_with_evidence'] else 'no'} | "
            f"{case['solo']['recommendation']} | "
            f"{'yes' if case['solo']['flaw_caught_with_evidence'] else 'no'} | "
            f"{case['council']['latency_s']:.2f}s / {case['solo']['latency_s']:.2f}s |"
        )
    cost = result["cost"]
    lines.extend(
        [
            "",
            "## Participation, fidelity, and cost",
            "",
            f"- Honest abstention on thin material: council "
            f"{result['council_honest_abstentions']}/{result['thin_material_tasks']}; "
            f"solo {result['solo_honest_abstentions']}/{result['thin_material_tasks']}.",
            f"- Code decision preserved: {result['all_machine_decisions_preserved']}; "
            f"dissent preserved: {result['all_dissent_preserved']}.",
            f"- Dead seats: {', '.join(result['dead_seats']) if result['dead_seats'] else 'none'}.",
        ]
    )
    for seat, counts in result["seat_participation"].items():
        lines.append(
            f"  - `{seat}`: {counts['participated']}/{counts['tasks']} "
            f"({counts['rate'] * 100:.1f}%)."
        )
    lines.extend(
        [
            f"- Latency: council {cost['council_latency_s']:.2f}s vs solo "
            f"{cost['solo_latency_s']:.2f}s ({cost['latency_multiple']}×).",
            f"- Estimated output tokens: council {cost['council_estimated_output_tokens']} "
            f"vs solo {cost['solo_estimated_output_tokens']} "
            f"({cost['output_token_multiple']}×). {cost['note']}",
            "",
            "## Isolation",
            "",
            result["isolation"]["detail"],
            "",
            "## Scope",
            "",
            "The set is intentionally small: two known-flaw closeout reviews and one "
            "thin-material case. It measures this task class honestly but is not a "
            "general benchmark of every decision or policy review.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bench platform Council Review vs solo")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args()
    result = run_live_bench()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    report = render_markdown(result)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(report)
    if not args.json_out and not args.report_out:
        print(report)


if __name__ == "__main__":
    main()
