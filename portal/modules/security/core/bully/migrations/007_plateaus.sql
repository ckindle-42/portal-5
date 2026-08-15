-- 007_plateaus.sql -- P4.4: PLT statistical plateau records (DATA_MODEL SS1.13).
-- Additive; never edits 001_init.sql..006_cost_ledger.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE plateaus (
    plateau_id                TEXT PRIMARY KEY,
    hunt_id                    TEXT,
    neighborhood                 TEXT NOT NULL,
    qualifying_trial_ids           TEXT NOT NULL DEFAULT '[]',
    promotions                        INTEGER NOT NULL DEFAULT 0,
    unique_response_gain                 REAL NOT NULL DEFAULT 0.0,
    posterior_upper_bound                   REAL NOT NULL DEFAULT 0.0,
    saturation                                 REAL NOT NULL DEFAULT 0.0,
    policy_version                                TEXT NOT NULL,
    decision                                         TEXT NOT NULL
                                                        CHECK (decision IN ('CONTINUE', 'PLATEAU', 'INSUFFICIENT')),
    action                                              TEXT NOT NULL
                                                            CHECK (action IN ('continue', 'rotate', 'stop')),
    note                                                    TEXT NOT NULL DEFAULT '',
    reset_trigger                                              TEXT,
    reset_version                                                 TEXT,
    override                                                        TEXT,
    expiry                                                             REAL,
    created_at                                                            REAL NOT NULL
);
CREATE INDEX idx_plateaus_neighborhood ON plateaus(neighborhood, created_at);
CREATE INDEX idx_plateaus_hunt ON plateaus(hunt_id);
