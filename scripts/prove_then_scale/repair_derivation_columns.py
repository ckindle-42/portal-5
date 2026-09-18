"""One-time repair of the live store after the migration-17 table rebuild
dropped four columns (PROVE_THEN_SCALE_V1 §0-bis incident).

What happened, in one paragraph: migration 17 rebuilt
``relationship_assertions`` to widen the ``status`` CHECK, but named only the
19 base columns in its CREATE/INSERT — silently dropping ``coverage``,
``proposed_coverage``, ``confidence`` (migration 5) and ``derivation``
(migration 10). It applied to the live store the next time any process opened
a ``Repository``. The loss was caught within minutes:
``reading_assembly.linked_internal`` queries ``derivation`` and failed loudly.

What this script does, in order:

1. backs the store up (SQLite backup API, not a file copy under WAL);
2. re-adds the four columns with their original defaults;
3. reconstructs ``derivation`` from the fingerprints the original writers
   left in PRESERVED columns — every writer of this table writes a
   distinctive relation_type or rationale:
       folder_placeholder_org  relation_type NOT IN (IMPLEMENTS, EVIDENCES,
                               REFERENCES) — the placeholder-org writer emits
                               PERFORMED_BY/APPLIES_TO/EVIDENCED_BY/HAS_ACTIVITY
       folder_cartesian        rationale == 'content-derived candidate;
                               determination does not depend on approval'
       projection_rerank       rationale contains 'cross-encoder rerank'
       projection_rerank|reading   rerank rationale AND an appended
                               '\\nanswer ' line from record_reading_link
       reading                 rationale startswith 'answer '
       semantic_reading        rationale LIKE 'semantic reading pass (%'
4. reconstructs ``confidence`` for rerank rows from the 'score X' their own
   rationale records (record_links wrote score AND rationale together);
   every other writer left confidence 0.0;
5. leaves coverage/proposed_coverage '' — no writer of any surviving row ever
   set them (mapping_store.propose was never run against this store);
6. VERIFIES the result against the pre-rebuild distribution recorded before
   the rebuild, and exits non-zero on any mismatch.

Idempotent: re-running on a repaired store reports and exits 0. A FRESH store
never needs this — migration 17 now rebuilds with the full column list.

Usage: uv run python scripts/prove_then_scale/repair_derivation_columns.py
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.repository import Repository  # noqa: E402

#: The (status, derivation) distribution of relationship_assertions, recorded
#: from the live store BEFORE the rebuild ran (GROUP BY status, derivation).
EXPECTED_DISTRIBUTION = {
    ("proposed", "folder_cartesian"): 1070,
    ("proposed", "folder_placeholder_org"): 272,
    ("proposed", "projection_rerank"): 75,
    ("proposed", "projection_rerank|reading"): 1,
    ("proposed", "reading"): 1,
    ("proposed", "semantic_reading"): 9,
    ("revoked", ""): 1,
}

RERANK_SCORE_RE = re.compile(r"score ([0-9]+\.[0-9]+)")


def column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}  # noqa: S608


def backup(repo: Repository) -> Path:
    dest = repo.path.with_suffix(".db.pre-repair-backup")
    repo._conn.commit()
    source = sqlite3.connect(str(repo.path))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return dest


def main() -> int:
    repo = Repository()
    try:
        conn = repo._conn
        have = column_names(conn, "relationship_assertions")
        missing = [
            c
            for c in ("coverage", "proposed_coverage", "confidence", "derivation")
            if c not in have
        ]
        if not missing:
            print("store already has all columns — nothing to repair")
            return 0
        backup_path = backup(repo)
        print(f"backup written: {backup_path}")

        before = conn.execute(
            "SELECT status, COUNT(*) FROM relationship_assertions GROUP BY status"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM relationship_assertions").fetchone()[0]
        print(f"rows before: {total}; by status: {[tuple(r) for r in before]}")

        with repo._lock, repo._conn:
            for name, decl in (
                ("coverage", "TEXT NOT NULL DEFAULT ''"),
                ("proposed_coverage", "TEXT NOT NULL DEFAULT ''"),
                ("confidence", "REAL NOT NULL DEFAULT 0.0"),
                ("derivation", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name in missing:
                    conn.execute(
                        f"ALTER TABLE relationship_assertions ADD COLUMN {name} {decl}"  # noqa: S608 - fixed DDL
                    )

            # derivation reconstruction, most specific pattern first: the
            # combined rerank|reading row carries BOTH markers; plain rerank
            # must be tested after it.
            conn.execute(
                """UPDATE relationship_assertions SET derivation = 'folder_placeholder_org'
                   WHERE derivation = '' AND relation_type NOT IN
                   ('IMPLEMENTS','EVIDENCES','REFERENCES')"""
            )
            conn.execute(
                """UPDATE relationship_assertions SET derivation = 'folder_cartesian'
                   WHERE derivation = '' AND relation_type IN
                   ('IMPLEMENTS','EVIDENCES','REFERENCES')
                   AND rationale = 'content-derived candidate; determination does not depend on approval'"""
            )
            conn.execute(
                """UPDATE relationship_assertions SET derivation = 'projection_rerank|reading'
                   WHERE derivation = '' AND rationale LIKE '%cross-encoder rerank%'
                   AND instr(rationale, char(10) || 'answer ') > 0"""
            )
            conn.execute(
                """UPDATE relationship_assertions SET derivation = 'projection_rerank'
                   WHERE derivation = '' AND rationale LIKE '%cross-encoder rerank%'"""
            )
            conn.execute(
                """UPDATE relationship_assertions SET derivation = 'semantic_reading'
                   WHERE derivation = '' AND rationale LIKE 'semantic reading pass (%'"""
            )
            conn.execute(
                """UPDATE relationship_assertions SET derivation = 'reading'
                   WHERE derivation = '' AND rationale LIKE 'answer %'"""
            )

            # confidence reconstruction: record_links wrote the score into the
            # rationale it stored, so the number comes back from the row's own
            # record rather than from a guess.
            rows = conn.execute(
                """SELECT assertion_id, rationale FROM relationship_assertions
                   WHERE derivation IN ('projection_rerank','projection_rerank|reading')"""
            ).fetchall()
            for assertion_id, rationale in rows:
                match = RERANK_SCORE_RE.search(str(rationale or ""))
                if match is None:
                    print(f"NO SCORE IN RATIONALE for {assertion_id}; leaving confidence 0.0")
                    continue
                conn.execute(
                    "UPDATE relationship_assertions SET confidence = ? WHERE assertion_id = ?",
                    (float(match.group(1)), assertion_id),
                )

        after = {
            (str(r[0]), str(r[1])): int(r[2])
            for r in conn.execute(
                "SELECT status, derivation, COUNT(*) FROM relationship_assertions GROUP BY status, derivation"
            ).fetchall()
        }
        print("after reconstruction:")
        for key in sorted(set(after) | set(EXPECTED_DISTRIBUTION)):
            mark = ""
            if after.get(key) != EXPECTED_DISTRIBUTION.get(key):
                mark = "  <-- MISMATCH"
            print(
                f"  {key}: {after.get(key, 0)} (expected {EXPECTED_DISTRIBUTION.get(key, 0)}){mark}"
            )
        if after != EXPECTED_DISTRIBUTION:
            print("RECONSTRUCTION DOES NOT MATCH THE RECORDED PRE-REBUILD DISTRIBUTION")
            return 1
        total_after = conn.execute("SELECT COUNT(*) FROM relationship_assertions").fetchone()[0]
        if total_after != total:
            print(f"ROW COUNT CHANGED: {total} -> {total_after}")
            return 1
        print("reconstruction verified against the recorded pre-rebuild distribution")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
