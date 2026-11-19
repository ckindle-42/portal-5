from __future__ import annotations

from pathlib import Path

from portal.platform.wiki.archive import archive_unit
from portal.platform.wiki.claims import evaluate_claims
from portal.platform.wiki.drift import claim_coverage_gaps
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import (
    load_archived_unit,
    load_unit,
    reset_archive_dir,
    reset_canonical_dir,
    set_archive_dir,
    set_canonical_dir,
)
from portal_wiki.mcp import wiki_get_unit, wiki_search


def test_schema_drops_stored_time_stamps_and_keeps_historical_mark() -> None:
    unit = KnowledgeUnit.from_markdown(
        """---
id: unit-old
kind: what
title: Old
sources:
  - type: code
    path: portal/example.py
claims: []
created_at: 12
updated_at: 34
last_generated_commit: deadbeef
historical: true
---

Body.
"""
    )

    frontmatter = unit.to_frontmatter()
    assert "created_at" not in frontmatter
    assert "updated_at" not in frontmatter
    assert "last_generated_commit" not in frontmatter
    assert frontmatter["historical"] is True
    assert "updated_at" not in unit.to_markdown()


def test_claim_coverage_guard_allows_only_claimed_historical_or_pending_units(
    tmp_path: Path,
) -> None:
    current = KnowledgeUnit(
        id="current",
        kind="what",
        title="Current",
        sources=[SourceRef(type="code", path="portal/current.py")],
    )
    historical = KnowledgeUnit(
        id="historical",
        kind="why",
        title="Historical",
        sources=[SourceRef(type="doc", path="docs/old.md")],
        historical=True,
    )
    pending = KnowledgeUnit(
        id="pending",
        kind="what",
        title="Pending",
        sources=[SourceRef(type="code", path="portal/pending.py")],
    )
    triage = tmp_path / "docs" / "wiki" / "CLAIMS_TRIAGE.md"
    triage.parent.mkdir(parents=True)
    triage.write_text("- `pending` | pending | awaiting content review\n")

    assert claim_coverage_gaps([current, historical, pending], tmp_path) == ["current"]


def test_real_canonical_claim_is_evaluated() -> None:
    unit = load_unit("unit-capability-compliance")
    assert unit is not None
    assert unit.claims
    assert evaluate_claims([unit]) == []


def test_repo_path_claim_checks_the_named_source() -> None:
    present = KnowledgeUnit(
        id="path-present",
        kind="what",
        title="Present source",
        sources=[SourceRef(type="code", path="portal/platform/wiki/schema.py")],
        claims=[
            {
                "probe": "repo.path.exists",
                "path": "portal/platform/wiki/schema.py",
                "equals": True,
            }
        ],
    )
    missing = KnowledgeUnit(
        id="path-missing",
        kind="what",
        title="Missing source",
        sources=[SourceRef(type="code", path="missing/source.py")],
        claims=[{"probe": "repo.path.exists", "path": "missing/source.py", "equals": True}],
    )

    assert evaluate_claims([present]) == []
    assert len(evaluate_claims([missing])) == 1


def test_repo_symbol_claim_checks_the_named_code_symbol() -> None:
    unit = KnowledgeUnit(
        id="symbol-present",
        kind="what",
        title="Schema class",
        sources=[SourceRef(type="code", path="portal/platform/wiki/schema.py")],
        claims=[
            {
                "probe": "repo.symbol.exists",
                "path": "portal/platform/wiki/schema.py",
                "symbol": "KnowledgeUnit",
                "equals": True,
            }
        ],
    )

    assert evaluate_claims([unit]) == []


def test_model_claim_probe_reads_current_configuration() -> None:
    configured = "qwen3-coder:30b-a3b-q4_K_M"
    catalog = KnowledgeUnit(
        id="model-catalog-entry",
        kind="what",
        title="Model catalog entry",
        sources=[SourceRef(type="code", path="config/backends.yaml")],
        claims=[{"probe": "models.configured", "contains": configured}],
    )

    assert evaluate_claims([catalog]) == []


def test_wiki_search_and_get_include_archived_units(tmp_path: Path) -> None:
    unit = KnowledgeUnit(
        id="unit-historical-test",
        kind="what",
        title="Archived routing history",
        sources=[SourceRef(type="doc", path="docs/old-routing.md")],
        body="An archived phrase for quartzarchiveprobe retrieval checks.",
        historical=True,
    )
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / f"{unit.id}.md").write_text(unit.to_markdown(), encoding="utf-8")
    set_archive_dir(archive_dir)
    try:
        results = wiki_search("quartzarchiveprobe", top_k=10)["results"]
        assert any(row["unit_id"] == unit.id and row["historical"] for row in results)
        fetched = wiki_get_unit(unit.id)
        assert fetched["unit_id"] == unit.id
        assert fetched["historical"] is True
    finally:
        reset_archive_dir()


def test_explicit_historical_archive_keeps_live_source_and_marks_unit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "portal_wiki" / "canonical"
    archive = repo / "portal_wiki" / "archive"
    source = repo / "portal" / "current.py"
    canonical.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    source.write_text("class CurrentSource: pass\n", encoding="utf-8")
    unit = KnowledgeUnit(
        id="unit-historical-live-source",
        kind="what",
        title="Closed run result",
        sources=[SourceRef(type="code", path="portal/current.py")],
        body="A dated run result retained as history.",
    )
    (canonical / f"{unit.id}.md").write_text(unit.to_markdown(), encoding="utf-8")
    set_canonical_dir(canonical)
    set_archive_dir(archive)
    try:
        ok, message = archive_unit(
            unit.id,
            "closed run result retained for audit",
            repo,
            historical=True,
        )
        assert ok, message
        assert load_unit(unit.id) is None
        archived = load_archived_unit(unit.id)
        assert archived is not None
        assert archived.historical is True
    finally:
        reset_canonical_dir()
        reset_archive_dir()
