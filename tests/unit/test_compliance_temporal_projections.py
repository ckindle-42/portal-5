"""END_TO_END Phase 5 — both clocks operational + projection fingerprints.

Under test: two-clock selection of governing revisions (late-recorded facts,
corrected effectivity, future revisions, replay before/after a correction),
the valid_at/known_at predicates on relationship traversal (trace/impact),
and canonical-fingerprint projection manifests that detect staleness (L14).
"""

from __future__ import annotations

from portal.modules.compliance.core.temporal_selection import (
    withhold_unknown_knowledge,
)


class TestWithholdAndStoreNodes:
    def test_withhold_unknown_knowledge_splits_parts(self):
        selection = {
            "unknown_knowledge": [
                {"version": "6", "detail": "recorded later"},
            ]
        }
        parts = [
            {"id": "CIP-007-6 R1", "standard": "CIP-007-6"},
            {"id": "CIP-007-7.1 R1", "standard": "CIP-007-7.1"},
        ]
        kept, withheld = withhold_unknown_knowledge(parts, selection)
        assert [p["id"] for p in kept] == ["CIP-007-7.1 R1"]
        assert withheld == [
            {
                "id": "CIP-007-6 R1",
                "version": "6",
                "as_known": "UNKNOWN_KNOWLEDGE",
                "detail": "recorded later",
            }
        ]
        # no selection (family unresolvable) withholds nothing
        kept2, withheld2 = withhold_unknown_knowledge(parts, None)
        assert kept2 == parts and withheld2 == []
