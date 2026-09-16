#!/usr/bin/env python3
"""Capture the Register's 14 standards into the canonical store (ONE_REGULATORY_EXTRACTION_V1 P3).

The backlog was never 33 unreachable PDFs. The Register holds ``source_pdfs``
with a sha256 for **14 standards** — proof those URLs resolved and those bytes
were fetched. What does not resolve is NERC's per-version URL for *older*
revisions, which is a separate and smaller problem about history.

Thirteen of those fourteen standards reached the store as ``pymupdf`` sections
with ``char_start = -1``: a structural extraction with no captured coordinate
space, so nothing could be projected from them and nothing could be anchored
into them. This script gives each one the ``docling`` whole-document capture the
reading path actually needs.

**sha-verify or STOP, per document.** The Register's structure was extracted
from those exact bytes. Anchoring a requirement's ``verbatim_text`` against
different bytes produces a join that is silently wrong rather than loudly
absent, so a mismatch fails that document and never captures it.

``store_capture`` scopes its rebuild to the capture's own extractor, so the
existing ``pymupdf`` and ``regulatory-bundle/1`` sections are left exactly
where they are. This adds a capture — it does not edit one, and it writes no
section to carry a relationship (every relationship this task adds lives in
``requirement_sections``).

    uv run python scripts/capture_register_standards.py --verify-sha --all
    uv run python scripts/capture_register_standards.py --verify-sha --standard CIP-011-3
    uv run python scripts/capture_register_standards.py --all --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.capture import (  # noqa: E402
    assert_faithful,
    capture_document,
    store_capture,
)
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

PDF_DIR = REPO_ROOT / "portal" / "modules" / "compliance" / "data" / "cip_pdfs"


def _standard_of(register: Register, pdf_name: str) -> str:
    """``cip-007-6.pdf`` -> ``CIP-007-6``, in the REGISTER'S OWN spelling.

    Not a naive ``.upper()``: ``cip-002-5.1a.pdf`` is standard ``CIP-002-5.1a``,
    and the store's ``logical_id`` carries that lowercase revision letter. An
    upper-cased id resolves to no revision at all, silently skipping a standard.
    """
    stem = pdf_name.removesuffix(".pdf")
    for node in register.nodes:
        if node.source_pdf == pdf_name or node.standard.lower() == stem:
            return node.standard
    return stem.upper()


def _revision_for(repo: Repository, standard: str, sha256_prefix: str) -> str:
    """The revision whose bytes are the Register's bytes.

    ``revision_id`` is the content hash, so the Register's recorded sha256
    prefix identifies the revision directly. Matching on ``logical_id`` alone
    would happily pick a different version of the same standard.
    """
    row = repo._conn.execute(
        """SELECT r.revision_id FROM document_revisions r
           WHERE r.logical_id = ? AND r.revision_id LIKE ? || '%'""",
        (f"NERC/{standard}", sha256_prefix),
    ).fetchone()
    return str(row[0]) if row else ""


def capture_one(
    repo: Repository,
    register: Register,
    pdf_name: str,
    sha256_prefix: str,
    *,
    verify_sha: bool,
    dry_run: bool,
) -> dict[str, Any]:
    standard = _standard_of(register, pdf_name)
    record: dict[str, Any] = {"standard": standard, "pdf": pdf_name, "status": "", "detail": ""}
    path = PDF_DIR / pdf_name
    if not path.is_file():
        record.update(status="ABSENT", detail=f"{path} does not exist")
        return record

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record["sha256"] = digest[:12]
    record["sha256_recorded"] = sha256_prefix
    if verify_sha and not digest.startswith(sha256_prefix):
        record.update(
            status="SHA_MISMATCH",
            detail=(
                f"bytes on disk hash {digest[:12]}, the Register records "
                f"{sha256_prefix} — the Register's structure came from different bytes, "
                "so an anchor against these would be silently wrong"
            ),
        )
        return record

    revision_id = _revision_for(repo, standard, digest[:12])
    if not revision_id:
        record.update(
            status="NO_REVISION",
            detail=f"no document_revisions row for NERC/{standard} at {digest[:12]}",
        )
        return record
    record["revision_id"] = revision_id

    existing = repo.get_document_text(revision_id) or ""
    record["already_captured"] = bool(existing)
    if dry_run:
        record["status"] = "DRY_RUN"
        return record

    started = time.time()
    captured = capture_document(path)
    report = assert_faithful(captured)  # raises on a lossy capture
    store_capture(repo, revision_id, captured)
    record.update(
        status="CAPTURED",
        elapsed_s=round(time.time() - started, 2),
        pages=report["pages"],
        characters=report["characters"],
        sections=report["sections"],
        sections_by_unit_kind=report["sections_by_unit_kind"],
        character_coverage_pct=report["character_coverage_pct"],
        reconstruction_diff=report["reconstruction_diff"] or "clean",
        table_rows=report["table_rows"],
    )
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="every standard the Register records")
    ap.add_argument("--standard", default="", help="one standard, e.g. CIP-011-3")
    ap.add_argument("--verify-sha", action="store_true", help="STOP a document whose bytes moved")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.all and not args.standard:
        ap.error("pass --all or --standard")

    register = Register.load()
    wanted = sorted(register.source_pdfs.items())
    if args.standard:
        target = args.standard.lower()
        wanted = [(p, s) for p, s in wanted if _standard_of(register, p).lower() == target]
        if not wanted:
            print(f"no such standard in the Register: {args.standard}", file=sys.stderr)
            return 2

    repo = Repository()
    records: list[dict[str, Any]] = []
    try:
        for pdf_name, sha256_prefix in wanted:
            record = capture_one(
                repo,
                register,
                pdf_name,
                sha256_prefix,
                verify_sha=args.verify_sha,
                dry_run=args.dry_run,
            )
            records.append(record)
            if not args.json:
                line = f"{record['standard']:14s} {record['status']:14s}"
                if record["status"] == "CAPTURED":
                    line += (
                        f" {record['pages']:3d}p {record['characters']:7d}ch "
                        f"{record['sections']:4d} sections  "
                        f"coverage {record['character_coverage_pct']}%  "
                        f"reconstruction {record['reconstruction_diff']}"
                    )
                elif record["detail"]:
                    line += f" {record['detail']}"
                print(line, flush=True)
    finally:
        repo.close()

    summary = {
        "requested": len(wanted),
        "captured": sum(1 for r in records if r["status"] == "CAPTURED"),
        "sha_verified": args.verify_sha,
        "failures": [r for r in records if r["status"] not in {"CAPTURED", "DRY_RUN"}],
        "documents": records,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"\n{summary['captured']}/{summary['requested']} captured"
            f"{' (sha-verified)' if args.verify_sha else ''}"
        )
        for failure in summary["failures"]:
            print(f"  FAILED {failure['standard']}: {failure['status']} — {failure['detail']}")
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
