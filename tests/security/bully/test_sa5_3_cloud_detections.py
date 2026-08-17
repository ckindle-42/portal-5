"""SA5.3 -- cloud/identity detections + discriminator tokens.

Hermetic: each new `aws:cloudtrail` detection fires on a known-positive
record shaped like the acquired datasets (invictus-ir / flaws.cloud exports)
and is quiet on the shared benign corpus. No network, no live Splunk.
"""

from __future__ import annotations

import json

from portal.modules.security.core.bully.handoff import (
    check_quiet_on_benign,
    gather_quiet_on_benign,
    validate_spl_syntax,
)
from portal.modules.security.core.recall_attribution import (
    evidence_presence,
    technique_discriminators,
)
from portal.modules.security.core.siem.spl_detections import (
    _invalidate_cache,
    spl_for_source,
    validated_detection_sourcetypes,
)
from scripts import corpus_ingest

# Real eventName values observed in the staged invictus-ir / flaws.cloud
# CloudTrail exports (verified against the acquisition, not invented).
_DETECTIONS = {
    "T1078.004": ["ConsoleLogin"],
    "T1098": ["CreateAccessKey", "CreateUser", "CreateRole", "AttachUserPolicy"],
    "T1530": ["GetSecretValue", "ListBuckets"],
    "T1526": ["DescribeInstances", "ListUsers", "GetCallerIdentity"],
}


def _invalidate():
    _invalidate_cache()


def _record(event_name: str) -> str:
    """A CloudTrail record with the given eventName, in the shape the export
    files carry (JSON body, `eventName` + `eventSource` + `userIdentity`)."""
    return json.dumps(
        {
            "eventVersion": "1.08",
            "userIdentity": {
                "type": "IAMUser",
                "arn": "arn:aws:iam::811596193553:user/backup",
                "accountId": "811596193553",
                "userName": "backup",
            },
            "eventTime": "2018-04-16T06:59:20Z",
            "eventSource": "signin.amazonaws.com",
            "eventName": event_name,
            "awsRegion": "us-east-1",
            "sourceIPAddress": "203.0.113.42",
            "requestID": "83A6C73FE87F51FF",
            "eventID": "3038ebd2-c98a-4c65-9b6e-e22506292313",
            "eventType": "AwsApiCall",
            "recipientAccountId": "811596193553",
        }
    )


def test_aws_cloudtrail_becomes_admitted_detection_sourcetype():
    """SA5.3 A4: with validated cloud/identity detections the cloud class is
    reachable -- `aws:cloudtrail` now appears in the derived admit set."""
    _invalidate()
    assert "aws:cloudtrail" in validated_detection_sourcetypes()
    assert "aws:cloudtrail" in corpus_ingest.INGESTED_SOURCETYPES


def test_each_cloud_detection_fires_on_known_positive_and_is_quiet_on_benign():
    """Every new detection has valid syntax, fires on a known-positive
    acquired record (evidence oracle sees its discriminator tokens), and is
    quiet on the shared benign corpus."""
    _invalidate()
    for technique_id, event_names in _DETECTIONS.items():
        spl = spl_for_source(technique_id, "aws:cloudtrail")
        assert spl, f"{technique_id}: no aws:cloudtrail SPL variant"
        ok, errors = validate_spl_syntax(spl)
        assert ok, f"{technique_id}: invalid SPL: {errors}"

        discriminators = technique_discriminators(technique_id)["tokens"]
        assert discriminators, f"{technique_id}: no discriminator tokens declared"

        # Fires on at least one known-positive acquired eventName.
        fired_any = False
        for event_name in event_names:
            result, matched = evidence_presence(_record(event_name), discriminators)
            if result == "PRESENT" and matched:
                fired_any = True
                break
        assert fired_any, f"{technique_id}: no known-positive record fired {discriminators}"

        # Quiet on the shared benign corpus.
        quiet = check_quiet_on_benign(gather_quiet_on_benign(spl))
        assert quiet["outcome"] == "pass", f"{technique_id}: {quiet}"


def test_cloud_detection_discriminators_are_event_specific():
    """A detection must not fire on unrelated CloudTrail events -- the
    discriminator tokens are eventName-specific, not a blanket cloud match."""
    _invalidate()
    for technique_id in _DETECTIONS:
        discriminators = technique_discriminators(technique_id)["tokens"]
        result, _matched = evidence_presence(
            _record("ListVersionsByFunction20150331"), discriminators
        )
        assert result != "PRESENT", (
            f"{technique_id}: fired on unrelated event ListVersionsByFunction20150331"
        )


def test_cloud_detection_sourcetypes_strict_scope():
    """spl_for_source must only return the aws:cloudtrail variant for a cloud
    technique -- a Windows/Linux default must never satisfy a cloud class."""
    _invalidate()
    assert spl_for_source("T1078.004", "windows:security") is None
    assert spl_for_source("T1526", "linux:auditd") is None
    assert spl_for_source("T1098", "OktaIM2:log") is None
