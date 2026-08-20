"""E.1 -- field-role inference resolves entities/timestamps/actions from
value behaviour, not field names, across schemas with zero field names in
common. TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1."""

from __future__ import annotations

from portal.modules.security.core.bully import field_roles as fr

_CT_VERBS = ["AssumeRole", "ListBuckets", "GetObject", "PutObject"]
CLOUDTRAIL_RECORDS = [
    {
        "eventTime": f"2024-01-01T00:{i // 60:02d}:{i % 60:02d}Z",
        "eventName": _CT_VERBS[i % len(_CT_VERBS)],
        "userIdentity": {"arn": f"arn:aws:iam::111122223333:user/alice{i % 3}"},
        "sourceIPAddress": f"10.0.0.{i % 5}",
        "awsRegion": "us-east-1",
    }
    for i in range(40)
]

_OSQ_ACTIONS = ["added", "removed"]
OSQUERY_RECORDS = [
    {
        "calendarTime": f"Mon Jan 01 00:{i // 60:02d}:{i % 60:02d} 2024 UTC",
        "hostIdentifier": f"host-{i % 3}",
        "columns": {"action": _OSQ_ACTIONS[i % len(_OSQ_ACTIONS)], "path": f"/etc/passwd{i}"},
        "name": "file_events",
    }
    for i in range(40)
]

_SYSMON_EVENT_IDS = [1, 3, 5]
SYSMON_RECORDS = [
    {
        "UtcTime": f"2024-01-01 00:{i // 60:02d}:{i % 60:02d}",
        "Computer": f"WS0{i % 3}.corp.local",
        "EventID": _SYSMON_EVENT_IDS[i % len(_SYSMON_EVENT_IDS)],
        "Image": f"C:\\Windows\\System32\\proc{i}.exe",
        "ParentImage": "C:\\Windows\\explorer.exe",
    }
    for i in range(40)
]


def test_cloudtrail_resolves_entity_timestamp_action() -> None:
    role_map = fr.infer_field_roles(CLOUDTRAIL_RECORDS, source_id="cloudtrail")
    assert role_map.extraction_valid, role_map.failure_reasons
    assert role_map.entity_fields
    assert role_map.timestamp_fields
    assert role_map.action_fields


def test_osquery_resolves_entity_timestamp_action() -> None:
    role_map = fr.infer_field_roles(OSQUERY_RECORDS, source_id="osquery")
    assert role_map.extraction_valid, role_map.failure_reasons
    assert role_map.entity_fields
    assert role_map.timestamp_fields
    assert role_map.action_fields


def test_sysmon_resolves_entity_timestamp_action() -> None:
    role_map = fr.infer_field_roles(SYSMON_RECORDS, source_id="sysmon")
    assert role_map.extraction_valid, role_map.failure_reasons
    assert role_map.entity_fields
    assert role_map.timestamp_fields
    assert role_map.action_fields


def test_schemas_share_zero_field_names() -> None:
    def flat_field_names(records: list[dict[str, object]]) -> set[str]:
        role_map = fr.infer_field_roles(records)
        return set(role_map.profiles)

    ct = flat_field_names(CLOUDTRAIL_RECORDS)
    osq = flat_field_names(OSQUERY_RECORDS)
    sys_ = flat_field_names(SYSMON_RECORDS)
    assert not (ct & osq)
    assert not (ct & sys_)
    assert not (osq & sys_)


def test_seeded_violation_hardcoded_lists_would_return_empty() -> None:
    """The regression this module exists to fix: a hardcoded CloudTrail
    field-name list returns nothing on osquery/Sysmon records."""
    old_entity_fields = ("userIdentity.arn", "user", "host", "sourceIPAddress")
    old_time_fields = ("eventTime", "_time", "timestamp")
    old_action_fields = ("eventName", "action")

    def _dig(record: dict, dotted: str):
        cursor = record
        for part in dotted.split("."):
            if not isinstance(cursor, dict):
                return None
            cursor = cursor.get(part)
        return cursor

    def old_entities(record: dict) -> list[str]:
        return [
            f
            for f in old_entity_fields
            if isinstance(_dig(record, f), (str, int, float)) and str(_dig(record, f)).strip()
        ]

    def old_time(record: dict) -> str | None:
        for f in old_time_fields:
            v = _dig(record, f)
            if isinstance(v, (str, int, float)) and str(v).strip():
                return f
        return None

    for record in OSQUERY_RECORDS + SYSMON_RECORDS:
        assert old_entities(record) == []
        assert old_time(record) is None
        assert not any(f in record for f in old_action_fields)


def test_unextractable_source_reports_itemised_failure() -> None:
    junk_records = [
        {"blob": "x" * 300, "note": f"free text {i} unrelated content"} for i in range(10)
    ]
    role_map = fr.infer_field_roles(junk_records, source_id="unextractable")
    assert role_map.extraction_valid is False
    assert role_map.failure_reasons
    assert any("entity_coverage" in r for r in role_map.failure_reasons)


def test_empty_sample_is_invalid() -> None:
    role_map = fr.infer_field_roles([], source_id="empty")
    assert role_map.extraction_valid is False
    assert role_map.failure_reasons == ("empty_sample",)


def test_high_cardinality_record_id_is_payload_not_entity() -> None:
    import uuid

    records = [
        {"requestID": str(uuid.uuid4()), "user": f"alice{i % 3}", "eventTime": float(i)}
        for i in range(50)
    ]
    role_map = fr.infer_field_roles(records, source_id="record-ids")
    assert role_map.profiles["requestID"].role == "PAYLOAD"
    assert role_map.profiles["user"].role == "ENTITY"


def test_diff_type_action_resolves_to_action_not_identifier() -> None:
    role_map = fr.infer_field_roles(OSQUERY_RECORDS, source_id="osquery")
    action_field = "columns.action"
    assert role_map.profiles[action_field].role == "ACTION"
    # closed vocabulary: only two values ever appear
    assert role_map.profiles[action_field].distinct_count == 2
