-- 001_init.sql -- P1 subset of SUB tables (DATA_MODEL SS1 table order).
-- Later phases append migrations 002_*.sql, 003_*.sql, ... ; never edit this
-- file after it has shipped (ordered-migration discipline, MASTER SS10).

PRAGMA foreign_keys = ON;

-- schema_migrations itself is created by store.py::Store._migrate() before
-- any numbered migration runs (it is the ledger *of* the numbered
-- migrations, not one of them).

CREATE TABLE hunts (
    hunt_id             TEXT PRIMARY KEY,
    objective           TEXT NOT NULL,
    neighborhood_scope  TEXT NOT NULL,
    authorization_ref   TEXT NOT NULL,
    config_version      TEXT NOT NULL,
    role_snapshot       TEXT NOT NULL,
    budgets             TEXT NOT NULL,
    budgets_used        TEXT NOT NULL DEFAULT '{}',
    stage               TEXT NOT NULL,
    status              TEXT NOT NULL,
    stop_reason         TEXT,
    lease_owner         TEXT,
    lease_expiry        REAL,
    version             INTEGER NOT NULL DEFAULT 0,
    parent_hunt_id      TEXT,
    started_at          REAL NOT NULL,
    ended_at            REAL
);

CREATE TABLE iterations (
    iteration_id            TEXT PRIMARY KEY,
    hunt_id                 TEXT NOT NULL REFERENCES hunts(hunt_id),
    seq                     INTEGER NOT NULL,
    target_cell             TEXT,
    mutation_plan_id        TEXT,
    episode_id              TEXT,
    assessment_id           TEXT,
    outcome                 TEXT,
    infrastructure_status   TEXT,
    created_at              REAL NOT NULL,
    UNIQUE (hunt_id, seq)
);

-- Append-only, hash-chained provenance backbone (DATA_MODEL SS1.9). No
-- application-level UPDATE/DELETE path is ever exposed through store.py.
CREATE TABLE decision_events (
    event_id            TEXT PRIMARY KEY,
    hunt_id              TEXT,
    iteration_id         TEXT,
    actor                TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    subject_id           TEXT NOT NULL,
    rationale            TEXT NOT NULL,
    data                 TEXT NOT NULL DEFAULT '{}',
    prev_event_hash      TEXT,
    chain_hash           TEXT NOT NULL,
    occurred_at          REAL NOT NULL,
    recorded_at          REAL NOT NULL
);
CREATE INDEX idx_decision_events_hunt ON decision_events(hunt_id, recorded_at);

-- Append-only enforcement at the DB level, not just application discipline:
-- no code path (and no operator SQL slip) can update or delete a landed
-- decision event.
CREATE TRIGGER trg_decision_events_no_update
BEFORE UPDATE ON decision_events
BEGIN
    SELECT RAISE(ABORT, 'decision_events is append-only: UPDATE is forbidden');
END;

CREATE TRIGGER trg_decision_events_no_delete
BEFORE DELETE ON decision_events
BEGIN
    SELECT RAISE(ABORT, 'decision_events is append-only: DELETE is forbidden');
END;

CREATE TABLE evidence_manifests (
    manifest_id       TEXT PRIMARY KEY,
    episode_id        TEXT,
    attempt_refs      TEXT NOT NULL DEFAULT '[]',
    required_types    TEXT NOT NULL DEFAULT '[]',
    present_items     TEXT NOT NULL DEFAULT '[]',
    completeness      REAL NOT NULL DEFAULT 0.0,
    reasons           TEXT NOT NULL DEFAULT '[]',
    created_at        REAL NOT NULL
);

CREATE TABLE evidence_items (
    evidence_id           TEXT PRIMARY KEY,
    manifest_id           TEXT REFERENCES evidence_manifests(manifest_id),
    type                  TEXT NOT NULL,
    uri                   TEXT NOT NULL,
    content_hash          TEXT NOT NULL,
    byte_size             INTEGER,
    media_encoding        TEXT,
    captured_at           REAL,
    event_time            REAL,
    source_actor          TEXT,
    source_system         TEXT,
    synthetic             INTEGER NOT NULL DEFAULT 0,
    redacted              INTEGER NOT NULL DEFAULT 0,
    access_class          TEXT,
    verification_status   TEXT NOT NULL DEFAULT 'declared',
    verified_at           REAL,
    retention_hold        INTEGER NOT NULL DEFAULT 0,
    parent_evidence_id    TEXT,
    parser_version        TEXT,
    created_at            REAL NOT NULL
);

CREATE TABLE behavior_signatures (
    signature_id              TEXT PRIMARY KEY,
    episode_ref                TEXT NOT NULL,
    signature_algorithm_version TEXT NOT NULL,
    input_manifest_hash        TEXT NOT NULL,
    canonical_fingerprint       TEXT NOT NULL,
    action_sequence             TEXT NOT NULL DEFAULT '[]',
    event_graph                 TEXT NOT NULL DEFAULT '{}',
    parameter_families          TEXT NOT NULL DEFAULT '{}',
    context_topology            TEXT NOT NULL DEFAULT '{}',
    artifacts                   TEXT NOT NULL DEFAULT '{}',
    attack_mappings              TEXT NOT NULL DEFAULT '[]',
    telemetry_shape              TEXT NOT NULL DEFAULT '{}',
    detector_outcomes            TEXT NOT NULL DEFAULT '{}',
    evidence_manifest_id          TEXT REFERENCES evidence_manifests(manifest_id),
    completeness                  REAL NOT NULL DEFAULT 1.0,
    created_at                    REAL NOT NULL,
    UNIQUE (episode_ref, signature_algorithm_version, input_manifest_hash)
);

CREATE TABLE cousin_assessments (
    assessment_id           TEXT PRIMARY KEY,
    subject_signature_id     TEXT NOT NULL REFERENCES behavior_signatures(signature_id),
    reference_signature_id   TEXT REFERENCES behavior_signatures(signature_id),
    candidate_set_id          TEXT NOT NULL,
    d_behavior                REAL,
    d_telemetry                REAL,
    d_semantic                 REAL,
    d_attack                    REAL,
    d_context                   REAL,
    composite                    REAL NOT NULL,
    relationship                 TEXT NOT NULL,
    nonsemantic_channels          INTEGER NOT NULL,
    vetoes                        TEXT NOT NULL DEFAULT '[]',
    defense_response               TEXT NOT NULL,
    nearest_knowns                  TEXT NOT NULL DEFAULT '[]',
    confidence                       REAL NOT NULL,
    completeness                      REAL NOT NULL,
    algorithm_version                 TEXT NOT NULL,
    thresholds_version                 TEXT NOT NULL,
    explanation                         TEXT NOT NULL DEFAULT '{}',
    superseded_by                        TEXT,
    created_at                            REAL NOT NULL
);

CREATE TABLE known_state (
    entry_id                  TEXT PRIMARY KEY,
    subject                   TEXT NOT NULL,
    kind                      TEXT NOT NULL,
    trust_tier                TEXT NOT NULL,
    posterior_adjustment      TEXT NOT NULL DEFAULT '{}',
    applicability             TEXT NOT NULL DEFAULT '{}',
    confidence_half_life_days REAL,
    evidence                  TEXT NOT NULL,
    contradiction_links       TEXT NOT NULL DEFAULT '[]',
    superseded_by             TEXT,
    created_at                REAL NOT NULL,
    hunt_id                   TEXT
);

CREATE TABLE index_outbox (
    outbox_id            TEXT PRIMARY KEY,
    record_type           TEXT NOT NULL,
    record_id              TEXT NOT NULL,
    record_version           INTEGER NOT NULL DEFAULT 0,
    projection_version        TEXT NOT NULL,
    source_hash                 TEXT NOT NULL,
    operation                    TEXT NOT NULL,
    required_for_closure          INTEGER NOT NULL DEFAULT 0,
    status                         TEXT NOT NULL DEFAULT 'pending',
    attempts                        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at                  REAL,
    error                              TEXT,
    completed_at                       REAL,
    projected_row_hash                  TEXT,
    payload                              TEXT NOT NULL DEFAULT '{}',
    created_at                            REAL NOT NULL,
    UNIQUE (record_type, record_id, record_version, projection_version)
);

CREATE TABLE recall_receipts (
    recall_id           TEXT PRIMARY KEY,
    hunt_id              TEXT NOT NULL,
    query                 TEXT NOT NULL,
    filters                TEXT NOT NULL DEFAULT '{}',
    trust_policy             TEXT NOT NULL DEFAULT '{}',
    projection_version         TEXT,
    embedding_version            TEXT,
    reranker_version               TEXT,
    source_health                    TEXT NOT NULL DEFAULT '{}',
    candidates                        TEXT NOT NULL DEFAULT '[]',
    exclusions                         TEXT NOT NULL DEFAULT '[]',
    selected_context                    TEXT NOT NULL DEFAULT '[]',
    token_budget                         INTEGER,
    created_at                            REAL NOT NULL
);
CREATE INDEX idx_recall_receipts_hunt ON recall_receipts(hunt_id, created_at);

CREATE TABLE decision_impacts (
    impact_id                TEXT PRIMARY KEY,
    recall_id                 TEXT NOT NULL REFERENCES recall_receipts(recall_id),
    consuming_decision_ref      TEXT NOT NULL,
    before_json                   TEXT NOT NULL DEFAULT '{}',
    after_json                     TEXT NOT NULL DEFAULT '{}',
    cited_record_ids                 TEXT NOT NULL DEFAULT '[]',
    change_kind                       TEXT NOT NULL,
    explanation                        TEXT NOT NULL,
    created_at                          REAL NOT NULL
);
