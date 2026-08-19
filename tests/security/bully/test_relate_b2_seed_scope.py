"""B.2 -- seed contract + constructed scope. Identical seed+bounds -> identical
scope; a capability-poor source yields a small honest scope rather than an
error."""

from __future__ import annotations

from portal.modules.security.core.bully.connectors import IterableIngestConnector
from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane
from portal.modules.security.core.bully.seed_scope import Seed, build_scope


def _plane_with(source_id: str, capabilities: dict[str, bool], records: list[dict]) -> DataPlane:
    plane = DataPlane()
    connector = IterableIngestConnector(source_id, records)
    plane.connect(
        source_id, connector, connector.records, source_meta={"capabilities": capabilities}
    )
    return plane


def _seed() -> Seed:
    return Seed(
        seed_id="seed-001",
        kind="detection_fire",
        entities=("host-a",),
        start=1000.0,
        end=2000.0,
    )


def test_identical_seed_and_bounds_produce_identical_scope():
    caps = dict.fromkeys(CAPABILITIES, True)
    plane = _plane_with("edr", caps, [{"host": "host-a", "action": "proc_create"}])
    seed = _seed()
    scope_a = build_scope(seed, plane, "edr")
    scope_b = build_scope(seed, plane, "edr")
    assert scope_a.scope_id == scope_b.scope_id
    assert scope_a.bounds == scope_b.bounds


def test_capability_poor_source_yields_small_honest_scope_not_error():
    caps = dict.fromkeys(CAPABILITIES, False)
    plane = _plane_with("opaque-feed", caps, [{"raw": "line one"}, {"raw": "line two"}])
    seed = _seed()
    scope = build_scope(seed, plane, "opaque-feed")
    assert scope.degraded is True
    assert "entity_identity_absent:time_only_traversal" in scope.reasons
    assert "episode_boundary_absent:flat_scope" in scope.reasons
    assert scope.bounds.entities == ()
    assert len(scope.records) == 2


def test_episode_structured_source_returns_episode_boundary_true():
    caps = dict.fromkeys(CAPABILITIES, True)
    plane = _plane_with("attack-corpus", caps, [{"host": "host-a"}])
    scope = build_scope(_seed(), plane, "attack-corpus")
    assert scope.episode_boundary is True
    assert scope.degraded is False


def test_scale_cap_truncation_is_recorded_not_hidden():
    caps = dict.fromkeys(CAPABILITIES, True)
    records = [{"host": "host-a", "i": i} for i in range(10)]
    plane = _plane_with("busy-source", caps, records)
    seed = _seed()
    scope = build_scope(seed, plane, "busy-source", scale_cap=3)
    assert len(scope.records) == 3
    assert scope.truncated is True
    assert "scale_cap_reached" in scope.reasons
