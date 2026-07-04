"""Case Notebook — investigation memory for one case.

Phase 6a of BUILD_PROGRAM_SEC_RBP_V1.  V3 §2.7 / §3.6.

The case notebook is one of seven memory kinds, kept strictly separate:
1. Agent scratch — one agent turn (discarded)
2. Case notebook — life of one investigation (THIS)
3. Case evidence — immutable, append-only (EvidenceStore)
4. Prior-Incident library — long-lived, analyst-confirm-only
5. Confirmed org knowledge — operator-approved
6. Analyst feedback — growth loop only
7. Agent long-term memory — NOT PERMITTED at inference

The case notebook is writable by all agents in the same case, readable by
all agents in the same case, and promotable to Prior-Incident only by
analyst confirm at case close.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class NotebookEntry:
    """One entry in the case notebook."""

    entry_id: str  # nb-<case_id>-<seq>
    case_id: str
    agent_id: str  # which agent wrote this (A1-A5 or "analyst")
    entry_type: str  # "hypothesis", "finding", "annotation", "scratch", "decision"
    content: dict  # the actual content
    created_at: float = 0.0
    superseded_by: str = ""  # if this entry was revised

    def to_dict(self) -> dict:
        return asdict(self)


class CaseNotebook:
    """SQLite-backed case notebook for one investigation.

    Provides structured storage for hypotheses, findings, annotations,
    and decisions made during an investigation.  All entries are keyed
    by case_id — multiple cases can coexist in the same database.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seq: dict[str, int] = {}  # case_id → next sequence number

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS notebook_entries (
                entry_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                superseded_by TEXT DEFAULT ''
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notebook_case
            ON notebook_entries(case_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notebook_type
            ON notebook_entries(case_id, entry_type)
        """)
        self._conn.commit()

    def _next_entry_id(self, case_id: str) -> str:
        seq = self._seq.get(case_id, 0) + 1
        self._seq[case_id] = seq
        return f"nb-{case_id}-{seq:04d}"

    def write(
        self,
        case_id: str,
        agent_id: str,
        entry_type: str,
        content: dict,
    ) -> NotebookEntry:
        """Write a new entry to the notebook."""
        entry = NotebookEntry(
            entry_id=self._next_entry_id(case_id),
            case_id=case_id,
            agent_id=agent_id,
            entry_type=entry_type,
            content=content,
            created_at=time.time(),
        )
        self._conn.execute(
            "INSERT INTO notebook_entries (entry_id, case_id, agent_id, entry_type, content, created_at, superseded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.entry_id,
                entry.case_id,
                entry.agent_id,
                entry.entry_type,
                json.dumps(entry.content),
                entry.created_at,
                entry.superseded_by,
            ),
        )
        self._conn.commit()
        return entry

    def read(self, entry_id: str) -> NotebookEntry | None:
        """Read an entry by ID."""
        row = self._conn.execute(
            "SELECT * FROM notebook_entries WHERE entry_id = ?", (entry_id,)
        ).fetchone()
        if not row:
            return None
        return NotebookEntry(
            entry_id=row["entry_id"],
            case_id=row["case_id"],
            agent_id=row["agent_id"],
            entry_type=row["entry_type"],
            content=json.loads(row["content"]),
            created_at=row["created_at"],
            superseded_by=row["superseded_by"],
        )

    def read_case(self, case_id: str, entry_type: str = "") -> list[NotebookEntry]:
        """Read all entries for a case, optionally filtered by type."""
        if entry_type:
            rows = self._conn.execute(
                "SELECT * FROM notebook_entries WHERE case_id = ? AND entry_type = ? ORDER BY created_at",
                (case_id, entry_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notebook_entries WHERE case_id = ? ORDER BY created_at",
                (case_id,),
            ).fetchall()

        return [
            NotebookEntry(
                entry_id=r["entry_id"],
                case_id=r["case_id"],
                agent_id=r["agent_id"],
                entry_type=r["entry_type"],
                content=json.loads(r["content"]),
                created_at=r["created_at"],
                superseded_by=r["superseded_by"],
            )
            for r in rows
        ]

    def supersede(self, old_entry_id: str, new_entry: NotebookEntry) -> NotebookEntry:
        """Mark an old entry as superseded and write the new one."""
        self._conn.execute(
            "UPDATE notebook_entries SET superseded_by = ? WHERE entry_id = ?",
            (new_entry.entry_id, old_entry_id),
        )
        self._conn.commit()
        return new_entry

    def count(self, case_id: str = "") -> int:
        """Count entries, optionally for a specific case."""
        if case_id:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM notebook_entries WHERE case_id = ?", (case_id,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM notebook_entries").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> CaseNotebook:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
