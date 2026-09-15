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
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.determination import (
    UNRESOLVED_CODES,
    AssessmentResult,
    AtomResult,
    FieldResult,
    RequirementResult,
)
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


def process_identity(pid: int) -> str:
    """OS process birth time disambiguates a live worker from a reused PID."""
    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "lstart="], text=True, timeout=2
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _run_owner_alive(request: dict[str, Any]) -> bool:
    owner = request.get("worker_owner") or {}
    pid = owner.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    identity = process_identity(pid)
    # An unavailable process query is not proof that a live owner has died.
    return not identity or not owner.get("started") or identity == owner["started"]


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
    def migrate(self) -> dict[str, Any]:
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
        **dates: Any,
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
                document_number=dates.get("document_number", ""),
                version=dates.get("version", ""),
                owner=dates.get("owner", ""),
                owner_title=dates.get("owner_title", ""),
            )
            self._conn.execute(
                """INSERT INTO document_revisions(revision_id, logical_id, alias_path,
                       binding_effect, authored_date, approved_date, effective_date,
                       last_reviewed_date, retrieved_at, org_id, recorded_from, recorded_to,
                       document_number, version, owner, owner_title)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?)""",
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
                    rev.document_number,
                    rev.version,
                    rev.owner,
                    rev.owner_title,
                ),
            )
            self._write_outbox_unlocked("document_revision_added", {"revision_id": revision_id})
            return rev

    def update_revision_control_metadata(
        self,
        revision_id: str,
        *,
        binding_effect: str | None = None,
        document_number: str | None = None,
        version: str | None = None,
        owner: str | None = None,
        owner_title: str | None = None,
        effective_date: str | None = None,
        approved_date: str | None = None,
        authored_date: str | None = None,
        last_reviewed_date: str | None = None,
    ) -> bool:
        """Record sourced control-block metadata on an existing immutable
        revision. Bytes are untouched; absent arguments are left as-is;
        sourced values overwrite only previous NULL/empty placeholders, so a
        re-run can never clobber a real value with an empty one. Returns
        False when the revision does not resolve."""
        with self._lock, self._conn:
            if not self._conn.execute(
                "SELECT 1 FROM document_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone():
                return False
            assignments: list[str] = []
            params: list[Any] = []
            for column, value in (
                ("binding_effect", binding_effect),
                ("document_number", document_number),
                ("version", version),
                ("owner", owner),
                ("owner_title", owner_title),
                ("effective_date", effective_date),
                ("approved_date", approved_date),
                ("authored_date", authored_date),
                ("last_reviewed_date", last_reviewed_date),
            ):
                if value is None:
                    continue
                if column == "binding_effect":
                    assignments.append(f"{column} = ?")
                    params.append(value)
                else:
                    # dates/text: fill honest placeholders only
                    assignments.append(
                        f"{column} = (CASE WHEN ({column} IS NULL OR {column} = '') THEN ? ELSE {column} END)"
                    )
                    params.append(value)
            if not assignments:
                return True
            params.append(revision_id)
            self._conn.execute(
                f"UPDATE document_revisions SET {', '.join(assignments)} WHERE revision_id = ?",
                params,
            )
            return True

    def set_section_function(self, section_id: str, *, role: str, title: str) -> bool:
        """Assign a section's controlled function (role + heading title).
        Used to type the legacy whole-document section with the document's
        own source role. Returns False when the section does not resolve."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE source_sections SET role = ?, title = ? WHERE section_id = ?",
                (role, title, section_id),
            )
            return cur.rowcount > 0

    def sections_with_role(self, revision_id: str) -> list[dict[str, Any]]:
        """Every classified section of a revision, ordered by page then
        position — the operative-section resolution surface."""
        rows = self._conn.execute(
            """SELECT s.section_id, s.path, s.role, s.title, s.page_start, s.page_end,
                      MIN(sp.char_start) AS char_start
               FROM source_sections s LEFT JOIN source_spans sp ON sp.section_id = s.section_id
               WHERE s.revision_id = ?
               GROUP BY s.section_id
               ORDER BY char_start, s.path""",
            (revision_id,),
        ).fetchall()
        return [dict(r) for r in rows]

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
                       page_end, table_ref, extractor, extractor_version, org_id, role, title)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
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
                    section.role,
                    section.title,
                ),
            )

    def add_source_span(
        self,
        span_id: str,
        section_id: str,
        char_start: int,
        char_end: int,
        text_sha256: str,
        *,
        org_id: str = "default",
    ) -> None:
        """Persist an immutable offset anchor after validating its bounds."""
        if char_start < 0 or char_end <= char_start:
            raise ValueError("source span requires 0 <= char_start < char_end")
        with self._lock, self._conn:
            if not self._conn.execute(
                "SELECT 1 FROM source_sections WHERE section_id = ?", (section_id,)
            ).fetchone():
                raise BrokenReferenceError(
                    f"source_spans.section_id {section_id!r} does not resolve"
                )
            self._conn.execute(
                """INSERT INTO source_spans(span_id, section_id, char_start, char_end,
                       text_sha256, org_id) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(span_id) DO NOTHING""",
                (span_id, section_id, char_start, char_end, text_sha256, org_id),
            )

    # ── P3: obligation decomposition, dependencies, semantic lineage ────
    def replace_obligation_derivation(
        self,
        node_id: str,
        atoms: list[dict[str, Any]],
        expression: dict[str, Any],
        *,
        expression_id: str,
        org_id: str = "default",
    ) -> None:
        """Re-derive one node's atoms + expression atomically.

        Atoms and expressions are machine-derived assertions (§3.1): when the
        decomposer changes, re-derivation REPLACES the previous rows for the
        node under the same source anchors — stale derived rows are never
        kept beside fresh ones (lesson L14, same-fingerprint dependents).
        Dependency rows for the node are cleared with the atoms.
        """
        with self._lock, self._conn:
            if not self._conn.execute(
                "SELECT 1 FROM requirement_nodes WHERE node_id = ?", (node_id,)
            ).fetchone():
                raise BrokenReferenceError(f"requirement node {node_id!r} does not resolve")
            self._conn.execute("DELETE FROM obligation_dependencies WHERE node_id = ?", (node_id,))
            self._conn.execute("DELETE FROM obligation_atoms WHERE node_id = ?", (node_id,))
            self._conn.execute("DELETE FROM obligation_expressions WHERE node_id = ?", (node_id,))
            for atom in atoms:
                self._conn.execute(
                    """INSERT INTO obligation_atoms(atom_id,node_id,actor,modality,action,object,population,trigger,deadline_cadence,conditions_json,exceptions_json,evidence_expectation,source_anchor_ids_json,interpretation_status,clause_text,org_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        atom["atom_id"],
                        node_id,
                        atom.get("actor", ""),
                        atom.get("modality", ""),
                        atom.get("action", ""),
                        atom.get("object", ""),
                        atom.get("population", ""),
                        atom.get("trigger", ""),
                        atom.get("deadline_cadence", ""),
                        json.dumps(atom.get("conditions", [])),
                        json.dumps(atom.get("exceptions", [])),
                        atom.get("evidence_expectation", ""),
                        json.dumps(atom.get("source_anchor_ids", [])),
                        atom.get("interpretation_status", "proposed"),
                        atom.get("text", ""),
                        org_id,
                    ),
                )
            self._conn.execute(
                """INSERT INTO obligation_expressions(expression_id,node_id,structure_json,org_id)
                   VALUES (?,?,?,?)""",
                (expression_id, node_id, json.dumps(expression), org_id),
            )

    def add_obligation_dependency(
        self,
        dependency_id: str,
        node_id: str,
        atom_id: str,
        *,
        depends_on_node_id: str = "",
        depends_on_ref: str = "",
        kind: str = "references",
        org_id: str = "default",
    ) -> None:
        with self._lock, self._conn:
            if not self._conn.execute(
                "SELECT 1 FROM obligation_atoms WHERE atom_id = ?", (atom_id,)
            ).fetchone():
                raise BrokenReferenceError(f"obligation atom {atom_id!r} does not resolve")
            self._conn.execute(
                """INSERT INTO obligation_dependencies(dependency_id,node_id,atom_id,
                       depends_on_node_id,depends_on_ref,kind,org_id)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(dependency_id) DO NOTHING""",
                (
                    dependency_id,
                    node_id,
                    atom_id,
                    depends_on_node_id,
                    depends_on_ref,
                    kind,
                    org_id,
                ),
            )

    def upsert_obligation_concept(
        self,
        concept_id: str,
        *,
        family: str = "",
        label: str = "",
        derivation: str = "",
        org_id: str = "default",
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO obligation_concepts(concept_id,family,label,derivation,org_id)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(concept_id) DO UPDATE SET
                       label = excluded.label,
                       derivation = excluded.derivation""",
                (concept_id, family, label, derivation, org_id),
            )

    def set_requirement_lineage(self, node_id: str, concept_id: str) -> None:
        """Record concept membership on a revision-specific duty row. The
        concept must already exist — lineage identity is never implicit."""
        with self._lock, self._conn:
            if not self._conn.execute(
                "SELECT 1 FROM obligation_concepts WHERE concept_id = ?", (concept_id,)
            ).fetchone():
                raise BrokenReferenceError(f"obligation concept {concept_id!r} does not resolve")
            self._conn.execute(
                "UPDATE requirement_nodes SET logical_lineage_id = ? WHERE node_id = ?",
                (concept_id, node_id),
            )

    # ── V3 determinations and exhaustive-search receipts ───────────────
    def record_boundary_proof(
        self,
        *,
        subject_ref: str,
        query_set: list[str],
        index_generation: str,
        manifest_hash: str,
        eligible_document_count: int,
        candidates_retrieved: list[dict[str, Any]] | None = None,
        candidates_rejected: list[dict[str, Any]] | None = None,
        truncation_flags: list[str] | None = None,
        budget_ceilings: dict[str, Any] | None = None,
        boundary_proof_id: str = "",
        org_id: str = "default",
    ) -> str:
        if not query_set or not index_generation:
            raise ValueError("a boundary proof requires its actual query set and index generation")
        proof_id = boundary_proof_id or _new_id()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO corpus_boundary_proofs(
                       boundary_proof_id, subject_ref, query_set_json, index_generation,
                       manifest_hash, eligible_document_count, candidates_retrieved_json,
                       candidates_rejected_json, truncation_flags_json, budget_ceilings_json,
                       created_at, org_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(boundary_proof_id) DO NOTHING""",
                (
                    proof_id,
                    subject_ref,
                    json.dumps(query_set),
                    index_generation,
                    manifest_hash,
                    eligible_document_count,
                    json.dumps(candidates_retrieved or []),
                    json.dumps(candidates_rejected or []),
                    json.dumps(truncation_flags or []),
                    json.dumps(budget_ceilings or {}),
                    now_iso(),
                    org_id,
                ),
            )
        return proof_id

    def record_analysis_run(
        self, context: dict[str, Any], *, run_id: str = "", org_id: str = "default"
    ) -> str:
        run_id = run_id or _new_id()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO analysis_runs(run_id, context_json, created_at, org_id) VALUES (?,?,?,?)",
                (run_id, json.dumps(context), now_iso(), org_id),
            )
        return run_id

    # ── reading architecture: assessments and durable runs ──────────────
    RUN_STATES = ("QUEUED", "RUNNING", "COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED")

    def record_assessment(
        self,
        result: AssessmentResult,
        *,
        parent_assessment_id: str = "",
        schema_version: int = 0,
    ) -> str:
        """Persist one canonical AssessmentResult atomically after validating
        the whole record and every source ref it cites (brief §6)."""
        payload = asdict(result)
        # Re-running __post_init__ rejects a mutated/invalid record before SQL.
        AssessmentResult(**dict(payload))
        if result.documentary_coverage == "UNRESOLVED" and (
            result.unresolved_code not in UNRESOLVED_CODES or not result.missing_fact
        ):
            raise ValueError("UNRESOLVED assessment requires a code and its missing_fact payload")
        self._validate_result_source_refs(payload)
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO assessment_results(
                       assessment_id, run_id, parent_assessment_id, requirement_id,
                       engine_version, schema_version, org_id, kb_id, input_fingerprint,
                       effective_on, known_at, applicability, coverage,
                       documentary_coverage, substantively_resolved, unresolved_code,
                       source_readiness, temporal_currency, documentary_alignment,
                       implementation_evidence, review_required, review_reason,
                       result_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    result.assessment_id,
                    result.run_id,
                    parent_assessment_id,
                    result.requirement_id,
                    result.engine_version,
                    schema_version or self.schema_version,
                    str(payload.get("org_id", "default")),
                    str(payload.get("kb_id", "")),
                    result.input_fingerprint,
                    str(payload.get("effective_on", "")),
                    str(payload.get("known_at", "")),
                    result.applicability,
                    result.coverage,
                    result.documentary_coverage,
                    1 if result.substantively_resolved else 0,
                    result.unresolved_code,
                    result.source_readiness,
                    result.temporal_currency,
                    result.documentary_alignment,
                    result.implementation_evidence,
                    1 if result.review_required else 0,
                    result.review_reason,
                    json.dumps(payload),
                    now_iso(),
                ),
            )
        return result.assessment_id

    def _validate_result_source_refs(self, payload: dict[str, Any]) -> None:
        """Every slice ID an assessment cites must be present in the same
        result's selected slices — a report cannot cite a source it did not
        actually select (brief §4, strict source validation)."""
        selected = {
            s.get("slice_id")
            for s in payload.get("selected_source_slices", [])
            if isinstance(s, dict)
        }
        selected.discard(None)
        referenced: list[str] = []
        for item in payload.get("covered", []):
            referenced += item.get("governing_slice_ids", []) + item.get("internal_slice_ids", [])
        for item in payload.get("gaps", []):
            referenced += item.get("governing_slice_ids", []) + item.get(
                "internal_counterevidence_slice_ids", []
            )
        for item in payload.get("uncertainties", []):
            referenced += item.get("source_slice_ids", [])
        dangling = sorted({r for r in referenced if r and r not in selected})
        if dangling:
            raise ValueError(f"assessment cites source slices it did not select: {dangling}")

    def get_assessment(self, assessment_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT result_json FROM assessment_results WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()
        if row is None:
            return None
        result: dict[str, Any] = json.loads(row["result_json"])
        return result

    def assessments_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT result_json FROM assessment_results WHERE run_id = ? ORDER BY requirement_id",
            (run_id,),
        ).fetchall()
        return [json.loads(r["result_json"]) for r in rows]

    def run_assessment_ids(self, run_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT assessment_id FROM assessment_results WHERE run_id = ? ORDER BY requirement_id",
            (run_id,),
        ).fetchall()
        return [r["assessment_id"] for r in rows]

    def create_run(
        self,
        request: dict[str, Any],
        *,
        run_id: str = "",
        status: str = "QUEUED",
        org_id: str = "default",
    ) -> str:
        if status not in self.RUN_STATES:
            raise ValueError(f"unknown run status: {status!r}")
        run_id = run_id or _new_id()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO analysis_runs(
                       run_id, context_json, created_at, org_id, status, request_json,
                       progress_json, cancel_requested, started_at, finished_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    json.dumps(request),
                    now_iso(),
                    org_id,
                    status,
                    json.dumps(request),
                    "{}",
                    0,
                    None,
                    None,
                    now_iso(),
                ),
            )
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        progress: dict[str, Any] | None = None,
        cancel_requested: bool | None = None,
        finished: bool = False,
    ) -> None:
        sets: list[str] = ["updated_at = ?"]
        params: list[Any] = [now_iso()]
        if status is not None:
            if status not in self.RUN_STATES:
                raise ValueError(f"unknown run status: {status!r}")
            sets.append("status = ?")
            params.append(status)
            if status == "RUNNING":
                sets.append("started_at = COALESCE(started_at, ?)")
                params.append(now_iso())
        if progress is not None:
            sets.append("progress_json = ?")
            params.append(json.dumps(progress))
        if cancel_requested is not None:
            sets.append("cancel_requested = ?")
            params.append(1 if cancel_requested else 0)
        if finished:
            sets.append("finished_at = ?")
            params.append(now_iso())
        params.append(run_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE analysis_runs SET {', '.join(sets)} WHERE run_id = ?", params
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["request"] = json.loads(d.get("request_json") or "{}")
        d["progress"] = json.loads(d.get("progress_json") or "{}")
        d["cancel_requested"] = bool(d.get("cancel_requested"))
        return d

    def mark_interrupted_runs(self) -> int:
        """Recover abandoned jobs without interrupting another live process."""
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT run_id, request_json FROM analysis_runs WHERE status IN ('RUNNING', 'QUEUED')"
            ).fetchall()
            abandoned = [row[0] for row in rows if not _run_owner_alive(json.loads(row[1] or "{}"))]
            for run_id in abandoned:
                self._conn.execute(
                    "UPDATE analysis_runs SET status = 'INTERRUPTED', updated_at = ?, finished_at = ? "
                    "WHERE run_id = ? AND status IN ('RUNNING', 'QUEUED')",
                    (now_iso(), now_iso(), run_id),
                )
        return len(abandoned)

    def record_claim(
        self,
        result: AtomResult | RequirementResult | dict[str, Any],
        *,
        run_id: str,
        assertion: str = "",
        claim_id: str = "",
        review_status: str = "proposed",
        org_id: str = "default",
    ) -> str:
        """Validate through the P1 dataclasses before touching SQL (C1-C4)."""
        if isinstance(result, dict):
            payload = dict(result)
            payload["field_results"] = [
                item if isinstance(item, FieldResult) else FieldResult(**item)
                for item in payload.get("field_results", [])
            ]
            result = AtomResult(**payload)
        if isinstance(result, RequirementResult):
            atoms = result.atom_results
            governing = sorted({a for atom in atoms for a in atom.governing_anchor_ids})
            internal = sorted({a for atom in atoms for a in atom.internal_anchor_ids})
            counter = sorted({a for atom in atoms for a in atom.counterevidence_anchor_ids})
            field_results = [asdict(f) for atom in atoms for f in atom.field_results]
            atom_ids = [atom.atom_id for atom in atoms]
            unresolved_code = result.unresolved_code
            missing_fact = result.missing_fact
            boundary_proof_id = next(
                (a.boundary_proof_id for a in atoms if a.boundary_proof_id), ""
            )
            determination = result.determination
            rationale = "; ".join(a.rationale for a in atoms if a.rationale)
        elif isinstance(result, AtomResult):
            # Reconstructing executes __post_init__ even if a caller managed to
            # mutate an already-created dataclass after construction.
            payload = asdict(result)
            payload["field_results"] = [FieldResult(**item) for item in payload["field_results"]]
            result = AtomResult(**payload)
            governing = result.governing_anchor_ids
            internal = result.internal_anchor_ids
            counter = result.counterevidence_anchor_ids
            field_results = [asdict(f) for f in result.field_results]
            atom_ids = [result.atom_id]
            unresolved_code = result.unresolved_code
            missing_fact = result.missing_fact
            boundary_proof_id = result.boundary_proof_id
            determination = result.determination
            rationale = result.rationale
        else:
            raise TypeError(
                "result must be AtomResult, RequirementResult, or an AtomResult mapping"
            )
        claim_id = claim_id or _new_id()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO claims(
                       claim_id, run_id, obligation_atom_ids_json, claim_kind, review_status,
                       assertion, rationale, governing_anchor_ids_json, internal_anchor_ids_json,
                       counterevidence_anchor_ids_json, created_at, org_id, determination,
                       unresolved_code, missing_fact_json, field_results_json, boundary_proof_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    claim_id,
                    run_id,
                    json.dumps(atom_ids),
                    "requirement_determination",
                    review_status,
                    assertion,
                    rationale,
                    json.dumps(governing),
                    json.dumps(internal),
                    json.dumps(counter),
                    now_iso(),
                    org_id,
                    determination,
                    unresolved_code,
                    json.dumps(missing_fact),
                    json.dumps(field_results),
                    boundary_proof_id,
                ),
            )
            evidence = [(a, "supporting") for a in governing + internal]
            evidence += [(a, "contradicting") for a in counter]
            self._conn.executemany(
                "INSERT INTO claim_evidence(claim_id, anchor_id, role) VALUES (?,?,?)",
                [(claim_id, anchor, role) for anchor, role in evidence],
            )
            finding_kind = {
                "ABSENT": "GAP_ABSENT",
                "PARTIAL": "GAP_PARTIAL",
                "CONTRADICTED": "CONTRADICTION",
            }.get(determination)
            if finding_kind:
                self._conn.execute(
                    "INSERT INTO findings(finding_id, claim_id, finding_kind, org_id) VALUES (?,?,?,?)",
                    (_new_id(), claim_id, finding_kind, org_id),
                )
        return claim_id

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
                       decided_by, decided_at, version, org_id, coverage, proposed_coverage,
                       confidence, derivation)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    rel.coverage,
                    rel.proposed_coverage,
                    rel.confidence,
                    rel.derivation,
                ),
            )
            self._write_outbox_unlocked("relationship_proposed", {"assertion_id": rel.assertion_id})
        return rel

    def tag_relationship_derivation(
        self,
        derivation: str,
        *,
        from_rationale: str | None = None,
        relation_types: tuple[str, ...] = (),
        statuses: tuple[str, ...] = ("proposed",),
    ) -> int:
        """P4 quarantine: stamp the derivation on legacy assertions matching
        an explicit provenance shape — either ``from_rationale`` (substring
        match) or ``relation_types`` — so folder/prefix Cartesian candidates
        become machine-recognizable discovery-only rows. Returns the number
        of rows tagged. Never touches assertions that already carry a
        derivation; at least one shape filter is required so a caller cannot
        stamp the whole table blind."""
        if from_rationale is None and not relation_types:
            raise ValueError("tag_relationship_derivation requires a provenance shape filter")
        placeholders = ",".join("?" for _ in statuses)
        sql = f"UPDATE relationship_assertions SET derivation = ? WHERE derivation = '' AND status IN ({placeholders})"
        params: list[Any] = [derivation, *statuses]
        if from_rationale is not None:
            sql += " AND rationale LIKE '%' || ? || '%'"
            params.append(from_rationale)
        if relation_types:
            rt = ",".join("?" for _ in relation_types)
            sql += f" AND relation_type IN ({rt})"
            params.extend(relation_types)
        with self._lock, self._conn:
            cur = self._conn.execute(sql, params)
            return cur.rowcount

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

    def close_relationship_validity(
        self, assertion_id: str, valid_to: str
    ) -> RelationshipAssertion:
        """Close ``valid_to`` on an approved relationship because the
        STANDARD superseded it, not because an SME reviewed and rejected it
        — no review event, no status change (an expired-but-was-correct-at-
        the-time mapping stays ``approved`` for historical `as_known`
        replay). Raises ``KeyError`` if the assertion does not exist."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE relationship_assertions SET valid_to = ? WHERE assertion_id = ?",
                (valid_to, assertion_id),
            )
            if cur.rowcount == 0:
                raise KeyError(assertion_id)
            return self._row_to_relationship(
                self._conn.execute(
                    "SELECT * FROM relationship_assertions WHERE assertion_id = ?", (assertion_id,)
                ).fetchone()
            )

    def list_relationship_assertions(
        self,
        *,
        ref: str | None = None,
        statuses: tuple[str, ...] = ("approved",),
        org_id: str | None = None,
        valid_at: str | None = None,
        known_at: str | None = None,
    ) -> list[RelationshipAssertion]:
        """Governed reads default to ``statuses=("approved",)`` — a caller
        must explicitly widen this to see proposals/rejections (design §4:
        "Normal governed reads must be unable to include proposed/rejected
        rows by forgetting a status filter"). ``org_id``, when given, is a
        bound-parameter equality filter (P6.4/A28) — a caller scoped to one
        org never sees another org's edges, even when both reference the
        same ``ref``.

        Phase 5: ``valid_at``/``known_at`` apply both clocks. A ``valid_at``
        filter excludes rows whose validity interval does not contain the
        moment — and a row with an UNKNOWN ``valid_from`` is never treated as
        "always valid" (F02): it is excluded, and
        :func:`temporal_selection.temporal_exclusion_census` names how many.
        ``known_at`` filters recorded knowledge (``recorded_from`` is NOT
        NULL on every row). Without either argument the governed status
        surface is unchanged."""
        placeholders = ",".join("?" for _ in statuses)
        sql = f"SELECT * FROM relationship_assertions WHERE status IN ({placeholders})"
        params: list[str] = list(statuses)
        if ref is not None:
            sql += " AND (src_ref = ? OR dst_ref = ?)"
            params += [ref, ref]
        if org_id is not None:
            sql += " AND org_id = ?"
            params.append(org_id)
        if valid_at:
            sql += " AND valid_from IS NOT NULL AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
            params += [valid_at, valid_at]
        if known_at:
            sql += " AND recorded_from <= ? AND (recorded_to IS NULL OR recorded_to > ?)"
            params += [known_at, known_at]
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
        evidence: list[dict[str, Any]] | None = None,
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
            # CORRECTED approves the edge (like CONFIRMED) but ALSO records a
            # different coverage than what was proposed — corrected_coverage
            # is a coverage value, never a status; writing it into the status
            # column would violate that column's CHECK constraint the moment
            # a real coverage string (e.g. "PARTIAL") reached it.
            new_status = {
                "CONFIRMED": "approved",
                "CORRECTED": "approved",
                "REJECTED": "rejected",
                "REVOKED": "revoked",
            }[decision]
            new_coverage = (
                corrected_coverage
                if decision == "CORRECTED" and corrected_coverage
                else current.coverage
            )
            now = now_iso()
            cur = self._conn.execute(
                """UPDATE relationship_assertions
                   SET status = ?, review_state = ?, decided_by = ?, decided_at = ?,
                       coverage = ?, version = version + 1
                   WHERE assertion_id = ? AND version = ?""",
                (
                    new_status,
                    decision,
                    decided_by,
                    now,
                    new_coverage,
                    assertion_id,
                    expected_version,
                ),
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
        org_id: str | None = None,
        valid_at: str | None = None,
        known_at: str | None = None,
    ) -> dict[str, Any]:
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
        edges_out: list[dict[str, Any]] = []
        depth_limited: set[str] = set()
        truncated = False

        while frontier:
            ref, depth = frontier.popleft()
            if depth >= max_depth:
                depth_limited.add(ref)
                continue
            for rel in self.list_relationship_assertions(
                ref=ref,
                statuses=statuses,
                org_id=org_id,
                valid_at=valid_at,
                known_at=known_at,
            ):
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
            "org_scope": org_id,
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
    def _write_outbox_unlocked(self, event_type: str, payload: dict[str, Any]) -> None:
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
    def record_catalog_snapshot(
        self, counts: dict[str, Any], hashes: dict[str, Any]
    ) -> CatalogSnapshot:
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

    # ── policy decisions (Q08 intentionality record) ───────────────────
    def record_policy_decision(
        self,
        control_id: str,
        rationale: str,
        owner: str = "",
        approving_authority: str = "",
        review_date: str | None = None,
        org_id: str = "default",
    ) -> str:
        decision_id = _new_id()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO policy_decisions(decision_id, control_id, rationale, owner,"
                " approving_authority, review_date, org_id) VALUES (?,?,?,?,?,?,?)",
                (
                    decision_id,
                    control_id,
                    rationale,
                    owner,
                    approving_authority,
                    review_date,
                    org_id,
                ),
            )
        return decision_id

    def get_policy_decisions(self, control_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT decision_id, control_id, rationale, owner, approving_authority,"
            " review_date, org_id FROM policy_decisions WHERE control_id = ?",
            (control_id,),
        ).fetchall()
        cols = (
            "decision_id",
            "control_id",
            "rationale",
            "owner",
            "approving_authority",
            "review_date",
            "org_id",
        )
        return [dict(zip(cols, row, strict=True)) for row in rows]

    def as_dict(self, obj: Any) -> dict[str, Any]:
        return asdict(obj)
