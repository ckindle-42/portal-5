"""Regression tests for TASK_DETECTOR_PRECISION_V1.

Two detectors reported debt that did not exist:

  1. `drift._NUMERIC_CLAIM_RE` flagged any number next to a noun, so Windows
     Event IDs, model versions, version numbers split across a noun, singular
     generic uses, and fenced terminal excerpts all read as counts.
  2. `archive._CODE_EXTENSIONS` decided liveness by extension, missing real
     files live units cite (`opencode.jsonc`, `.env.example`, ...) and
     misreading a glob (`portal/modules/*/tools/*_mcp.py`) as nothing at all.

The two guards that matter most: a real present-tense figure must still be
caught (the narrowing must not disable the detector), and hand-authored
`CLAUDE.md` must still count as a source (the marker test is line-anchored,
not a substring test).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.wiki import drift as drift_mod
from portal.platform.wiki.archive import is_live_source
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import load_all, reset_canonical_dir, set_canonical_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unit(uid: str, body: str, unit_claims: list[dict] | None = None) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uid,
        kind="what",
        title=uid,
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        body=body,
        claims=unit_claims or [],
    )


# ── numeric detector: false-positive classes are not counts ─────────────────


def test_event_id_is_not_a_count():
    body = "the destination-side 5140 variant and the Windows 4688 variant"
    assert drift_mod.undeclared_numeric_claims([_unit("u1", body)]) == {}


def test_model_version_is_not_a_count():
    body = "when a 2509 model card appears, prefer the Q4_K_M quant"
    assert drift_mod.undeclared_numeric_claims([_unit("u2", body)]) == {}


def test_version_number_split_across_noun_is_not_a_count():
    body = "requests must follow per the Qwen3.6 tool-call format"
    assert drift_mod.undeclared_numeric_claims([_unit("u3", body)]) == {}


def test_singular_generic_noun_is_not_a_count():
    body = "Gates: 2658 unit ✅"
    assert drift_mod.undeclared_numeric_claims([_unit("u4", body)]) == {}


def test_fenced_transcript_is_not_a_count():
    body = "start\n```\n0 backends\n```\nend"
    assert drift_mod.undeclared_numeric_claims([_unit("u5", body)]) == {}


# ── numeric detector: the narrowing must not disable the detector ────────────


def test_a_real_present_tense_platform_figure_is_still_caught():
    body = "Portal ships 12 workspaces across 14 backends today."
    found = drift_mod.undeclared_numeric_claims([_unit("u6", body)])
    assert "u6" in found
    assert "12 workspaces" in found["u6"]
    assert "14 backends" in found["u6"]


# ── numeric detector: derived families are already gated by AW ───────────────


def test_derived_families_skip_the_numeric_detector():
    fact = _unit("unit-fact-mcp-fleet", "The fleet exposes 14 servers today.")
    sig = _unit("unit-T1558.003-signature", "Telemetry 14 techniques require EDR.")
    bare = _unit("unit-T1003-signature", "Also 14 techniques.")
    plain = _unit("unit-manual-notes", "The fleet exposes 14 servers today.")
    found = drift_mod.undeclared_numeric_claims([fact, sig, bare, plain])
    assert "unit-fact-mcp-fleet" not in found
    assert "unit-T1558.003-signature" not in found
    assert "unit-T1003-signature" not in found
    assert "unit-manual-notes" in found


def test_live_store_reports_zero_undeclared_numeric():
    set_canonical_dir(REPO_ROOT / "portal_wiki" / "canonical")
    try:
        found = drift_mod.undeclared_numeric_claims(load_all())
    finally:
        reset_canonical_dir()
    assert found == {}


# ── source detection: ask the filesystem, not the extension ─────────────────


@pytest.mark.parametrize(
    "rel",
    [
        "opencode.jsonc",
        ".env.example",
        "config/cloudflared/config.yml.example",
        "Dockerfile.mcp",
        "Dockerfile.attack",
        ".gitignore",
    ],
)
def test_missed_config_files_are_live_sources(rel):
    """Six real files the old extension allowlist never saw."""
    assert (REPO_ROOT / rel).exists()
    assert is_live_source(rel, REPO_ROOT)


def test_glob_source_resolves_to_live_files():
    assert is_live_source("portal/modules/*/tools/*_mcp.py", REPO_ROOT)
    assert not is_live_source("portal/modules/*/nope/*.py", REPO_ROOT)


def test_generated_markdown_is_rejected_as_a_source(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "generated.md").write_text(
        "<!-- WIKI:GENERATED unit=unit-fact-mcp-fleet -->\n\nrendered body\n"
    )
    assert not is_live_source("docs/generated.md", tmp_path)


def test_hand_authored_markdown_is_a_source():
    """CLAUDE.md describes the marker in prose but carries none at line start."""
    assert (REPO_ROOT / "CLAUDE.md").exists()
    assert is_live_source("CLAUDE.md", REPO_ROOT)


@pytest.mark.parametrize(
    "ident",
    [
        "ATT&CK:T1003.001",
        "bench-run:agentic-blue-sweep:2026-07-07",
    ],
)
def test_path_shaped_identifiers_are_rejected(ident):
    assert not is_live_source(ident, REPO_ROOT)


@pytest.mark.parametrize(
    "src",
    [
        "https://example.invalid/spec",
        "http://example.invalid/spec",
        "/etc/passwd",
        "/abs/path/foo.py",
    ],
)
def test_urls_and_absolute_paths_are_rejected(src):
    assert not is_live_source(src, REPO_ROOT)


def test_every_live_unit_has_at_least_one_live_source():
    set_canonical_dir(REPO_ROOT / "portal_wiki" / "canonical")
    try:
        units = load_all()
    finally:
        reset_canonical_dir()
    assert units
    bad = [
        u.id
        for u in units
        if not any(
            is_live_source((s.path or "").split("#", 1)[0].strip(), REPO_ROOT) for s in u.sources
        )
    ]
    assert not bad, f"units with no live source: {bad}"
