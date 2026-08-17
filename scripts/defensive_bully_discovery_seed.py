#!/usr/bin/env python3
"""Seed a fresh version-tagged ORG projection for one embedding arm (SA3.4).

Re-embeds and re-indexes the FULL real-parent corpus (all `attack_data` lanes
of SPECIMEN_CORPUS_V2) through the given arm's embed endpoint into a separate,
version-tagged projection. Records wall-clock for the full seed -- the SA3.3 A3
session bar (full-corpus discovery must complete within one session).

Usage:
    uv run python scripts/defensive_bully_discovery_seed.py \\
        --arm arm-a \\
        --embed-url http://localhost:8941/v1/embeddings \\
        --embedding-version mlx-qwen3-embed-0.6b-mxfp8 \\
        --batch-size 32 \\
        --output-dir /Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/arm-a
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully.cousin_calibration_bench import (
    corpus_parent_reference_record,
    load_specimen_corpus,
)
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store

SEED_REPORT_SCHEMA = "EMBEDDING_BAKEOFF_SEED_V1"


def _real_parent_records(corpus: dict) -> list[dict]:
    records = []
    for specimen in corpus["specimens"]:
        if specimen["source_lane"] != "attack_data":
            continue
        records.append(corpus_parent_reference_record(specimen))
    return records


def seed_projection(
    *,
    corpus_path: Path,
    output_dir: Path,
    embed_url: str,
    query_embed_url: str | None,
    embedding_version: str,
    batch_size: int,
    embed_client: httpx.Client | None = None,
) -> dict:
    corpus = load_specimen_corpus(corpus_path)
    records = _real_parent_records(corpus)
    output_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with Store(output_dir / "snapshot_state.db") as store:
        organ = Organ(
            store=store,
            db_path=output_dir / "organ_snapshot",
            embed_url=embed_url,
            query_embed_url=query_embed_url,
            embedding_version=embedding_version,
            embed_client=embed_client or httpx.Client(timeout=600.0),
        )
        try:
            seeded = organ.upsert_many(records, batch_size=batch_size)
        finally:
            organ.close()
    wall_s = round(time.perf_counter() - t0, 3)
    report = {
        "schema": SEED_REPORT_SCHEMA,
        "embedding_version": embedding_version,
        "embed_url": embed_url,
        "query_embed_url": query_embed_url,
        "corpus_snapshot_hash": corpus["snapshot_hash"],
        "parent_count": len(records),
        "seeded_ids": len(seeded),
        "batch_size": batch_size,
        "wall_s": wall_s,
        "items_per_sec": round(len(records) / wall_s, 3) if wall_s else None,
        "started_at": datetime.now(tz=UTC).isoformat(),
    }
    (output_dir / "seed_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=("arm-a", "arm-b"))
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--embed-url", required=True)
    parser.add_argument("--query-embed-url")
    parser.add_argument("--embedding-version", required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus_path = args.corpus or Path(
        "/Volumes/data01/portal5_hunt/artifacts/specimen_corpus_v2/specimen_corpus_v2.json"
    )
    seed_projection(
        corpus_path=corpus_path,
        output_dir=args.output_dir,
        embed_url=args.embed_url,
        query_embed_url=args.query_embed_url,
        embedding_version=args.embedding_version,
        batch_size=args.batch_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
