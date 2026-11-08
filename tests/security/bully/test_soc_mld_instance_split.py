"""SOC-MLD attack-instance split holds instances, not labels, disjoint."""

from __future__ import annotations

from portal.modules.security.core.bully import unit_measurement as um


def test_attack_instance_id_is_source_and_120s_floor():
    assert um.attack_instance_id("192.168.70.132", 250.0) == "ATT_192.168.70.132_2"
    assert um.attack_instance_id("192.168.70.132", 0.0) == "ATT_192.168.70.132_0"
    assert um.session_id("192.168.70.132", 59.0) == "S_192.168.70.132_1"


def test_split_keeps_each_instance_on_one_side_and_covers_labels():
    labels = {
        "i1": frozenset({"A"}),
        "i2": frozenset({"A"}),
        "i3": frozenset({"B"}),
    }
    split = um.split_attack_instances(labels, test_ratio=0.99, seed=0)
    assert not (split.type_dataset_keys & split.eval_dataset_keys)
    assert split.type_dataset_keys | split.eval_dataset_keys == set(labels)
    train_labels = set().union(*(labels[key] for key in split.type_dataset_keys))
    assert train_labels == {"A", "B"}


def test_split_is_deterministic_and_does_not_reuse_dataset_half_split():
    labels = {f"inst-{i}": frozenset({f"L{i % 3}"}) for i in range(12)}
    first = um.split_attack_instances(labels, test_ratio=0.2, seed=42)
    second = um.split_attack_instances(labels, test_ratio=0.2, seed=42)
    assert first == second
    dataset_half = um.split_datasets(list(labels), type_fraction=0.5, seed=0)
    assert first.type_dataset_keys != dataset_half.type_dataset_keys


def test_layer_correlation_counts_groups_that_carry_every_required_layer():
    groups = {
        "a": frozenset({"L3/L4", "L7"}),
        "b": frozenset({"L7"}),
        "c": frozenset({"L3/L4", "L7", "NIDS"}),
    }
    report = um.verify_layer_correlation(groups, ("L3/L4", "L7"))
    assert report.group_count == 3
    assert report.covered_group_count == 2
    assert report.covered_fraction == 2 / 3
    assert dict(report.layer_group_counts)["NIDS"] == 1


def test_layer_correlation_of_no_groups_does_not_invent_coverage():
    report = um.verify_layer_correlation({}, ("L3/L4", "L7"))
    assert report.group_count == 0
    assert report.covered_group_count == 0
    assert report.covered_fraction is None


def test_session_overlap_is_empty_when_sessions_nest_in_one_instance():
    split = um.HeldOutSplit(
        type_dataset_keys=frozenset({"inst-a"}),
        eval_dataset_keys=frozenset({"inst-b"}),
    )
    nested = {"inst-a": frozenset({"s1", "s2"}), "inst-b": frozenset({"s3"})}
    assert um.session_overlap(split, nested) == frozenset()
    crossed = {"inst-a": frozenset({"s1"}), "inst-b": frozenset({"s1"})}
    assert um.session_overlap(split, crossed) == frozenset({"s1"})
