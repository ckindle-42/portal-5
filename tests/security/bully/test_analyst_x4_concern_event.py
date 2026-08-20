"""X.4 -- a Splunk-notable-shaped payload, routable separately from
promotion-queue arrivals (TASK_BULLY_ANALYST_LOOP_V1)."""

from __future__ import annotations

from unittest.mock import patch

from portal.modules.security.core.bully import analyst_loop as al
from portal.platform.inference.notifications import EventType

_NOTABLE_FIELDS = {
    "concern_id",
    "concern_class",
    "relationship",
    "entity_id",
    "n_sources",
    "source_ids",
    "aligned_spine",
    "resembles",
    "match_level",
    "robustness",
    "span_seconds",
    "brief",
}


def test_default_notify_payload_carries_every_notable_field():
    notified = []
    al.raise_concern(
        assessment_id="as-1",
        entity_id="jsmith",
        relationship="SAME",
        n_sources=2,
        source_ids=("s1", "s2"),
        aligned_spine=("auth", "enumerate"),
        notify=notified.append,
    )
    assert notified[0].keys() >= _NOTABLE_FIELDS


def test_concern_raised_event_type_exists_and_is_distinct_from_promotion_queued():
    assert EventType.CONCERN_RAISED.value == "concern_raised"
    assert EventType.CONCERN_RAISED != EventType.PROMOTION_QUEUED


def test_default_dispatcher_path_fires_concern_raised_not_promotion_queued():
    dispatched = []

    class _FakeDispatcher:
        def add_channel(self, ch):
            pass

        def dispatch(self, event):
            dispatched.append(event)
            return None

        def _schedule(self, coro):
            pass

    with patch(
        "portal.platform.inference.notifications.NotificationDispatcher",
        return_value=_FakeDispatcher(),
    ):
        al.raise_concern(
            assessment_id="as-1",
            entity_id="jsmith",
            relationship="SAME",
            n_sources=1,
            source_ids=("s1",),
        )

    assert len(dispatched) == 1
    assert dispatched[0].type == EventType.CONCERN_RAISED
