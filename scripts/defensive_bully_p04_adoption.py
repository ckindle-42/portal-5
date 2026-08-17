#!/usr/bin/env python3
"""P0.4 -- re-run embedding arms A/B/C on the deduplicated corpus set, adopt,
freeze DISCOVERY_BASELINE_V2 (TASK_BULLY_SA5_ACQUIRE_AND_RUN_V1).

For each arm:
  1. re-seed its version-tagged projection from the DEDUPLICATED real-parent
     corpus (dedupe on canonical embed text -- the identity control then runs
     on distinct texts, removing the corpus-composition ambiguity),
  2. derive per-space thresholds from the arm's self/near/far distributions
     (P0.2) and run the SA2 discovery lane with those thresholds + identity
     classified as a diagnostic (P0.3),
  3. record the report under the arm's bakeoff directory.

Then compare discovery precision among arms that clear the one-session
throughput bar and adopt the winner (default embed URL, batch, launch.sh /
services.sh pointer).  Freeze the winner's run as DISCOVERY_BASELINE_V2.

Usage:
    uv run python scripts/defensive_bully_p04_adoption.py \\
        --corpus /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v2.json \\
        --bakeoff-root /Volumes/data01/portal5_hunt/artifacts/embedding_bakeoff \\
        --embed-cpu http://localhost:8917/v1/embeddings \\
        --embed-arm-a http://localhost:8941/v1/embeddings \\
        --embed-arm-b http://localhost:8943/v1/embeddings
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully.cousin_calibration_bench import (  # noqa: E402
    corpus_parent_reference_record,
    load_specimen_corpus,
)
from portal.modules.security.core.bully.discovery_bench import run_discovery_bench  # noqa: E402
from portal.modules.security.core.bully.embedding_spaces import (  # noqa: E402
    derive_thresholds,
    measure_distances,
)
from portal.modules.security.core.bully.organ import (  # noqa: E402
    Organ,
    _canonical_record_text,
)
from portal.modules.security.core.bully.store import Store  # noqa: E402

ARM_SPECS = {
    "arm-c": {
        "embed_url": None,  # filled from CLI
        "query_embed_url": None,
        "embedding_version": "sentence-transformers-v1",
        "batch_size": 64,
        "label": "cpu-harrier-batched",
    },
    "arm-a": {
        "embed_url": None,
        "query_embed_url": None,
        "embedding_version": "mlx-qwen3-embed-0.6b-mxfp8",
        "batch_size": 32,
        "label": "mlx-qwen3",
    },
    "arm-b": {
        "embed_url": None,
        "query_embed_url": None,
        "embedding_version": "llamacpp-embeddinggemma-300m-q8",
        # llama-server n_ubatch=512 tokens bounds the embed batch: real corpus
        # texts are ~300 tokens each, so >4 texts/batch exceeds the slot and
        # returns 500 (recorded Arm B operational limit, P0.4).
        "batch_size": 4,
        "label": "llamacpp-embeddinggemma",
    },
}


def _dedupe_parents(corpus: dict) -> list[dict]:
    """Real parents deduplicated on canonical embed text (P0.4)."""
    seen: dict[str, dict] = {}
    for specimen in corpus["specimens"]:
        if specimen["source_lane"] != "attack_data":
            continue
        record = corpus_parent_reference_record(specimen)
        text = _canonical_record_text(record)
        seen.setdefault(text, specimen)
    return [seen[text] for text in sorted(seen)]


def canonical_text_by_id(parents: list[dict]) -> dict[str, str]:
    by_id: dict[str, str] = {}
    for specimen in parents:
        record = corpus_parent_reference_record(specimen)
        by_id[str(specimen["specimen_id"])] = _canonical_record_text(record)
    return by_id


def _seed_projection(
    parents: list[dict],
    *,
    output_dir: Path,
    embed_url: str,
    query_embed_url: str | None,
    embedding_version: str,
    batch_size: int,
) -> None:
    records = [corpus_parent_reference_record(specimen) for specimen in parents]
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
            # Transient 502s from a saturated embed backend (e.g. llama-server
            # under CPU contention) must not abort the seed -- retry the batch.
            attempts = 0
            while True:
                try:
                    organ.upsert_many(records, batch_size=batch_size)
                    break
                except Exception as exc:  # noqa: BLE001 -- retry on transient transport errors
                    attempts += 1
                    if attempts >= 3:
                        raise
                    print(f"  [retry] seed batch {attempts}: {exc}", file=sys.stderr)
                    time.sleep(3)
        finally:
            organ.close()


def _measure_space(
    parents: list[dict],
    *,
    embed_url: str,
    query_embed_url: str | None,
    sample_size: int = 64,
) -> dict:
    texts = sorted({_canonical_record_text(corpus_parent_reference_record(s)) for s in parents})
    # A bounded sample is enough to characterize self/near/far geometry; the
    # full set would take minutes on the CPU path for no extra signal (P0.2).
    texts = texts[:sample_size]

    def embed_fn(batch: list[str]):
        r = httpx.post(embed_url, json={"input": batch}, timeout=600)
        r.raise_for_status()
        items = sorted(r.json()["data"], key=lambda x: x["index"])
        return [it["embedding"] for it in items]

    query_fn = (
        (lambda batch: embed_fn(batch))
        if query_embed_url is None or query_embed_url == embed_url
        else None
    )
    if query_fn is None:

        def query_fn(batch):
            r = httpx.post(query_embed_url, json={"input": batch}, timeout=600)
            r.raise_for_status()
            items = sorted(r.json()["data"], key=lambda x: x["index"])
            return [it["embedding"] for it in items]

    return measure_distances(embed_fn=embed_fn, query_embed_fn=query_fn, texts=texts)


def run_arm(
    arm: str,
    *,
    parents: list[dict],
    corpus: dict,
    output_dir: Path,
    embed_url: str,
    query_embed_url: str | None,
    embedding_version: str,
    batch_size: int,
) -> dict:
    arm_dir = output_dir / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    _seed_projection(
        parents,
        output_dir=arm_dir,
        embed_url=embed_url,
        query_embed_url=query_embed_url,
        embedding_version=embedding_version,
        batch_size=batch_size,
    )
    distributions = _measure_space(parents, embed_url=embed_url, query_embed_url=query_embed_url)
    thresholds = derive_thresholds(distributions, embedding_version=embedding_version)
    (arm_dir / "space_thresholds.json").write_text(
        json.dumps(thresholds.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with Store(arm_dir / "snapshot_state.db") as store:
        snapshot = Organ(
            store=store,
            db_path=arm_dir / "organ_snapshot",
            embed_url=embed_url,
            query_embed_url=query_embed_url,
            embedding_version=embedding_version,
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            report = run_discovery_bench(
                snapshot,
                corpus_path=corpus["_path"],
                output_dir=arm_dir / "discovery_v2",
                thresholds=thresholds.to_dict(),
                canonical_text_by_id=canonical_text_by_id(parents),
                identity_gate="diagnostic",
                knn_batch_size=max(1, batch_size),
            )
        finally:
            snapshot.close()
    return {
        "arm": arm,
        "embedding_version": embedding_version,
        "label": ARM_SPECS[arm]["label"],
        "thresholds": thresholds.to_dict(),
        "report": report.to_dict(),
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--bakeoff-root", type=Path, required=True)
    p.add_argument("--embed-cpu", required=True)
    p.add_argument("--embed-arm-a", required=True)
    p.add_argument("--embed-arm-b", required=True)
    p.add_argument("--arms", default="arm-c,arm-a,arm-b")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = load_specimen_corpus(args.corpus)
    corpus["_path"] = args.corpus
    parents = _dedupe_parents(corpus)
    print(f"deduplicated parents: {len(parents)}")

    urls = {
        "arm-c": (args.embed_cpu, None),
        "arm-a": (args.embed_arm_a, None),
        "arm-b": (args.embed_arm_b, f"{args.embed_arm_b}/query"),
    }
    results = []
    for arm in args.arms.split(","):
        arm = arm.strip()
        spec = ARM_SPECS[arm]
        embed_url, query_embed_url = urls[arm]
        print(f"\n=== {arm} ({spec['label']}) ===")
        result = run_arm(
            arm,
            parents=parents,
            corpus=corpus,
            output_dir=args.bakeoff_root,
            embed_url=embed_url,
            query_embed_url=query_embed_url,
            embedding_version=spec["embedding_version"],
            batch_size=spec["batch_size"],
        )
        print(
            f"{arm}: status={result['report']['status']} "
            f"precision={result['report']['discovery_precision']}"
        )
        results.append(result)

    (args.bakeoff_root / "p04_adoption.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print("\nwritten p04_adoption.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
