"""Tests for wiki core backbone — Phase W1.

Validates:
- KnowledgeUnit schema with mandatory provenance
- SourceRef serialization
- Markdown round-trip (frontmatter ↔ KnowledgeUnit)
- Store operations (save/load/list/delete)
- Core import-clean (no Portal-specific imports)
- MCP tools (search, get_unit, explain)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from portal_wiki.core.schema import KnowledgeUnit, SourceRef
from portal_wiki.core.store import (
    delete_unit,
    list_ids,
    load_all,
    load_unit,
    reset_canonical_dir,
    save_unit,
    set_canonical_dir,
)

# ── Schema ───────────────────────────────────────────────────────────────────


class TestSourceRef:
    """SourceRef serialization."""

    def test_to_dict(self):
        s = SourceRef(type="code", path="portal_pipeline/sync_config.py", commit="abc123")
        d = s.to_dict()
        assert d["type"] == "code"
        assert d["path"] == "portal_pipeline/sync_config.py"
        assert d["commit"] == "abc123"

    def test_from_dict(self):
        d = {"type": "design", "path": "docs/ARCHITECTURE.md", "section": "sync"}
        s = SourceRef.from_dict(d)
        assert s.type == "design"
        assert s.section == "sync"

    def test_optional_fields(self):
        s = SourceRef(type="spl", path="T1190")
        d = s.to_dict()
        assert "commit" not in d  # empty = omitted


class TestKnowledgeUnit:
    """KnowledgeUnit schema — mandatory provenance enforcement."""

    def test_create_with_sources(self):
        unit = KnowledgeUnit(
            id="unit-test-001",
            kind="what",
            title="Test unit",
            sources=[SourceRef(type="code", path="test.py")],
            body="Test body",
        )
        assert unit.id == "unit-test-001"
        assert unit.kind == "what"
        assert len(unit.sources) == 1

    def test_reject_no_sources(self):
        """HEADLINE: a unit with empty sources is INVALID."""
        with pytest.raises(ValueError, match="no sources"):
            KnowledgeUnit(
                id="unit-invalid",
                kind="what",
                title="Invalid",
                sources=[],
            )

    def test_reject_invalid_kind(self):
        with pytest.raises(ValueError, match="Invalid kind"):
            KnowledgeUnit(
                id="unit-bad-kind",
                kind="invalid",
                title="Bad kind",
                sources=[SourceRef(type="code", path="test.py")],
            )

    def test_valid_kinds(self):
        for kind in ("what", "why", "mixed"):
            unit = KnowledgeUnit(
                id=f"unit-{kind}",
                kind=kind,
                title=f"{kind} unit",
                sources=[SourceRef(type="code", path="test.py")],
            )
            assert unit.kind == kind

    def test_to_frontmatter(self):
        unit = KnowledgeUnit(
            id="unit-fm-001",
            kind="mixed",
            title="Frontmatter test",
            sources=[SourceRef(type="spl", path="T1190")],
            body="Body content",
        )
        fm = unit.to_frontmatter()
        assert fm["id"] == "unit-fm-001"
        assert fm["kind"] == "mixed"
        assert len(fm["sources"]) == 1

    def test_to_markdown_roundtrip(self):
        unit = KnowledgeUnit(
            id="unit-rt-001",
            kind="why",
            title="Round-trip test",
            sources=[
                SourceRef(type="design", path="docs/ARCHITECTURE.md", section="sync"),
                SourceRef(type="code", path="portal_pipeline/sync_config.py", commit="abc123"),
            ],
            body="# Round-trip\n\nThis is the body content.\n",
            confidence="high",
            tags=["test", "roundtrip"],
        )
        md = unit.to_markdown()
        assert md.startswith("---\n")
        assert "unit-rt-001" in md
        assert "# Round-trip" in md

        # Parse back
        parsed = KnowledgeUnit.from_markdown(md)
        assert parsed.id == unit.id
        assert parsed.kind == unit.kind
        assert parsed.title == unit.title
        assert len(parsed.sources) == 2
        assert parsed.sources[0].section == "sync"
        assert parsed.sources[1].commit == "abc123"
        assert parsed.body.strip() == unit.body.strip()

    def test_content_hash_deterministic(self):
        unit = KnowledgeUnit(
            id="unit-hash-001",
            kind="what",
            title="Hash test",
            sources=[SourceRef(type="code", path="test.py")],
            body="Stable content",
        )
        h1 = unit.content_hash()
        h2 = unit.content_hash()
        assert h1 == h2
        assert len(h1) == 16


# ── Store ────────────────────────────────────────────────────────────────────


class TestStore:
    """Git-backed store operations."""

    def test_save_and_load(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            unit = KnowledgeUnit(
                id="unit-store-001",
                kind="what",
                title="Store test",
                sources=[SourceRef(type="code", path="test.py")],
                body="Body content",
            )
            save_unit(unit)
            loaded = load_unit("unit-store-001")
            assert loaded is not None
            assert loaded.id == "unit-store-001"
            assert loaded.body == "Body content"
        finally:
            reset_canonical_dir()

    def test_load_nonexistent(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            assert load_unit("nonexistent") is None
        finally:
            reset_canonical_dir()

    def test_load_all(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            for i in range(3):
                save_unit(
                    KnowledgeUnit(
                        id=f"unit-all-{i}",
                        kind="what",
                        title=f"Unit {i}",
                        sources=[SourceRef(type="code", path=f"test{i}.py")],
                        body=f"Body {i}",
                    )
                )
            units = load_all()
            assert len(units) == 3
        finally:
            reset_canonical_dir()

    def test_list_ids(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            save_unit(
                KnowledgeUnit(
                    id="unit-list-001",
                    kind="what",
                    title="List test",
                    sources=[SourceRef(type="code", path="test.py")],
                )
            )
            ids = list_ids()
            assert "unit-list-001" in ids
        finally:
            reset_canonical_dir()

    def test_delete_unit(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            save_unit(
                KnowledgeUnit(
                    id="unit-del-001",
                    kind="what",
                    title="Delete test",
                    sources=[SourceRef(type="code", path="test.py")],
                )
            )
            assert delete_unit("unit-del-001") is True
            assert load_unit("unit-del-001") is None
            assert delete_unit("unit-del-001") is False  # already deleted
        finally:
            reset_canonical_dir()


# ── Core import-clean ────────────────────────────────────────────────────────


class TestCoreImportClean:
    """The extraction guarantee: core/ has ZERO Portal-specific imports."""

    def test_core_no_portal_imports(self):
        """Verify portal_wiki/core/ imports nothing from portal_pipeline or bench_security."""
        import glob as glob_mod

        bad = []
        for f in glob_mod.glob("portal_wiki/core/**/*.py", recursive=True):
            content = Path(f).read_text(encoding="utf-8")
            for forbidden in ["portal_pipeline", "bench_security", "import portal."]:
                if forbidden in content:
                    bad.append(f"{f}: contains '{forbidden}'")
        assert bad == [], f"Core has Portal imports: {bad}"


# ── MCP tools ────────────────────────────────────────────────────────────────


class TestMCPTools:
    """Wiki MCP tools: search, get_unit, explain."""

    def test_wiki_search(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            save_unit(
                KnowledgeUnit(
                    id="unit-search-001",
                    kind="what",
                    title="T1190 — Web exploit signature",
                    sources=[SourceRef(type="spl", path="T1190")],
                    body="Web exploit detection via access-log signatures",
                    tags=["T1190", "web", "exploit"],
                )
            )
            from portal_wiki.mcp import wiki_search

            result = wiki_search("T1190")
            assert result["count"] > 0
            assert result["results"][0]["unit_id"] == "unit-search-001"
        finally:
            reset_canonical_dir()

    def test_wiki_get_unit(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            save_unit(
                KnowledgeUnit(
                    id="unit-get-001",
                    kind="mixed",
                    title="Test unit",
                    sources=[SourceRef(type="code", path="test.py")],
                    body="Test body content",
                )
            )
            from portal_wiki.mcp import wiki_get_unit

            result = wiki_get_unit("unit-get-001")
            assert result["unit_id"] == "unit-get-001"
            assert result["body"] == "Test body content"
            assert len(result["sources"]) == 1
        finally:
            reset_canonical_dir()

    def test_wiki_get_unit_not_found(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            from portal_wiki.mcp import wiki_get_unit

            result = wiki_get_unit("nonexistent")
            assert "error" in result
        finally:
            reset_canonical_dir()

    def test_wiki_explain(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            save_unit(
                KnowledgeUnit(
                    id="unit-explain-001",
                    kind="mixed",
                    title="T1003.006 — DCSync signature",
                    sources=[SourceRef(type="spl", path="T1003.006")],
                    body="DCSync detection via Windows Security Event 4662",
                    tags=["T1003.006", "DCSync"],
                )
            )
            from portal_wiki.mcp import wiki_explain

            result = wiki_explain("T1003.006")
            assert "answer" in result
            assert len(result["sources"]) > 0
            assert "unit-explain-001" in result["units_referenced"]
        finally:
            reset_canonical_dir()

    def test_wiki_explain_no_results(self, tmp_path):
        set_canonical_dir(tmp_path)
        try:
            from portal_wiki.mcp import wiki_explain

            result = wiki_explain("nonexistent topic xyz")
            assert "No knowledge found" in result["answer"]
            assert result["sources"] == []
        finally:
            reset_canonical_dir()
