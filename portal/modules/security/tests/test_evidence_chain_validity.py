"""Validity invariants for the red→evidence→blue chain."""

from __future__ import annotations


def test_hec_indexes_origin_and_episode_fields() -> None:
    from portal.modules.security.core.siem.hec_ship import ship

    result = ship(
        "GET / HTTP/1.1",
        sourcetype="web:access",
        host="10.0.0.10",
        dry_run=True,
        evidence_origin="observed_target_log",
        episode_id="ep-hec-test",
    )
    assert result["envelope"]["fields"] == {
        "evidence_origin": "observed_target_log",
        "episode_id": "ep-hec-test",
    }
