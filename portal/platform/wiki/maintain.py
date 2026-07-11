"""Self-maintenance loop — keep the wiki current as code moves.

Phase W3 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.

Re-runs the code pass → updates WHAT units + re-cites + bumps
last_generated_commit.  WHY units persist unless deliberately revised.
Snapshot-diff (hash the canonical dir) so a no-change run produces no churn.
"""

from __future__ import annotations

import hashlib

from portal.platform.wiki.schema import KnowledgeUnit
from portal.platform.wiki.store import load_all


def canonical_snapshot_hash() -> str:
    """Hash the canonical directory for change detection.

    Returns a hash of all unit content — if nothing changed, the hash
    is the same and no update is needed.
    """
    units = load_all()
    content = "".join(sorted(u.content_hash() for u in units))
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def check_staleness(current_commit: str) -> list[dict]:
    """Check which units are stale (generated against an older commit).

    Returns list of {unit_id, generated_commit, commits_behind} dicts.
    """
    units = load_all()
    stale = []
    for unit in units:
        if unit.last_generated_commit and unit.last_generated_commit != current_commit:
            stale.append(
                {
                    "unit_id": unit.id,
                    "kind": unit.kind,
                    "generated_commit": unit.last_generated_commit,
                    "current_commit": current_commit,
                }
            )
    return stale


def update_what_units(current_commit: str, dry_run: bool = False) -> list[KnowledgeUnit]:
    """Update WHAT units from code.  WHY units are untouched.

    Returns list of updated units.
    """
    from portal.platform.wiki.adapters.seed_code import seed_code
    from portal.platform.wiki.adapters.seed_security import (
        seed_dcsync_specifically,
        seed_technique_signatures,
    )

    # Take a snapshot before
    before_hash = canonical_snapshot_hash()

    # Re-run the code seeder
    updated = seed_code(dry_run=dry_run)

    # Re-run the security technique-signature seeder (W2) — idempotent: save_unit()
    # overwrites by unit.id, so re-seeding updates in place rather than duplicating.
    # This was previously implemented but never invoked anywhere outside its own
    # tests, so the 30 technique-signature units (29 techniques + enriched DCSync)
    # never landed in the store that load_all()/similarity/blue-lookup reads.
    updated += seed_technique_signatures(dry_run=dry_run)
    dcsync_unit = seed_dcsync_specifically(dry_run=dry_run)
    if dcsync_unit is not None:
        updated.append(dcsync_unit)

    # Check if anything actually changed
    after_hash = canonical_snapshot_hash() if not dry_run else before_hash

    if before_hash == after_hash and not dry_run:
        return []  # no churn

    return updated


def wiki_status(current_commit: str) -> dict:
    """Report wiki status: unit count, staleness, freshness."""
    units = load_all()
    stale = check_staleness(current_commit)

    return {
        "total_units": len(units),
        "what_units": sum(1 for u in units if u.kind == "what"),
        "why_units": sum(1 for u in units if u.kind == "why"),
        "mixed_units": sum(1 for u in units if u.kind == "mixed"),
        "stale_units": len(stale),
        "current_commit": current_commit,
        "snapshot_hash": canonical_snapshot_hash(),
    }
