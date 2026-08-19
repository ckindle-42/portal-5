"""bully.provenance -- anchor provenance tiers, revocation, and depth
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 G.2, guards self-confirmation).

Only `EXTERNAL` and `ANALYST_CONFIRMED` anchors may raise confidence;
`SYSTEM_GENERATED` contributes context but is capped, never ground truth.
Generation depth is recorded (A.1) and capped here: an anchor derived from
an outcome that itself leaned on a `SYSTEM_GENERATED` anchor is depth 2 and
decays past the cap to context-only, regardless of its own tier. When an
analyst overturns an outcome, every anchor derived from it -- transitively
-- is demoted, with an audit trail linking each demoted anchor back to the
revoked outcome.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .anchors import Anchor, AnchorLibrary

MAX_GENERATION_DEPTH = 1  # depth 0-1 may still raise confidence; depth >1 decays

RAISING_TIERS: frozenset[str] = frozenset({"EXTERNAL", "ANALYST_CONFIRMED"})


def can_raise_confidence(anchor: Anchor) -> bool:
    """G.2's core rule: tier gates it, depth caps it. A SYSTEM_GENERATED
    anchor never raises confidence regardless of depth; an EXTERNAL/
    ANALYST_CONFIRMED anchor stops raising confidence once its generation
    depth exceeds the cap (context-only beyond that point)."""
    if anchor.provenance_tier not in RAISING_TIERS:
        return False
    return anchor.generation_depth <= MAX_GENERATION_DEPTH


def context_only(anchor: Anchor) -> bool:
    return not can_raise_confidence(anchor)


@dataclass(frozen=True)
class RevocationRecord:
    anchor_id: str
    outcome_anchor_id: str
    action: str  # "demoted"


def revoke_outcome(
    anchor_library: AnchorLibrary, outcome_anchor_id: str
) -> tuple[RevocationRecord, ...]:
    """Demote the revoked outcome anchor and every anchor transitively
    derived from it to SYSTEM_GENERATED/weak -- never silently leaving a
    now-overturned outcome (or anything built on it) able to raise
    confidence. Demotes rather than deletes, so the audit trail
    (anchor -> outcome) stays inspectable."""
    frontier = [outcome_anchor_id]
    visited: set[str] = set()
    affected: list[Anchor] = []
    while frontier:
        current = frontier.pop()
        for anchor in anchor_library.all():
            if current in anchor.derived_from and anchor.anchor_id not in visited:
                visited.add(anchor.anchor_id)
                affected.append(anchor)
                frontier.append(anchor.anchor_id)

    records: list[RevocationRecord] = []
    root = anchor_library.get(outcome_anchor_id)
    if root is not None:
        anchor_library.add(
            dataclasses.replace(root, provenance_tier="SYSTEM_GENERATED", grade="weak")
        )
        records.append(RevocationRecord(outcome_anchor_id, outcome_anchor_id, "demoted"))
    for anchor in affected:
        anchor_library.add(
            dataclasses.replace(anchor, provenance_tier="SYSTEM_GENERATED", grade="weak")
        )
        records.append(RevocationRecord(anchor.anchor_id, outcome_anchor_id, "demoted"))
    return tuple(records)
