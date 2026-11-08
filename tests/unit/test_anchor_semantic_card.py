"""Anchor cards must be semantic: the publisher's description, not a file path.

Lane anchor-semantic-card: every attack_episode anchor embedded near-identical
path boilerplate (``attack_data:datasets/... techniques=T…``), so the
known_similar channel compared one path string against another. These tests pin
the card to the publisher's own description, carry ``description``/``steps``
onto the anchor record, keep provenance as fields, and keep the path card as
the fallback when no manifest description exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from portal.modules.security.core.review.store import ReviewStore
from scripts.corpus_ingest import ManifestDataset
from scripts.load_attack_data_anchors import episode_card, load_episodes


def _write_episode(
    datasets: Path,
    name: str,
    technique: str,
    description: str | None,
    command: str,
) -> None:
    episode = datasets / name
    episode.mkdir(parents=True)
    lines = [
        "mitre_technique:",
        f"- {technique}",
        "datasets:",
        f"- path: {name}.log",
        "  sourcetype: XmlWinEventLog",
    ]
    if description is not None:
        lines.insert(2, f"description: {json.dumps(description)}")
    (episode / "data.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    record = json.dumps({"CommandLine": command}) + "\n"
    (episode / f"{name}.log").write_text(record, encoding="utf-8")


def _fixture_root(tmp_path: Path) -> Path:
    """Two genuinely different attacks plus one manifest with no description."""
    datasets = (tmp_path / "attack_data") / "datasets"
    _write_episode(
        datasets,
        "ep_lsass",
        "T1003.001",
        "Atomic Test Results: Successful Execution of test T1003.001-1 "
        "Dump LSASS.exe Memory using ProcDump",
        "procdump.exe -ma lsass.exe dump.dmp",
    )
    _write_episode(
        datasets,
        "ep_task",
        "T1053.005",
        "Create a scheduled task on a remote host that runs whoami every day",
        "schtasks.exe /create /tn whoami_task /tr whoami.exe /sc daily",
    )
    _write_episode(datasets, "ep_nodisc", "T1001", None, "whoami.exe")
    return datasets.parent


def _records_by_episode(store: ReviewStore) -> dict[str, dict[str, Any]]:
    return {row.record["file"].split("/")[1]: row.record for row in store.anchors()}


def test_cards_embed_the_description_and_differ_beyond_the_path(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    store = ReviewStore(path=tmp_path / "store.sqlite3")
    try:
        report = load_episodes(root, store, type_fraction=1.0, check_fn=lambda keys, split: None)
        records = _records_by_episode(store)
    finally:
        store.close()
    assert report["anchors_stored"] == 3

    lsass, task = records["ep_lsass"], records["ep_task"]
    # The card is what gets embedded: it must carry the attack, not the path.
    assert "Dump LSASS.exe Memory using ProcDump" in lsass["card"]
    assert "Create a scheduled task" in task["card"]

    def body(card: str) -> set[str]:
        return set(re.findall(r"[a-z]{3,}", card.lower()))

    # Two different attacks' cards differ in more than their path tokens.
    assert body(lsass["card"]) - body(task["card"])
    assert body(task["card"]) - body(lsass["card"])

    # description and steps travel onto the record as fields.
    assert lsass["description"].startswith("Atomic Test Results:")
    assert [step["text"] for step in lsass["steps"]] == ["Dump LSASS.exe Memory using ProcDump"]
    assert lsass["steps"][0]["step_id"] == "T1003.001-1"
    assert lsass["steps"][0]["outcome"] == "successful"

    # Provenance stays in fields, untouched.
    assert lsass["file"] == "datasets/ep_lsass/ep_lsass.log"
    assert lsass["technique_ids"] == ["T1003.001"]
    assert lsass["sourcetype"] == "XmlWinEventLog"


def test_episode_without_description_keeps_the_path_card(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    store = ReviewStore(path=tmp_path / "store.sqlite3")
    try:
        report = load_episodes(root, store, type_fraction=1.0, check_fn=lambda keys, split: None)
        records = _records_by_episode(store)
    finally:
        store.close()
    assert report["anchors_stored"] == 3

    nodisc = records["ep_nodisc"]
    assert nodisc["description"] is None
    assert nodisc["steps"] == []
    assert nodisc["card"] == ("attack_data:datasets/ep_nodisc/ep_nodisc.log techniques=T1001")


def _item(path: str, description: str | None) -> ManifestDataset:
    return ManifestDataset(
        path=Path(path),
        sourcetype=None,
        source=None,
        dataset_epoch=None,
        techniques=("T1003.001",),
        mapped_sourcetype="windows:event",
        manifest=Path(path).parent / "data.yml",
        description=description,
    )


def test_distinct_manifest_descriptions_are_joined_in_order() -> None:
    items = [
        _item("datasets/ep/a.log", "Dump LSASS memory with procdump"),
        _item("datasets/ep/b.log", "Mirror the registry hives of the host"),
    ]
    card = episode_card(items, "datasets/ep/a.log", ("T1003.001",))
    assert "Dump LSASS memory with procdump" in card
    assert "Mirror the registry hives of the host" in card
    assert card.index("Dump LSASS") < card.index("Mirror the registry")


def test_repeated_dataset_entries_collapse_to_one_description() -> None:
    items = [
        _item("datasets/ep/a.log", "Dump LSASS memory with procdump"),
        _item("datasets/ep/b.log", "Dump LSASS memory with procdump"),
    ]
    card = episode_card(items, "datasets/ep/a.log", ("T1003.001",))
    assert card.count("Dump LSASS memory with procdump") == 1


def test_no_description_falls_back_to_the_provenance_path_card() -> None:
    items = [_item("datasets/ep/a.log", None)]
    card = episode_card(items, "datasets/ep/a.log", ("T1003.001", "T1003.002"))
    assert card == "attack_data:datasets/ep/a.log techniques=T1003.001,T1003.002"
