"""TASK_COMPLIANCE_REASONING_V2 P2 — migrating the legacy JSON stores into the
canonical repository. Uses synthetic fixtures only (never the private
operator corpus) so this suite stays hermetic and committable.
"""

from __future__ import annotations

from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.migrate_legacy import (
    import_document_directory,
    import_mapping_store,
    import_register,
    snapshot_legacy_sources,
)
from portal.modules.compliance.core.repository import Repository


def _node(**kw) -> RegisterNode:
    base = {
        "id": "TEST-1 R1 Part 1.1",
        "standard": "TEST-1",
        "version": "1",
        "requirement": "R1",
        "part": "1.1",
        "verbatim_text": "Do the thing.",
        "measure_text": "",
        "applicable_systems": "",
        "table_name": "",
        "vrf": "",
        "time_horizon": "",
        "lifecycle_state": "EFFECTIVE",
        "valid_from": "2020-01-01",
        "valid_to": None,
        "supersedes": None,
        "superseded_by": None,
        "authority_tier": 0,
        "source_pdf": "test-1.pdf",
        "source_pages": [1],
        "recorded_at": 0.0,
        "granularity": "part",
    }
    base.update(kw)
    return RegisterNode(**base)


def test_snapshot_does_not_mutate_the_source_register(tmp_path):
    repo = Repository(tmp_path / "s.db")
    reg = Register(nodes=[_node()])
    before = reg.to_json()
    snap = snapshot_legacy_sources(repo, register=reg)
    assert reg.to_json() == before  # untouched
    assert snap.counts["register_nodes"] == 1
    repo.close()


def test_register_import_creates_unverified_effectivity_never_verified(tmp_path):
    repo = Repository(tmp_path / "s.db")
    reg = Register(
        nodes=[_node(id="TEST-1 R1 Part 1.1"), _node(id="TEST-1 R1 Part 1.2", part="1.2")]
    )
    report = import_register(repo, reg)
    assert report["requirement_nodes_imported"] == 2
    assert report["effectivity_assertions_imported"] == 2
    row = repo._conn.execute(  # noqa: SLF001 - direct read for test assertion
        "SELECT approval_status, valid_from FROM effectivity_assertions WHERE node_id = ?",
        ("TEST-1 R1 Part 1.1",),
    ).fetchone()
    assert row["approval_status"] == "unverified"
    assert row["valid_from"] == "2020-01-01"
    repo.close()


def test_register_import_is_idempotent_on_repeat_run(tmp_path):
    repo = Repository(tmp_path / "s.db")
    reg = Register(nodes=[_node()])
    import_register(repo, reg)
    import_register(repo, reg)  # second run: no duplicates
    n = repo._conn.execute(  # noqa: SLF001
        "SELECT COUNT(*) FROM effectivity_assertions WHERE node_id = ?", ("TEST-1 R1 Part 1.1",)
    ).fetchone()[0]
    assert n == 1
    repo.close()


def test_register_import_dry_run_writes_nothing(tmp_path):
    repo = Repository(tmp_path / "s.db")
    reg = Register(nodes=[_node()])
    report = import_register(repo, reg, dry_run=True)
    assert report["requirement_nodes_imported"] == 1
    n = repo._conn.execute("SELECT COUNT(*) FROM requirement_nodes").fetchone()[0]  # noqa: SLF001
    assert n == 0
    repo.close()


def test_mapping_import_preserves_legacy_provenance_not_authenticated(tmp_path):
    repo = Repository(tmp_path / "s.db")
    store = MappingStore(tmp_path / "m.json")
    mp = store.propose("TEST-1 R1 Part 1.1", "OT-POL-1", "§1", "FULL")
    store.approve(mp.id, "original_sme")

    report = import_mapping_store(repo, store)
    assert report["imported"] == 1
    rel = repo.get_relationship(f"legacy:{mp.id}")
    assert rel.status == "approved"  # authoritative for legacy-compat reads
    # but visibly NOT an authenticated P7 decision:
    assert rel.review_state == "imported_legacy_unverified"
    assert rel.decided_by.startswith("legacy:")
    repo.close()


def test_mapping_import_is_idempotent(tmp_path):
    repo = Repository(tmp_path / "s.db")
    store = MappingStore(tmp_path / "m.json")
    mp = store.propose("TEST-1 R1 Part 1.1", "OT-POL-1", "§1", "FULL")
    store.approve(mp.id, "sme")
    import_mapping_store(repo, store)
    report2 = import_mapping_store(repo, store)
    assert report2["imported"] == 0 and report2["already_imported"] == 1
    repo.close()


def test_document_directory_import_hashes_real_bytes_no_filename_date_guess(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = corpus / "policy_2024.pdf"
    f.write_bytes(b"%PDF-1.4 fake policy content")
    repo = Repository(tmp_path / "s.db")
    report = import_document_directory(repo, corpus)
    assert report["files_seen"] == 1 and report["new_revisions"] == 1
    # logical_id is the source-dir-relative, human-facing name...
    revs = repo.revisions_for_logical_id("policy_2024.pdf")
    assert len(revs) == 1
    # no filename-date guessing — "2024" in the name must not become a date
    assert revs[0].authored_date is None and revs[0].effective_date is None
    # ...while alias_path is the real resolvable filesystem path, so a live
    # integrity check (compliance_sources) can actually open the file again
    # regardless of the caller's current working directory (P8-L live finding).
    assert revs[0].alias_path == str(f)
    assert repo.revisions_for_alias(str(f)) == revs
    repo.close()


def test_document_directory_reimport_is_idempotent_and_detects_replacement(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = corpus / "policy.pdf"
    f.write_bytes(b"version one")
    repo = Repository(tmp_path / "s.db")
    r1 = import_document_directory(repo, corpus)
    assert r1["new_revisions"] == 1
    r2 = import_document_directory(repo, corpus)
    assert r2["new_revisions"] == 0 and r2["already_current"] == 1  # idempotent re-run

    f.write_bytes(b"version two")  # replacement bytes at the same path
    r3 = import_document_directory(repo, corpus)
    assert r3["new_revisions"] == 1
    assert len(repo.revisions_for_alias(str(f))) == 2  # both revisions kept
    repo.close()
