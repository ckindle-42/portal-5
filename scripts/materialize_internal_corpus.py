#!/usr/bin/env python3
"""Materialize truthful internal revisions and source functions (END_TO_END P4).

Reads every controlled document on disk, reads each document's own control
block (identity, version, effective/approval/review dates, owner — never a
filename guess), classifies every section's function into the controlled
SOURCE_ROLES vocabulary, and records both onto the existing immutable store
revisions. Folder/prefix Cartesian mapping proposals are quarantined as
discovery-only (``derivation`` column) so established trace and deterministic
impact cannot present them as fact.

Non-destructive by construction: snapshots first, additive column updates,
re-derived sections replace only sections written by this extractor, and no
revision bytes or legacy rows are touched. The run receipt carries per-document
provenance and the quarantine census.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from portal.modules.compliance.core import internal_corpus as ic
from portal.modules.compliance.core.internal_corpus import InternalSection
from portal.modules.compliance.core.internal_model import extract_assertions
from portal.modules.compliance.core.models import SourceDocument, SourceSection
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.result_contract import is_source_role

BACKUP_DIR = Path("data/private/backups")
RECEIPT_ROOT = Path("coding_task/v9_compliance/private/internal_corpus")

#: derivation labels for the quarantine (P4 exit: no Cartesian assertion in
#: established trace/impact)
DERIVATION_FOLDER_CARTESIAN = "folder_cartesian"
DERIVATION_FOLDER_ORG_PLACEHOLDER = "folder_placeholder_org"

V3_CANDIDATE_RATIONALE = "content-derived candidate"
_PLACEHOLDER_ORG_EDGES = ("PERFORMED_BY", "APPLIES_TO", "EVIDENCED_BY", "HAS_ACTIVITY")
EXTRACTOR = "internal_corpus"
EXTRACTOR_VERSION = "1"


def _control_dict(control: ic.DocumentControl) -> dict:
    return {
        "title": control.title,
        "document_number": control.document_number,
        "stated_type": control.stated_type,
        "nerc_standard": control.nerc_standard,
        "effective_date": control.effective_date,
        "approval_date": control.approval_date,
        "approver": control.approver,
        "owner": control.owner,
        "owner_title": control.owner_title,
        "version": control.version,
        "authored_date": control.authored_date,
        "last_reviewed_date": control.last_reviewed_date,
        "sources": control.sources,
    }


def _section_dict(section: InternalSection, assertions: int) -> dict:
    return {
        "path": section.path,
        "title": section.title,
        "role": section.role,
        "page_start": section.page_start,
        "page_end": section.page_end,
        "span_sha256": section.span_sha256(),
        "operative_assertions": assertions,
    }


def _snapshot(backup: bool) -> str:
    """Pre-run snapshot of the live store (never migrate without one)."""
    if not backup:
        return ""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    pre = BACKUP_DIR / f"pre-v10-{stamp}.db"
    Repository().backup_to(pre)
    return str(pre)


def _materialize_document(repo: Repository, corpus: Path, pdf: Path, inv: dict) -> dict:
    """Record sourced metadata, re-derive classified sections, and type the
    legacy whole-document section for one on-disk controlled document."""
    from portal.modules.compliance.core.temporal import now_iso

    conn = repo._conn
    revision_id = inv["sha256"]
    control = inv["control"]
    entry: dict = {
        "path": str(pdf.relative_to(corpus)),
        "sha256": revision_id,
        "pages": inv["pages"],
        "control": _control_dict(control),
        "source_kind": inv["source_kind"],
        "binding_effect": inv["binding_effect"],
        "document_role": inv["document_role"],
        "kind_evidence": inv["kind_evidence"],
        "materialized_at": now_iso(),
    }
    repo.update_revision_control_metadata(
        revision_id,
        binding_effect=inv["binding_effect"],
        document_number=control.document_number or "",
        version=control.version or "",
        owner=control.owner or "",
        owner_title=control.owner_title or "",
        effective_date=control.effective_date,
        approved_date=control.approval_date,
        authored_date=control.authored_date,
        last_reviewed_date=control.last_reviewed_date,
    )
    _update_logical_document(repo, conn, corpus, pdf, inv)
    _rederive_sections(repo, conn, pdf, inv)
    _type_legacy_document_section(repo, conn, revision_id, inv["document_role"])
    return entry


def _update_logical_document(repo: Repository, conn, corpus: Path, pdf: Path, inv: dict) -> None:
    """The sourced kind and title (the document's own title block when it
    states one, else the filename stem it was registered with)."""
    logical_id = str(pdf.relative_to(corpus))
    existing = conn.execute(
        "SELECT title, jurisdiction FROM source_documents WHERE logical_id = ?",
        (logical_id,),
    ).fetchone()
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=(inv["control"].title or (existing[0] if existing else "")) or pdf.stem,
            issuer="LSPG",
            source_kind=inv["source_kind"],
            jurisdiction=(existing[1] if existing else "") or "internal",
        )
    )


def _rederive_sections(repo: Repository, conn, pdf: Path, inv: dict) -> None:
    """Same-fingerprint rebuild: a changed classification never leaves stale
    sections beside fresh ones. Every role must be in the vocabulary."""
    revision_id = inv["sha256"]
    with repo._lock, conn:
        conn.execute(
            """DELETE FROM source_spans WHERE section_id IN (
                   SELECT section_id FROM source_sections
                   WHERE revision_id = ? AND extractor = ?)""",
            (revision_id, EXTRACTOR),
        )
        conn.execute(
            "DELETE FROM source_sections WHERE revision_id = ? AND extractor = ?",
            (revision_id, EXTRACTOR),
        )
    section_rows = []
    for section in inv["sections"]:
        section.revision_id = revision_id  # scope the section id to this revision
        if not is_source_role(section.role):
            raise ValueError(
                f"{pdf.name}: section {section.path!r} classified outside the "
                f"controlled vocabulary: {section.role!r}"
            )
        assertions = extract_assertions(
            revision_id,
            section.text,
            anchor_id=f"{revision_id}:{section.path}",
            section_role=section.role,
        )
        repo.add_source_section(
            SourceSection(
                section_id=section.section_id,
                revision_id=revision_id,
                path=section.path,
                page_start=section.page_start,
                page_end=section.page_end,
                extractor=EXTRACTOR,
                extractor_version=EXTRACTOR_VERSION,
                role=section.role,
                title=section.title,
            )
        )
        span_id = "ispan-" + section.section_id[len("isection-") :]
        repo.add_source_span(
            span_id,
            section.section_id,
            section.char_start,
            section.char_end,
            section.span_sha256(),
        )
        section_rows.append(_section_dict(section, len(assertions)))
    inv["section_rows"] = section_rows


def _type_legacy_document_section(
    repo: Repository, conn, revision_id: str, document_role: str
) -> None:
    """Give the pre-P4 whole-document section the document's own role so
    historical anchors carry the function too."""
    if not document_role:
        return
    with repo._lock, conn:
        legacy = conn.execute(
            """SELECT section_id FROM source_sections
               WHERE revision_id = ? AND extractor = 'pymupdf' AND path = 'document'""",
            (revision_id,),
        ).fetchone()
    if legacy:
        repo.set_section_function(legacy[0], role=document_role, title="")


def materialize(
    corpus: Path,
    *,
    repository: Repository | None = None,
    backup: bool = True,
) -> dict:
    from portal.modules.compliance.core.temporal import now_iso

    backup_path = _snapshot(backup)
    repo = repository or Repository()  # opening applies migration 10
    conn = repo._conn

    pdfs = sorted(f for f in corpus.rglob("*.pdf") if f.is_file())
    known_revisions = {
        row[0] for row in conn.execute("SELECT revision_id FROM document_revisions").fetchall()
    }
    receipt: dict = {
        "materialized_at": now_iso(),
        "corpus": str(corpus.resolve()),
        "backup": backup_path,
        "schema_version": repo.schema_version,
        "documents": [],
        "unmatched_on_disk": [],
        "documents_missing_from_disk": [],
        "quarantine": {},
        "metadata_census": {},
        "role_census": {},
    }

    seen_revisions: set[str] = set()
    for pdf in pdfs:
        inv = ic.inventory_file(pdf)
        if inv["sha256"] not in known_revisions:
            # Disk drifted from the store (new/changed file): report, never
            # silently register inside a metadata pass.
            receipt["unmatched_on_disk"].append(str(pdf.relative_to(corpus)))
            receipt["documents"].append(
                {"path": str(pdf.relative_to(corpus)), "status": "NOT_IN_STORE"}
            )
            continue
        seen_revisions.add(inv["sha256"])
        entry = _materialize_document(repo, corpus, pdf, inv)
        entry["status"] = "MATERIALIZED"
        entry["sections"] = inv.get("section_rows", [])
        receipt["documents"].append(entry)

    # Store revisions not seen on disk (private corpus moved?) — explicit.
    for (rid,) in conn.execute(
        "SELECT revision_id FROM document_revisions WHERE binding_effect != 'regulatory'"
    ).fetchall():
        if rid not in seen_revisions:
            logical = conn.execute(
                "SELECT logical_id FROM document_revisions WHERE revision_id = ?", (rid,)
            ).fetchone()[0]
            receipt["documents_missing_from_disk"].append(logical)

    receipt["quarantine"] = _quarantine(repo, conn)
    receipt["metadata_census"] = _metadata_census(receipt["documents"], len(pdfs))
    receipt["role_census"] = _role_census(receipt["documents"])
    return receipt


def _quarantine(repo: Repository, conn) -> dict:
    """P4 exit: no Cartesian assertion may survive in established trace or
    deterministic impact. The v3 folder pass produced IMPLEMENTS proposals
    (node x document per standard folder) and placeholder org-graph edges —
    both are marked discovery-only."""
    tagged_cartesian = repo.tag_relationship_derivation(
        DERIVATION_FOLDER_CARTESIAN,
        from_rationale=V3_CANDIDATE_RATIONALE,
        relation_types=("IMPLEMENTS",),
    )
    tagged_placeholder = repo.tag_relationship_derivation(
        DERIVATION_FOLDER_ORG_PLACEHOLDER,
        relation_types=_PLACEHOLDER_ORG_EDGES,
    )
    return {
        "folder_cartesian": tagged_cartesian,
        "folder_placeholder_org": tagged_placeholder,
        "remaining_untagged_proposed": conn.execute(
            "SELECT count(*) FROM relationship_assertions WHERE status='proposed' AND derivation=''"
        ).fetchone()[0],
    }


def _metadata_census(documents: list[dict], on_disk: int) -> dict:
    materialized = [d for d in documents if d.get("status") == "MATERIALIZED"]
    return {
        "documents_on_disk": on_disk,
        "documents_materialized": len(materialized),
        "with_effective_date": sum(1 for d in materialized if d["control"]["effective_date"]),
        "with_version": sum(1 for d in materialized if d["control"]["version"]),
        "with_document_number": sum(1 for d in materialized if d["control"]["document_number"]),
        "with_owner": sum(1 for d in materialized if d["control"]["owner"]),
        "with_approval_date": sum(1 for d in materialized if d["control"]["approval_date"]),
        "with_last_reviewed_date": sum(
            1 for d in materialized if d["control"]["last_reviewed_date"]
        ),
    }


def _role_census(documents: list[dict]) -> dict[str, int]:
    census: dict[str, int] = {}
    for d in documents:
        for s in d.get("sections", []):
            census[s["role"]] = census.get(s["role"], 0) + 1
    return dict(sorted(census.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="skip the pre-run snapshot (testing only)",
    )
    args = parser.parse_args(argv)
    receipt = materialize(args.corpus.resolve(), backup=not args.no_backup)
    payload = json.dumps(receipt, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_receipt = RECEIPT_ROOT / stamp / "inventory.json"
    default_receipt.parent.mkdir(parents=True, exist_ok=True)
    default_receipt.write_text(payload + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "metadata_census": receipt["metadata_census"],
                "role_census": receipt["role_census"],
                "quarantine": receipt["quarantine"],
                "unmatched_on_disk": receipt["unmatched_on_disk"],
                "receipt": str(default_receipt),
            },
            indent=2,
        )
    )
    return 1 if receipt["unmatched_on_disk"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
