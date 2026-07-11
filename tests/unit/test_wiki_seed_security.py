"""Tests for wiki security seeding — Phase W2.

Validates:
- Technique signatures seeded as cited units
- Every unit has sources (mandatory provenance)
- DCSync specifically gets enriched unit
- wiki.explain returns cited answers for techniques
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from portal.platform.wiki.store import load_all, reset_canonical_dir, set_canonical_dir


class TestSecuritySeeding:
    """Technique signatures seeded as cited units."""

    def test_seed_technique_signatures(self, tmp_path):
        from portal.platform.wiki.adapters.seed_security import seed_technique_signatures

        set_canonical_dir(tmp_path)
        try:
            units = seed_technique_signatures(dry_run=False)
            assert len(units) >= 20
            # Every unit must have sources
            for unit in units:
                assert unit.sources, f"Unit {unit.id} has no sources"
                assert unit.kind == "mixed"
            # Check specific techniques
            ids = [u.id for u in units]
            assert "unit-T1190-signature" in ids
            assert "unit-T1558.003-signature" in ids
        finally:
            reset_canonical_dir()

    def test_dcsync_enriched_unit(self, tmp_path):
        from portal.platform.wiki.adapters.seed_security import seed_dcsync_specifically

        set_canonical_dir(tmp_path)
        try:
            unit = seed_dcsync_specifically(dry_run=False)
            assert unit is not None
            assert unit.id == "unit-T1003.006-signature"
            assert "4662" in unit.body
            assert "Replication-Get-Changes" in unit.body
            assert unit.sources  # has citations
        finally:
            reset_canonical_dir()

    def test_units_loadable_via_mcp(self, tmp_path):
        from portal.platform.wiki.adapters.seed_security import seed_technique_signatures
        from portal_wiki.mcp import wiki_explain, wiki_search

        set_canonical_dir(tmp_path)
        try:
            seed_technique_signatures(dry_run=False)

            # Search for a technique
            result = wiki_search("T1190")
            assert result["count"] > 0

            # Explain returns cited answer
            explain = wiki_explain("T1558.003 Kerberoasting")
            assert explain["sources"]
            assert len(explain["units_referenced"]) > 0
        finally:
            reset_canonical_dir()

    def test_all_units_have_provenance(self, tmp_path):
        from portal.platform.wiki.adapters.seed_security import (
            seed_dcsync_specifically,
            seed_technique_signatures,
        )

        set_canonical_dir(tmp_path)
        try:
            seed_technique_signatures(dry_run=False)
            seed_dcsync_specifically(dry_run=False)

            units = load_all()
            assert len(units) > 0
            for unit in units:
                assert unit.sources, f"Unit {unit.id} has no sources — violates never-bloat rule"
        finally:
            reset_canonical_dir()
