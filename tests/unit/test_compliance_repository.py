"""TASK_COMPLIANCE_REASONING_V2 P2 — the canonical versioned compliance store.

Exit criteria under test: migration roundtrip, broken-reference rejection,
same-path new revision (with historical anchors still resolving), crash
recovery (idempotent re-migration), decision concurrency, and as-known
replay — without touching unrelated ``kb_*`` indexes (there are none here;
this store is entirely separate from the LanceDB retrieval tables).
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.models import (
    RelationshipAssertion,
)
from portal.modules.compliance.core.repository import (
    Repository,
)


@pytest.fixture
def repo(tmp_path):
    r = Repository(tmp_path / "store.db")
    yield r
    r.close()


def test_corrected_decision_writes_coverage_not_status(repo):
    """Regression: decide_relationship's CORRECTED branch used to write
    corrected_coverage into the STATUS column (which only accepts
    proposed/approved/rejected/revoked/stale) instead of the new coverage
    column — any real coverage string would violate the CHECK constraint."""
    rel = RelationshipAssertion(
        assertion_id="",
        relation_type="IMPLEMENTS",
        src_ref="CIP-007-6 R2 Part 2.2",
        src_revision_id=None,
        dst_ref="DOC::S1",
        dst_revision_id=None,
        scope="",
        coverage="FULL",
        proposed_coverage="FULL",
    )
    saved = repo.propose_relationship(rel)
    updated = repo.decide_relationship(
        saved.assertion_id,
        "CORRECTED",
        "sme",
        expected_version=saved.version,
        corrected_coverage="PARTIAL",
    )
    assert updated.status == "approved"
    assert updated.coverage == "PARTIAL"
    assert updated.review_state == "CORRECTED"
