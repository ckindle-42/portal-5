-- 004_mutation.sql -- P3.1: MUT typed MutationPlans (DATA_MODEL SS7
-- "MutationPlan" is a contracts.py DTO, "persisted as a record"). Additive;
-- never edits 001_init.sql/002_bin_heart.sql/003_soc_deliveries.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE mutation_plans (
    plan_id                 TEXT PRIMARY KEY,
    plan_version             INTEGER NOT NULL,
    reference_scenario        TEXT NOT NULL,
    operators                  TEXT NOT NULL DEFAULT '[]',
    invariants                  TEXT NOT NULL DEFAULT '[]',
    expected_observables          TEXT NOT NULL DEFAULT '{}',
    controls                        TEXT NOT NULL DEFAULT '[]',
    replay_policy                     TEXT,
    allowed_targets                     TEXT NOT NULL DEFAULT '[]',
    allowed_tools                          TEXT NOT NULL DEFAULT '[]',
    cleanup                                   TEXT NOT NULL DEFAULT '[]',
    approval_ref                                 TEXT,
    budget_class                                    TEXT NOT NULL,
    idempotency_key                                    TEXT NOT NULL,
    proposer                                              TEXT NOT NULL,
    status                                                   TEXT NOT NULL
                                                                CHECK (status IN ('validated', 'rejected')),
    rejection_reason_code                                       TEXT,
    rejection_detail                                                TEXT,
    overlay                                                            TEXT,
    created_at                                                            REAL NOT NULL,
    UNIQUE (idempotency_key)
);
CREATE INDEX idx_mutation_plans_reference ON mutation_plans(reference_scenario);
