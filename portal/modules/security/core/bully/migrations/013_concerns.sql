-- 013_concerns.sql -- X.2: the analyst review queue the store never had.

CREATE TABLE concerns (
    concern_id       TEXT PRIMARY KEY,
    assessment_id    TEXT NOT NULL,
    entity_id        TEXT NOT NULL,
    relationship     TEXT NOT NULL,
    concern_class    TEXT NOT NULL,
    match_level      TEXT,
    robustness       REAL NOT NULL DEFAULT 0.0,
    n_sources        INTEGER NOT NULL DEFAULT 0,
    source_ids_json  TEXT NOT NULL DEFAULT '[]',
    span_seconds     REAL,
    aligned_spine_json TEXT NOT NULL DEFAULT '[]',
    resembles        TEXT,
    brief            TEXT NOT NULL DEFAULT '',
    raised_at        REAL NOT NULL,
    verdict          TEXT,
    verdict_note     TEXT NOT NULL DEFAULT '',
    verdict_at       REAL,
    version          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_concerns_open ON concerns (verdict, raised_at);
