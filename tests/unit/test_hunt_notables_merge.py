from __future__ import annotations

import pytest

from portal.modules.security.core.hunt.notables.generators import Notable, _make
from portal.modules.security.core.hunt.notables.merge import (
    DEFAULT_MERGE,
    DEFAULT_WEIGHTS,
    MEASURED_SOURCE,
    RRF_K,
    UNMEASURED_WEIGHT,
    duplicate_key,
    group_by_generator,
    marginal_weights,
    merge_notables,
    remerge_without,
)

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

    _head, measured = merge_notables(
        notables, PRIORITY, "weighted", {"similar_to_known": 3}, weights_source=MEASURED_SOURCE
    )
    assert measured["weights_source"] == "measured"
    assert measured["weights_defaulted"] == ["deviation"]
    # a key the vector never measured keeps its default rather than a unit share
    assert measured["weights"]["deviation"] == DEFAULT_WEIGHTS["deviation"]
    with pytest.raises(ValueError, match="refusing to merge on defaults"):
        merge_notables(notables, PRIORITY, "weighted", {}, weights_source=MEASURED_SOURCE)


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


def test_remerge_without_drops_a_generators_only_covering_notable_from_the_head() -> None:
    notables = (
        [_notable("deviation", "known")]
        + [_notable("deviation", f"d{index}") for index in range(30)]
        + [_notable("misfit", f"m{index}") for index in range(30)]
        + [_notable("alerts", f"a{index}") for index in range(30)]
    )
    weights = {"deviation": 10, "misfit": 1, "alerts": 0}
    merged, _receipt = merge_notables(notables, PRIORITY, "weighted", weights)
    assert "deviation known" in [item.what for item in merged[:50]]

    without_deviation = remerge_without(notables, PRIORITY, "weighted", weights, "deviation")
    assert "deviation known" not in [item.what for item in without_deviation[:50]]

    without_misfit = remerge_without(notables, PRIORITY, "weighted", weights, "misfit")
    assert "deviation known" in [item.what for item in without_misfit[:50]]


def test_marginal_weights_average_the_remerge_losses_and_floor_unmeasured() -> None:
    families = [
        {
            "family": "a",
            "marginal_generators": {
                "deviation": {"candidates": 1, "marginal@50": 2},
                "misfit": {"candidates": 1, "marginal@50": 0},
            },
        },
        {
            "family": "b",
            "marginal_generators": {
                "deviation": {"candidates": 1, "marginal@50": 4},
                "alerts": {"candidates": 0, "marginal@50": 0},
            },
        },
    ]
    weights = marginal_weights(families)
    assert weights["deviation"] == 3
    assert weights["misfit"] == UNMEASURED_WEIGHT  # measured at zero, floored, never negative
    assert weights["alerts"] == UNMEASURED_WEIGHT  # existed == 0 keeps a unit weight
    assert weights["peer_rare"] == UNMEASURED_WEIGHT  # absent from every family
    assert marginal_weights([]) == DEFAULT_WEIGHTS
    assert marginal_weights([], {"deviation": 7}) == {"deviation": 7}
