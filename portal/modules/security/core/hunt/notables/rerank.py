"""Stage 2 re-rank: fuse the Stage 1 order with judge p_yes, then a council second pass.

python -m portal.modules.security.core.hunt.notables.rerank \
    --run kyoushi=<run dir> --run santos=<run dir> \
    --keys kyoushi=<keys.jsonl> --keys santos=<keys.jsonl> [--offline]

The live Stage 2 receipt (receipts_stage2_live1_20261116.log) measured the judge's
yes-always as model bias, not a parse fault: 0 wrapped answers, 31 bare. The 0.5
yes/no gate is therefore not the signal — the logprob p_yes rank is. This module
combines the Stage 1 order with p_yes by a weighted rank fusion whose weight is
chosen across the training families by leave-one-family-out (no per-corpus
constant), then runs the Portal council only on the top-K (K = the deadline divided
by the measured council seconds per call) and lets SUPPORT/REJECT adjust order
within K. Recall@50/@100 is reported before and after. All model calls go through
the Pipeline; --offline replays the stored Stage 2 council calls instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..judge import DEFAULT_KEY_ENV, JudgeClient, OpenAICompatibleClient, chat_completions_endpoint
from . import stage2 as stage2_run
from .receipt import read_json, utc_now, write_json
from .scoreboard import (
    PROGRESS_FILE,
    Notable,
    ScoreboardError,
    _check_family,
    _claim,
    _covers,
    _default_logs,
    _honesty,
    _on_source,
    _read_keys,
    _read_notables,
    _run_index,
    _steps,
    _year,
    event_time,
)
from .stage2 import (
    COUNCIL_TIMEOUT_SECONDS,
    COUNCIL_WORKSPACE,
    CouncilJudged,
    Stage2Error,
    _run_arm,
    judge_council,
)

FUSION_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)  # candidate p_yes weights, chosen by LOFO
RECALL_CUTS = (50, 100)
COUNCIL_DEADLINE_SECONDS = 720.0  # effort budget: the hunt job wall time for the second pass
COUNCIL_PROBE_CALLS = 4  # effort budget: calibration sample measuring the council rate
DECISION_RANK = {"SUPPORT": 0, "REJECT": 2}  # absent / REVISE / ESCALATE -> 1 (abstain)
REPORT_FILE = "rerank.json"
CALLS_FILE = "rerank_council_calls.jsonl"
LOFO_RULE = (
    "weight chosen on the other training families by recall@50 + recall@100; "
    "ties take the smallest weight"
)
BIAS_NOTE = (
    "the measured cause is model bias, not a parse fault: live Stage 2 (kyoushi, 31 common "
    "notables, 2026-11-16) recorded 0 wrapped answers and 31 bare, yes-rate 1.0/1.0, so the 0.5 "
    "gate is meaningless and the logprob p_yes rank is the signal. The wrapper parse is "
    "defensive only."
)


@dataclass
class Family:
    name: str
    run: Path
    rows: list[dict[str, Any]]
    notables: list[Notable]
    cmap: dict[str, set[int]]
    n_steps: int
    scores: dict[float, dict[Any, int]] = field(default_factory=dict)
    honesty: dict[str, Any] = field(default_factory=dict)
    year: int = 0


def _rule_name(weight: float) -> str:
    if weight <= 0.0:
        return "stage1"
    if weight >= 1.0:
        return "p_yes"
    return f"fusion_w{weight:g}"


def _coverage_map(
    notables: Sequence[Notable], keys: Sequence[Any], logs: Path, year: int
) -> dict[str, set[int]]:
    """step label -> indices of notables that cover one of its labelled lines."""
    wanted: dict[tuple[str, str], dict[int, tuple[str, ...]]] = defaultdict(dict)
    for line in keys:
        wanted[(line.host, line.source)][line.number] = line.labels
    cmap: dict[str, set[int]] = defaultdict(set)
    timed = any(not notable.claim.terms for notable in notables)
    for (host, source), lines in sorted(wanted.items()):
        path = logs / host / "logs" / source.lstrip("/")
        if not path.is_file():
            raise ScoreboardError(f"keys name {host}{source} but {path} is not there")
        active = [
            (index, notable)
            for index, notable in enumerate(notables)
            if _on_source(notable.claim, source)
        ]
        if not active:
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, 1):
                labels = lines.get(number)
                if labels is None:
                    continue
                text = raw.rstrip("\r\n")
                folded = text.casefold()
                moment = event_time(text, year) if timed else None
                for index, notable in active:
                    if _covers(notable.claim, folded, moment):
                        for label in labels:
                            cmap[label].add(index)
    return cmap


def _recall(cmap: Mapping[str, set[int]], rank_of: Mapping[int, int]) -> dict[Any, int]:
    first = {label: min(rank_of[i] for i in indices) for label, indices in cmap.items() if indices}
    out: dict[Any, int] = {
        cut: sum(1 for rank in first.values() if rank < cut) for cut in RECALL_CUTS
    }
    out[None] = len(first)
    return out


def _fusion_order(notables: Sequence[Notable], weight: float) -> list[int]:
    """Weighted fusion of the Stage 1 rank and the p_yes rank; unjudged rank last."""
    count = len(notables)
    indices = list(range(count))
    if weight <= 0.0:
        return indices
    judged = sorted(
        (i for i in indices if notables[i].p_yes is not None),
        key=lambda i: (-(notables[i].p_yes or 0.0), i),
    )
    unjudged = [i for i in indices if notables[i].p_yes is None]
    if weight >= 1.0:
        return judged + unjudged
    pyes_rank = {ni: rank for rank, ni in enumerate(judged + unjudged)}
    denom = max(1, count - 1)
    score = {i: weight * pyes_rank[i] / denom + (1.0 - weight) * i / denom for i in indices}
    return sorted(indices, key=lambda i: (score[i], i))


def _rank_of(order: Sequence[int]) -> dict[int, int]:
    return {ni: rank for rank, ni in enumerate(order)}


def _family_scores(family: Family) -> None:
    for weight in FUSION_WEIGHTS:
        order = _fusion_order(family.notables, weight)
        family.scores[weight] = _recall(family.cmap, _rank_of(order))


def _metric(families: Mapping[str, Family], names: Sequence[str], weight: float) -> int:
    return sum(families[name].scores[weight][cut] for name in names for cut in RECALL_CUTS)


def _select_weight(
    families: Mapping[str, Family],
) -> tuple[float, dict[str, float]]:
    """LOFO: choose the weight on the other families; ties take the smallest weight."""
    names = list(families)
    global_weight = min(FUSION_WEIGHTS, key=lambda w: (-_metric(families, names, w), w))
    folds: dict[str, float] = {}
    for held in names:
        others = [name for name in names if name != held]
        folds[held] = (
            min(FUSION_WEIGHTS, key=lambda w: (-_metric(families, others, w), w))
            if others
            else global_weight
        )
    return global_weight, folds


def _council_adjust(
    order: Sequence[int], notables: Sequence[Notable], decisions: Mapping[str, str], top_k: int
) -> tuple[list[int], int]:
    """Within the top-K, SUPPORT rises and REJECT sinks; ties keep the re-rank order."""
    head = list(order[:top_k])
    tail = list(order[top_k:])
    before = {ni: rank for rank, ni in enumerate(head)}
    head.sort(key=lambda ni: DECISION_RANK.get(decisions.get(notables[ni].content_key, ""), 1))
    moved = sum(1 for rank, ni in enumerate(head) if before[ni] != rank)
    return head + tail, moved


def _stored_council(run: Path) -> tuple[dict[str, str], dict[str, Any] | None]:
    """The stored council decisions and the Stage 2 rate that measured a call, if the run has them."""
    decisions: dict[str, str] = {}
    path = run / stage2_run.CALLS_FILE
    if path.is_file():
        for raw in path.read_text().splitlines():
            if not raw.strip():
                continue
            call = json.loads(raw)
            if call.get("arm") == "council" and call.get("decision"):
                decisions[str(call.get("content_key"))] = str(call["decision"])
    council = read_json(run / stage2_run.REPORT_FILE).get("council")
    basis = council.get("budget_basis") if isinstance(council, Mapping) else None
    return decisions, dict(basis) if isinstance(basis, Mapping) else None


def _council_budget(count: int, deadline: float, rate: float | None) -> int:
    """K: how many council reviews the deadline buys at the measured seconds per call."""
    if rate is None or rate <= 0:
        return 0
    return min(count, int(deadline // rate))


def _answer_shape(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    wrapped = bare = 0
    for row in rows:
        judge = row.get("judge")
        index = judge.get("decision_index") if isinstance(judge, Mapping) else None
        if index is None:
            continue
        if index > 0:
            wrapped += 1
        else:
            bare += 1
    return {"wrapped_answers": wrapped, "bare_answers": bare}


def _load_family(name: str, run: Path, keys_path: Path, year: int | None) -> Family:
    rows = _read_notables(run)
    progress = read_json(run / PROGRESS_FILE)
    if not progress:
        raise Stage2Error(f"{run / PROGRESS_FILE} is missing; this run is not scored")
    keys = _read_keys(keys_path)
    index, run_sources = _run_index(run)
    _check_family(index, keys, run_sources)
    honesty = _honesty(progress, name)
    logs = _default_logs(keys_path)
    picked = year if year is not None else _year(progress, rows)
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
    cmap = _coverage_map(notables, keys, logs, picked)
    family = Family(
        name, run, rows, notables, cmap, len(_steps(keys)), honesty=honesty, year=picked
    )
    _family_scores(family)
    return family


def _council_second_pass(
    family: Family,
    order: list[int],
    *,
    offline: bool,
    council_client: JudgeClient | None,
    council_workspace: str,
    deadline: float,
    concurrency: int,
    probe: int,
) -> tuple[list[int], dict[str, Any]]:
    notables = family.notables
    if offline:
        decisions, basis = _stored_council(family.run)
        rate = basis.get("seconds_per_call") if basis else None
        top_k = _council_budget(len(order), deadline, float(rate) if rate else None)
        final, moved = _council_adjust(order, notables, decisions, top_k)
        return final, {
            "source": "stored_calls",
            "top_k": top_k,
            "budget_basis": basis
            or {"source": "none", "deadline_seconds": deadline, "seconds_per_call": None},
            "decisions": dict(_decision_counts(decisions)),
            "decisions_in_k": sum(
                1 for ni in order[:top_k] if notables[ni].content_key in decisions
            ),
            "moved_within_k": moved,
        }
    assert council_client is not None
    candidates: list[dict[str, Any]] = [
        {"notable": family.rows[ni], "content_key": notables[ni].content_key} for ni in order
    ]

    def call(item: dict[str, Any]) -> CouncilJudged:
        return judge_council(council_client, council_workspace, item["notable"])

    results, basis = _run_arm(
        candidates, call, deadline=deadline, probe=probe, concurrency=concurrency
    )
    decisions = {
        candidates[index]["content_key"]: result.decision
        for index, result in enumerate(results)
        if result.decision
    }
    top_k = len(results)
    final, moved = _council_adjust(order, notables, decisions, top_k)
    records = [
        {
            "content_key": candidates[index]["content_key"],
            "decision": result.decision,
            "p_yes": result.p_yes,
            "votes": result.votes,
            "seconds": result.seconds,
            "reason": result.reason,
        }
        for index, result in enumerate(results)
    ]
    (family.run / CALLS_FILE).write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    )
    return final, {
        "source": "live",
        "top_k": top_k,
        "budget_basis": basis,
        "decisions": dict(_decision_counts(decisions)),
        "moved_within_k": moved,
        "unjudged_reasons": _reason_counts(results),
        "calls_file": str(family.run / CALLS_FILE),
    }


def _decision_counts(decisions: Mapping[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions.values():
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _reason_counts(results: Sequence[CouncilJudged]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        if result.p_yes is None:
            counts[str(result.reason or "unjudged")] = (
                counts.get(str(result.reason or "unjudged"), 0) + 1
            )
    return counts


def _recall_row(scores: Mapping[Any, int]) -> dict[str, int]:
    return {str(cut): scores[cut] for cut in (*RECALL_CUTS, None)}


def _lofo_table(family: Family) -> dict[str, dict[str, int]]:
    """The training scoreboard: each candidate weight's recall on this family."""
    return {_rule_name(weight): _recall_row(family.scores[weight]) for weight in FUSION_WEIGHTS}


def _family_report(
    family: Family,
    weight: float,
    global_weight: float,
    weight_basis: str,
    final: list[int],
    council: dict[str, Any],
) -> dict[str, Any]:
    notables = family.notables
    before = _recall(family.cmap, _rank_of(list(range(len(notables)))))
    reranked = _fusion_order(notables, weight)
    after_rerank = _recall(family.cmap, _rank_of(reranked))
    after_council = _recall(family.cmap, _rank_of(final))
    return {
        "family": family.name,
        "year": family.year,
        "honesty": family.honesty,
        "notables": len(notables),
        "judged": sum(1 for n in notables if n.p_yes is not None),
        "steps": family.n_steps,
        "answer_shape": _answer_shape(family.rows),
        "finding": BIAS_NOTE,
        "chosen_weight": weight,
        "chosen_rule": _rule_name(weight),
        "weight_basis": weight_basis,
        "global_weight": global_weight,
        "lofo": _lofo_table(family),
        "recall": {
            "before": _recall_row(before),
            "after_rerank": _recall_row(after_rerank),
            "after_council": _recall_row(after_council),
        },
        "council": council,
    }


def product_order(
    rows: Sequence[dict[str, Any]],
    *,
    run: Path,
    council_client: JudgeClient,
    deadline: float,
    council_workspace: str = COUNCIL_WORKSPACE,
    concurrency: int = 2,
    probe: int = COUNCIL_PROBE_CALLS,
) -> tuple[list[int], dict[str, Any]]:
    normalized = [dict(row) for row in rows]
    notables = []
    for rank, row in enumerate(normalized):
        key = str(row.get("content_key") or f"product:{row.get('notable_id') or rank}")
        row["content_key"] = key
        try:
            p_yes = float(row["p_yes"]) if row.get("p_yes") is not None else None
        except (TypeError, ValueError):
            p_yes = None
        notables.append(Notable(rank, str(row.get("generator") or ""), _claim(row), p_yes, key))
    order = _fusion_order(notables, 1.0)
    if order and deadline > 0:
        family = Family("product", run, normalized, notables, {}, 0)
        final, council = _council_second_pass(
            family,
            order,
            offline=False,
            council_client=council_client,
            council_workspace=council_workspace,
            deadline=deadline,
            concurrency=concurrency,
            probe=probe,
        )
        calls_file = council.get("calls_file")
        if isinstance(calls_file, str):
            records = [
                json.loads(line)
                for line in Path(calls_file).read_text().splitlines()
                if line.strip()
            ]
            council["model_seconds"] = round(
                sum(float(record.get("seconds") or 0) for record in records), 3
            )
    else:
        final = order
        council = {
            "source": "skipped",
            "top_k": 0,
            "budget_basis": {
                "source": "no_budget" if not deadline else "no_notables",
                "deadline_seconds": deadline,
                "seconds_per_call": None,
                "derived_budget": 0,
            },
        }
    return final, {
        "content_keys": [notable.content_key for notable in notables],
        "weight": 1.0,
        "weight_basis": "p_yes_signal_without_product_label_keys",
        "council": council,
    }


def score(
    runs: Mapping[str, Path],
    keys: Mapping[str, Path],
    *,
    year: int | None = None,
    offline: bool = False,
    council: bool = True,
    council_client: JudgeClient | None = None,
    council_workspace: str = COUNCIL_WORKSPACE,
    council_deadline: float = COUNCIL_DEADLINE_SECONDS,
    concurrency: int = 2,
    probe: int = COUNCIL_PROBE_CALLS,
) -> dict[str, Any]:
    families = {name: _load_family(name, run, keys[name], year) for name, run in runs.items()}
    global_weight, folds = _select_weight(families)
    basis = "lofo" if len(families) > 1 else "self"
    reports = []
    for name, family in families.items():
        weight = folds[name]
        order = _fusion_order(family.notables, weight)
        if council:
            final, council_receipt = _council_second_pass(
                family,
                order,
                offline=offline,
                council_client=council_client,
                council_workspace=council_workspace,
                deadline=council_deadline,
                concurrency=concurrency,
                probe=probe,
            )
        else:
            final, council_receipt = order, {"source": "skipped"}
        reports.append(_family_report(family, weight, global_weight, basis, final, council_receipt))
    report = {
        "generated": utc_now(),
        "fusion_weights": list(FUSION_WEIGHTS),
        "lofo_rule": LOFO_RULE,
        "global_weight": global_weight,
        "global_rule": _rule_name(global_weight),
        "lofo_folds": folds,
        "finding": BIAS_NOTE,
        "families": reports,
    }
    for family in families.values():
        write_json(family.run / REPORT_FILE, report)
    return report


def _fmt_recall(block: Mapping[str, Any], steps: int) -> str:
    return f"@50 {block['50']}/{steps} @100 {block['100']}/{steps} all {block['None']}/{steps}"


def _fmt_lofo(table: Mapping[str, Mapping[str, int]]) -> str:
    return "  ".join(f"{name} {row['50']}/{row['100']}" for name, row in table.items())


def render(report: Mapping[str, Any]) -> str:
    lines = [
        f"pooled best {_rule_name(report['global_weight'])} "
        f"(w={report['global_weight']:g}; diagnostic, not applied)  "
        f"LOFO folds {report['lofo_folds']}",
        f"LOFO {report['lofo_rule']}",
        f"finding: {report['finding']}",
    ]
    for fam in report["families"]:
        steps = fam["steps"]
        recall = fam["recall"]
        lines += [
            "",
            f"family {fam['family']}  notables {fam['notables']} judged {fam['judged']} "
            f"steps {steps}  answers {fam['answer_shape']}",
            f"  chosen {_rule_name(fam['chosen_weight'])} (w={fam['chosen_weight']:g}) "
            f"basis {fam['weight_basis']}  "
            f"honesty excluded {fam['honesty'].get('excluded_family')}",
            f"  candidates @50/@100  {_fmt_lofo(fam['lofo'])}",
            f"  before        {_fmt_recall(recall['before'], steps)}",
            f"  after rerank  {_fmt_recall(recall['after_rerank'], steps)}",
            f"  after council {_fmt_recall(recall['after_council'], steps)}",
            f"  council {fam['council']}",
        ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, help="family=run-dir (repeat)")
    parser.add_argument("--keys", action="append", required=True, help="family=keys.jsonl (repeat)")
    parser.add_argument("--year", type=int, help="year for a timestamp that carries none")
    parser.add_argument("--offline", action="store_true", help="replay stored council calls")
    parser.add_argument("--no-council", action="store_true", help="skip the council second pass")
    parser.add_argument("--council-workspace", default=COUNCIL_WORKSPACE)
    parser.add_argument("--council-deadline", type=float, default=COUNCIL_DEADLINE_SECONDS)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--probe", type=int, default=COUNCIL_PROBE_CALLS)
    parser.add_argument("--json", action="store_true")
    return parser


def _pairs(values: Sequence[str], flag: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for value in values:
        name, _, path = value.partition("=")
        if not name or not path:
            raise Stage2Error(f"--{flag} {value!r} is not family=path")
        found[name.strip()] = Path(path)
    return found


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        runs = _pairs(args.run, "run")
        keys = _pairs(args.keys, "keys")
        missing = sorted(set(runs) - set(keys))
        if missing:
            raise Stage2Error(f"no --keys given for {', '.join(missing)}")
        council_client = None
        if not args.offline and not args.no_council:
            url = os.environ.get("PORTAL_HUNT_JUDGE_URL", "")
            key_env = os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", DEFAULT_KEY_ENV)
            api_key = os.environ.get(key_env) if key_env else None
            if not url:
                print("set PORTAL_HUNT_JUDGE_URL (the Pipeline :9099 endpoint)", file=sys.stderr)
                return 2
            council_client = OpenAICompatibleClient(
                chat_completions_endpoint(url), api_key, timeout_seconds=COUNCIL_TIMEOUT_SECONDS
            )
        started = time.monotonic()
        report = score(
            runs,
            keys,
            year=args.year,
            offline=args.offline,
            council=not args.no_council,
            council_client=council_client,
            council_workspace=args.council_workspace,
            council_deadline=args.council_deadline,
            concurrency=args.concurrency,
            probe=args.probe,
        )
    except (Stage2Error, ScoreboardError) as error:
        print(f"rerank: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=False))
    else:
        print(render(report) + f"\n\nscored in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
