"""SA5.6 -- ANALYST_CORPUS_SNAPSHOT_V2 at real multi-source scale + pivot pairs.

Hermetic: real cloud/identity specimens + stamped endpoint parents combine
into an immutable hash-verified snapshot with cross-class pivot pairs from
real shared authoritative labels; the corpus stays appendable.
"""

from __future__ import annotations

from portal.modules.security.core.bully.analyst_corpus import (
    SNAPSHOT_SCHEMA,
    identify_pivot_pairs,
    stamp_specimen,
    take_snapshot,
    verify_snapshot,
)
from tests.security.bully._discovery_fixtures import make_specimen


# Real-shaped cloud specimen with authoritative external labels.
def _cloud_specimen(specimen_id: str, techniques: tuple[str, ...]) -> dict:
    from portal.modules.security.core.bully.analyst_corpus import ingest_events

    return ingest_events(
        [
            {
                "eventSource": "ec2.amazonaws.com",
                "eventName": "RunInstances",
                "awsRegion": "us-east-1",
            }
        ],
        specimen_id=specimen_id,
        sourcetype="aws:cloudtrail",
        techniques=techniques,
        labeling="authoritative",
        provenance={"source_id": "flaws_cloud_cloudtrail", "origin": "cloudtrail"},
    )


def _endpoint_parent(specimen_id: str, techniques: tuple[str, ...], source_class: str) -> dict:
    parent = make_specimen(
        specimen_id,
        technique_ids=list(techniques),
        family=f"attack:{techniques[0]}",
        source_class=source_class,
        action_sequence=["logon", "ticket_request", f"ev-{specimen_id}"],
    )
    return stamp_specimen(
        parent,
        label_tier="T0",
        provenance={"labeling": "authoritative", "source": "attack_data"},
        trust_tier="imported_observed",
        source_lane="attack_data",
    )


def test_cross_class_pivot_pairs_from_real_shared_labels():
    """Endpoint and cloud specimens sharing authoritative ATT&CK labels form
    genuine cross-class pivot pairs (A6) -- the cloud class is now reachable."""
    cloud = _cloud_specimen("cloud-1", ("T1098", "T1526"))
    endpoint = _endpoint_parent("endpoint-1", ("T1098",), "windows:security")
    endpoint_other = _endpoint_parent("endpoint-2", ("T1526",), "windows:sysmon")
    pairs = identify_pivot_pairs([cloud, endpoint, endpoint_other])
    cross = [p for p in pairs if p.cross_class]
    assert cross, "expected cross-class pivot pairs"
    assert all(p.cross_class for p in cross)
    assert {p.basis for p in cross} == {"shared_external_technique_label"}


def test_snapshot_v2_immutable_and_hash_verified():
    cloud = _cloud_specimen("cloud-1", ("T1098",))
    endpoint = _endpoint_parent("endpoint-1", ("T1098",), "windows:security")
    pairs = identify_pivot_pairs([cloud, endpoint])
    snapshot = take_snapshot([cloud, endpoint], pairs=pairs, name="ANALYST_CORPUS_SNAPSHOT_V2")
    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert snapshot["name"] == "ANALYST_CORPUS_SNAPSHOT_V2"
    assert verify_snapshot(snapshot)["valid"] is True
    assert snapshot["composition"]["per_class_counts"] == {
        "aws:cloudtrail": 1,
        "windows:security": 1,
    }
    assert snapshot["composition"]["pivot_pair_counts"]["cross_class"] >= 1
    tampered = dict(snapshot)
    tampered["distinct_specimens"] = tampered["distinct_specimens"][1:]
    assert verify_snapshot(tampered)["valid"] is False


def test_snapshot_v2_remains_appendable():
    cloud = _cloud_specimen("cloud-1", ("T1098",))
    first = take_snapshot([cloud], name="ANALYST_CORPUS_SNAPSHOT_V2")
    second = take_snapshot(
        [cloud, _endpoint_parent("endpoint-1", ("T1098",), "windows:security")],
        name="ANALYST_CORPUS_SNAPSHOT_V2",
    )
    assert first["snapshot_hash"] != second["snapshot_hash"]
    assert verify_snapshot(first)["valid"] is True  # first snapshot immutable


def test_distinct_text_collapse_reported_at_real_shape():
    """The snapshot reports the canonical-text collapse as a measured property
    (the P7.3 duplicate defect becomes a metric)."""
    cloud = _cloud_specimen("cloud-1", ("T1098",))
    dup = _cloud_specimen("cloud-1", ("T1098",))  # identical text
    snapshot = take_snapshot([cloud, dup], name="ANALYST_CORPUS_SNAPSHOT_V2")
    collapse = snapshot["composition"]["distinct_text_collapse"]
    assert collapse["specimen_count"] == 2
    assert collapse["distinct_texts"] == 1
    assert collapse["duplicate_texts"] == 1
