-- 005_drift.sql -- P3.2: BR-DRIFT baselines/flags (DATA_MODEL SS1.8).
-- Additive; never edits 001_init.sql/002_bin_heart.sql/003_soc_deliveries.sql/
-- 004_mutation.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE detection_baselines (
    baseline_key                TEXT PRIMARY KEY,
    detection_id                 TEXT NOT NULL,
    policy_version                 TEXT NOT NULL,
    status                            TEXT NOT NULL
                                        CHECK (status IN ('warmup', 'active', 'superseded')),
    window                               TEXT NOT NULL DEFAULT '[]',
    sample_count                            INTEGER NOT NULL DEFAULT 0,
    model_canary_ref                           TEXT,
    last_episode_id                               TEXT,
    updated_at                                       REAL NOT NULL
);
CREATE INDEX idx_detection_baselines_detection ON detection_baselines(detection_id);

CREATE TABLE drift_flags (
    flag_id              TEXT PRIMARY KEY,
    detection_id           TEXT NOT NULL,
    episode_id                TEXT NOT NULL,
    drift_class                  TEXT NOT NULL,
    status                          TEXT NOT NULL CHECK (status IN ('FLAGGED', 'INSUFFICIENT_BASELINE')),
    score                               REAL NOT NULL DEFAULT 0.0,
    signals                                TEXT NOT NULL DEFAULT '{}',
    bands                                     TEXT NOT NULL DEFAULT '{}',
    breaches                                     TEXT NOT NULL DEFAULT '{}',
    consecutive_count                               INTEGER NOT NULL DEFAULT 0,
    routed                                             INTEGER NOT NULL DEFAULT 0,
    detail                                                TEXT NOT NULL DEFAULT '',
    created_at                                               REAL NOT NULL
);
CREATE INDEX idx_drift_flags_detection ON drift_flags(detection_id, created_at);
CREATE INDEX idx_drift_flags_episode ON drift_flags(episode_id);
