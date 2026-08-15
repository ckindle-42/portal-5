"""bully.events -- hash-chained decision-event emission (P1.2).

Pure compute: given the previous chain hash and an event's own content,
produce the next chain hash. `store.py` is the only module that persists a
`DecisionEvent`; it calls `compute_chain_hash` at insert time so the chain
computation itself stays testable without a database.
"""

from __future__ import annotations

import hashlib
import json

from .contracts import DecisionEvent

GENESIS_HASH = "0" * 64


def _canonical_payload(event: DecisionEvent) -> dict:
    """The fields that participate in the hash -- excludes the hash fields
    themselves and `recorded_at` (server-assigned, not part of the event's
    own content)."""
    return {
        "event_id": event.event_id,
        "hunt_id": event.hunt_id,
        "iteration_id": event.iteration_id,
        "actor": event.actor,
        "kind": event.kind,
        "subject_id": event.subject_id,
        "rationale": event.rationale,
        "data": event.data,
        "occurred_at": event.occurred_at,
    }


def compute_chain_hash(prev_event_hash: str | None, event: DecisionEvent) -> str:
    """`chain_hash = sha256(prev_hash || canonical(event))`.

    Tamper-evidence, not a backup substitute (DATA_MODEL SS1.9): any
    mutation of a stored event, or reordering, breaks every following
    chain_hash when replayed.
    """
    prev = prev_event_hash or GENESIS_HASH
    canonical = json.dumps(_canonical_payload(event), sort_keys=True, default=str)
    return hashlib.sha256((prev + canonical).encode("utf-8")).hexdigest()


def verify_chain(events_in_order: list[DecisionEvent]) -> tuple[bool, str | None]:
    """Replay a hunt's event sequence and confirm every chain_hash still matches.

    Returns (ok, first_broken_event_id_or_none). Pure -- the caller (store.py
    `hunt doctor`, or a test) supplies the events already read from SQLite in
    recorded order.
    """
    prev_hash: str | None = None
    for event in events_in_order:
        expected = compute_chain_hash(prev_hash, event)
        if event.chain_hash != expected:
            return False, event.event_id
        prev_hash = event.chain_hash
    return True, None
