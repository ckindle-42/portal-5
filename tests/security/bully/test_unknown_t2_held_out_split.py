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
