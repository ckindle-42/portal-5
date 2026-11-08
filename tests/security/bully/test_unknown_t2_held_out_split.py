"""T.2 -- held-out split ends seed/anchor contamination (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import unit_measurement as um


def test_split_is_disjoint_and_deterministic():
    keys = [f"dataset-{i}" for i in range(20)]
    split_a = um.split_datasets(keys, seed=42)
    split_b = um.split_datasets(keys, seed=42)
    assert split_a.type_dataset_keys == split_b.type_dataset_keys
    assert not (split_a.type_dataset_keys & split_a.eval_dataset_keys)
    assert split_a.type_dataset_keys | split_a.eval_dataset_keys == set(keys)


def test_held_out_split_rejects_overlap_directly():
    with pytest.raises(um.ContaminationError):
        um.HeldOutSplit(
            type_dataset_keys=frozenset({"a", "b"}), eval_dataset_keys=frozenset({"b", "c"})
        )


def test_seeded_violation_unsplit_run_is_detected_and_fails():
    """An 'unsplit' run: every evaluation dataset is also a type dataset
    (the exact defect -- attack_data seeds from the same root that built
    the anchors). assert_no_contamination must raise, not pass silently."""
    keys = [f"dataset-{i}" for i in range(6)]
    unsplit = um.HeldOutSplit(type_dataset_keys=frozenset(keys), eval_dataset_keys=frozenset())
    with pytest.raises(um.ContaminationError):
        um.assert_no_contamination(keys, unsplit)


def test_clean_evaluation_set_passes():
    split = um.split_datasets([f"dataset-{i}" for i in range(10)], seed=1)
    um.assert_no_contamination(list(split.eval_dataset_keys), split)  # must not raise


def test_component_grouped_split_keeps_shared_techniques_together():
    techniques_by_key = {
        "ep-a": {"T1059", "T1003"},
        "ep-b": {"T1059"},
        "ep-c": {"T1003"},
        "ep-d": {"T1082"},
        "ep-e": {"T1027"},
    }
    groups = um.technique_component_groups(techniques_by_key)
    assert groups["ep-a"] == groups["ep-b"] == groups["ep-c"]
    assert groups["ep-d"] != groups["ep-a"]
    split = um.split_grouped_datasets(
        list(techniques_by_key), group_of=groups, type_fraction=0.5, seed=0
    )

    assert len(split.type_dataset_keys) == 3
    type_groups = {groups[key] for key in split.type_dataset_keys}
    eval_groups = {groups[key] for key in split.eval_dataset_keys}
    assert type_groups.isdisjoint(eval_groups)
    assert split.type_dataset_keys | split.eval_dataset_keys == set(techniques_by_key)


def test_component_split_leak_measurement_repeats_for_seed_and_input_order():
    techniques_by_key = {
        "ep-a": {"T1059", "T1003"},
        "ep-b": {"T1059"},
        "ep-c": {"T1003"},
        "ep-d": {"T1082"},
        "ep-e": {"T1027"},
    }
    groups = um.technique_component_groups(techniques_by_key)
    first = um.split_grouped_datasets(
        list(techniques_by_key), group_of=groups, type_fraction=0.5, seed=17
    )
    second = um.split_grouped_datasets(
        list(reversed(techniques_by_key)), group_of=groups, type_fraction=0.5, seed=17
    )

    assert first == second
    assert um.measure_technique_split(first, techniques_by_key) == um.measure_technique_split(
        second, techniques_by_key
    )
    assert um.measure_technique_split(first, techniques_by_key).leak_episode_count == 0
