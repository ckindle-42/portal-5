"""python -m portal.modules.security.core.hunt.notables — cards, behaviours, notables, judge."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from .behaviours import Behaviour
from .pipeline import model_from_env, model_requirement
from .run import (
    GENERATORS,
    STAGES,
    behaviours_stage,
    cards_stage,
    default_search,
    judge_stage,
    notables_stage,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, help="index to review")
    parser.add_argument("--out", required=True, help="directory for receipts and stores")
    parser.add_argument(
        "--stage",
        choices=(*STAGES, "all"),
        default="all",
        help="which stage to run (default: all)",
    )
    parser.add_argument("--start", type=float, default=0.0, help="earliest epoch seconds")
    parser.add_argument("--end", type=float, default=None, help="latest epoch seconds")
    parser.add_argument(
        "--generators",
        default=",".join(GENERATORS),
        help="comma-separated generators (default: all)",
    )
    return parser


def _print_behaviours(behaviours: list[Behaviour], receipt: dict[str, Any]) -> None:
    counts: dict[str, int] = {}
    for behaviour in behaviours:
        counts[behaviour.source_id] = counts.get(behaviour.source_id, 0) + 1
    for item in receipt.get("receipts", []):
        print(
            f"  {item['source_id']} events={item['events_read']} "
            f"of={item['events_available']} share={item['share_of_source']} "
            f"windows={item['windows']} behaviours={counts.get(item['source_id'], 0)} "
            f"seconds={item['seconds']}"
        )
    for item in receipt.get("skipped", []):
        print(f"  skipped {item['source_id']}: {item['reason']}")
    print(
        f"behaviours: events_read={receipt['events_read']} "
        f"existed={receipt['behaviours_existed']} kept={receipt['behaviours_kept']} "
        f"wall={receipt['seconds']}s peak={receipt['peak_memory_mb']}MB -> {receipt['store']}"
    )


def _print_judge(receipt: dict[str, Any]) -> None:
    print(
        f"judge: notables={receipt['notables']} judged={receipt['judged']} "
        f"unjudged={receipt['unjudged']} reasons={receipt['unjudged_reasons']} "
        f"requests={receipt['requests']} cached={receipt['cached']} "
        f"model_seconds={receipt['model_seconds']} wall={receipt['seconds']}s "
        f"served={receipt['served_models']} -> {receipt['file']}"
    )


def _print_notables(receipt: dict[str, Any]) -> None:
    raw_seconds = receipt.get("seconds")
    seconds: dict[str, Any] = raw_seconds if isinstance(raw_seconds, dict) else {}
    for name in GENERATORS:
        detail = receipt.get(name)
        if isinstance(detail, dict):
            print(
                f"  {name}: existed={detail.get('existed')} kept={detail.get('kept')} "
                f"seconds={seconds.get(name)}"
            )
    print(
        f"notables: total={receipt['total']} wall={seconds.get('total')}s "
        f"peak={receipt['peak_memory_mb']}MB -> {receipt['file']}"
    )


def _print_cards(receipt: dict[str, Any]) -> None:
    for item in receipt.get("sources_receipt", []):
        reason = f" reason={item['reason']}" if item.get("reason") else ""
        print(
            f"  {item['source_id']} kind={item['kind']} understood={item['understood']} "
            f"roles=[{item['roles']}] structure={item['structure']} "
            f"sample={item['sample_lines']} coverage={item['parse_coverage']:.2f} "
            f"model={item['model_seconds']}s{reason}"
        )
    print(
        f"cards: sources={receipt['sources']} understood={receipt['understood']} "
        f"unparsed={receipt['unparsed']} model_requests={receipt['model_requests']} "
        f"model_seconds={receipt['model_seconds']} wall={receipt['seconds']}s "
        f"peak={receipt['peak_memory_mb']}MB -> sources.json"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    end = args.end if args.end is not None else time.time() + 1.0
    stages = STAGES if args.stage == "all" else (args.stage,)
    target = model_from_env()
    search = default_search()
    if "cards" in stages:
        if target is None:
            print(model_requirement(), file=sys.stderr)
            return 2
        client, model = target
        receipt = cards_stage(
            index=args.index,
            out=out,
            start=args.start,
            end=end,
            client=client,
            model=model,
            search=search,
        )
        _print_cards(receipt)
    if "behaviours" in stages:
        behaviours, receipt = behaviours_stage(out=out, search=search)
        _print_behaviours(behaviours, receipt)
    if "notables" in stages:
        enabled = [name.strip() for name in args.generators.split(",") if name.strip()]
        unknown = sorted(set(enabled) - set(GENERATORS))
        if unknown:
            print(f"unknown generators: {', '.join(unknown)}", file=sys.stderr)
            return 2
        _rows, receipt = notables_stage(
            index=args.index,
            out=out,
            start=args.start,
            end=end,
            search=search,
            enabled=enabled,
        )
        _print_notables(receipt)
    if "judge" in stages:
        if target is None:
            print(model_requirement(), file=sys.stderr)
            return 2
        client, model = target
        _judged, receipt = judge_stage(out=out, client=client, model=model)
        _print_judge(receipt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
