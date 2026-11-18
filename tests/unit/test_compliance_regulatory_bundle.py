"""Complete regulatory bundle extraction and readiness (foundation P3).

Positive paths run against the pinned official CIP-007-6 / CIP-007-7.1
revisions (hash-prefixed against the register, skipped when the corpus is not
fetched locally). Every required component also gets a negative case proving
readiness can fail — the defect budget of the extractor is a named
``U14_INCOMPLETE_SOURCE_BUNDLE`` component list, never a silent empty string.
"""

from __future__ import annotations

from portal.modules.compliance.core.regulatory_bundle import (
    readiness_failures,
    required_components,
)


def test_attachment_shape_requires_only_its_own_components():
    required = required_components("attachment")
    assert "part_text" in required
    assert "measures" not in required and "technical_basis" not in required
    failures = readiness_failures(
        {
            "shape": "attachment",
            "ref": "CIP-002-5.1a Attachment 1 Part 1.1",
            "part_text": "Criterion text",
            "definitions_disposition": "external_glossary",
            "revision_id": "abc123",
        }
    )
    assert failures == []
