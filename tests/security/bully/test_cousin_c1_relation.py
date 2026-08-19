"""C.1 -- the cousin grader's contract, each claim seeded so it can fail."""

from __future__ import annotations

from types import SimpleNamespace

from portal.modules.security.core.bully import cousin_relation as cr


def subject(actions=None, telemetry=None, context=None, params=None, attack=None, sid="s1"):
    return SimpleNamespace(
        signature_id=sid,
        action_sequence=list(actions or []),
        telemetry_shape=dict(telemetry or {}),
        context_topology=dict(context or {}),
        parameter_families=dict(params or {}),
        event_graph={},
        attack_mappings=[{"technique_id": t} for t in (attack or [])],
    )


def corpus(n_common=60):
    records = [
        {
            "record_id": f"common-{i}",
            "action_sequence": ["whoami", "net user", "ipconfig"],
            "telemetry_shape": {"source_class": "windows"},
            "context_topology": {"os": "windows"},
            "attack_mappings": [{"technique_id": "T1087"}],
        }
        for i in range(n_common)
    ]
    records.append(
        {
            "record_id": "PARENT-cred",
            "action_sequence": ["AssumeRole", "GetSessionToken", "ListBuckets"],
            "telemetry_shape": {"source_class": "cloudtrail"},
            "context_topology": {"cloud": "aws"},
            "attack_mappings": [{"technique_id": "T1078.004"}],
        }
    )
    return records


def test_coverage_never_gates_classification():
    """N2: an arrival carrying ONE observable axis (coverage 0.30, far under the
    old 0.6 mass floor) is still graded, not refused."""
    records = corpus()
    thin = subject(["AssumeRole", "GetSessionToken", "ListBuckets"])
    rel = cr.relate_cousin(thin, records)
    assert rel.coverage < 0.6
    assert rel.status == "COUSIN_CANDIDATE"
    assert rel.anchor_id == "PARENT-cred"
    assert rel.distance is not None


def test_distance_is_comparable_across_coverage_levels():
    """Inversion 1: identical behavioural agreement yields identical distance
    whether or not the arrival also carries telemetry/context."""
    records = corpus()
    thin = subject(["AssumeRole", "GetSessionToken", "ListBuckets"])
    rich = subject(
        ["AssumeRole", "GetSessionToken", "ListBuckets"],
        {"source_class": "cloudtrail"},
        {"cloud": "aws"},
    )
    d_thin = cr.relate_cousin(thin, records).distance
    d_rich = cr.relate_cousin(rich, records).distance
    assert d_thin == d_rich == 0.0
    assert cr.relate_cousin(rich, records).coverage > cr.relate_cousin(thin, records).coverage


def test_attack_axis_never_required_of_the_arrival():
    """Inversion 3: the arrival carries no technique id -- the circular
    requirement -- and still relates, with the technique emitted as output."""
    records = corpus()
    arrival = subject(
        ["AssumeRole", "GetSessionToken", "ListBuckets"],
        {"source_class": "cloudtrail"},
        {"cloud": "aws"},
    )
    assert arrival.attack_mappings == []
    rel = cr.relate_cousin(arrival, records)
    assert rel.status == "COUSIN_CANDIDATE"
    assert "T1078.004" in rel.hypothesized_techniques
    assert "attack" in rel.delta.unobservable_dimensions


def test_delta_is_mandatory_and_populated_for_a_cousin():
    """Inversion 4: a cousin without a delta is not an actionable product."""
    records = corpus()
    arrival = subject(
        ["AssumeRole", "GetSessionToken", "DescribeInstances"],
        {"source_class": "cloudtrail"},
        {"cloud": "aws"},
    )
    rel = cr.relate_cousin(arrival, records)
    assert rel.status == "COUSIN_CANDIDATE"
    assert not rel.delta.is_empty
    assert "AssumeRole" in rel.delta.shared_features
    assert "DescribeInstances" in rel.delta.diverging_features
    assert rel.delta.axis_of_divergence is not None


def test_insufficient_view_is_not_novelty():
    """The bin split: an arrival sharing no dimension with any anchor is an
    instrument finding, never a discovery."""
    records = corpus()
    blank = subject()
    rel = cr.relate_cousin(blank, records)
    assert rel.status == "INSUFFICIENT_VIEW"
    assert rel.distance is None
    assert "no_comparable_anchor:relation_uncomputable" in rel.uncertainty_reasons


def test_novel_notable_requires_positive_distinctiveness():
    """Anti-inflation: novelty needs distinctive content, never mere absence
    of a match."""
    records = corpus()
    unrelated = subject(["SELECT", "INSERT", "COMMIT"], {"source_class": "db"}, {"engine": "pg"})
    rel = cr.relate_cousin(unrelated, records)
    assert rel.status == "NOVEL_NOTABLE"
    assert rel.distinctiveness >= cr.NOVELTY_MIN_DISTINCTIVENESS
    # seeded violation: raise the bar above what this arrival can show
    demoted = cr.relate_cousin(unrelated, records, novelty_min_distinctiveness=1.1)
    assert demoted.status == "NO_RELATION"


def test_no_parent_is_named_outside_a_cousin_verdict():
    """N3 overclaim guard: a nearest-but-far anchor is not a parent, and its
    technique is not hypothesized -- this is anchor-bias forcing."""
    records = corpus()
    unrelated = subject(["SELECT", "INSERT", "COMMIT"], {"source_class": "db"}, {"engine": "pg"})
    rel = cr.relate_cousin(unrelated, records)
    assert rel.status != "COUSIN_CANDIDATE"
    assert rel.anchor_id is None
    assert rel.hypothesized_techniques == ()
    # the distance profile is still published -- silence is the only real failure
    assert rel.ranked_cousins and rel.distance is not None


def test_rare_shared_feature_outweighs_boilerplate():
    """Inversion 5: divergence can raise interest. A rare motif held in common
    must close more distance than a motif every anchor carries."""
    records = corpus()
    index = cr.build_discriminative_index(records)
    rare = index.weight("AssumeRole")
    common = index.weight("whoami")
    assert rare > common


def test_distinctiveness_is_bounded():
    records = corpus()
    for arrival in (
        subject(["AssumeRole"]),
        subject(["zzz-never-seen-token"]),
        subject(["whoami", "net user"]),
    ):
        rel = cr.relate_cousin(arrival, records)
        assert 0.0 <= rel.distinctiveness <= 1.0
        assert 0.0 <= rel.confidence <= 1.0


def test_constructed_ladder_ranks_monotonically():
    """Truth by construction: distance must increase as the constructed cousin
    is walked away from its parent."""
    records = corpus()
    index = cr.build_discriminative_index(records)
    cloud = ({"source_class": "cloudtrail"}, {"cloud": "aws"})
    ladder = [
        (["AssumeRole", "GetSessionToken", "ListBuckets"], *cloud),
        (["AssumeRole", "GetSessionToken", "GetCallerIdentity"], *cloud),
        (["AssumeRole", "DescribeInstances", "RunInstances"], *cloud),
        # last rung leaves the environment entirely -- otherwise a shared
        # telemetry/context axis correctly keeps it a distant cousin.
        (["SELECT", "INSERT", "COMMIT"], {"source_class": "db"}, {"engine": "pg"}),
    ]
    distances = [
        cr.relate_cousin(subject(a, t, c), records, index=index).distance for a, t, c in ladder
    ]
    assert distances == sorted(distances), distances
    assert distances[0] == 0.0
    assert distances[-1] > cr.COUSIN_MAX_DISTANCE


def test_shared_environment_keeps_a_distant_cousin_related():
    """A property worth pinning: an arrival doing entirely different actions in
    the *same* environment is a distant cousin, not unrelated -- the telemetry
    and context axes still agree. The old grader could not express this."""
    records = corpus()
    same_env = subject(
        ["SELECT", "INSERT", "COMMIT"], {"source_class": "cloudtrail"}, {"cloud": "aws"}
    )
    rel = cr.relate_cousin(same_env, records)
    assert 0.0 < rel.distance < 1.0
    assert rel.delta.axis_of_divergence == "behavior"


def test_uncertainty_reasons_vary_within_one_source_shape():
    """The G.4 evasion closed: reasons must differ between two arrivals that
    share a schema but differ in content."""
    records = corpus()
    a = cr.relate_cousin(subject(["AssumeRole", "GetSessionToken", "ListBuckets"]), records)
    b = cr.relate_cousin(subject(["SELECT", "INSERT"]), records)
    assert set(a.uncertainty_reasons) != set(b.uncertainty_reasons)


def test_label_is_advisory_only():
    """N1: bands are derived for humans and gate nothing."""
    assert cr.derive_label(0.0) == "SAME"
    assert cr.derive_label(None) == "UNCOMPUTED"
    assert cr.derive_label(0.99) == "UNRELATED"
