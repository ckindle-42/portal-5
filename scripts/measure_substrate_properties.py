#!/usr/bin/env python3
"""Measure what the substrate properties changed (SUBSTRATE_PROPERTIES_V1 P6.2).

Run against the LIVE store and index. Records, as numbers rather than
arguments:

* the superseded-competition measurement — for a sample of requirement
  queries, how many of the PRE-pushdown top-15 were superseded revisions, and
  how many queries had their governing section outside the pre-filter top-k
  entirely (the size of the defect §P3 removed);
* recall at top_k in {5, 10, 15} with and without pushdown, against the §P5
  mapping ground truth (which sets the search default) and, when the mapping
  store is empty, against the hand-labelled probe discriminator from
  ``reports/compliance/READING_SEAT_RESEARCH_V1.md`` §2.1 — labelled
  ``hand-judged, provisional``;
* scorer validation against the four hand-judged seat-probe transcripts;
* the count of untiered documents §P4.1 surfaced.

    uv run python scripts/measure_substrate_properties.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import evaluation, section_index, tiers  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.tools.compliance_mcp import _search_predicate  # noqa: E402
from portal.platform.retrieval import store as _store  # noqa: E402

PROBE_SECTIONS = {
    # READING_SEAT_RESEARCH_V1 §2.1, hand-judged: the three sections that decide Q2
    "standard_row": "csection-7700dd5499cead0994ec",
    "procedure_3_3": "isection-21a30e0d44708f5dfdce",
    "operator_note": "csection-440a5cdf9a6b65292ef3",
}
PROBE_QUERY = (
    "Our own procedure evaluates security patches every thirty calendar days, not "
    "thirty-five. Are we stricter than we need to be, and does that matter?"
)
TOPKS = (5, 10, 15)


def _rows(kb_id: str) -> dict[str, dict]:
    table = _store.text_table(kb_id, create=False, prefix="compliance_")
    if table is None:
        return {}
    return {r["chunk_id"]: r for r in table.search().limit(1_000_000).to_list()}


def _unfiltered_and_filtered(kb_ids: list[str], query: str, k: int) -> tuple[list[dict], list[dict]]:
    """The pre-P3 shape (no predicate) and the post-P3 shape (default
    predicate) of the same query, per corpus, merged and ranked."""
    from portal.modules.compliance.tools import compliance_retrieval as cr

    where = _search_predicate(standard="", layer="", valid_at="", known_at="")

    async def both():
        plain, pushed = [], []
        for kb_id in kb_ids:
            try:
                plain.append(await cr.search(kb_id, query, k))
            except Exception:  # noqa: BLE001 — an absent corpus is not a finding
                pass
            try:
                pushed.append(await cr.search(kb_id, query, k, where=where))
            except Exception:  # noqa: BLE001
                pass
        return plain, pushed

    def merge(bodies):
        hits = []
        for body in bodies:
            hits.extend(body.get("results", []))
        hits.sort(key=lambda r: -float(r.get("fused_score", 0) or 0))
        return hits

    plain, pushed = asyncio.run(both())
    return merge(plain), merge(pushed)


def superseded_competition(kb_ids: list[str], queries: list[str], rows: dict[str, dict]) -> dict:
    per_query = []
    for query in queries:
        unfiltered, _ = _unfiltered_and_filtered(kb_ids, query, 15)
        top15 = unfiltered[:15]
        superseded_in_top15 = sum(
            1 for h in top15 if rows.get(str(h.get("chunk_id")), {}).get("is_superseded") == 1
        )
        # the governing target: a governing row whose text the query quotes
        needle = " ".join(query.split())[:60].lower()
        target = next(
            (
                cid
                for cid, r in rows.items()
                if r.get("is_superseded") == 0 and needle in " ".join(str(r.get("text", "")).split()).lower()
            ),
            None,
        )
        governing_ids = {section_index.parent_section_id(cid) for cid in rows if rows[cid].get("is_superseded") == 0}
        top15_sections = {section_index.parent_section_id(str(h.get("chunk_id"))) for h in top15}
        governing_outside = (
            target is not None
            and section_index.parent_section_id(target) not in top15_sections
        )
        per_query.append(
            {
                "query": query[:60],
                "superseded_in_top15": superseded_in_top15,
                "target_located": target is not None,
                "governing_outside_prefilter_top15": governing_outside,
            }
        )
    located = [q for q in per_query if q["target_located"]]
    return {
        "n_queries": len(queries),
        "superseded_rows_in_prefilter_top15": sum(q["superseded_in_top15"] for q in per_query),
        "queries_with_superseded_in_top15": sum(1 for q in per_query if q["superseded_in_top15"]),
        "queries_with_target_located": len(located),
        "queries_with_governing_outside_prefilter_top15": sum(
            1 for q in located if q["governing_outside_prefilter_top15"]
        ),
        "per_query": per_query,
    }


def recall_at_k(kb_ids: list[str], rows: dict[str, dict], truth: dict) -> dict:
    """Recall of the expected sections at k, with and without pushdown."""
    out = {"source": truth["source"], "expected": truth["expected"], "table": []}
    if not truth["expected"]:
        out["table"] = []
        out["note"] = "no expected sections — recall unmeasurable"
        return out
    for k in TOPKS:
        unfiltered, pushed = _unfiltered_and_filtered(kb_ids, truth["query"], k)
        row = {"k": k}
        for name, hits in (("without_pushdown", unfiltered), ("with_pushdown", pushed)):
            sections = {
                section_index.parent_section_id(str(h.get("chunk_id")))
                for h in hits[:k]
            }
            found = [s for s in truth["expected"] if s in sections]
            row[name] = round(len(found) / len(truth["expected"]), 3)
            row[f"{name}_superseded_in_topk"] = sum(
                1
                for h in hits[:k]
                if rows.get(str(h.get("chunk_id")), {}).get("is_superseded") == 1
            )
        out["table"].append(row)
    return out


def scorer_validation() -> dict:
    """score_reading over the four hand-judged seat-probe transcripts."""
    probe_dir = REPO_ROOT / "reports" / "compliance" / "seat_probe"
    repo = Repository()
    try:
        examples = evaluation.labelled_examples(repo)
    finally:
        repo.close()
    n_answers = n_scored = n_blocked = 0
    blocked_reasons: list[str] = []
    for path in sorted(probe_dir.glob("*-seats.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for seat in data.get("seats", []):
            for answer in seat.get("answers", []):
                n_answers += 1
                score = evaluation.score_reading(answer, examples)
                if score["verdict"] == "scored":
                    n_scored += 1
                else:
                    n_blocked += 1
                    if score["reason"] not in blocked_reasons:
                        blocked_reasons.append(score["reason"])
    return {
        "n_transcripts": len(list(probe_dir.glob("*-seats.json"))),
        "n_hand_judged_answers": n_answers,
        "n_scored": n_scored,
        "n_blocked": n_blocked,
        "blocked_reason": blocked_reasons[0] if blocked_reasons else "",
        "note": (
            "the hand judgment scored reading quality; the scorer scores citation "
            "recall against settled mappings — with none approved, every answer is "
            "honest-BLOCKED, which confirms the §0 finding rather than disagreeing "
            "with the hand judgment"
        ),
    }


def untiered_documents(repo: Repository) -> dict:
    untiered: list[dict[str, str]] = []
    for row in repo._conn.execute(
        """SELECT d.logical_id, d.source_kind, d.jurisdiction
           FROM source_documents d"""
    ).fetchall():
        logical_id, source_kind, jurisdiction = str(row[0]), str(row[1]), str(row[2])
        if tiers.recorded_tier(logical_id, source_kind) == "":
            untiered.append(
                {"logical_id": logical_id, "source_kind": source_kind, "jurisdiction": jurisdiction}
            )
    by_kind: dict[str, int] = {}
    for entry in untiered:
        by_kind[entry["source_kind"]] = by_kind.get(entry["source_kind"], 0) + 1
    return {
        "n_documents": len(untiered),
        "by_source_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
        "untiered": untiered,
    }


def main() -> int:
    started = time.time()
    repo = Repository()
    try:
        kb_ids = list(dict.fromkeys(section_index.CORPUS_FOR_JURISDICTION.values()))
        kb_ids = [k for k in kb_ids if k in ("operator_corpus", "nerc_corpus", "operator_notes")]
        rows: dict[str, dict] = {}
        for kb_id in kb_ids:
            rows.update(_rows(kb_id))

        queries = [
            PROBE_QUERY,
            "At least once every 35 calendar days, evaluate security patches for "
            "applicability that have been released since the last evaluation",
            "evaluate security patches every 30 days",
            "patch evaluation sources SME review",
            "CIP-007-6 R2 Part 2.2 measures",
            "ESP review cadence 15 calendar months",
        ]
        examples = evaluation.labelled_examples(repo)
        settled_total = sorted({s for e in examples for s in e["settled_sections"]})
        measurements: dict = {
            "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "index_rows": len(rows),
            "mapping_ground_truth": {
                "n_labelled_requirements": len(examples),
                "n_settled_sections": len(settled_total),
                "n_rejected_sections": sum(len(e["rejected_sections"]) for e in examples),
                "status": "NO SETTLED ROWS — the declared evaluation set has zero approved "
                "mappings; only a rejected one"
                if not settled_total
                else "POPULATED",
            },
            "superseded_competition": superseded_competition(kb_ids, queries, rows),
            "untiered_documents": untiered_documents(repo),
            "scorer_validation": scorer_validation(),
        }
        # recall: the §P5 ground truth when populated, else the hand-judged
        # probe discriminator, labelled provisional
        if settled_total:
            truth = {
                "source": "mapping_store",
                "query": PROBE_QUERY,
                "expected": settled_total,
            }
        else:
            truth = {
                "source": "hand-judged, provisional (READING_SEAT_RESEARCH_V1 §2.1)",
                "query": PROBE_QUERY,
                "expected": sorted(PROBE_SECTIONS.values()),
            }
        measurements["recall_at_k"] = recall_at_k(kb_ids, rows, truth)
        measurements["elapsed_s"] = round(time.time() - started, 1)
        out = REPO_ROOT / "reports" / "compliance" / "SUBSTRATE_PROPERTIES_V1_measurements.json"
        out.write_text(json.dumps(measurements, indent=1) + "\n")
        print(f"measurements: {out}")
        print(json.dumps({k: v for k, v in measurements.items() if k not in ("superseded_competition", "untiered_documents", "recall_at_k")}, indent=1)[:800])
        print("\nsuperseded in pre-filter top-15:",
              measurements["superseded_competition"]["superseded_rows_in_prefilter_top15"],
              "queries with governing outside top-15:",
              measurements["superseded_competition"]["queries_with_governing_outside_prefilter_top15"])
        print("\nrecall@k:")
        for row in measurements["recall_at_k"]["table"]:
            print(" ", row)
        print("\nuntiered documents:", measurements["untiered_documents"]["n_documents"])
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
