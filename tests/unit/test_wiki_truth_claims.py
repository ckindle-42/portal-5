from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.platform.wiki.adapters import seed_facts
from portal.platform.wiki.archive import archive_unit
from portal.platform.wiki.claims import authored_claim_violations, evaluate_claims
from portal.platform.wiki.drift import claim_coverage_gaps, volatile_prose_violations
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import (
    load_archived_unit,
    load_unit,
    reset_archive_dir,
    reset_canonical_dir,
    save_unit,
    set_archive_dir,
    set_canonical_dir,
)
from portal_wiki.mcp import wiki_get_unit, wiki_search
from scripts.validation.wiki import check_spine_drift


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


def test_claims_optional_for_narrative_unless_pending_triage(
    tmp_path: Path,
) -> None:
    current = KnowledgeUnit(
        id="current",
        kind="what",
        title="Current narrative",
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

    assert claim_coverage_gaps([current, historical, pending], tmp_path) == ["pending"]


def test_real_canonical_claim_is_evaluated() -> None:
    unit = load_unit("unit-capability-rag")
    assert unit is not None
    assert unit.claims
    assert evaluate_claims([unit]) == []


def test_authored_units_reject_volatile_probes_and_name_alternative(tmp_path: Path) -> None:
    unit = KnowledgeUnit(
        id="unit-module-bad",
        kind="mixed",
        title="Bad module",
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        claims=[{"probe": "modules.enabled", "contains": "music"}],
    )
    violations = authored_claim_violations([unit])
    assert len(violations) == 1
    assert "unit-fact-module-states" in str(violations[0])

    set_canonical_dir(tmp_path)
    try:
        with pytest.raises(ValueError, match="unit-fact-module-states"):
            save_unit(unit)
    finally:
        reset_canonical_dir()


def test_volatile_prose_violations_catch_counts_and_module_state() -> None:
    bad = KnowledgeUnit(
        id="unit-authored-bad",
        kind="what",
        title="Music (off by default)",
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        claims=[{"probe": "repo.path.exists", "path": "config/portal.yaml", "equals": True}],
        body="Currently 22 workspaces; `modules.music.enabled: false`.",
    )
    conditional_ok = KnowledgeUnit(
        id="unit-authored-ok",
        kind="what",
        title="Workspaces",
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        body="Bench lanes are hidden when the `eval` module is disabled.",
    )
    found = volatile_prose_violations([bad, conditional_ok])
    assert "unit-authored-bad" in found
    assert len(found["unit-authored-bad"]) >= 3
    assert "unit-authored-ok" not in found


def test_module_toggle_and_mcp_addition_leave_bs_pass_with_no_doc_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import shutil
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    skip = {
        ".git",
        ".venv",
        ".ci-local-venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    for entry in repo_root.iterdir():
        if entry.name in skip:
            continue
        dst = tmp_path / entry.name
        if entry.name in {"config", ".mcp.json", ".gitignore"}:
            shutil.copytree(entry, dst) if entry.is_dir() else shutil.copy2(entry, dst)
        elif entry.is_dir():
            shutil.copytree(
                entry,
                dst,
                ignore=shutil.ignore_patterns(*skip),
                copy_function=os.symlink,
                symlinks=True,
            )
        else:
            dst.symlink_to(entry)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    # 1. Flip module states (disable music, enable eval) in config + generated manifest.
    portal_text = (tmp_path / "config" / "portal.yaml").read_text(encoding="utf-8")
    portal_text = portal_text.replace("  music:\n    enabled: true", "  music:\n    enabled: false")
    portal_text = portal_text.replace("  eval:\n    enabled: false", "  eval:\n    enabled: true")
    # 2. Add a new MCP server to mcp_fleet.
    portal_text = portal_text.replace(
        "mcp_fleet:\n",
        "mcp_fleet:\n  - id: extra_demo\n    name: portal-extra-demo\n    port: 8999\n    module: research\n",
        1,
    )
    (tmp_path / "config" / "portal.yaml").write_text(portal_text, encoding="utf-8")

    gen_text = (tmp_path / "config" / "modules.generated.yaml").read_text(encoding="utf-8")
    gen_text = gen_text.replace("  music:\n    enabled: true", "  music:\n    enabled: false")
    gen_text = gen_text.replace("  eval:\n    enabled: false", "  eval:\n    enabled: true")
    (tmp_path / "config" / "modules.generated.yaml").write_text(gen_text, encoding="utf-8")

    mcp_data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    mcp_data["mcpServers"].pop("portal-music", None)
    mcp_data["mcpServers"]["portal-extra-demo"] = {
        "type": "http",
        "url": "http://localhost:8999/mcp",
    }
    (tmp_path / ".mcp.json").write_text(json.dumps(mcp_data, indent=2), encoding="utf-8")

    monkeypatch.setattr(seed_facts, "_REPO_ROOT", tmp_path)
    status, detail, _ = check_spine_drift(tmp_path)
    assert status == "PASS", detail

    # BS must still fail on a broken stable path claim.
    broken = KnowledgeUnit(
        id="unit-broken-path",
        kind="what",
        title="Broken",
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        claims=[{"probe": "repo.path.exists", "path": "portal/does_not_exist.py", "equals": True}],
    )
    assert len(evaluate_claims([broken], tmp_path)) == 1


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
