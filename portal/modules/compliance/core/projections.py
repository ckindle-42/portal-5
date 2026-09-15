"""Canonical fingerprints and projection manifests (END_TO_END Phase 5 / P6).

The canonical transactional store is the source of truth; graph, lexical and
vector systems are reproducible projections. This module makes that
relationship checkable:

* :func:`canonical_fingerprint` — one deterministic hash over the canonical
  truth tables (revisions, nodes, effectivity, decompositions, sections,
  governed relationship rows). The same store always fingerprints the same;
  any recorded change (a new revision, a corrected effectivity, a new
  derived row) changes the hash.
* :func:`record_index_manifest` — a projection generation is recorded with
  the canonical fingerprint it was built from (``index_manifests``).
* :func:`projection_status` — FRESH / STALE / ABSENT for a projection kind,
  by comparing the active manifest's fingerprint to the store's current one.
  A stale dependent annotation is detectable, never silently consumed
  (lesson L14).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from portal.modules.compliance.core.temporal import now_iso

#: canonical tables that define the store's truth fingerprint, with the
#: columns that make a row's identity and meaning.
_FINGERPRINT_TABLES: tuple[tuple[str, str], ...] = (
    (
        "document_revisions",
        "revision_id || ':' || binding_effect || ':' || COALESCE(recorded_from, '')",
    ),
    ("standard_revisions", "revision_id || ':' || family || ':' || version"),
    ("requirement_nodes", "node_id || ':' || COALESCE(logical_lineage_id, '')"),
    ("obligation_atoms", "atom_id || ':' || node_id"),
    ("obligation_expressions", "expression_id || ':' || node_id"),
    ("obligation_dependencies", "dependency_id"),
    ("obligation_concepts", "concept_id"),
    (
        "effectivity_assertions",
        "assertion_id || ':' || COALESCE(valid_from, '') || ':' || COALESCE(valid_to, '') || ':' || COALESCE(recorded_to, '')",
    ),
    ("source_sections", "section_id || ':' || role"),
    ("internal_controls", "control_id || ':' || revision_id"),
)


def canonical_fingerprint(repo: Any) -> str:
    """sha256 over the ordered identity columns of the canonical truth
    tables. Deterministic for the same store state; stable across processes."""
    conn = repo._conn
    digest = hashlib.sha256()
    for table, row_expr in _FINGERPRINT_TABLES:
        digest.update(f"#{table}".encode())
        rows = conn.execute(f"SELECT {row_expr} FROM {table} ORDER BY 1").fetchall()
        digest.update(json.dumps([r[0] for r in rows], separators=(",", ":")).encode())
    return digest.hexdigest()


def record_index_manifest(
    repo: Any,
    *,
    index_kind: str,
    generation_id: str,
    canonical_fingerprint_value: str,
    counts: dict[str, Any] | None = None,
    active: bool = True,
) -> str:
    """Record one projection generation with the canonical fingerprint it was
    built from, marking it active (and deactivating prior generations of the
    same kind)."""
    conn = repo._conn
    with repo._lock, conn:
        if active:
            conn.execute(
                "UPDATE index_manifests SET active = 0 WHERE index_kind = ?", (index_kind,)
            )
        conn.execute(
            """INSERT INTO index_manifests(generation_id, index_kind, created_at,
                   active, counts_json, org_id)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(generation_id) DO UPDATE SET
                   active = excluded.active,
                   counts_json = excluded.counts_json""",
            (
                generation_id,
                index_kind,
                now_iso(),
                1 if active else 0,
                json.dumps(
                    {"canonical_fingerprint": canonical_fingerprint_value, **(counts or {})}
                ),
                "default",
            ),
        )
    return generation_id


def projection_status(
    repo: Any, index_kind: str, current_fingerprint: str | None = None
) -> dict[str, Any]:
    """FRESH / STALE / ABSENT for one projection kind against the store's
    current canonical fingerprint."""
    fp = current_fingerprint or canonical_fingerprint(repo)
    row = repo._conn.execute(
        """SELECT generation_id, created_at, counts_json FROM index_manifests
           WHERE index_kind = ? AND active = 1
           ORDER BY created_at DESC LIMIT 1""",
        (index_kind,),
    ).fetchone()
    if row is None:
        return {"index_kind": index_kind, "status": "ABSENT", "canonical_fingerprint": fp}
    counts = json.loads(row[2] or "{}")
    built_fp = counts.get("canonical_fingerprint", "")
    return {
        "index_kind": index_kind,
        "status": "FRESH" if built_fp == fp else "STALE",
        "generation_id": row[0],
        "built_at": row[1],
        "built_from_fingerprint": built_fp,
        "canonical_fingerprint": fp,
    }


def census(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts over the fingerprinted truth tables — the cheap sanity
    half of a materialization proof."""
    return {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table, _ in _FINGERPRINT_TABLES
    }
