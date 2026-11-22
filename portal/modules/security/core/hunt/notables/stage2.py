"""Stage 2: judge separation on labelled notables — single judge vs Portal council, LOFO.

python -m portal.modules.security.core.hunt.notables.stage2 \
    --out results/hunt/knowledge_s2b/kyoushi --keys kyoushi=<keys.jsonl> [--logs <gather>]

Both arms call the Portal Pipeline only (PORTAL_HUNT_JUDGE_URL, :9099): the seated
single judge (PORTAL_HUNT_JUDGE_MODEL) and a council workspace (default auto-council).
No engine is called directly and no model is downloaded. Each arm's request budget is
derived from its measured per-call wall rate and the deadline, never a constant.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..judge import (
    DEFAULT_KEY_ENV,
    JudgeClient,
    JudgeResult,
    OpenAICompatibleClient,
    chat_completions_endpoint,
    judge_cell,
)
from .judge_notables import JUDGE_PROMPT_CHARS, notable_body, notable_prompt
from .knowledge import PROOF_INDEXES, TRAINING_INDEXES
from .pipeline import content_of, model_from_env, model_requirement
from .receipt import read_json, utc_now, write_json
from .run import _judge_order
from .scoreboard import (
    JUDGE_CACHE,
    PROGRESS_FILE,
    RULE,
    Notable,
    ScoreboardError,
    _auc,
    _check_family,
    _claim,
    _coverage,
    _default_logs,
    _honesty,
    _key_paths,
    _rate,
    _read_keys,
    _read_notables,
    _run_index,
    _steps,
    _targets,
    _year,
)

COUNCIL_WORKSPACE = "auto-council"
STAGE2_PROBE_CALLS = 4  # effort budget: calibration sample per arm
STAGE2_DEADLINE_SECONDS = 720.0  # effort budget: the hunt job wall time, per arm
COUNCIL_TIMEOUT_SECONDS = 300.0  # effort budget: one full council review
ANSWER_CHARS = 400  # effort budget: raw answer text kept per call receipt
CALLS_FILE = "stage2_calls.jsonl"
REPORT_FILE = "stage2.json"
LABELLING = "bad = the notable covers a labelled line; good = it covers none"

COUNCIL_QUESTION = """Review this proposal about one notable raised from machine-written log data.
Proposal: the notable shows an intrusion or abnormal hands-on activity (for example scanning,
exploitation, credential abuse, unauthorized access, command execution, tampering or exfiltration)
and should be raised to an analyst, rather than routine operation (boot, scheduled jobs, service
restarts, log rotation, software updates, ordinary user and service traffic).
SUPPORT the proposal when the notable shows intrusion; REJECT it when it shows routine operation.

NOTABLE:"""


class Stage2Error(RuntimeError):
    """The run cannot be evaluated as asked."""


@dataclass(frozen=True)
class CouncilJudged:
    p_yes: float | None
    decision: str
    votes: dict[str, int]
    participating: int
    roster: int
    seats: list[dict[str, Any]]
    seconds: float
    reason: str | None
    answer: str


def _council_failed(reason: str, began: float) -> CouncilJudged:
    return CouncilJudged(None, "", {}, 0, 0, [], round(time.monotonic() - began, 3), reason, "")


def parse_council(response: Mapping[str, Any], seconds: float) -> CouncilJudged:
    """The coded council result: vote-fraction p_yes plus the decision and seats."""
    answer = content_of(response)[:ANSWER_CHARS]
    block = response.get("portal_council")
    if not isinstance(block, Mapping):
        return CouncilJudged(None, "", {}, 0, 0, [], seconds, "missing_council_block", answer)
    aggregate = block.get("aggregate")
    aggregate = aggregate if isinstance(aggregate, Mapping) else {}
    decision = str(aggregate.get("decision") or "")
    raw_votes = aggregate.get("votes")
    votes = (
        {name: int(raw_votes.get(name) or 0) for name in ("SUPPORT", "REVISE", "REJECT")}
        if isinstance(raw_votes, Mapping)
        else {"SUPPORT": 0, "REVISE": 0, "REJECT": 0}
    )
    participating = int(aggregate.get("participating") or 0)
    roster = int(aggregate.get("roster") or 0)
    reviewers = block.get("reviewers")
    seats = (
        [
            {
                "member_id": str(item.get("member_id") or ""),
                "recommendation": str(item.get("recommendation") or ""),
                "confidence": float(item.get("confidence") or 0.0),
                "valid": bool(item.get("valid")),
                "error": str(item.get("error") or ""),
            }
            for item in reviewers
            if isinstance(item, Mapping)
        ]
        if isinstance(reviewers, list)
        else []
    )
    decisive = votes["SUPPORT"] + votes["REJECT"]
    if decisive <= 0:
        return CouncilJudged(
            None,
            decision,
            votes,
            participating,
            roster,
            seats,
            seconds,
            "no_decisive_votes",
            answer,
        )
    return CouncilJudged(
        votes["SUPPORT"] / decisive,
        decision,
        votes,
        participating,
        roster,
        seats,
        seconds,
        None,
        answer,
    )


def judge_council(client: JudgeClient, workspace: str, notable: Mapping[str, Any]) -> CouncilJudged:
    """One council review of one notable through the Pipeline; failures stay unjudged."""
    prompt = (COUNCIL_QUESTION + "\n" + notable_body(notable))[:JUDGE_PROMPT_CHARS]
    began = time.monotonic()
    try:
        response = client.complete(
            model=workspace,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
    except (httpx.TimeoutException, TimeoutError):
        return _council_failed("timeout", began)
    except httpx.HTTPStatusError:
        return _council_failed("http_error", began)
    except Exception:  # noqa: BLE001 -- failure is per-notable unjudged coverage
        return _council_failed("request_failed", began)
    if not isinstance(response, Mapping):
        return _council_failed("invalid_response", began)
    return parse_council(response, round(time.monotonic() - began, 3))


def _parallel[T](
    call: Callable[[dict[str, Any]], T],
    candidates: Sequence[dict[str, Any]],
    done: dict[int, T],
    indices: Sequence[int],
    concurrency: int,
) -> None:
    if not indices:
        return
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(call, candidates[index]): index for index in indices}
        for future in as_completed(futures):
            done[futures[future]] = future.result()


def _run_arm[T](
    candidates: Sequence[dict[str, Any]],
    call: Callable[[dict[str, Any]], T],
    *,
    deadline: float,
    probe: int,
    concurrency: int,
) -> tuple[list[T], dict[str, Any]]:
    """Probe the call rate, then spend the remaining deadline on as many calls as it buys."""
    began = time.monotonic()
    done: dict[int, T] = {}
    probe_n = min(max(1, probe), len(candidates))
    _parallel(call, candidates, done, list(range(probe_n)), concurrency)
    probe_seconds = time.monotonic() - began
    rate = probe_seconds / probe_n if probe_n else 0.0
    remaining = max(0.0, deadline - probe_seconds)
    budget = min(len(candidates), probe_n + (int(remaining // rate) if rate > 0 else 0))
    _parallel(call, candidates, done, list(range(probe_n, budget)), concurrency)
    basis = {
        "source": "measured_rate",
        "probe_calls": probe_n,
        "probe_seconds": round(probe_seconds, 3),
        "seconds_per_call": round(rate, 4),
        "deadline_seconds": deadline,
        "derived_budget": budget,
        "wall_seconds": round(time.monotonic() - began, 3),
    }
    return [done[index] for index in range(budget)], basis


def _separation(pairs: Sequence[tuple[bool, float]]) -> dict[str, Any]:
    bad = [value for bad, value in pairs if bad]
    good = [value for bad, value in pairs if not bad]
    return {
        "judged": len(pairs),
        "bad": len(bad),
        "good": len(good),
        "auc": _auc(bad, good),
        "yes_rate_bad": _rate(bad),
        "yes_rate_good": _rate(good),
    }


def _reasons(reasons: Sequence[str | None]) -> dict[str, int]:
    return dict(Counter(str(reason or "unjudged") for reason in reasons))


def _mean_seconds(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _finding(shape: Mapping[str, int]) -> str:
    """What the answer tokens measured: bias, a wrapper, or no answer index at all."""
    if shape["wrapped_answers"] == 0 and shape["bare_answers"] > 0:
        return (
            "yes-always is model bias, not a parse fault: every answer was a bare yes/no, so the "
            "0.5 gate is meaningless and the logprob p_yes rank is the signal. The wrapper parse "
            "is defensive only."
        )
    if shape["wrapped_answers"] > 0:
        return "answers include markdown-wrapped yes/no; the parse scores the answer token."
    return "no answer-token index in this run's calls; the wrapper question is not measured here."


def _single_report(
    results: Sequence[JudgeResult], candidates: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    pairs = [
        (candidates[index]["bad"], result.p_yes)
        for index, result in enumerate(results)
        if result.p_yes is not None
    ]
    indices = [result.decision_index for result in results if result.p_yes is not None]
    return {
        "score": "p_yes = yes/(yes+no) logprob mass at the answer token, wrapper skipped",
        **_separation(pairs),
        "unjudged_reasons": _reasons([result.reason for result in results if result.p_yes is None]),
        "wrapped_answers": sum(1 for index in indices if index is not None and index > 0),
        "bare_answers": sum(1 for index in indices if index == 0),
        "mean_seconds": _mean_seconds([result.seconds for result in results]),
        "served_models": sorted({result.served_model for result in results if result.served_model}),
        "requests": len(results),
    }


def _council_report(
    results: Sequence[CouncilJudged], candidates: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    pairs = [
        (candidates[index]["bad"], result.p_yes)
        for index, result in enumerate(results)
        if result.p_yes is not None
    ]
    decisions: dict[str, dict[str, int]] = {"bad": {}, "good": {}}
    for index, result in enumerate(results):
        side = "bad" if candidates[index]["bad"] else "good"
        label = result.decision if result.decision in ("SUPPORT", "REJECT") else "ABSTAIN"
        decisions[side][label] = decisions[side].get(label, 0) + 1
    rates = {}
    for side in ("bad", "good"):
        counts = decisions[side]
        total = sum(counts.values())
        rates[f"decision_yes_rate_{side}"] = counts.get("SUPPORT", 0) / total if total else None
        rates[f"decision_no_rate_{side}"] = counts.get("REJECT", 0) / total if total else None
        rates[f"abstain_{side}"] = counts.get("ABSTAIN", 0)
    return {
        "score": "p_yes = SUPPORT/(SUPPORT+REJECT) seat votes; decision yes-rate: SUPPORT=yes, "
        "REJECT=no, REVISE/ESCALATE=abstain",
        **_separation(pairs),
        **rates,
        "decisions": dict(Counter(result.decision or "NONE" for result in results)),
        "unjudged_reasons": _reasons([result.reason for result in results if result.p_yes is None]),
        "mean_seconds": _mean_seconds([result.seconds for result in results]),
        "requests": len(results),
    }


def _candidates(
    rows: Sequence[dict[str, Any]], notables: Sequence[Notable]
) -> list[dict[str, Any]]:
    covered = {notable.content_key: notable.covered for notable in notables}
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _judge_order(rows):
        key = str(row.get("content_key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        found.append({"content_key": key, "notable": row, "bad": covered.get(key, False)})
    return found


def _baseline(candidates: Sequence[dict[str, Any]], cache: Mapping[str, Any]) -> dict[str, Any]:
    pairs: list[tuple[bool, float]] = []
    for candidate in candidates:
        value = candidate["notable"].get("p_yes")
        if value is None:
            stored = cache.get(candidate["content_key"])
            if isinstance(stored, Mapping):
                value = stored.get("p_yes")
        if value is not None:
            pairs.append((candidate["bad"], float(value)))
    return {
        "score": "incumbent first-token p_yes recorded by the Stage 1 run itself",
        **_separation(pairs),
    }


def _call_records(
    arm: str,
    results: Sequence[Any],
    candidates: Sequence[dict[str, Any]],
    common: int,
) -> list[dict[str, Any]]:
    records = []
    for index, result in enumerate(results):
        record: dict[str, Any] = {
            "arm": arm,
            "content_key": candidates[index]["content_key"],
            "bad": candidates[index]["bad"],
            "common": index < common,
            "p_yes": result.p_yes,
            "seconds": result.seconds,
            "reason": result.reason,
            "answer": result.answer[:ANSWER_CHARS],
        }
        if arm == "single_judge":
            record["decision_index"] = result.decision_index
            record["served_model"] = result.served_model
        else:
            record["decision"] = result.decision
            record["votes"] = result.votes
            record["participating"] = result.participating
            record["roster"] = result.roster
            record["seats"] = result.seats
        records.append(record)
    return records


def evaluate_family(
    family: str,
    directory: Path,
    keys_path: Path,
    logs: Path | None,
    year: int | None,
    *,
    judge_target: tuple[JudgeClient, str],
    council_client: JudgeClient,
    council_workspace: str = COUNCIL_WORKSPACE,
    deadline: float = STAGE2_DEADLINE_SECONDS,
    concurrency: int = 2,
    probe: int = STAGE2_PROBE_CALLS,
    limit: int | None = None,
) -> dict[str, Any]:
    """Label one family's notables, judge them with both arms, score separation."""
    rows = _read_notables(directory)
    progress = read_json(directory / PROGRESS_FILE)
    if not progress:
        raise Stage2Error(f"{directory / PROGRESS_FILE} is missing; this run is not scored")
    keys = _read_keys(keys_path)
    index, run_sources = _run_index(directory)
    _check_family(index, keys, run_sources)
    if index in PROOF_INDEXES or index not in TRAINING_INDEXES:
        raise Stage2Error(
            f"{index!r} is not a training index ({', '.join(sorted(TRAINING_INDEXES))})"
        )
    honesty = _honesty(progress, family)
    resolved = logs if logs is not None else _default_logs(keys_path)
    picked = year if year is not None else _year(progress, rows)
    steps = _steps(keys)
    notables = [
        Notable(
            rank,
            str(row.get("generator") or ""),
            _claim(row),
            float(row["p_yes"]) if row.get("p_yes") is not None else None,
            str(row.get("content_key") or ""),
        )
        for rank, row in enumerate(rows)
    ]
    _coverage(steps, notables, keys, resolved, picked)
    candidates = _candidates(rows, notables)
    judge_client, judge_model = judge_target

    def single_call(item: dict[str, Any]) -> JudgeResult:
        return judge_cell(judge_client, model=judge_model, prompt=notable_prompt(item["notable"]))

    def council_call(item: dict[str, Any]) -> CouncilJudged:
        return judge_council(council_client, council_workspace, item["notable"])

    single_results, single_basis = _run_arm(
        candidates, single_call, deadline=deadline, probe=probe, concurrency=concurrency
    )
    council_results, council_basis = _run_arm(
        candidates, council_call, deadline=deadline, probe=probe, concurrency=concurrency
    )
    common = min(len(single_results), len(council_results))
    if limit is not None:
        common = min(common, max(0, limit))
    records = _call_records("single_judge", single_results, candidates, common)
    records += _call_records("council", council_results, candidates, common)
    calls_path = directory / CALLS_FILE
    calls_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    single_report = _single_report(single_results[:common], candidates)
    finding = _finding(single_report)
    report = {
        "family": family,
        "index": index,
        "generated": utc_now(),
        "rule": RULE,
        "labelling": LABELLING,
        "finding": finding,
        "honesty": honesty,
        "keys": {
            "file": str(keys_path),
            "labelled_lines": len(keys),
            "logs": str(resolved),
            "year": picked,
        },
        "notables": {
            "total": len(rows),
            "distinct": len(candidates),
            "bad": sum(1 for candidate in candidates if candidate["bad"]),
            "good": sum(1 for candidate in candidates if not candidate["bad"]),
        },
        "common_notables": common,
        "deadline_seconds": deadline,
        "concurrency": concurrency,
        "stage1_judge": _baseline(candidates, read_json(directory / JUDGE_CACHE)),
        "single_judge": {
            "model": judge_model,
            "budget_basis": single_basis,
            **single_report,
        },
        "council": {
            "workspace": council_workspace,
            "budget_basis": council_basis,
            **_council_report(council_results[:common], candidates),
        },
        "calls_file": str(calls_path),
    }
    write_json(directory / REPORT_FILE, report)
    return report


def score(
    out: Path,
    key_args: Sequence[str],
    *,
    judge_target: tuple[JudgeClient, str],
    council_client: JudgeClient,
    logs: Path | None = None,
    year: int | None = None,
    council_workspace: str = COUNCIL_WORKSPACE,
    deadline: float = STAGE2_DEADLINE_SECONDS,
    concurrency: int = 2,
    probe: int = STAGE2_PROBE_CALLS,
    limit: int | None = None,
) -> dict[str, Any]:
    targets = _targets(out)
    keys = _key_paths(key_args, [family for family, _directory in targets])
    return {
        "families": [
            evaluate_family(
                family,
                directory,
                keys[family],
                logs,
                year,
                judge_target=judge_target,
                council_client=council_client,
                council_workspace=council_workspace,
                deadline=deadline,
                concurrency=concurrency,
                probe=probe,
                limit=limit,
            )
            for family, directory in targets
        ]
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _summary_lines(report: Mapping[str, Any]) -> list[str]:
    notables = report["notables"]
    lines = [
        f"family {report['family']}  index {report['index']}  "
        f"notables {notables['total']} distinct {notables['distinct']} "
        f"bad {notables['bad']} good {notables['good']}",
        f"honesty {report['honesty']}",
        f"common notables {report['common_notables']}  "
        f"deadline {report['deadline_seconds']}s per arm  concurrency {report['concurrency']}",
        f"{'arm':<14}{'judged':>7}{'bad':>5}{'good':>6}{'AUC':>8}"
        f"{'yes-bad':>9}{'yes-good':>9}{'s/call':>8}{'budget':>8}",
    ]
    for arm in ("stage1_judge", "single_judge", "council"):
        block = report[arm]
        basis = block.get("budget_basis") or {}
        lines.append(
            f"{arm:<14}{block['judged']:>7}{block['bad']:>5}{block['good']:>6}"
            f"{_fmt(block['auc']):>8}{_fmt(block['yes_rate_bad']):>9}"
            f"{_fmt(block['yes_rate_good']):>9}"
            f"{_fmt(basis.get('seconds_per_call')):>8}{basis.get('derived_budget', '-'):>8}"
        )
    council = report["council"]
    lines.append(
        f"council decisions {council['decisions']}  "
        f"decision yes-rate bad {_fmt(council['decision_yes_rate_bad'])} "
        f"good {_fmt(council['decision_yes_rate_good'])}  "
        f"abstain bad {council['abstain_bad']} good {council['abstain_good']}"
    )
    single = report["single_judge"]
    lines.append(
        f"single judge wrapped answers {single['wrapped_answers']} "
        f"bare {single['bare_answers']}  unjudged {single['unjudged_reasons']}"
    )
    lines.append(f"council unjudged {council['unjudged_reasons']}")
    lines.append(f"calls {report['calls_file']}")
    return lines


def render(report: Mapping[str, Any]) -> str:
    return "\n".join(_summary_lines(report))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="run dir, or the dir of families")
    parser.add_argument(
        "--keys",
        action="append",
        required=True,
        help="family=path to that family's keys.jsonl (repeat per family)",
    )
    parser.add_argument("--logs", type=Path, help="raw log tree holding the labelled lines")
    parser.add_argument("--year", type=int, help="year for a timestamp that carries none")
    parser.add_argument(
        "--council-workspace", default=COUNCIL_WORKSPACE, help="Pipeline council workspace id"
    )
    parser.add_argument(
        "--deadline",
        type=float,
        default=STAGE2_DEADLINE_SECONDS,
        help="wall seconds each arm may spend (budget = measured rate x deadline)",
    )
    parser.add_argument("--concurrency", type=int, default=2, help="parallel calls per arm")
    parser.add_argument("--probe", type=int, default=STAGE2_PROBE_CALLS, help="calibration calls")
    parser.add_argument("--limit", type=int, help="cap the common notable set")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    target = model_from_env()
    if target is None:
        print(model_requirement(), file=sys.stderr)
        return 2
    url = os.environ.get("PORTAL_HUNT_JUDGE_URL", "")
    key_env = os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", DEFAULT_KEY_ENV)
    api_key = os.environ.get(key_env) if key_env else None
    council_client = OpenAICompatibleClient(
        chat_completions_endpoint(url), api_key, timeout_seconds=COUNCIL_TIMEOUT_SECONDS
    )
    started = time.monotonic()
    try:
        report = score(
            args.out,
            args.keys,
            judge_target=target,
            council_client=council_client,
            logs=args.logs,
            year=args.year,
            council_workspace=args.council_workspace,
            deadline=args.deadline,
            concurrency=args.concurrency,
            probe=args.probe,
            limit=args.limit,
        )
    except (Stage2Error, ScoreboardError) as error:
        print(f"stage2: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=False))
    else:
        print(
            "\n\n".join(render(family) for family in report["families"])
            + f"\n\nscored in {time.monotonic() - started:.1f}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
