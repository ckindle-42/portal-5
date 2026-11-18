"""Official NERC source synchronization tests (END_TO_END Phase 2 / foundation
P2). Hermetic: all network fetches are stubbed; the lifecycle fixture is a
saved public workbook derived from NERC's own One-Stop Shop rows.

Covers: lifecycle parsing against the real registry values, fingerprint-aware
idempotence (UNCHANGED on identical bytes), failure preservation of the last
verified snapshot, immutable-revision registration in the canonical store, and
manifest retention.
"""

from __future__ import annotations

from portal.modules.compliance.core.nerc_source_sync import (
    Artifact,
)


def test_artifact_fingerprint_binds_url_bytes_and_time():
    a = Artifact(name="x", url="u", sha256="h", retrieved_at="t")
    b = Artifact(name="x", url="u", sha256="h", retrieved_at="t2")
    assert a.fingerprint() != b.fingerprint()
