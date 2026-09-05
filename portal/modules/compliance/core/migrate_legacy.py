"""Import the pre-P2 JSON/LanceDB stores into the canonical repository (P2).

Snapshots the source files' counts/hashes WITHOUT mutating them, then imports:

1. The bitemporal register (``cip_register.Register``) as source-linked legacy
   extraction — each standard becomes a ``standard_revisions``/
   ``requirement_nodes`` row, each node's stored dates become an
   ``effectivity_assertions`` row with ``approval_status='unverified'`` (P2
   requirement 2: "Import unsupported effectivity/authority assertions as
   unverified until P3 reconciliation").
2. The mapping store (``mapping_store.MappingStore``) as ``relationship_
   assertions`` — an approved legacy mapping imports with
   ``review_state='imported_legacy_unverified'`` and ``decided_by`` prefixed
   ``legacy:`` (requirement 3: "Preserve historical reviewer names/dates as
   imported records; do not promote them to authenticated decisions").
3. Real document bytes under an operator corpus directory, when given, as
   immutable ``document_revisions`` (requirement 4). Unknown document-control
   dates stay ``None`` — never guessed from a filename.

All three are independently idempotent: re-running with the same source data
produces zero additional rows (repeat-run idempotence, P2 exit criterion).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from portal.modules.compliance.core.models import (
    RelationshipAssertion,
    SourceDocument,
)
from portal.modules.compliance.core.provenance import content_hash
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal import now_iso


def _register_fingerprint(register) -> dict[str, object]:
    return {
        "n_nodes": len(register.nodes),
        "n_edges": len(register.edges),
        "content_sha256": hashlib.sha256(
            json.dumps(register.to_json(), sort_keys=True, default=str).encode()
        ).hexdigest(),
    }


def _mapping_store_fingerprint(store) -> dict[str, object]:
    rows = [m.__dict__ for m in store._rows]  # noqa: SLF001 - snapshot only, never mutated
    return {
        "n_mappings": len(rows),
        "content_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }


def snapshot_legacy_sources(
    repo: Repository,
    *,
    register=None,
    mapping_store=None,
    sidecar: dict[str, object] | None = None,
) -> object:
    """Requirement 1: record counts/hashes of the JSON sources BEFORE
    importing, without mutating them. Returns the catalog snapshot."""
    counts: dict = {}
    hashes: dict = {}
    if register is not None:
        fp = _register_fingerprint(register)
        counts["register_nodes"] = fp["n_nodes"]
        counts["register_edges"] = fp["n_edges"]
        hashes["register"] = fp["content_sha256"]
    if mapping_store is not None:
        fp = _mapping_store_fingerprint(mapping_store)
        counts["mappings"] = fp["n_mappings"]
        hashes["mapping_store"] = fp["content_sha256"]
    if sidecar is not None:
        counts["sidecar_documents"] = len(sidecar)
        hashes["sidecar"] = hashlib.sha256(json.dumps(sidecar, sort_keys=True).encode()).hexdigest()
    return repo.record_catalog_snapshot(counts, hashes)


def import_register(repo: Repository, register, *, dry_run: bool = False) -> dict[str, object]:
    """Requirement 2. Every node's stored dates import as an UNVERIFIED
    effectivity assertion — the P1 fix already stopped treating an unknown
    date as effective; this migration does not silently upgrade a legacy
    date to "verified" either."""
    conn = repo._conn  # noqa: SLF001 - migration owns direct access, same module family
    standards_seen: set[str] = set()
    n_standards = n_nodes = n_effectivity = 0
    with repo._lock, conn:  # noqa: SLF001 - `with conn:` commits/rolls back the whole batch
        for node in register.nodes:
            if node.standard not in standards_seen:
                standards_seen.add(node.standard)
                if not dry_run:
                    conn.execute(
                        "INSERT OR IGNORE INTO standard_revisions(revision_id, logical_id, family, version, org_id) "
                        "VALUES (?,?,?,?, 'default')",
                        (
                            node.standard,
                            node.standard.rsplit("-", 1)[0],
                            node.standard.rsplit("-", 1)[0],
                            node.version,
                        ),
                    )
                n_standards += 1
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_nodes(node_id, standard_revision_id, requirement, "
                    "part, logical_lineage_id, org_id) VALUES (?,?,?,?,?, 'default')",
                    (node.id, node.standard, node.requirement, node.part, ""),
                )
                exists = conn.execute(
                    "SELECT 1 FROM effectivity_assertions WHERE node_id = ? AND source_anchor_id = 'legacy_register'",
                    (node.id,),
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO effectivity_assertions(assertion_id, node_id, jurisdiction, valid_from, "
                        "valid_to, recorded_from, recorded_to, source_anchor_id, approval_status, org_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?, 'default')",
                        (
                            f"legacy:{node.id}",
                            node.id,
                            "US",
                            node.valid_from,
                            node.valid_to,
                            now_iso(),
                            None,
                            "legacy_register",
                            "unverified",
                        ),
                    )
                    n_effectivity += 1
            n_nodes += 1
    return {
        "dry_run": dry_run,
        "standards_imported": n_standards,
        "requirement_nodes_imported": n_nodes,
        "effectivity_assertions_imported": n_effectivity,
    }


def import_mapping_store(
    repo: Repository, mapping_store, *, dry_run: bool = False
) -> dict[str, object]:
    """Requirement 3. An approved legacy mapping becomes an ``approved``
    relationship_assertion whose ``review_state`` names it
    ``imported_legacy_unverified`` — it is authoritative for legacy-compat
    reads, but was never an authenticated P7 decision and must not be
    displayed as one. A rejected/unapproved (proposed) mapping stays
    ``proposed``. Idempotent: keyed on the legacy mapping's own ``id``."""
    n_imported = n_skipped = 0
    for m in mapping_store._rows:  # noqa: SLF001 - read-only snapshot of the legacy store
        legacy_key = f"legacy:{m.id}"
        existing = repo.get_relationship(legacy_key)
        if existing is not None:
            n_skipped += 1
            continue
        n_imported += 1
        if dry_run:
            continue
        rel = RelationshipAssertion(
            assertion_id=legacy_key,
            relation_type=m.relationship.upper() if m.relationship else "REFERENCES",
            src_ref=m.requirement_id,
            src_revision_id=None,
            dst_ref=f"{m.internal_document_id} {m.section_id}",
            dst_revision_id=None,
            scope="",
            citations=[],
            status="approved" if m.is_approved else "proposed",
            review_state="imported_legacy_unverified" if m.is_approved else "proposed",
            valid_from=m.valid_from,
            valid_to=m.valid_to,
            recorded_from=now_iso(),
            rationale=f"imported from legacy mapping_store.json (coverage={m.coverage})",
            decided_by=f"legacy:{m.approved_by}" if m.approved_by else "",
            decided_at=m.approved_date or None,
        )
        repo.propose_relationship(rel)
    return {"dry_run": dry_run, "imported": n_imported, "already_imported": n_skipped}


def import_document_directory(
    repo: Repository, source_dir: str | Path, *, dry_run: bool = False
) -> dict:
    """Requirement 4. Real bytes under ``source_dir`` become immutable
    document revisions keyed by content hash. ``logical_id`` is the
    source-dir-relative path — stable, human-readable, and portable across a
    corpus move — while ``alias_path`` is stored as the real resolved
    absolute path, because that is what a LIVE integrity check
    (``compliance_sources``: does the file on disk still match this
    revision's hash?) must be able to open regardless of the caller's
    current working directory. A relative alias_path silently made every
    live drift check report "unverifiable" no matter what (found live during
    P8-L verification against the real LSPG-CIP corpus). No filename-date
    guessing: every date field stays ``None``, queued for review by a later
    phase, not invented here."""
    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        return {"error": f"not a directory: {src}", "imported": 0}
    files = sorted(f for f in src.rglob("*.pdf") if f.is_file())
    n_new = n_existing = 0
    hashes: dict[str, str] = {}
    for f in files:
        rel_path = str(f.relative_to(src))
        abs_path = str(f)
        data = f.read_bytes()
        h = content_hash(data)
        hashes[rel_path] = h
        if dry_run:
            continue
        prior = repo.revisions_for_alias(abs_path)
        repo.upsert_source_document(
            SourceDocument(
                logical_id=rel_path, title=f.stem, issuer="", source_kind="unknown", jurisdiction=""
            )
        )
        rev = repo.add_document_revision(rel_path, abs_path, data)
        if any(r.revision_id == rev.revision_id for r in prior):
            n_existing += 1
        else:
            n_new += 1
    return {
        "dry_run": dry_run,
        "files_seen": len(files),
        "new_revisions": n_new,
        "already_current": n_existing,
        "content_hashes": hashes,
    }
