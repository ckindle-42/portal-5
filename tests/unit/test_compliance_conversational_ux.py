"""Regression coverage for compliance inventory, conversation guidance and projection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml


def _repository(tmp_path, monkeypatch):
    from portal.modules.compliance.core import repository as repo_mod

    db_path = tmp_path / "store.db"
    monkeypatch.setattr(repo_mod, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(repo_mod.Repository.__init__, "__defaults__", (db_path,))
    return repo_mod.Repository(db_path)


def _add_section(repo, revision_id: str, section_id: str, text: str) -> None:
    from portal.modules.compliance.core.models import SourceSection

    repo.add_source_section(
        SourceSection(
            section_id=section_id,
            revision_id=revision_id,
            path=section_id,
            page_start=1,
            page_end=1,
            extractor="test",
            extractor_version="1",
            title=section_id,
            unit_kind="prose",
            ordinal=0,
            char_start=0,
            char_end=len(text),
        )
    )


def test_sources_inventory_is_current_structured_and_keeps_revision_lookup(
    tmp_path, monkeypatch
) -> None:
    from portal.modules.compliance.core.document_scope import store_scope
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.tools.compliance_mcp import compliance_sources

    repo = _repository(tmp_path, monkeypatch)
    operator_id = "CIP-007/access-policy.pdf"
    repo.upsert_source_document(
        SourceDocument(operator_id, "Access Control Policy", "Entity", "policy", "internal")
    )
    old = repo.add_document_revision(
        operator_id,
        str(tmp_path / "old.pdf"),
        b"old policy",
        effective_date="2024-01-01",
        document_number="POL-7",
        version="1",
    )
    active = repo.add_document_revision(
        operator_id,
        str(tmp_path / "current.pdf"),
        b"current policy",
        effective_date="2025-01-01",
        document_number="POL-7",
        version="2",
    )
    _add_section(repo, old.revision_id, "isection-old", "old")
    _add_section(repo, active.revision_id, "isection-current-a", "one")
    _add_section(repo, active.revision_id, "isection-current-b", "two")
    store_scope(
        repo,
        logical_id=operator_id,
        claims=[{"standard": "CIP-007", "quote": "scope text", "quote_valid": True}],
        about="Access control",
        states_scope=True,
        model="unit-test",
        read_chars=10,
        raw={},
    )
    regulatory_id = "NERC/CIP-007-6"
    repo.upsert_source_document(
        SourceDocument(regulatory_id, "CIP-007-6", "NERC", "regulatory_standard", "US")
    )
    regulatory = repo.add_document_revision(
        regulatory_id,
        str(tmp_path / "cip-007.pdf"),
        b"regulatory text",
        effective_date="2025-01-01",
        document_number="CIP-007-6",
        version="6",
    )
    _add_section(repo, regulatory.revision_id, "csection-standard", "rule")

    inventory = compliance_sources()

    assert inventory["mode"] == "inventory"
    assert inventory["count"] == 2
    operator = next(item for item in inventory["documents"] if item["logical_id"] == operator_id)
    assert operator["kind"] == "operator"
    assert operator["revision_id"] == active.revision_id
    assert operator["title"] == "Access Control Policy"
    assert operator["document_number"] == "POL-7"
    assert operator["version"] == "2"
    assert operator["effective_date"] == "2025-01-01"
    assert operator["section_count"] == 2
    assert operator["linked_standards"] == ["CIP-007"]
    regulatory_only = compliance_sources(kind="regulatory")
    assert [item["logical_id"] for item in regulatory_only["documents"]] == [regulatory_id]

    historical_lookup = compliance_sources(logical_id=operator_id)
    assert historical_lookup["found"] is True
    assert len(historical_lookup["revisions"]) == 2
    assert historical_lookup["current_revision_id"] == active.revision_id


def test_auto_compliance_prompts_route_conversations_to_direct_reading_tools() -> None:
    config = yaml.safe_load(Path("config/portal.yaml").read_text(encoding="utf-8"))
    workspace = config["workspaces"]["auto-compliance"]

    for prompt in (workspace["system_prompt_append"], workspace["owui_system_prompt"]):
        lowered = prompt.lower()
        assert "compliance_sources()" in prompt
        for tool in (
            "compliance_sources",
            "compliance_search",
            "compliance_read",
            "compliance_links",
            "compliance_coverage",
            "compliance_notes",
            "nerc_cip_requirement",
        ):
            assert tool in prompt
        assert "compliance_ask" in lowered and ("explicit" in lowered or "batch" in lowered)
        assert "verbatim" in lowered
        assert "approved" in lowered and "proposed" in lowered


def test_stored_conversation_is_projected_and_coverage_stays_clean(tmp_path, monkeypatch) -> None:
    from portal.modules.compliance.core import reader
    from portal.modules.compliance.tools import compliance_retrieval
    from scripts.compliance.truth import data_integrity

    repo = _repository(tmp_path, monkeypatch)
    projected = []
    project_calls = []

    async def project_sections(kb_id, units, *, rebuild):
        project_calls.append((kb_id, rebuild))
        projected.extend(units)
        return {"units_indexed": len(units)}

    monkeypatch.setattr(compliance_retrieval._store, "text_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(compliance_retrieval, "project_sections", project_sections)

    answer_id = reader.store_answer(
        repo,
        {
            "question": "What does our policy say?",
            "answer": "It requires approval.",
            "ref": "CIP-007-6 R2",
            "model": "test-seat",
            "verification": {"citations": []},
        },
        {"revision_id": "source-revision"},
    )

    assert answer_id.startswith("answer-")
    assert project_calls == [("conversation", True)]
    assert len(projected) == 1
    rows = {name: [] for name in data_integrity.TEXT_TABLES}
    rows["compliance_conversation"] = [{"chunk_id": unit.chunk_id} for unit in projected]
    conn = sqlite3.connect(repo.path)
    conn.row_factory = sqlite3.Row
    result = data_integrity.check_coverage(conn, rows)
    assert result.name == "store_index_coverage"
    assert result.status == "pass"
    conn.close()


def test_stored_conversation_survives_an_offline_embedder(tmp_path, monkeypatch) -> None:
    from portal.modules.compliance.core import reader
    from portal.modules.compliance.tools import compliance_retrieval

    repo = _repository(tmp_path, monkeypatch)

    async def offline_projection(*args, **kwargs):
        raise ConnectionError("embedder offline")

    monkeypatch.setattr(compliance_retrieval._store, "text_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(compliance_retrieval, "project_sections", offline_projection)

    answer_id = reader.store_answer(
        repo,
        {
            "question": "What does our policy say?",
            "answer": "It requires approval.",
            "verification": {"citations": []},
        },
        {},
    )

    assert answer_id.startswith("answer-")
    assert repo._conn.execute("SELECT COUNT(*) FROM source_sections").fetchone()[0] == 1
