"""Compare exact-register isolated/sweep retrieval against a live corpus.

Run with the service's environment, e.g. PYTHONPATH=. .venv/bin/python
scripts/compliance_reliability_probe.py --output /private/tmp/compliance-probe.
Output contains private corpus text; keep it outside the repository. Review
proposals are captured in the trace without writing to the operator's queue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--standard", default="CIP-007-6")
    parser.add_argument("--requirement", default="R5 Part 5.4")
    parser.add_argument("--kb-id", default="operator_corpus")
    parser.add_argument("--effective-on", default="2026-09-04")
    parser.add_argument(
        "--runs",
        nargs="+",
        choices=["isolated", "sweep"],
        default=["isolated", "sweep", "isolated"],
    )
    return parser.parse_args()


def run_matrix(args, reg, target, emit):
    from portal.modules.compliance.core.coverage import coverage_matrix
    from portal.modules.compliance.core.mapping_store import MappingStore
    from portal.modules.compliance.core.propose import make_real_proposer
    from portal.modules.compliance.core.scope_derive import derive_scope

    scope, _ = derive_scope(args.kb_id)
    started = time.monotonic()
    matrix = coverage_matrix(
        reg, scope, args.effective_on, make_real_proposer(args.kb_id), MappingStore()
    )
    cells = [
        {
            **c.to_dict(),
            "policy_spans": c.policy_spans,
            "procedure_spans": c.procedure_spans,
            "evidence_spans": c.evidence_spans,
        }
        for c in matrix.cells
    ]
    emit("matrix", cells=cells, summary=matrix.summary(), elapsed=time.monotonic() - started)
    return {
        "elapsed": round(time.monotonic() - started, 2),
        "summary": matrix.summary(),
        "target": next(c for c in cells if c["requirement_id"] == target.id),
        "query_sha256": hashlib.sha256(target.verbatim_text.encode()).hexdigest(),
    }


def main():
    args = parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    from portal.modules.compliance.core import review_queue as rq
    from portal.modules.compliance.core.cip_register import Register
    from portal.platform.retrieval import embedding, pipeline

    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    reg = Register.load()
    reg = Register(nodes=[n for n in reg.nodes if n.standard == args.standard], edges=reg.edges)
    isolated = Register(nodes=[n for n in reg.nodes if args.requirement in n.id], edges=reg.edges)
    if len(isolated.nodes) != 1:
        raise ValueError(f"Expected one target, found {len(isolated.nodes)}")
    original_search, original_rerank = pipeline.search, embedding.vl_rerank
    current = {}
    trace_file = None

    def emit(stage, **data):
        trace_file.write(json.dumps({**current, "stage": stage, **data}) + "\n")
        trace_file.flush()

    async def search(comp, kb_id, query, top_k):
        current["query"] = query
        current["requirement_id"] = next((n.id for n in reg.nodes if n.verbatim_text == query), "?")
        started = time.monotonic()
        try:
            result = await original_search(comp, kb_id, query, top_k)
        except BaseException as exc:
            emit("search", error=f"{type(exc).__name__}: {exc}", elapsed=time.monotonic() - started)
            raise
        emit("search", result=result, elapsed=time.monotonic() - started)
        return result

    async def rerank(query, candidates, top_n):
        started = time.monotonic()
        stage = "visual_rerank" if any("image_path" in c for c in candidates) else "text_rerank"
        try:
            result = await original_rerank(query, candidates, top_n)
        except BaseException as exc:
            emit(
                stage,
                candidates=candidates,
                error=f"{type(exc).__name__}: {exc}",
                elapsed=time.monotonic() - started,
            )
            raise
        emit(stage, candidates=candidates, result=result, elapsed=time.monotonic() - started)
        return result

    def review(kind, subject_id, proposed_value, evidence=None, confidence=0.0):
        item = rq.ReviewItem(
            kind=kind,
            subject_id=subject_id,
            proposed_value=proposed_value,
            evidence=evidence or [],
            confidence=confidence,
        )
        item.id = hashlib.sha256(
            json.dumps([kind, subject_id, proposed_value], sort_keys=True).encode()
        ).hexdigest()[:12]
        emit("review", item=item.to_row())
        return item

    summaries = []
    with (
        patch.object(pipeline, "search", search),
        patch.object(embedding, "vl_rerank", rerank),
        patch.object(rq, "propose", review),
    ):
        for index, mode in enumerate(args.runs):
            current.clear()
            current["run"] = f"{index}-{mode}"
            with (args.output / f"{index}-{mode}.jsonl").open("w") as trace_file:
                summary = run_matrix(
                    args, isolated if mode == "isolated" else reg, isolated.nodes[0], emit
                )
                summary["run"] = current["run"]
                summaries.append(summary)
                print(
                    json.dumps(
                        {
                            "run": summary["run"],
                            "elapsed": summary["elapsed"],
                            "target_coverage": summary["target"]["coverage"],
                            "policy_candidates": len(summary["target"]["policy_spans"]),
                        }
                    ),
                    flush=True,
                )
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()
