from __future__ import annotations

from pathlib import Path

from portal.platform.wiki.claims import evaluate_claims
from portal.platform.wiki.drift import claim_coverage_gaps
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import load_unit


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
