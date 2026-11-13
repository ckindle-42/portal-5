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


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _label(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or item.get("card_id") or "?")


def _print_behaviours(behaviours: list[Behaviour], receipt: dict[str, Any]) -> None:
    counts: dict[str, int] = {}
    for behaviour in behaviours:
        counts[behaviour.source_id] = counts.get(behaviour.source_id, 0) + 1
    for item in receipt.get("receipts", []):
        print(
            f"  {_label(item)} events={item.get('events_read', 0)} "
            f"of={item.get('events_available', 0)} share={item.get('share_of_source')} "
            f"windows={item.get('windows', 0)} "
            f"behaviours={item.get('behaviours', counts.get(_label(item), 0))} "
            f"singletons={item.get('singletons', 0)} "
            f"singleton_share={item.get('singleton_share')} "
            f"seconds={item.get('seconds')}"
        )
    for item in receipt.get("skipped", []):
        print(
            f"  skipped {_label(item)}: {item.get('reason') or 'unknown'} "
            f"behaviours={item.get('behaviours', 0)}"
        )
    print(
        f"behaviours: events_read={receipt.get('events_read', 0)} "
        f"existed={receipt.get('behaviours_existed', 0)} "
        f"kept={receipt.get('behaviours_kept', 0)} "
        f"wall={receipt.get('seconds')}s peak={receipt.get('peak_memory_mb')}MB "
        f"-> {receipt.get('store')}"
    )


def _print_judge(receipt: dict[str, Any]) -> None:
    print(
        f"judge: notables={receipt.get('notables', 0)} judged={receipt.get('judged', 0)} "
        f"unjudged={receipt.get('unjudged', 0)} "
        f"reasons={receipt.get('unjudged_reasons', {})} "
        f"requests={receipt.get('requests', 0)} cached={receipt.get('cached', 0)} "
        f"budget={receipt.get('request_budget')} unasked={receipt.get('unasked', 0)} "
        f"throttles={_mapping(receipt.get('backpressure')).get('throttles', 0)} "
        f"retries={_mapping(receipt.get('backpressure')).get('retries', 0)} "
        f"model_seconds={receipt.get('model_seconds', 0)} "
        f"wall={receipt.get('seconds')}s served={receipt.get('served_models', [])} "
        f"-> {receipt.get('file')}"
    )


def _print_notables(receipt: dict[str, Any]) -> None:
    raw_seconds = receipt.get("seconds")
    seconds: dict[str, Any] = raw_seconds if isinstance(raw_seconds, dict) else {}
    for name in GENERATORS:
        detail = receipt.get(name)
        if isinstance(detail, dict):
            exact = _mapping(detail.get("exact_counts"))
            counted = (
                f" exact={exact.get('counted', 0)}/{detail.get('kept', 0)}"
                f" tied_at_cut={detail.get('tied_at_cut', 0)}"
                if exact
                else ""
            )
            print(
                f"  {name}: existed={detail.get('existed')} kept={detail.get('kept')} "
                f"seconds={seconds.get(name)}{counted}"
            )
    print(
        f"notables: total={receipt.get('total', 0)} wall={seconds.get('total')}s "
        f"peak={receipt.get('peak_memory_mb')}MB -> {receipt.get('file')}"
    )


def _print_cards(receipt: dict[str, Any]) -> None:
    for item in receipt.get("sources_receipt", []):
        if "parts" in item:
            print(
                f"  {_label(item)} parts={item.get('parts')} "
                f"sample_unassigned={item.get('sample_unassigned')}"
            )
            continue
        reason = f" reason={item.get('reason')}" if item.get("reason") else ""
        part = item.get("part")
        label = f" [{part.get('field')}={part.get('value')}]" if isinstance(part, dict) else ""
        templates = item.get("templates")
        mined = (
            f" templates={templates.get('kept')}/{templates.get('existed')} "
            f"explained={templates.get('explained_share')}"
            if isinstance(templates, dict)
            else ""
        )
        print(
            f"  {_label(item)}{label} kind={item.get('kind')} "
            f"understood={item.get('understood')} roles={item.get('roles')} "
            f"structure={item.get('structure')} sample={item.get('sample_lines')} "
            f"coverage={item.get('parse_coverage', 0):.2f} "
            f"model={item.get('model_seconds')}s{mined}{reason}"
        )
    print(
        f"cards: sources={receipt.get('sources', 0)} cards={receipt.get('cards', 0)} "
        f"understood={receipt.get('understood', 0)} unparsed={receipt.get('unparsed', 0)} "
        f"structures={receipt.get('structures', 0)} "
        f"model_requests={receipt.get('model_requests', 0)} "
        f"answers_reused={receipt.get('answers_reused', 0)} "
        f"cache_hits={receipt.get('cache_hits', 0)} "
        f"budget={receipt.get('request_budget')} unasked={receipt.get('unasked', 0)} "
        f"throttles={_mapping(receipt.get('backpressure')).get('throttles', 0)} "
        f"retries={_mapping(receipt.get('backpressure')).get('retries', 0)} "
        f"waited={_mapping(receipt.get('backpressure')).get('wait_seconds', 0)}s "
        f"model_seconds={receipt.get('model_seconds', 0)} "
        f"wall={receipt.get('seconds')}s peak={receipt.get('peak_memory_mb')}MB -> sources.json"
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
