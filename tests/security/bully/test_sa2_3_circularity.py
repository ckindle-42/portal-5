from __future__ import annotations

from portal.modules.security.core.bully import discovery_bench
from tests.security.bully._discovery_fixtures import build_corpus, build_snapshot


def _run():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    verdicts = discovery_bench.run_real_pairs(probes, snapshot, corpus=corpus)
    return probes, verdicts


def test_shuffled_labels_collapse_score_toward_chance():
    probes, verdicts = _run()
    probes_by_id = {p["specimen_id"]: p for p in probes}
    result = discovery_bench.shuffled_label_control(verdicts, probes_by_id)
    assert result["passed"] is True
    if result["real_precision"] is not None and result["mean_shuffled_precision"] is not None:
        assert result["mean_shuffled_precision"] <= result["real_precision"]


def test_all_p74_style_controls_pass_on_fixture_corpus():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    verdicts = discovery_bench.run_real_pairs(probes, snapshot, corpus=corpus)
    controls = discovery_bench.run_controls(probes, verdicts, snapshot)
    assert controls["identity"]["passed"] is True
    assert controls["retrieval_health"]["passed"] is True
    assert controls["known_near_far"]["passed"] is True
    assert controls["shuffled_label_control"]["passed"] is True
    assert controls["passed"] is True


def test_deliberately_circular_variant_is_caught():
    """A7's own falsification test: build a truth source that is *itself* a
    function of the engine's verdict (attached by specimen id, exactly the
    shape a real circular scorer would take) and confirm the shuffle-based
    control reports it as NOT collapsing -- i.e. it correctly refuses to
    certify a circular measurement as independent."""
    probes, verdicts = _run()
    probes_by_id = {p["specimen_id"]: p for p in probes}
    # Deliberately circular: "truth" is unconditionally True for every
    # specimen -- a truth source with zero independent information content,
    # exactly what a self-referential (engine-agrees-with-itself) scorer
    # degenerates to. Because it carries no real per-identity signal,
    # shuffling the probe<->label correspondence changes nothing: precision
    # stays pinned at 1.0 before and after, so it must NOT collapse.
    circular_truth_by_specimen = {p["specimen_id"]: True for p in probes}
    result = discovery_bench.circularity_probe(verdicts, circular_truth_by_specimen, probes_by_id)
    assert result["passed"] is False, (
        "a truth source defined purely from the engine's own verdict must "
        "fail the collapse-to-chance check, proving the control is not "
        "vacuously satisfied"
    )
