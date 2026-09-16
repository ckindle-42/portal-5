#!/usr/bin/env python3
"""Run the whole-document capture fidelity gates over PDFs (BILATERAL_CORPUS_V1 P1).

    uv run python scripts/compliance_capture_fidelity.py portal/modules/compliance/data/cip_pdfs/*.pdf
    uv run python scripts/compliance_capture_fidelity.py --internal   # the operator corpus

Per document it reports page count, section count by ``unit_kind``, character
coverage, gaps/overlaps, missing pages, the reconstruction diff, and how many of
the layout reader's own strings failed to survive the capture. Exit status is
non-zero if any document fails any gate — a capture that drops material must not
be reported as green.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import capture as cap  # noqa: E402

INTERNAL_CORPUS = REPO_ROOT / "coding_task" / "v9_compliance" / "LSPG-CIP"


def _internal_report(pdf: Path) -> dict:
    """The same three properties over the internal sectionizer's own tiling."""
    from portal.modules.compliance.core import internal_corpus as ic

    inv = ic.inventory_file(pdf)
    full, sections = inv["full_text"], inv["sections"]
    cursor, covered, gaps, overlaps = 0, 0, [], []
    for section in sorted(sections, key=lambda s: s.char_start):
        if section.char_start > cursor:
            gaps.append((cursor, section.char_start))
        elif section.char_start < cursor:
            overlaps.append((section.char_start, cursor))
        covered += max(0, section.char_end - max(section.char_start, cursor))
        cursor = max(cursor, section.char_end)
    if cursor < len(full):
        gaps.append((cursor, len(full)))
    roles: dict[str, int] = {}
    for section in sections:
        roles[section.role] = roles.get(section.role, 0) + 1
    rebuilt = "".join(s.text for s in sorted(sections, key=lambda s: s.char_start))
    return {
        "document": pdf.name,
        "pages": inv["pages"],
        "characters": len(full),
        "sections": len(sections),
        "sections_by_role": roles,
        "character_coverage_pct": round(100.0 * covered / len(full), 4) if full else 0.0,
        "gaps": gaps,
        "overlaps": overlaps,
        "missing_pages": [],
        "reconstruction_diff": "" if rebuilt == full else "MISMATCH",
        "reader_strings_absent": 0,
    }


def _failed(report: dict) -> list[str]:
    bad = []
    if report["character_coverage_pct"] != 100.0:
        bad.append("coverage")
    for key in ("gaps", "overlaps", "missing_pages"):
        if report.get(key):
            bad.append(key)
    if report["reconstruction_diff"]:
        bad.append("reconstruction")
    if report.get("reader_strings_absent"):
        bad.append("reader_strings")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdfs", nargs="*", type=Path)
    ap.add_argument("--internal", action="store_true", help="run over the operator corpus")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args()

    if args.internal:
        targets = sorted(INTERNAL_CORPUS.rglob("*.pdf"))
        run = _internal_report
    else:
        targets = [p for p in args.pdfs if p.is_file()]
        run = lambda p: cap.fidelity_report(cap.capture_document(p))  # noqa: E731
    if not targets:
        print("no documents to check", file=sys.stderr)
        return 2

    reports, failures = [], []
    for pdf in targets:
        started = time.time()
        report = run(pdf)
        report["elapsed_s"] = round(time.time() - started, 2)
        reports.append(report)
        bad = _failed(report)
        if bad:
            failures.append((pdf.name, bad))
        if not args.as_json:
            kinds = report.get("sections_by_unit_kind") or report.get("sections_by_role") or {}
            print(
                f"{'FAIL' if bad else 'ok  '} {pdf.name[:46]:48s} "
                f"pages {report['pages']:3d}  sections {report['sections']:4d}  "
                f"chars {report['characters']:7d}  cov {report['character_coverage_pct']:6.2f}%  "
                f"recon {report['reconstruction_diff'] or 'empty':6s}  "
                f"{report['elapsed_s']:5.1f}s  {kinds}"
            )
    if args.as_json:
        print(json.dumps(reports, indent=2))
    else:
        print(f"\n{len(targets) - len(failures)}/{len(targets)} documents captured faithfully")
        for name, bad in failures:
            print(f"  FAIL {name}: {', '.join(bad)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
