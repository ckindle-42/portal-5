#!/usr/bin/env python3
"""Rebuild the compliance projections from the canonical snapshot (P5/P6).

The canonical transactional store is the source of truth; the retrieval
(lexical/vector) and graph systems are reproducible projections. This script:

1. fingerprints the canonical store (``projections.canonical_fingerprint``);
2. optionally ACQUIRES an operator folder first (``--corpus`` — layer/tier
   derivation and queueing; see ``ingest_folder``);
3. rebuilds the retrieval projection from the canonical sections — ONE
   projection path (LOAD_AND_CONVERSE_V1 §P2): ``project_sections`` emits the
   index from ``source_sections`` per jurisdiction with ``chunk_id =
   section_id``, so every hit resolves to a canonical section. The previous
   version of this script called ``ingest_folder`` here, the path
   BILATERAL_CORPUS_V1 P4.4 marks DEPRECATED for building sha1 chunk ids that
   resolve to nothing — while GS's own remediation line pointed at
   ``scripts/project_compliance_sections.py``. Two paths, and the one named
   "rebuild" was the wrong one;
4. proves post-projection materialization with a live search against EVERY
   corpus (lesson L07: ingestion metadata is not proof);
5. rebuilds the graph projection (the policy graph, deterministically derived
   from the register) and proves node/edge materialization;
6. records the graph generation in ``index_manifests`` with the canonical
   fingerprint it was built from (lesson L14); the retrieval generation is
   recorded by the projection itself, fingerprinted against each
   jurisdiction's section population — the manifest one projection writes,
   never two.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portal.modules.compliance.core import projections  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.section_index import (  # noqa: E402
    CORPUS_FOR_JURISDICTION,
)

#: a live query a corpus that holds any compliance material at all must answer.
_PROOF_QUERY = "patch management responsibilities"


def _materialization_proof(kb_id: str) -> dict:
    """A real query against the rebuilt index — an empty hit is a FAILURE,
    not a pass with zero results."""
    from portal.modules.compliance.tools.compliance_retrieval import search

    result = asyncio.run(search(kb_id, _PROOF_QUERY, top_k=5))
    hits = result.get("results", result.get("hits", []))
    return {"query": _PROOF_QUERY, "hits": len(hits or [])}


def _acquire(corpus: Path, kb_id: str) -> dict:
    """ACQUISITION (optional, explicit): discover documents and derive layer
    and authority tier. Never the projection — the projection re-runs after
    it, and while it runs ingest_folder would refuse anyway."""
    from portal.modules.compliance.core.ingest import ingest_folder

    result = asyncio.run(ingest_folder(str(corpus), kb_id=kb_id, rebuild=True))
    return {
        "role": "acquisition",
        "files_ingested": result.get("files_ingested", 0),
        "layer_census": result.get("layer_census", {}),
        "ingest_error": result.get("ingest_error"),
    }


def _graph_proof() -> dict:
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.policy_graph import build_policy_graph

    graph = build_policy_graph(Register.load())
    return {"nodes": len(graph.nodes), "edges": len(graph.edges)}


def rebuild(corpus: Path | None, kb_id: str = "operator_corpus") -> dict:
    from portal.modules.compliance.core.temporal import now_iso

    repo = Repository()
    conn = repo._conn
    fingerprint = projections.canonical_fingerprint(repo)
    campaign = f"proj-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    repo.close()
    receipt: dict = {
        "campaign": campaign,
        "materialized_at": now_iso(),
        "canonical_fingerprint": fingerprint,
        "projections": {},
    }

    # ── acquisition (optional) — never the projection ────────────────────
    if corpus is not None:
        receipt["projections"]["acquisition"] = _acquire(corpus, kb_id)

    # ── retrieval projection — ONE path: sections in, section ids out ────
    from scripts.project_compliance_sections import project

    projection = project(list(CORPUS_FOR_JURISDICTION))
    corpora_proofs: dict[str, dict] = {}
    for corpus_record in projection["corpora"]:
        if corpus_record.get("dry_run") or not corpus_record.get("units_indexed", 0):
            continue
        proof = _materialization_proof(corpus_record["kb_id"])
        proof["materialized"] = proof["hits"] > 0
        corpora_proofs[corpus_record["kb_id"]] = proof
    receipt["projections"]["retrieval"] = {
        "basis": "section projection (project_sections, chunk_id = section_id)",
        "generation_id": projection.get("generation_id"),
        "corpora": projection["corpora"],
        "materialization_proofs": corpora_proofs,
    }

    # ── graph projection ────────────────────────────────────────────────
    graph_counts = _graph_proof()
    graph_counts["materialized"] = graph_counts["nodes"] > 0 and graph_counts["edges"] > 0
    receipt["projections"]["graph"] = {"counts": graph_counts}
    repo = Repository()
    try:
        projections.record_index_manifest(
            repo,
            index_kind="graph",
            generation_id=f"{campaign}-graph",
            canonical_fingerprint_value=fingerprint,
            counts=graph_counts,
        )
        # ── staleness verdicts against the store ────────────────────────
        receipt["status"] = {
            kind: projections.projection_status(repo, kind, fingerprint) for kind in ("graph",)
        }
        receipt["status"]["retrieval"] = projections.retrieval_projection_status(repo)
        receipt["census"] = projections.census(conn)
    finally:
        repo.close()
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="optional: ACQUIRE this operator folder first (layer/tier derivation). "
        "The index is always re-projected from the canonical sections afterwards, "
        "so acquisition can never leave sha1 chunks as the product index.",
    )
    parser.add_argument("--kb-id", default="operator_corpus")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    receipt = rebuild(args.corpus.resolve() if args.corpus else None, kb_id=args.kb_id)
    payload = json.dumps(receipt, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    retrieval = receipt["projections"]["retrieval"]
    proofs = retrieval.get("materialization_proofs", {})
    all_proofs = bool(proofs) and all(p["materialized"] for p in proofs.values())
    retrieval_fresh = receipt["status"]["retrieval"]["status"] == "FRESH"
    graph_ok = receipt["projections"]["graph"]["counts"]["materialized"]
    return 0 if (all_proofs and retrieval_fresh and graph_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
