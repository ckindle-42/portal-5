"""Sealed scorer-side truth ledger for the specimen calibration corpus."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import config

LEDGER_SCHEMA = "BULLY_SPECIMEN_LEDGER_V1"
SOURCE_LANES = frozenset({"attack_data", "replay_mutation", "live_lab"})


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class SpecimenRecord:
    specimen_id: str
    parent_id: str | None
    source_lane: str
    transform_ops: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    construction_distance: float = 0.0
    data_yml_techniques: tuple[str, ...] = field(default_factory=tuple)
    created_at: float = field(default_factory=time.time)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.specimen_id:
            raise ValueError("specimen_id is required")
        if self.source_lane not in SOURCE_LANES:
            raise ValueError(f"unknown specimen source lane: {self.source_lane!r}")
        if not 0.0 <= self.construction_distance <= 1.0:
            raise ValueError("construction_distance must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SpecimenLedger:
    """Append-only, hash-chained ledger outside the engine state database."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else config.hunt_dir() / "specimens"
        self.path = self.root / "specimen_ledger.jsonl"
        self._rows_cache: list[dict[str, Any]] | None = None
        self._rows_cache_stat: tuple[int, int] | None = None
        self._by_specimen_id: dict[str, dict[str, Any]] = {}

    def _path_stat(self) -> tuple[int, int] | None:
        if not self.path.exists():
            return None
        stat = self.path.stat()
        return stat.st_mtime_ns, stat.st_size

    def _rows(self) -> list[dict[str, Any]]:
        path_stat = self._path_stat()
        if path_stat is None:
            self._rows_cache = []
            self._rows_cache_stat = None
            self._by_specimen_id = {}
            return []
        if self._rows_cache is not None and path_stat == self._rows_cache_stat:
            return self._rows_cache
        rows = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        previous = ""
        for sequence, row in enumerate(rows, start=1):
            payload = {
                "schema": row.get("schema"),
                "sequence": row.get("sequence"),
                "previous_hash": row.get("previous_hash"),
                "specimen": row.get("specimen"),
            }
            expected = hashlib.sha256(_canonical(payload).encode()).hexdigest()
            if (
                row.get("schema") != LEDGER_SCHEMA
                or row.get("sequence") != sequence
                or row.get("previous_hash") != previous
                or row.get("record_hash") != expected
            ):
                raise RuntimeError(f"specimen ledger seal broken at sequence {sequence}")
            previous = expected
        self._rows_cache = rows
        self._rows_cache_stat = path_stat
        self._by_specimen_id = {
            str(row["specimen"]["specimen_id"]): row["specimen"] for row in rows
        }
        return rows

    def record(self, specimen: SpecimenRecord | dict[str, Any]) -> dict[str, Any]:
        record = specimen if isinstance(specimen, SpecimenRecord) else SpecimenRecord(**specimen)
        body = record.to_dict()
        rows = self._rows()
        existing = self._by_specimen_id.get(record.specimen_id)
        if existing is not None:
            if _canonical(existing) != _canonical(body):
                raise ValueError(
                    f"specimen_id already sealed with different truth: {record.specimen_id}"
                )
            return dict(existing)

        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {
            "schema": LEDGER_SCHEMA,
            "sequence": len(rows) + 1,
            "previous_hash": rows[-1]["record_hash"] if rows else "",
            "specimen": body,
        }
        sealed = {
            **payload,
            "record_hash": hashlib.sha256(_canonical(payload).encode()).hexdigest(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(sealed) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.path.chmod(0o600)
        rows.append(sealed)
        self._rows_cache = rows
        self._rows_cache_stat = self._path_stat()
        self._by_specimen_id[record.specimen_id] = body
        return dict(body)

    def truth_for(self, specimen_id: str) -> dict[str, Any] | None:
        for row in self._rows():
            if row["specimen"]["specimen_id"] == specimen_id:
                return dict(row["specimen"])
        return None

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row["specimen"]) for row in self._rows())

    def snapshot_hash(self) -> str:
        rows = self._rows()
        return rows[-1]["record_hash"] if rows else hashlib.sha256(b"").hexdigest()


def record(
    specimen: SpecimenRecord | dict[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    return SpecimenLedger(root).record(specimen)


def truth_for(specimen_id: str, *, root: Path | None = None) -> dict[str, Any] | None:
    return SpecimenLedger(root).truth_for(specimen_id)
