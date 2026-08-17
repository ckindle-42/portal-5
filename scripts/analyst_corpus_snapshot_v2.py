#!/usr/bin/env python3
"""SA5.6 -- ANALYST_CORPUS_SNAPSHOT_V2 at real multi-source scale + pivot pairs
(TASK_BULLY_SA5_ACQUIRE_AND_RUN_V1).

Builds the real analyst corpus: acquired cloud/identity specimens (SA5.5) plus
the frozen endpoint attack_data parents, runs `identify_pivot_pairs` (shared
authoritative external labels -> genuine cross-class pairs), and freezes an
immutable, hash-verified ANALYST_CORPUS_SNAPSHOT_V2.

Usage:
    uv run python scripts/analyst_corpus_snapshot_v2.py \
        --cloud-corpus /Volumes/data01/portal5_hunt/artifacts/analyst_corpus_real/corpus.json \
        --endpoint-corpus /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_sa1_v1/specimen_corpus_v2.json \
        --out /Volumes/data01/portal5_hunt/artifacts/analyst_corpus_snapshot_v2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully.analyst_corpus import (  # noqa: E402
    T0_AUTHORITATIVE,
    identify_pivot_pairs,
    save_snapshot,
    stamp_specimen,
    take_snapshot,
    verify_snapshot,
)

SNAPSHOT_V2_NAME = "ANALYST_CORPUS_SNAPSHOT_V2"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    specimens = payload.get("specimens")
    if not isinstance(specimens, list):
        raise ValueError(f"{path}: no 'specimens' list")
    return payload


def _stamp_endpoint_parents(specimens: list[dict]) -> list[dict]:
    """Stamp the frozen attack_data parents with the analyst-corpus tier +
    provenance so pivot identification can use their authoritative data.yml
    technique labels (shared external labels across classes, A6). The frozen
    corpus artifact itself is never mutated -- these are working copies."""
    stamped: list[dict] = []
    for specimen in specimens:
        if specimen.get("label_tier") is not None:
            stamped.append(specimen)
            continue
        stamped.append(
            stamp_specimen(
                dict(specimen),
                label_tier=T0_AUTHORITATIVE,
                provenance={
                    "labeling": "authoritative",
                    "source": "attack_data",
                    "origin": "attack_data_data_yml",
                },
                trust_tier="imported_observed",
                source_lane=str(specimen.get("source_lane") or "external_corpus"),
            )
        )
    return stamped


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cloud-corpus", type=Path, required=True)
    ap.add_argument("--endpoint-corpus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    cloud = _load(args.cloud_corpus)
    endpoint = _load(args.endpoint_corpus)
    endpoint_parents = [s for s in endpoint["specimens"] if s.get("source_lane") == "attack_data"]

    all_specimens = cloud["specimens"] + _stamp_endpoint_parents(endpoint_parents)
    print(
        f"combined specimens: {len(all_specimens)} "
        f"(cloud={len(cloud['specimens'])}, endpoint={len(endpoint_parents)})"
    )

    pairs = identify_pivot_pairs(all_specimens)
    cross = [p for p in pairs if p.cross_class]
    print(f"pivot pairs: {len(pairs)} total, {len(cross)} cross-class")
    for pair in cross[:12]:
        print(
            f"  {pair.pair_id[:12]} {pair.left_source_class or '?'} <-> "
            f"{pair.right_source_class or '?'} basis={pair.basis}"
        )

    snapshot = take_snapshot(all_specimens, pairs=pairs, name=SNAPSHOT_V2_NAME)
    verdict = verify_snapshot(snapshot)
    if not verdict["valid"]:
        print(f"[FAIL] snapshot verification: {verdict['errors']}", file=sys.stderr)
        return 1
    path = save_snapshot(snapshot, args.out)
    print(f"snapshot hash: {snapshot['snapshot_hash']}")
    print(f"composition: {json.dumps(snapshot['composition'], indent=2, sort_keys=True)}")
    print(f"written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
