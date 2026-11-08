"""Offline tests for the labelled_corpus answer key: leak filter and entity ranking."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.bully import corpus_bed
from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry
from portal.modules.security.core.review_eval.corpus_truth import (
    LABELLED_CORPUS_INDEX,
    LEAK_WHERE,
    EntityCandidate,
    behaviour_spine,
    derive_labelled_corpus_truth,
    load,
    rank_entity_pairs,
    raw_leaks_label,
    select_pairs,
)
from portal.modules.security.core.review_eval.truth import derive_bots_truth
from scripts.corpus_reingest import p5_item_id
from scripts.corpus_truth_key import _clean_pairs, candidates_for, load_attack_items


def _pair(
    host: str,
    artifact: str,
    *,
    cooccurrence: int = 4,
    host_corpus: int = 10,
    artifact_corpus: int = 6,
    host_days: int = 1,
    artifact_days: int = 1,
    host_term_indexed: bool = True,
    artifact_term_indexed: bool = True,
) -> EntityCandidate:
    return EntityCandidate(
        host,
        artifact,
        cooccurrence,
        host_corpus,
        artifact_corpus,
        host_days,
        artifact_days,
        host_term_indexed,
        artifact_term_indexed,
    )


def test_raw_leaks_label_scans_technique_ids_and_red_team_names() -> None:
    assert not raw_leaks_label(r"Image=C:\Tools\procdump.exe Computer=win-host")
    assert raw_leaks_label("CommandLine=dump T1003.001 lsass")
    assert raw_leaks_label("path attack_techniques/T1059/atomic")
    assert raw_leaks_label("tool AtomicRedTeam")
    assert raw_leaks_label("Atomic Red Team test")
    assert raw_leaks_label("atomic_red_team/T1003")
    assert raw_leaks_label("StratusRedTeam")
    assert raw_leaks_label("Stratus Red Team")
    assert raw_leaks_label("stratus_red_team")
    assert not raw_leaks_label("NOT1059 powershell.exe")
    assert not raw_leaks_label("")
    assert LEAK_WHERE.startswith("where NOT (")
    assert "_raw" in LEAK_WHERE
    assert r'match(_raw, "\bT\d{4}(\.\d{3})?\b")' in LEAK_WHERE
    assert "atomic" in LEAK_WHERE and "stratus" in LEAK_WHERE


def test_clean_pairs_reduces_windows_paths_to_basenames() -> None:
    class _Probe:
        def rows(self, search: str, start: float, end: float | None = None) -> list[dict[str, str]]:
            assert "p5_item=item1" in search
            assert start == 1_604_361_600.0
            return [
                {
                    "host_entity": "win-host",
                    "artifact": r"C:\Windows\System32\procdump.exe",
                    "cooccur": "4",
                },
                {
                    "host_entity": "win-host",
                    "artifact": r"C:\Tools\procdump.exe",
                    "cooccur": "2",
                },
            ]

    pairs = _clean_pairs(_Probe(), "item1", "XmlWinEventLog", 1_604_361_600)  # type: ignore[arg-type]
    assert pairs == [("win-host", "procdump.exe", 6)]


def test_rank_prefers_rare_cooccurring_artifact_over_a_common_binary() -> None:
    rare = _pair("win-host", "procdump.exe", cooccurrence=4, host_corpus=10, artifact_corpus=6)
    common = _pair(
        "win-host", "powershell.exe", cooccurrence=200, host_corpus=10, artifact_corpus=50_000
    )
    ranked = rank_entity_pairs([common, rare], sensor_days=100)
    assert ranked[0].artifact == "procdump.exe"


def test_rank_drops_entities_present_on_every_sensor_day() -> None:
    background = _pair("win-host", "procdump.exe", host_days=100, artifact_days=1)
    assert rank_entity_pairs([background], sensor_days=100) == ()
    assert rank_entity_pairs([background], sensor_days=1)[0].artifact == "procdump.exe"


def test_rank_skips_unindexed_terms_label_leaks_and_used_sets() -> None:
    unindexed = _pair("win-host", "procdump.exe", artifact_term_indexed=False)
    leaked = _pair("win-host", "T1003.001.exe")
    red_team = _pair("AtomicRedTeam", "procdump.exe")
    assert rank_entity_pairs([unindexed, leaked, red_team], sensor_days=10) == ()
    rare = _pair("win-host", "procdump.exe")
    used = {frozenset({"win-host", "procdump.exe"})}
    assert rank_entity_pairs([rare], sensor_days=10, used_sets=used) == ()


def test_select_pairs_does_not_reuse_an_entity_set() -> None:
    shared = _pair("win-host", "procdump.exe", artifact_corpus=2)
    other = _pair("win-host", "mal.ps1", artifact_corpus=3)
    chosen = select_pairs(
        {"T1003.001": [shared, other], "T1059.001": [shared, other]},
        {"T1003.001": 10, "T1059.001": 10},
        ("T1003.001", "T1059.001"),
    )
    first = frozenset(
        {chosen["T1003.001"].host.casefold(), chosen["T1003.001"].artifact.casefold()}
    )
    second = frozenset(
        {chosen["T1059.001"].host.casefold(), chosen["T1059.001"].artifact.casefold()}
    )
    assert first != second
    assert chosen["T1003.001"].artifact == "procdump.exe"
    assert chosen["T1059.001"].artifact == "mal.ps1"


def test_behaviour_spine_classifies_a_sysmon_record() -> None:
    records = [
        {
            "_raw": "<Channel>Microsoft-Windows-Sysmon/Operational</Channel><EventID>1</EventID>",
            "EventID": "1",
        }
    ]
    assert behaviour_spine(records, "XmlWinEventLog") == ("execute",)
    assert behaviour_spine([{"_raw": "noise", "EventID": "1"}], "raw") == ()


def test_resolve_indexes_keeps_portal5_lab_and_adds_labelled_corpus() -> None:
    indexes = corpus_bed.resolve_indexes()
    assert indexes[0] == corpus_bed.CORPUS_INDEX
    assert "labelled_corpus" in indexes
    lane_b = [lane.index for lane in corpus_bed.LANES if lane.lane == "B"]
    assert corpus_bed.CORPUS_INDEX in lane_b
    assert LABELLED_CORPUS_INDEX in lane_b


def test_catalog_joins_data_yml_technique_to_p5_item(tmp_path: Path) -> None:
    folder = tmp_path / "datasets" / "attack_techniques" / "T1003.001" / "atomic_red_team"
    folder.mkdir(parents=True)
    (folder / "atomic_red_team.yml").write_text(
        "mitre_technique:\n- T1003.001\ndatasets:\n- path: windows-sysmon.log\n  sourcetype: XmlWinEventLog\n",
        encoding="utf-8",
    )
    mixed = tmp_path / "datasets" / "attack_techniques" / "T1003.001" / "mixed"
    mixed.mkdir()
    (mixed / "data.yml").write_text(
        "mitre_technique:\n- T1003.001\n- T1059.001\ndatasets:\n- path: mixed.log\n  sourcetype: XmlWinEventLog\n",
        encoding="utf-8",
    )
    items = load_attack_items(tmp_path)
    chosen = candidates_for(items, "T1003.001")
    assert len(chosen) == 1
    assert chosen[0].techniques == frozenset({"T1003.001"})
    assert chosen[0].p5_item == p5_item_id("attack_data", chosen[0].test_id)
    assert chosen[0].test_id.endswith("atomic_red_team")


def test_load_requires_provenance_and_labelled_corpus(tmp_path: Path) -> None:
    path = tmp_path / "corpus_truth_key.json"
    path.write_text(
        '{"provenance": {"index": "labelled_corpus", "rule": "rarity"}, "entries": []}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load(path)
    path.write_text(
        """{"provenance": {"index": "botsv1", "rule": "rarity"},
        "entries": [{"dataset": "botsv1", "technique": "T1003.001", "entities": ["h", "a.exe"],
        "sourcetypes": ["XmlWinEventLog"]}]}""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load(path)


def test_labelled_corpus_truth_matches_all_entities_and_rejects_other_indexes() -> None:
    entry = AnswerKeyEntry(
        dataset="labelled_corpus",
        technique="T1003.001",
        behavioural_spine=("execute",),
        entities=("win-host", "procdump.exe"),
        sourcetypes=("XmlWinEventLog",),
    )
    bots = AnswerKeyEntry(
        dataset="botsv3",
        technique="T1000",
        behavioural_spine=(),
        entities=("win-host", "procdump.exe"),
        sourcetypes=("XmlWinEventLog",),
    )

    def unused(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("not called")

    with pytest.raises(ValueError):
        derive_labelled_corpus_truth(unused, unused, entries=[bots])
    with pytest.raises(ValueError):
        derive_bots_truth(unused, unused, entries=[entry])

    both = {
        "_time": 100.0,
        "_raw": "Computer=win-host Image=procdump.exe",
        "index": "labelled_corpus",
        "sourcetype": "XmlWinEventLog",
    }
    only_artifact = {
        "_time": 120.0,
        "_raw": "Image=procdump.exe",
        "index": "labelled_corpus",
        "sourcetype": "XmlWinEventLog",
    }

    def fetch(*_args: Any) -> list[dict[str, Any]]:
        return [only_artifact, both]

    def days(_index: str, _sourcetype: str, entities: tuple[str, ...]) -> dict[float, int]:
        if entities == ("win-host", "procdump.exe"):
            return {0.0: 1}
        return {0.0: 1}

    derived = derive_labelled_corpus_truth(fetch, unused, entries=[entry], query_days=days)
    assert derived.receipts[0].status == "derived"
    assert derived.receipts[0].event_count == 1
    assert len(derived.items[0].event_ids) == 1
