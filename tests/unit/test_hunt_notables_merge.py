from __future__ import annotations

import json
import math
from typing import Any

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.__main__ import main
from portal.modules.security.core.hunt.notables.behaviours import collect_behaviours
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.generators import Notable, _make
from portal.modules.security.core.hunt.notables.merge import (
    DEFAULT_MERGE,
    DEFAULT_WEIGHTS,
    RRF_K,
    duplicate_key,
    group_by_generator,
    merge_notables,
)
from portal.modules.security.core.hunt.notables.receipt import write_json
from portal.modules.security.core.hunt.notables.run import judge_stage, notables_stage
from portal.modules.security.core.hunt.notables.sample import SourceFacts

PRIORITY = ("similar_to_known", "alerts", "peer_rare", "deviation", "misfit")


def _notable(generator: str, line: str = "raw", source_id: str = "ix:st") -> Notable:
    return _make(
        generator=generator,
        basis="b",
        what=f"{generator} {line}",
        entities=(),
        source_id=source_id,
        first_seen=0.0,
        last_seen=1.0,
        counts={},
        measure_name="m",
        measure_value=0.0,
        why="w",
        evidence=({"line": line, "query": "q", "earliest": 0.0, "latest": 1.0},),
    )


def test_duplicate_key_names_the_source_and_its_first_evidence_line() -> None:
    assert duplicate_key(_notable("alerts", "L")) == ("ix:st", "L")
    empty = _make(
        generator="alerts",
        basis="b",
        what="w",
        entities=(),
        source_id="ix:st",
        first_seen=0.0,
        last_seen=1.0,
        counts={},
        measure_name="m",
        measure_value=0.0,
        why="w",
        evidence=(),
    )
    assert duplicate_key(empty) is None


def test_blocks_keeps_generator_blocks_in_priority_order() -> None:
    notables = [
        _notable("misfit", "m1"),
        _notable("alerts", "a1"),
        _notable("misfit", "m2"),
        _notable("similar_to_known", "s1"),
    ]
    merged, receipt = merge_notables(notables, PRIORITY, "blocks")
    assert [(item.generator, item.what) for item in merged] == [
        ("similar_to_known", "similar_to_known s1"),
        ("alerts", "alerts a1"),
        ("misfit", "misfit m1"),
        ("misfit", "misfit m2"),
    ]
    assert receipt["groups"] == {"misfit": 2, "alerts": 1, "similar_to_known": 1}
    assert receipt["fused"] == 0


def test_interleave_round_robins_groups_in_priority_order() -> None:
    notables = [
        _notable("peer_rare", "p1"),
        _notable("peer_rare", "p2"),
        _notable("alerts", "a1"),
        _notable("alerts", "a2"),
    ]
    merged, receipt = merge_notables(notables, PRIORITY, "interleave")
    assert [item.what for item in merged] == [
        "alerts a1",
        "peer_rare p1",
        "alerts a2",
        "peer_rare p2",
    ]
    assert receipt["method"] == "interleave"


def test_rrf_fuses_one_finding_raised_by_two_generators_above_a_single_one() -> None:
    notables = [
        _notable("peer_rare", "X"),
        _notable("alerts", "L"),
        _notable("misfit", "L"),
    ]
    merged, receipt = merge_notables(notables, PRIORITY, "rrf")
    assert [item.what for item in merged] == ["alerts L", "peer_rare X"]
    assert receipt["fused"] == 1
    assert receipt["merged"] == 2
    fused_score = 2.0 / (RRF_K + 1)
    single_score = 1.0 / (RRF_K + 1)
    assert fused_score > single_score


def test_rrf_without_duplicates_matches_interleave() -> None:
    notables = [
        _notable("alerts", "a1"),
        _notable("peer_rare", "p1"),
        _notable("alerts", "a2"),
        _notable("misfit", "m1"),
    ]
    rrf, _ = merge_notables(notables, PRIORITY, "rrf")
    inter, _ = merge_notables(notables, PRIORITY, "interleave")
    assert [item.what for item in rrf] == [item.what for item in inter]


def test_rrf_does_not_collapse_notables_without_evidence() -> None:
    notables = [
        _make(
            generator="alerts",
            basis="b",
            what=f"finding {index}",
            entities=(),
            source_id="ix:st",
            first_seen=0.0,
            last_seen=1.0,
            counts={},
            measure_name="m",
            measure_value=0.0,
            why="w",
            evidence=(),
        )
        for index in range(2)
    ]

    merged, receipt = merge_notables(notables, PRIORITY, "rrf")

    assert [item.what for item in merged] == ["finding 0", "finding 1"]
    assert receipt["fused"] == 0


def test_weighted_merge_shares_slots_by_the_measured_weight() -> None:
    notables = [_notable("deviation", f"d{index}") for index in range(3)] + [
        _notable("similar_to_known", f"s{index}") for index in range(3)
    ]

    merged, receipt = merge_notables(
        notables, PRIORITY, "weighted", weights={"similar_to_known": 3, "deviation": 1}
    )

    assert [item.generator for item in merged[:4]] == [
        "similar_to_known",
        "deviation",
        "similar_to_known",
        "similar_to_known",
    ]
    assert receipt["weights"] == {"deviation": 1, "similar_to_known": 3}
    assert receipt["merged"] == 6


def test_weighted_merge_puts_a_zero_weight_generator_after_the_measured_ones() -> None:
    notables = [_notable("peer_rare", "p1"), _notable("deviation", "d1")]

    merged, _receipt = merge_notables(
        notables,
        PRIORITY,
        "weighted",
        weights={"peer_rare": 0, "deviation": 1},
    )

    assert [item.generator for item in merged] == ["deviation", "peer_rare"]


def test_the_default_merge_is_weighted_and_declares_its_weights() -> None:
    assert DEFAULT_MERGE == "weighted"
    notables = [_notable("peer_rare", "p1"), _notable("deviation", "d1")]

    merged, receipt = merge_notables(notables, PRIORITY, DEFAULT_MERGE)

    assert receipt["weights"] == DEFAULT_WEIGHTS
    assert [item.generator for item in merged] == ["deviation", "peer_rare"]


def test_a_generator_outside_the_priority_sorts_last_deterministically() -> None:
    notables = [_notable("zebra", "z1"), _notable("alerts", "a1")]
    merged, _ = merge_notables(notables, ("alerts",), "blocks")
    assert [item.generator for item in merged] == ["alerts", "zebra"]
    groups = group_by_generator(notables, ("alerts",))
    assert [group[0].generator for group in groups] == ["alerts", "zebra"]


class _RowsExecutor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del query, start, end, kind, row_cap
        return Read([dict(row) for row in self.rows], False, None)


def _card() -> SourceCard:
    return SourceCard(
        index="ix",
        sourcetype="st",
        kind="activity",
        roles={"actor": ("user",), "action": ("image",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=0.95,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
    )


def test_the_stage_receipt_declares_every_requested_generator_and_the_merge(tmp_path) -> None:
    rows: list[dict[str, object]] = [
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 1.0, "host": "h1"}
    ] * 200
    rows.append({"_raw": "bash: 196: Bad file descriptor", "_time": 2.0, "host": "h1"})
    collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [_card()],
        {"ix:st": SourceFacts("ix", "st", 201, 100.0, 100.0, ("h1",), 1, ("/s1",), 1)},
        tmp_path / "behaviours.duckdb",
    )
    write_json(tmp_path / "sources.json", {"cards": [_card().as_dict()]})
    _found, receipt = notables_stage(
        index="ix",
        out=tmp_path,
        start=0.0,
        end=7200.0,
        search=_RowsExecutor([]),  # type: ignore[arg-type]
        enabled=["misfit"],
    )
    assert receipt["enabled"] == ["misfit"]
    assert receipt["merge"]["method"] == DEFAULT_MERGE
    assert receipt["merge"]["groups"] == {"misfit": 1}
    stored = [
        json.loads(line)
        for line in (tmp_path / "notables.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [row["generator"] for row in stored] == ["misfit"]


def test_knowledge_flags_without_the_similar_generator_exit_nonzero(tmp_path, capsys) -> None:
    code = main(
        [
            "--index",
            "ix",
            "--out",
            str(tmp_path),
            "--stage",
            "notables",
            "--generators",
            "alerts,peer_rare,deviation,misfit",
            "--knowledge-store",
            str(tmp_path / "knowledge.duckdb"),
        ],
        search=_RowsExecutor([]),  # type: ignore[arg-type]
    )
    assert code == 2
    assert "similar_to_known" in capsys.readouterr().err


class _Client:
    def complete(self, **request: object) -> dict[str, object]:
        del request
        return {
            "model": "seat",
            "usage": {"prompt_tokens": 9},
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "top_logprobs": [
                                    {"token": " yes", "logprob": math.log(0.8)},
                                    {"token": "no", "logprob": math.log(0.2)},
                                ]
                            }
                        ]
                    }
                }
            ],
        }


def _row(generator: str, key: str) -> dict[str, Any]:
    return {
        "notable_id": key,
        "generator": generator,
        "basis": "b",
        "what": "w",
        "entities": [],
        "source_id": "ix:st",
        "why": "w",
        "content_key": key,
        "evidence": [{"line": "example"}],
    }


def test_the_judge_consumes_the_merged_file_order(tmp_path) -> None:
    rows = [_row("misfit", "k1"), _row("similar_to_known", "k2"), _row("alerts", "k3")]
    (tmp_path / "notables.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    judged, receipt = judge_stage(out=tmp_path, client=_Client(), model="seat")
    assert [row["generator"] for row in judged] == ["misfit", "similar_to_known", "alerts"]
    assert receipt["ranking"]["order"] == "merged_file_order"
    stored = [
        json.loads(line)
        for line in (tmp_path / "notables.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [row["generator"] for row in stored] == ["misfit", "similar_to_known", "alerts"]
