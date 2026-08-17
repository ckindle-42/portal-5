"""SA4.2 -- broad multi-source ingestion with T0-T3 label tiering.

Hermetic: ingest through the source-adapter seam, stamp tiers, and census
every input. No network, no external data.
"""

from __future__ import annotations

from portal.modules.security.core.bully.analyst_corpus import (
    T0_AUTHORITATIVE,
    T1_CONFIRMED,
    T2_PROPOSED,
    T3_UNKNOWN,
    census_specimens,
    ingest_events,
    label_tier_for,
    tier_is_scoreable,
    tier_resolution,
)
from scripts import corpus_ingest


def test_label_tier_mapping_a1():
    assert label_tier_for("authoritative") == T0_AUTHORITATIVE
    assert label_tier_for("per-entry ATT&CK") == T0_AUTHORITATIVE
    assert label_tier_for("confirmed") == T1_CONFIRMED
    assert label_tier_for("reviewed") == T1_CONFIRMED
    assert label_tier_for("machine-clustered") == T2_PROPOSED
    assert label_tier_for("proposed") == T2_PROPOSED
    assert label_tier_for(None) == T3_UNKNOWN
    assert label_tier_for("") == T3_UNKNOWN
    assert label_tier_for("benign") == T3_UNKNOWN
    assert tier_is_scoreable(T0_AUTHORITATIVE) is True
    assert tier_is_scoreable(T1_CONFIRMED) is True
    assert tier_is_scoreable(T2_PROPOSED) is False
    assert tier_is_scoreable(T3_UNKNOWN) is False


def test_t3_specimen_ingests_is_retrievable_but_unscoreable():
    """A T3 (unlabeled/unknown) specimen is ingested and participates in
    retrieval, but a graded pair involving it resolves INDETERMINATE -- never
    a hit or a miss (A1)."""
    specimen = ingest_events(
        [{"eventType": "user.authentication.auth_via_mfa", "outcome": {"result": "FAILURE"}}],
        specimen_id="okta-t3",
        sourcetype="OktaIM2:log",
        labeling="none",
        provenance={"source_id": "okta_export", "origin": "okta_syslog"},
    )
    assert specimen["label_tier"] == T3_UNKNOWN
    assert specimen["scoreable"] is False
    assert specimen["source_lane"] == "external_corpus"
    assert specimen["source_class"] == "OktaIM2:log"
    # Retrievable: the engine view carries the identity-shaped dimensions.
    assert "action_sequence" in specimen["engine_view"]["telemetry_view"]
    # Unscoreable: any graded pair resolves INDETERMINATE, never a hit/miss.
    assert tier_resolution(T0_AUTHORITATIVE, T3_UNKNOWN) == "INDETERMINATE"
    assert tier_resolution(T3_UNKNOWN, T0_AUTHORITATIVE) == "INDETERMINATE"
    assert tier_resolution(T2_PROPOSED, T1_CONFIRMED) == "INDETERMINATE"
    assert tier_resolution(T0_AUTHORITATIVE, T1_CONFIRMED) is None


def test_t0_authoritative_specimen_is_scoreable():
    specimen = ingest_events(
        [{"EventCode": 1, "Image": "powershell.exe"}],
        specimen_id="sysmon-t0",
        sourcetype="windows:sysmon",
        labeling="authoritative",
        provenance={"source_id": "attack_data", "origin": "external_corpus"},
    )
    assert specimen["label_tier"] == T0_AUTHORITATIVE
    assert specimen["scoreable"] is True


def test_unmapped_class_routes_to_fallback_with_absent_dimensions():
    """An unmapped shape routes through the fallback adapter: missing
    dimensions stay absent (honest completeness), never padded (A7)."""
    specimen = ingest_events(
        ["netflow exporter 192.0.2.1 443 -> 198.51.100.7 49152"],
        specimen_id="netflow-unmapped",
        sourcetype="netflow",
        techniques=("T1043",),
        labeling=None,
        provenance={"source_id": "netflow_exporter", "origin": "edge_router"},
    )
    view = specimen["engine_view"]["telemetry_view"]
    assert specimen["adapter_status"] == "unmapped"
    assert specimen["label_tier"] == T3_UNKNOWN
    assert "action_sequence" not in view
    assert "event_graph" not in view
    assert view["telemetry_shape"]["adapter_status"] == "unmapped"
    assert view["artifacts"]["raw_event_count"] == 1
    assert {m["technique_id"] for m in view["attack_mappings"]} == {"T1043"}


def test_cloud_class_admitted_and_classified():
    """A cloud sourcetype (CloudTrail) is recognized as a broad cloud class by
    the injector, and admitted through the fallback adapter seam with honest
    completeness (no cloud adapter yet -- A7): missing dimensions stay absent,
    never padded, and the specimen is censused, never dropped."""
    specimen = ingest_events(
        [
            {
                "eventSource": "s3.amazonaws.com",
                "eventName": "PutObject",
                "userIdentity": {"arn": "arn:aws:iam::123:user/x"},
            }
        ],
        specimen_id="cloudtrail-1",
        sourcetype="aws:cloudtrail",
        labeling="authoritative",
        provenance={"source_id": "flaws.cloud", "origin": "cloudtrail"},
    )
    assert specimen["adapter_status"] == "unmapped"
    assert specimen["source_class"] == "aws:cloudtrail"
    assert specimen["label_tier"] == T0_AUTHORITATIVE
    assert corpus_ingest.resolve_source_class("aws:cloudtrail") == "cloud"
    assert corpus_ingest.resolve_sourcetype(None, None, {}, "cloudtrail.log") == "aws:cloudtrail"


def test_census_accounts_for_every_input_dataset(tmp_path):
    """The corpus census accounts for every specimen -- admitted, unmapped,
    per class/tier/lane -- with a reconciled total (A7)."""
    specimens = [
        ingest_events(
            [{"EventCode": 4688, "Image": "cmd.exe"}],
            specimen_id="win-a",
            sourcetype="windows:security",
            labeling="authoritative",
            provenance={"source_id": "attack_data"},
        ),
        ingest_events(
            [{"eventType": "user.authentication.auth_via_mfa"}],
            specimen_id="okta-b",
            sourcetype="OktaIM2:log",
            labeling="confirmed",
            provenance={"source_id": "okta"},
        ),
        ingest_events(
            ["vendor advisory IOC 203.0.113.4"],
            specimen_id="adv-c",
            sourcetype="threat-intel:advisory",
            labeling=None,
            provenance={"source_id": "vendor_bulletin"},
        ),
    ]
    census = census_specimens(specimens)
    assert census["total"] == 3
    assert census["reconciled"] is True
    assert census["per_class_counts"] == {
        "OktaIM2:log": 1,
        "threat-intel:advisory": 1,
        "windows:security": 1,
    }
    assert census["tier_distribution"] == {T0_AUTHORITATIVE: 1, T1_CONFIRMED: 1, T3_UNKNOWN: 1}
    # The advisory has no class adapter yet -> routed to fallback, censused as
    # an unmapped class, never dropped (A7).
    assert census["unmapped_count"] == 1
    assert census["unmapped_specimens"] == ["adv-c"]


def test_dataset_census_accounts_for_every_input_file(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "cloudtrail.log").write_text(
        '{"eventSource": "s3.amazonaws.com", "eventName": "PutObject"}\n', encoding="utf-8"
    )
    (root / "okta.json").write_text(
        '{"eventType": "user.authentication.auth_via_mfa"}\n', encoding="utf-8"
    )
    (root / "netflow.txt").write_text(
        "exporter 192.0.2.1 443 -> 10.0.0.5 49152\n", encoding="utf-8"
    )
    (root / "proprietary.log").write_text("PII sensor reading 0x7f\n", encoding="utf-8")
    (root / "empty.log").write_text("\n", encoding="utf-8")
    census = corpus_ingest.dataset_census(root)
    assert census["datasets_observed"] == 5
    assert census["reconciled"] is True
    admitted_by_dataset = {row["dataset"]: row for row in census["admitted"]}
    assert "cloudtrail.log" in admitted_by_dataset
    assert admitted_by_dataset["cloudtrail.log"]["source_class"] == "cloud"
    assert (
        admitted_by_dataset["cloudtrail.log"]["label_tier"] == T3_UNKNOWN
    )  # no manifest -> unlabeled
    assert admitted_by_dataset["okta.json"]["source_class"] == "identity"
    assert admitted_by_dataset["netflow.txt"]["source_class"] == "network"
    unmapped_by_dataset = {row["dataset"]: row for row in census["unmapped"]}
    assert "proprietary.log" in unmapped_by_dataset
    assert unmapped_by_dataset["proprietary.log"]["source_class"] == "unmapped"
    assert census["no_events"] == ["empty.log"]
