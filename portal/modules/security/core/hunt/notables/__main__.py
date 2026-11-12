"""python -m portal.modules.security.core.hunt.notables — source cards for an unseen index."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from .pipeline import model_from_env, model_requirement
from .run import STAGES, cards_stage, default_search


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
    return parser


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
    target = model_from_env()
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
        search=default_search(),
    )
    _print_cards(receipt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
