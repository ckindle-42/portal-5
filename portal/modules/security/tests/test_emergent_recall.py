"""Slice 3.2: detection recall vs an arbitrary procedure corpus (D4).

Proves generate_coverage_json's `corpus` parameter reuses the exact existing
recall math (no new formula) but scores it against the corpus instead of the
graph's own accumulated exercised|detected set — and that this differs from
default scenario-signature-scoped coverage on the same graph.
"""

from __future__ import annotations

from portal.modules.security.core.agentic_blue_eval import emergent_recall_metric
from portal.modules.security.core.capability_graph import (
    CapabilityGraph,
    Detection,
    Gap,
)


def _graph_with_one_detected_technique() -> CapabilityGraph:
    graph = CapabilityGraph()
    graph.add_detection(Detection(detection_id="det-T1110", technique_id="T1110"))
    graph.add_gap(
        Gap(
            gap_id="gap-scripted-T1110",
            procedure_id="proc-scripted",
            technique_id="T1110",
            axes={
                "red": "RED_LANDED",
                "telemetry": "TELEMETRY_OBSERVED",
                "detection": "DETECTION_CONFIRMED",
            },
            summary="COVERED",
            reason_codes=[],
        )
    )
    return graph


def test_corpus_recall_matches_hand_derived_expectation():
    graph = _graph_with_one_detected_technique()
    # An emergent corpus of 4 techniques, only 1 of which has a detection.
    corpus = {"T1110", "T1595", "T1078", "T1021"}

    metric = emergent_recall_metric(graph, corpus)

    assert metric["metric"] == "recall_vs_emergent_corpus"
    assert metric["corpus_size"] == 4
    assert metric["detected"] == 1
    assert metric["recall_pct"] == 25.0  # 1/4, hand-derived


def test_corpus_recall_differs_from_default_scenario_recall():
    graph = _graph_with_one_detected_technique()

    from portal.modules.security.core.capability_graph import generate_coverage_json

    default_coverage = generate_coverage_json(graph)  # scenario-signature scope: eligible=1
    corpus_metric = emergent_recall_metric(graph, {"T1110", "T1595", "T1078", "T1021"})

    assert default_coverage["tiers"]["eligible"] == 1
    assert default_coverage["tiers"]["detected_pct"] == 100.0
    assert corpus_metric["corpus_size"] == 4
    assert corpus_metric["recall_pct"] == 25.0
    assert default_coverage["tiers"]["detected_pct"] != corpus_metric["recall_pct"]


def test_empty_corpus_is_zero_not_a_crash():
    graph = _graph_with_one_detected_technique()
    metric = emergent_recall_metric(graph, set())
    assert metric["corpus_size"] == 0
    assert metric["recall_pct"] == 0
