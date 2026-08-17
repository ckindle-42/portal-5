#!/usr/bin/env python3
"""Run the SA3.5 embedding bake-off: the SA2 real-vs-real discovery lane per
embedding arm on its version-tagged full-corpus projection.

Same frozen corpus, same scorer, same controls (identity, retrieval-health,
near/far, shuffled-label) -- the only variable is the embedding backend.
A control failure marks that arm INVALID (disqualified, not compared).

Usage:
    uv run python scripts/defensive_bully_discovery_bakeoff.py \\
        --arm arm-a \\
        --embed-url http://localhost:8941/v1/embeddings \\
        --query-embed-url http://localhost:8941/v1/embeddings \\
        --corpus /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_v2/specimen_corpus_v2.json \\
        --projection /Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/arm-a \\
        --output-dir /Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/arm-a/discovery
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully.discovery_bench import run_discovery_bench  # noqa: E402
from portal.modules.security.core.bully.organ import Organ  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=("arm-a", "arm-b"))
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--embed-url", required=True)
    parser.add_argument("--query-embed-url")
    parser.add_argument("--embedding-version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    query_embed_url = args.query_embed_url or args.embed_url
    with Store(args.projection / "snapshot_state.db") as store:
        snapshot = Organ(
            store=store,
            db_path=args.projection / "organ_snapshot",
            embed_url=args.embed_url,
            query_embed_url=query_embed_url,
            embedding_version=args.embedding_version,
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            report = run_discovery_bench(
                snapshot,
                corpus_path=args.corpus,
                output_dir=args.output_dir,
            )
        finally:
            snapshot.close()
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str))
    return 0 if report.status == "VALID" and bool(report.controls.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
