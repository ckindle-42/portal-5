-- 008_handoff.sql -- P5.1: detection-proposal lifecycle tables (DATA_MODEL
-- SS1.20) + the KNOWN_COVERED-requires-deploy+post-deploy-replay DB check
-- (SS4.8). Additive only; prior migrations are never edited after shipping
-- (MASTER SS10 ordered-migration discipline).

PRAGMA foreign_keys = ON;

-- ── detection_proposals (HND, I-14) ─────────────────────────────────────────
--
-- One row per built/rebuilt handoff package (DESIGN SS23's 11-part
-- family-generalizing proposal). `package_json` holds the full rendered
-- package (parts 1-11); the discrete proof-leg / lifecycle columns exist so
-- the DB can enforce "a proof-leg failure blocks the package" and
-- "rejected requires rationale" without parsing JSON in a trigger.
CREATE TABLE detection_proposals (
    proposal_id             TEXT PRIMARY KEY,
    version                     INTEGER NOT NULL DEFAULT 1,
    candidate_id                   TEXT NOT NULL REFERENCES candidates(candidate_id),
    hunt_id                            TEXT,
    family                                 TEXT NOT NULL,
    status                                     TEXT NOT NULL DEFAULT 'draft'
                                                   CHECK (status IN
                                                   ('draft','submitted','accepted','revise',
                                                    'rejected','expired','deployed',
                                                    'replay-validated','replay-failed','retired')),
    package_json                                   TEXT NOT NULL DEFAULT '{}',
    content_hash                                       TEXT NOT NULL,
    fires_on_attack                                        INTEGER NOT NULL DEFAULT 0,
    quiet_on_benign                                            INTEGER NOT NULL DEFAULT 0,
    no_regression                                                  INTEGER NOT NULL DEFAULT 0,
    proof_legs_json                                                    TEXT NOT NULL DEFAULT '{}',
    regression_recipe_name                                                 TEXT,
    owner                                                                      TEXT,
    expiry                                                                        REAL,
    rationale                                                                        TEXT,
    deployment_id                                                                       TEXT,
    coverage_validation_ref                                                                TEXT,
    superseded_by                                                                            TEXT,
    artifacts_dir                                                                              TEXT,
    created_at                                                                                    REAL NOT NULL
);
CREATE INDEX idx_detection_proposals_candidate ON detection_proposals(candidate_id, version);

-- SS4.8 / I-14 "a proof-leg failure blocks the package, never shipped": the
-- DB-level backstop -- no code path, including a future bug, can land a
-- 'deployed' status without all three real proof legs recorded pass.
CREATE TRIGGER trg_detection_proposal_deploy_requires_proof_legs
BEFORE UPDATE OF status ON detection_proposals
WHEN NEW.status = 'deployed'
BEGIN
    SELECT RAISE(ABORT, 'deployed requires fires_on_attack+quiet_on_benign+no_regression all passing')
    WHERE NEW.fires_on_attack = 0 OR NEW.quiet_on_benign = 0 OR NEW.no_regression = 0;
END;

-- "Rejected/revised/expired dispositions feed ORG as negative learning" (I-14
-- DESIGN SS23) requires a rationale to be worth indexing -- mirrors
-- promotion_queue's reject-requires-rationale trigger (002_bin_heart.sql).
CREATE TRIGGER trg_detection_proposal_reject_requires_rationale
BEFORE UPDATE OF status ON detection_proposals
WHEN NEW.status = 'rejected'
BEGIN
    SELECT RAISE(ABORT, 'detection_proposals rejection requires a rationale')
    WHERE NEW.rationale IS NULL OR TRIM(NEW.rationale) = '';
END;

-- ── deployments (operator commit receipt) ───────────────────────────────────
--
-- The spl_detections.yaml change itself is an operator commit through the
-- repo's normal pre-push validation (BQ/AZ green); this table is the
-- *receipt* of that commit for the KNOWN_COVERED check below, never the
-- commit mechanism itself (I-14 "operator boundary").
CREATE TABLE deployments (
    deployment_id           TEXT PRIMARY KEY,
    proposal_id                 TEXT NOT NULL REFERENCES detection_proposals(proposal_id),
    spl_commit_ref                  TEXT NOT NULL,
    deployed_by                         TEXT NOT NULL,
    receipt_hash                            TEXT NOT NULL,
    deployed_at                                 REAL NOT NULL,
    UNIQUE (proposal_id, spl_commit_ref)
);

-- SS4.8 / MASTER SS7: deployment ownership is an operator action; DB-enforced
-- the same way trg_promotion_queue_operator_only enforces queue resolution.
CREATE TRIGGER trg_deployment_operator_only
BEFORE INSERT ON deployments
BEGIN
    SELECT RAISE(ABORT, 'deployment requires actor=''operator:*''')
    WHERE NEW.deployed_by NOT LIKE 'operator:%';
END;

-- ── replay_validations (post-deploy Purple replay, I-14) ────────────────────

CREATE TABLE replay_validations (
    validation_id           TEXT PRIMARY KEY,
    deployment_id                TEXT NOT NULL REFERENCES deployments(deployment_id),
    passed                            INTEGER NOT NULL,
    noise_estimate                       REAL,
    detail                                   TEXT,
    validated_at                                REAL NOT NULL
);
CREATE INDEX idx_replay_validations_deployment ON replay_validations(deployment_id);

-- ── known_state: KNOWN_COVERED requires deploy + post-deploy replay ────────
--
-- known_state shipped in 001_init.sql without a column linking a
-- 'known_covered' entry to the deployment that earned it -- added here
-- rather than retrofitted into the already-shipped table definition
-- (precedent: 002_bin_heart.sql's evidence_items.origin ALTER).
ALTER TABLE known_state ADD COLUMN deployment_id TEXT;

-- SS4.8: "checks preventing KNOWN_COVERED without deployment + post-deploy
-- replay validation." A coverage cell can only become known_covered when it
-- carries a deployment_id whose replay_validations show a passed replay --
-- DB-level backstop, not merely an application-code convention.
CREATE TRIGGER trg_known_covered_requires_deploy_replay
BEFORE INSERT ON known_state
WHEN NEW.kind = 'known_covered'
BEGIN
    SELECT RAISE(ABORT, 'known_covered requires a deployment_id with a passed post-deploy replay')
    WHERE NEW.deployment_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM replay_validations
        WHERE deployment_id = NEW.deployment_id AND passed = 1
    );
END;
