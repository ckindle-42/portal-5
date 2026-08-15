-- 011_coverage_cells.sql -- P7 persisted coverage-cell successor to cold graph rebuild.

CREATE TABLE coverage_cells (
    cell_id          TEXT PRIMARY KEY,
    subject          TEXT NOT NULL,
    scenario         TEXT,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    source_hash      TEXT NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    updated_at       REAL NOT NULL
);
