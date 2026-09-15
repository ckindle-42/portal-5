"""Typed traceability traversal used by the MCP operation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portal.modules.compliance.core.repository import Repository


def trace(
    repo: Repository,
    start_ref: str,
    *,
    direction: str = "both",
    statuses: tuple[str, ...] = ("approved",),
    max_depth: int = 3,
    max_edges: int = 500,
    valid_at: str | None = None,
    known_at: str | None = None,
) -> dict[str, Any]:
    """Typed traceability traversal used by the MCP operation.

    ``valid_at``/``known_at`` apply both clocks to every edge (Phase 5);
    when ``valid_at`` is requested, the result discloses how many edges were
    excluded for unknown validity so a temporal trace can never silently
    read as complete."""
    from portal.modules.compliance.core.runtime import bump
    from portal.modules.compliance.core.temporal_selection import temporal_exclusion_census

    bump("traceability")
    result = repo.traverse_relationships(
        start_ref,
        direction=direction,
        statuses=statuses,
        max_depth=max_depth,
        max_edges=max_edges,
        valid_at=valid_at,
        known_at=known_at,
    )
    result["paths"] = [
        {
            "edge_type": edge["relation_type"],
            "source": edge["from"],
            "target": edge["to"],
            "anchors": edge["citations"],
        }
        for edge in result["edges"]
    ]
    if valid_at or known_at:
        result["temporal"] = {
            "valid_at": valid_at or "any",
            "known_at": known_at or "latest recorded knowledge",
            "excluded_unknown_validity": temporal_exclusion_census(
                repo._conn, valid_at=valid_at, known_at=known_at, statuses=statuses
            )["excluded_unknown_validity"],
        }
    return result
