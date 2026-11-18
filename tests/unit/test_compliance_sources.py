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
