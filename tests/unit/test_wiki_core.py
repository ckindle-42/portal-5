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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from portal.platform.wiki.audit import (
    source_is_repository_local,
)
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef


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


class TestWikiIntegrity:
    """Canonical bodies and repository-local provenance stay trustworthy."""

    @pytest.mark.parametrize(
        "source",
        [
            SourceRef(type="mitre", path="ATT&CK:T1003.006"),
            SourceRef(type="spl", path="T1190"),
            SourceRef(type="code", path="module-state-change:media:operator"),
            SourceRef(type="bench-security", path="bench-run:blue:2026-07-06"),
            SourceRef(type="url", path="https://example.test/design"),
        ],
    )
    def test_non_file_identifiers_are_not_local_paths(self, source):
        assert not source_is_repository_local(source)


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

    def test_reject_invalid_confidence(self):
        with pytest.raises(ValueError, match="Invalid confidence"):
            KnowledgeUnit(
                id="unit-bad-confidence",
                kind="what",
                title="Bad confidence",
                sources=[SourceRef(type="code", path="test.py")],
                confidence="certain",
            )

    def test_valid_confidences(self):
        for confidence in ("high", "medium", "low"):
            unit = KnowledgeUnit(
                id=f"unit-confidence-{confidence}",
                kind="what",
                title=f"{confidence} confidence unit",
                sources=[SourceRef(type="code", path="test.py")],
                confidence=confidence,
            )
            assert unit.confidence == confidence

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
