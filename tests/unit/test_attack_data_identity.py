from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.security.core.review_eval.item_identity import attack_data_test_id
from portal.modules.security.core.review_eval.mixed import labels_from_attack_data
from scripts.corpus_reingest import p5_item_id, read_attack_data
from scripts.load_attack_data_anchors import _anchor_id_for_episode


def _episode_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "attack_data"
    episode = root / "datasets" / "apt_simulations" / "Example"
    episode.mkdir(parents=True)
    (episode / "data.yml").write_text(
        "mitre_technique:\n- T1003.001\ndatasets:\n- path: episode.log\n  sourcetype: XmlWinEventLog\n",
        encoding="utf-8",
    )
    (episode / "episode.log").write_text("event\n", encoding="utf-8")
    return root, root / "datasets", episode


def test_attack_data_test_id_normalizes_both_root_forms(tmp_path: Path) -> None:
    root, datasets_root, episode = _episode_tree(tmp_path)

    from_checkout_root = attack_data_test_id(episode, root)
    from_datasets_root = attack_data_test_id(episode, datasets_root)

    assert from_checkout_root == "datasets/apt_simulations/Example"
    assert from_datasets_root == from_checkout_root


def test_attack_data_test_id_rejects_a_root_without_datasets(tmp_path: Path) -> None:
    _, _, episode = _episode_tree(tmp_path)

    with pytest.raises(ValueError, match="checkout directory containing datasets/"):
        attack_data_test_id(episode, tmp_path)


def test_ingest_anchor_and_harness_share_episode_namespace(tmp_path: Path) -> None:
    root, datasets_root, episode = _episode_tree(tmp_path)

    ingest_item = read_attack_data(root)[0]
    datasets_root_item = read_attack_data(datasets_root)[0]
    expected_test_id = "datasets/apt_simulations/Example"
    expected_item_id = p5_item_id("attack_data", expected_test_id)

    assert ingest_item.test_id == expected_test_id
    assert datasets_root_item.test_id == expected_test_id
    assert _anchor_id_for_episode(episode, datasets_root) == f"an-{expected_item_id}"
    assert _anchor_id_for_episode(episode, root) == f"an-{expected_item_id}"

    from_checkout_root = labels_from_attack_data(
        root,
        corpus="labelled_corpus",
        publisher="attack_data",
        item_id=p5_item_id,
    )
    from_datasets_root = labels_from_attack_data(
        datasets_root,
        corpus="labelled_corpus",
        publisher="attack_data",
        item_id=p5_item_id,
    )

    assert from_checkout_root[0].dataset_key == f"labelled_corpus/{expected_item_id}"
    assert from_datasets_root[0].dataset_key == from_checkout_root[0].dataset_key
