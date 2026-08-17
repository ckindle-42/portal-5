"""SA5.2 -- CloudTrail + multi-source parsers into the eight-dimension contract.

Hermetic: a real CloudTrail record shape (as observed in flaws.cloud and
invictus-ir exports) produces a valid signature with honest completeness via
the CloudSourceAdapter; envelope expansion turns a `{"Records":[...]}` export
into individual records; absent dimensions stay absent, never padded (A3/A7).
"""

from __future__ import annotations

from portal.modules.security.core.bully import signatures
from portal.modules.security.core.bully.analyst_corpus import ingest_events
from portal.modules.security.core.bully.source_adapters import (
    adapt,
)
from scripts import corpus_ingest

# A real CloudTrail record, shaped like the flaws.cloud / invictus exports.
_CLOUDTRAIL_RECORD = {
    "eventVersion": "1.08",
    "userIdentity": {
        "type": "IAMUser",
        "principalId": "AIDA9BO36HFBHKGJAO9C1",
        "arn": "arn:aws:iam::811596193553:user/backup",
        "accountId": "811596193553",
        "accessKeyId": "ASIAGD2JRX0V6RJGWR59-FAKEFORCORPUS",
        "userName": "backup",
    },
    "eventTime": "2018-04-16T06:59:20Z",
    "eventSource": "ec2.amazonaws.com",
    "eventName": "RunInstances",
    "awsRegion": "us-east-1",
    "sourceIPAddress": "203.0.113.42",
    "userAgent": "aws-sdk-go/1.12.11",
    "requestParameters": {"instancesSet": {"items": [{"instanceType": "t2.micro"}]}},
    "responseElements": None,
    "requestID": "83A6C73FE87F51FF",
    "eventID": "3038ebd2-c98a-4c65-9b6e-e22506292313",
    "eventType": "AwsApiCall",
    "recipientAccountId": "811596193553",
    "resources": [
        {
            "ARN": "arn:aws:ec2:us-east-1:811596193553:instance/i-0abc123",
            "accountId": "811596193553",
            "type": "AWS::EC2::Instance",
        }
    ],
}


def test_real_cloudtrail_record_produces_cloud_shaped_signature():
    """A genuine CloudTrail record maps into the eight-dimension contract with
    cloud semantics: action_sequence from eventName, context_topology from
    account/region/principal, artifacts from resource ARNs (A3)."""
    specimen = ingest_events(
        [_CLOUDTRAIL_RECORD],
        specimen_id="cloudtrail-real",
        sourcetype="aws:cloudtrail",
        labeling="authoritative",
        provenance={"source_id": "flaws.cloud", "origin": "cloudtrail"},
    )
    view = specimen["engine_view"]["telemetry_view"]
    assert specimen["adapter_status"] == "mapped"
    actions = view["action_sequence"]
    assert any("RunInstances" in action for action in actions)
    assert "ec2.amazonaws.com" in " ".join(actions)
    topology = view["context_topology"]
    assert "811596193553" in topology["accounts"]
    assert topology["regions"] == ["us-east-1"]
    assert any("backup" in principal for principal in topology["principals"])
    assert (
        "arn:aws:ec2:us-east-1:811596193553:instance/i-0abc123"
        in view["artifacts"]["resource_arns"]
    )


def test_cloudtrail_record_signature_is_valid_with_honest_completeness():
    """The adapted view builds a valid signature; completeness reflects the
    dimensions actually present -- never padded by the adapter (A7)."""
    view = adapt(
        [_CLOUDTRAIL_RECORD],
        {
            "sourcetype": "aws:cloudtrail",
            "techniques": ("T1578.004",),
            "origin": "flaws.cloud",
            "trust_tier": "imported_observed",
        },
    )
    signature = signatures.build_signature({"episode_id": "x", "target_host": "h"}, view)
    assert signature.signature_id
    assert signature.completeness > 0.0
    assert signature.completeness < 1.0  # absent dims (event_graph context etc.) stay absent
    assert {m["technique_id"] for m in view["attack_mappings"]} == {"T1578.004"}


def test_cloudtrail_record_without_resource_arns_leaves_artifacts_absent():
    """A CloudTrail record without a `resources` list must not fabricate ARN
    artifacts -- the dimension stays absent (honest completeness, A7)."""
    sparse = {key: value for key, value in _CLOUDTRAIL_RECORD.items() if key != "resources"}
    view = adapt(
        [sparse],
        {"sourcetype": "aws:cloudtrail", "techniques": (), "origin": "x", "trust_tier": "t"},
    )
    assert "resource_arns" not in view["artifacts"]
    assert view["context_topology"]["accounts"] == ["811596193553"]


def test_cloudtrail_envelope_expansion_into_individual_records():
    """A CloudTrail `{"Records":[...]}` export expands into one event per
    record -- the SPL library can then match individual API calls."""
    envelope = '{"Records": [{"eventName": "ListBuckets"}, {"eventName": "PutObject"}]}'
    records = corpus_ingest.iter_cloudtrail_records(envelope)
    assert len(records) == 2
    assert [record["eventName"] for record in records] == ["ListBuckets", "PutObject"]


def test_non_envelope_json_is_unaffected_by_expansion():
    """Plain JSONL and raw text must round-trip unchanged -- expansion only
    triggers on a top-level `Records` array (Windows/auditd lanes are safe)."""
    assert corpus_ingest.iter_cloudtrail_records('{"EventCode": 4688, "Image": "cmd.exe"}') == [
        {"EventCode": 4688, "Image": "cmd.exe"}
    ]
    assert corpus_ingest.iter_cloudtrail_records("hello raw line") == ["hello raw line"]


def test_cloudtrail_timestamp_parsed_from_eventtime():
    """CloudTrail eventTime is ISO-8601 -- event_epoch recovers the original
    time so backdating is never needed for real records."""
    epoch = corpus_ingest.event_epoch(_CLOUDTRAIL_RECORD, fallback=0.0)
    assert epoch > 1_500_000_000
    assert epoch < 1_600_000_000  # 2018-04-16, not ship time


def test_sourcetype_resolution_for_cloudtrail_records():
    assert corpus_ingest.resolve_sourcetype(None, None, _CLOUDTRAIL_RECORD, "") == "aws:cloudtrail"
    assert corpus_ingest.resolve_source_class("aws:cloudtrail") == "cloud"
