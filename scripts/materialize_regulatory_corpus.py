#!/usr/bin/env python3
"""Materialize the regulatory corpus into the canonical store (BILATERAL_CORPUS_V1 P3).

The twin of ``materialize_internal_corpus.py``. Every acquired official artifact
— standard PDF, implementation plan, technical rationale, RSAW, the lifecycle
workbook, the Glossary — becomes a ``source_documents`` row with
``jurisdiction='US'`` and its own ``source_kind``, a ``document_revisions`` row
keyed on byte hash carrying the lifecycle dates **parsed from the One-Stop-Shop
workbook and never from a filename**, and a faithful whole-document capture as
typed ``source_sections`` / ``source_spans``.

Symmetry is the point: after this runs, the regulatory side and the operator
side are the same kind of thing in the same tables, and the only difference
between them is the ``jurisdiction`` column.

Guarantees:

* **hash-match or fail.** Every artifact on disk is re-hashed and compared to the
  acquisition manifest. A mismatch is a hard failure, never a warning — a
  document whose bytes moved under the manifest is not the document the
  lifecycle facts describe.
* **both clocks.** ``effective_date`` and ``inactive_date`` come from the
  workbook; ``recorded_from`` is when this store started believing it. A
  future-effective standard resolves as ``future`` under ``valid_at``; a
  late-recorded fact answers ``UNKNOWN_KNOWLEDGE`` under ``known_at``.
* **one identity per standard.** ``NERC/CIP-007-6``, not
  ``NERC/cip-007-6.pdf`` — two acquisitions of one standard are two revisions of
  one document. Pre-P3 filename-shaped identities are repaired in place and the
  repair is reported.
* **non-destructive.** A snapshot is taken first, sections are a
  same-fingerprint rebuild scoped to this extractor, and no revision bytes are
  touched.

    uv run python scripts/materialize_regulatory_corpus.py
    uv run python scripts/materialize_regulatory_corpus.py --no-backup --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import nerc_source_sync as sync  # noqa: E402
from portal.modules.compliance.core.capture import (  # noqa: E402
    capture_document,
    store_capture,
)
from portal.modules.compliance.core.glossary import (  # noqa: E402
    GLOSSARY_ARTIFACT,
    GLOSSARY_LOGICAL_ID,
    register_glossary,
)
from portal.modules.compliance.core.models import SourceDocument  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

BACKUP_DIR = REPO_ROOT / "data" / "private" / "backups"
RECEIPT_ROOT = REPO_ROOT / "coding_task" / "v9_compliance" / "private" / "regulatory_corpus"

#: artifact names that carry no document text to capture. The workbook is a
#: spreadsheet — its content is the lifecycle facts, already parsed and
#: recorded on every revision it describes, so capturing it as prose would add
#: a searchable copy of data that is already structured.
_NO_CAPTURE = {"one-stop-shop.xlsx"}


class HashMismatchError(RuntimeError):
    """An artifact's bytes on disk do not match the acquisition manifest."""


def _snapshot(backup: bool) -> str:
    if not backup:
        return ""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUP_DIR / f"pre-regulatory-{stamp}.db"
    repo = Repository()
    try:
        repo.backup_to(target)
    finally:
        repo.close()
    return str(target)


def _verify_hashes(manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Re-hash every artifact against the manifest. Raises on any mismatch."""
    checked: list[dict[str, str]] = []
    problems: list[str] = []
    for entry in manifest.get("artifacts", []):
        path = Path(str(entry.get("path", "")))
        declared = str(entry.get("sha256", ""))
        if entry.get("status") == "FAILED" or not declared:
            continue
        if not path.is_file():
            problems.append(f"{entry.get('name')}: manifest names {path}, which does not exist")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != declared:
            problems.append(
                f"{entry.get('name')}: bytes on disk hash {actual[:16]}…, "
                f"manifest says {declared[:16]}…"
            )
            continue
        checked.append({"name": str(entry.get("name")), "sha256": declared})
    if problems:
        raise HashMismatchError(
            "acquisition manifest does not match the bytes on disk:\n  " + "\n  ".join(problems)
        )
    return checked


def _standard_of(logical_id: str) -> str:
    """``NERC/CIP-007-6 implementation plan`` -> ``CIP-007-6``."""
    tail = logical_id.split("/", 1)[-1]
    return tail.split(" ", 1)[0]


def _repair_filename_identities(repo: Repository, report: dict[str, Any]) -> None:
    """Point pre-P3 filename-shaped logical ids at the canonical standard.

    Before P3 an acquired artifact registered as ``NERC/cip-007-6.pdf``, so the
    same standard existed twice: once under its stable id from the register
    materializer and once under its filename. ``revision_id`` is the content
    hash and therefore a primary key, so the revision cannot simply be
    re-registered — the row is repointed and the orphaned document removed.
    """
    conn = repo._conn
    moved: list[dict[str, str]] = []
    # only FILENAME-shaped ids are legacy. A canonical id never carries a file
    # extension, so this can never repoint 'NERC/CIP-007-6 implementation plan'
    # at 'NERC/CIP-007-6' and merge a component into the standard it belongs to.
    rows = conn.execute(
        """SELECT logical_id FROM source_documents
           WHERE logical_id GLOB 'NERC/*.[Pp][Dd][Ff]'
              OR logical_id GLOB 'NERC/*.[Xx][Ll][Ss][Xx]'"""
    ).fetchall()
    for (old_id,) in rows:
        name = old_id.split("/", 1)[-1]
        artifact = sync.Artifact(name=name, url="", role=_role_of(name))
        new_id, _kind, _title = sync.canonical_identity(artifact)
        if new_id == old_id:
            continue
        if not conn.execute(
            "SELECT 1 FROM source_documents WHERE logical_id = ?", (new_id,)
        ).fetchone():
            continue  # the canonical document does not exist yet; this run creates it
        with repo._lock, conn:
            conn.execute(
                "UPDATE document_revisions SET logical_id = ? WHERE logical_id = ?",
                (new_id, old_id),
            )
            conn.execute("DELETE FROM source_documents WHERE logical_id = ?", (old_id,))
        moved.append({"from": old_id, "to": new_id})
    report["identity_repairs"] = moved


def _role_of(artifact_name: str) -> str:
    """The acquisition role a legacy filename-shaped identity implies."""
    name = artifact_name.lower()
    if "one-stop-shop" in name:
        return "registry"
    if "implementation-plan" in name:
        return "implementation_plan"
    if "technical-rationale" in name:
        return "technical_rationale"
    if "rsaw" in name:
        return "rsaw"
    return "standard"


def _normalise_jurisdictions(repo: Repository, report: dict[str, Any]) -> None:
    """One jurisdiction, one spelling.

    The store carried both ``US`` (from the acquisition path) and
    ``United States`` (from the register materializer) for the same
    jurisdiction, so every jurisdiction-filtered query was wrong by
    construction. ISO-style ``US`` wins because it is what the acquisition path
    and the Glossary already write.
    """
    conn = repo._conn
    with repo._lock, conn:
        cur = conn.execute(
            "UPDATE source_documents SET jurisdiction = 'US' WHERE jurisdiction = 'United States'"
        )
    report["jurisdiction_normalised"] = cur.rowcount


def _lifecycle_for(manifest: dict[str, Any], logical_id: str) -> dict[str, Any]:
    """The workbook row governing this document, by standard id. Never a
    filename parse — the workbook is the authority and a document with no
    workbook row gets no dates at all."""
    return dict(manifest.get("lifecycle", {}).get(_standard_of(logical_id), {}))


def _capture_into(repo: Repository, revision_id: str, path: Path) -> dict[str, Any]:
    captured = capture_document(path)
    return store_capture(repo, revision_id, captured)


def materialize(
    *,
    directory: Path | None = None,
    repository: Repository | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    from portal.modules.compliance.core.temporal import now_iso

    directory = directory or sync.OFFICIAL_DIR
    manifest = sync.load_manifest(directory)
    if not manifest:
        raise RuntimeError(
            f"no acquisition manifest under {directory} — run the source sync before materializing"
        )

    backup_path = _snapshot(backup) if repository is None else ""
    repo = repository or Repository()
    report: dict[str, Any] = {
        "materialized_at": now_iso(),
        "directory": str(directory),
        "backup": backup_path,
        "schema_version": repo.schema_version,
        "hash_verified": _verify_hashes(manifest),
        "documents": [],
        "skipped": [],
    }

    for entry in manifest.get("artifacts", []):
        if entry.get("status") == "FAILED":
            report["skipped"].append({"name": entry.get("name"), "reason": "acquisition failed"})
            continue
        name = str(entry.get("name", ""))
        path = Path(str(entry.get("path", "")))
        payload = path.read_bytes()

        if name == GLOSSARY_ARTIFACT:
            glossary_report = register_glossary(repo, payload, str(path))
            report["documents"].append(
                {
                    "logical_id": GLOSSARY_LOGICAL_ID,
                    "source_kind": "glossary",
                    "revision_id": glossary_report["revision_id"],
                    "sections": glossary_report["sections"],
                    "terms": glossary_report["terms"],
                }
            )
            continue

        artifact = sync.Artifact(
            name=name, url=str(entry.get("url", "")), role=str(entry.get("role", ""))
        )
        logical_id, source_kind, title = sync.canonical_identity(artifact)
        lifecycle = _lifecycle_for(manifest, logical_id)
        repo.upsert_source_document(
            SourceDocument(
                logical_id=logical_id,
                title=str(lifecycle.get("title") or title),
                issuer="NERC",
                source_kind=source_kind,
                jurisdiction="US",
            )
        )
        revision = repo.add_document_revision(
            logical_id, str(path), payload, binding_effect="regulatory"
        )
        repo.set_regulatory_lifecycle(
            revision.revision_id,
            effective_date=str(lifecycle.get("effective", "")),
            inactive_date=str(lifecycle.get("inactive", "")),
            approved_date=str(lifecycle.get("board_adopted", "")),
            authored_date=str(lifecycle.get("filed", "")),
            lifecycle_status=str(lifecycle.get("status", "")),
            source_url=str(entry.get("url", "")),
        )
        record: dict[str, Any] = {
            "logical_id": logical_id,
            "source_kind": source_kind,
            "revision_id": revision.revision_id,
            "alias_path": str(path),
            "effective_date": lifecycle.get("effective", ""),
            "inactive_date": lifecycle.get("inactive", ""),
            "lifecycle_status": lifecycle.get("status", ""),
            "lifecycle_source": "One-Stop-Shop workbook" if lifecycle else "none recorded",
        }
        if name in _NO_CAPTURE:
            record["capture"] = "not captured — structured lifecycle registry, not prose"
        else:
            record["capture"] = _capture_into(repo, revision.revision_id, path)
        report["documents"].append(record)

    _repair_filename_identities(repo, report)
    _normalise_jurisdictions(repo, report)
    report["census"] = _census(repo)
    if repository is None:
        repo.close()
    return report


def _census(repo: Repository) -> dict[str, Any]:
    conn = repo._conn
    by_kind = conn.execute(
        """SELECT d.jurisdiction, d.source_kind, count(DISTINCT d.logical_id) AS documents,
                  count(s.section_id) AS sections
           FROM source_documents d
           LEFT JOIN document_revisions r ON r.logical_id = d.logical_id
           LEFT JOIN source_sections s ON s.revision_id = r.revision_id
           GROUP BY 1, 2 ORDER BY 1, 2"""
    ).fetchall()
    by_unit = conn.execute(
        """SELECT s.unit_kind, count(*) FROM source_sections s
           JOIN document_revisions r ON r.revision_id = s.revision_id
           JOIN source_documents d ON d.logical_id = r.logical_id
           WHERE d.jurisdiction = 'US' GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()
    return {
        "documents_and_sections": [dict(r) for r in by_kind],
        "regulatory_sections_by_unit_kind": dict(by_unit),
        "jurisdictions": [
            r[0] for r in conn.execute("SELECT DISTINCT jurisdiction FROM source_documents")
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    report = materialize(directory=args.directory, backup=not args.no_backup)
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt = args.output or (RECEIPT_ROOT / stamp / "materialization.json")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(payload + "\n", encoding="utf-8")

    if args.as_json:
        print(payload)
    else:
        for doc in report["documents"]:
            capture = doc.get("capture")
            if isinstance(capture, dict):
                detail = (
                    f"{capture['sections']:4d} sections, {capture['characters']:7d} chars, "
                    f"cov {capture['character_coverage_pct']}%"
                )
            elif doc.get("terms") is not None:
                detail = f"{doc['sections']:4d} sections, {doc['terms']} glossary terms"
            else:
                detail = str(capture)
            print(
                f"  {doc['logical_id'][:46]:48s} {str(doc['source_kind'])[:20]:22s} "
                f"eff {str(doc.get('effective_date') or '-'):11s} "
                f"inact {str(doc.get('inactive_date') or '-'):11s} {detail}"
            )
        print(f"\nhash-verified artifacts: {len(report['hash_verified'])}")
        print(f"identity repairs: {report.get('identity_repairs')}")
        print(f"jurisdiction rows normalised: {report.get('jurisdiction_normalised')}")
        print(f"jurisdictions now: {report['census']['jurisdictions']}")
        print(f"receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
