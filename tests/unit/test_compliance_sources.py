"""TASK_COMPLIANCE_REASONING_V2 P7 — compliance_sources: the first MCP
operation wired to the P2 canonical repository (core.repository) rather than
the legacy JSON stores.
"""

from __future__ import annotations

from portal.modules.compliance.core.models import SourceDocument


def _repo(tmp_path, monkeypatch):
    from portal.modules.compliance.core import repository as repo_mod

    db_path = tmp_path / "store.db"
    monkeypatch.setattr(repo_mod, "DEFAULT_DB_PATH", db_path)
    # `compliance_sources` constructs `Repository()` with no override — its
    # default arg was already bound to the OLD DEFAULT_DB_PATH at class
    # definition time, so the module-level patch above alone would not
    # redirect it (default args bind once, at def time). Rebind directly.
    monkeypatch.setattr(repo_mod.Repository.__init__, "__defaults__", (db_path,))
    return repo_mod.Repository(db_path)


def test_not_found_is_explicit_not_an_error(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    result = compliance_sources(revision_id="does-not-exist")
    assert result["found"] is False


def test_missing_both_args_is_a_clear_error(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    assert "error" in compliance_sources()


def test_finds_exact_revision_and_verifies_integrity(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    corpus_file = tmp_path / "policy.pdf"
    corpus_file.write_bytes(b"the real policy text")
    repo.upsert_source_document(SourceDocument("policy.pdf", "Policy", "op", "policy", "US"))
    rev = repo.add_document_revision("policy.pdf", str(corpus_file), corpus_file.read_bytes())

    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    result = compliance_sources(revision_id=rev.revision_id)
    assert result["found"] is True
    assert result["revisions"][0]["integrity"] == "verified"
    assert result["n_historical_revisions"] == 0


def test_detects_drift_when_source_file_changed_without_new_revision(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    corpus_file = tmp_path / "policy.pdf"
    corpus_file.write_bytes(b"original text")
    repo.upsert_source_document(SourceDocument("policy.pdf", "Policy", "op", "policy", "US"))
    rev = repo.add_document_revision("policy.pdf", str(corpus_file), corpus_file.read_bytes())
    # the file changed on disk WITHOUT a new revision being ingested — this
    # is exactly the silent-drift case a stored hash alone cannot catch.
    corpus_file.write_bytes(b"tampered text")

    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    result = compliance_sources(revision_id=rev.revision_id)
    assert result["revisions"][0]["integrity"] == "DRIFTED"
    assert "drift_detail" in result["revisions"][0]


def test_alias_path_lookup_returns_every_historical_revision(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    corpus_file = tmp_path / "policy.pdf"
    corpus_file.write_bytes(b"version one")
    repo.upsert_source_document(SourceDocument("policy.pdf", "Policy", "op", "policy", "US"))
    repo.add_document_revision("policy.pdf", "policy.pdf", b"version one")
    repo.add_document_revision("policy.pdf", "policy.pdf", b"version two")

    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    result = compliance_sources(alias_path="policy.pdf")
    assert result["found"] is True
    assert len(result["revisions"]) == 2
    assert result["n_historical_revisions"] == 1


def test_logical_id_lookup_finds_a_revision_stored_under_a_different_alias_path(
    tmp_path, monkeypatch
):
    """The exact live gap found during P8-L verification: import_document_directory
    stores a source-dir-relative logical_id alongside a real resolvable
    absolute alias_path — a caller who naturally knows the relative name
    (what an operator or another tool would call it) must still be able to
    look it up, not just the raw filesystem path."""
    repo = _repo(tmp_path, monkeypatch)
    corpus_file = tmp_path / "policy.pdf"
    corpus_file.write_bytes(b"text")
    repo.upsert_source_document(
        SourceDocument("CIP-007/policy.pdf", "Policy", "op", "policy", "US")
    )
    repo.add_document_revision("CIP-007/policy.pdf", str(corpus_file), b"text")

    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    result = compliance_sources(logical_id="CIP-007/policy.pdf")
    assert result["found"] is True
    assert result["revisions"][0]["integrity"] == "verified"


def test_missing_source_file_is_unverifiable_not_a_false_pass(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    repo.upsert_source_document(SourceDocument("gone.pdf", "T", "op", "policy", "US"))
    rev = repo.add_document_revision("gone.pdf", "gone.pdf", b"bytes never on disk at this alias")

    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    result = compliance_sources(revision_id=rev.revision_id)
    assert "unverifiable" in result["revisions"][0]["integrity"]


# ── compliance_trace ─────────────────────────────────────────────────────
def test_trace_finds_approved_edges_forward(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    from portal.modules.compliance.core.models import RelationshipAssertion

    proposed = repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="CIP-007-6 R2",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=None,
            scope="",
        )
    )
    repo.decide_relationship(proposed.assertion_id, "CONFIRMED", "sme", expected_version=1)

    from portal.modules.compliance.tools.compliance_mcp import compliance_trace

    result = compliance_trace("CIP-007-6 R2", direction="forward")
    assert result["n_edges"] == 1
    assert result["edges"][0]["to"] == "POL §1"


def test_trace_invalid_direction_is_a_clear_error(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    from portal.modules.compliance.tools.compliance_mcp import compliance_trace

    result = compliance_trace("REQ-1", direction="sideways")
    assert "error" in result


def test_trace_excludes_proposed_edges_unless_widened(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    from portal.modules.compliance.core.models import RelationshipAssertion

    repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref="REQ-1",
            src_revision_id=None,
            dst_ref="POL §1",
            dst_revision_id=None,
            scope="",
        )
    )
    from portal.modules.compliance.tools.compliance_mcp import compliance_trace

    assert compliance_trace("REQ-1")["n_edges"] == 0
    assert compliance_trace("REQ-1", include_proposed=True)["n_edges"] == 1
