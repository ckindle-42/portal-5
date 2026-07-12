"""Loop -> wiki record (the CI-gated write path).

A thin wrapper over portal.platform.wiki.writeback.propose_unit: the loop
distills an outcome into a cited proposed unit that lands in
portal_wiki/proposed/ (status "proposed"). Promotion is the gate
(confirm_unit / reject_unit) — nothing auto-merges. Writeback failure never
blocks a loop.
"""

from __future__ import annotations


def record_outcome(
    *,
    title: str,
    body: str,
    sources: list[dict],
    tags: list[str] | None = None,
    proposed_by: str = "agent-loop",
    kind: str = "mixed",
) -> str | None:
    """Propose a unit summarizing a loop outcome. Returns the proposed_id or None."""
    if not sources:
        return None
    try:
        from portal.platform.wiki.writeback import propose_unit

        unit = propose_unit(
            {
                "title": title,
                "kind": kind,
                "sources": sources,
                "body": body,
                "tags": tags or [],
            },
            proposed_by=proposed_by,
        )
        return getattr(unit, "proposed_id", None) or getattr(unit, "id", None)
    except Exception:
        return None
