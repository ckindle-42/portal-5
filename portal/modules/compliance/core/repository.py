"""The canonical compliance repository (P2).

SQLite on a local persistent private volume — the design's explicit default
for this single-application-host deployment (`config/backends.yaml`/CLAUDE.md:
"No new graph server or model infrastructure is required"). Foreign keys are
enabled per connection (SQLite does not persist that pragma), WAL mode is
set once at the file, and every WRITE goes through one process-local lock so
concurrent callers serialize instead of hitting `SQLITE_BUSY` — the documented
SQLite WAL/foreign-key constraints this design cites, not a workaround for a
graph server we chose not to build.

Reads default to the EFFECTIVE surface (`status='approved'`); a caller that
wants proposals/rejections must say so explicitly via `statuses=`. Every
query is parameterized — no interpolated identifiers or values.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
from collections import deque
from dataclasses import asdict
from pathlib import Path

from portal.modules.compliance.core.migrations import apply_migrations, get_schema_version
from portal.modules.compliance.core.models import (
    CatalogSnapshot,
    DocumentRevision,
    OutboxEvent,
    RelationshipAssertion,
    ReviewEvent,
    SourceDocument,
    SourceSection,
)
from portal.modules.compliance.core.provenance import content_hash
from portal.modules.compliance.core.temporal import now_iso

_DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_PATH = Path(os.environ.get("COMPLIANCE_DB_PATH", _DATA / "compliance_store.db"))


class ConcurrencyError(RuntimeError):
    """A decision targeted a stale ``expected_version`` — the row moved under
    it. The caller must re-read and retry; this is never silently resolved
    by "last write wins" (P7/A25)."""


class BrokenReferenceError(RuntimeError):
    """A relationship endpoint (or any foreign key) does not resolve — SQLite
    foreign-key enforcement raising through, given an explicit name so a
    caller can distinguish it from a generic integrity error."""


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class Repository:
    """One repository instance per process is the intended usage — the write
    lock is process-local, matching the "single application host" default
    this design commits to (multi-host concurrent writers require Postgres
    through this same interface, per the design doc; not implemented here
    since no multi-host deployment was discovered in this environment)."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._connect()
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        self._conn.close()

    # ── migrations ───────────────────────────────────────────────────────
    def migrate(self) -> dict:
        with self._lock:
            return apply_migrations(self._conn)

    @property
    def schema_version(self) -> int:
        return get_schema_version(self._conn)

    # ── backup / restore (P2 exit: "backup/restore") ────────────────────
    def backup_to(self, dest: Path | str) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            # sqlite3's own backup API copies a live, WAL-mode DB safely —
            # never a raw file copy, which can grab a torn WAL state.
            dest_conn = sqlite3.connect(str(dest))
            with dest_conn:
                self._conn.backup(dest_conn)
            dest_conn.close()
        return dest

    @classmethod
    def restore_from(cls, backup_path: Path | str, dest_path: Path | str) -> Repository:
        dest_path = Path(dest_path)
        shutil.copyfile(Path(backup_path), dest_path)
        return cls(dest_path)

    # ── source documents / revisions ────────────────────────────────────
    def upsert_source_document(self, doc: SourceDocument) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO source_documents(logical_id, title, issuer, source_kind,
                       jurisdiction, org_id)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(logical_id) DO UPDATE SET
                       title=excluded.title, issuer=excluded.issuer,
                       source_kind=excluded.source_kind, jurisdiction=excluded.jurisdiction""",
                (
                    doc.logical_id,
                    doc.title,
                    doc.issuer,
                    doc.source_kind,
                    doc.jurisdiction,
                    doc.org_id,
                ),
            )

    def add_document_revision(
        self,
        logical_id: str,
        alias_path: str,
        content: bytes,
        *,
        binding_effect: str = "unknown",
        **dates,
    ) -> DocumentRevision:
        """Idempotent on identical bytes (same ``revision_id`` — content
        hash — is a no-op re-insert); replacement bytes at the SAME
        ``alias_path`` create a NEW revision. Historical anchors into the
        prior revision still resolve because revisions are never deleted or
        mutated."""
        revision_id = content_hash(content)
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT revision_id FROM document_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if existing:
                rev = self._get_revision_unlocked(revision_id)
                if rev is None:  # pragma: no cover - defensive, row just confirmed to exist
                    raise RuntimeError(f"revision {revision_id} vanished mid-transaction")
                return rev
            rev = DocumentRevision(
                revision_id=revision_id,
                logical_id=logical_id,
                alias_path=alias_path,
                binding_effect=binding_effect,
                retrieved_at=now_iso(),
                recorded_from=now_iso(),
                authored_date=dates.get("authored_date"),
                approved_date=dates.get("approved_date"),
                effective_date=dates.get("effective_date"),
                last_reviewed_date=dates.get("last_reviewed_date"),
            )
            self._conn.execute(
                """INSERT INTO document_revisions(revision_id, logical_id, alias_path,
                       binding_effect, authored_date, approved_date, effective_date,
                       last_reviewed_date, retrieved_at, org_id, recorded_from, recorded_to)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (
                    rev.revision_id,
                    rev.logical_id,
                    rev.alias_path,
                    rev.binding_effect,
                    rev.authored_date,
                    rev.approved_date,
                    rev.effective_date,
                    rev.last_reviewed_date,
                    rev.retrieved_at,
                    rev.org_id,
                    rev.recorded_from,
                ),
            )
            self._write_outbox_unlocked("document_revision_added", {"revision_id": revision_id})
            return rev

    def get_revision(self, revision_id: str) -> DocumentRevision | None:
        with self._lock:
            return self._get_revision_unlocked(revision_id)

    def _get_revision_unlocked(self, revision_id: str) -> DocumentRevision | None:
        row = self._conn.execute(
            "SELECT * FROM document_revisions WHERE revision_id = ?", (revision_id,)
        ).fetchone()
        return DocumentRevision(**dict(row)) if row else None

    def revisions_for_alias(self, alias_path: str) -> list[DocumentRevision]:
        """Every revision ever ingested at this alias path, oldest first —
        a same-path replacement never erases the prior revision's history."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM document_revisions WHERE alias_path = ? ORDER BY retrieved_at",
                (alias_path,),
            ).fetchall()
            return [DocumentRevision(**dict(r)) for r in rows]

    def revisions_for_logical_id(self, logical_id: str) -> list[DocumentRevision]:
        """Every revision under this stable logical id, oldest first — the
        human-facing identity (e.g. a source-dir-relative path), distinct
        from ``alias_path`` which is stored as a real resolvable filesystem
        path for live integrity checking."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM document_revisions WHERE logical_id = ? ORDER BY retrieved_at",
                (logical_id,),
            ).fetchall()
            return [DocumentRevision(**dict(r)) for r in rows]

    def add_source_section(self, section: SourceSection) -> None:
        with self._lock, self._conn:
            if not self._conn.execute(
                "SELECT 1 FROM document_revisions WHERE revision_id = ?", (section.revision_id,)
            ).fetchone():
                raise BrokenReferenceError(
                    f"source_sections.revision_id {section.revision_id!r} does not resolve"
                )
            self._conn.execute(
                """INSERT INTO source_sections(section_id, revision_id, path, page_start,
                       page_end, table_ref, extractor, extractor_version, org_id)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(section_id) DO NOTHING""",
                (
                    section.section_id,
                    section.revision_id,
                    section.path,
                    section.page_start,
                    section.page_end,
                    section.table_ref,
                    section.extractor,
                    section.extractor_version,
                    section.org_id,
                ),
            )

    # ── relationship assertions: proposal vs effective ──────────────────
    def propose_relationship(self, rel: RelationshipAssertion) -> RelationshipAssertion:
        rel.assertion_id = rel.assertion_id or _new_id()
        rel.recorded_from = rel.recorded_from or now_iso()
        with self._lock, self._conn:
            for ref, rev_id in (
                (rel.src_ref, rel.src_revision_id),
                (rel.dst_ref, rel.dst_revision_id),
            ):
                if (
                    rev_id
                    and not self._conn.execute(
                        "SELECT 1 FROM document_revisions WHERE revision_id = ?", (rev_id,)
                    ).fetchone()
                ):
                    raise BrokenReferenceError(
                        f"relationship endpoint {ref!r} -> {rev_id!r} does not resolve"
                    )
            self._conn.execute(
                """INSERT INTO relationship_assertions(assertion_id, relation_type, src_ref,
                       src_revision_id, dst_ref, dst_revision_id, scope, citations_json, status,
                       review_state, valid_from, valid_to, recorded_from, recorded_to, rationale,
                       decided_by, decided_at, version, org_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rel.assertion_id,
                    rel.relation_type,
                    rel.src_ref,
                    rel.src_revision_id,
                    rel.dst_ref,
                    rel.dst_revision_id,
                    rel.scope,
                    json.dumps(rel.citations),
                    rel.status,
                    rel.review_state,
                    rel.valid_from,
                    rel.valid_to,
                    rel.recorded_from,
                    rel.recorded_to,
                    rel.rationale,
                    rel.decided_by,
                    rel.decided_at,
                    rel.version,
                    rel.org_id,
                ),
            )
            self._write_outbox_unlocked("relationship_proposed", {"assertion_id": rel.assertion_id})
        return rel

    def _row_to_relationship(self, row: sqlite3.Row) -> RelationshipAssertion:
        d = dict(row)
        d["citations"] = json.loads(d.pop("citations_json"))
        return RelationshipAssertion(**d)

    def get_relationship(self, assertion_id: str) -> RelationshipAssertion | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM relationship_assertions WHERE assertion_id = ?", (assertion_id,)
            ).fetchone()
            return self._row_to_relationship(row) if row else None

    def list_relationship_assertions(
        self, *, ref: str | None = None, statuses: tuple[str, ...] = ("approved",)
    ) -> list[RelationshipAssertion]:
        """Governed reads default to ``statuses=("approved",)`` — a caller
        must explicitly widen this to see proposals/rejections (design §4:
        "Normal governed reads must be unable to include proposed/rejected
        rows by forgetting a status filter")."""
        placeholders = ",".join("?" for _ in statuses)
        sql = f"SELECT * FROM relationship_assertions WHERE status IN ({placeholders})"
        params: list = list(statuses)
        if ref is not None:
            sql += " AND (src_ref = ? OR dst_ref = ?)"
            params += [ref, ref]
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_relationship(r) for r in rows]

    def decide_relationship(
        self,
        assertion_id: str,
        decision: str,
        decided_by: str,
        *,
        expected_version: int,
        rationale: str = "",
        evidence: list[dict] | None = None,
        corrected_coverage: str | None = None,
    ) -> RelationshipAssertion:
        """Atomically apply a review decision: update the assertion, record
        the review event, and write an invalidation outbox entry — all in one
        transaction. A stale ``expected_version`` raises ``ConcurrencyError``
        rather than silently overwriting a concurrent decision (P7/A25)."""
        if decision not in ("CONFIRMED", "CORRECTED", "REJECTED", "REVOKED"):
            raise ValueError(f"unknown decision: {decision!r}")
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM relationship_assertions WHERE assertion_id = ?", (assertion_id,)
            ).fetchone()
            if row is None:
                raise KeyError(assertion_id)
            current = self._row_to_relationship(row)
            if current.version != expected_version:
                raise ConcurrencyError(
                    f"assertion {assertion_id} is at version {current.version}, "
                    f"expected {expected_version} — re-read and retry"
                )
            new_status = {
                "CONFIRMED": "approved",
                "CORRECTED": corrected_coverage or current.status,
                "REJECTED": "rejected",
                "REVOKED": "revoked",
            }[decision]
            now = now_iso()
            cur = self._conn.execute(
                """UPDATE relationship_assertions
                   SET status = ?, review_state = ?, decided_by = ?, decided_at = ?, version = version + 1
                   WHERE assertion_id = ? AND version = ?""",
                (new_status, decision, decided_by, now, assertion_id, expected_version),
            )
            if cur.rowcount == 0:
                # the version-scoped WHERE matched nothing: someone else's
                # decision landed between our read and this write.
                raise ConcurrencyError(f"concurrent write to {assertion_id} lost the race")
            event = ReviewEvent(
                event_id=_new_id(),
                target_type="relationship_assertion",
                target_id=assertion_id,
                expected_version=expected_version,
                decision=decision,
                decided_by=decided_by,
                rationale=rationale,
                evidence=evidence or [],
                created_at=now,
            )
            self._conn.execute(
                """INSERT INTO review_events(event_id, target_type, target_id, expected_version,
                       decision, decided_by, rationale, evidence_json, created_at, prior_event_id, org_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.event_id,
                    event.target_type,
                    event.target_id,
                    event.expected_version,
                    event.decision,
                    event.decided_by,
                    event.rationale,
                    json.dumps(event.evidence),
                    event.created_at,
                    event.prior_event_id,
                    event.org_id,
                ),
            )
            self._write_outbox_unlocked(
                "relationship_decided", {"assertion_id": assertion_id, "decision": decision}
            )
            return self._row_to_relationship(
                self._conn.execute(
                    "SELECT * FROM relationship_assertions WHERE assertion_id = ?", (assertion_id,)
                ).fetchone()
            )

    # ── bidirectional traversal (P4) ────────────────────────────────────
    def traverse_relationships(
        self,
        start_ref: str,
        *,
        direction: str = "both",
        statuses: tuple[str, ...] = ("approved",),
        max_depth: int = 3,
        max_edges: int = 500,
    ) -> dict:
        """Forward/reverse/both-direction traversal from ``start_ref``,
        cycle-safe (each node expands at most once) and bounded by both
        ``max_depth`` and a ``max_edges`` work budget. Returns typed edges
        with status/citations/validity, plus ``depth_limited_nodes`` and
        ``unexplored_frontier`` — a truncated or depth-capped traversal is
        disclosed explicitly, never silently presented as complete (design
        §4: "detect cycles, bound depth/work, and disclose unexplored
        frontiers"). ``statuses`` defaults to the governed (approved-only)
        surface, same as ``list_relationship_assertions``."""
        if direction not in ("forward", "reverse", "both"):
            raise ValueError(f"direction must be forward/reverse/both, got {direction!r}")
        visited = {start_ref}
        seen_assertions: set[str] = set()
        frontier: deque[tuple[str, int]] = deque([(start_ref, 0)])
        edges_out: list[dict] = []
        depth_limited: set[str] = set()
        truncated = False

        while frontier:
            ref, depth = frontier.popleft()
            if depth >= max_depth:
                depth_limited.add(ref)
                continue
            for rel in self.list_relationship_assertions(ref=ref, statuses=statuses):
                if len(edges_out) >= max_edges:
                    truncated = True
                    break
                if direction in ("forward", "both") and rel.src_ref == ref:
                    other, edge_direction = rel.dst_ref, "forward"
                elif direction in ("reverse", "both") and rel.dst_ref == ref:
                    other, edge_direction = rel.src_ref, "reverse"
                else:
                    continue
                if rel.assertion_id in seen_assertions:
                    # a "both"-direction BFS reaches the SAME edge again from
                    # its other endpoint (e.g. after visiting POL §1, REQ-1's
                    # edge to it looks like a "reverse" discovery from POL
                    # §1's side) — that is not new information, so it does
                    # not count against the edge/work budget either.
                    if other not in visited:
                        visited.add(other)
                        frontier.append((other, depth + 1))
                    continue
                seen_assertions.add(rel.assertion_id)
                edges_out.append(
                    {
                        "assertion_id": rel.assertion_id,
                        "relation_type": rel.relation_type,
                        "direction": edge_direction,
                        "from": ref,
                        "to": other,
                        "status": rel.status,
                        "citations": rel.citations,
                        "valid_from": rel.valid_from,
                        "valid_to": rel.valid_to,
                        "decided_at": rel.decided_at,
                    }
                )
                if other not in visited:
                    visited.add(other)
                    frontier.append((other, depth + 1))
            if truncated:
                break

        return {
            "start_ref": start_ref,
            "direction": direction,
            "max_depth": max_depth,
            "nodes_visited": sorted(visited),
            "edges": edges_out,
            "n_edges": len(edges_out),
            "truncated": truncated,
            "depth_limited_nodes": sorted(depth_limited),
            "unexplored_frontier": sorted({r for r, _ in frontier}) if truncated else [],
        }

    # ── as-known replay (recorded-time history) ─────────────────────────
    def status_as_known(self, assertion_id: str, known_at: str) -> str:
        """Reconstruct the assertion's status as it would have read AT
        ``known_at`` (recorded time), from the append-only ``review_events``
        log — never from the current mutated row, which only holds the
        latest state. "The system's recorded history is not proof of what an
        employee knew at that time" (design §5.1); this replays what the
        SYSTEM recorded as of that timestamp, starting from ``proposed``
        before any decision existed."""
        with self._lock:
            events = self._conn.execute(
                """SELECT decision, created_at FROM review_events
                   WHERE target_type = 'relationship_assertion' AND target_id = ?
                     AND created_at <= ?
                   ORDER BY created_at ASC, rowid ASC""",
                (assertion_id, known_at),
            ).fetchall()
        status = "proposed"
        for e in events:
            status = {
                "CONFIRMED": "approved",
                "CORRECTED": status,
                "REJECTED": "rejected",
                "REVOKED": "revoked",
            }[e["decision"]]
        return status

    # ── outbox ───────────────────────────────────────────────────────────
    def _write_outbox_unlocked(self, event_type: str, payload: dict) -> None:
        self._conn.execute(
            "INSERT INTO outbox_events(event_type, payload_json, created_at) VALUES (?,?,?)",
            (event_type, json.dumps(payload), now_iso()),
        )

    def drain_outbox(self, limit: int = 100) -> list[OutboxEvent]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM outbox_events WHERE published_at IS NULL ORDER BY event_id LIMIT ?",
                (limit,),
            ).fetchall()
            events = [
                OutboxEvent(
                    event_id=r["event_id"],
                    event_type=r["event_type"],
                    payload=json.loads(r["payload_json"]),
                    created_at=r["created_at"],
                    published_at=r["published_at"],
                )
                for r in rows
            ]
            if events:
                now = now_iso()
                ids = [e.event_id for e in events]
                self._conn.executemany(
                    "UPDATE outbox_events SET published_at = ? WHERE event_id = ?",
                    [(now, i) for i in ids],
                )
            return events

    # ── catalog snapshots ────────────────────────────────────────────────
    def record_catalog_snapshot(self, counts: dict, hashes: dict) -> CatalogSnapshot:
        snap = CatalogSnapshot(
            snapshot_id=_new_id(), taken_at=now_iso(), counts=counts, hashes=hashes
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO catalog_snapshots(snapshot_id, taken_at, counts_json, hashes_json, org_id)"
                " VALUES (?,?,?,?,?)",
                (
                    snap.snapshot_id,
                    snap.taken_at,
                    json.dumps(counts),
                    json.dumps(hashes),
                    snap.org_id,
                ),
            )
        return snap

    def as_dict(self, obj) -> dict:
        return asdict(obj)
