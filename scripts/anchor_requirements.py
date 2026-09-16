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
    anchor_bundle_spans,
    anchor_report,
    anchor_revision,
)

PDF_DIR = REPO_ROOT / "portal" / "modules" / "compliance" / "data" / "cip_pdfs"

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
    bundle_anchors = _bundle_anchors(repo, revision_id, pdf, sha256_prefix, nodes, record)
    record["status"] = "DRY_RUN" if dry_run else "ANCHORED"
    if not dry_run:
        record["written"] = repo.record_anchors(anchors)
        if bundle_anchors:
            record["bundle_written"] = repo.record_anchors(bundle_anchors)
    return record


def _bundle_anchors(
    repo: Repository,
    revision_id: str,
    pdf: str,
    sha256_prefix: str,
    nodes: list[Any],
    record: dict[str, Any],
) -> list[Any]:
    """The revision bundle's Measures and Technical Basis, anchored (P5.1).

    `regulatory_bundle` owns the whole semantic content of a revision and all of
    it was reachable only through `resolve_governing_bundle`, re-parsed from the
    PDF at call time. The GTB prose is already IN the capture, so nothing is
    added to `source_sections` — each span is located in the captured character
    space and a `requirement_sections` row points at the sections that already
    contain it.

    A bundle that cannot be extracted is reported, never fatal: the requirement
    join stands on its own and the annotation is an enrichment on top of it.
    """
    from portal.modules.compliance.core.regulatory_bundle import extract_revision_bundle

    path = PDF_DIR / pdf
    if not path.is_file():
        record["bundle"] = f"no local copy of {pdf} to extract"
        return []
    try:
        bundle = extract_revision_bundle(path.read_bytes(), source_name=pdf, expected_sha256="")
    except Exception as exc:  # noqa: BLE001 — a bundle failure is reported, not fatal
        record["bundle"] = f"{type(exc).__name__}: {exc}"
        return []
    if not str(getattr(bundle, "source_sha256", "")).startswith(sha256_prefix):
        record["bundle"] = "local bytes are not the Register's revision — bundle skipped"
        return []
    anchors = anchor_bundle_spans(repo, revision_id, bundle, nodes)
    census: dict[str, int] = {}
    sections: dict[str, set[str]] = {}
    for anchor in anchors:
        census[anchor.relation] = census.get(anchor.relation, 0) + 1
        sections.setdefault(anchor.relation, set()).update(anchor.section_ids)
    record["bundle"] = {
        "technical_basis_section": getattr(bundle, "technical_basis_section", ""),
        "spans_anchored": census,
        "sections_joined": {rel: len(ids) for rel, ids in sections.items()},
    }
    return anchors


def verify_bundle_equivalence(
    repo: Repository, register: Register, standard: str
) -> dict[str, Any]:
    """Does the join reach everything re-parsing the PDF reaches? (P5.3)

    The precondition for file D. `resolve_governing_bundle` re-parses the PDF at
    call time to obtain the Measures and the Guidelines and Technical Basis; §P5
    claims the same material is reachable through the stored join. This measures
    it, and the measure is by SECTION, not by byte: the two readers render the
    same bytes differently (pymupdf splices the running page header inline,
    docling does not), so byte equality between their outputs is the wrong test
    and would fail for reasons that have nothing to do with reachability.

    For every Technical Basis piece the bundle carries, locate it in the capture
    and check the sections covering it are all in the join's set. Anything the
    bundle reaches and the join does not is NAMED.
    """
    from portal.modules.compliance.core.regulatory_bundle import extract_revision_bundle
    from portal.modules.compliance.core.requirement_anchor import (
        OffsetMap,
        _span_pieces,
        locate,
        sections_overlapping,
    )

    nodes = [n for n in register.nodes if n.standard == standard]
    pdf = next((n.source_pdf for n in nodes if n.source_pdf), "")
    revision_id = _revision_for(repo, standard, register.source_pdfs.get(pdf, ""))
    if not revision_id or not (repo.get_document_text(revision_id) or ""):
        return {"standard": standard, "status": "NOT_CAPTURED"}
    offsets = OffsetMap.build(repo.get_document_text(revision_id) or "")
    bundle = extract_revision_bundle((PDF_DIR / pdf).read_bytes(), source_name=pdf)

    located = covered = 0
    unreachable: list[str] = []
    for node in nodes:
        joined = {
            str(r["section_id"])
            for r in repo.sections_for_requirement(node.id, relations=("technical_basis",))
        }
        # every component `anchor_bundle_spans` writes, so the measure covers
        # what the join actually claims rather than a subset of it.
        spans = [
            *bundle.technical_basis.get(node.requirement, []),
            *bundle.technical_basis_rationale.get(node.requirement, []),
            *(
                bundle.technical_basis_parts.get(f"{node.requirement} Part {node.part}", [])
                if node.part
                else []
            ),
        ]
        for span in spans:
            for group in _span_pieces(span.text):
                for piece in group[1:] or group[:1]:
                    start, end, _count, _why = locate(piece, offsets)
                    if start < 0:
                        continue
                    located += 1
                    missing = set(sections_overlapping(repo, revision_id, start, end)) - joined
                    if missing:
                        unreachable.append(f"{node.id}: {sorted(missing)[0]}")
                    else:
                        covered += 1
    return {
        "standard": standard,
        "status": "MEASURED",
        "pieces_located": located,
        "covered_by_the_join": covered,
        "rate": round(covered / located, 4) if located else 0.0,
        "reachable_by_reparse_only": sorted(set(unreachable)),
    }


def _print_summary(summary: dict[str, Any]) -> None:
    """The fleet-wide rates, and every miss by name — never a rounded total."""
    print("\nfleet-wide, per relation:")
    for relation, stats in summary["by_relation"].items():
        print(f"  {relation:20s} {stats['anchored']:4d}/{stats['attempted']:4d} = {stats['rate']}")
    if summary["unanchored"]:
        print(f"\n{len(summary['unanchored'])} unanchored, every one named:")
        for miss in summary["unanchored"]:
            print(f"  {miss['relation']:20s} {miss['requirement_id']:28s} {miss['reason']}")


def _console_line(record: dict[str, Any]) -> str:
    """One standard's per-relation rates, as the operator reads them."""
    rates = " ".join(
        f"{rel[:4]}={record['by_relation'][rel]['anchored']}"
        f"/{record['by_relation'][rel]['attempted']}"
        for rel in RELATIONS
        if rel in record.get("by_relation", {})
    )
    return (
        f"{record['standard']:14s} {record['status']:12s} nodes={record['nodes']:3d}  "
        f"{rates}  {record.get('detail', '')}"
    )


def _equivalence_pass(
    register: Register, standards: list[str], *, quiet: bool
) -> list[dict[str, Any]]:
    """The P5.3 measurement across a set of standards, reported as it runs."""
    repo = Repository()
    try:
        rows = [verify_bundle_equivalence(repo, register, s) for s in standards]
    finally:
        repo.close()
    if quiet:
        return rows
    print("\nbundle equivalence — does the join reach what re-parsing reaches?")
    for row in rows:
        if row["status"] != "MEASURED":
            print(f"  {row['standard']:14s} {row['status']}")
            continue
        only = row["reachable_by_reparse_only"]
        print(
            f"  {row['standard']:14s} {row['covered_by_the_join']:4d}/"
            f"{row['pieces_located']:4d} = {row['rate']}"
            + (f"  reparse-only: {len(only)}" if only else "")
        )
    return rows


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
    ap.add_argument(
        "--verify-bundle-equivalence",
        action="store_true",
        help="measure whether the join reaches everything re-parsing the PDF reaches (P5.3)",
    )
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
                print(_console_line(record), flush=True)
    finally:
        repo.close()

    summary = _summarise(records)
    if args.verify_bundle_equivalence:
        summary["bundle_equivalence"] = _equivalence_pass(register, standards, quiet=args.json)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_summary(summary)
    if args.report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
