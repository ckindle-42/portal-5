"""Provenance ledger — append-only cross-run audit trail.

Phase 3 of TASK-SEC-DESIGN-GAP-DELIVERY-V1 / V3's original promise.

Distinct from the per-unit `sources` field (KnowledgeUnit.sources), which cites
where ONE unit's content came from. This ledger instead records the audit trail
of a RUN or a write-back event across the whole episode→exec→telemetry→models
chain — "what happened, when, on what evidence, with what result" — so a later
audit can answer "why does the wiki believe X" without re-deriving it from
scattered result files.

Append-only JSONL. Never rewritten, never deleted from — only appended to.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_LEDGER_PATH: Path | None = None


def _get_ledger_path() -> Path:
    if _LEDGER_PATH is not None:
        return _LEDGER_PATH
    return Path(__file__).resolve().parents[3] / "portal_wiki" / "provenance_ledger.jsonl"


def set_ledger_path(path: Path) -> None:
    """Override the ledger path (for testing)."""
    global _LEDGER_PATH
    _LEDGER_PATH = path


def reset_ledger_path() -> None:
    global _LEDGER_PATH
    _LEDGER_PATH = None


@dataclass
class LedgerEntry:
    """One append-only audit record.

    `evidence_refs` are pointers into results/captures/ or results/*.json —
    not the evidence itself, so the ledger stays small and durable even as
    results files rotate.
    """

    timestamp: float
    episode_id: str
    scenario: str
    red_model: str
    blue_model: str
    capability_verdict: str
    evidence_refs: list[str] = field(default_factory=list)
    wiki_units_written: list[str] = field(default_factory=list)
    library_version: str = ""
    event: str = ""  # "purple_run" | "write_back" — what produced this entry

    def to_dict(self) -> dict:
        return asdict(self)


def append_entry(
    *,
    episode_id: str,
    scenario: str,
    red_model: str = "",
    blue_model: str = "",
    capability_verdict: str = "",
    evidence_refs: list[str] | None = None,
    wiki_units_written: list[str] | None = None,
    library_version: str = "",
    event: str = "",
) -> LedgerEntry:
    """Append one entry to the provenance ledger. Never rewrites prior lines.

    Safe to call from any loop (purple-run completion, write-back confirmation)
    — each call is independent, appended, and immutable once written.
    """
    entry = LedgerEntry(
        timestamp=time.time(),
        episode_id=episode_id,
        scenario=scenario,
        red_model=red_model or "",
        blue_model=blue_model or "",
        capability_verdict=capability_verdict or "",
        evidence_refs=evidence_refs or [],
        wiki_units_written=wiki_units_written or [],
        library_version=library_version or _project_version(),
        event=event,
    )
    path = _get_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")
    return entry


def _project_version() -> str:
    """Best-effort read of the project version from pyproject.toml.

    Never raises — an audit trail entry is worth writing even if the version
    can't be determined (e.g. pyproject.toml moved or is unreadable).
    """
    try:
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def read_ledger() -> list[LedgerEntry]:
    """Read all ledger entries in append order. Returns [] if no ledger exists yet."""
    path = _get_ledger_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(LedgerEntry(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue  # skip malformed lines rather than fail the whole read
    return entries
