"""Answer-key truth is derived from entity-matched source records, not engine output."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry
from portal.modules.security.core.review.intake import event_id_for
from portal.modules.security.core.review_eval.captures import (
    _known_answer_fixture,
    certify_capture_store,
)
from portal.modules.security.core.review_eval.truth import (
    EntitySearchStat,
    benign_interval_candidates,
    derive_bots_truth,
    derive_capture_truth,
)


def entry(*, entities: tuple[str, ...] = ("host-a", "user-a")) -> AnswerKeyEntry:
    return AnswerKeyEntry(
        dataset="botsv3",
        technique="T1000",
        behavioural_spine=("auth",),
        entities=entities,
        sourcetypes=("wineventlog:security",),
    )


def test_truth_uses_product_event_ids_and_requires_every_answer_key_entity() -> None:
    records = [
        {
            "_time": 100.0,
            "_raw": "Computer=HOST-A Account=user-a EventCode=4624",
            "host": "host-a",
            "source": "wineventlog",
            "index": "botsv3",
            "sourcetype": "wineventlog:security",
        },
        {
            "_time": 110.0,
            "_raw": "Computer=host-a Account=user-a EventCode=4624",
            "host": "host-a",
            "source": "wineventlog",
            "index": "botsv3",
            "sourcetype": "wineventlog:security",
        },
    ]

    def fetch(
        index: str,
        sourcetype: str,
        _entities: Sequence[str],
        start: float,
        end: float,
    ) -> list[dict[str, Any]]:
        assert (index, sourcetype) == ("botsv3", "wineventlog:security")
        assert (start, end) == (100.0, 110.000001)
        return records

    def stats(_index: str, _sourcetype: str, _entities: Sequence[str]) -> EntitySearchStat:
        return EntitySearchStat(2, 100.0, 110.0)

    derived = derive_bots_truth(fetch, stats, entries=[entry()])
    assert len(derived.items) == 1
    assert derived.items[0].klass == "known"
    assert derived.items[0].event_ids == tuple(
        sorted(event_id_for("botsv3:wineventlog:security", row) for row in records)
    )
    receipt = derived.receipts[0]
    assert receipt.status == "derived" and receipt.event_count == 2
    assert (receipt.start_epoch, receipt.end_exclusive_epoch) == (100.0, 110.000001)
    assert receipt.expected_entity_count == receipt.located_entity_count == 2
    assert len(receipt.entity_tokens) == 2


def test_truth_drops_partial_entity_matches_with_a_receipt() -> None:
    record = {
        "_time": 100.0,
        "_raw": "Computer=host-a EventCode=4624",
        "host": "host-a",
        "index": "botsv3",
        "sourcetype": "wineventlog:security",
    }

    def fetch(
        _index: str, _sourcetype: str, _entities: Sequence[str], _start: float, _end: float
    ) -> list[dict[str, Any]]:
        return [record]

    def stats(_index: str, _sourcetype: str, entities: Sequence[str]) -> EntitySearchStat:
        if len(entities) == 1 and entities[0] == "user-a":
            return EntitySearchStat(0, None, None)
        return EntitySearchStat(1, 100.0, 100.0)

    derived = derive_bots_truth(fetch, stats, entries=[entry()])
    assert derived.items == ()
    receipt = derived.receipts[0]
    assert receipt.status == "dropped"
    assert receipt.reason == "answer_key_entity_count_mismatch"
    assert receipt.expected_entity_count == 2 and receipt.located_entity_count == 1
    assert receipt.event_count == 1 and receipt.start_epoch == 100.0


def test_entity_matching_does_not_confuse_a_host_prefix_with_another_entity() -> None:
    record = {
        "_time": 100.0,
        "_raw": "Computer=BSTOLL-L EventCode=4624",
        "host": "BSTOLL-L",
        "index": "botsv3",
        "sourcetype": "wineventlog:security",
    }

    def fetch(
        _index: str, _sourcetype: str, _entities: Sequence[str], _start: float, _end: float
    ) -> list[dict[str, Any]]:
        return [record]

    def stats(_index: str, _sourcetype: str, entities: Sequence[str]) -> EntitySearchStat:
        if len(entities) == 1 and entities[0] == "bstoll":
            return EntitySearchStat(0, None, None)
        return EntitySearchStat(1, 100.0, 100.0)

    derived = derive_bots_truth(fetch, stats, entries=[entry(entities=("BSTOLL-L", "bstoll"))])
    assert derived.items == ()
    assert derived.receipts[0].located_entity_count == 1


def test_duplicate_answer_key_techniques_get_distinct_item_ids() -> None:
    first, second = entry(), entry(entities=("host-b", "user-b"))

    def fetch(
        _index: str, _sourcetype: str, _entities: Sequence[str], start: float, end: float
    ) -> list[dict[str, Any]]:
        return [
            {
                "_time": start,
                "_raw": "Computer=host-a Account=user-a Computer=host-b Account=user-b",
                "host": "host-a",
                "index": "botsv3",
                "sourcetype": "wineventlog:security",
            }
        ]

    def stats(_index: str, _sourcetype: str, _entities: Sequence[str]) -> EntitySearchStat:
        return EntitySearchStat(1, 100.0, 100.0)

    result = derive_bots_truth(fetch, stats, entries=[first, second])
    assert len(result.items) == 2
    assert result.items[0].item_id != result.items[1].item_id


def test_benign_interval_candidates_exclude_attack_day_and_margin() -> None:
    day = 86_400.0
    assert benign_interval_candidates(
        0.0,
        4 * day,
        [(day + 3600.0, day + 7200.0)],
        margin_seconds=3600.0,
        duration_seconds=day / 2,
    ) == ((0.0, day / 2), (2 * day, 2.5 * day))


def test_capture_truth_uses_only_the_hashed_admitted_population(tmp_path: Any) -> None:
    capture, _source = _known_answer_fixture()
    capture["target_host"] = "fixture-host"
    capture_path = tmp_path / "capture-fixture.json"
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    manifest = certify_capture_store(tmp_path, stamp_digest="test-stamp")

    population = derive_capture_truth(tmp_path, manifest)

    assert population.admitted_capture_count == 1
    assert population.admission_manifest_sha256 == manifest["admission_manifest_sha256"]
    assert len(population.items) == 1
    assert population.items[0].klass in {"cousin", "novel"}
    assert population.items[0].event_ids
    assert sum(map(len, population.records_by_source.values())) == len(
        population.items[0].event_ids
    )
    assert "_raw" in next(iter(population.records_by_source.values()))[0]


DAY = 86_400.0


def _day_scoped(
    days: dict[tuple[str, ...], dict[float, int]],
    records: list[dict[str, Any]],
) -> tuple[Any, list[tuple[float, float]]]:
    fetched: list[tuple[float, float]] = []

    def fetch(
        _index: str, _sourcetype: str, _entities: Sequence[str], start: float, end: float
    ) -> list[dict[str, Any]]:
        fetched.append((start, end))
        return [row for row in records if start <= row["_time"] < end]

    def stats(_index: str, _sourcetype: str, _entities: Sequence[str]) -> EntitySearchStat:
        raise AssertionError("the day-scoped span never reads whole-index stats")

    def query_days(_index: str, _sourcetype: str, entities: Sequence[str]) -> dict[float, int]:
        return days.get(tuple(entities), {})

    derived = derive_bots_truth(
        fetch, stats, entries=[entry(entities=("web.example", "10.0.0.5"))], query_days=query_days
    )
    return derived, fetched


def _http(when: float, raw: str) -> dict[str, Any]:
    return {
        "_time": when,
        "_raw": raw,
        "host": "web",
        "source": "stream",
        "index": "botsv3",
        "sourcetype": "wineventlog:security",
    }


def test_day_scoped_span_ignores_an_entity_that_is_everyday_background() -> None:
    # The server address appears every day; the attacked name only on day 10. The entry is day 10.
    records = [_http(d * DAY + 60, "dst=10.0.0.5") for d in range(28)]
    records.append(_http(10 * DAY + 120, "Host: web.example dst=10.0.0.5"))
    days = {
        ("web.example",): {10 * DAY: 1},
        ("10.0.0.5",): {d * DAY: 1 + (d == 10) for d in range(28)},
        ("web.example", "10.0.0.5"): {d * DAY: 1 + (d == 10) for d in range(28)},
    }
    derived, fetched = _day_scoped(days, records)
    receipt = derived.receipts[0]
    assert receipt.status == "derived"
    assert (receipt.start_epoch, receipt.end_exclusive_epoch) == (10 * DAY, 11 * DAY)
    assert fetched == [(10 * DAY, 11 * DAY)]
    assert receipt.event_count == 2


def test_day_scoped_span_drops_entities_that_never_share_a_day() -> None:
    days = {
        ("web.example",): {3 * DAY: 1},
        ("10.0.0.5",): {4 * DAY: 1},
        ("web.example", "10.0.0.5"): {3 * DAY: 1, 4 * DAY: 1},
    }
    derived, fetched = _day_scoped(days, [])
    receipt = derived.receipts[0]
    assert receipt.status == "dropped"
    assert receipt.reason == "answer_key_entities_share_no_utc_day"
    assert fetched == []
