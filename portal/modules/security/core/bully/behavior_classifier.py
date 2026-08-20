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


@dataclass(frozen=True)
class CoverageReport:
    """Both coverages, reported honestly and never merged (R.5c)."""

    n_examples: int
    deterministic_correct: int
    learned_correct: int
    deterministic_coverage: float
    learned_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_examples": self.n_examples,
            "deterministic_correct": self.deterministic_correct,
            "learned_correct": self.learned_correct,
            "deterministic_coverage": round(self.deterministic_coverage, 4),
            "learned_coverage": round(self.learned_coverage, 4),
        }


def measure_coverage(
    classifier: LearnedBehaviorClassifier, held_out: list[tuple[str, str]]
) -> CoverageReport:
    """Held-out cross-schema behavioural-verb coverage, learned vs
    deterministic, over the SAME examples -- the before/after R.6 reports."""
    n = len(held_out)
    det_correct = sum(
        1 for text, cls in held_out if pyramid.default_behavior_classifier(text) == cls
    )
    learned_correct = sum(1 for text, cls in held_out if classifier(text) == cls)
    return CoverageReport(
        n_examples=n,
        deterministic_correct=det_correct,
        learned_correct=learned_correct,
        deterministic_coverage=(det_correct / n) if n else 0.0,
        learned_coverage=(learned_correct / n) if n else 0.0,
    )
