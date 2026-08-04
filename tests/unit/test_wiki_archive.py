"""Tests for the wiki archive mechanism — retained on disk, out of the working set.

The preconditions for archiving are enforced in `archive.py`, not by the
operator's discipline. These tests pin each refusal: a missing reason, a doc
block reference, an inbound live-unit link, and a live code source. The last is
overridable only via `--superseded-by` with a verified survivor.
"""

from __future__ import annotations

import pytest

from portal.platform.wiki.archive import (
    archive_reachability,
    archive_unit,
    check_archivable,
)
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import (
    load_all,
    load_archived,
    reset_archive_dir,
    reset_canonical_dir,
    save_unit,
    set_archive_dir,
    set_canonical_dir,
)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Every test runs against an isolated canonical + archive pair."""
    set_canonical_dir(tmp_path / "canonical")
    set_archive_dir(tmp_path / "archive")
    (tmp_path / "canonical").mkdir(parents=True, exist_ok=True)
    yield
    reset_canonical_dir()
    reset_archive_dir()


def _unit(uid: str, body: str = "factual body", sources=None) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uid,
        kind="what",
        title=uid,
        sources=sources or [SourceRef(type="doc", path="docs/STALE.md")],
        body=body,
    )


# ── store: archived units are out of the live set ────────────────────────────


def test_load_archived_separate_from_live(tmp_path):
    save_unit(_unit("unit-live"))
    save_unit(_unit("unit-arch"))
    assert {u.id for u in load_all()} == {"unit-live", "unit-arch"}
    # Nothing has been archived yet.
    assert load_archived() == []


# ── preconditions ────────────────────────────────────────────────────────────


def test_check_archivable_ok_for_doc_only_orphan(tmp_path):
    save_unit(_unit("unit-doc-only", sources=[SourceRef(type="doc", path="docs/STALE.md")]))
    unit = load_all()[0]
    assert check_archivable(unit, tmp_path) == []


def test_refuses_missing_reason(tmp_path):
    save_unit(_unit("unit-doc-only", sources=[SourceRef(type="doc", path="docs/STALE.md")]))
    ok, msg = archive_unit("unit-doc-only", "", tmp_path)
    assert ok is False
    assert "reason" in msg
    assert load_archived() == []


def test_refuses_live_code_source(tmp_path):
    code = tmp_path / "config"
    code.mkdir()
    (code / "portal.yaml").write_text("x: 1")
    save_unit(_unit("unit-coded", sources=[SourceRef(type="code", path="config/portal.yaml")]))
    ok, msg = archive_unit("unit-coded", "no reason", tmp_path)
    assert ok is False
    assert "cites live source" in msg
    assert load_archived() == []


def test_superseded_by_requires_survivor_covering_all_code_paths(tmp_path):
    code = tmp_path / "config"
    code.mkdir()
    (code / "portal.yaml").write_text("x: 1")
    (code / "backends.yaml").write_text("x: 1")
    save_unit(
        _unit(
            "unit-coded",
            sources=[
                SourceRef(type="code", path="config/portal.yaml"),
                SourceRef(type="code", path="config/backends.yaml"),
            ],
        )
    )
    # Survivor cites only one of the two paths — must refuse.
    save_unit(
        _unit(
            "unit-survivor",
            sources=[SourceRef(type="code", path="config/portal.yaml")],
        )
    )
    ok, msg = archive_unit("unit-coded", "reason", tmp_path, superseded_by="unit-survivor")
    assert ok is False
    assert "does not cite" in msg
    assert load_archived() == []


def test_superseded_by_ok_when_survivor_covers_all(tmp_path):
    code = tmp_path / "config"
    code.mkdir()
    (code / "portal.yaml").write_text("x: 1")
    save_unit(_unit("unit-coded", sources=[SourceRef(type="code", path="config/portal.yaml")]))
    save_unit(_unit("unit-survivor", sources=[SourceRef(type="code", path="config/portal.yaml")]))
    ok, msg = archive_unit("unit-coded", "reason", tmp_path, superseded_by="unit-survivor")
    assert ok is True
    assert load_archived()[0].id == "unit-coded"


def test_refuses_when_survivor_does_not_exist(tmp_path):
    save_unit(_unit("unit-coded", sources=[SourceRef(type="code", path="config/portal.yaml")]))
    ok, msg = archive_unit("unit-coded", "reason", tmp_path, superseded_by="unit-nope")
    assert ok is False
    assert "survivor unit does not exist" in msg


def test_archive_moves_file_and_writes_index(tmp_path):
    save_unit(_unit("unit-arch", body="leaving"))
    ok, msg = archive_unit("unit-arch", "cites only a generated doc", tmp_path)
    assert ok is True
    assert {u.id for u in load_archived()} == {"unit-arch"}
    assert load_all() == []
    index = tmp_path / "archive" / "INDEX.md"
    assert index.exists()
    line = index.read_text()
    assert "unit-arch" in line
    assert "cites only a generated doc" in line


# ── reachability ─────────────────────────────────────────────────────────────


def test_reachability_clean_when_nothing_archived(tmp_path):
    save_unit(_unit("unit-live"))
    assert archive_reachability(tmp_path) == []


def test_reachability_flags_inbound_link(tmp_path):
    save_unit(_unit("unit-arch", body="leaving"))
    save_unit(_unit("unit-live", body="see unit-arch for details"))
    assert archive_unit("unit-arch", "reason", tmp_path)[0] is False  # linked → refused
    # Force the archive anyway to test the reachability check.
    (tmp_path / "archive").mkdir(parents=True, exist_ok=True)
    (tmp_path / "canonical" / "unit-arch.md").rename(tmp_path / "archive" / "unit-arch.md")
    problems = archive_reachability(tmp_path)
    assert any("unit-live links archived unit-arch" in p for p in problems)
