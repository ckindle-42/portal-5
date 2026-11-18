"""The compliance evaluation instance (root-fix Part 2c-2): every path under its root, the
operator's private inputs unreachable, a store built from public material only, only verified
tools served, and scoped compliance calls routed to it or refused — never to the operator."""

from __future__ import annotations

from pathlib import Path


def test_a_tilde_root_stages_under_the_home_dir_not_a_literal_tilde_directory(
    tmp_path, monkeypatch
):
    """Live 2026-10-15: the default root '~/.portal-data/compliance-eval' was staged into a
    literal './~/...' directory, ingest_folder (which expands '~') found nothing, and the
    store was built with zero documents while the build printed success."""
    from portal.modules.compliance.core import eval_instance

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    out = eval_instance._stage_planted("~/.portal-data/compliance-eval")
    assert out == tmp_path / ".portal-data" / "compliance-eval" / "planted_staged"
    assert out.is_dir() and any(out.glob("*.md"))
    assert not (tmp_path / "~").exists()


def test_every_planted_document_is_registered_and_captured_without_its_answer_key(tmp_path):
    """Live 2026-10-15: embedding the corpus alone (ingest_folder) left source_sections empty,
    so compliance_read answered {"resolved": false} for every planted id and every hit was
    excluded. Each document must resolve under its own id, key-free."""
    from portal.modules.compliance.core import eval_instance
    from portal.modules.compliance.core.repository import Repository

    repo = Repository(tmp_path / "c.db")
    repo.migrate()
    ids = eval_instance._capture_planted(repo, tmp_path)
    assert len(ids) == len(list(eval_instance.PLANTED.glob("*.md"))) == 12
    for doc_id in ids:
        n = repo._conn.execute(
            "SELECT COUNT(*) FROM source_sections s JOIN document_revisions r "
            "ON r.revision_id = s.revision_id WHERE r.logical_id = ?",
            (doc_id,),
        ).fetchone()[0]
        assert n >= 1, doc_id
        rev = repo._conn.execute(
            "SELECT alias_path FROM document_revisions WHERE logical_id = ?", (doc_id,)
        ).fetchone()[0]
        assert "PLANT" not in Path(rev).read_text()


def test_the_register_is_captured_and_anchored_so_the_standard_side_of_a_payload_is_not_empty(
    tmp_path,
):
    """Live 2026-10-16: the store held the register tables but no captured standard, so
    compliance_coverage said sections_in_standard 0 and the dual-document payload carried only
    '== CIP-007-6 R2 ==' for every determination. Each standard is a text-only document whose
    units are the requirement nodes, anchored exactly."""
    from portal.modules.compliance.core import dual_document, eval_instance, section_index
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.migrate_legacy import import_register
    from portal.modules.compliance.core.repository import Repository

    repo = Repository(tmp_path / "c.db")
    repo.migrate()
    register = Register.load()
    import_register(repo, register)
    ids = eval_instance._capture_register(repo, register)
    assert "NERC/CIP-007-6" in ids and "NERC/CIP-003-8" in ids and "NERC/CIP-003-9" in ids
    assert section_index.sections_in_scope(repo, logical_id="NERC/CIP-007-6")
    payload = dual_document.build(repo, requirement_ref="CIP-007-6 R2 Part 2.2")
    assert "at least once every 35 calendar days" in payload["text"].lower()
    repo.close()
