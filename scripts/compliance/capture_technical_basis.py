#!/usr/bin/env python3
"""Every register requirement carries what it says AND how it is meant to be met.

A standard has two layers. The normative text says what is required; the
Guidelines and Technical Basis (GTB), or in newer versions a separate
Technical Rationale document, says what the requirement is for and how an
entity is meant to meet it. Procedure reviews need both. Measured 2026-09-22:
eight register versions (CIP-003-9, 004-7, 005-7, 008-6, 010-4, 011-3, 012-2,
013-2; 120 requirements) had NO technical-basis material, because their
Technical Rationale PDFs were acquired and registered but never captured.

This script, idempotent and non-destructive:

1. captures every regulatory revision the store holds bytes for but never
   captured (``materialize_regulatory_corpus.capture_registered``: hash-match
   or skip);
2. places each register version's Technical Rationale sections on the
   requirements their own headings name
   (``requirement_anchor.anchor_rationale_document``, ``method='heading'``);
   sections whose heading names no requirement are recorded as unplaced;
3. writes a receipt: technical-basis coverage per standard before and after,
   what was unplaced and why, and each standard's fixed-body and largest
   render size, so a context overflow is visible before a sweep hits it.

    # dry run against a copy (no live write):
    uv run python scripts/compliance/capture_technical_basis.py --store /tmp/copy.sqlite --out r.json
    # live (snapshot first):
    uv run python scripts/compliance/capture_technical_basis.py \\
        --out reports/compliance/cite_and_scope/p2/technical_basis.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sqlite3
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import reading_material, requirement_anchor  # noqa: E402
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from scripts.materialize_regulatory_corpus import capture_registered  # noqa: E402

_TR_SUFFIX = " technical rationale"


def _snapshot(repo: Repository) -> str:
    src = pathlib.Path(repo._conn.execute("PRAGMA database_list").fetchone()[2])
    dst_dir = REPO_ROOT / "data" / "compliance" / "backups"
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    dst = dst_dir / f"pre_technical_basis_{stamp}.sqlite"
    source, target = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    return str(dst)


def coverage(repo: Repository, register: Register) -> dict[str, dict[str, int]]:
    """Per register version: requirements, and how many carry technical basis."""
    with_tb = {
        str(r[0])
        for r in repo._conn.execute(
            "SELECT DISTINCT requirement_id FROM requirement_sections"
            " WHERE relation = 'technical_basis'"
        )
    }
    out: dict[str, dict[str, int]] = {}
    for node in register.nodes:
        row = out.setdefault(node.standard, {"requirements": 0, "with_technical_basis": 0})
        row["requirements"] += 1
        row["with_technical_basis"] += int(str(node.id) in with_tb)
    return dict(sorted(out.items()))


def render_sizes(repo: Repository, register: Register) -> dict[str, dict[str, int]]:
    """Fixed-body chars and the largest rendered material per register version."""
    out: dict[str, dict[str, int]] = {}
    for standard in sorted({n.standard for n in register.nodes}):
        fixed = reading_material.fixed_body(repo, standard)
        if "error" in fixed:
            out[standard] = {"error": 1}
            continue
        largest = 0
        for node in (n for n in register.nodes if n.standard == standard):
            rendered = reading_material.render(repo, str(node.id), fixed=fixed)
            largest = max(largest, int(rendered.get("chars", 0)))
        out[standard] = {"fixed_chars": int(fixed["chars"]), "max_render_chars": largest}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", type=pathlib.Path, help="store path (default: the live store)")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--no-sizes", action="store_true", help="skip the render-size pass")
    args = ap.parse_args()

    register = Register.load()
    repo = Repository(args.store) if args.store else Repository()
    receipt: dict[str, Any] = {"run_id": _dt.datetime.now(_dt.UTC).isoformat()}
    try:
        receipt["store"] = str(repo._conn.execute("PRAGMA database_list").fetchone()[2])
        receipt["backup"] = "" if (args.no_backup or args.store) else _snapshot(repo)
        receipt["coverage_before"] = coverage(repo, register)
        if not args.no_sizes:
            receipt["render_before"] = render_sizes(repo, register)

        captured = capture_registered(repo)
        receipt["captured"] = [
            {k: v for k, v in c.items() if k != "capture"}
            | {"sections": (c.get("capture") or {}).get("sections")}
            for c in captured["captured"]
        ]
        receipt["capture_skipped"] = captured["skipped"]

        anchored: dict[str, Any] = {}
        for standard in sorted({n.standard for n in register.nodes}):
            row = repo._conn.execute(
                """SELECT v.revision_id FROM document_revisions v
                    WHERE v.logical_id = ?
                    ORDER BY (SELECT COUNT(*) FROM source_sections s
                               WHERE s.revision_id = v.revision_id) DESC
                    LIMIT 1""",
                (f"NERC/{standard}{_TR_SUFFIX}",),
            ).fetchone()
            if row is None:
                continue
            nodes = [n for n in register.nodes if n.standard == standard]
            anchors, unplaced = requirement_anchor.anchor_rationale_document(
                repo, str(row[0]), nodes
            )
            written = repo.record_anchors(anchors) if anchors else {"sections_joined": 0}
            anchored[standard] = {
                "revision_id": str(row[0]),
                "requirements_placed": len(anchors),
                "sections_joined": written.get("sections_joined", 0),
                "unplaced_sections": len(unplaced),
                "unplaced_chars": sum(u["chars"] for u in unplaced),
                "unplaced": unplaced,
            }
        receipt["technical_rationale_anchoring"] = anchored
        receipt["coverage_after"] = coverage(repo, register)
        if not args.no_sizes:
            receipt["render_after"] = render_sizes(repo, register)
    finally:
        repo.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    print(f"captured {len(receipt['captured'])}, skipped {len(receipt['capture_skipped'])}")
    print(
        f"{'standard':14s} {'tb before':>10s} {'tb after':>10s} {'unplaced':>9s} {'max render':>11s}"
    )
    for standard, after in receipt["coverage_after"].items():
        before = receipt["coverage_before"][standard]
        tr = anchored.get(standard, {})
        size = (receipt.get("render_after") or {}).get(standard, {})
        print(
            f"{standard:14s} {before['with_technical_basis']:>4d}/{before['requirements']:<5d}"
            f" {after['with_technical_basis']:>4d}/{after['requirements']:<5d}"
            f" {tr.get('unplaced_sections', '-')!s:>9s} {size.get('max_render_chars', '-')!s:>11s}"
        )
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
