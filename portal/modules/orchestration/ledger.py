"""SQLite state ledger for the orchestration arm."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .contracts import Bite, TaskPlan, plan_json

_MOVES = {
    "pending": {"ready", "blocked", "superseded"},
    "ready": {"running", "blocked", "superseded"},
    "running": {"checking", "ready", "superseded"},
    "checking": {"passed", "failed", "ready", "superseded"},
    "failed": {"ready", "blocked", "superseded"},
    "passed": {"superseded"},
    "blocked": {"superseded"},
    "superseded": set(),
}


class ResumeMismatchError(ValueError):
    """Raised when a task is resumed under an unapproved identity."""


class ArmLedger:
    """Own one task's append-only state history."""

    def __init__(self, task_dir: Path) -> None:
        self.task_dir = task_dir
        self.path = task_dir / "ledger.db"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.db.close()

    def _create_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS task (
                task_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                build_sha TEXT NOT NULL,
                model_digest TEXT NOT NULL,
                model_tags_json TEXT NOT NULL,
                residency_mode TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bite (
                task_id TEXT NOT NULL REFERENCES task(task_id),
                bite_id TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                contract_json TEXT NOT NULL,
                failure_json TEXT,
                PRIMARY KEY(task_id, bite_id)
            );
            CREATE TABLE IF NOT EXISTS transition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                bite_id TEXT NOT NULL,
                state TEXT NOT NULL,
                build_sha TEXT NOT NULL,
                model_tag TEXT NOT NULL,
                model_digest TEXT NOT NULL,
                wall_seconds REAL NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def initialize(
        self,
        plan: TaskPlan,
        *,
        build_sha: str,
        model_digest: str,
        engines: dict[str, dict[str, str]],
        residency_mode: str,
    ) -> None:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        now = _now()
        self.db.execute(
            "INSERT INTO task VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                plan.task_id,
                plan.goal,
                "running",
                plan_json(plan),
                build_sha,
                model_digest,
                json.dumps(engines, sort_keys=True),
                residency_mode,
                now,
            ),
        )
        for bite in plan.bites:
            identity = engines[bite.model]
            self.db.execute(
                "INSERT INTO bite (task_id, bite_id, state, contract_json) VALUES (?, ?, ?, ?)",
                (plan.task_id, bite.bite_id, "pending", json.dumps(bite.as_dict(), sort_keys=True)),
            )
            self._insert_event(
                plan.task_id,
                bite.bite_id,
                "pending",
                build_sha,
                identity["model_tag"],
                identity["model_digest"],
                0,
                {"attempt": 0},
            )
        self.db.commit()
        self.task_dir.joinpath("plan.json").write_text(plan_json(plan) + "\n", encoding="utf-8")

    def task(self) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM task").fetchone()
        if row is None:
            raise ValueError("task ledger is empty")
        return cast(sqlite3.Row, row)

    def bites(self) -> list[sqlite3.Row]:
        return [
            cast(sqlite3.Row, row) for row in self.db.execute("SELECT * FROM bite ORDER BY rowid")
        ]

    def bite(self, bite_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM bite WHERE bite_id = ?", (bite_id,)).fetchone()
        if row is None:
            raise KeyError(bite_id)
        return cast(sqlite3.Row, row)

    def transition(
        self,
        bite: Bite,
        state: str,
        *,
        build_sha: str,
        engine: dict[str, str],
        wall_seconds: float = 0,
        detail: dict[str, Any] | None = None,
        failure: dict[str, Any] | None = None,
    ) -> None:
        row = self.bite(bite.bite_id)
        previous = str(row["state"])
        if state not in _MOVES[previous]:
            raise ValueError(f"illegal bite transition {bite.bite_id}: {previous} -> {state}")
        attempts = int(row["attempts"]) + (state == "running")
        failure_json = json.dumps(failure, sort_keys=True) if failure is not None else None
        self.db.execute(
            "UPDATE bite SET state = ?, attempts = ?, failure_json = ? WHERE bite_id = ?",
            (state, attempts, failure_json, bite.bite_id),
        )
        self._insert_event(
            str(self.task()["task_id"]),
            bite.bite_id,
            state,
            build_sha,
            engine["model_tag"],
            engine["model_digest"],
            wall_seconds,
            {"from": previous, "attempt": attempts, **(detail or {})},
        )
        self.db.commit()

    def ready(self, bite: Bite, *, build_sha: str, engine: dict[str, str]) -> None:
        self.transition(bite, "ready", build_sha=build_sha, engine=engine)

    def yield_attempt(
        self, bite: Bite, *, build_sha: str, engine: dict[str, str], reason: str
    ) -> None:
        """Return a running bite to ready without counting an attempt that never reached a model."""
        row = self.bite(bite.bite_id)
        if str(row["state"]) != "running":
            raise ValueError(f"bite {bite.bite_id}: cannot yield from {row['state']}")
        attempts = max(0, int(row["attempts"]) - 1)
        self.db.execute(
            "UPDATE bite SET state = 'ready', attempts = ? WHERE bite_id = ?",
            (attempts, bite.bite_id),
        )
        self._insert_event(
            str(self.task()["task_id"]),
            bite.bite_id,
            "ready",
            build_sha,
            engine["model_tag"],
            engine["model_digest"],
            0,
            {"from": "running", "attempt": attempts, "queue_yield": reason},
        )
        self.db.commit()

    def set_task_status(self, status: str, *, build_sha: str, model: dict[str, str]) -> None:
        self.db.execute("UPDATE task SET status = ?", (status,))
        self._insert_event(
            str(self.task()["task_id"]),
            "__task__",
            status,
            build_sha,
            model["model_tag"],
            model["model_digest"],
            0,
            {},
        )
        self.db.commit()

    def resume(
        self,
        plan: TaskPlan,
        *,
        build_sha: str,
        model_digest: str,
        engines: dict[str, dict[str, str]],
        override: bool,
    ) -> None:
        task = self.task()
        mismatch = []
        if task["build_sha"] != build_sha:
            mismatch.append("build SHA")
        if task["model_digest"] != model_digest:
            mismatch.append("model digest")
        if mismatch and not override:
            raise ResumeMismatchError("resume refused: " + " and ".join(mismatch) + " changed")
        if mismatch:
            self.db.execute(
                "UPDATE task SET build_sha = ?, model_digest = ?, model_tags_json = ? WHERE task_id = ?",
                (build_sha, model_digest, json.dumps(engines, sort_keys=True), plan.task_id),
            )
            self._insert_event(
                plan.task_id,
                "__task__",
                "resume_override",
                build_sha,
                "|".join(engines[seat]["model_tag"] for seat in ("fast", "deep")),
                model_digest,
                0,
                {"mismatches": mismatch},
            )
        for bite in plan.bites:
            state = str(self.bite(bite.bite_id)["state"])
            should_requeue = state in {"running", "checking"} or (
                state == "failed" and self._failed_retry_available(bite.bite_id)
            )
            if should_requeue:
                self.transition(
                    bite,
                    "ready",
                    build_sha=build_sha,
                    engine=engines[bite.model],
                    detail={"resume": True},
                )
        self.db.commit()

    def _failed_retry_available(self, bite_id: str) -> bool:
        row = self.db.execute(
            "SELECT detail_json FROM transition WHERE bite_id = ? AND state = 'failed' "
            "ORDER BY id DESC LIMIT 1",
            (bite_id,),
        ).fetchone()
        if row is None:
            return False
        return json.loads(row["detail_json"]).get("retry_available") is True

    def history(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM transition ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def _insert_event(
        self,
        task_id: str,
        bite_id: str,
        state: str,
        build_sha: str,
        model_tag: str,
        model_digest: str,
        wall_seconds: float,
        detail: dict[str, Any],
    ) -> None:
        self.db.execute(
            """INSERT INTO transition
            (task_id, bite_id, state, build_sha, model_tag, model_digest,
             wall_seconds, detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                bite_id,
                state,
                build_sha,
                model_tag,
                model_digest,
                float(wall_seconds),
                json.dumps(detail, sort_keys=True),
                _now(),
            ),
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()
