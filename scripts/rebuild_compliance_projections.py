#!/usr/bin/env python3
"""Rebuild the compliance projections from the canonical snapshot (P5/P6).

The canonical transactional store is the source of truth; the retrieval
(lexical/vector) and graph systems are reproducible projections. This script:

1. fingerprints the canonical store (``projections.canonical_fingerprint``);
2. rebuilds the retrieval projection over the operator corpus
   (``ingest_folder(..., rebuild=True)`` — new LanceDB generation);
3. proves post-ingestion materialization with a live search against the
   rebuilt index (lesson L07: ingestion metadata is not proof);
4. rebuilds the graph projection (the policy graph, deterministically derived
   from the register) and proves node/edge materialization;
5. records every generation in ``index_manifests`` with the canonical
   fingerprint it was built from, so ``projection_status`` can detect staleness
   (lesson L14: a projection built from an older fingerprint is STALE).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portal.modules.compliance.core import projections  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402


def _materialization_proof(kb_id: str) -> dict:
    """A real query against the rebuilt index — an empty hit is a FAILURE,
    not a pass with zero results."""
    import asyncio

    from portal.modules.compliance.tools.compliance_retrieval import search

    result = asyncio.run(search(kb_id, "security patch management 35 calendar days", top_k=5))
    hits = result.get("results", result.get("hits", []))
    return {"query": "security patch management 35 calendar days", "hits": len(hits or [])}


def _graph_proof() -> dict:
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.policy_graph import build_policy_graph

    graph = build_policy_graph(Register.load())
    return {"nodes": len(graph.nodes), "edges": len(graph.edges)}


def rebuild(corpus: Path, kb_id: str = "operator_corpus") -> dict:
    from portal.modules.compliance.core.temporal import now_iso

    repo = Repository()
    conn = repo._conn
    fingerprint = projections.canonical_fingerprint(repo)
    campaign = f"proj-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    receipt: dict = {
        "campaign": campaign,
        "materialized_at": now_iso(),
        "canonical_fingerprint": fingerprint,
        "projections": {},
    }

    # ── retrieval projection (lexical + vector over the operator corpus) ──
    import asyncio

    from portal.modules.compliance.core.ingest import ingest_folder

    ingest_result = asyncio.run(ingest_folder(str(corpus), kb_id=kb_id, rebuild=True))
    retrieval_counts = {
        "files_ingested": ingest_result.get("files_ingested", 0),
        "chunks_added": ingest_result.get("chunks_added", 0),
        "pages_added": ingest_result.get("pages_added", 0),
    }
    proof = _materialization_proof(kb_id)
    retrieval_counts["materialization_search_hits"] = proof["hits"]
    retrieval_counts["materialized"] = proof["hits"] > 0
    receipt["projections"]["retrieval"] = {
        "counts": retrieval_counts,
        "ingest_error": ingest_result.get("ingest_error"),
    }
    projections.record_index_manifest(
        repo,
        index_kind="retrieval",
        generation_id=f"{campaign}-retrieval",
        canonical_fingerprint_value=fingerprint,
        counts=retrieval_counts,
    )

    # ── graph projection ────────────────────────────────────────────────
    graph_counts = _graph_proof()
    graph_counts["materialized"] = graph_counts["nodes"] > 0 and graph_counts["edges"] > 0
    receipt["projections"]["graph"] = {"counts": graph_counts}
    projections.record_index_manifest(
        repo,
        index_kind="graph",
        generation_id=f"{campaign}-graph",
        canonical_fingerprint_value=fingerprint,
        counts=graph_counts,
    )

    # ── staleness verdicts against the same fingerprint ─────────────────
    receipt["status"] = {
        kind: projections.projection_status(repo, kind, fingerprint)
        for kind in ("retrieval", "graph")
    }
    receipt["census"] = projections.census(conn)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--kb-id", default="operator_corpus")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    receipt = rebuild(args.corpus.resolve(), kb_id=args.kb_id)
    payload = json.dumps(receipt, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    ok = all(p["counts"].get("materialized") for p in receipt["projections"].values()) and all(
        s["status"] == "FRESH" for s in receipt["status"].values()
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
