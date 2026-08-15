-- 003_soc_deliveries.sql -- P2.4: G3 SOC visibility lane's durable receipt
-- table (DATA_MODEL SS1.19). Not in P2.1's explicit table list (which named
-- candidates/gate_results/council_*/promotion_queue only) -- a drift finding
-- (MASTER SS0): SS1.19 documents soc_deliveries as a persisted SUB table and
-- I-7a's own STATE EFFECT says "external delivery + durable receipt", so G3's
-- own phase (P2.4) adds it here rather than silently keeping the receipt
-- transient. Additive; never edits 001_init.sql or 002_bin_heart.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE soc_deliveries (
    delivery_id             TEXT PRIMARY KEY,
    candidate_id                TEXT NOT NULL REFERENCES candidates(candidate_id),
    correlation_key                 TEXT NOT NULL,
    destination                        TEXT,
    config_version                        TEXT,
    payload_hash                             TEXT NOT NULL,
    producer_ack                                INTEGER NOT NULL DEFAULT 0,
    consumer_query_ran                             INTEGER NOT NULL DEFAULT 0,
    consumer_triage_report                            TEXT,
    priority                                             TEXT,
    latency_s                                               REAL,
    content_hash_match                                         INTEGER NOT NULL DEFAULT 0,
    load_profile                                                  TEXT,
    lifecycle_status                                                 TEXT NOT NULL DEFAULT 'intended'
                                                                        CHECK (lifecycle_status IN
                                                                        ('intended', 'sent', 'visible',
                                                                         'failed', 'unknown')),
    created_at                                                          REAL NOT NULL,
    UNIQUE (correlation_key)
);
CREATE INDEX idx_soc_deliveries_candidate ON soc_deliveries(candidate_id);
