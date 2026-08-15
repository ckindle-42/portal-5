-- 012_imported_observed.sql -- gradeable external observations remain sub-live.

ALTER TABLE evidence_items ADD COLUMN trust_tier TEXT NOT NULL DEFAULT 'non_observed';

UPDATE evidence_items
SET trust_tier = CASE
    WHEN origin IN ('observed_packet', 'observed_target_log', 'sensor_derived') THEN 'live_sensor'
    WHEN origin = 'imported_observed' THEN 'imported_observed'
    ELSE 'non_observed'
END;

DROP TRIGGER trg_g0_blocks_synthetic_only;

CREATE TRIGGER trg_g0_blocks_synthetic_only
BEFORE INSERT ON gate_results
WHEN NEW.gate_id = 'G0' AND NEW.outcome = 'pass'
BEGIN
    SELECT RAISE(ABORT, 'G0 cannot pass without >=1 gradeable evidence item (synthetic blocked)')
    WHERE NOT EXISTS (
        SELECT 1
        FROM evidence_items ei
        JOIN candidates c ON c.evidence_manifest_id = ei.manifest_id
        WHERE c.candidate_id = NEW.candidate_id
          AND ei.synthetic = 0
          AND ei.origin IN (
              'observed_packet', 'observed_target_log', 'sensor_derived', 'imported_observed'
          )
    );
END;
