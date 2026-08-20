"""bully.behavior_classifier -- the learned action->behaviour classifier (R.5c).

R.5b measured the deterministic verb table (`pyramid.default_behavior_
classifier`) at low cross-schema coverage against the procedurally-invented
universe: a source's own concrete realization of a behavioural class (a
numeric EventID-like code, a syscall name, a URL path, an invented verb, a
free-text fragment) rarely contains any of the deterministic table's English
verb substrings. That table cannot work on universal data by itself.

This module fits a classifier over the SEALED `true_behavior_class` corpus
the generators produce (universe.py's per-artifact truth, or any
(raw_observable, true_class) pairs from a real corpus with EventIDs/
syscalls/osquery diffs/cloud verbs) -- a character-trigram multinomial naive
Bayes model, pure stdlib, no torch/transformers (SS8: this module lives under
`portal/modules/security/core/`, outside `portal/platform/inference/`, but
the project-wide "no heavy ML deps" posture is honored anyway: a trigram NB
model is adequate for a closed 10-class alphabet and keeps the fit/inference
COLD and fast).

`LearnedBehaviorClassifier.__call__` matches the `pyramid.BehaviorClassifier`
signature exactly (`str -> str`), so it is a drop-in for
`default_behavior_classifier` anywhere pyramid/series_cousin/signatures
accept a classifier. Fit is offline; the fitted model is frozen (immutable
after `fit`) and injected into the grade path -- the grade path itself never
trains. The deterministic table remains the labelled fallback: `measure_
coverage` reports the deterministic and learned coverage over the same
held-out corpus side by side, so both are visible every run, never
silently merged into one number.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from . import pyramid

ALGORITHM_VERSION = "behavior-classifier-v1"

# Laplace smoothing for unseen trigrams at inference time.
_SMOOTHING = 1.0
_MIN_CONFIDENCE = 0.35  # below this, "learned" is not confident enough to assert


def _trigrams(text: str) -> list[str]:
    t = f"^{text.lower()}$"
    if len(t) < 3:
        return [t]
    return [t[i : i + 3] for i in range(len(t) - 2)]


@dataclass(frozen=True)
class LearnedBehaviorClassifier:
    """A fitted, frozen trigram naive-Bayes verb->behaviour-class classifier."""

    class_priors: dict[str, float]
    feature_log_probs: dict[str, dict[str, float]]  # class -> trigram -> log P(trigram|class)
    vocab_size: int
    classes: tuple[str, ...]
    trained_on: int

    def _score(self, text: str) -> dict[str, float]:
        grams = _trigrams(text)
        scores: dict[str, float] = {}
        for cls in self.classes:
            log_p = self.class_priors[cls]
            table = self.feature_log_probs[cls]
            default = math.log(_SMOOTHING / (self.vocab_size * _SMOOTHING + self.vocab_size))
            for g in grams:
                log_p += table.get(g, default)
            scores[cls] = log_p
        return scores

    def predict(self, text: str) -> tuple[str, float]:
        """Return (predicted_class, confidence in [0,1]) via softmax over
        the naive-Bayes log-scores."""
        if not text:
            return "", 0.0
        scores = self._score(text)
        max_score = max(scores.values())
        exp_scores = {c: math.exp(s - max_score) for c, s in scores.items()}
        total = sum(exp_scores.values())
        probs = {c: v / total for c, v in exp_scores.items()}
        best_cls = max(probs, key=probs.get)
        return best_cls, probs[best_cls]

    def __call__(self, verb: str) -> str:
        """`pyramid.BehaviorClassifier`-compatible: text -> class, or '' on
        low confidence (never a false positive class -- mirrors the
        deterministic table's honest-miss contract)."""
        if not verb:
            return ""
        cls, confidence = self.predict(verb)
        return cls if confidence >= _MIN_CONFIDENCE else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "classes": list(self.classes),
            "trained_on": self.trained_on,
            "vocab_size": self.vocab_size,
        }


def fit_classifier(examples: list[tuple[str, str]]) -> LearnedBehaviorClassifier:
    """Fit a trigram naive-Bayes classifier from (raw_observable, true_class)
    pairs -- the sealed truth a generator (universe.py's build_universe, or
    a real corpus) produces. COLD: pure counting, no gradient/iterative
    training, deterministic given the examples."""
    class_counts: Counter[str] = Counter()
    trigram_counts: dict[str, Counter[str]] = defaultdict(Counter)
    vocab: set[str] = set()

    for text, cls in examples:
        if not text or not cls:
            continue
        class_counts[cls] += 1
        for g in _trigrams(text):
            trigram_counts[cls][g] += 1
            vocab.add(g)

    total = sum(class_counts.values()) or 1
    classes = tuple(sorted(class_counts))
    vocab_size = len(vocab) or 1

    priors = {cls: math.log(class_counts[cls] / total) for cls in classes}
    feature_log_probs: dict[str, dict[str, float]] = {}
    for cls in classes:
        counts = trigram_counts[cls]
        denom = sum(counts.values()) + _SMOOTHING * vocab_size
        feature_log_probs[cls] = {g: math.log((c + _SMOOTHING) / denom) for g, c in counts.items()}

    return LearnedBehaviorClassifier(
        class_priors=priors,
        feature_log_probs=feature_log_probs,
        vocab_size=vocab_size,
        classes=classes,
        trained_on=total,
    )


# Below this bits-of-entropy, the classifier's output on real verbs is
# reported degenerate regardless of held-out accuracy (Y.5,
# TASK_BULLY_TRUTH_ACCEPTANCE_V1): a run that collapses toward one or two
# classes is exactly the information-free labelling that produced
# `execute x14` spines in X.6.
DEGENERATE_ENTROPY_FLOOR_BITS = 1.0


@dataclass(frozen=True)
class CoverageReport:
    """Both coverages, reported honestly and never merged (R.5c).

    `real_verb_*` fields (Y.5) report what the classifier's held-out
    ACCURACY does not: held-out accuracy on `universe.py`'s synthetic
    realizations is measured on a distribution where the class name is often
    embedded in the verb string itself (`{stem}Execute`) -- honest, but it
    says little about real telemetry. The deterministic classifier leaves
    69% of real captured verbs unclassified (`4624`, `4688`, `openat`,
    `user.authentication.sso` all return no class), so on live data the
    learned model is carrying nearly all the weight with no measured
    real-world accuracy. These fields report the OUTPUT distribution and its
    entropy on the run's own real captured verbs -- a classifier whose
    output collapses toward one class is degenerate however high its
    held-out accuracy."""

    n_examples: int
    deterministic_correct: int
    learned_correct: int
    deterministic_coverage: float
    learned_coverage: float
    real_verb_output_distribution: dict[str, int] | None = None
    real_verb_class_entropy_bits: float | None = None
    real_verb_max_entropy_bits: float | None = None
    real_verb_degenerate: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_examples": self.n_examples,
            "deterministic_correct": self.deterministic_correct,
            "learned_correct": self.learned_correct,
            "deterministic_coverage": round(self.deterministic_coverage, 4),
            "learned_coverage": round(self.learned_coverage, 4),
            "real_verb_output_distribution": self.real_verb_output_distribution,
            "real_verb_class_entropy_bits": (
                round(self.real_verb_class_entropy_bits, 4)
                if self.real_verb_class_entropy_bits is not None
                else None
            ),
            "real_verb_max_entropy_bits": (
                round(self.real_verb_max_entropy_bits, 4)
                if self.real_verb_max_entropy_bits is not None
                else None
            ),
            "real_verb_degenerate": self.real_verb_degenerate,
        }


def output_distribution(
    classifier: LearnedBehaviorClassifier | Any, real_verbs: list[str]
) -> tuple[dict[str, int], float, float]:
    """Per-class output distribution and Shannon entropy (bits) of
    `classifier` over `real_verbs` -- the run's own real captured verbs, not
    a synthetic held-out set. An unclassified verb (`''`) is its own bucket
    (`UNCLASSIFIED`), never silently merged into a real class."""
    counts: dict[str, int] = {}
    for verb in real_verbs:
        cls = classifier(verb) or "UNCLASSIFIED"
        counts[cls] = counts.get(cls, 0) + 1
    n = sum(counts.values())
    entropy = 0.0
    if n:
        for c in counts.values():
            p = c / n
            if p > 0:
                entropy -= p * math.log2(p)
    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 0.0
    return counts, entropy, max_entropy


def measure_coverage(
    classifier: LearnedBehaviorClassifier,
    held_out: list[tuple[str, str]],
    *,
    real_verbs: list[str] | None = None,
    degenerate_entropy_floor: float = DEGENERATE_ENTROPY_FLOOR_BITS,
) -> CoverageReport:
    """Held-out cross-schema behavioural-verb coverage, learned vs
    deterministic, over the SAME examples -- the before/after R.6 reports.

    `real_verbs`, when supplied (Y.5), adds the classifier's OUTPUT
    distribution and entropy over the run's own real captured verbs
    alongside the held-out accuracy numbers -- accuracy and distribution are
    never merged into one figure."""
    n = len(held_out)
    det_correct = sum(
        1 for text, cls in held_out if pyramid.default_behavior_classifier(text) == cls
    )
    learned_correct = sum(1 for text, cls in held_out if classifier(text) == cls)

    dist: dict[str, int] | None = None
    entropy: float | None = None
    max_entropy: float | None = None
    degenerate: bool | None = None
    if real_verbs:
        dist, entropy, max_entropy = output_distribution(classifier, real_verbs)
        degenerate = entropy < degenerate_entropy_floor

    return CoverageReport(
        n_examples=n,
        deterministic_correct=det_correct,
        learned_correct=learned_correct,
        deterministic_coverage=(det_correct / n) if n else 0.0,
        learned_coverage=(learned_correct / n) if n else 0.0,
        real_verb_output_distribution=dist,
        real_verb_class_entropy_bits=entropy,
        real_verb_max_entropy_bits=max_entropy,
        real_verb_degenerate=degenerate,
    )
