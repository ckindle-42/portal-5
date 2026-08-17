"""SA5.5 -- real multi-source ingest + per-class onboarding verdicts.

Hermetic: the analyst-corpus ingest path (real CloudTrail records -> tiered
specimens) and the SA1 loop (detection QA -> class_verdict -> cross-class
acceptance) are exercised offline. The acquired-corpus cohort counts as the
positive evidence when a class has no attack_data parents (A4); the frozen
four classes keep their attack_data path unchanged.
"""

from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.bully.analyst_corpus import (
    T0_AUTHORITATIVE,
    T1_CONFIRMED,
    census_specimens,
    ingest_events,
)
from portal.modules.security.core.bully.class_onboarding import run_detection_qa
from tests.security.bully._discovery_fixtures import make_specimen

_CLOUDTRAIL_RECORD = {
    "eventVersion": "1.08",
    "userIdentity": {
        "type": "IAMUser",
        "arn": "arn:aws:iam::811596193553:user/backup",
        "accountId": "811596193553",
        "userName": "backup",
    },
    "eventTime": "2018-04-16T06:59:20Z",
    "eventSource": "ec2.amazonaws.com",
    "eventName": "RunInstances",
    "awsRegion": "us-east-1",
    "sourceIPAddress": "203.0.113.42",
    "requestID": "83A6C73FE87F51FF",
    "eventID": "3038ebd2-c98a-4c65-9b6e-e22506292313",
    "eventType": "AwsApiCall",
    "recipientAccountId": "811596193553",
}


def _ingest_cloud_specimens() -> list[dict]:
    """Real-format CloudTrail records ingested with real T0/T1 tiering."""
    flaws = ingest_events(
        [_CLOUDTRAIL_RECORD, {**_CLOUDTRAIL_RECORD, "eventName": "CreateAccessKey"}],
        specimen_id="corpus-flaws_cloudtrail-00",
        sourcetype="aws:cloudtrail",
        techniques=("T1098",),
        labeling="authoritative",
        label_tier=T0_AUTHORITATIVE,
        provenance={"source_id": "flaws_cloud_cloudtrail", "origin": "cloudtrail:flaws"},
    )
    invictus = ingest_events(
        [_CLOUDTRAIL_RECORD],
        specimen_id="corpus-invictus-00",
        sourcetype="aws:cloudtrail",
        techniques=("T1526",),
        labeling="confirmed",
        label_tier=T1_CONFIRMED,
        provenance={"source_id": "invictus_ir_aws_dataset", "origin": "cloudtrail:invictus"},
    )
    for specimen, outcomes in ((flaws, {"T1098": "fired"}), (invictus, {"T1526": "missed"})):
        specimen["engine_view"]["telemetry_view"]["detector_outcomes"] = outcomes
    return [flaws, invictus]


def test_real_cloud_records_ingest_with_tiers_and_reconciled_census():
    specimens = _ingest_cloud_specimens()
    census = census_specimens(specimens)
    assert census["total"] == 2
    assert census["reconciled"] is True
    assert census["per_class_counts"] == {"aws:cloudtrail": 2}
    assert census["tier_distribution"] == {T0_AUTHORITATIVE: 1, T1_CONFIRMED: 1}
    assert census["unmapped_count"] == 0
    assert all(s["source_lane"] == "external_corpus" for s in specimens)


def test_detection_qa_counts_acquired_corpus_as_positive_evidence():
    """A class with no attack_data parents proves its detection on the
    acquired external-corpus cohort's live fires (A4) -- the cloud class is
    scoreable, not just present."""
    flaws = _ingest_cloud_specimens()[0]
    report = run_detection_qa(
        {"specimens": [flaws]},
        source_techniques={"aws:cloudtrail": "T1098"},
    )
    assert report["classes"]["aws:cloudtrail"]["passed"] is True
    assert report["classes"]["aws:cloudtrail"]["known_positive_live_fires"] == 1
    assert report["classes"]["aws:cloudtrail"]["positive_lane"] == "external_corpus"


def test_detection_qa_attack_data_path_unchanged_for_frozen_classes():
    """The frozen four classes still prove detection on attack_data parents --
    the acquired-cohort fallback never changes their lane."""
    parent = make_specimen(
        "sysmon-parent",
        technique_ids=["T1059.001"],
        family="attack:T1059.001",
        source_class="windows:sysmon",
        action_sequence=["powershell_launch"],
        detector_outcomes={"opaque-detector": "fired"},
    )
    report = run_detection_qa(
        {"specimens": [parent]},
        source_techniques={"windows:sysmon": "T1059.001"},
    )
    assert report["classes"]["windows:sysmon"]["positive_lane"] == "attack_data"
    assert report["classes"]["windows:sysmon"]["known_positive_live_fires"] == 1


def test_ingest_writes_corpus_artifact(tmp_path: Path, monkeypatch):
    """The SA5.5 driver writes the tiered corpus artifact with a detection QA
    report -- exercised offline with a small file limit and no live Splunk."""
    from scripts import analyst_corpus_real_ingest

    corpora = tmp_path / "corpora"
    source = corpora / "flaws_cloud_cloudtrail" / "records" / "flaws_cloudtrail_logs"
    source.mkdir(parents=True)
    (source / "flaws00.json").write_text(
        '{"Records": [{"eventName": "CreateAccessKey", "eventSource": "iam.amazonaws.com"}]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "artifacts"
    monkeypatch.setattr(
        analyst_corpus_real_ingest, "attach_detector_outcomes", lambda *a, **k: None
    )
    analyst_corpus_real_ingest.run(["--out", str(out), "--corpora", str(corpora), "--skip-live"])
    corpus = out / "corpus.json"
    assert corpus.exists()
    payload = corpus.read_text(encoding="utf-8")
    assert '"specimens"' in payload
    assert (out / "detection_qa.json").exists()
