"""Guard tests: the join must refuse ground-truth columns as features or records.

Written first (red), before the guard existed — the refusal is the reason the
test initially failed. See TASK_MAWA_STEP_MANIFESTATION_JOIN.md.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.mawa.events import ParsedEvent
from portal.modules.security.core.mawa.join import (
    GroundTruthFeatureError,
    build_groups,
    co_group_records,
    validate_feature_keys,
    validate_records,
)


def _event(event_id: int = 1, ts: float = 1_787_380_200.0) -> ParsedEvent:
    return ParsedEvent(
        event_id=event_id,
        ts=ts,
        source_file="log/apache2/access.log",
        kind="apache_access",
        tag="",
        pid="",
        message="GET /x HTTP/1.1",
        fields={"method": "GET", "url": "/x", "proto": "HTTP/1.1", "code": "200"},
        entities=frozenset({"path:/x"}),
        raw='1.2.3.4 - - [22/Aug/2026:13:30:00 +0700] "GET /x HTTP/1.1" 200 10 "-" "ua"',
    )


@pytest.mark.parametrize(
    "key", ["actor", "ground_truth_label", "low_level_ids", "tag", "decoded", "normalized"]
)
def test_feature_key_from_ground_truth_is_refused(key: str) -> None:
    with pytest.raises(GroundTruthFeatureError, match=key):
        validate_feature_keys([key])


def test_build_groups_refuses_ground_truth_feature_key() -> None:
    with pytest.raises(GroundTruthFeatureError):
        build_groups([_event()], feature_keys=("actor",))


def test_record_carrying_ground_truth_column_is_refused() -> None:
    record = {"ts": 1.0, "actor": "192.0.2.1"}
    with pytest.raises(GroundTruthFeatureError):
        co_group_records([record])


def test_records_validator_refuses_any_ground_truth_column() -> None:
    with pytest.raises(GroundTruthFeatureError):
        validate_records([{"ts": 1.0, "low_level_ids": "1|2"}])


def test_content_feature_keys_are_accepted() -> None:
    assert validate_feature_keys(["entities", "ts", "message"]) is None
    groups = build_groups([_event()], feature_keys=("entities",))
    assert len(groups) == 1
    assert groups[0].member_ids == (1,)


def test_clean_records_are_grouped() -> None:
    groups = co_group_records([{"ts": 1.0}, {"ts": 2.0}, {"ts": 300.0}])
    assert sorted(sorted(g) for g in groups) == [[0, 1], [2]]
