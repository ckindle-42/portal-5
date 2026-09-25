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


def _projectable_sections_in_store(repo: Any, jurisdiction: str) -> int:
    """Sections the store holds for one jurisdiction that a projection SHOULD
    hold: anchored into a capture (``char_start >= 0``). Pre-capture rows carry
    ``char_start = -1`` — a second extraction of bytes the capture already
    covers, never part of the eligible population (``section_index.build_plan``
    classifies them superseded, not eligible) — so they do not count as
    something the index is missing."""
    return int(
        repo._conn.execute(
            """SELECT COUNT(*) FROM source_sections s
             JOIN document_revisions r ON r.revision_id = s.revision_id
             JOIN source_documents d ON d.logical_id = r.logical_id
            WHERE d.jurisdiction = ? AND s.char_start >= 0""",
            (jurisdiction,),
        ).fetchone()[0]
    )


def retrieval_projection_status(repo: Any) -> dict[str, Any]:
    """FRESH / STALE / UNPROJECTED / ABSENT per corpus, against the SECTION
    POPULATION each is a projection of (BILATERAL_CORPUS_V1 P4.5).

    :func:`canonical_fingerprint` hashes ``section_id || role``, which does not
    move when a section's span does — so a re-capture that shifted a boundary
    left the manifest reading FRESH over an index that no longer matched the
    store. The retrieval manifest is fingerprinted against each section's
    identity, span and revision instead, so STALE means what it says.

    Per corpus, because the corpora are projected independently: one store-wide
    hash would mark the regulatory index stale the moment somebody writes an
    operator note, which is false and teaches people to ignore the signal. The
    overall status is the worst of them.

    **The manifest alone cannot see an unprojected corpus** (LOAD_AND_CONVERSE_V1
    P1.2): "nothing to project is a state, not a drift" is true of an empty
    corpus and false of one whose sections sit in the store while the index holds
    none — to a manifest-only check those are indistinguishable, and GS passed
    across exactly that hole. Each entry therefore carries the store's own
    projectable section count, and a corpus with sections in the store and no
    recorded generation reads ``UNPROJECTED`` — a failure, never an absence.
    """
    from portal.modules.compliance.core.section_index import (
        CORPUS_FOR_JURISDICTION,
        section_population_fingerprint,
    )

    row = repo._conn.execute(
        """SELECT generation_id, created_at, counts_json FROM index_manifests
           WHERE index_kind = 'retrieval' AND active = 1
           ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()
    built: dict[str, Any] = {}
    if row is not None:
        built = json.loads(row[2] or "{}").get("corpora", {})
    corpora: dict[str, Any] = {}
    for jurisdiction, kb_id in CORPUS_FOR_JURISDICTION.items():
        live = section_population_fingerprint(repo, jurisdiction)
        recorded = str((built.get(kb_id) or {}).get("fingerprint", ""))
        in_store = _projectable_sections_in_store(repo, jurisdiction)
        if not recorded:
            status = "UNPROJECTED" if in_store else "ABSENT"
        else:
            status = "FRESH" if recorded == live else "STALE"
        corpora[kb_id] = {
            "status": status,
            "live_fingerprint": live,
            "built_from_fingerprint": recorded,
            "sections": (built.get(kb_id) or {}).get("sections"),
            "sections_in_store": in_store,
        }
    # an empty corpus is not a stale one: nothing to project is a state, not a
    # drift. An UNPROJECTED corpus is neither — it is the failure the gate exists
    # to catch, and it is never excluded.
    interesting = [
        entry["status"]
        for entry in corpora.values()
        if entry["status"] != "ABSENT" or entry["sections_in_store"]
    ]
    overall = (
        "UNPROJECTED"
        if "UNPROJECTED" in interesting
        else ("STALE" if "STALE" in interesting else ("FRESH" if interesting else "ABSENT"))
    )
    if row is None:
        return {"index_kind": "retrieval", "status": overall, "corpora": corpora}
    return {
        "index_kind": "retrieval",
        "status": overall,
        "generation_id": row[0],
        "built_at": row[1],
        "corpora": corpora,
    }


def census(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts over the fingerprinted truth tables — the cheap sanity
    half of a materialization proof."""
    return {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table, _ in _FINGERPRINT_TABLES
    }
