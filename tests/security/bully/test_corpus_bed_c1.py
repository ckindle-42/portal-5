"""C.1 -- corpus bed binding, cousin planning, floor/product/cost.

Each test is seeded against a concrete failure mode this module closes:
D.4's own numbers never again silently pass as a haystack, and floor/product/
cost never collapse into one number.
"""

from __future__ import annotations

from portal.modules.security.core.bully import corpus_bed


def test_d4_record_counts_are_not_a_haystack_permanent_regression() -> None:
    # D.4's real numbers: only portal5_lab, 2000 records read.
    bed = corpus_bed.assess_bed({"portal5_lab": 2000}, records_read=2000)
    assert bed.is_haystack is False
    reasons = " ".join(bed.reasons)
    assert "corpus_too_small" in reasons
    assert "lane_A_absent" in reasons


def test_real_multi_index_bed_passes() -> None:
    available = {
        "portal5_lab": 50_000,
        "botsv1": 3_000_000,
        "botsv2": 5_000_000,
        "botsv3": 5_650_000,
    }
    total = sum(available.values())
    bed = corpus_bed.assess_bed(available, records_read=total)
    assert bed.is_haystack is True
    assert bed.lanes_present == ("A", "B", "C")
    assert bed.reasons == ()


def test_resolve_indexes_includes_all_bots_indexes() -> None:
    indexes = corpus_bed.resolve_indexes()
    for bots_index in corpus_bed.BOTS_INDEXES:
        assert bots_index in indexes
    assert indexes[0] == corpus_bed.CORPUS_INDEX


def test_floor_only_yields_fail() -> None:
    bed = corpus_bed.assess_bed(
        {"portal5_lab": 50_000, "botsv1": 3_000_000, "botsv2": 5_000_000, "botsv3": 5_650_000},
        records_read=13_700_000,
    )
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=10,
        answer_key_total=10,
        cousin_hit=0,
        cousin_total=10,
        background_flagged=0,
        background_total=1000,
        bed=bed,
    )
    assert acceptance.floor_known_recall == 1.0
    assert acceptance.product_cousin_recall == 0.0
    assert acceptance.verdict == "FAIL"
    assert any("zero_cousin_recall" in r for r in acceptance.reasons)


def test_non_haystack_bed_yields_invalid_whatever_the_recall() -> None:
    bed = corpus_bed.assess_bed({"portal5_lab": 2000}, records_read=2000)
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=25,
        answer_key_total=25,
        cousin_hit=25,
        cousin_total=25,
        background_flagged=0,
        background_total=100,
        bed=bed,
    )
    assert acceptance.floor_known_recall == 1.0
    assert acceptance.product_cousin_recall == 1.0
    assert acceptance.verdict == "INVALID"


def test_plan_cousins_refuses_technique_absent_from_answer_key() -> None:
    answer_key = [
        corpus_bed.AnswerKeyEntry(
            dataset="botsv3",
            technique="T1558.004",
            behavioural_spine=("kerberos_svc_ticket_request", "hash_extraction"),
            sourcetypes=("wineventlog:security",),
        )
    ]
    cousins = corpus_bed.plan_cousins(
        answer_key, corpus_sourcetypes=("wineventlog:security", "aws:cloudtrail")
    )
    # every cousin's parent technique is drawn from the answer key
    assert all(c.parent_technique == "T1558.004" for c in cousins)
    assert {c.parent_technique for c in cousins} <= {e.technique for e in answer_key}
    # no cousin is planned for a technique never passed in
    assert all(c.parent_technique != "T1110" for c in cousins)


def test_reschema_cousin_targets_a_sourcetype_the_parent_did_not_use() -> None:
    answer_key = [
        corpus_bed.AnswerKeyEntry(
            dataset="botsv3",
            technique="T1558.004",
            behavioural_spine=("kerberos_svc_ticket_request",),
            sourcetypes=("wineventlog:security",),
        )
    ]
    cousins = corpus_bed.plan_cousins(
        answer_key,
        transformations=("RESCHEMA",),
        corpus_sourcetypes=("wineventlog:security", "aws:cloudtrail", "stream:dns"),
    )
    assert len(cousins) == 1
    reschema = cousins[0]
    assert reschema.transformation == "RESCHEMA"
    assert "wineventlog:security" not in reschema.target_sourcetypes


def test_stream_corpus_batches_across_indexes_without_loading_whole() -> None:
    class FakeConnector:
        def __init__(self, index: str) -> None:
            self.index = index
            self._rows = [{"id": f"{index}-{i}"} for i in range(25)]

        def fetch(self, *, offset: int, limit: int) -> list[dict]:
            return self._rows[offset : offset + limit]

    records = list(
        corpus_bed.stream_corpus(
            FakeConnector, ("botsv1", "botsv2"), batch_size=10, max_records=None
        )
    )
    assert len(records) == 50
    assert all(r["__index"] in ("botsv1", "botsv2") for r in records)


def test_stream_corpus_respects_max_records() -> None:
    class FakeConnector:
        def __init__(self, index: str) -> None:
            self._rows = [{"id": i} for i in range(1000)]

        def fetch(self, *, offset: int, limit: int) -> list[dict]:
            return self._rows[offset : offset + limit]

    records = list(
        corpus_bed.stream_corpus(FakeConnector, ("botsv1",), batch_size=100, max_records=250)
    )
    assert len(records) == 250
