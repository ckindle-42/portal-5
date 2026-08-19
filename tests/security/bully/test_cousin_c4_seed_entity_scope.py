"""C.4 -- seeds carry entities so scope varies per seed. Without this,
seeds from a source whose connector cannot filter by entity all resolve to
the same record window, and part of a reported compounding improvement is
the system recognising literal repeats, not relating anything."""

from __future__ import annotations

from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.connectors import IterableIngestConnector
from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane
from portal.modules.security.core.bully.seed_scope import build_scope
from scripts.bully_relate_run import _extract_entity, harvest_seeds, run_pass


def _no_entity_identity_plane(records: list[dict]) -> DataPlane:
    plane = DataPlane()
    connector = IterableIngestConnector("flaws_cloud_cloudtrail", records)
    caps = dict.fromkeys(CAPABILITIES, True)
    caps["entity_identity"] = False
    plane.connect(
        "flaws_cloud_cloudtrail", connector, connector.records, source_meta={"capabilities": caps}
    )
    return plane


def test_extract_entity_prefers_arn_then_falls_through_fields():
    assert (
        _extract_entity({"userIdentity": {"arn": "arn:aws:iam::1:user/alice"}})
        == "arn:aws:iam::1:user/alice"
    )
    assert _extract_entity({"user": "bob"}) == "bob"
    assert _extract_entity({"host": "host-9"}) == "host-9"
    assert _extract_entity({"src_ip": "10.0.0.1"}) == "10.0.0.1"
    assert _extract_entity({"account_id": "123456789012"}) == "123456789012"
    assert _extract_entity({}) is None


def test_extract_entity_unwraps_nested_record():
    nested = {"raw": {"userIdentity": {"arn": "arn:aws:iam::1:user/nested"}}}
    assert _extract_entity(nested) == "arn:aws:iam::1:user/nested"


def test_harvest_seeds_gives_each_seed_its_own_entity():
    records = [
        {"userIdentity": {"arn": "arn:aws:iam::1:user/alice"}, "eventName": "AssumeRole"},
        {"userIdentity": {"arn": "arn:aws:iam::1:user/bob"}, "eventName": "ListBuckets"},
    ]
    plane = _no_entity_identity_plane(records)
    seeds = harvest_seeds(plane, per_source=2)
    cloudtrail_seeds = [s for s, source_id in seeds if source_id == "flaws_cloud_cloudtrail"]
    assert len(cloudtrail_seeds) == 2
    assert cloudtrail_seeds[0].entities == ("arn:aws:iam::1:user/alice",)
    assert cloudtrail_seeds[1].entities == ("arn:aws:iam::1:user/bob",)
    assert cloudtrail_seeds[0].entities != cloudtrail_seeds[1].entities


def test_two_seeds_from_one_source_yield_different_scope_records_and_signatures():
    records = [
        {"userIdentity": {"arn": "arn:aws:iam::1:user/alice"}, "eventName": "AssumeRole"},
        {"userIdentity": {"arn": "arn:aws:iam::1:user/bob"}, "eventName": "ListBuckets"},
    ]
    plane = _no_entity_identity_plane(records)
    seeds = harvest_seeds(plane, per_source=2)
    lib = AnchorLibrary()

    rows = run_pass(seeds, plane, lib, write_back=False)
    cloudtrail_rows = [r for r in rows if r["source_id"] == "flaws_cloud_cloudtrail"]
    assert len(cloudtrail_rows) == 2
    # Without the harness-level entity filter both seeds would see the full
    # unfiltered window (both records) and resolve to the same signature --
    # the confound this phase closes.
    assert cloudtrail_rows[0]["record_count"] == 1
    assert cloudtrail_rows[1]["record_count"] == 1
    assert cloudtrail_rows[0]["scope_degraded"] is True


def test_seed_whose_entity_matches_nothing_yields_empty_but_valid_scope():
    records = [{"userIdentity": {"arn": "arn:aws:iam::1:user/alice"}, "eventName": "AssumeRole"}]
    plane = _no_entity_identity_plane(records)
    seeds = harvest_seeds(plane, per_source=1)
    seed, source_id = seeds[0]
    from dataclasses import replace

    seed = replace(seed, entities=("arn:aws:iam::1:user/nobody",))

    lib = AnchorLibrary()
    rows = run_pass([(seed, source_id)], plane, lib, write_back=False)
    assert len(rows) == 1
    assert rows[0]["record_count"] == 0
    assert rows[0]["scope_degraded"] is True


def test_harness_entity_filter_reason_only_applied_when_connector_cannot_filter():
    """A source that DOES declare entity_identity is left to the connector's
    own filtering -- the harness-level narrowing never fires (and never
    claims the connector doesn't support it) when it isn't needed."""
    plane = DataPlane()
    connector = IterableIngestConnector("edr", [{"host": "host-a", "action": "proc_create"}])
    caps = dict.fromkeys(CAPABILITIES, True)
    plane.connect("edr", connector, connector.records, source_meta={"capabilities": caps})
    from portal.modules.security.core.bully.seed_scope import Seed

    seed = Seed(seed_id="s1", kind="detection_fire", entities=("host-a",))
    scope = build_scope(seed, plane, "edr", scale_cap=32)
    assert "harness_entity_filter" not in scope.reasons

    lib = AnchorLibrary()
    rows = run_pass([(seed, "edr")], plane, lib, write_back=False)
    assert rows[0]["record_count"] == 1
