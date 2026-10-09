"""Proof windows resume only on the exact content hash and store aggregate receipts."""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.security.core.review_eval.proof import ProofRunStore, window_digest


def _digest(event_ids: list[str] | None = None) -> str:
    return window_digest(
        window_id="w1",
        environment="botsv2",
        sources=["botsv2:stream:dns"],
        start=1501784416.0,
        end=1501784577.0,
        event_ids=event_ids or ["event:1", "event:2"],
        corpus_stamp="real:botsv2:manifest",
        arm="review_d0",
    )


def test_window_hash_binds_exact_rows_and_arm() -> None:
    digest = _digest()
    assert digest == _digest(["event:2", "event:1"])
    assert digest != _digest(["event:1", "event:3"])
    assert (
        window_digest(
            window_id="w1",
            environment="botsv2",
            sources=["botsv2:stream:dns"],
            start=1501784416.0,
            end=1501784577.0,
            event_ids=["event:1", "event:2"],
            corpus_stamp="real:botsv2:manifest",
            arm="legacy_funnel",
        )
        != digest
    )


def test_window_hash_rejects_proxy_or_invalid_intervals() -> None:
    with pytest.raises(ValueError, match="real:"):
        window_digest(
            window_id="w1",
            environment="botsv2",
            sources=["botsv2:stream:dns"],
            start=1.0,
            end=2.0,
            event_ids=[],
            corpus_stamp="proxy:fixture",
            arm="review_d0",
        )
    with pytest.raises(ValueError, match="positive interval"):
        window_digest(
            window_id="w1",
            environment="botsv2",
            sources=["botsv2:stream:dns"],
            start=2.0,
            end=2.0,
            event_ids=[],
            corpus_stamp="real:botsv2:manifest",
            arm="review_d0",
        )


def test_store_skips_only_exact_completed_window_hash(tmp_path: Path) -> None:
    store = ProofRunStore(tmp_path / "proof.sqlite3")
    digest = _digest()
    assert store.completed("w1", digest, "review_d0") is None
    receipt = store.record_complete(
        window_id="w1",
        window_hash=digest,
        arm="review_d0",
        runtime_run_id="run-real-1",
        summary={"concern_count": 1, "expected_events": 2, "fetched_events": 2},
    )
    assert store.completed("w1", digest, "review_d0") == receipt
    assert store.completed("w1", digest, "legacy_funnel") is None
    assert store.completed("w1", _digest(["event:other"]), "review_d0") is None
    store.close()

    reopened = ProofRunStore(tmp_path / "proof.sqlite3")
    saved = reopened.completed("w1", digest, "review_d0")
    assert saved is not None
    assert saved.runtime_run_id == "run-real-1"
    assert saved.summary["fetched_events"] == 2
    reopened.close()


def test_store_refuses_raw_event_payloads(tmp_path: Path) -> None:
    store = ProofRunStore(tmp_path / "proof.sqlite3")
    with pytest.raises(ValueError, match="aggregates"):
        store.record_complete(
            window_id="w1",
            window_hash=_digest(),
            arm="review_d0",
            runtime_run_id="run-real-1",
            summary={"concern_count": 1, "raw_text": "do not persist"},
        )
    store.close()
