"""X.2 -- concerns table and open-queue enumeration: the store can now
persist a concern and enumerate the analyst's queue, which it never could
before (TASK_BULLY_ANALYST_LOOP_V1)."""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import analyst_loop as al
from portal.modules.security.core.bully.store import ConcernError, Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _concern(**overrides):
    kwargs = {
        "assessment_id": "as-1",
        "entity_id": "jsmith",
        "relationship": "SAME",
        "n_sources": 2,
        "source_ids": ("s1", "s2"),
        "aligned_spine": ("auth", "enumerate"),
    }
    kwargs.update(overrides)
    return al.raise_concern(notify=lambda _p: None, **kwargs)


def test_recorded_verdict_leaves_open_queue_and_is_retrievable_with_note_and_timestamp(store):
    concern = _concern()
    store.concern_put(concern.to_dict())

    assert [c["concern_id"] for c in store.concerns_open()] == [concern.concern_id]

    updated = store.concern_record_verdict(
        concern.concern_id, al.CONFIRMED, note="confirmed by analyst", expected_version=0
    )
    assert updated["verdict"] == al.CONFIRMED
    assert updated["verdict_note"] == "confirmed by analyst"
    assert updated["verdict_at"] is not None

    assert store.concerns_open() == []
    fetched = store.concern_get(concern.concern_id)
    assert fetched["verdict"] == al.CONFIRMED
    assert fetched["verdict_note"] == "confirmed by analyst"


def test_concern_put_is_idempotent_on_concern_id(store):
    concern = _concern()
    store.concern_put(concern.to_dict())
    store.concern_put(concern.to_dict())  # re-drive, same id
    assert len(store.concerns_open()) == 1


def test_concern_record_verdict_rejects_stale_version(store):
    concern = _concern()
    store.concern_put(concern.to_dict())
    store.concern_record_verdict(concern.concern_id, al.CONFIRMED, expected_version=0)
    with pytest.raises(ConcernError):
        store.concern_record_verdict(concern.concern_id, al.BENIGN, expected_version=0)


def test_concern_record_verdict_unknown_id_raises(store):
    with pytest.raises(ConcernError):
        store.concern_record_verdict("cn-does-not-exist", al.CONFIRMED, expected_version=0)


def test_concerns_open_orders_unknown_cousins_first(store):
    known = _concern(relationship="SAME", n_sources=10)
    unknown = _concern(relationship="SIMILAR", n_sources=1)
    store.concern_put(known.to_dict())
    store.concern_put(unknown.to_dict())
    queue = store.concerns_open()
    assert queue[0]["concern_id"] == unknown.concern_id
    assert queue[1]["concern_id"] == known.concern_id
