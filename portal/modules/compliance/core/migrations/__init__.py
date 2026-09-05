"""Forward-only, transactional migration runner (P2).

Applies every migration in ``schema.MIGRATIONS`` with a version greater than
the store's recorded ``schema_version``, inside one transaction per call —
either every pending migration applies and the version is bumped once at the
end, or none of them do and the store is untouched. Never re-applies an
already-recorded version (idempotent re-run).
"""

from __future__ import annotations

import sqlite3

from portal.modules.compliance.core.migrations.schema import MIGRATIONS

CURRENT_SCHEMA_VERSION = max(v for v, _, _ in MIGRATIONS)


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )


def get_schema_version(conn: sqlite3.Connection) -> int:
    _ensure_meta_table(conn)
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row else 0


def _statements(sql: str) -> list[str]:
    """Split a migration's DDL block into individual statements. Needed
    because ``sqlite3.Connection.executescript`` implicitly commits any
    pending transaction before it runs and does not participate in a
    caller-managed transaction — using it here would silently break the
    whole-batch atomicity this migration runner promises."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def apply_migrations(conn: sqlite3.Connection) -> dict:
    """Apply pending migrations inside ONE transaction — either every
    pending migration applies and the version is bumped once at the end, or
    a failure partway through leaves the store exactly as it was before this
    call (crash recovery: a subsequent call resumes from the last good
    version). Returns a report with the before/after version and which
    migrations ran — a dry-run (no pending work) reports an empty ``applied``
    list rather than an error, so a repeat call is always safe (P2 exit:
    "repeat-run idempotence")."""
    _ensure_meta_table(conn)
    before = get_schema_version(conn)
    pending = sorted(m for m in MIGRATIONS if m[0] > before)
    applied = []
    if pending:
        conn.execute("BEGIN")
        try:
            for version, description, sql in pending:
                for stmt in _statements(sql):
                    conn.execute(stmt)
                applied.append({"version": version, "description": description})
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(pending[-1][0]),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "schema_version_before": before,
        "schema_version_after": get_schema_version(conn),
        "applied": applied,
    }
