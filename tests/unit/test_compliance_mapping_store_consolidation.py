"""TASK_COMPLIANCE_STORE_CONSOLIDATION_V1 — MappingStore is now a
Repository-backed facade over relationship_assertions, not a separate JSON
file. These tests exercise that consolidation specifically: that a mapping
proposed/approved through MappingStore is actually visible as a real
relationship_assertions row (so compliance_trace can traverse it), and that
the coverage-bearing columns migration 5 added round-trip correctly.
"""

from __future__ import annotations

from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.repository import Repository


def test_approving_a_mapping_creates_a_real_relationship_assertion(tmp_path):
    db_path = tmp_path / "store.db"
    store = MappingStore(db_path)
    mp = store.propose("CIP-007-6 R2 Part 2.2", "OT-POL-007", "§4.2", "FULL", confidence=0.7)
    store.approve(mp.id, "sme@entity")

    # the SAME underlying store, opened as a plain Repository, must see this
    # as a real relationship_assertions row — the whole point of the
    # consolidation is that compliance_trace's traversal sees it too.
    repo = Repository(db_path)
    rel = repo.get_relationship(mp.id)
    assert rel is not None
    assert rel.relation_type == "IMPLEMENTS"
    assert rel.src_ref == "CIP-007-6 R2 Part 2.2"
    assert rel.dst_ref == "OT-POL-007::§4.2"
    assert rel.status == "approved"
    assert rel.coverage == "FULL"
    assert rel.confidence == 0.7


def test_approved_mapping_is_traversable_via_compliance_trace(tmp_path):
    db_path = tmp_path / "store.db"
    store = MappingStore(db_path)
    mp = store.propose("CIP-007-6 R2 Part 2.2", "OT-POL-007", "§4.2", "FULL")
    store.approve(mp.id, "sme")

    repo = Repository(db_path)
    result = repo.traverse_relationships("CIP-007-6 R2 Part 2.2", direction="both", max_depth=2)
    assert result["n_edges"] == 1
    assert result["edges"][0]["assertion_id"] == mp.id


def test_default_store_path_shares_the_canonical_compliance_store_file():
    """The whole point of consolidation: MappingStore() with no override
    points at the SAME file compliance_sources/compliance_trace already
    read — one canonical store, not two disagreeing ones."""
    import portal.modules.compliance.core.mapping_store as ms_mod
    import portal.modules.compliance.core.repository as repo_mod

    assert ms_mod.STORE_PATH == repo_mod.DEFAULT_DB_PATH


def test_revoke_then_reread_via_repository_shows_revoked_status(tmp_path):
    db_path = tmp_path / "store.db"
    store = MappingStore(db_path)
    mp = store.propose("CIP-007-6 R2 Part 2.2", "OT-POL-007", "§4.2", "FULL")
    store.approve(mp.id, "sme")
    store.revoke(mp.id, "sme")

    repo = Repository(db_path)
    rel = repo.get_relationship(mp.id)
    assert rel.status == "revoked"
    assert (
        repo.list_relationship_assertions(ref="CIP-007-6 R2 Part 2.2", statuses=("approved",)) == []
    )


def test_non_mapping_relation_types_are_invisible_to_mapping_store(tmp_path):
    """A structural edge (e.g. a future CROSS_REFERENCES row between two
    requirement nodes) must never masquerade as a coverage mapping just
    because it lives in the same table."""
    from portal.modules.compliance.core.models import RelationshipAssertion

    db_path = tmp_path / "store.db"
    repo = Repository(db_path)
    repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="CROSS_REFERENCES",
            src_ref="CIP-007-6 R2 Part 2.2",
            src_revision_id=None,
            dst_ref="CIP-007-6 R2 Part 2.3",
            dst_revision_id=None,
            scope="",
        )
    )
    store = MappingStore(db_path)
    assert store.all_for("CIP-007-6 R2 Part 2.2") == []
    assert store._rows == []  # noqa: SLF001
