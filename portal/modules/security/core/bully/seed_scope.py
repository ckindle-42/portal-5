"""bully.seed_scope -- seed contract + constructed scope
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 B.2).

A seed (detection fire, advisory, red-team event, operator hunch) names an
entity/time neighbourhood of interest; scope is *constructed* from it by
traversal bounded by what the source actually supports (S1: a
capability-poor source degrades honestly rather than erroring). Identical
seed + bounds always produce an identical scope -- `scope_id` is a
deterministic hash of the request, never random, so a re-run is provably
the same investigation input.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .connectors import QueryIntent
from .data_plane import DataPlane

SEED_KINDS: tuple[str, ...] = (
    "detection_fire",
    "advisory",
    "red_team_event",
    "operator_hunch",
)

DEFAULT_SCALE_CAP = 500


@dataclass(frozen=True)
class Seed:
    seed_id: str
    kind: str
    entities: tuple[str, ...] = ()
    start: float | None = None
    end: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in SEED_KINDS:
            raise ValueError(f"unknown seed kind: {self.kind!r}")


@dataclass(frozen=True)
class ScopeBounds:
    entities: tuple[str, ...]
    start: float | None
    end: float | None
    scale_cap: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": list(self.entities),
            "start": self.start,
            "end": self.end,
            "scale_cap": self.scale_cap,
        }


@dataclass(frozen=True)
class Scope:
    scope_id: str
    seed_id: str
    source_id: str
    bounds: ScopeBounds
    records: tuple[Any, ...]
    episode_boundary: bool
    truncated: bool
    degraded: bool
    reasons: tuple[str, ...]
    created_at: float = field(default_factory=time.time)


def _scope_id(seed: Seed, source_id: str, bounds: ScopeBounds) -> str:
    """Deterministic -- same seed + source + bounds always hashes the same,
    so identical inputs produce an identical scope_id (the B.2 idempotency
    claim), independent of wall-clock call time."""
    payload = {"seed_id": seed.seed_id, "source_id": source_id, "bounds": bounds.to_dict()}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return f"scope-{digest[:16]}"


def build_scope(
    seed: Seed,
    plane: DataPlane,
    source_id: str,
    *,
    scale_cap: int = DEFAULT_SCALE_CAP,
) -> Scope:
    """Construct scope for `seed` against one connected source, bounded by
    what that source's capability profile supports. Never raises for a
    capability-poor source -- it degrades the traversal and records why."""
    profile = plane.catalog.get(source_id)
    reasons: list[str] = []

    entities = seed.entities
    if profile is not None and not profile.capabilities.entity_identity and entities:
        reasons.append("entity_identity_absent:time_only_traversal")
        entities = ()

    episode_boundary = bool(profile is not None and profile.capabilities.episode_boundary)
    if not episode_boundary:
        reasons.append("episode_boundary_absent:flat_scope")

    bounds = ScopeBounds(entities=entities, start=seed.start, end=seed.end, scale_cap=scale_cap)

    intent = QueryIntent(
        purpose=f"scope:{seed.kind}",
        seed={"seed_id": seed.seed_id, **seed.payload},
        start=bounds.start,
        end=bounds.end,
        entities=bounds.entities,
        limit=bounds.scale_cap,
    )
    result = plane.query(source_id, intent)
    if result.truncated:
        reasons.append("scale_cap_reached")
    if profile is None:
        reasons.append("source_unprofiled:degraded_scope")

    return Scope(
        scope_id=_scope_id(seed, source_id, bounds),
        seed_id=seed.seed_id,
        source_id=source_id,
        bounds=bounds,
        records=result.records,
        episode_boundary=episode_boundary,
        truncated=result.truncated,
        degraded=bool(reasons),
        reasons=tuple(reasons),
    )
