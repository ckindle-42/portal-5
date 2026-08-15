"""bully.store -- SUB, the sole owner of ``hunt_state.db`` (P1.2).

SQLite WAL, ordered migrations (`migrations/NNN_*.sql`, tracked in
`schema_migrations`), hash-chained decision events (chain math lives in
`events.py`; this module is the only place that writes a row), and the
transactional index outbox (retry/backoff policy lives in `outbox.py`).

No other bully module touches SQL (MASTER SS3 boundary rule -- enforced by
an import-scan test in ``tests/security/bully/test_boundaries.py``).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import events, outbox
from .contracts import (
    CousinAssessment,
    DecisionEvent,
    DecisionImpact,
    HuntContext,
    RecallReceipt,
    is_legal_hunt_transition,
)

SCHEMA_VERSION = 1  # highest migration this code understands
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class StoreError(RuntimeError):
    """Base class for SUB errors."""


class IllegalTransitionError(StoreError):
    """Raised on a stale/illegal hunt-stage transition attempt (C1)."""


class SchemaTooNewError(StoreError):
    """Raised when the on-disk schema is newer than this code understands."""


class OutboxIntegrityError(StoreError):
    """Raised when an outbox completion's source hash does not match (C3)."""


class LeaseError(StoreError):
    """Raised on a lease conflict (one active lease per hunt)."""


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row is not None else None


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value: str | None, default):
    if value is None:
        return default
    return json.loads(value)


class Store:
    """SUB -- the sole owner of ``hunt_state.db``."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── migrations ───────────────────────────────────────────────────────

    def _migrate(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, filename TEXT NOT NULL, applied_at REAL NOT NULL)"
        )
        applied = {
            r["version"] for r in self._conn.execute("SELECT version FROM schema_migrations")
        }
        migration_files = sorted(_MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
        for path in migration_files:
            version = int(path.name.split("_", 1)[0])
            if version in applied:
                continue
            if version > SCHEMA_VERSION:
                # A migration file exists on disk that this code doesn't
                # declare support for -- refuse rather than half-apply.
                raise SchemaTooNewError(
                    f"migration {path.name} (v{version}) exceeds SCHEMA_VERSION={SCHEMA_VERSION}"
                )
            sql = path.read_text(encoding="utf-8")
            with self._tx() as cur:
                cur.executescript(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (version, filename, applied_at) VALUES (?, ?, ?)",
                    (version, path.name, time.time()),
                )
        # A DB stamped with a version this code has no migration file for at
        # all is a newer schema than this code understands -- refuse (I-5
        # "code refuses a newer unsupported schema").
        unknown = applied - {int(p.name.split("_", 1)[0]) for p in migration_files}
        if unknown:
            raise SchemaTooNewError(f"database has unrecognized migration version(s): {unknown}")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            yield cur
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    # ── hunts ────────────────────────────────────────────────────────────

    def hunt_create(
        self,
        *,
        hunt_id: str,
        objective: str,
        neighborhood_scope: str,
        authorization_ref: str,
        config_version: str,
        role_snapshot: dict,
        budgets: dict,
    ) -> None:
        now = time.time()
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO hunts (hunt_id, objective, neighborhood_scope, authorization_ref, "
                "config_version, role_snapshot, budgets, budgets_used, stage, status, "
                "lease_owner, lease_expiry, version, parent_hunt_id, started_at, ended_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    hunt_id,
                    objective,
                    neighborhood_scope,
                    authorization_ref,
                    config_version,
                    _json(role_snapshot),
                    _json(budgets),
                    _json({}),
                    "DRAFT",
                    "running",
                    None,
                    None,
                    0,
                    None,
                    now,
                    None,
                ),
            )

    def hunt_get(self, hunt_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM hunts WHERE hunt_id=?", (hunt_id,)).fetchone()
        return _row_to_dict(row)

    def hunt_advance_stage(self, hunt_id: str, target_stage: str, *, expected_version: int) -> None:
        """Compare-and-swap stage transition; rejects stale/illegal transitions (C1)."""
        row = self.hunt_get(hunt_id)
        if row is None:
            raise StoreError(f"no such hunt: {hunt_id}")
        if row["version"] != expected_version:
            raise IllegalTransitionError(
                f"stale expected_version={expected_version} for hunt {hunt_id} "
                f"(current={row['version']})"
            )
        if not is_legal_hunt_transition(row["stage"], target_stage):
            raise IllegalTransitionError(
                f"{row['stage']} -> {target_stage} is not a legal transition"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE hunts SET stage=?, version=version+1 WHERE hunt_id=? AND version=?",
                (target_stage, hunt_id, expected_version),
            )
            if cur.rowcount != 1:
                raise IllegalTransitionError(f"concurrent modification of hunt {hunt_id}")

    def load_context(self, hunt_id: str) -> HuntContext:
        row = self.hunt_get(hunt_id)
        if row is None:
            raise StoreError(f"no such hunt: {hunt_id}")
        known = [
            _row_to_dict(r)
            for r in self._conn.execute(
                "SELECT * FROM known_state WHERE hunt_id=? AND superseded_by IS NULL", (hunt_id,)
            )
        ]
        return HuntContext(
            hunt_id=hunt_id,
            neighborhood_scope=row["neighborhood_scope"],
            config_version=row["config_version"],
            open_cells=[],
            known_state_view=known,
            plateau_view=None,
            cost_view=None,
        )

    # ── leases (one active lease per hunt) ──────────────────────────────

    def lease_acquire(self, hunt_id: str, owner: str, ttl_s: float = 300.0) -> None:
        now = time.time()
        row = self.hunt_get(hunt_id)
        if row is None:
            raise StoreError(f"no such hunt: {hunt_id}")
        held = row["lease_owner"] is not None and (row["lease_expiry"] or 0) > now
        if held and row["lease_owner"] != owner:
            raise LeaseError(f"hunt {hunt_id} already leased by {row['lease_owner']!r}")
        with self._tx() as cur:
            cur.execute(
                "UPDATE hunts SET lease_owner=?, lease_expiry=? WHERE hunt_id=?",
                (owner, now + ttl_s, hunt_id),
            )

    def lease_renew(self, hunt_id: str, owner: str, ttl_s: float = 300.0) -> None:
        row = self.hunt_get(hunt_id)
        if row is None or row["lease_owner"] != owner:
            raise LeaseError(f"cannot renew: {owner!r} does not hold the lease on {hunt_id}")
        with self._tx() as cur:
            cur.execute(
                "UPDATE hunts SET lease_expiry=? WHERE hunt_id=? AND lease_owner=?",
                (time.time() + ttl_s, hunt_id, owner),
            )

    def lease_release(self, hunt_id: str, owner: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE hunts SET lease_owner=NULL, lease_expiry=NULL "
                "WHERE hunt_id=? AND lease_owner=?",
                (hunt_id, owner),
            )

    # ── decision events (append-only, hash-chained) ─────────────────────

    def _last_event_hash(self, hunt_id: str | None) -> str | None:
        row = self._conn.execute(
            "SELECT chain_hash FROM decision_events WHERE hunt_id IS ? "
            "ORDER BY recorded_at DESC, event_id DESC LIMIT 1",
            (hunt_id,),
        ).fetchone()
        return row["chain_hash"] if row else None

    def record_decision(self, event: DecisionEvent) -> DecisionEvent:
        """Append-only. No update/delete path is ever exposed for this table."""
        with self._tx() as cur:
            prev_hash = self._last_event_hash(event.hunt_id)
            chain_hash = events.compute_chain_hash(prev_hash, event)
            recorded_at = time.time()
            cur.execute(
                "INSERT INTO decision_events (event_id, hunt_id, iteration_id, actor, kind, "
                "subject_id, rationale, data, prev_event_hash, chain_hash, occurred_at, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event.event_id,
                    event.hunt_id,
                    event.iteration_id,
                    event.actor,
                    event.kind,
                    event.subject_id,
                    event.rationale,
                    _json(event.data),
                    prev_hash,
                    chain_hash,
                    event.occurred_at,
                    recorded_at,
                ),
            )
        from dataclasses import replace

        return replace(
            event, prev_event_hash=prev_hash, chain_hash=chain_hash, recorded_at=recorded_at
        )

    def decision_events_for_hunt(self, hunt_id: str | None) -> list[DecisionEvent]:
        rows = self._conn.execute(
            "SELECT * FROM decision_events WHERE hunt_id IS ? ORDER BY recorded_at ASC, event_id ASC",
            (hunt_id,),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                DecisionEvent(
                    event_id=r["event_id"],
                    hunt_id=r["hunt_id"],
                    iteration_id=r["iteration_id"],
                    actor=r["actor"],
                    kind=r["kind"],
                    subject_id=r["subject_id"],
                    rationale=r["rationale"],
                    data=_loads(r["data"], {}),
                    prev_event_hash=r["prev_event_hash"],
                    chain_hash=r["chain_hash"],
                    occurred_at=r["occurred_at"],
                    recorded_at=r["recorded_at"],
                )
            )
        return out

    # ── known_state (supersede, never delete) ───────────────────────────

    def update_known_state(
        self,
        subject: str,
        kind: str,
        evidence: dict,
        *,
        hunt_id: str | None = None,
        trust_tier: str = "SUSPECT",
        supersedes: str | None = None,
    ) -> str:
        if not evidence:
            raise StoreError("known_state entries require evidence -- no evidence, no entry")
        entry_id = f"ks-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._tx() as cur:
            if supersedes is not None:
                cur.execute(
                    "UPDATE known_state SET superseded_by=? WHERE entry_id=? AND superseded_by IS NULL",
                    (entry_id, supersedes),
                )
                if cur.rowcount != 1:
                    raise StoreError(
                        f"cannot supersede {supersedes!r}: not found or already superseded"
                    )
            cur.execute(
                "INSERT INTO known_state (entry_id, subject, kind, trust_tier, posterior_adjustment, "
                "applicability, confidence_half_life_days, evidence, contradiction_links, "
                "superseded_by, created_at, hunt_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry_id,
                    subject,
                    kind,
                    trust_tier,
                    _json({}),
                    _json({}),
                    None,
                    _json(evidence),
                    _json([]),
                    None,
                    now,
                    hunt_id,
                ),
            )
        return entry_id

    # ── cousin assessments ───────────────────────────────────────────────

    def record_cousin(self, assessment: CousinAssessment) -> None:
        d = assessment.decomposition
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO cousin_assessments (assessment_id, subject_signature_id, "
                "reference_signature_id, candidate_set_id, d_behavior, d_telemetry, d_semantic, "
                "d_attack, d_context, composite, relationship, nonsemantic_channels, vetoes, "
                "defense_response, nearest_knowns, confidence, completeness, algorithm_version, "
                "thresholds_version, explanation, superseded_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    assessment.assessment_id,
                    assessment.subject_signature_id,
                    assessment.reference_signature_id,
                    assessment.candidate_set_id,
                    d.behavior,
                    d.telemetry,
                    d.semantic,
                    d.attack,
                    d.context,
                    assessment.composite,
                    assessment.relationship,
                    assessment.nonsemantic_channels,
                    _json(assessment.vetoes),
                    assessment.defense_response,
                    _json(assessment.nearest_knowns),
                    assessment.confidence,
                    assessment.completeness,
                    assessment.algorithm_version,
                    assessment.thresholds_version,
                    _json(assessment.explanation),
                    assessment.superseded_by,
                    time.time(),
                ),
            )

    # ── recall receipts / decision impacts ──────────────────────────────

    def recall_receipt_put(self, receipt: RecallReceipt) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO recall_receipts (recall_id, hunt_id, query, filters, trust_policy, "
                "projection_version, embedding_version, reranker_version, source_health, "
                "candidates, exclusions, selected_context, token_budget, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    receipt.recall_id,
                    receipt.hunt_id,
                    receipt.query,
                    _json(receipt.filters),
                    _json({}),
                    receipt.projection_version,
                    receipt.embedding_version,
                    receipt.reranker_version,
                    _json(receipt.source_health),
                    _json(receipt.candidates),
                    _json(receipt.exclusions),
                    _json(receipt.selected_context),
                    receipt.token_budget,
                    receipt.created_at,
                ),
            )

    def recall_receipt_exists(self, hunt_id: str) -> bool:
        """C3: 'a hunt cannot target without a persisted RecallReceipt.'"""
        row = self._conn.execute(
            "SELECT 1 FROM recall_receipts WHERE hunt_id=? LIMIT 1", (hunt_id,)
        ).fetchone()
        return row is not None

    def decision_impact_put(self, impact: DecisionImpact) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO decision_impacts (impact_id, recall_id, consuming_decision_ref, "
                "before_json, after_json, cited_record_ids, change_kind, explanation, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    impact.impact_id,
                    impact.recall_id,
                    impact.consuming_decision_ref,
                    _json(impact.before),
                    _json(impact.after),
                    _json(impact.cited_record_ids),
                    impact.change_kind,
                    impact.explanation,
                    impact.created_at,
                ),
            )

    # ── outbox ───────────────────────────────────────────────────────────

    def outbox_append(
        self,
        *,
        record_type: str,
        record_id: str,
        record_version: int,
        projection_version: str,
        source_hash: str,
        operation: str,
        required_for_closure: bool,
        payload: dict,
    ) -> str:
        # Idempotent: (record_type, record_id, record_version, projection_version)
        # is the natural key (DATA_MODEL SS1.10). A re-drive with the same key
        # returns the existing outbox_id rather than erroring or duplicating.
        existing = self._conn.execute(
            "SELECT outbox_id FROM index_outbox WHERE record_type=? AND record_id=? "
            "AND record_version=? AND projection_version=?",
            (record_type, record_id, record_version, projection_version),
        ).fetchone()
        if existing is not None:
            return existing["outbox_id"]
        outbox_id = f"ob-{uuid.uuid4().hex[:12]}"
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO index_outbox (outbox_id, record_type, record_id, record_version, "
                "projection_version, source_hash, operation, required_for_closure, status, "
                "attempts, next_attempt_at, error, completed_at, projected_row_hash, payload, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    outbox_id,
                    record_type,
                    record_id,
                    record_version,
                    projection_version,
                    source_hash,
                    operation,
                    1 if required_for_closure else 0,
                    "pending",
                    0,
                    time.time(),
                    None,
                    None,
                    None,
                    _json(payload),
                    time.time(),
                ),
            )
        return outbox_id

    def outbox_lease(self, limit: int = 10) -> list[dict]:
        now = time.time()
        with self._tx() as cur:
            rows = cur.execute(
                "SELECT * FROM index_outbox WHERE status='pending' AND "
                "(next_attempt_at IS NULL OR next_attempt_at <= ?) LIMIT ?",
                (now, limit),
            ).fetchall()
            ids = [r["outbox_id"] for r in rows]
            for oid in ids:
                cur.execute("UPDATE index_outbox SET status='leased' WHERE outbox_id=?", (oid,))
        leased = [_row_to_dict(r) for r in rows]
        for r in leased:
            r["status"] = "leased"
        return leased

    def outbox_complete(self, outbox_id: str, *, source_hash: str) -> None:
        """C3: completion requires source_hash equality with the authoritative record."""
        row = self._conn.execute(
            "SELECT source_hash FROM index_outbox WHERE outbox_id=?", (outbox_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no such outbox item: {outbox_id}")
        if row["source_hash"] != source_hash:
            raise OutboxIntegrityError(
                f"outbox {outbox_id}: source_hash mismatch at completion "
                f"({row['source_hash']!r} != {source_hash!r})"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE index_outbox SET status='completed', completed_at=? WHERE outbox_id=?",
                (time.time(), outbox_id),
            )

    def outbox_fail(self, outbox_id: str, *, error: str) -> None:
        row = self._conn.execute(
            "SELECT attempts FROM index_outbox WHERE outbox_id=?", (outbox_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no such outbox item: {outbox_id}")
        attempts = row["attempts"] + 1
        if outbox.should_dead_letter(attempts):
            with self._tx() as cur:
                cur.execute(
                    "UPDATE index_outbox SET status='dead_letter', attempts=?, error=? WHERE outbox_id=?",
                    (attempts, error, outbox_id),
                )
        else:
            with self._tx() as cur:
                cur.execute(
                    "UPDATE index_outbox SET status='pending', attempts=?, error=?, "
                    "next_attempt_at=? WHERE outbox_id=?",
                    (attempts, error, outbox.next_attempt_at(time.time(), attempts), outbox_id),
                )

    def outbox_required_dead_letters(self, hunt_id_prefix: str | None = None) -> list[dict]:
        """A required dead letter blocks hunt closure (DATA_MODEL SS1.10)."""
        rows = self._conn.execute(
            "SELECT * FROM index_outbox WHERE status='dead_letter' AND required_for_closure=1"
        ).fetchall()
        out = [_row_to_dict(r) for r in rows]
        if hunt_id_prefix is not None:
            out = [r for r in out if str(r["record_id"]).startswith(hunt_id_prefix)]
        return out

    # ── doctor (integrity check) ─────────────────────────────────────────

    def doctor(self) -> dict:
        report: dict = {"ok": True, "issues": []}
        hunt_ids = [None] + [
            r["hunt_id"] for r in self._conn.execute("SELECT DISTINCT hunt_id FROM hunts")
        ]
        for hunt_id in hunt_ids:
            evs = self.decision_events_for_hunt(hunt_id)
            ok, broken_at = events.verify_chain(evs)
            if not ok:
                report["ok"] = False
                report["issues"].append(f"hash chain broken for hunt={hunt_id!r} at {broken_at}")
        dead = self.outbox_required_dead_letters()
        if dead:
            report["ok"] = False
            report["issues"].append(f"{len(dead)} required outbox dead letter(s) block closure")
        return report
