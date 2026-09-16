#!/usr/bin/env python3
"""Anchor the Register's requirements into the captured corpus (ONE_REGULATORY_EXTRACTION_V1 P3).

Runs :mod:`portal.modules.compliance.core.requirement_anchor` over every
standard that has both Register nodes and a capture, and persists the result
through ``Repository.record_anchors``: the hits into ``requirement_sections``,
every miss into ``requirement_anchor_misses``.

The report is per standard and **per relation**, because the relations are not
equally costly to lose. An unanchored ``governing`` requirement is one the
reading path cannot retrieve at all; an unanchored ``measure`` is a smaller
loss. One blended rate over both would hide the difference, which is the whole
reason the census is shaped this way.

Nothing here is fuzzy and nothing is rounded away. A requirement whose text does
not occur in the captured revision is named, with its reason, and stays named.

    uv run python scripts/anchor_requirements.py --all --report
    uv run python scripts/anchor_requirements.py --standard CIP-007-6 --report
    uv run python scripts/anchor_requirements.py --all --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.requirement_anchor import (  # noqa: E402
    RELATIONS,
    anchor_report,
    anchor_revision,
)

REPORT_PATH = REPO_ROOT / "reports" / "compliance" / "requirement_anchor_rates.json"


def _revision_for(repo: Repository, standard: str, sha256_prefix: str) -> str:
    """The revision whose bytes are the Register's bytes.

    ``revision_id`` is the content hash, so the recorded sha256 prefix names the
    revision exactly. Matching on ``logical_id`` alone would pick up the
    implementation plan or the technical rationale filed under the same standard
    and anchor the requirement text into the wrong document.
    """
    row = repo._conn.execute(
        """SELECT revision_id FROM document_revisions
           WHERE logical_id = ? AND revision_id LIKE ? || '%'""",
        (f"NERC/{standard}", sha256_prefix),
    ).fetchone()
    return str(row[0]) if row else ""


def anchor_standard(
    repo: Repository, register: Register, standard: str, *, dry_run: bool
) -> dict[str, Any]:
    nodes = [n for n in register.nodes if n.standard == standard]
    record: dict[str, Any] = {"standard": standard, "nodes": len(nodes)}
    pdf = next((n.source_pdf for n in nodes if n.source_pdf), "")
    sha256_prefix = register.source_pdfs.get(pdf, "")
    if not sha256_prefix:
        record.update(status="NO_SOURCE_PDF", detail=f"the Register records no sha for {pdf!r}")
        return record
    revision_id = _revision_for(repo, standard, sha256_prefix)
    if not revision_id:
        record.update(status="NO_REVISION", detail=f"no revision for NERC/{standard}")
        return record
    if not (repo.get_document_text(revision_id) or ""):
        record.update(
            status="NOT_CAPTURED",
            revision_id=revision_id,
            detail="the revision exists but carries no full_text — run capture_register_standards",
        )
        return record

    anchors = anchor_revision(repo, revision_id, nodes)
    record["revision_id"] = revision_id
    record.update(anchor_report(anchors))
    record["status"] = "DRY_RUN" if dry_run else "ANCHORED"
    if not dry_run:
        record["written"] = repo.record_anchors(anchors)
    return record


def _summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The fleet-wide census, per relation, with every miss carried through.

    Kept separate from ``main`` so the rates are computed once and read the same
    way by the console line, the JSON and the written report.
    """
    totals: dict[str, dict[str, int]] = {r: {"attempted": 0, "anchored": 0} for r in RELATIONS}
    misses: list[dict[str, str]] = []
    for record in records:
        for relation, stats in record.get("by_relation", {}).items():
            totals[relation]["attempted"] += stats["attempted"]
            totals[relation]["anchored"] += stats["anchored"]
            misses += [
                {**miss, "relation": relation, "standard": record["standard"]}
                for miss in stats["unanchored"]
            ]
    return {
        "standards": len(records),
        "by_relation": {
            relation: {
                **stats,
                "rate": round(stats["anchored"] / stats["attempted"], 4),
            }
            for relation, stats in totals.items()
            if stats["attempted"]
        },
        "unanchored": misses,
        "per_standard": records,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--standard", default="")
    ap.add_argument("--report", action="store_true", help=f"write {REPORT_PATH}")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.all and not args.standard:
        ap.error("pass --all or --standard")

    register = Register.load()
    standards = sorted({n.standard for n in register.nodes})
    if args.standard:
        target = args.standard.lower()
        standards = [s for s in standards if s.lower() == target]
        if not standards:
            print(f"no such standard in the Register: {args.standard}", file=sys.stderr)
            return 2

    repo = Repository()
    records: list[dict[str, Any]] = []
    try:
        for standard in standards:
            record = anchor_standard(repo, register, standard, dry_run=args.dry_run)
            records.append(record)
            if not args.json:
                rates = " ".join(
                    f"{rel[:4]}={record['by_relation'][rel]['anchored']}"
                    f"/{record['by_relation'][rel]['attempted']}"
                    for rel in RELATIONS
                    if rel in record.get("by_relation", {})
                )
                print(
                    f"{standard:14s} {record['status']:12s} nodes={record['nodes']:3d}  {rates}"
                    f"  {record.get('detail', '')}",
                    flush=True,
                )
    finally:
        repo.close()

    summary = _summarise(records)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\nfleet-wide, per relation:")
        for relation, stats in summary["by_relation"].items():
            print(
                f"  {relation:20s} {stats['anchored']:4d}/{stats['attempted']:4d} = {stats['rate']}"
            )
        if summary["unanchored"]:
            print(f"\n{len(summary['unanchored'])} unanchored, every one named:")
            for miss in summary["unanchored"]:
                print(f"  {miss['relation']:20s} {miss['requirement_id']:28s} {miss['reason']}")
    if args.report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
