"""Y.5 -- report what the classifier's held-out coverage does not: the
output distribution and entropy on the run's own real captured verbs.
See docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md."""

from __future__ import annotations

from portal.modules.security.core.bully.behavior_classifier import (
    fit_classifier,
    measure_coverage,
    output_distribution,
)

_TRAINING_CORPUS: list[tuple[str, str]] = [
    ("4672", "escalate"),
    ("setuid", "escalate"),
    ("dcsync", "escalate"),
    ("4624", "auth"),
    ("login", "auth"),
    ("kerberos_tgt", "auth"),
    ("4661", "enumerate"),
    ("openat", "enumerate"),
    ("getdents", "enumerate"),
    ("4688", "execute"),
    ("exec", "execute"),
    ("spawn", "execute"),
]


def _classifier():
    return fit_classifier(_TRAINING_CORPUS)


def test_output_distribution_buckets_unclassified_separately():
    classifier = _classifier()
    dist, entropy, max_entropy = output_distribution(classifier, ["totally_unknown_$$$"])
    assert dist == {"UNCLASSIFIED": 1}
    assert entropy == 0.0


def test_collapsed_output_is_low_entropy_and_degenerate():
    """A classifier whose real-verb output collapses to one class must be
    flagged degenerate however high its held-out accuracy -- X.6's grading
    collapsed almost everything to SAME/SIMILAR (execute-heavy spines)."""
    classifier = _classifier()
    real_verbs = ["exec"] * 20  # every real verb classifies the same way
    report = measure_coverage(
        classifier, _TRAINING_CORPUS, real_verbs=real_verbs, degenerate_entropy_floor=1.0
    )
    assert report.real_verb_class_entropy_bits == 0.0
    assert report.real_verb_degenerate is True


def test_diverse_output_is_not_degenerate():
    classifier = _classifier()
    real_verbs = ["4672", "4624", "openat", "4688"] * 5  # spread across 4 classes evenly
    report = measure_coverage(
        classifier, _TRAINING_CORPUS, real_verbs=real_verbs, degenerate_entropy_floor=1.0
    )
    assert report.real_verb_class_entropy_bits > 1.0
    assert report.real_verb_degenerate is False


def test_report_omits_real_verb_fields_when_not_supplied():
    classifier = _classifier()
    report = measure_coverage(classifier, _TRAINING_CORPUS)
    assert report.real_verb_output_distribution is None
    assert report.real_verb_class_entropy_bits is None
    assert report.real_verb_degenerate is None
    d = report.to_dict()
    assert d["real_verb_degenerate"] is None


def test_distribution_totals_match_input_count():
    classifier = _classifier()
    real_verbs = ["4624", "openat", "exec", "unknown_thing"]
    report = measure_coverage(classifier, _TRAINING_CORPUS, real_verbs=real_verbs)
    assert sum(report.real_verb_output_distribution.values()) == len(real_verbs)
