"""Reverse/forward closure for regulatory and internal change impact.

Established impact is computed from **approved** edges only. Proposed
assertions — including the folder/prefix Cartesian candidates quarantined in
Phase 4 (``derivation='folder_cartesian'``) — never merge into the
deterministic impact claim; they are returned separately as
``discovery_candidates`` so a caller can see what *might* relate without the
proposal reading as established fact (lesson L19).

Phase 5: ``valid_at``/``known_at`` apply both clocks to every traversal, and
the result discloses how many edges each clock excluded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portal.modules.compliance.core.repository import Repository


def analyze(
    repo: Repository,
    start_ref: str,
    *,
    max_depth: int = 5,
    max_edges: int = 1000,
    include_discovery: bool = True,
    valid_at: str | None = None,
    known_at: str | None = None,
) -> dict[str, Any]:
    from portal.modules.compliance.core.runtime import bump
    from portal.modules.compliance.core.temporal_selection import temporal_exclusion_census

    bump("impact")
    reverse = repo.traverse_relationships(
        start_ref,
        direction="reverse",
        statuses=("approved",),
        max_depth=max_depth,
        max_edges=max_edges,
        valid_at=valid_at,
        known_at=known_at,
    )
    forward = repo.traverse_relationships(
        start_ref,
        direction="forward",
        statuses=("approved",),
        max_depth=max_depth,
        max_edges=max_edges,
        valid_at=valid_at,
        known_at=known_at,
    )
    direct = [edge for edge in reverse["edges"] + forward["edges"] if edge["from"] == start_ref]
    direct_ids = {edge["assertion_id"] for edge in direct}
    transitive = [
        edge
        for edge in reverse["edges"] + forward["edges"]
        if edge["assertion_id"] not in direct_ids
    ]
    result: dict[str, Any] = {
        "start_ref": start_ref,
        "direct": direct,
        "transitive": transitive,
        "inferred": [],
        # Establish impact on governed edges only; proposals live in
        # discovery_candidates and never in direct/transitive.
        "established_statuses": ("approved",),
        "cutoff": {
            "max_depth": max_depth,
            "max_edges": max_edges,
            "truncated": reverse["truncated"] or forward["truncated"],
        },
        "unexplored_frontier": sorted(
            set(reverse["unexplored_frontier"] + forward["unexplored_frontier"])
        ),
    }
    if valid_at or known_at:
        result["temporal"] = {
            "valid_at": valid_at or "any",
            "known_at": known_at or "latest recorded knowledge",
            "excluded_unknown_validity": temporal_exclusion_census(
                repo._conn, valid_at=valid_at, known_at=known_at, statuses=("approved",)
            )["excluded_unknown_validity"],
        }
    if include_discovery:
        proposed = repo.list_relationship_assertions(
            ref=start_ref, statuses=("proposed",), valid_at=valid_at, known_at=known_at
        )
        result["discovery_candidates"] = [
            {
                "assertion_id": rel.assertion_id,
                "relation_type": rel.relation_type,
                "from": rel.src_ref,
                "to": rel.dst_ref,
                "derivation": rel.derivation,
                "note": "discovery-only; not an established trace or impact edge",
            }
            for rel in proposed
        ]
    return result
