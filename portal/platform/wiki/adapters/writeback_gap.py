"""Gap engine → wiki write-back — Phase P5.

When a gap is resolved (detection added, scenario added), the gap engine
updates the relevant wiki unit's coverage status.
"""

from __future__ import annotations


def writeback_gap_resolution(
    technique_id: str,
    gap_summary: str,
    episode_id: str = "",
    *,
    auto_confirm: bool = False,
) -> dict | None:
    """Write a gap resolution back to the wiki as an updated unit.

    Args:
        technique_id: MITRE ATT&CK technique ID
        gap_summary: the CoverageSummary value (COVERED, RED_ONLY, etc.)
        episode_id: the episode that changed the gap status
        auto_confirm: if True, skip confirm gate

    Returns:
        proposed unit dict, or None on failure
    """
    from portal.platform.wiki.writeback import propose_unit

    sources = [
        {"type": "mitre", "path": f"ATT&CK:{technique_id}"},
    ]
    if episode_id:
        sources.append({"type": "scenario", "path": f"episode:{episode_id}"})

    try:
        pu = propose_unit(
            {
                "title": f"{technique_id} — Coverage Status: {gap_summary}",
                "kind": "mixed",
                "sources": sources,
                "body": (
                    f"# {technique_id} — Coverage Status Update\n\n"
                    f"**Technique:** {technique_id}\n\n"
                    f"**Coverage:** {gap_summary}\n\n"
                    f"**Episode:** {episode_id or 'N/A'}\n\n"
                    f"**Updated by:** gap engine\n"
                ),
                "tags": [technique_id, "gap-engine", gap_summary.lower()],
            },
            proposed_by="gap-engine",
            auto_confirm=auto_confirm,
        )
        return pu.to_dict()
    except Exception:
        return None
