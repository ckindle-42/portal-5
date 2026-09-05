"""Typed traceability traversal used by the MCP operation."""

from __future__ import annotations


def trace(
    repo,
    start_ref: str,
    *,
    direction: str = "both",
    statuses=("approved",),
    max_depth: int = 3,
    max_edges: int = 500,
) -> dict:
    from portal.modules.compliance.core.runtime import bump

    bump("traceability")
    result = repo.traverse_relationships(
        start_ref,
        direction=direction,
        statuses=tuple(statuses),
        max_depth=max_depth,
        max_edges=max_edges,
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
    return result
