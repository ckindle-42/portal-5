#!/usr/bin/env python3
"""SA5.7 -- discovery re-run on the multi-class analyst corpus; freezes
DISCOVERY_BASELINE_V3 (TASK_BULLY_SA5_ACQUIRE_AND_RUN_V1).

Runs the discovery lane on ANALYST_CORPUS_SNAPSHOT_V2 (the real multi-class
snapshot: cloud/identity + endpoint) with the adopted embedding backend and
per-space thresholds. All controls run (identity classified diagnostic,
retrieval health, near/far, degenerate rate, shuffled-label); same-class vs
cross-class and T0-only vs full-haystack cohorts are reported so the noise
effect is visible. Frozen as DISCOVERY_BASELINE_V3 when controls pass.

Usage:
    uv run python scripts/defensive_bully_discovery_v3.py \\
        --snapshot /Volumes/data01/portal5_hunt/artifacts/analyst_corpus_snapshot_v2/ANALYST_CORPUS_SNAPSHOT_V2.json \\
        --embed-url http://localhost:8941/v1/embeddings \\
        --embedding-version mlx-qwen3-embed-0.6b-mxfp8 \\
        --projection /Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff/arm-a \\
        --out /Volumes/data01/portal5_hunt/artifacts/calibration/DISCOVERY_BASELINE_V3
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

from portal.modules.security.core.bully.cousin_calibration_bench import (  # noqa: E402
    corpus_parent_reference_record,
)
from portal.modules.security.core.bully.discovery_bench import (  # noqa: E402
    DISCOVERY_BASELINE_V1,
    analyst_probe_specimens,
    analyst_snapshot_specimens,
    run_discovery_bench,
)
from portal.modules.security.core.bully.organ import (  # noqa: E402
    Organ,
    _canonical_record_text,
)
from portal.modules.security.core.bully.store import Store  # noqa: E402

BASELINE_V3 = "DISCOVERY_BASELINE_V3"


def _snapshot_corpus(snapshot_path: Path) -> dict:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    specimens = analyst_snapshot_specimens(payload)
    return {
        "schema": DISCOVERY_BASELINE_V1,
        "snapshot_hash": payload.get("snapshot_hash", ""),
        "specimens": specimens,
    }


def _seed_projection(
    specimens: list[dict],
    *,
    output_dir: Path,
    embed_url: str,
    query_embed_url: str | None,
    embedding_version: str,
    batch_size: int,
) -> None:
    records = [corpus_parent_reference_record(specimen) for specimen in specimens]
    with Store(output_dir / "snapshot_state.db") as store:
        organ = Organ(
            store=store,
            db_path=output_dir / "organ_snapshot",
            embed_url=embed_url,
            query_embed_url=query_embed_url,
            embedding_version=embedding_version,
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            organ.upsert_many(records, batch_size=batch_size)
        finally:
            organ.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--embed-url", required=True)
    ap.add_argument("--query-embed-url")
    ap.add_argument("--embedding-version", required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args(argv)

    corpus = _snapshot_corpus(args.snapshot)
    probes = analyst_probe_specimens(corpus)
    print(f"analyst probes: {len(probes)}")

    records = [corpus_parent_reference_record(s) for s in corpus["specimens"]]
    canonical_by_id = {
        str(s["specimen_id"]): _canonical_record_text(corpus_parent_reference_record(s))
        for s in corpus["specimens"]
    }

    args.projection.mkdir(parents=True, exist_ok=True)
    _seed_projection(
        corpus["specimens"],
        output_dir=args.projection,
        embed_url=args.embed_url,
        query_embed_url=args.query_embed_url,
        embedding_version=args.embedding_version,
        batch_size=args.batch_size,
    )

    with Store(args.projection / "snapshot_state.db") as store:
        snapshot = Organ(
            store=store,
            db_path=args.projection / "organ_snapshot",
            embed_url=args.embed_url,
            query_embed_url=args.query_embed_url,
            embedding_version=args.embedding_version,
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            report = run_discovery_bench(
                snapshot,
                corpus=corpus,
                output_dir=args.out,
                thresholds=None,  # adopted backend defaults to its frozen scale
                canonical_text_by_id=canonical_by_id,
                probe_selector=analyst_probe_specimens,
                identity_gate="diagnostic",
                knn_batch_size=args.batch_size,
            )
        finally:
            snapshot.close()

    # DISCOVERY_BASELINE_V3 = the frozen reference; write the V3-stamped copy.
    artifact = args.out / "discovery_baseline_v3.json"
    payload = report.to_dict()
    payload["schema"] = BASELINE_V3
    payload["baseline_supersedes"] = DISCOVERY_BASELINE_V1
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"status: {report.status} precision: {report.discovery_precision}")
    print(f"written: {artifact}")
    return 0 if report.status == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
