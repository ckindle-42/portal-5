"""Self-maintenance loop — keep the wiki current as code moves.

Phase W3 of BUILD_PROGRAM_SEC_RBP_WIKI_FIXES_V1.

Re-runs the code pass → updates WHAT units + re-cites.  WHY units persist
unless deliberately revised.  Snapshot-diff (hash the canonical dir) so a
no-change run produces no churn.  (P0 A1 removed the `last_generated_commit`
pin this module used to also bump.)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from portal.platform.wiki.audit import audit_units
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


def _regenerate_derived_units() -> list[KnowledgeUnit]:
    """Build code-seeded units in memory without writing the store."""
    from portal.platform.plugins import wiki_seeders
    from portal.platform.wiki.adapters.seed_code import seed_code

    units = seed_code(dry_run=True)
    for seeder in wiki_seeders():
        units += seeder(True)
    return units


def check_staleness(
    current_commit: str,
    repo_root: Path | None = None,
    regenerated_units: list[KnowledgeUnit] | None = None,
) -> list[dict[str, Any]]:
    """Compare machine-derived unit bodies with exact current derivations.

    Advancing HEAD alone does not make an authored canonical unit stale.
    Authored units are the spine; provenance is navigation, not reverse
    authority. Stored code-derived units are stale only when their would-be
    body differs from the canonical body. Live fact units are resolved by MCP.
    """
    del repo_root  # retained for backward-compatible callers
    units = {unit.id: unit for unit in load_all()}
    if regenerated_units is None:
        regenerated_units = _regenerate_derived_units()
    fresh_by_id = {unit.id: unit for unit in regenerated_units}
    stale: list[dict[str, Any]] = []
    for fresh in fresh_by_id.values():
        stored = units.get(fresh.id)
        if stored is None or stored.body.strip() != fresh.body.strip():
            stale.append(
                {
                    "unit_id": fresh.id,
                    "kind": fresh.kind,
                    "current_commit": current_commit,
                }
            )
    return stale


def update_what_units(current_commit: str, dry_run: bool = False) -> list[KnowledgeUnit]:
    """Update WHAT units from code.  WHY units are untouched.

    Returns list of updated units.
    """
    from portal.platform.plugins import wiki_seeders
    from portal.platform.wiki.adapters.seed_code import seed_code

    # Take a snapshot before
    before_hash = canonical_snapshot_hash()

    # Re-run the code seeder
    updated = seed_code(dry_run=dry_run)

    for seeder in wiki_seeders():
        updated += seeder(dry_run)

    # Check if anything actually changed
    after_hash = canonical_snapshot_hash() if not dry_run else before_hash

    if before_hash == after_hash and not dry_run:
        return []  # no churn

    return updated


def wiki_status(current_commit: str, repo_root: Path | None = None) -> dict[str, Any]:
    """Report wiki status: unit count, staleness, freshness."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]
    units = load_all()
    stale = check_staleness(current_commit, repo_root)
    integrity_issues = audit_units(repo_root, units)

    return {
        "total_units": len(units),
        "what_units": sum(1 for u in units if u.kind == "what"),
        "why_units": sum(1 for u in units if u.kind == "why"),
        "mixed_units": sum(1 for u in units if u.kind == "mixed"),
        "stale_units": len(stale),
        "integrity_issues": len(integrity_issues),
        "current_commit": current_commit,
        "snapshot_hash": canonical_snapshot_hash(),
    }
