"""U.1 -- artifact graph and gradeable units (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag


def _benign_record(i: int, base_time: float) -> dict:
    return {
        "eventName": "ListBuckets",
        "userIdentity.userName": f"benign-user-{i % 7}",
        "eventTime": base_time + i * 37.0,
    }


def _chain_records(base_time: float) -> list[dict]:
    """A 6-step chain on one identity, spanning under 300s."""
    verbs = [
        "AssumeRole",
        "ListBuckets",
        "AttachUserPolicy",
        "PutObject",
        "GetObject",
        "DeleteBucket",
    ]
    return [
        {
            "eventName": verb,
            "user": "arn:aws:iam::111:user/attacker",
            "eventTime": base_time + step * 40.0,
        }
        for step, verb in enumerate(verbs)
    ]


def test_chain_surfaces_as_l2_and_l3_size_six():
    base_time = 1_700_000_000.0
    benign = [_benign_record(i, base_time) for i in range(120)]
    chain = _chain_records(base_time + 10_000.0)
    records = benign + chain

    graph = ag.build_graph(records)
    units = ag.enumerate_units(graph)

    l2 = [u for u in units if u.level == "L2_ENTITY" and u.size == 6]
    l3 = [u for u in units if u.level == "L3_CHAIN" and u.size == 6]
    assert l2, "expected a size-6 L2_ENTITY unit for the attacker identity"
    assert l3, "expected a size-6 L3_CHAIN unit for the attacker chain"

    chain_ids = set(l3[0].artifact_ids)
    assert chain_ids == set(l2[0].artifact_ids)


def test_seeded_violation_temporal_edge_without_shared_entity_collapses_l3_to_l4():
    """If temporal adjacency is allowed to create an edge without a shared
    entity, a steady stream chains into one component and L3 collapses into
    L4 -- exactly the defect this module exists to prevent."""
    base_time = 1_700_000_000.0
    # Users recur (25 distinct identities over 50 records) rather than being
    # unique per record: field-role inference (E.1/E.2) demotes a
    # near-unique-per-record field to PAYLOAD (a record id), not ENTITY --
    # correctly, since that is the identifier-of-the-record case, not a
    # thing an analyst pivots on. Recurrence keeps this a genuine ENTITY
    # field while consecutive-in-time records still never share an identity,
    # so the guard-vs-unguarded contrast this test exists to prove still
    # holds.
    records = [
        {
            "eventName": "ListBuckets",
            "userIdentity.userName": f"user-{i % 25}",
            "eventTime": base_time + i * 5.0,
        }
        for i in range(50)
    ]

    graph = ag.build_graph(records)
    # Correct behaviour: no shared entity between distinct users -> no
    # temporal_adjacency edges at all, so no chains beyond isolated nodes.
    assert not any(e.kind == "temporal_adjacency" for e in graph.edges)

    # Now simulate the bug directly: build edges the way an unguarded
    # temporal-only rule would, and confirm it *would* collapse into one
    # window-sized component (proving the guard in build_graph matters).
    unguarded_edges = []
    timed = sorted(
        (a for a in graph.artifacts.values() if a.timestamp is not None),
        key=lambda a: a.timestamp or 0.0,
    )
    for left, right in zip(timed, timed[1:], strict=False):
        gap = (right.timestamp or 0.0) - (left.timestamp or 0.0)
        if gap <= ag.TEMPORAL_ADJACENCY_SECONDS:
            unguarded_edges.append(
                ag.Edge(left.artifact_id, right.artifact_id, "temporal_adjacency", f"{gap:.0f}s")
            )
    unguarded_graph = ag.ArtifactGraph(list(graph.artifacts.values()), unguarded_edges)
    components = unguarded_graph.components()
    assert len(components) == 1
    assert len(components[0]) == len(records)


def test_artifact_set_reachable_via_two_entity_keys_yields_one_unit_per_level():
    base_time = 1_700_000_000.0
    # A benign backdrop with recurring, varied identities gives "user" and
    # "src_ip" enough distinct-value evidence for field-role inference
    # (E.1/E.2) to resolve them as ENTITY; a two-record sample alone cannot
    # be told apart, structurally, from a whole-corpus CONSTANT (an account
    # id, a region) at n=2.
    records = [
        {
            "eventName": "ListBuckets",
            "user": f"arn:aws:iam::111:user/benign{i % 10}",
            "src_ip": f"10.0.0.{i % 10}",
            "eventTime": base_time - 10_000.0 + i * 5.0,
        }
        for i in range(60)
    ]
    records += [
        {
            "eventName": "AssumeRole",
            "user": "arn:aws:iam::111:user/dual",
            "src_ip": "10.0.0.9",
            "eventTime": base_time,
        },
        {
            "eventName": "PutObject",
            "user": "arn:aws:iam::111:user/dual",
            "src_ip": "10.0.0.9",
            "eventTime": base_time + 30.0,
        },
    ]
    graph = ag.build_graph(records)
    units = ag.enumerate_units(graph)
    dual_ids = {"a00060", "a00061"}
    l2_units = [u for u in units if u.level == "L2_ENTITY" and set(u.artifact_ids) == dual_ids]
    assert len(l2_units) == 1


def test_unit_counts_are_on_k_not_2n():
    base_time = 1_700_000_000.0
    records = [_benign_record(i, base_time) for i in range(126)]
    chain = _chain_records(base_time + 50_000.0)
    records += chain

    graph = ag.build_graph(records)
    units = ag.enumerate_units(graph)
    assert len(units) < 300


def test_unit_cap_holds_under_large_window():
    base_time = 1_700_000_000.0
    records = [
        {
            "eventName": "ListBuckets",
            "userIdentity.userName": f"user-{i % 40}",
            "eventTime": base_time + i,
        }
        for i in range(5000)
    ]
    graph = ag.build_graph(records)
    units = ag.enumerate_units(graph)
    for level in ag.UNIT_LEVELS:
        assert sum(1 for u in units if u.level == level) <= ag.MAX_UNITS_PER_LEVEL


def test_structural_signature_matches_across_disjoint_vocabulary_once_classes_align():
    base_time = 1_700_000_000.0
    # Field-role inference (E.1/E.2) is statistical: it needs the chain
    # repeated a few times to see the eventName field's cardinality is low
    # relative to sample size (ACTION) and the identity field has more than
    # one value (ENTITY, not a whole-corpus CONSTANT) -- neither is visible
    # from 3 literally-unique records. Repeating the 3-step pattern keeps
    # `class_sequence[2]` pointing at the same first-repetition step (sorted
    # by ascending timestamp) while giving inference enough signal.
    aws_verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
    aws_users = ["arn:aws:iam::1:user/a", "arn:aws:iam::1:user/a", "arn:aws:iam::1:user/a2"]
    aws_chain = [
        {
            "eventName": aws_verbs[i % 3],
            "user": aws_users[i % 3],
            "eventTime": base_time + i * 40.0,
        }
        for i in range(15)
    ]
    win_verbs = ["Logon", "net user", "Add-LocalGroupMember"]
    win_hosts = ["WIN-HOST-1", "WIN-HOST-1", "WIN-HOST-2"]
    win_chain = [
        {
            "eventName": win_verbs[i % 3],
            "host": win_hosts[i % 3],
            "eventTime": base_time + i * 40.0,
        }
        for i in range(15)
    ]

    aws_graph = ag.build_graph(aws_chain)
    win_graph = ag.build_graph(win_chain)

    aws_units = ag.enumerate_units(aws_graph)
    win_units = ag.enumerate_units(win_graph)

    aws_window = next(u for u in aws_units if u.level == "L4_WINDOW")
    win_window = next(u for u in win_units if u.level == "L4_WINDOW")

    assert set(aws_window.vocabulary).isdisjoint(set(win_window.vocabulary))
    # "Add-LocalGroupMember" does not map to "escalate" under the deterministic
    # table -- this assertion documents the U.3 seam rather than papering
    # over it; class sequences diverge exactly where the table's coverage runs out.
    assert aws_window.structural_signature["class_sequence"][2] == "escalate"
    assert win_window.structural_signature["class_sequence"][2] != "escalate"


def test_empty_window_returns_no_units_and_never_raises():
    graph = ag.build_graph([])
    units = ag.enumerate_units(graph)
    assert units == []
