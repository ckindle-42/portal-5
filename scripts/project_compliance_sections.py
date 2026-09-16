#!/usr/bin/env python3
"""Project the canonical section store into the retrieval index (BILATERAL_CORPUS_V1 P4).

One identity space: the index is emitted FROM ``source_sections``, at section
granularity, with ``chunk_id = section_id``. Both jurisdictions project —
internal into ``operator_corpus``, regulatory into ``nerc_corpus`` — both under
the ``compliance_`` table prefix so ``search_all`` spans them.

Each run records an ``index_manifests`` generation fingerprinted against the
**section population** (not just the canonical truth tables), so FRESH / STALE /
ABSENT means something checkable: a re-capture that moves a section boundary
marks the index stale.

Each run also writes the boundary receipt the projection is entitled to make:
eligible sections, examined sections, document revision hashes, and every
section it could not project with the reason it could not.

    uv run python scripts/project_compliance_sections.py
    uv run python scripts/project_compliance_sections.py --jurisdiction US
    uv run python scripts/project_compliance_sections.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import projections, section_index  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

RECEIPT_ROOT = REPO_ROOT / "coding_task" / "v9_compliance" / "private" / "projections"


def _project_one(repo: Repository, jurisdiction: str, *, dry_run: bool) -> dict[str, Any]:
    from portal.modules.compliance.tools.compliance_retrieval import project_sections

    started = time.time()
    plan = section_index.build_plan(repo, jurisdiction=jurisdiction)
    record: dict[str, Any] = {
        "jurisdiction": jurisdiction,
        "kb_id": plan.kb_id,
        "eligible_sections": len(plan.eligible_sections),
        "projected_sections": len(plan.examined_sections),
        "indexable_units": len(plan.units),
        "split_sections": sum(1 for u in plan.units if "#" in u.chunk_id),
        "unprojectable": len(plan.unprojectable),
        "unprojectable_reasons": _reason_census(plan.unprojectable),
    }
    if dry_run:
        record["dry_run"] = True
        record["elapsed_s"] = round(time.time() - started, 2)
        return record

    result = asyncio.run(project_sections(plan.kb_id, plan.units, rebuild=True))
    record.update(result)
    record["elapsed_s"] = round(time.time() - started, 2)
    record["boundary_receipt"] = section_index.boundary_receipt(
        repo,
        plan,
        index_generation=f"{result['table']}@{result['table_version']}:{result['embed_model']}",
    )
    # the receipt is large; the run record keeps its shape and its verdict
    receipt = record["boundary_receipt"]
    record["boundary"] = {
        "complete": receipt["complete"],
        "eligible": len(receipt["eligible_sections"]),
        "examined": len(receipt["examined_sections"]),
        "omissions": len(receipt["omissions"]),
        "revisions": len(receipt["document_revision_hashes"]),
    }
    return record


def _reason_census(entries: list[dict[str, str]]) -> dict[str, int]:
    census: dict[str, int] = {}
    for entry in entries:
        reason = entry["reason"].split(" (")[0]
        census[reason] = census.get(reason, 0) + 1
    return census


def verify_corpus(repo: Repository, jurisdiction: str) -> dict[str, Any]:
    """Does the LIVE index table hold exactly this jurisdiction's current units?

    Not a fingerprint comparison — a row comparison. Used to re-stamp a
    manifest without re-embedding, which is only honest when the index provably
    already matches the store.
    """
    from portal.platform.retrieval import store as _store

    plan = section_index.build_plan(repo, jurisdiction=jurisdiction)
    expected = {u.chunk_id for u in plan.units}
    table = _store.text_table(plan.kb_id, create=False, prefix="compliance_")
    if table is None:
        return {"kb_id": plan.kb_id, "matches": not expected, "detail": "no index table"}
    live = {str(r.get("chunk_id")) for r in table.search().limit(1_000_000).to_list()}
    return {
        "kb_id": plan.kb_id,
        "jurisdiction": jurisdiction,
        "expected_units": len(expected),
        "live_units": len(live),
        "missing_from_index": len(expected - live),
        "stale_in_index": len(live - expected),
        "matches": expected == live,
    }


def restamp(jurisdictions: list[str]) -> dict[str, Any]:
    """Record the manifest for corpora whose index PROVABLY already matches the
    store. A corpus that does not match is reported and left unstamped."""
    from portal.modules.compliance.core.temporal import now_iso

    repo = Repository()
    try:
        checks = [verify_corpus(repo, j) for j in jurisdictions]
        corpora = _active_corpora(repo)
        for check, jurisdiction in zip(checks, jurisdictions, strict=True):
            if not check["matches"]:
                continue
            entry = dict(corpora.get(check["kb_id"], {}))
            entry.update(
                {
                    "units": check["live_units"],
                    "sections": check["live_units"],
                    "fingerprint": section_index.section_population_fingerprint(repo, jurisdiction),
                    "restamped_at": now_iso(),
                }
            )
            corpora[check["kb_id"]] = entry
        generation = "proj-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-restamp"
        projections.record_index_manifest(
            repo,
            index_kind="retrieval",
            generation_id=generation,
            canonical_fingerprint_value=section_index.section_population_fingerprint(repo),
            counts={"basis": "row-verified re-stamp", "corpora": corpora},
        )
        return {
            "generation_id": generation,
            "checks": checks,
            "projection_status": projections.retrieval_projection_status(repo),
        }
    finally:
        repo.close()


def _active_corpora(repo: Repository) -> dict[str, Any]:
    """The per-corpus counts the active retrieval manifest already records."""
    row = repo._conn.execute(
        """SELECT counts_json FROM index_manifests
           WHERE index_kind = 'retrieval' AND active = 1
           ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()
    if row is None:
        return {}
    return dict(json.loads(row[0] or "{}").get("corpora", {}) or {})


def project(jurisdictions: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    from portal.modules.compliance.core.temporal import now_iso

    repo = Repository()
    try:
        report: dict[str, Any] = {
            "projected_at": now_iso(),
            "section_population_fingerprint": section_index.section_population_fingerprint(repo),
            "canonical_fingerprint": projections.canonical_fingerprint(repo),
            "corpora": [_project_one(repo, j, dry_run=dry_run) for j in jurisdictions],
        }
        if not dry_run:
            generation = "proj-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-sections"
            # carry forward every corpus this run did not touch: a partial run
            # must not erase another corpus's recorded generation, and must not
            # claim to have rebuilt it either.
            previous = _active_corpora(repo)
            previous.update(
                {
                    c["kb_id"]: {
                        "units": c.get("units_indexed", 0),
                        "sections": c["projected_sections"],
                        "boundary_complete": c.get("boundary", {}).get("complete"),
                        "fingerprint": section_index.section_population_fingerprint(
                            repo, c["jurisdiction"]
                        ),
                        "projected_at": report["projected_at"],
                    }
                    for c in report["corpora"]
                }
            )
            projections.record_index_manifest(
                repo,
                index_kind="retrieval",
                generation_id=generation,
                canonical_fingerprint_value=report["section_population_fingerprint"],
                counts={
                    "basis": "section projection",
                    "canonical_fingerprint_tables": report["canonical_fingerprint"],
                    "corpora": previous,
                },
            )
            report["generation_id"] = generation
            report["projection_status"] = projections.retrieval_projection_status(repo)
        return report
    finally:
        repo.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jurisdiction",
        action="append",
        default=None,
        help="repeatable; default projects every jurisdiction with a corpus",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--restamp",
        action="store_true",
        help="re-record the manifest for corpora whose index already matches the store, "
        "row for row — never a claim of freshness without that check",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    jurisdictions = args.jurisdiction or list(section_index.CORPUS_FOR_JURISDICTION)
    if args.restamp:
        out = restamp(jurisdictions)
        for check in out["checks"]:
            print(
                f"  {check['kb_id']:18s} expected {check.get('expected_units', 0):5d}  "
                f"live {check.get('live_units', 0):5d}  matches {check['matches']}"
            )
        print(f"\nprojection status: {out['projection_status']['status']}")
        for kb_id, entry in out["projection_status"]["corpora"].items():
            print(f"  {kb_id:18s} {entry['status']}")
        return 0
    report = project(jurisdictions, dry_run=args.dry_run)
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt = args.output or (RECEIPT_ROOT / stamp / "section_projection.json")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(payload + "\n", encoding="utf-8")

    if args.as_json:
        print(payload)
    else:
        for corpus in report["corpora"]:
            print(
                f"  {corpus['kb_id']:18s} eligible {corpus['eligible_sections']:5d}  "
                f"projected {corpus['projected_sections']:5d}  "
                f"units {corpus.get('units_indexed', corpus['indexable_units']):5d}  "
                f"split {corpus['split_sections']:3d}  "
                f"unprojectable {corpus['unprojectable']:4d}  "
                f"boundary {corpus.get('boundary', {}).get('complete')}  "
                f"{corpus['elapsed_s']:6.1f}s"
            )
            for reason, count in corpus["unprojectable_reasons"].items():
                print(f"      {count:5d}  {reason}")
        print(f"\nsection population fingerprint: {report['section_population_fingerprint'][:16]}…")
        if not args.dry_run:
            print(f"projection status: {report['projection_status']['status']}")
        print(f"receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
