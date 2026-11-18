"""T3 Phase 8 — the currency probe. Currency is never inferred; honest-BLOCKED
when nerc.com is unreachable.
"""

from __future__ import annotations

from portal.modules.compliance.core.currency import (
    _next_versions,
)


def test_next_versions_enumerates_candidate_stems_including_decimal_errata():
    """F02: the prior version of this function checked only the next two
    INTEGER versions and could never discover a decimal/errata revision of
    the SAME major version (the design doc's real example: CIP-006-7.1)."""
    assert _next_versions("CIP-007-6") == ["cip-007-6.1", "cip-007-7", "cip-007-7.1", "cip-007-8"]
    assert _next_versions("CIP-002-5.1a") == [
        "cip-002-5.1",
        "cip-002-6",
        "cip-002-6.1",
        "cip-002-7",
    ]
    assert _next_versions("not-a-standard") == []
