"""K.1 -- stratified scorer sample (TASK_BULLY_SCORER_FEED_V1).

Each check is seeded to fail against the F.4 defect: the analytical path was
fed `last_batch` -- whatever the final streaming iteration held -- instead of
a sample spanning the sourcetypes the stream actually covered."""

from __future__ import annotations

from portal.modules.security.core.bully.score_sample import (
    StratifiedSample,
    scorer_input_verdict,
)


def _f4_shaped_stream() -> list[tuple[dict, str]]:
    """325 sourcetypes worth of stream: a dominant head sourcetype (5000
    records, so a per-sourcetype cap of 200 actually truncates it), 323 thin
    middle sourcetypes, ending on a 63-record tail of one tiny source --
    F.4's exact shape (real corpora are volume-skewed, not flat)."""
    stream: list[tuple[dict, str]] = []
    head_st = "sourcetype-0"
    for j in range(5000):
        stream.append(({"j": j, "st": head_st}, head_st))
    for i in range(1, 324):
        st = f"sourcetype-{i}"
        for j in range(5):
            stream.append(({"i": i, "j": j, "st": st}, st))
    tail_st = "yum-too_small"
    for j in range(63):
        stream.append(({"tail": j, "st": tail_st}, tail_st))
    return stream


def test_f4_shape_last_batch_grades_starved_permanent_regression():
    """F.4 as shipped: the scorer sees only `last_batch`, 63 records of one
    sourcetype out of 325 covered by the stream. Must always grade STARVED."""
    stream = _f4_shaped_stream()
    last_batch = [rec for rec, st in stream if st == "yum-too_small"]
    last_batch_sourcetypes = {"yum-too_small"}

    report = {
        "algorithm_version": "score-sample-v1",
        "sourcetypes_seen": 325,
        "sourcetypes_sampled": len(last_batch_sourcetypes),
        "records_seen": len(stream),
        "records_sampled": len(last_batch),
        "per_sourcetype_cap": 200,
        "sample_fraction": len(last_batch) / len(stream),
        "truncated_at_max_total": False,
        "largest_sourcetype_share": 1.0,
    }
    verdict = scorer_input_verdict(report, sourcetypes_covered_by_stream=325)
    assert verdict["verdict"] == "STARVED", verdict
    assert any("scorer_saw_1_of_325_sourcetypes" in r for r in verdict["reasons"])
    assert any("single_sourcetype_share" in r for r in verdict["reasons"])


def test_stratified_sample_of_same_stream_grades_ok_all_sourcetypes_present():
    """The fix: a StratifiedSample built from the same 325-sourcetype stream
    keeps every sourcetype and grades OK."""
    stream = _f4_shaped_stream()
    sample = StratifiedSample(per_sourcetype=200)
    sample.extend([r for r, _st in stream], sourcetype_of=lambda r: r["st"])

    report = sample.report()
    assert report["sourcetypes_sampled"] == 325
    verdict = scorer_input_verdict(report, sourcetypes_covered_by_stream=325)
    assert verdict["verdict"] == "OK", verdict
    assert verdict["reasons"] == []
    assert set(sample.sourcetypes) == {rec_st for _rec, rec_st in stream}


def test_head_slice_of_equal_size_is_also_caught_starved():
    """A naive head-slice 'fix' of the same total size as the stratified
    sample must also be caught -- a flat slice is the obvious wrong fix."""
    stream = _f4_shaped_stream()
    sample = StratifiedSample(per_sourcetype=200)
    sample.extend([r for r, _st in stream], sourcetype_of=lambda r: r["st"])
    target_size = sample.total

    head_slice = stream[:target_size]
    head_sourcetypes = {st for _r, st in head_slice}

    report = {
        "algorithm_version": "score-sample-v1",
        "sourcetypes_seen": 325,
        "sourcetypes_sampled": len(head_sourcetypes),
        "records_seen": len(stream),
        "records_sampled": len(head_slice),
        "per_sourcetype_cap": 200,
        "sample_fraction": len(head_slice) / len(stream),
        "truncated_at_max_total": False,
        "largest_sourcetype_share": (
            max(sum(1 for _r, st in head_slice if st == s) for s in head_sourcetypes)
            / len(head_slice)
        ),
    }
    verdict = scorer_input_verdict(report, sourcetypes_covered_by_stream=325)
    assert verdict["verdict"] == "STARVED", verdict
    assert len(head_sourcetypes) < 325


def test_reservoir_replaces_with_decreasing_probability_not_head_biased():
    """A busy source's sample must be drawn across its whole appearance in
    the stream, not just its first N records -- head bias reproduces the
    time-ordering defect at sourcetype granularity."""
    sample = StratifiedSample(per_sourcetype=50, seed=1337)
    busy_st = "busy-source"
    n_seen = 5000
    for i in range(n_seen):
        sample.add({"i": i}, busy_st)

    kept = sample._by_st[busy_st]
    assert len(kept) == 50
    kept_indices = sorted(r["i"] for r in kept)
    # a head-biased sample would keep indices [0, 49]; a reservoir sample
    # draws representatives across the whole 5000-record appearance.
    assert kept_indices != list(range(50))
    assert max(kept_indices) > 100
    assert min(kept_indices) < n_seen - 100


def test_max_total_truncation_is_reported_never_silent():
    """A corpus with more sourcetypes than MAX_TOTAL / per_sourcetype allows
    must report the truncation, not silently drop records."""
    sample = StratifiedSample(per_sourcetype=10, max_total=100)
    for st_i in range(50):
        st = f"st-{st_i}"
        for j in range(10):
            sample.add({"st_i": st_i, "j": j}, st)

    report = sample.report()
    assert report["truncated_at_max_total"] is True
    assert sample.total <= 100

    verdict = scorer_input_verdict(report, sourcetypes_covered_by_stream=50)
    assert "sample_truncated_at_max_total" in verdict["reasons"]
