"""TASK_COMPLIANCE_REASONING_V2 P2 — the canonical versioned compliance store.

Exit criteria under test: migration roundtrip, broken-reference rejection,
same-path new revision (with historical anchors still resolving), crash
recovery (idempotent re-migration), decision concurrency, and as-known
replay — without touching unrelated ``kb_*`` indexes (there are none here;
this store is entirely separate from the LanceDB retrieval tables).
"""

from __future__ import annotations

import sqlite3

import pytest

from portal.modules.compliance.core.migrations import (
    CURRENT_SCHEMA_VERSION,
    apply_migrations,
    get_schema_version,
)
from portal.modules.compliance.core.models import (
    RelationshipAssertion,
    SourceDocument,
)
from portal.modules.compliance.core.repository import (
    BrokenReferenceError,
    ConcurrencyError,
    Repository,
)
from portal.modules.compliance.core.temporal import now_iso


@pytest.fixture
def repo(tmp_path):
    r = Repository(tmp_path / "store.db")
    yield r
    r.close()


# ── migration roundtrip / idempotence / crash recovery ──────────────────────
def test_migration_reaches_current_version_and_is_idempotent(repo):
    assert repo.schema_version == CURRENT_SCHEMA_VERSION
    report = repo.migrate()
    assert report["applied"] == []  # nothing pending — safe to call again
    assert (
        report["schema_version_before"] == report["schema_version_after"] == CURRENT_SCHEMA_VERSION
    )


def test_migration_from_scratch_reports_every_applied_version(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "fresh.db"))
    assert get_schema_version(conn) == 0
    report = apply_migrations(conn)
    assert report["schema_version_before"] == 0
    assert report["schema_version_after"] == CURRENT_SCHEMA_VERSION
    assert [m["version"] for m in report["applied"]] == list(range(1, CURRENT_SCHEMA_VERSION + 1))
    conn.close()


def test_crash_mid_migration_leaves_prior_version_not_half_upgraded(tmp_path, monkeypatch):
    """Simulates a crash mid-migration: a failing statement in a later
    migration must not leave earlier-in-the-same-call migrations applied —
    the whole call is one transaction. A subsequent clean call then succeeds
    (resume), proving the store recovers rather than wedging."""
    import portal.modules.compliance.core.migrations as mig

    conn = sqlite3.connect(str(tmp_path / "crash.db"))
    bad_migrations = [
        (1, "ok", "CREATE TABLE t1(id TEXT PRIMARY KEY);"),
        (2, "broken", "THIS IS NOT VALID SQL;"),
    ]
    monkeypatch.setattr(mig, "MIGRATIONS", bad_migrations)
    with pytest.raises(sqlite3.OperationalError):
        mig.apply_migrations(conn)
    # crashed mid-way: version 1's table must NOT exist either (one transaction)
    assert get_schema_version(conn) == 0
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "t1" not in tables

    # resume with the real, valid migrations — the store is not wedged
    monkeypatch.undo()
    report = mig.apply_migrations(conn)
    assert report["schema_version_after"] == CURRENT_SCHEMA_VERSION
    conn.close()


# ── document revisions: same-path new revision, historical anchors resolve ─
def test_identical_bytes_reingested_are_idempotent(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "Title", "issuer", "policy", "US"))
    r1 = repo.add_document_revision("DOC-1", "policy.pdf", b"hello world")
    r2 = repo.add_document_revision("DOC-1", "policy.pdf", b"hello world")
    assert r1.revision_id == r2.revision_id
    assert len(repo.revisions_for_alias("policy.pdf")) == 1


def test_replacement_bytes_at_same_path_create_new_revision_old_still_resolves(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "Title", "issuer", "policy", "US"))
    old = repo.add_document_revision("DOC-1", "policy.pdf", b"version one text")
    new = repo.add_document_revision("DOC-1", "policy.pdf", b"version two text")
    assert old.revision_id != new.revision_id
    revisions = repo.revisions_for_alias("policy.pdf")
    assert {r.revision_id for r in revisions} == {old.revision_id, new.revision_id}
    # the OLD revision id still resolves directly — a historical anchor into
    # it is not silently redirected or deleted when the alias moves on.
    assert repo.get_revision(old.revision_id) is not None


# ── broken-reference rejection ──────────────────────────────────────────────
def test_relationship_to_nonexistent_revision_is_rejected(repo):
    with pytest.raises(BrokenReferenceError):
        repo.propose_relationship(
            RelationshipAssertion(
                assertion_id="",
                relation_type="IMPLEMENTS",
                src_ref="CIP-007-6 R2 Part 2.2",
                src_revision_id=None,
                dst_ref="POL-1 §1",
                dst_revision_id="does-not-exist",
                scope="",
            )
        )


def test_source_section_to_nonexistent_revision_is_rejected(repo):
    from portal.modules.compliance.core.models import SourceSection

    with pytest.raises(BrokenReferenceError):
        repo.add_source_section(SourceSection(section_id="s1", revision_id="ghost", path="§1"))


# ── proposal/effective separation ───────────────────────────────────────────
def test_governed_read_defaults_to_approved_only(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "T", "i", "policy", "US"))
    rev = repo.add_document_revision("DOC-1", "policy.pdf", b"text")
    proposed = repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="REQ-1",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=rev.revision_id,
            scope="",
        )
    )
    # a caller that forgets to widen the status filter sees NOTHING proposed
    assert repo.list_relationship_assertions(ref="REQ-1") == []
    assert repo.list_relationship_assertions(ref="REQ-1", statuses=("proposed",)) != []

    approved = repo.decide_relationship(
        proposed.assertion_id, "CONFIRMED", "sme_a", expected_version=1
    )
    assert approved.status == "approved"
    assert repo.list_relationship_assertions(ref="REQ-1")[0].assertion_id == proposed.assertion_id


# ── decision concurrency (P7/A25) ───────────────────────────────────────────
def test_stale_expected_version_is_rejected_not_silently_overwritten(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "T", "i", "policy", "US"))
    rev = repo.add_document_revision("DOC-1", "policy.pdf", b"text")
    proposed = repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="REQ-1",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=rev.revision_id,
            scope="",
        )
    )
    repo.decide_relationship(proposed.assertion_id, "CONFIRMED", "sme_a", expected_version=1)
    # a second reviewer submits against the version they read BEFORE sme_a's
    # decision landed — the write is rejected, never silently applied on top.
    with pytest.raises(ConcurrencyError):
        repo.decide_relationship(proposed.assertion_id, "REJECTED", "sme_b", expected_version=1)
    # the confirmed decision stands
    current = repo.get_relationship(proposed.assertion_id)
    assert current.status == "approved" and current.version == 2


def test_revoking_a_confirmed_mapping_removes_it_from_effective_reads(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "T", "i", "policy", "US"))
    rev = repo.add_document_revision("DOC-1", "policy.pdf", b"text")
    proposed = repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="REQ-1",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=rev.revision_id,
            scope="",
        )
    )
    confirmed = repo.decide_relationship(
        proposed.assertion_id, "CONFIRMED", "sme_a", expected_version=1
    )
    assert repo.list_relationship_assertions(ref="REQ-1")
    repo.decide_relationship(
        proposed.assertion_id, "REVOKED", "sme_b", expected_version=confirmed.version
    )
    assert repo.list_relationship_assertions(ref="REQ-1") == []


# ── outbox / invalidation ───────────────────────────────────────────────────
def test_decision_writes_an_invalidation_outbox_event(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "T", "i", "policy", "US"))
    rev = repo.add_document_revision("DOC-1", "policy.pdf", b"text")
    proposed = repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="REQ-1",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=rev.revision_id,
            scope="",
        )
    )
    repo.decide_relationship(proposed.assertion_id, "CONFIRMED", "sme_a", expected_version=1)
    events = repo.drain_outbox()
    types = [e.event_type for e in events]
    assert "relationship_proposed" in types and "relationship_decided" in types
    # drained once — a second drain finds nothing new
    assert repo.drain_outbox() == []


# ── as-known replay ──────────────────────────────────────────────────────
def test_as_known_replay_reflects_history_not_current_state(repo):
    repo.upsert_source_document(SourceDocument("DOC-1", "T", "i", "policy", "US"))
    rev = repo.add_document_revision("DOC-1", "policy.pdf", b"text")
    proposed = repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="REQ-1",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=rev.revision_id,
            scope="",
        )
    )
    before_decision = "2026-01-01T00:00:00"
    confirmed = repo.decide_relationship(
        proposed.assertion_id, "CONFIRMED", "sme_a", expected_version=1
    )
    after_confirm = repo.get_relationship(proposed.assertion_id).decided_at
    repo.decide_relationship(
        proposed.assertion_id, "REVOKED", "sme_b", expected_version=confirmed.version
    )
    current = repo.get_relationship(proposed.assertion_id)
    assert current.status == "revoked"  # CURRENT state
    # AS-KNOWN replay for a timestamp before either decision existed:
    assert repo.status_as_known(proposed.assertion_id, before_decision) == "proposed"
    # AS-KNOWN replay for a timestamp right after the confirm, before the revoke:
    assert repo.status_as_known(proposed.assertion_id, after_confirm) == "approved"
    # AS-KNOWN replay for now reflects the full history, matching current:
    assert repo.status_as_known(proposed.assertion_id, now_iso()) == "revoked"


# ── backup / restore ─────────────────────────────────────────────────────
def test_backup_and_restore_roundtrip(repo, tmp_path):
    repo.upsert_source_document(SourceDocument("DOC-1", "T", "i", "policy", "US"))
    repo.add_document_revision("DOC-1", "policy.pdf", b"text")
    backup_path = repo.backup_to(tmp_path / "backup.db")
    restored = Repository.restore_from(backup_path, tmp_path / "restored.db")
    try:
        assert restored.revisions_for_alias("policy.pdf")
        assert restored.schema_version == CURRENT_SCHEMA_VERSION
    finally:
        restored.close()
