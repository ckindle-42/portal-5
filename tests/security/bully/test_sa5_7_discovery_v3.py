"""SA5.7 -- discovery re-run on the multi-class analyst corpus (DISCOVERY_BASELINE_V3).

Hermetic: the analyst snapshot feeds the discovery lane with the multi-class
probe selector (T0/T1 across endpoint + cloud/identity); the report carries
same-class vs cross-class and T0-only vs full-haystack cohorts; the V3-stamped
artifact supersedes V1.
"""

from __future__ import annotations

from portal.modules.security.core.bully.discovery_bench import (
    analyst_probe_specimens,
    analyst_snapshot_specimens,
)
from tests.security.bully._discovery_fixtures import (
    make_specimen,
)


def _analyst_snapshot() -> dict:
    from portal.modules.security.core.bully.analyst_corpus import (
        ingest_events,
        take_snapshot,
    )

    endpoint = [
        make_specimen(
            f"endpoint-{i}",
            technique_ids=["T1098"],
            family="attack:T1098",
            source_class="windows:security",
            action_sequence=["logon", "create_user", f"variant_{i}"],
        )
        for i in range(4)
    ]
    cloud = ingest_events(
        [
            {
                "eventSource": "iam.amazonaws.com",
                "eventName": "CreateAccessKey",
                "awsRegion": "us-east-1",
            }
        ],
        specimen_id="cloud-1",
        sourcetype="aws:cloudtrail",
        techniques=("T1098",),
        labeling="authoritative",
        provenance={"source_id": "flaws_cloud_cloudtrail", "origin": "cloudtrail"},
    )
    from portal.modules.security.core.bully.analyst_corpus import stamp_specimen

    stamped_endpoint = [
        stamp_specimen(
            s,
            label_tier="T0",
            provenance={"labeling": "authoritative", "source": "attack_data"},
            trust_tier="imported_observed",
            source_lane="attack_data",
        )
        for s in endpoint
    ]
    return take_snapshot(stamped_endpoint + [cloud], name="ANALYST_CORPUS_SNAPSHOT_V2")


def test_analyst_snapshot_probes_span_multi_class():
    """The analyst probe selector picks T0/T1 specimens across endpoint AND
    cloud/identity lanes -- the discovery lane finally has breadth (SA5.7)."""
    snapshot = _analyst_snapshot()
    probes = analyst_probe_specimens(snapshot)
    assert len(probes) == 5
    classes = {p["source_class"] for p in probes}
    assert classes == {"windows:security", "aws:cloudtrail"}


def test_analyst_snapshot_specimens_extraction():
    snapshot = _analyst_snapshot()
    assert len(analyst_snapshot_specimens(snapshot)) == 5


def test_t0_only_cohort_keeps_the_comparison_honest():
    """SA5.7 reports the T0-only cohort alongside the full-haystack so the
    noise effect of a real heterogeneous corpus is visible, not alarming."""
    snapshot = _analyst_snapshot()
    probes = analyst_probe_specimens(snapshot)
    t0 = [p for p in probes if p.get("label_tier") == "T0"]
    t1 = [p for p in probes if p.get("label_tier") == "T1"]
    assert len(t0) + len(t1) == len(probes)
    assert all(p.get("label_tier") in ("T0", "T1") for p in probes)
