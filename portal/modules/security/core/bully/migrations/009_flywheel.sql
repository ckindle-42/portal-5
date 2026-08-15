-- 009_flywheel.sql -- P6: HARV/PLAY/TRAIN/ROSTER flywheel tables (DATA_MODEL
-- SS1.15-1.17, M8). Additive only; prior migrations are never edited after
-- shipping (MASTER SS10 ordered-migration discipline).

PRAGMA foreign_keys = ON;

-- ── playbooks (PLAY, I-16) ───────────────────────────────────────────────
--
-- One row per drafted/activated version of a scenario class's learned
-- playbook. Lifecycle DRAFT -> REPLAY_VALIDATED -> CANARY ->
-- AWAITING_OPERATOR -> ACTIVE -> RETIRED (or ROLLED_BACK on canary
-- failure). `version` + `expected_version` CAS mirrors
-- `candidates.version` (store.candidate_promote precedent).
CREATE TABLE playbooks (
    playbook_id          TEXT PRIMARY KEY,
    scenario_class            TEXT NOT NULL,
    version                        INTEGER NOT NULL DEFAULT 1,
    content_hash                        TEXT NOT NULL,
    instruction_set_json                    TEXT NOT NULL DEFAULT '{}',
    source_hunts_json                            TEXT NOT NULL DEFAULT '[]',
    status                                            TEXT NOT NULL DEFAULT 'draft'
                                                           CHECK (status IN
                                                           ('draft','replay_validated','canary',
                                                            'awaiting_operator','active','retired',
                                                            'rolled_back')),
    replay_results_json                                       TEXT,
    canary_results_json                                           TEXT,
    revert_cause                                                      TEXT,
    activated_by                                                          TEXT,
    activated_at                                                              REAL,
    superseded_by                                                                TEXT,
    created_at                                                                      REAL NOT NULL
);
CREATE INDEX idx_playbooks_class ON playbooks(scenario_class, version);

-- SS4.8 "one active playbook per class" -- a partial unique index is the
-- DB-level backstop; the atomic-pointer CAS in store.playbook_activate is
-- the application-level half.
CREATE UNIQUE INDEX idx_playbooks_one_active_per_class
    ON playbooks(scenario_class) WHERE status = 'active';

-- I-16 "activation is confirm-only": mirrors trg_promotion_queue_operator_
-- only / trg_candidate_promote's operator-prefix checks -- any UPDATE that
-- moves a playbook to 'active' must carry an operator-prefixed activated_by.
CREATE TRIGGER trg_playbooks_activation_operator_only
BEFORE UPDATE OF status ON playbooks
WHEN NEW.status = 'active'
BEGIN
    SELECT RAISE(ABORT, 'playbook activation requires actor=''operator:*''')
    WHERE NEW.activated_by IS NULL OR NEW.activated_by NOT LIKE 'operator:%';
END;

-- ── training_examples + dataset_versions + trained_models (TRAIN/HARV) ────
--
-- `training_examples`: role-tagged corpus rows (I-15). `example_id` is
-- content/evidence-derived so a re-harvest of the same window is idempotent
-- (I-15 IDEMPOTENCY). Quarantine is first-class: a row with a non-null
-- `quarantine_reason` is never included in a built dataset (I-15 FAILURE
-- SEMANTICS "quarantine, never silent inclusion").
CREATE TABLE training_examples (
    example_id            TEXT PRIMARY KEY,
    role                       TEXT NOT NULL
                                   CHECK (role IN ('hunter','analyst','disprover','cousin_smeller')),
    input_text                        TEXT NOT NULL,
    output_text                            TEXT NOT NULL,
    provenance_json                            TEXT NOT NULL DEFAULT '{}',
    group_family                                   TEXT,
    group_campaign                                     TEXT,
    group_time                                             TEXT,
    leakage_flag                                               INTEGER NOT NULL DEFAULT 0,
    oracle_flag                                                    INTEGER NOT NULL DEFAULT 0,
    is_negative                                                        INTEGER NOT NULL DEFAULT 0,
    is_adversarial                                                         INTEGER NOT NULL DEFAULT 0,
    is_distance_pair                                                           INTEGER NOT NULL DEFAULT 0,
    consent_class                                                                  TEXT NOT NULL DEFAULT 'internal',
    split                                                                              TEXT
                                                                                            CHECK (split IN
                                                                                            ('train','val','test') OR split IS NULL),
    quarantine_reason                                                                      TEXT,
    transformation_version                                                                     TEXT NOT NULL DEFAULT '1',
    superseded_by                                                                                  TEXT,
    created_at                                                                                        REAL NOT NULL
);
CREATE INDEX idx_training_examples_role ON training_examples(role, quarantine_reason);

-- `dataset_versions`: immutable-after-release manifest for a built dataset
-- (I-15 "same window + config -> same content hash"; a corrected label
-- forces a *new* dataset_version row, never an in-place edit of a released
-- one -- I-15 IDEMPOTENCY).
CREATE TABLE dataset_versions (
    dataset_version         TEXT PRIMARY KEY,
    role                        TEXT NOT NULL,
    window_json                     TEXT NOT NULL DEFAULT '{}',
    counts_json                          TEXT NOT NULL DEFAULT '{}',
    split_manifest_json                       TEXT NOT NULL DEFAULT '{}',
    dedup_leakage_report_json                      TEXT NOT NULL DEFAULT '{}',
    replay_mix_sources_json                            TEXT NOT NULL DEFAULT '[]',
    manifest_path                                          TEXT,
    status                                                     TEXT NOT NULL DEFAULT 'built'
                                                                    CHECK (status IN ('built','released')),
    approval_ref                                                   TEXT,
    released_by                                                        TEXT,
    released_at                                                            REAL,
    created_at                                                                 REAL NOT NULL
);

-- I-15 "dataset build is operator-initiated; dataset release is a separate
-- operator approval from model promotion": release requires an operator
-- actor, mirroring trg_deployment_operator_only.
CREATE TRIGGER trg_dataset_versions_release_operator_only
BEFORE UPDATE OF status ON dataset_versions
WHEN NEW.status = 'released'
BEGIN
    SELECT RAISE(ABORT, 'dataset_versions release requires actor=''operator:*''')
    WHERE NEW.released_by IS NULL OR NEW.released_by NOT LIKE 'operator:%';
END;

-- DATA_MODEL SS4.4 "TRAINING artifacts immutable": once released, a
-- dataset_versions row accepts no further writes at all (release is
-- terminal -- a correction supersedes via a brand-new dataset_version row,
-- never an in-place mutation of a released one).
CREATE TRIGGER trg_dataset_versions_immutable_after_release
BEFORE UPDATE ON dataset_versions
WHEN OLD.status = 'released'
BEGIN
    SELECT RAISE(ABORT, 'dataset_versions is immutable once released');
END;

-- `trained_models`: one row per TRAIN run's candidate artifact (I-17).
CREATE TABLE trained_models (
    model_tag              TEXT PRIMARY KEY,
    role                       TEXT NOT NULL,
    base_model                    TEXT NOT NULL,
    base_digest                       TEXT,
    dataset_version                       TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
    seed                                       INTEGER NOT NULL,
    hyperparams_json                              TEXT NOT NULL DEFAULT '{}',
    toolchain_versions_json                           TEXT NOT NULL DEFAULT '{}',
    gguf_path                                             TEXT,
    gguf_hash                                                 TEXT,
    five_arm_report_json                                          TEXT,
    intake_report_json                                                TEXT,
    canary_report_json                                                    TEXT,
    acceptance_policy_version                                                 TEXT NOT NULL,
    verdict                                                                       TEXT NOT NULL DEFAULT 'pending'
                                                                                       CHECK (verdict IN
                                                                                       ('pending','served','rejected',
                                                                                        'rolled_back','declined_no_gain',
                                                                                        'training_failed')),
    provenance_json                                                                       TEXT NOT NULL DEFAULT '{}',
    active_alias_before                                                                       TEXT,
    active_alias_after                                                                            TEXT,
    created_at                                                                                        REAL NOT NULL,
    served_by                                                                                             TEXT,
    served_at                                                                                                 REAL
);
CREATE INDEX idx_trained_models_role ON trained_models(role, verdict);

-- I-17 "NO serving change without operator confirm": a 'served' verdict
-- requires an operator-prefixed served_by, mirroring
-- trg_promotion_queue_operator_only.
CREATE TRIGGER trg_trained_models_serve_operator_only
BEFORE UPDATE OF verdict ON trained_models
WHEN NEW.verdict = 'served'
BEGIN
    SELECT RAISE(ABORT, 'trained_models serve requires actor=''operator:*''')
    WHERE NEW.served_by IS NULL OR NEW.served_by NOT LIKE 'operator:%';
END;

-- DATA_MODEL SS4.4 "TRAINING artifacts immutable": the artifact identity
-- fields never change after the row is created; `gguf_path`/`gguf_hash` are
-- allowed exactly one write (the training run's own
-- `trained_model_set_reports` call, from NULL to a value) and are then
-- frozen -- everything else (dataset_version/base_model/hyperparams/seed)
-- is fixed at INSERT and never updated by any code path.
CREATE TRIGGER trg_trained_models_immutable_core
BEFORE UPDATE ON trained_models
BEGIN
    SELECT RAISE(ABORT, 'trained_models artifact fields are immutable once recorded')
    WHERE (OLD.gguf_path IS NOT NULL AND NEW.gguf_path IS NOT OLD.gguf_path)
       OR (OLD.gguf_hash IS NOT NULL AND NEW.gguf_hash IS NOT OLD.gguf_hash)
       OR NEW.dataset_version IS NOT OLD.dataset_version
       OR NEW.base_model IS NOT OLD.base_model
       OR NEW.hyperparams_json IS NOT OLD.hyperparams_json
       OR NEW.seed IS NOT OLD.seed;
END;

-- ── model_aliases (one active model alias per role, I-17) ─────────────────
--
-- A one-row-per-role table is the simplest DB-level way to guarantee "one
-- active model alias per role" (SS4.8): the primary key *is* the
-- uniqueness constraint. Canary rollback = alias re-point (an UPDATE, not
-- a new row) -- MASTER SS8 "training failure -> active alias unchanged".
CREATE TABLE model_aliases (
    role                  TEXT PRIMARY KEY,
    model_tag                 TEXT NOT NULL,
    previous_model_tag             TEXT,
    updated_by                         TEXT NOT NULL,
    updated_at                             REAL NOT NULL
);

CREATE TABLE model_alias_history (
    history_id            TEXT PRIMARY KEY,
    role                       TEXT NOT NULL,
    model_tag                     TEXT NOT NULL,
    action                            TEXT NOT NULL CHECK (action IN ('promote','rollback')),
    actor                                 TEXT NOT NULL,
    reason                                    TEXT,
    at                                           REAL NOT NULL
);
CREATE INDEX idx_model_alias_history_role ON model_alias_history(role, at);

-- ── roster_records (ROSTER, I-19) ──────────────────────────────────────────

CREATE TABLE roster_records (
    record_id             TEXT PRIMARY KEY,
    seat_id                    TEXT NOT NULL,
    window_json                     TEXT NOT NULL DEFAULT '{}',
    independence_family                 TEXT,
    capability_suite_version                TEXT,
    citation_validity                           REAL,
    objection_precision                             REAL,
    objection_recall                                    REAL,
    cousin_call_correctness                                 REAL,
    abstention_quality                                          REAL,
    latency_cost_json                                               TEXT NOT NULL DEFAULT '{}',
    eligibility                                                         TEXT NOT NULL
                                                                             CHECK (eligibility IN
                                                                             ('candidate','eligible','probation',
                                                                              'ineligible','retired')),
    advisory_weight                                                         REAL NOT NULL DEFAULT 1.0
                                                                                 CHECK (advisory_weight >= 0.5
                                                                                        AND advisory_weight <= 2.0),
    rationale_json                                                              TEXT NOT NULL DEFAULT '{}',
    content_key                                                                     TEXT NOT NULL,
    state                                                                               TEXT NOT NULL DEFAULT 'proposed'
                                                                                             CHECK (state IN
                                                                                             ('proposed','active')),
    activated_by                                                                            TEXT,
    activated_at                                                                                REAL,
    superseded_by                                                                                   TEXT,
    created_at                                                                                          REAL NOT NULL
);
CREATE INDEX idx_roster_records_seat ON roster_records(seat_id, state);

-- I-19 IDEMPOTENCY "same window -> same update (content key)": a seat's
-- recompute for a given window is a content-keyed no-op on retry.
CREATE UNIQUE INDEX idx_roster_records_content_key ON roster_records(content_key);

-- I-19 "activation confirm-only".
CREATE TRIGGER trg_roster_records_activation_operator_only
BEFORE UPDATE OF state ON roster_records
WHEN NEW.state = 'active'
BEGIN
    SELECT RAISE(ABORT, 'roster activation requires actor=''operator:*''')
    WHERE NEW.activated_by IS NULL OR NEW.activated_by NOT LIKE 'operator:%';
END;

-- One active roster_record per seat -- same partial-unique-index pattern as
-- playbooks' one-active-per-class.
CREATE UNIQUE INDEX idx_roster_records_one_active_per_seat
    ON roster_records(seat_id) WHERE state = 'active';
