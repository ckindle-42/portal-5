-- 002_bin_heart.sql -- P2.1: bin/council/queue tables (DATA_MODEL SS1.5-1.6,
-- SS1.14) + hard DB constraints (SS4.8). Additive only; 001_init.sql is never
-- edited after shipping (MASTER SS10 ordered-migration discipline).

PRAGMA foreign_keys = ON;

-- evidence_items shipped in 001_init.sql without a column distinguishing
-- *how* an item was produced (telemetry.py's OBSERVED_EVIDENCE_ORIGINS vs
-- NON_OBSERVED_EVIDENCE_ORIGINS) from whether it is flagged `synthetic` --
-- G0 needs the former (evidence.py::has_observed_origin), so it is added
-- here rather than retrofitted into the already-shipped table definition.
ALTER TABLE evidence_items ADD COLUMN origin TEXT;

-- ── candidates + gate_results (the bin, I-7) ────────────────────────────────

CREATE TABLE candidates (
    candidate_id          TEXT PRIMARY KEY,
    hunt_id                TEXT NOT NULL REFERENCES hunts(hunt_id),
    assessment_id             TEXT NOT NULL REFERENCES cousin_assessments(assessment_id),
    evidence_manifest_id         TEXT REFERENCES evidence_manifests(manifest_id),
    alert_version                   INTEGER NOT NULL DEFAULT 1,
    current_state                      TEXT NOT NULL,
    gate_policy_version                   TEXT NOT NULL,
    terminal_reason                          TEXT,
    queue_state                                 TEXT,
    decided_by                                     TEXT,
    decided_at                                        REAL,
    rationale                                            TEXT,
    version                                                 INTEGER NOT NULL DEFAULT 0,
    created_at                                                 REAL NOT NULL
);

CREATE TABLE gate_results (
    result_id           TEXT PRIMARY KEY,
    candidate_id            TEXT NOT NULL REFERENCES candidates(candidate_id),
    alert_version               INTEGER NOT NULL,
    gate_id                        TEXT NOT NULL
                                       CHECK (gate_id IN ('G-1','G0','G1a','G1b','G2','G4','G3','G5')),
    attempt                           INTEGER NOT NULL,
    outcome                              TEXT NOT NULL CHECK (outcome IN ('pass','fail','blocked')),
    validator_version                       TEXT NOT NULL,
    inputs_json                                TEXT NOT NULL DEFAULT '{}',
    evidence_json                                 TEXT NOT NULL DEFAULT '{}',
    checks_json                                      TEXT NOT NULL DEFAULT '[]',
    reasons_json                                        TEXT NOT NULL DEFAULT '[]',
    created_at                                             REAL NOT NULL,
    UNIQUE (candidate_id, alert_version, gate_id, attempt)
);
CREATE INDEX idx_gate_results_candidate ON gate_results(candidate_id, alert_version, gate_id);

-- C2 / SS4.8: synthetic-origin-only evidence can never pass G0. Application
-- code (evidence.synthetic_never_passes_g0) is the primary check exercised
-- before a promotion.py gate write is even attempted; this trigger is the
-- DB-level backstop so no code path -- including a future bug or an
-- operator SQL slip -- can land a G0 'pass' row for a candidate whose
-- evidence manifest holds no observed-origin item. Mirrors
-- telemetry.OBSERVED_EVIDENCE_ORIGINS; keep the literal set in sync with
-- that module if it ever changes.
CREATE TRIGGER trg_g0_blocks_synthetic_only
BEFORE INSERT ON gate_results
WHEN NEW.gate_id = 'G0' AND NEW.outcome = 'pass'
BEGIN
    SELECT RAISE(ABORT, 'G0 cannot pass without >=1 observed-origin evidence item (synthetic blocked)')
    WHERE NOT EXISTS (
        SELECT 1
        FROM evidence_items ei
        JOIN candidates c ON c.evidence_manifest_id = ei.manifest_id
        WHERE c.candidate_id = NEW.candidate_id
          AND ei.synthetic = 0
          AND ei.origin IN ('observed_packet', 'observed_target_log', 'sensor_derived')
    );
END;

-- SS4.8: "checks preventing PROMOTED without passing gates + a G5 record."
-- HEART's clearance is persisted as a gate_results row with gate_id='G5'
-- (I-8's objection-gate outcome, recorded through the same gate_results
-- table as every other bin gate); G3 is SOC visibility. PROMOTED requires
-- all seven gates passing at the candidate's *current* alert_version --
-- this is also how "a changed evidence manifest invalidates downstream
-- passes" is enforced at the DB level: bumping alert_version orphans the
-- prior gate_results rows from this COUNT because they carry the old
-- alert_version.
CREATE TRIGGER trg_candidate_promote_requires_full_gate_chain
BEFORE UPDATE OF current_state ON candidates
WHEN NEW.current_state = 'PROMOTED'
BEGIN
    SELECT RAISE(ABORT, 'PROMOTED requires G-1,G0,G1a,G1b,G2,G5,G3 all passing at the current alert_version')
    WHERE (
        SELECT COUNT(DISTINCT gate_id) FROM gate_results
        WHERE candidate_id = NEW.candidate_id
          AND alert_version = NEW.alert_version
          AND outcome = 'pass'
          AND gate_id IN ('G-1','G0','G1a','G1b','G2','G5','G3')
    ) < 7;
END;

-- ── council (HEART, I-8) ─────────────────────────────────────────────────────

CREATE TABLE council_packets (
    packet_id                TEXT PRIMARY KEY,
    candidate_id                 TEXT NOT NULL REFERENCES candidates(candidate_id),
    evidence_manifest_id             TEXT,
    evidence_manifest_hash               TEXT NOT NULL,
    roster_snapshot                         TEXT NOT NULL DEFAULT '{}',
    materiality_version                        TEXT NOT NULL,
    unresolved                                    INTEGER NOT NULL DEFAULT 0,
    review_valid                                     INTEGER NOT NULL DEFAULT 1,
    participation                                       REAL,
    superseded_by                                          TEXT,
    created_at                                                REAL NOT NULL
);

CREATE TABLE council_opinions (
    opinion_id                  TEXT PRIMARY KEY,
    packet_id                       TEXT NOT NULL REFERENCES council_packets(packet_id),
    seat_id                            TEXT NOT NULL,
    attempt                               INTEGER NOT NULL DEFAULT 1,
    member_id                               TEXT,
    model                                      TEXT,
    family                                        TEXT,
    valid                                            INTEGER NOT NULL DEFAULT 0,
    error                                               TEXT,
    recommendation                                         TEXT,
    confidence                                                REAL,
    findings_json                                                TEXT NOT NULL DEFAULT '[]',
    strongest_objection                                             TEXT,
    missing_evidence_json                                              TEXT NOT NULL DEFAULT '[]',
    conditions_to_change_json                                             TEXT NOT NULL DEFAULT '[]',
    created_at                                                               REAL NOT NULL,
    UNIQUE (packet_id, seat_id, attempt)
);

CREATE TABLE objections (
    objection_id                TEXT PRIMARY KEY,
    packet_id                       TEXT NOT NULL REFERENCES council_packets(packet_id),
    seat_id                             TEXT NOT NULL,
    category                               TEXT NOT NULL,
    material                                  INTEGER NOT NULL,
    claim                                        TEXT NOT NULL,
    evidence_citations_json                         TEXT NOT NULL DEFAULT '[]',
    missing_proof_citations_json                       TEXT NOT NULL DEFAULT '[]',
    status                                                TEXT NOT NULL DEFAULT 'open'
                                                             CHECK (status IN
                                                             ('open','rebutted','re_review',
                                                              'withdrawn','sustained','waived',
                                                              'superseded')),
    age_seconds                                             REAL,
    created_at                                                 REAL NOT NULL
);

CREATE TABLE rebuttals (
    rebuttal_id             TEXT PRIMARY KEY,
    objection_id                TEXT NOT NULL REFERENCES objections(objection_id),
    author                          TEXT NOT NULL,
    claim                              TEXT NOT NULL,
    evidence_citations_json              TEXT NOT NULL DEFAULT '[]',
    requested_review                        TEXT,
    re_review_result                           TEXT,
    created_at                                    REAL NOT NULL
);

-- ── promotion_queue (I-3/I-7, SS4.8) ────────────────────────────────────────

CREATE TABLE promotion_queue (
    queue_id           TEXT PRIMARY KEY,
    item_kind              TEXT NOT NULL
                               CHECK (item_kind IN
                               ('cousin_detection','model','playbook','roster',
                                'waiver','policy','review_escalation')),
    item_id                    TEXT NOT NULL,
    hunt_id                        TEXT,
    state                              TEXT NOT NULL DEFAULT 'pending'
                                           CHECK (state IN ('pending','confirmed','rejected')),
    enqueued_at                            REAL NOT NULL,
    resolved_by                                TEXT,
    resolved_at                                   REAL,
    rationale                                        TEXT
);

-- SS4.8 / MASTER SS7: "store.promotion_resolve requires actor='operator:*';
-- there is no code path that promotes without it." DB-enforced, not merely
-- documented: any UPDATE moving state out of 'pending' must carry an
-- operator-prefixed resolved_by.
CREATE TRIGGER trg_promotion_queue_operator_only
BEFORE UPDATE OF state ON promotion_queue
WHEN NEW.state IN ('confirmed', 'rejected')
BEGIN
    SELECT RAISE(ABORT, 'promotion_queue resolution requires actor=''operator:*''')
    WHERE NEW.resolved_by IS NULL OR NEW.resolved_by NOT LIKE 'operator:%';
END;

-- A rejected item requires a rationale (P2.5 "reject requires rationale").
CREATE TRIGGER trg_promotion_queue_reject_requires_rationale
BEFORE UPDATE OF state ON promotion_queue
WHEN NEW.state = 'rejected'
BEGIN
    SELECT RAISE(ABORT, 'promotion_queue rejection requires a rationale')
    WHERE NEW.rationale IS NULL OR TRIM(NEW.rationale) = '';
END;
