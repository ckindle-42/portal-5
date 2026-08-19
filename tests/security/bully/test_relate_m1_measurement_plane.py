"""M.1 -- measurement plane, scoped: an unscored investigation is excluded
from accuracy, not counted wrong; shuffled labels collapse the score; two
sources in one lineage set cannot corroborate."""

from __future__ import annotations

from portal.modules.security.core.bully import measurement
from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.data_plane import (
    AccessPolicy,
    CapabilityProfile,
    EntityLink,
    QualityReport,
    SourceProfile,
    SourceSchema,
    TimeBinding,
    VolumeStrategy,
)


def _eligible_relation():
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["proc_create", "net_connect"]},
        techniques=("T1059",),
    )
    signature = sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    return relation_mod.relate(signature, lib), lib


def _unscored_relation():
    """Matches a SYSTEM_GENERATED, unreviewed anchor -- a real SAME/SIMILAR
    match, but not one that can ground a score."""
    lib = AnchorLibrary()
    lib.load_confirmed_finding(
        source_id="observed-mode",
        record={"action_sequence": ["proc_create", "net_connect"]},
        outcome="ESCALATE",
        analyst_confirmed=False,
    )
    signature = sig_mod.build_signature(
        {"target_host": "host1"}, {"action_sequence": ["proc_create", "net_connect"]}
    )
    return relation_mod.relate(signature, lib), lib


def test_unscored_investigation_excluded_from_accuracy_not_counted_wrong():
    eligible, eligible_lib = _eligible_relation()
    unscored, unscored_lib = _unscored_relation()

    assert measurement.score_eligible(eligible, eligible_lib) is True
    assert measurement.score_eligible(unscored, unscored_lib) is False

    rows = [
        (eligible, eligible_lib, eligible.verdict),  # ground truth matches -> correct
        (unscored, unscored_lib, "__never_matches__"),  # would tank accuracy if wrongly scored
    ]
    report = measurement.compute_accuracy(rows)
    assert report.scored_count == 1
    assert report.unscored_count == 1
    assert report.accuracy == 1.0  # the unscored "wrong" row never counted


def test_shuffled_labels_collapse_the_score():
    from types import SimpleNamespace

    _, lib = _eligible_relation()
    eligible_anchor_id = next(a.anchor_id for a in lib.all() if a.kind == "attack_episode")
    verdict_cycle = ["SAME", "SIMILAR", "NEW", "ANOMALOUS_UNCLASSIFIED"]
    rows = []
    for i in range(20):
        verdict = verdict_cycle[i % len(verdict_cycle)]
        fake_relation = SimpleNamespace(
            verdict=verdict, assessment=SimpleNamespace(reference_signature_id=eligible_anchor_id)
        )
        rows.append((fake_relation, lib, verdict))  # ground truth == prediction -> perfect

    real_accuracy, shuffled_accuracy = measurement.shuffled_label_control(rows, seed=42)
    assert real_accuracy == 1.0
    assert shuffled_accuracy is not None
    assert shuffled_accuracy < real_accuracy


def test_two_sources_in_one_lineage_set_cannot_corroborate():
    groups = measurement.LineageGroups(
        groups={"splunk-hec": "lab-splunk", "splunk-rest": "lab-splunk"}
    )
    assert measurement.corroboration_count(groups, ["splunk-hec", "splunk-rest"]) == 1
    assert measurement.corroboration_count(groups, ["splunk-hec", "edr-feed"]) == 2


def _profile(source_id: str, *, comparable: bool, entity_links=()) -> SourceProfile:
    schema = SourceSchema(source_id, 1, (), 1.0, "fp")
    time_binding = TimeBinding(source_id, "ts", "epoch", "UTC", "s", 0.0, "none", comparable)
    return SourceProfile(
        source_id=source_id,
        mode="ingest",
        schema=schema,
        bindings=(),
        time_binding=time_binding,
        capabilities=CapabilityProfile(True, True, True, True, True, True, True, True),
        entity_links=entity_links,
        volume=VolumeStrategy("indexed", 1.0, 0.0, 0.0, 0.0, "none", "none"),
        quality=QualityReport(0.0, {}, 0, 0, 0.0, "A"),
        access=AccessPolicy(),
        record_count=1,
        profile_version="v1",
    )


def test_pairwise_timeline_and_entity_properties_are_not_global_scalars():
    a = _profile("edr", comparable=True)
    b = _profile("splunk", comparable=True)
    assert measurement.pairwise_timeline_comparable(a, b) is True
    assert measurement.pairwise_entity_linkable(a, b) is False  # no EntityLink declared

    link = EntityLink("edr", "host1", "splunk", "host1", 0.9, "hostname", "manual")
    a_linked = _profile("edr", comparable=True, entity_links=(link,))
    assert measurement.pairwise_entity_linkable(a_linked, b) is True
