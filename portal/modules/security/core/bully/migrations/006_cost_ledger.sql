-- 006_cost_ledger.sql -- P4.1: COST typed cost ledger (DATA_MODEL SS1.12).
-- Additive; never edits 001_init.sql..005_drift.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE cost_ledger (
    record_id                TEXT PRIMARY KEY,
    hunt_id                   TEXT NOT NULL,
    iteration_id               TEXT,
    components                   TEXT NOT NULL DEFAULT '[]',
    pricing_profile_version        TEXT NOT NULL,
    computed_units                    REAL,
    quality_flag                         INTEGER NOT NULL DEFAULT 0,
    created_at                              REAL NOT NULL
);
CREATE INDEX idx_cost_ledger_hunt ON cost_ledger(hunt_id, created_at);
CREATE INDEX idx_cost_ledger_iteration ON cost_ledger(iteration_id);
