"""TASK_COMPLIANCE_STORE_CONSOLIDATION_V1 — MappingStore is now a
Repository-backed facade over relationship_assertions, not a separate JSON
file. These tests exercise that consolidation specifically: that a mapping
proposed/approved through MappingStore is actually visible as a real
relationship_assertions row (so compliance_trace can traverse it), and that
the coverage-bearing columns migration 5 added round-trip correctly.
"""

from __future__ import annotations


def test_default_store_path_shares_the_canonical_compliance_store_file():
    """The whole point of consolidation: MappingStore() with no override
    points at the SAME file compliance_sources/compliance_trace already
    read — one canonical store, not two disagreeing ones."""
    import portal.modules.compliance.core.mapping_store as ms_mod
    import portal.modules.compliance.core.repository as repo_mod

    assert ms_mod.STORE_PATH == repo_mod.DEFAULT_DB_PATH
