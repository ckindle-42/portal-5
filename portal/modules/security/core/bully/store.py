"""bully.store -- SUB, the sole owner of ``hunt_state.db`` (P1.2).

SQLite WAL, ordered migrations (`migrations/NNN_*.sql`, tracked in
`schema_migrations`), hash-chained decision events (chain math lives in
`events.py`; this module is the only place that writes a row), and the
transactional index outbox (retry/backoff policy lives in `outbox.py`).

No other bully module touches SQL (MASTER SS3 boundary rule -- enforced by
an import-scan test in ``tests/security/bully/test_boundaries.py``).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import events, outbox
from .contracts import (
    CostRecord,
    CousinAssessment,
    DecisionEvent,
    DecisionImpact,
    DriftFlag,
    HuntContext,
    MutationPlan,
    PlateauDecision,
    RecallReceipt,
    ScenarioOverlay,
    is_legal_bin_transition,
    is_legal_hunt_transition,
)

SCHEMA_VERSION = 11  # highest migration this code understands
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


class IllegalBinTransitionError(StoreError):
    """Raised on a stale/illegal candidate-state transition attempt (C7)."""


class OperatorActorRequiredError(StoreError):
    """Raised when a queue/promotion resolution is attempted by a non-operator
    actor -- mirrors the DB trigger's refusal so the Python exception carries
    a clear message instead of a bare sqlite3.IntegrityError (SS4.8)."""


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
                if version == 10:
                    self._migrate_train_acceptance_report(cur)
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

    @staticmethod
    def _migrate_train_acceptance_report(cur: sqlite3.Cursor) -> None:
        """Rename the one superseded report column without naming old policy.

        Fresh databases already expose ``acceptance_report_json`` in migration
        009. For an existing v9 database, the only other generic report column
        besides intake/canary is the legacy acceptance payload; identify that
        column from schema metadata and preserve it under the new neutral name.
        """
        columns = {row[1] for row in cur.execute("PRAGMA table_info(trained_models)")}
        target = "acceptance_report_json"
        if target in columns:
            return
        known = {"intake_report_json", "canary_report_json"}
        candidates = sorted(
            name for name in columns if name.endswith("_report_json") and name not in known
        )
        if len(candidates) != 1:
            raise StoreError(
                f"cannot identify the v9 TRAIN acceptance report column (candidates={candidates!r})"
            )
        legacy = candidates[0].replace('"', '""')
        cur.execute(f'ALTER TABLE trained_models RENAME COLUMN "{legacy}" TO "{target}"')

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

    def hunts(self) -> list[dict[str, Any]]:
        """Read hunt headers for audit/proof reporting."""
        rows = self._conn.execute("SELECT * FROM hunts ORDER BY started_at, hunt_id").fetchall()
        return [_row_to_dict(row) for row in rows]

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

    def any_active_lease(self) -> bool:
        """TRAIN's preflight (P6.4, MASTER SS5): 'refuse if a hunt ... is
        active' -- a live (non-expired) lease on any hunt means a hunt
        iteration is in flight."""
        row = self._conn.execute(
            "SELECT 1 FROM hunts WHERE lease_owner IS NOT NULL AND lease_expiry > ? LIMIT 1",
            (time.time(),),
        ).fetchone()
        return row is not None

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
        deployment_id: str | None = None,
    ) -> str:
        """`deployment_id` (P5.1): required by the DB when `kind='known_covered'`
        (`trg_known_covered_requires_deploy_replay`, SS4.8) -- the deployment
        must already carry a passed `replay_validations` row, or this insert
        raises `sqlite3.IntegrityError`. Ignored for every other kind."""
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
                "superseded_by, created_at, hunt_id, deployment_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    deployment_id,
                ),
            )
        return entry_id

    # ── persisted coverage cells (P7 capability-graph cutover) ────────

    def coverage_cell_put(self, cell: dict[str, Any]) -> bool:
        """Content-idempotent SUB persistence for on-demand coverage readout."""
        cell_id = str(cell["cell_id"])
        payload = _json(cell)
        source_hash = hashlib.sha256(payload.encode()).hexdigest()
        existing = self._conn.execute(
            "SELECT source_hash FROM coverage_cells WHERE cell_id=?", (cell_id,)
        ).fetchone()
        if existing is not None and existing["source_hash"] == source_hash:
            return False
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO coverage_cells "
                "(cell_id, subject, scenario, payload_json, source_hash, version, updated_at) "
                "VALUES (?,?,?,?,?,1,?) ON CONFLICT(cell_id) DO UPDATE SET "
                "subject=excluded.subject, scenario=excluded.scenario, "
                "payload_json=excluded.payload_json, source_hash=excluded.source_hash, "
                "version=coverage_cells.version+1, updated_at=excluded.updated_at",
                (
                    cell_id,
                    str(cell.get("subject", cell_id)),
                    cell.get("scenario"),
                    payload,
                    source_hash,
                    time.time(),
                ),
            )
        return True

    def coverage_cells(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM coverage_cells ORDER BY cell_id").fetchall()
        out = []
        for row in rows:
            stored = _row_to_dict(row)
            payload = _loads(stored["payload_json"], {})
            payload["persistence"] = {
                "source_hash": stored["source_hash"],
                "version": stored["version"],
            }
            out.append(payload)
        return out

    # ── behavior signatures ──────────────────────────────────────────────

    def record_signature(self, signature: Any) -> None:
        """Persist a `signatures.BehaviorSignature` (idempotent on its
        natural key: episode_ref + algorithm version + input manifest
        hash -- a re-drive with identical inputs is a silent no-op, not a
        duplicate row or an error)."""
        existing = self._conn.execute(
            "SELECT 1 FROM behavior_signatures WHERE signature_id=?", (signature.signature_id,)
        ).fetchone()
        if existing is not None:
            return
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO behavior_signatures (signature_id, episode_ref, "
                "signature_algorithm_version, input_manifest_hash, canonical_fingerprint, "
                "action_sequence, event_graph, parameter_families, context_topology, artifacts, "
                "attack_mappings, telemetry_shape, detector_outcomes, evidence_manifest_id, "
                "completeness, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    signature.signature_id,
                    signature.episode_ref,
                    signature.signature_algorithm_version,
                    signature.input_manifest_hash,
                    signature.canonical_fingerprint,
                    _json(signature.action_sequence),
                    _json(signature.event_graph),
                    _json(signature.parameter_families),
                    _json(signature.context_topology),
                    _json(signature.artifacts),
                    _json(signature.attack_mappings),
                    _json(signature.telemetry_shape),
                    _json(signature.detector_outcomes),
                    signature.evidence_manifest_id,
                    signature.completeness,
                    signature.created_at,
                ),
            )

    def signature_get(self, signature_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM behavior_signatures WHERE signature_id=?", (signature_id,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            for key in ("attack_mappings", "action_sequence", "event_graph"):
                d[key] = _loads(d[key], [] if key != "event_graph" else {})
        return d

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

    def cousin_assessment_get(self, assessment_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM cousin_assessments WHERE assessment_id=?", (assessment_id,)
        ).fetchone()
        return _row_to_dict(row)

    def scoreboard_records_for_hunt(self, hunt_id: str) -> list[dict]:
        """Assemble `scoreboard.py`-ready records for a hunt (P4.2): every
        `grade`-kind decision event's cousin assessment, left-joined with
        that hunt's candidate state (the latest candidate row for the
        assessment, if BIN has been driven for it) and a `known_state`
        `known_benign` flag keyed on the assessment's reference signature
        -- read-only assembly, no scoring (scoring itself stays pure in
        `scoreboard.py`)."""
        grade_events = self._conn.execute(
            "SELECT subject_id FROM decision_events WHERE hunt_id=? AND kind='grade' "
            "ORDER BY recorded_at ASC",
            (hunt_id,),
        ).fetchall()
        out: list[dict] = []
        for ev in grade_events:
            assessment = self.cousin_assessment_get(ev["subject_id"])
            if assessment is None:
                continue
            candidate = self._conn.execute(
                "SELECT current_state FROM candidates WHERE hunt_id=? AND assessment_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (hunt_id, assessment["assessment_id"]),
            ).fetchone()
            known_benign = self._conn.execute(
                "SELECT 1 FROM known_state WHERE subject=? AND kind='known_benign' "
                "AND superseded_by IS NULL LIMIT 1",
                (assessment["reference_signature_id"] or assessment["subject_signature_id"],),
            ).fetchone()
            out.append(
                {
                    "assessment_id": assessment["assessment_id"],
                    "relationship": assessment["relationship"],
                    "defense_response": assessment["defense_response"],
                    "composite": assessment["composite"],
                    "candidate_state": candidate["current_state"] if candidate else None,
                    "known_benign": known_benign is not None,
                }
            )
        return out

    def plateau_trials_for_neighborhood(self, neighborhood: str) -> list[dict]:
        """Assemble `plateau.py`-ready trial facts (P4.4): one trial per
        hunt scoped to this `neighborhood_scope` (this build runs exactly
        one iteration per hunt, so a hunt IS a trial). `valid=False`
        (blocked/infrastructure-failed, excluded from every plateau
        denominator) whenever the hunt never reached `CLOSED`.
        `mutation_dim` comes from the `gate`-kind decision event MUT
        records (`_do_mutate`'s `applied_operators`) -- the first applied
        operator, or `"NONE"` for an unmutated passthrough iteration.
        Read-only assembly, no scoring -- `orchestrator.py`'s caller
        derives `discovery_positive` via `scoreboard.score_record`."""
        hunts = self._conn.execute(
            "SELECT hunt_id, stage, config_version, started_at FROM hunts "
            "WHERE neighborhood_scope=? ORDER BY started_at ASC",
            (neighborhood,),
        ).fetchall()
        out: list[dict] = []
        for h in hunts:
            hunt_id = h["hunt_id"]
            promoted = self._conn.execute(
                "SELECT 1 FROM candidates WHERE hunt_id=? AND current_state='PROMOTED' LIMIT 1",
                (hunt_id,),
            ).fetchone()
            gate_event = self._conn.execute(
                "SELECT data FROM decision_events WHERE hunt_id=? AND kind='gate' "
                "ORDER BY recorded_at ASC LIMIT 1",
                (hunt_id,),
            ).fetchone()
            mutation_dim = "NONE"
            if gate_event is not None:
                data = _loads(gate_event["data"], {})
                ops = data.get("applied_operators") or []
                if ops:
                    mutation_dim = ops[0]
            assessments = self.scoreboard_records_for_hunt(hunt_id)
            out.append(
                {
                    "trial_id": hunt_id,
                    "neighborhood": neighborhood,
                    "version": h["config_version"],
                    "valid": h["stage"] == "CLOSED",
                    "promoted": promoted is not None,
                    "mutation_dim": mutation_dim,
                    "assessment": assessments[0] if assessments else None,
                }
            )
        return out

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

    def recall_receipts(self) -> list[dict[str, Any]]:
        """Read all recall receipts with their JSON fields decoded."""
        rows = self._conn.execute(
            "SELECT * FROM recall_receipts ORDER BY created_at, recall_id"
        ).fetchall()
        out = []
        for row in rows:
            item = _row_to_dict(row)
            for key, fallback in (
                ("filters", {}),
                ("source_health", {}),
                ("candidates", []),
                ("exclusions", []),
                ("selected_context", []),
            ):
                item[key] = _loads(item[key], fallback)
            out.append(item)
        return out

    def latest_recall_id_for_hunt(self, hunt_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT recall_id FROM recall_receipts WHERE hunt_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (hunt_id,),
        ).fetchone()
        return str(row["recall_id"]) if row is not None else None

    def latest_recall_id(self) -> str | None:
        """Return the newest durable recall for out-of-band flywheel links."""
        row = self._conn.execute(
            "SELECT recall_id FROM recall_receipts ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return str(row["recall_id"]) if row is not None else None

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

    def decision_impacts_for_recall(self, recall_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM decision_impacts WHERE recall_id=? ORDER BY created_at, impact_id",
            (recall_id,),
        ).fetchall()
        out = []
        for row in rows:
            item = _row_to_dict(row)
            item["before"] = _loads(item["before_json"], {})
            item["after"] = _loads(item["after_json"], {})
            item["cited_record_ids"] = _loads(item["cited_record_ids"], [])
            out.append(item)
        return out

    def decision_impacts(self) -> list[dict[str, Any]]:
        """Read all compounding links for closeout/audit reporting."""
        rows = self._conn.execute(
            "SELECT * FROM decision_impacts ORDER BY created_at, impact_id"
        ).fetchall()
        out = []
        for row in rows:
            item = _row_to_dict(row)
            item["before"] = _loads(item["before_json"], {})
            item["after"] = _loads(item["after_json"], {})
            item["cited_record_ids"] = _loads(item["cited_record_ids"], [])
            out.append(item)
        return out

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

    # ── evidence manifests / items (P2.1 -- G0 needs a persisted manifest) ──

    def evidence_manifest_put(
        self,
        *,
        manifest_id: str,
        episode_id: str | None,
        required_types: list[str],
        items: list[dict],
        completeness: float,
        reasons: list[str],
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO evidence_manifests (manifest_id, episode_id, "
                "attempt_refs, required_types, present_items, completeness, reasons, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    manifest_id,
                    episode_id,
                    _json([]),
                    _json(required_types),
                    _json([i["evidence_id"] for i in items]),
                    completeness,
                    _json(reasons),
                    time.time(),
                ),
            )
            for item in items:
                cur.execute(
                    "INSERT OR IGNORE INTO evidence_items (evidence_id, manifest_id, type, uri, "
                    "content_hash, byte_size, media_encoding, captured_at, event_time, "
                    "source_actor, source_system, synthetic, redacted, access_class, "
                    "verification_status, verified_at, retention_hold, parent_evidence_id, "
                    "parser_version, origin, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item["evidence_id"],
                        manifest_id,
                        item["type"],
                        item["uri"],
                        item["content_hash"],
                        item.get("byte_size"),
                        item.get("media_encoding"),
                        item.get("captured_at"),
                        item.get("event_time"),
                        item.get("source_actor"),
                        item.get("source_system"),
                        1 if item.get("synthetic") else 0,
                        1 if item.get("redacted") else 0,
                        item.get("access_class"),
                        item.get("verification_status", "declared"),
                        item.get("verified_at"),
                        1 if item.get("retention_hold") else 0,
                        item.get("parent_evidence_id"),
                        item.get("parser_version"),
                        item.get("origin"),
                        time.time(),
                    ),
                )

    def evidence_items_for_manifest(self, manifest_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM evidence_items WHERE manifest_id=?", (manifest_id,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ── candidates / gate_results (BIN, I-7) ─────────────────────────────

    def candidate_create(
        self,
        *,
        candidate_id: str,
        hunt_id: str,
        assessment_id: str,
        evidence_manifest_id: str | None,
        gate_policy_version: str,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO candidates (candidate_id, hunt_id, assessment_id, "
                "evidence_manifest_id, alert_version, current_state, gate_policy_version, "
                "terminal_reason, queue_state, decided_by, decided_at, rationale, version, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    candidate_id,
                    hunt_id,
                    assessment_id,
                    evidence_manifest_id,
                    1,
                    "CREATED",
                    gate_policy_version,
                    None,
                    None,
                    None,
                    None,
                    None,
                    0,
                    time.time(),
                ),
            )

    def candidate_get(self, candidate_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        return _row_to_dict(row)

    def candidate_advance(
        self,
        candidate_id: str,
        target_state: str,
        *,
        expected_version: int,
        terminal_reason: str | None = None,
        rationale: str | None = None,
    ) -> None:
        """Compare-and-swap candidate-state transition (C7): rejects
        stale/illegal (skip-a-gate) transitions."""
        row = self.candidate_get(candidate_id)
        if row is None:
            raise StoreError(f"no such candidate: {candidate_id}")
        if row["version"] != expected_version:
            raise IllegalBinTransitionError(
                f"stale expected_version={expected_version} for candidate {candidate_id} "
                f"(current={row['version']})"
            )
        if not is_legal_bin_transition(row["current_state"], target_state):
            raise IllegalBinTransitionError(
                f"{row['current_state']} -> {target_state} is not a legal bin transition"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE candidates SET current_state=?, terminal_reason=?, rationale=?, "
                "version=version+1 WHERE candidate_id=? AND version=?",
                (target_state, terminal_reason, rationale, candidate_id, expected_version),
            )
            if cur.rowcount != 1:
                raise IllegalBinTransitionError(
                    f"concurrent modification of candidate {candidate_id}"
                )

    def candidate_resume(
        self, candidate_id: str, *, expected_version: int, target_state: str
    ) -> None:
        """Resume a BLOCKED/OPERATOR_ESCALATED candidate back into the main
        gate sequence at `target_state` (I-3/I-7 "resumption re-drives the
        specific gate that was blocked/escalated, not a generic hop").
        Deliberately bypasses `is_legal_bin_transition`'s blanket refusal
        for BLOCKED/OPERATOR_ESCALATED to bare-transition onward -- this
        *is* the dedicated resume path that refusal exists to force callers
        through, not a workaround of it. `target_state` must still be one
        of the main-sequence states (never PROMOTED/a terminal state)."""
        from .contracts import _BIN_MAIN_ORDER

        if target_state not in _BIN_MAIN_ORDER or target_state == "PROMOTED":
            raise IllegalBinTransitionError(
                f"candidate_resume target_state must be a main-sequence, non-terminal state, "
                f"got {target_state!r}"
            )
        row = self.candidate_get(candidate_id)
        if row is None:
            raise StoreError(f"no such candidate: {candidate_id}")
        if row["current_state"] not in ("BLOCKED", "OPERATOR_ESCALATED"):
            raise IllegalBinTransitionError(
                f"candidate_resume only applies from BLOCKED/OPERATOR_ESCALATED, "
                f"current state is {row['current_state']!r}"
            )
        if row["version"] != expected_version:
            raise IllegalBinTransitionError(
                f"stale expected_version={expected_version} for candidate {candidate_id}"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE candidates SET current_state=?, terminal_reason=NULL, version=version+1 "
                "WHERE candidate_id=? AND version=?",
                (target_state, candidate_id, expected_version),
            )
            if cur.rowcount != 1:
                raise IllegalBinTransitionError(
                    f"concurrent modification of candidate {candidate_id}"
                )

    def candidate_bump_alert_version(
        self, candidate_id: str, *, expected_version: int, new_evidence_manifest_id: str
    ) -> int:
        """A changed evidence manifest creates a new alert version and
        invalidates downstream passes (I-7 / SS4.8): the candidate rolls
        back to G_MINUS_1_PASS (scope/budget approval is evidence-independent
        and carries over; every evidence-dependent gate from G0 onward must
        re-run and can only write gate_results at the *new* alert_version,
        which the PROMOTED trigger's COUNT check requires)."""
        row = self.candidate_get(candidate_id)
        if row is None:
            raise StoreError(f"no such candidate: {candidate_id}")
        if row["version"] != expected_version:
            raise IllegalBinTransitionError(
                f"stale expected_version={expected_version} for candidate {candidate_id}"
            )
        new_alert_version = row["alert_version"] + 1
        with self._tx() as cur:
            cur.execute(
                "UPDATE candidates SET alert_version=?, evidence_manifest_id=?, "
                "current_state='G_MINUS_1_PASS', version=version+1 "
                "WHERE candidate_id=? AND version=?",
                (new_alert_version, new_evidence_manifest_id, candidate_id, expected_version),
            )
            if cur.rowcount != 1:
                raise IllegalBinTransitionError(
                    f"concurrent modification of candidate {candidate_id}"
                )
        return new_alert_version

    def gate_result_put(
        self,
        *,
        result_id: str,
        candidate_id: str,
        alert_version: int,
        gate_id: str,
        attempt: int,
        outcome: str,
        validator_version: str,
        inputs: dict,
        evidence: dict,
        checks: list,
        reasons: list,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO gate_results (result_id, candidate_id, alert_version, gate_id, "
                "attempt, outcome, validator_version, inputs_json, evidence_json, checks_json, "
                "reasons_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result_id,
                    candidate_id,
                    alert_version,
                    gate_id,
                    attempt,
                    outcome,
                    validator_version,
                    _json(inputs),
                    _json(evidence),
                    _json(checks),
                    _json(reasons),
                    time.time(),
                ),
            )

    def gate_results_for_candidate(
        self, candidate_id: str, *, alert_version: int | None = None
    ) -> list[dict]:
        if alert_version is None:
            rows = self._conn.execute(
                "SELECT * FROM gate_results WHERE candidate_id=? ORDER BY created_at ASC",
                (candidate_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM gate_results WHERE candidate_id=? AND alert_version=? "
                "ORDER BY created_at ASC",
                (candidate_id, alert_version),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def gate_next_attempt(self, candidate_id: str, alert_version: int, gate_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(attempt) AS n FROM gate_results WHERE candidate_id=? "
            "AND alert_version=? AND gate_id=?",
            (candidate_id, alert_version, gate_id),
        ).fetchone()
        return (row["n"] or 0) + 1

    # ── council (HEART, I-8) ──────────────────────────────────────────────

    def council_packet_put(
        self,
        *,
        packet_id: str,
        candidate_id: str,
        evidence_manifest_id: str | None,
        evidence_manifest_hash: str,
        roster_snapshot: dict,
        materiality_version: str,
        unresolved: bool,
        review_valid: bool,
        participation: float | None,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO council_packets (packet_id, candidate_id, evidence_manifest_id, "
                "evidence_manifest_hash, roster_snapshot, materiality_version, unresolved, "
                "review_valid, participation, superseded_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    packet_id,
                    candidate_id,
                    evidence_manifest_id,
                    evidence_manifest_hash,
                    _json(roster_snapshot),
                    materiality_version,
                    1 if unresolved else 0,
                    1 if review_valid else 0,
                    participation,
                    None,
                    time.time(),
                ),
            )

    def council_opinion_put(
        self,
        *,
        opinion_id: str,
        packet_id: str,
        seat_id: str,
        attempt: int,
        member_id: str,
        model: str,
        family: str,
        valid: bool,
        recommendation: str,
        confidence: float,
        error: str,
        findings: list,
        strongest_objection: str,
        missing_evidence: list,
        conditions_to_change: list,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO council_opinions (opinion_id, packet_id, seat_id, attempt, "
                "member_id, model, family, valid, error, recommendation, confidence, "
                "findings_json, strongest_objection, missing_evidence_json, "
                "conditions_to_change_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    opinion_id,
                    packet_id,
                    seat_id,
                    attempt,
                    member_id,
                    model,
                    family,
                    1 if valid else 0,
                    error,
                    recommendation,
                    confidence,
                    _json(findings),
                    strongest_objection,
                    _json(missing_evidence),
                    _json(conditions_to_change),
                    time.time(),
                ),
            )

    def objection_put(
        self,
        *,
        objection_id: str,
        packet_id: str,
        seat_id: str,
        category: str,
        material: bool,
        claim: str,
        evidence_citations: list,
        missing_proof_citations: list,
        status: str = "open",
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO objections (objection_id, packet_id, seat_id, category, material, "
                "claim, evidence_citations_json, missing_proof_citations_json, status, "
                "age_seconds, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    objection_id,
                    packet_id,
                    seat_id,
                    category,
                    1 if material else 0,
                    claim,
                    _json(evidence_citations),
                    _json(missing_proof_citations),
                    status,
                    0.0,
                    time.time(),
                ),
            )

    def objection_get(self, objection_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM objections WHERE objection_id=?", (objection_id,)
        ).fetchone()
        return _row_to_dict(row)

    def objection_set_status(self, objection_id: str, status: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE objections SET status=? WHERE objection_id=?", (status, objection_id)
            )

    def objections_for_packet(self, packet_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM objections WHERE packet_id=?", (packet_id,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def council_packet_get(self, packet_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM council_packets WHERE packet_id=?", (packet_id,)
        ).fetchone()
        return _row_to_dict(row)

    def council_opinions_for_packet(self, packet_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM council_opinions WHERE packet_id=?", (packet_id,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def rebuttals_for_objection(self, objection_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM rebuttals WHERE objection_id=?", (objection_id,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def council_packet_set_unresolved(self, packet_id: str, unresolved: bool) -> None:
        """Recompute-and-persist `unresolved` after a rebuttal/withdrawal/
        waiver changes an objection's status (I-8 "closure paths")."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE council_packets SET unresolved=? WHERE packet_id=?",
                (1 if unresolved else 0, packet_id),
            )

    def council_packet_finalize(
        self, packet_id: str, *, review_valid: bool, participation: float, unresolved: bool
    ) -> None:
        """`adversary.review` inserts the packet row before its seat
        opinions (opinions FK-reference the packet), then finalizes
        review_valid/participation/unresolved once all seats have answered
        and objections have been classified."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE council_packets SET review_valid=?, participation=?, unresolved=? "
                "WHERE packet_id=?",
                (1 if review_valid else 0, participation, 1 if unresolved else 0, packet_id),
            )

    def rebuttal_put(
        self,
        *,
        rebuttal_id: str,
        objection_id: str,
        author: str,
        claim: str,
        evidence_citations: list,
        requested_review: str | None,
        re_review_result: str | None,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO rebuttals (rebuttal_id, objection_id, author, claim, "
                "evidence_citations_json, requested_review, re_review_result, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    rebuttal_id,
                    objection_id,
                    author,
                    claim,
                    _json(evidence_citations),
                    requested_review,
                    re_review_result,
                    time.time(),
                ),
            )

    # ── promotion_queue (I-3/I-7, SS4.8) ─────────────────────────────────

    def promotion_enqueue(
        self, *, queue_id: str, item_kind: str, item_id: str, hunt_id: str | None
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO promotion_queue (queue_id, item_kind, item_id, hunt_id, state, "
                "enqueued_at, resolved_by, resolved_at, rationale) VALUES (?,?,?,?,?,?,?,?,?)",
                (queue_id, item_kind, item_id, hunt_id, "pending", time.time(), None, None, None),
            )

    def promotion_get(self, queue_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM promotion_queue WHERE queue_id=?", (queue_id,)
        ).fetchone()
        return _row_to_dict(row)

    def promotion_list(self, *, state: str | None = None) -> list[dict]:
        if state is None:
            rows = self._conn.execute(
                "SELECT * FROM promotion_queue ORDER BY enqueued_at ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM promotion_queue WHERE state=? ORDER BY enqueued_at ASC", (state,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def promotion_resolve(
        self, queue_id: str, *, actor: str, state: str, rationale: str = ""
    ) -> None:
        """I-5 / MASTER SS7: 'requires actor="operator:*"'; DB check (the
        002 migration's trg_promotion_queue_operator_only trigger) is the
        actual enforcement -- this raises the same class of refusal as a
        Python-level exception up front so the caller never even reaches
        the trigger for the common non-operator case, and the trigger
        still fires on any other write path (an operator SQL slip)."""
        if state not in ("confirmed", "rejected"):
            raise StoreError(f"promotion_resolve: unknown terminal state {state!r}")
        if not actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {actor!r} is not an operator; promotion_resolve requires "
                f"actor='operator:<id>'"
            )
        if state == "rejected" and not rationale.strip():
            raise StoreError("promotion_resolve: rejection requires a rationale")
        row = self.promotion_get(queue_id)
        if row is None:
            raise StoreError(f"no such promotion_queue item: {queue_id}")
        with self._tx() as cur:
            cur.execute(
                "UPDATE promotion_queue SET state=?, resolved_by=?, resolved_at=?, rationale=? "
                "WHERE queue_id=? AND state='pending'",
                (state, actor, time.time(), rationale, queue_id),
            )
            if cur.rowcount != 1:
                raise StoreError(
                    f"promotion_queue item {queue_id} was not in 'pending' state (already resolved?)"
                )

    def candidate_promote(
        self, candidate_id: str, *, expected_version: int, operator_actor: str, note: str = ""
    ) -> None:
        """AWAITING_OPERATOR -> PROMOTED. DB-enforced by
        trg_candidate_promote_requires_full_gate_chain (SS4.8) -- a
        candidate whose current alert_version does not have all seven
        gates passing raises sqlite3.IntegrityError here, never silently
        promotes."""
        if not operator_actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {operator_actor!r} is not an operator; candidate_promote requires "
                f"actor='operator:<id>'"
            )
        row = self.candidate_get(candidate_id)
        if row is None:
            raise StoreError(f"no such candidate: {candidate_id}")
        if row["version"] != expected_version:
            raise IllegalBinTransitionError(
                f"stale expected_version={expected_version} for candidate {candidate_id}"
            )
        if not is_legal_bin_transition(row["current_state"], "PROMOTED"):
            raise IllegalBinTransitionError(
                f"{row['current_state']} -> PROMOTED is not a legal bin transition"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE candidates SET current_state='PROMOTED', decided_by=?, decided_at=?, "
                "rationale=?, version=version+1 WHERE candidate_id=? AND version=?",
                (operator_actor, time.time(), note, candidate_id, expected_version),
            )
            if cur.rowcount != 1:
                raise IllegalBinTransitionError(
                    f"concurrent modification of candidate {candidate_id}"
                )

    def candidate_kill(
        self, candidate_id: str, *, expected_version: int, gate: str, rationale: str
    ) -> None:
        row = self.candidate_get(candidate_id)
        if row is None:
            raise StoreError(f"no such candidate: {candidate_id}")
        if row["version"] != expected_version:
            raise IllegalBinTransitionError(
                f"stale expected_version={expected_version} for candidate {candidate_id}"
            )
        if not is_legal_bin_transition(row["current_state"], "DISPROVED"):
            raise IllegalBinTransitionError(
                f"{row['current_state']} -> DISPROVED is not a legal bin transition"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE candidates SET current_state='DISPROVED', terminal_reason=?, "
                "decided_at=?, rationale=?, version=version+1 WHERE candidate_id=? AND version=?",
                (gate, time.time(), rationale, candidate_id, expected_version),
            )
            if cur.rowcount != 1:
                raise IllegalBinTransitionError(
                    f"concurrent modification of candidate {candidate_id}"
                )

    # ── soc_deliveries (G3, I-7a) ─────────────────────────────────────────

    def soc_delivery_put(
        self,
        *,
        delivery_id: str,
        candidate_id: str,
        correlation_key: str,
        destination: str | None,
        config_version: str | None,
        payload_hash: str,
        producer_ack: bool,
        consumer_query_ran: bool,
        consumer_triage_report: dict | None,
        priority: str | None,
        latency_s: float | None,
        content_hash_match: bool,
        load_profile: str | None,
        lifecycle_status: str = "sent",
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO soc_deliveries (delivery_id, candidate_id, correlation_key, "
                "destination, config_version, payload_hash, producer_ack, consumer_query_ran, "
                "consumer_triage_report, priority, latency_s, content_hash_match, load_profile, "
                "lifecycle_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    delivery_id,
                    candidate_id,
                    correlation_key,
                    destination,
                    config_version,
                    payload_hash,
                    1 if producer_ack else 0,
                    1 if consumer_query_ran else 0,
                    _json(consumer_triage_report) if consumer_triage_report is not None else None,
                    priority,
                    latency_s,
                    1 if content_hash_match else 0,
                    load_profile,
                    lifecycle_status,
                    time.time(),
                ),
            )

    def soc_delivery_get(self, delivery_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM soc_deliveries WHERE delivery_id=?", (delivery_id,)
        ).fetchone()
        return _row_to_dict(row)

    def soc_deliveries_for_candidate(self, candidate_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM soc_deliveries WHERE candidate_id=? ORDER BY created_at ASC",
            (candidate_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ── mutation plans (P3.1, I-1) ───────────────────────────────────────

    def mutation_plan_record(
        self,
        plan: MutationPlan,
        *,
        status: str,
        overlay: ScenarioOverlay | None = None,
        rejection_reason_code: str | None = None,
        rejection_detail: str | None = None,
    ) -> None:
        """Persist a validated-or-rejected `MutationPlan` (I-1 PROVENANCE).
        Idempotent on `idempotency_key`: re-recording the same plan is a
        no-op, not a duplicate row or an error."""
        if status not in ("validated", "rejected"):
            raise ValueError(f"unknown mutation plan status: {status!r}")
        existing = self._conn.execute(
            "SELECT 1 FROM mutation_plans WHERE idempotency_key=?", (plan.idempotency_key,)
        ).fetchone()
        if existing is not None:
            return
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO mutation_plans (plan_id, plan_version, reference_scenario, "
                "operators, invariants, expected_observables, controls, replay_policy, "
                "allowed_targets, allowed_tools, cleanup, approval_ref, budget_class, "
                "idempotency_key, proposer, status, rejection_reason_code, rejection_detail, "
                "overlay, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    plan.plan_id,
                    plan.plan_version,
                    plan.reference_scenario,
                    _json([op.to_dict() for op in plan.operators]),
                    _json(list(plan.invariants)),
                    _json(plan.expected_observables),
                    _json(list(plan.controls)),
                    plan.replay_policy,
                    _json(list(plan.allowed_targets)),
                    _json(list(plan.allowed_tools)),
                    _json(list(plan.cleanup)),
                    plan.approval_ref,
                    plan.budget_class,
                    plan.idempotency_key,
                    plan.proposer,
                    status,
                    rejection_reason_code,
                    rejection_detail,
                    _json(overlay.to_dict()) if overlay is not None else None,
                    plan.created_at,
                ),
            )

    def mutation_plan_get(self, plan_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM mutation_plans WHERE plan_id=?", (plan_id,)
        ).fetchone()
        return _row_to_dict(row)

    # ── drift baselines / flags (P3.2, I-9) ──────────────────────────────

    def detection_baseline_get(self, baseline_key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM detection_baselines WHERE baseline_key=?", (baseline_key,)
        ).fetchone()
        if row is None:
            return None
        d = _row_to_dict(row)
        d["window"] = _loads(d["window"], [])
        return d

    def detection_baselines_get_many(self, baseline_keys: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for key in baseline_keys:
            baseline = self.detection_baseline_get(key)
            if baseline is not None:
                out[key] = baseline
        return out

    def detection_baseline_upsert(self, baseline: dict) -> None:
        """Persist a `drift_engine.update`-returned baseline dict (DATA_MODEL
        SS1.8). `baseline_key` already encodes `(detection_id,
        policy_version)`, so a version change lands on a distinct row (the
        warm-up mechanism -- no special-cased supersede logic needed)."""
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO detection_baselines (baseline_key, detection_id, policy_version, "
                "status, window, sample_count, model_canary_ref, last_episode_id, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(baseline_key) DO UPDATE SET "
                "status=excluded.status, window=excluded.window, "
                "sample_count=excluded.sample_count, model_canary_ref=excluded.model_canary_ref, "
                "last_episode_id=excluded.last_episode_id, updated_at=excluded.updated_at",
                (
                    baseline["baseline_key"],
                    baseline["detection_id"],
                    baseline["policy_version"],
                    baseline["status"],
                    _json(baseline["window"]),
                    baseline["sample_count"],
                    baseline.get("model_canary_ref"),
                    baseline.get("last_episode_id"),
                    time.time(),
                ),
            )

    def drift_flag_record(self, flag: DriftFlag) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO drift_flags (flag_id, detection_id, episode_id, drift_class, "
                "status, score, signals, bands, breaches, consecutive_count, routed, detail, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    flag.flag_id,
                    flag.detection_id,
                    flag.episode_id,
                    flag.drift_class,
                    flag.status,
                    flag.score,
                    _json(flag.signals),
                    _json(flag.bands),
                    _json(flag.breaches),
                    flag.consecutive_count,
                    1 if flag.routed else 0,
                    flag.detail,
                    flag.created_at,
                ),
            )

    def drift_flags_for_detection(self, detection_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM drift_flags WHERE detection_id=? ORDER BY created_at ASC",
            (detection_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ── cost ledger (P4.1, I-13) ─────────────────────────────────────────

    def cost_ledger_put(self, record: CostRecord) -> None:
        """Append a `CostRecord` (DATA_MODEL SS1.12). Append-only, like
        `decision_events` -- a re-metered iteration produces a new row, it
        never overwrites a prior one."""
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO cost_ledger (record_id, hunt_id, iteration_id, components, "
                "pricing_profile_version, computed_units, quality_flag, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    record.record_id,
                    record.hunt_id,
                    record.iteration_id,
                    _json([c.to_dict() for c in record.components]),
                    record.pricing_profile_version,
                    record.computed_units,
                    1 if record.quality_flag else 0,
                    record.created_at,
                ),
            )

    def cost_ledger_for_hunt(self, hunt_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM cost_ledger WHERE hunt_id=? ORDER BY created_at ASC", (hunt_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = _row_to_dict(r)
            d["components"] = _loads(d["components"], [])
            d["quality_flag"] = bool(d["quality_flag"])
            out.append(d)
        return out

    def cost_ledger(self) -> list[dict]:
        """Read cross-hunt cost history for later ROI target selection."""
        rows = self._conn.execute(
            "SELECT * FROM cost_ledger ORDER BY created_at, record_id"
        ).fetchall()
        out = []
        for row in rows:
            item = _row_to_dict(row)
            item["components"] = _loads(item["components"], [])
            item["quality_flag"] = bool(item["quality_flag"])
            out.append(item)
        return out

    # ── plateaus (P4.4, I-12) ────────────────────────────────────────────

    def plateau_put(self, decision: PlateauDecision) -> None:
        """Persist a `PlateauDecision` (DATA_MODEL SS1.13). Append-only: a
        version-change reset produces a fresh row for the same
        neighborhood, never an update of the prior one (the prior row
        stays the audit trail of what was decided before the reset)."""
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO plateaus (plateau_id, hunt_id, neighborhood, qualifying_trial_ids, "
                "promotions, unique_response_gain, posterior_upper_bound, saturation, "
                "policy_version, decision, action, note, reset_trigger, reset_version, "
                "override, expiry, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    decision.plateau_id,
                    decision.hunt_id,
                    decision.neighborhood,
                    _json(list(decision.qualifying_trial_ids)),
                    decision.promotions,
                    decision.unique_response_gain,
                    decision.posterior_upper_bound,
                    decision.saturation,
                    decision.policy_version,
                    decision.decision,
                    decision.action,
                    decision.note,
                    decision.reset_trigger,
                    decision.reset_version,
                    _json(decision.override) if decision.override is not None else None,
                    decision.expiry,
                    decision.created_at,
                ),
            )

    def plateau_latest_for_neighborhood(self, neighborhood: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM plateaus WHERE neighborhood=? ORDER BY created_at DESC LIMIT 1",
            (neighborhood,),
        ).fetchone()
        if row is None:
            return None
        d = _row_to_dict(row)
        d["qualifying_trial_ids"] = _loads(d["qualifying_trial_ids"], [])
        d["override"] = _loads(d["override"], None)
        return d

    # ── detection_proposals (HND, P5.1, I-14) ────────────────────────────

    def detection_proposal_put(
        self,
        *,
        proposal_id: str,
        candidate_id: str,
        hunt_id: str | None,
        family: str,
        package: dict,
        content_hash: str,
        owner: str | None = None,
        expiry: float | None = None,
        artifacts_dir: str | None = None,
        supersedes: str | None = None,
    ) -> int:
        """Insert a new (draft) proposal version. `supersedes`, when given,
        marks the prior proposal_id superseded and this row's `version` one
        past it -- the "rebuild produces a superseding package version" /
        idempotency contract (I-14)."""
        version = 1
        with self._tx() as cur:
            if supersedes is not None:
                prior = cur.execute(
                    "SELECT version FROM detection_proposals WHERE proposal_id=?", (supersedes,)
                ).fetchone()
                if prior is None:
                    raise StoreError(f"cannot supersede {supersedes!r}: not found")
                version = prior["version"] + 1
                cur.execute(
                    "UPDATE detection_proposals SET superseded_by=? "
                    "WHERE proposal_id=? AND superseded_by IS NULL",
                    (proposal_id, supersedes),
                )
                if cur.rowcount != 1:
                    raise StoreError(
                        f"cannot supersede {supersedes!r}: not found or already superseded"
                    )
            cur.execute(
                "INSERT INTO detection_proposals (proposal_id, version, candidate_id, hunt_id, "
                "family, status, package_json, content_hash, owner, expiry, artifacts_dir, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    version,
                    candidate_id,
                    hunt_id,
                    family,
                    "draft",
                    _json(package),
                    content_hash,
                    owner,
                    expiry,
                    artifacts_dir,
                    time.time(),
                ),
            )
        return version

    def detection_proposal_get(self, proposal_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM detection_proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            d["package"] = _loads(d["package_json"], {})
            d["proof_legs"] = _loads(d["proof_legs_json"], {})
        return d

    def detection_proposal_latest_for_candidate(self, candidate_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM detection_proposals WHERE candidate_id=? ORDER BY version DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            d["package"] = _loads(d["package_json"], {})
            d["proof_legs"] = _loads(d["proof_legs_json"], {})
        return d

    def detection_proposal_set_proof_legs(
        self,
        proposal_id: str,
        *,
        fires_on_attack: bool,
        quiet_on_benign: bool,
        no_regression: bool,
        proof_legs: dict,
        regression_recipe_name: str | None = None,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE detection_proposals SET fires_on_attack=?, quiet_on_benign=?, "
                "no_regression=?, proof_legs_json=?, regression_recipe_name=? "
                "WHERE proposal_id=?",
                (
                    int(fires_on_attack),
                    int(quiet_on_benign),
                    int(no_regression),
                    _json(proof_legs),
                    regression_recipe_name,
                    proposal_id,
                ),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such detection_proposal: {proposal_id}")

    def detection_proposal_set_status(
        self, proposal_id: str, status: str, *, rationale: str | None = None
    ) -> None:
        """Advance `status` (closed enum, DB CHECK-enforced). The 'deployed'
        transition additionally raises `sqlite3.IntegrityError` unless all
        three proof legs are recorded pass (`trg_detection_proposal_deploy_
        requires_proof_legs`); 'rejected' likewise requires a rationale
        (`trg_detection_proposal_reject_requires_rationale`)."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE detection_proposals SET status=?, rationale=COALESCE(?, rationale) "
                "WHERE proposal_id=?",
                (status, rationale, proposal_id),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such detection_proposal: {proposal_id}")

    def detection_proposal_set_deployment(self, proposal_id: str, deployment_id: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE detection_proposals SET deployment_id=? WHERE proposal_id=?",
                (deployment_id, proposal_id),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such detection_proposal: {proposal_id}")

    def detection_proposal_set_coverage_validation_ref(self, proposal_id: str, ref: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE detection_proposals SET coverage_validation_ref=? WHERE proposal_id=?",
                (ref, proposal_id),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such detection_proposal: {proposal_id}")

    # ── deployments + replay_validations (operator commit receipt, P5.3) ──

    def deployment_put(
        self,
        *,
        deployment_id: str,
        proposal_id: str,
        spl_commit_ref: str,
        deployed_by: str,
        receipt_hash: str,
    ) -> str:
        """Content-derived `deployment_id`: a rebuild with the same
        (proposal_id, spl_commit_ref) is a no-op, not a duplicate row --
        'deployment ids deduplicate' (I-14 idempotency)."""
        existing = self._conn.execute(
            "SELECT deployment_id FROM deployments WHERE proposal_id=? AND spl_commit_ref=?",
            (proposal_id, spl_commit_ref),
        ).fetchone()
        if existing is not None:
            return existing["deployment_id"]
        if not deployed_by.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {deployed_by!r} is not an operator; deployment_put requires "
                f"actor='operator:<id>'"
            )
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO deployments (deployment_id, proposal_id, spl_commit_ref, "
                "deployed_by, receipt_hash, deployed_at) VALUES (?,?,?,?,?,?)",
                (
                    deployment_id,
                    proposal_id,
                    spl_commit_ref,
                    deployed_by,
                    receipt_hash,
                    time.time(),
                ),
            )
        return deployment_id

    def deployment_get(self, deployment_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM deployments WHERE deployment_id=?", (deployment_id,)
        ).fetchone()
        return _row_to_dict(row)

    def replay_validation_put(
        self,
        *,
        validation_id: str,
        deployment_id: str,
        passed: bool,
        noise_estimate: float | None = None,
        detail: str = "",
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO replay_validations (validation_id, deployment_id, passed, "
                "noise_estimate, detail, validated_at) VALUES (?,?,?,?,?,?)",
                (validation_id, deployment_id, int(passed), noise_estimate, detail, time.time()),
            )

    def replay_validations_for_deployment(self, deployment_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM replay_validations WHERE deployment_id=? ORDER BY validated_at ASC",
            (deployment_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ── playbooks (PLAY, P6.1/I-16) ─────────────────────────────────────

    def playbook_draft_put(
        self,
        *,
        playbook_id: str,
        scenario_class: str,
        content_hash: str,
        instruction_set: dict,
        source_hunts: list[str],
        supersedes: str | None = None,
    ) -> int:
        version = 1
        with self._tx() as cur:
            if supersedes is not None:
                prior = cur.execute(
                    "SELECT version FROM playbooks WHERE playbook_id=?", (supersedes,)
                ).fetchone()
                if prior is not None:
                    version = prior["version"] + 1
                    cur.execute(
                        "UPDATE playbooks SET superseded_by=? "
                        "WHERE playbook_id=? AND superseded_by IS NULL",
                        (playbook_id, supersedes),
                    )
            cur.execute(
                "INSERT INTO playbooks (playbook_id, scenario_class, version, content_hash, "
                "instruction_set_json, source_hunts_json, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    playbook_id,
                    scenario_class,
                    version,
                    content_hash,
                    _json(instruction_set),
                    _json(source_hunts),
                    "draft",
                    time.time(),
                ),
            )
        return version

    def playbook_get(self, playbook_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM playbooks WHERE playbook_id=?", (playbook_id,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            d["instruction_set"] = _loads(d["instruction_set_json"], {})
            d["source_hunts"] = _loads(d["source_hunts_json"], [])
        return d

    def playbook_active_for_class(self, scenario_class: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM playbooks WHERE scenario_class=? AND status='active'",
            (scenario_class,),
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            d["instruction_set"] = _loads(d["instruction_set_json"], {})
            d["source_hunts"] = _loads(d["source_hunts_json"], [])
        return d

    def playbook_set_status(
        self,
        playbook_id: str,
        status: str,
        *,
        replay_results: dict | None = None,
        canary_results: dict | None = None,
        revert_cause: str | None = None,
        activated_by: str | None = None,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE playbooks SET status=?, "
                "replay_results_json=COALESCE(?, replay_results_json), "
                "canary_results_json=COALESCE(?, canary_results_json), "
                "revert_cause=COALESCE(?, revert_cause), "
                "activated_by=COALESCE(?, activated_by), "
                "activated_at=CASE WHEN ?='active' THEN ? ELSE activated_at END "
                "WHERE playbook_id=?",
                (
                    status,
                    _json(replay_results) if replay_results is not None else None,
                    _json(canary_results) if canary_results is not None else None,
                    revert_cause,
                    activated_by,
                    status,
                    time.time(),
                    playbook_id,
                ),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such playbook: {playbook_id}")

    def playbook_activate(self, playbook_id: str, *, operator_actor: str) -> None:
        """Atomic pointer CAS (I-16): supersede the prior active playbook for
        the same scenario_class, then flip this one to 'active', inside a
        single transaction. The unique partial index
        (idx_playbooks_one_active_per_class) is the DB-level backstop if two
        callers race."""
        if not operator_actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {operator_actor!r} is not an operator; playbook_activate requires "
                f"actor='operator:<id>'"
            )
        row = self.playbook_get(playbook_id)
        if row is None:
            raise StoreError(f"no such playbook: {playbook_id}")
        with self._tx() as cur:
            prior = cur.execute(
                "SELECT playbook_id FROM playbooks WHERE scenario_class=? AND status='active'",
                (row["scenario_class"],),
            ).fetchone()
            if prior is not None:
                cur.execute(
                    "UPDATE playbooks SET status='retired', superseded_by=? "
                    "WHERE playbook_id=? AND status='active'",
                    (playbook_id, prior["playbook_id"]),
                )
            cur.execute(
                "UPDATE playbooks SET status='active', activated_by=?, activated_at=? "
                "WHERE playbook_id=?",
                (operator_actor, time.time(), playbook_id),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such playbook: {playbook_id}")

    # ── training_examples / dataset_versions (HARV, P6.2/I-15) ──────────

    def training_example_put(
        self,
        *,
        example_id: str,
        role: str,
        input_text: str,
        output_text: str,
        provenance: dict,
        group_family: str | None,
        group_campaign: str | None,
        group_time: str | None,
        leakage_flag: bool = False,
        oracle_flag: bool = False,
        is_negative: bool = False,
        is_adversarial: bool = False,
        is_distance_pair: bool = False,
        split: str | None = None,
        quarantine_reason: str | None = None,
    ) -> None:
        """Idempotent on `example_id` (content-derived) -- a re-harvest of
        the same source data is an INSERT OR IGNORE no-op (I-15
        IDEMPOTENCY)."""
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO training_examples (example_id, role, input_text, "
                "output_text, provenance_json, group_family, group_campaign, group_time, "
                "leakage_flag, oracle_flag, is_negative, is_adversarial, is_distance_pair, "
                "split, quarantine_reason, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    example_id,
                    role,
                    input_text,
                    output_text,
                    _json(provenance),
                    group_family,
                    group_campaign,
                    group_time,
                    int(leakage_flag),
                    int(oracle_flag),
                    int(is_negative),
                    int(is_adversarial),
                    int(is_distance_pair),
                    split,
                    quarantine_reason,
                    time.time(),
                ),
            )

    def training_examples_for_role(
        self, role: str, *, include_quarantined: bool = False
    ) -> list[dict]:
        if include_quarantined:
            rows = self._conn.execute(
                "SELECT * FROM training_examples WHERE role=?", (role,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM training_examples WHERE role=? AND quarantine_reason IS NULL",
                (role,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def dataset_version_put(
        self,
        *,
        dataset_version: str,
        role: str,
        window: dict,
        counts: dict,
        split_manifest: dict,
        dedup_leakage_report: dict,
        replay_mix_sources: list,
        manifest_path: str | None,
    ) -> bool:
        """Content-keyed: inserting a `dataset_version` that already exists
        is a no-op that returns False (I-15 'same window + config -> same
        content hash') rather than raising or duplicating."""
        existing = self._conn.execute(
            "SELECT dataset_version FROM dataset_versions WHERE dataset_version=?",
            (dataset_version,),
        ).fetchone()
        if existing is not None:
            return False
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO dataset_versions (dataset_version, role, window_json, counts_json, "
                "split_manifest_json, dedup_leakage_report_json, replay_mix_sources_json, "
                "manifest_path, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    dataset_version,
                    role,
                    _json(window),
                    _json(counts),
                    _json(split_manifest),
                    _json(dedup_leakage_report),
                    _json(replay_mix_sources),
                    manifest_path,
                    "built",
                    time.time(),
                ),
            )
        return True

    def dataset_version_get(self, dataset_version: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM dataset_versions WHERE dataset_version=?", (dataset_version,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            for k in ("window", "counts", "split_manifest", "dedup_leakage_report"):
                d[k] = _loads(d[f"{k}_json"], {})
            d["replay_mix_sources"] = _loads(d["replay_mix_sources_json"], [])
        return d

    def last_trained_dataset_for_role(self, role: str) -> dict | None:
        """Return the immutable dataset behind the role's latest TRAIN attempt."""
        row = self._conn.execute(
            "SELECT dv.dataset_version FROM dataset_versions AS dv "
            "JOIN trained_models AS tm ON tm.dataset_version=dv.dataset_version "
            "WHERE tm.role=? ORDER BY tm.created_at DESC LIMIT 1",
            (role,),
        ).fetchone()
        return self.dataset_version_get(row["dataset_version"]) if row is not None else None

    def dataset_version_release(
        self, dataset_version: str, *, operator_actor: str, approval_ref: str
    ) -> None:
        """I-15 'dataset release is a separate operator approval from model
        promotion' -- DB-enforced by trg_dataset_versions_release_operator_
        only."""
        if not operator_actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {operator_actor!r} is not an operator; dataset_version_release requires "
                f"actor='operator:<id>'"
            )
        with self._tx() as cur:
            cur.execute(
                "UPDATE dataset_versions SET status='released', released_by=?, released_at=?, "
                "approval_ref=? WHERE dataset_version=? AND status='built'",
                (operator_actor, time.time(), approval_ref, dataset_version),
            )
            if cur.rowcount != 1:
                raise StoreError(
                    f"dataset_version {dataset_version} not found or not in 'built' state"
                )

    # ── trained_models / model_aliases (TRAIN, P6.4/I-17) ────────────────

    def trained_model_put(
        self,
        *,
        model_tag: str,
        role: str,
        base_model: str,
        base_digest: str | None,
        dataset_version: str,
        seed: int,
        hyperparams: dict,
        toolchain_versions: dict,
        acceptance_policy_version: str,
        provenance: dict,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO trained_models (model_tag, role, base_model, base_digest, "
                "dataset_version, seed, hyperparams_json, toolchain_versions_json, "
                "acceptance_policy_version, verdict, provenance_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    model_tag,
                    role,
                    base_model,
                    base_digest,
                    dataset_version,
                    seed,
                    _json(hyperparams),
                    _json(toolchain_versions),
                    acceptance_policy_version,
                    "pending",
                    _json(provenance),
                    time.time(),
                ),
            )

    def trained_model_get(self, model_tag: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM trained_models WHERE model_tag=?", (model_tag,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            for k in ("hyperparams", "toolchain_versions", "provenance"):
                d[k] = _loads(d[f"{k}_json"], {})
            for k in ("acceptance_report", "intake_report", "canary_report"):
                d[k] = _loads(d.get(f"{k}_json"), None)
        return d

    def trained_model_set_reports(
        self,
        model_tag: str,
        *,
        gguf_path: str | None = None,
        gguf_hash: str | None = None,
        acceptance_report: dict | None = None,
        intake_report: dict | None = None,
        canary_report: dict | None = None,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "UPDATE trained_models SET "
                "gguf_path=COALESCE(?, gguf_path), gguf_hash=COALESCE(?, gguf_hash), "
                "acceptance_report_json=COALESCE(?, acceptance_report_json), "
                "intake_report_json=COALESCE(?, intake_report_json), "
                "canary_report_json=COALESCE(?, canary_report_json) WHERE model_tag=?",
                (
                    gguf_path,
                    gguf_hash,
                    _json(acceptance_report) if acceptance_report is not None else None,
                    _json(intake_report) if intake_report is not None else None,
                    _json(canary_report) if canary_report is not None else None,
                    model_tag,
                ),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such trained_model: {model_tag}")

    def trained_model_set_verdict(
        self, model_tag: str, verdict: str, *, operator_actor: str | None = None
    ) -> None:
        """'served' is DB-enforced operator-only
        (trg_trained_models_serve_operator_only); every other terminal
        verdict (rejected/declined_no_gain/training_failed/rolled_back) is a
        system-recorded outcome, never requiring an operator actor (I-17
        FAILURE SEMANTICS: acceptance-fail is recorded automatically)."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE trained_models SET verdict=?, served_by=COALESCE(?, served_by), "
                "served_at=CASE WHEN ?='served' THEN ? ELSE served_at END WHERE model_tag=?",
                (verdict, operator_actor, verdict, time.time(), model_tag),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such trained_model: {model_tag}")

    def model_alias_get(self, role: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM model_aliases WHERE role=?", (role,)).fetchone()
        return _row_to_dict(row)

    def model_alias_promote(
        self, role: str, model_tag: str, *, operator_actor: str, model_tag_field: str = "model_tag"
    ) -> None:
        """Atomic alias re-point (I-17 'atomic promotion' / MASTER SS8
        'canary rollback = alias re-point'). `model_aliases` is one row per
        role -- an UPSERT is inherently the whole promotion, and
        `previous_model_tag` is what a rollback re-points back to."""
        if not operator_actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {operator_actor!r} is not an operator; model_alias_promote requires "
                f"actor='operator:<id>'"
            )
        current = self.model_alias_get(role)
        previous = current["model_tag"] if current is not None else None
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO model_aliases (role, model_tag, previous_model_tag, updated_by, "
                "updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(role) DO UPDATE SET model_tag=excluded.model_tag, "
                "previous_model_tag=?, updated_by=excluded.updated_by, "
                "updated_at=excluded.updated_at",
                (role, model_tag, previous, operator_actor, time.time(), previous),
            )
            cur.execute(
                "INSERT INTO model_alias_history (history_id, role, model_tag, action, actor, "
                "reason, at) VALUES (?,?,?,?,?,?,?)",
                (
                    f"mah-{uuid.uuid4().hex[:12]}",
                    role,
                    model_tag,
                    "promote",
                    operator_actor,
                    None,
                    time.time(),
                ),
            )

    def model_alias_rollback(self, role: str, *, operator_actor: str, reason: str) -> str | None:
        """Re-point the role's active alias back to `previous_model_tag`
        (canary regression -> atomic rollback, I-17). Returns the tag rolled
        back to, or None if there was nothing to roll back."""
        if not operator_actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {operator_actor!r} is not an operator; model_alias_rollback requires "
                f"actor='operator:<id>'"
            )
        current = self.model_alias_get(role)
        if current is None or current["previous_model_tag"] is None:
            return None
        target = current["previous_model_tag"]
        with self._tx() as cur:
            cur.execute(
                "UPDATE model_aliases SET model_tag=?, previous_model_tag=?, updated_by=?, "
                "updated_at=? WHERE role=?",
                (target, current["model_tag"], operator_actor, time.time(), role),
            )
            cur.execute(
                "INSERT INTO model_alias_history (history_id, role, model_tag, action, actor, "
                "reason, at) VALUES (?,?,?,?,?,?,?)",
                (
                    f"mah-{uuid.uuid4().hex[:12]}",
                    role,
                    target,
                    "rollback",
                    operator_actor,
                    reason,
                    time.time(),
                ),
            )
        return target

    # ── roster_records (ROSTER, P6.5/I-19) ────────────────────────────────

    def roster_record_put(
        self,
        *,
        record_id: str,
        seat_id: str,
        window: dict,
        independence_family: str | None,
        capability_suite_version: str | None,
        citation_validity: float | None,
        objection_precision: float | None,
        objection_recall: float | None,
        cousin_call_correctness: float | None,
        abstention_quality: float | None,
        latency_cost: dict,
        eligibility: str,
        advisory_weight: float,
        rationale: dict,
        content_key: str,
    ) -> str | None:
        """Content-keyed idempotency (I-19): re-running `recompute` for the
        same (seat, window, inputs) is a no-op that returns None instead of
        inserting a duplicate row."""
        existing = self._conn.execute(
            "SELECT record_id FROM roster_records WHERE content_key=?", (content_key,)
        ).fetchone()
        if existing is not None:
            return None
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO roster_records (record_id, seat_id, window_json, "
                "independence_family, capability_suite_version, citation_validity, "
                "objection_precision, objection_recall, cousin_call_correctness, "
                "abstention_quality, latency_cost_json, eligibility, advisory_weight, "
                "rationale_json, content_key, state, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record_id,
                    seat_id,
                    _json(window),
                    independence_family,
                    capability_suite_version,
                    citation_validity,
                    objection_precision,
                    objection_recall,
                    cousin_call_correctness,
                    abstention_quality,
                    _json(latency_cost),
                    eligibility,
                    advisory_weight,
                    _json(rationale),
                    content_key,
                    "proposed",
                    time.time(),
                ),
            )
        return record_id

    def roster_record_get(self, record_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM roster_records WHERE record_id=?", (record_id,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            d["window"] = _loads(d["window_json"], {})
            d["latency_cost"] = _loads(d["latency_cost_json"], {})
            d["rationale"] = _loads(d["rationale_json"], {})
        return d

    def roster_active_for_seat(self, seat_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM roster_records WHERE seat_id=? AND state='active'", (seat_id,)
        ).fetchone()
        d = _row_to_dict(row)
        if d is not None:
            d["window"] = _loads(d["window_json"], {})
            d["latency_cost"] = _loads(d["latency_cost_json"], {})
            d["rationale"] = _loads(d["rationale_json"], {})
        return d

    def roster_active_all(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM roster_records WHERE state='active'").fetchall()
        out = []
        for row in rows:
            d = _row_to_dict(row)
            d["window"] = _loads(d["window_json"], {})
            d["latency_cost"] = _loads(d["latency_cost_json"], {})
            d["rationale"] = _loads(d["rationale_json"], {})
            out.append(d)
        return out

    def roster_record_activate(self, record_id: str, *, operator_actor: str) -> None:
        """Confirm-only activation (I-19); supersedes the seat's prior active
        record inside the same transaction (mirrors playbook_activate's CAS
        pattern)."""
        if not operator_actor.startswith("operator:"):
            raise OperatorActorRequiredError(
                f"actor {operator_actor!r} is not an operator; roster_record_activate requires "
                f"actor='operator:<id>'"
            )
        row = self.roster_record_get(record_id)
        if row is None:
            raise StoreError(f"no such roster_record: {record_id}")
        with self._tx() as cur:
            prior = cur.execute(
                "SELECT record_id FROM roster_records WHERE seat_id=? AND state='active'",
                (row["seat_id"],),
            ).fetchone()
            if prior is not None:
                cur.execute(
                    "UPDATE roster_records SET state='proposed', superseded_by=? "
                    "WHERE record_id=? AND state='active'",
                    (record_id, prior["record_id"]),
                )
            cur.execute(
                "UPDATE roster_records SET state='active', activated_by=?, activated_at=? "
                "WHERE record_id=?",
                (operator_actor, time.time(), record_id),
            )
            if cur.rowcount != 1:
                raise StoreError(f"no such roster_record: {record_id}")

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
