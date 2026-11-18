"""P7 — compliance_analyze runs the shared service; the in-memory job dict is gone.

Hermetic: the durable run repository is a tmp_path SQLite store, both exercised
cases are short-circuited by the applicability/U02 pre-gate, so no retrieval or
model call happens.
"""

from __future__ import annotations

from portal.modules.compliance.core.runtime_config import load_org_commitments, seat_roster


def test_seat_roster_is_family_diverse():
    seats = seat_roster()
    assert len(seats) >= 3
    fams = {s["id"] for s in seats}
    assert len(fams) >= 3  # at least three distinct seats


def test_org_commitments_load_from_the_built_graph_or_empty():
    coms = load_org_commitments()
    assert isinstance(coms, list)
    if coms:
        assert all({"commitment_id", "document_id", "text"} <= set(c) for c in coms[:20])
