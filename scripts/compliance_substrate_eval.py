#!/usr/bin/env python3
"""Compliance retrieval substrate eval (TASK_COMPLIANCE_REASONING_V6 P1 / Y25).

Ingests the NERC CIP standard PDFs into a scratch *compliance* KB (the
compliance composition — docling chunks + BM25, not rag_multimodal) and reports
where each prose query's target file ranks. The acceptance bar: `prose-cip-07`
("How does NERC CIP-002 categorize BES Cyber Systems…", answered by CIP-002
Attachment 1, a table) must reach **rank 1**.

    uv run python scripts/compliance_substrate_eval.py \
        [--corpus portal/modules/compliance/data/cip_pdfs] \
        [--kb-id substrate_eval] [--reuse] [--out results.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
_QUERIES = REPO / "tests" / "fixtures" / "rag_eval_corpus" / "queries.yaml"


async def _run(corpus: Path, kb_id: str, reuse: bool, lance_dir: str) -> dict:
    os.environ.setdefault("LANCE_DIR", lance_dir)
    from portal.modules.compliance.tools import compliance_retrieval as cr
    from portal.platform.retrieval import store as _store

    _store.LANCE_DIR = lance_dir  # noqa: SLF001 - test isolation
    comp = cr._composition()

    if not reuse:
        from portal.modules.compliance.core.ingest import ingest_folder

        t = time.monotonic()
        ing = await ingest_folder(str(corpus), kb_id, rebuild=True)
        print(
            f"ingest: {ing.get('files_ingested')} files, {ing.get('chunks_added')} chunks "
            f"in {time.monotonic() - t:.0f}s  (error: {ing.get('ingest_error')})"
        )

    queries = yaml.safe_load(_QUERIES.read_text())
    queries = queries if isinstance(queries, list) else queries.get("queries", [])
    prose = [q for q in queries if q.get("category", "").startswith("prose")]

    rows = []
    for q in prose:
        res = await cr.search(kb_id, q["query"], top_k=10)
        hits = res.get("results", res.get("hits", []))
        target = q["target_file"].lower()
        rank = next(
            (i + 1 for i, h in enumerate(hits) if target in json.dumps(h).lower()),
            None,
        )
        rows.append(
            {
                "id": q["id"],
                "target": q["target_file"],
                "rank": rank,
                "top": [Path(str(h.get("source", h.get("path", "")))).name for h in hits[:3]],
            }
        )
        print(f"  {q['id']:16} target {q['target_file']:20} rank {rank}")

    cip07 = next((r for r in rows if r["id"] == "prose-cip-07"), None)
    verdict = "PASS" if cip07 and cip07["rank"] == 1 else "FAIL"
    ranked = [r for r in rows if r["rank"]]
    # The CIP subset only — the NIST slice is a different corpus and is not part
    # of Y25's "other 13 prose queries" guard.
    cip = [r for r in rows if r["id"].startswith("prose-cip-")]
    return {
        "kb_id": kb_id,
        # Flat fields the Y25 check in verify_compliance_v6_closeout.py reads.
        "prose_cip_07_rank": (cip07 or {}).get("rank"),
        "cip_prose_summary": {
            "n": len(cip),
            "rank1": sum(1 for r in cip if r["rank"] == 1),
            "in_top10": sum(1 for r in cip if r["rank"]),
            "prose_cip_07": (cip07 or {}).get("rank"),
            "mean_rank": round(
                sum(r["rank"] for r in cip if r["rank"]) / max(1, sum(1 for r in cip if r["rank"])),
                3,
            ),
        },
        "composition": "compliance_retrieval (docling chunks + BM25 + contextualize)",
        "stage_set": comp.stage_set,
        "fts": comp.fts,
        "prose_queries": len(prose),
        "target_in_top10": len(ranked),
        "mean_rank_when_found": round(sum(r["rank"] for r in ranked) / len(ranked), 2)
        if ranked
        else None,
        "prose_cip_07": cip07,
        "verdict_y25": verdict,
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=REPO / "portal/modules/compliance/data/cip_pdfs")
    ap.add_argument("--kb-id", default="substrate_eval")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--lance-dir", default="/tmp/portal5_compliance_substrate_lance")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    r = asyncio.run(_run(a.corpus, a.kb_id, a.reuse, a.lance_dir))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(r, indent=2, default=str))
    print(f"\nprose-cip-07 rank: {(r['prose_cip_07'] or {}).get('rank')}   Y25: {r['verdict_y25']}")
    print(f"prose targets in top-10: {r['target_in_top10']}/{r['prose_queries']}")


if __name__ == "__main__":
    main()
