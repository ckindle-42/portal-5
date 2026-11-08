"""Loader contamination guard: eval-half episode anchors must never enter the store.

TASK_BULLY_REAL_TELEMETRY_V1 T.2 -- attack_data seeds drawn from the same dataset
root that built the anchors are already "in the library" before evaluation starts,
unless `split_datasets` separates them and `assert_no_contamination` refuses to
let them cross. This test verifies the loader enforces that wall.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import unit_measurement as um


def test_contamination_guard_raises_when_eval_half_is_in_type_half():
    """Storing an eval-half episode anchor through the loader must raise via
    ``assert_no_contamination``, not silently contaminate the store."""
    from scripts.load_attack_data_anchors import check_split_and_assert_no_contamination

    # Simulate a contaminated split: the same dataset key appears in both halves.
    split = um.HeldOutSplit(
        type_dataset_keys=frozenset({"ep-a", "ep-b", "ep-c"}),
        eval_dataset_keys=frozenset({"ep-d"}),
    )
    # But then we feed eval keys that overlap the type half through the guard.
    contaminated_eval_keys = ["ep-b", "ep-d"]
    with pytest.raises(um.ContaminationError, match="eval.*also contributed"):
        check_split_and_assert_no_contamination(contaminated_eval_keys, split)


def test_clean_eval_split_passes_contamination_check():
    """A properly held-out split must not raise on the same call."""
    keys = [f"ep-{i}" for i in range(10)]
    split = um.split_datasets(keys, seed=0)
    um.assert_no_contamination(list(split.eval_dataset_keys), split)  # must not raise


def test_unsplit_run_is_detected_as_contaminated():
    """An unsplit run (all keys in type half, none in eval) must also raise."""
    from scripts.load_attack_data_anchors import check_split_and_assert_no_contamination

    keys = [f"ep-{i}" for i in range(6)]
    unsplit = um.HeldOutSplit(
        type_dataset_keys=frozenset(keys),
        eval_dataset_keys=frozenset(),
    )
    with pytest.raises(um.ContaminationError):
        check_split_and_assert_no_contamination(keys, unsplit)
