"""R.3b -- entity resolution and cross-source timeline assembly."""

from __future__ import annotations

from portal.modules.security.core.bully.correlation import (
    IdentifierObservation,
    assemble_timelines,
    resolve_entities,
)


def _artifact(aid, source, ts, **fields):
    return {"artifact_id": aid, "source_id": source, "time": ts, **fields}


def _obs(value, field_path, source_id, artifact_id):
    return IdentifierObservation(
        value=value, field_path=field_path, source_id=source_id, artifact_id=artifact_id
    )


def test_four_source_jsmith_chain_resolves_to_one_entity_one_timeline() -> None:
    artifacts = [
        _artifact("a1", "win", 100.0, user="CORP\\jsmith", host="ws01"),
        _artifact("a2", "dns", 110.0, user="jsmith@corp.com"),
        _artifact("a3", "cloud", 120.0, user="jsmith@corp.com", ip="10.0.1.45"),
        _artifact("a4", "fw", 130.0, ip="10.0.1.45"),
    ]
    observations = [
        _obs("CORP\\jsmith", "user", "win", "a1"),
        _obs("ws01", "host", "win", "a1"),
        _obs("jsmith@corp.com", "user", "dns", "a2"),
        _obs("jsmith@corp.com", "user", "cloud", "a3"),
        _obs("10.0.1.45", "ip", "cloud", "a3"),
        _obs("10.0.1.45", "ip", "fw", "a4"),
    ]
    entities, value_to_id = resolve_entities(observations)
    jsmith_eid = value_to_id["CORP\\jsmith"]
    assert value_to_id["jsmith@corp.com"] == jsmith_eid
    assert value_to_id["10.0.1.45"] == jsmith_eid
    assert value_to_id["ws01"] != jsmith_eid  # host stays distinct kind/root

    timelines = assemble_timelines(
        artifacts,
        entities,
        value_to_id,
        artifact_entity_values=lambda a: [
            v for v in (a.get("user"), a.get("host"), a.get("ip")) if v
        ],
        artifact_time=lambda a: a["time"],
        artifact_id=lambda a: a["artifact_id"],
        artifact_source=lambda a: a["source_id"],
    )
    jsmith_timeline = next(t for t in timelines if t.entity.entity_id == jsmith_eid)
    assert jsmith_timeline.n_sources == 4
    assert jsmith_timeline.is_cross_source
    assert set(jsmith_timeline.source_ids) == {"win", "dns", "cloud", "fw"}


def test_seeded_violation_disabling_cooccurrence_fragments_the_chain() -> None:
    """Seeded violation: without cross-kind co-occurrence linking, the
    username observed in win/dns/cloud never joins the IP observed in
    cloud/fw -- the exact UEBA false-negative the research names."""
    observations = [
        _obs("CORP\\jsmith", "user", "win", "a1"),
        _obs("jsmith@corp.com", "user", "dns", "a2"),
        _obs("jsmith@corp.com", "user", "cloud", "a3"),
        _obs("10.0.1.45", "ip", "cloud", "a3"),
        _obs("10.0.1.45", "ip", "fw", "a4"),
    ]

    # correct behavior: co-occurrence (jsmith@corp.com + 10.0.1.45 on a3) links them
    entities, value_to_id = resolve_entities(observations)
    assert value_to_id["CORP\\jsmith"] == value_to_id["10.0.1.45"]

    # seeded violation: simulate co-occurrence disabled by stripping the
    # shared-artifact evidence (only single-identifier observations survive)
    solo_observations = [
        _obs("CORP\\jsmith", "user", "win", "a1"),
        _obs("jsmith@corp.com", "user", "dns", "a2"),
        _obs("jsmith@corp.com", "user", "cloud", "a2b"),
        _obs("10.0.1.45", "ip", "cloud", "a2c"),
        _obs("10.0.1.45", "ip", "fw", "a4"),
    ]
    entities2, value_to_id2 = resolve_entities(solo_observations)
    assert value_to_id2["CORP\\jsmith"] != value_to_id2["10.0.1.45"]


def test_two_users_on_one_runas_record_stay_distinct() -> None:
    observations = [
        _obs("alice", "actor_user", "win", "a1"),
        _obs("bob", "target_user", "win", "a1"),
    ]
    entities, value_to_id = resolve_entities(observations)
    assert value_to_id["alice"] != value_to_id["bob"]


def test_two_ips_on_one_netflow_record_stay_distinct() -> None:
    observations = [
        _obs("10.0.0.1", "src_ip", "fw", "a1"),
        _obs("10.0.0.2", "dst_ip", "fw", "a1"),
    ]
    entities, value_to_id = resolve_entities(observations)
    assert value_to_id["10.0.0.1"] != value_to_id["10.0.0.2"]


def test_lone_benign_artifact_from_one_source_is_singleton_not_insufficient_view() -> None:
    artifacts = [_artifact("a1", "fw", 100.0, ip="10.9.9.9")]
    observations = [_obs("10.9.9.9", "ip", "fw", "a1")]
    entities, value_to_id = resolve_entities(observations)
    timelines = assemble_timelines(
        artifacts,
        entities,
        value_to_id,
        artifact_entity_values=lambda a: [a["ip"]],
        artifact_time=lambda a: a["time"],
        artifact_id=lambda a: a["artifact_id"],
        artifact_source=lambda a: a["source_id"],
    )
    assert len(timelines) == 1
    assert timelines[0].n_sources == 1
    assert timelines[0].artifact_ids == ("a1",)


def test_genuinely_opaque_unresolvable_record_yields_no_timeline() -> None:
    # No identifier observations at all for this artifact -- the ONLY
    # legitimate INSUFFICIENT_VIEW case: nothing to reason about even after
    # attempting correlation.
    artifacts = [_artifact("a1", "syslog", 100.0, msg="free text line")]
    entities, value_to_id = resolve_entities([])
    timelines = assemble_timelines(
        artifacts,
        entities,
        value_to_id,
        artifact_entity_values=lambda a: [],
        artifact_time=lambda a: a["time"],
        artifact_id=lambda a: a["artifact_id"],
        artifact_source=lambda a: a["source_id"],
    )
    assert timelines == []
