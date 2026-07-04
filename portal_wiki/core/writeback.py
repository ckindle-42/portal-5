"""Write-back API — confirm-gated path for loops to propose units.

Phase P1 of BUILD_PROGRAM_WIKI_FEATURE_COMPLETE_V1.

ONE reusable path every loop uses to propose a unit into the canonical
layer — confirm-gated, provenance-required, deterministic.

Loops don't each reinvent writing.  They call propose_unit(); the unit
sits in proposed/ until confirmed (or auto-confirmed if the operator
opts a specific loop in).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .schema import KnowledgeUnit, SourceRef
from .store import save_unit

# Proposed units staging directory
_PROPOSED_DIR: Path | None = None


def _get_proposed_dir() -> Path:
    if _PROPOSED_DIR is not None:
        return _PROPOSED_DIR
    return Path(__file__).resolve().parent.parent / "proposed"


def set_proposed_dir(path: Path) -> None:
    global _PROPOSED_DIR
    _PROPOSED_DIR = path


def reset_proposed_dir() -> None:
    global _PROPOSED_DIR
    _PROPOSED_DIR = None


@dataclass
class ProposedUnit:
    """A unit proposed by a loop, pending confirmation."""

    proposed_id: str
    unit_id: str  # the target unit ID when confirmed
    kind: str
    title: str
    sources: list[dict]  # serialized SourceRef dicts
    body: str
    tags: list[str] = field(default_factory=list)
    proposed_by: str = ""  # which loop/agent proposed this
    proposed_at: float = 0.0
    status: str = "proposed"  # "proposed" | "confirmed" | "rejected"
    auto_confirm: bool = False  # if True, skip confirm gate

    def to_dict(self) -> dict:
        return asdict(self)


def propose_unit(
    candidate: dict,
    *,
    proposed_by: str = "",
    auto_confirm: bool = False,
) -> ProposedUnit:
    """Propose a unit into the canonical layer.

    Args:
        candidate: dict with at least {title, kind, sources: [{type, path}]},
                   plus optional {body, tags, id}
        proposed_by: which loop/agent proposed this (for audit)
        auto_confirm: if True, skip confirm gate (operator opt-in per loop)

    Returns:
        ProposedUnit with status="proposed" (or "confirmed" if auto_confirm).

    Raises:
        ValueError: if sources is empty (provenance required) or kind is invalid
    """
    sources_raw = candidate.get("sources", [])
    if not sources_raw:
        raise ValueError(
            f"Cannot propose unit '{candidate.get('title', '?')}' — "
            "every unit must cite its source (never-bloat rule)"
        )

    kind = candidate.get("kind", "")
    if kind not in ("what", "why", "mixed"):
        raise ValueError(f"Invalid kind '{kind}'; must be what|why|mixed")

    # Build sources
    sources = []
    for s in sources_raw:
        if isinstance(s, SourceRef):
            sources.append(s)
        elif isinstance(s, dict):
            sources.append(SourceRef.from_dict(s))
        else:
            raise ValueError(f"Invalid source type: {type(s)}")

    # Generate unit ID if not provided
    unit_id = candidate.get("id", "")
    if not unit_id:
        import re

        title_slug = re.sub(r"[^a-z0-9]+", "-", candidate["title"].lower().strip())[:40]
        source_type = sources[0].type if sources else "unknown"
        unit_id = f"unit-{source_type}-{title_slug}-{int(time.time()) % 100000}"

    proposed_id = f"proposed-{unit_id}-{int(time.time())}"

    proposed = ProposedUnit(
        proposed_id=proposed_id,
        unit_id=unit_id,
        kind=kind,
        title=candidate["title"],
        sources=[s.to_dict() for s in sources],
        body=candidate.get("body", ""),
        tags=candidate.get("tags", []),
        proposed_by=proposed_by,
        proposed_at=time.time(),
        status="proposed",
        auto_confirm=auto_confirm,
    )

    # Save to staging
    proposed_dir = _get_proposed_dir()
    proposed_dir.mkdir(parents=True, exist_ok=True)
    path = proposed_dir / f"{proposed_id}.json"
    path.write_text(json.dumps(proposed.to_dict(), indent=2), encoding="utf-8")

    # Auto-confirm if opted in
    if auto_confirm:
        return confirm_unit(proposed_id)

    return proposed


def confirm_unit(proposed_id: str) -> ProposedUnit:
    """Confirm a proposed unit — promotes it to the canonical layer.

    Args:
        proposed_id: the proposed unit ID

    Returns:
        ProposedUnit with status="confirmed"

    Raises:
        FileNotFoundError: if proposed_id not found
    """
    proposed_dir = _get_proposed_dir()
    path = proposed_dir / f"{proposed_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Proposed unit '{proposed_id}' not found")

    data = json.loads(path.read_text(encoding="utf-8"))
    proposed = ProposedUnit(**data)

    if proposed.status == "confirmed":
        return proposed  # idempotent

    # Build the KnowledgeUnit
    sources = [SourceRef.from_dict(s) for s in proposed.sources]
    unit = KnowledgeUnit(
        id=proposed.unit_id,
        kind=proposed.kind,
        title=proposed.title,
        sources=sources,
        body=proposed.body,
        tags=proposed.tags,
    )

    # Save to canonical
    save_unit(unit)

    # Update proposed status
    proposed.status = "confirmed"
    path.write_text(json.dumps(proposed.to_dict(), indent=2), encoding="utf-8")

    return proposed


def list_proposed(status: str = "proposed") -> list[ProposedUnit]:
    """List proposed units, optionally filtered by status."""
    proposed_dir = _get_proposed_dir()
    if not proposed_dir.exists():
        return []

    results = []
    for path in sorted(proposed_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pu = ProposedUnit(**data)
            if not status or pu.status == status:
                results.append(pu)
        except Exception:
            continue
    return results


def reject_unit(proposed_id: str) -> ProposedUnit:
    """Reject a proposed unit."""
    proposed_dir = _get_proposed_dir()
    path = proposed_dir / f"{proposed_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Proposed unit '{proposed_id}' not found")

    data = json.loads(path.read_text(encoding="utf-8"))
    proposed = ProposedUnit(**data)
    proposed.status = "rejected"
    path.write_text(json.dumps(proposed.to_dict(), indent=2), encoding="utf-8")
    return proposed
