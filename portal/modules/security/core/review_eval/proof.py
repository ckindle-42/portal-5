"""Durable receipts for resumable, hash-keyed T6 proof windows."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def window_digest(
    *,
    window_id: str,
    environment: str,
    sources: Sequence[str],
    start: float,
    end: float,
    event_ids: Sequence[str],
    corpus_stamp: str,
    arm: str,
) -> str:
    """Hash the declared window together with the exact normalized event-id population."""
    if not window_id or not environment or not sources or end <= start:
        raise ValueError("a proof window needs an id, environment, source, and positive interval")
    if not corpus_stamp.startswith("real:"):
        raise ValueError("proof windows require a real: corpus stamp")
    payload = {
        "window_id": window_id,
        "environment": environment,
        "sources": sorted(sources),
        "start": round(start, 6),
        "end": round(end, 6),
        "event_ids": sorted(event_ids),
        "corpus_stamp": corpus_stamp,
        "arm": arm,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class WindowReceipt:
    window_id: str
    window_hash: str
    arm: str
    runtime_run_id: str
    result_digest: str
    summary: Mapping[str, Any]
    created_at: float


class ProofRunStore:
    """Persist aggregate-only completions and skip them only for an exact id/hash/arm match."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS proof_windows (
                window_id TEXT NOT NULL,
                window_hash TEXT NOT NULL,
                arm TEXT NOT NULL,
                runtime_run_id TEXT NOT NULL,
                result_digest TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (window_id, window_hash, arm)
            )
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def completed(self, window_id: str, window_hash: str, arm: str) -> WindowReceipt | None:
        row = self._db.execute(
            "SELECT * FROM proof_windows WHERE window_id = ? AND window_hash = ? AND arm = ?",
            (window_id, window_hash, arm),
        ).fetchone()
        if row is None:
            return None
        return WindowReceipt(
            window_id=str(row["window_id"]),
            window_hash=str(row["window_hash"]),
            arm=str(row["arm"]),
            runtime_run_id=str(row["runtime_run_id"]),
            result_digest=str(row["result_digest"]),
            summary=json.loads(row["summary_json"]),
            created_at=float(row["created_at"]),
        )

    def record_complete(
        self,
        *,
        window_id: str,
        window_hash: str,
        arm: str,
        runtime_run_id: str,
        summary: Mapping[str, Any],
    ) -> WindowReceipt:
        if not runtime_run_id:
            raise ValueError("a completed proof receipt needs its ReviewRuntime run id")
        safe_summary = dict(summary)
        if _has_raw_telemetry(safe_summary):
            raise ValueError("proof receipts may store aggregates, not raw telemetry")
        encoded = json.dumps(safe_summary, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now = time.time()
        self._db.execute(
            """
            INSERT OR REPLACE INTO proof_windows
            (window_id, window_hash, arm, runtime_run_id, result_digest, summary_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (window_id, window_hash, arm, runtime_run_id, digest, encoded, now),
        )
        self._db.commit()
        return WindowReceipt(window_id, window_hash, arm, runtime_run_id, digest, safe_summary, now)


def _has_raw_telemetry(value: Any) -> bool:
    if isinstance(value, Mapping):
        forbidden = {"raw", "_raw", "raw_text", "event_text", "telemetry", "transcript"}
        return any(
            str(key).lower() in forbidden or _has_raw_telemetry(item) for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return any(_has_raw_telemetry(item) for item in value)
    return False
