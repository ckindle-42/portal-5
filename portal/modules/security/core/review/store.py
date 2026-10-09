"""review.store -- what the reviewer raised, what analysts said, and what it learned.

Append-only where it matters: a verdict is never edited or overwritten; the *effective* verdict
of a concern is the latest OPERATOR decision, and a machine opinion (the judge) can never
displace it. Anchors carry two clocks' worth of honesty: ``recorded_at`` says when the system
began to believe something, so a review can be replayed "as of" a past time (what did we know
then?), and a reversed belief is quarantined, not deleted.

Stdlib only (sqlite3).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import TruthClass, Verdict
from .knowledge import AnchorCard

_SCHEMA = """
CREATE TABLE IF NOT EXISTS concerns (
    concern_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, unit_id TEXT NOT NULL,
    outcome TEXT NOT NULL, priority_p REAL NOT NULL, payload_json TEXT NOT NULL,
    record_json TEXT NOT NULL, card TEXT NOT NULL, recorded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS verdicts (
    verdict_id TEXT PRIMARY KEY, concern_id TEXT NOT NULL, verdict TEXT NOT NULL,
    actor TEXT NOT NULL, note TEXT NOT NULL, truth_class TEXT NOT NULL,
    scripted INTEGER NOT NULL, recorded_at REAL NOT NULL, seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS anchors (
    anchor_id TEXT PRIMARY KEY, kind TEXT NOT NULL, malice TEXT NOT NULL, label TEXT NOT NULL,
    record_json TEXT NOT NULL, derived_from TEXT NOT NULL, truth_class TEXT NOT NULL,
    quarantined INTEGER NOT NULL DEFAULT 0, quarantine_reason TEXT NOT NULL DEFAULT '',
    quarantined_at REAL, recorded_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class StoredConcern:
    concern_id: str
    run_id: str
    unit_id: str
    outcome: str
    priority_p: float
    payload: dict[str, Any]
    record: dict[str, Any]
    card: str


@dataclass(frozen=True)
class VerdictRow:
    verdict_id: str
    concern_id: str
    verdict: Verdict
    actor: str
    note: str
    truth_class: TruthClass
    scripted: bool
    recorded_at: float


@dataclass(frozen=True)
class AnchorRow:
    anchor_id: str
    kind: str
    malice: str
    label: str
    record: dict[str, Any]
    derived_from: str
    truth_class: TruthClass
    quarantined: bool
    quarantine_reason: str
    recorded_at: float

    def card(self) -> AnchorCard:
        return AnchorCard(
            anchor_id=self.anchor_id,
            kind=self.kind,
            label=self.label,
            malice=self.malice,
            text=str(self.record.get("card") or ""),
            record=self.record,
        )


class ReviewStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._seq = 0
        with self._lock:
            if str(path) != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)
            row = self._db.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM verdicts").fetchone()
            self._seq = int(row["m"])
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def health(self) -> dict[str, Any]:
        """Return database integrity and aggregate row counts, without telemetry content."""
        with self._lock:
            integrity = self._db.execute("PRAGMA integrity_check").fetchone()[0]
            counts = {
                table: int(self._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("concerns", "verdicts", "anchors")
            }
        return {"ok": integrity == "ok", "integrity": str(integrity), **counts}

    # ── concerns ─────────────────────────────────────────────────────────────

    def put_concern(
        self,
        run_id: str,
        concern_id: str,
        unit_id: str,
        outcome: str,
        priority_p: float,
        payload: Mapping[str, Any],
        record: Mapping[str, Any],
        *,
        at: float | None = None,
    ) -> None:
        card = str(record.get("card") or "")
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO concerns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    concern_id,
                    run_id,
                    unit_id,
                    outcome,
                    priority_p,
                    json.dumps(dict(payload), default=str),
                    json.dumps(dict(record), default=str),
                    card,
                    at if at is not None else time.time(),
                ),
            )
            self._db.commit()

    @staticmethod
    def _concern(row: sqlite3.Row) -> StoredConcern:
        return StoredConcern(
            concern_id=row["concern_id"],
            run_id=row["run_id"],
            unit_id=row["unit_id"],
            outcome=row["outcome"],
            priority_p=row["priority_p"],
            payload=json.loads(row["payload_json"]),
            record=json.loads(row["record_json"]),
            card=row["card"],
        )

    def get_concern(self, concern_id: str) -> StoredConcern | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM concerns WHERE concern_id = ?", (concern_id,)
            ).fetchone()
        return self._concern(row) if row else None

    def concerns(self, *, run_id: str | None = None) -> list[StoredConcern]:
        query = "SELECT * FROM concerns"
        args: tuple[Any, ...] = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            args = (run_id,)
        with self._lock:
            rows = self._db.execute(
                query + " ORDER BY priority_p ASC, concern_id ASC", args
            ).fetchall()
        return [self._concern(r) for r in rows]

    # ── verdicts (append-only) ───────────────────────────────────────────────

    def append_verdict(
        self,
        concern_id: str,
        verdict: Verdict,
        *,
        actor: str,
        note: str = "",
        truth_class: TruthClass = TruthClass.OPERATOR_DECISION,
        scripted: bool = False,
        at: float | None = None,
    ) -> str:
        verdict_id = f"vd-{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._seq += 1
            self._db.execute(
                "INSERT INTO verdicts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    verdict_id,
                    concern_id,
                    verdict.value,
                    actor,
                    note,
                    truth_class.value,
                    int(scripted),
                    at if at is not None else time.time(),
                    self._seq,
                ),
            )
            self._db.commit()
        return verdict_id

    @staticmethod
    def _verdict(row: sqlite3.Row) -> VerdictRow:
        return VerdictRow(
            verdict_id=row["verdict_id"],
            concern_id=row["concern_id"],
            verdict=Verdict(row["verdict"]),
            actor=row["actor"],
            note=row["note"],
            truth_class=TruthClass(row["truth_class"]),
            scripted=bool(row["scripted"]),
            recorded_at=row["recorded_at"],
        )

    def verdicts_for(self, concern_id: str) -> list[VerdictRow]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM verdicts WHERE concern_id = ? ORDER BY seq ASC", (concern_id,)
            ).fetchall()
        return [self._verdict(r) for r in rows]

    def effective_verdict(self, concern_id: str) -> VerdictRow | None:
        """Latest OPERATOR decision. A machine opinion can never displace it."""
        operator = [
            v
            for v in self.verdicts_for(concern_id)
            if v.truth_class == TruthClass.OPERATOR_DECISION
        ]
        return operator[-1] if operator else None

    def queue(self, *, limit: int = 50) -> list[StoredConcern]:
        """Concerns still awaiting a decision (no operator verdict, or latest is ``unsure``),
        most surprising (smallest calibrated p) first."""
        out: list[StoredConcern] = []
        for concern in self.concerns():
            effective = self.effective_verdict(concern.concern_id)
            if effective is None or effective.verdict == Verdict.UNSURE:
                out.append(concern)
            if len(out) >= limit:
                break
        return out

    # ── anchors ──────────────────────────────────────────────────────────────

    def put_anchor(
        self,
        *,
        anchor_id: str,
        kind: str,
        malice: str,
        label: str,
        record: Mapping[str, Any],
        derived_from: str,
        truth_class: TruthClass,
        at: float | None = None,
    ) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO anchors (anchor_id, kind, malice, label, record_json,"
                " derived_from, truth_class, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    anchor_id,
                    kind,
                    malice,
                    label,
                    json.dumps(dict(record), default=str),
                    derived_from,
                    truth_class.value,
                    at if at is not None else time.time(),
                ),
            )
            self._db.commit()

    def quarantine_anchor(self, anchor_id: str, reason: str, *, at: float | None = None) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE anchors SET quarantined = 1, quarantine_reason = ?, quarantined_at = ?"
                " WHERE anchor_id = ?",
                (reason, at if at is not None else time.time(), anchor_id),
            )
            self._db.commit()

    def anchors(
        self, *, as_of: float | None = None, include_quarantined: bool = False
    ) -> list[AnchorRow]:
        """Anchors the system believed at ``as_of`` (None: now). Replay never sees the future,
        and an anchor quarantined LATER is still part of what was believed then."""
        query = "SELECT * FROM anchors WHERE 1 = 1"
        args: list[Any] = []
        if as_of is not None:
            query += " AND recorded_at <= ?"
            args.append(as_of)
        if not include_quarantined:
            if as_of is None:
                query += " AND quarantined = 0"
            else:  # believed at as_of unless it had already been quarantined by then
                query += " AND (quarantined = 0 OR quarantined_at > ?)"
                args.append(as_of)
        with self._lock:
            rows = self._db.execute(
                query + " ORDER BY recorded_at ASC, anchor_id ASC", args
            ).fetchall()
        return [
            AnchorRow(
                anchor_id=r["anchor_id"],
                kind=r["kind"],
                malice=r["malice"],
                label=r["label"],
                record=json.loads(r["record_json"]),
                derived_from=r["derived_from"],
                truth_class=TruthClass(r["truth_class"]),
                quarantined=bool(r["quarantined"]),
                quarantine_reason=r["quarantine_reason"],
                recorded_at=r["recorded_at"],
            )
            for r in rows
        ]
