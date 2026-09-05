"""Reverse/forward closure for regulatory and internal change impact."""

from __future__ import annotations


def analyze(repo, start_ref: str, *, max_depth: int = 5, max_edges: int = 1000) -> dict:
    from portal.modules.compliance.core.runtime import bump

    bump("impact")
    reverse = repo.traverse_relationships(
        start_ref,
        direction="reverse",
        statuses=("approved", "proposed"),
        max_depth=max_depth,
        max_edges=max_edges,
    )
    forward = repo.traverse_relationships(
        start_ref,
        direction="forward",
        statuses=("approved", "proposed"),
        max_depth=max_depth,
        max_edges=max_edges,
    )
    direct = [edge for edge in reverse["edges"] + forward["edges"] if edge["from"] == start_ref]
    direct_ids = {edge["assertion_id"] for edge in direct}
    transitive = [
        edge
        for edge in reverse["edges"] + forward["edges"]
        if edge["assertion_id"] not in direct_ids
    ]
    return {
        "start_ref": start_ref,
        "direct": direct,
        "transitive": transitive,
        "inferred": [],
        "cutoff": {
            "max_depth": max_depth,
            "max_edges": max_edges,
            "truncated": reverse["truncated"] or forward["truncated"],
        },
        "unexplored_frontier": sorted(
            set(reverse["unexplored_frontier"] + forward["unexplored_frontier"])
        ),
    }
