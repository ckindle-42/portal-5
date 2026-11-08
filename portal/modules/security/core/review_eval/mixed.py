"""Score the review path on a held-out mixed corpus. Anchors and search stay disjoint."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from portal.modules.security.core.bully.unit_measurement import (
    ContaminationError,
    HeldOutSplit,
    assert_no_contamination,
    split_datasets,
)
from portal.modules.security.core.review_eval.item_identity import (
    attack_data_test_id,
    canonical_attack_data_root,
)

PROOF = "assert_no_contamination:ok"
DEFINITIONS = (
    "true_positives are labelled attacks with at least one overlapping concern; "
    "false_positives are concerns that overlap no label, plus every concern beyond one per hit attack; "
    "false_negatives are labelled attacks with no overlapping concern; "
    "precision is true_positives/(true_positives+false_positives); "
    "recall is true_positives/(true_positives+false_negatives); "
    "false_positive_rate is false_positives/known_benign_events and is null when that window "
    "has no known-benign events; a haystack window has no true positives and every concern is a "
    "false positive. BOTS is a haystack: it has no reliable per-event label and is not a source "
    "of true positives."
)
_REQUIRED = (
    "anchor_corpus",
    "search_corpus",
    "anchor_set_id",
    "embedder_id",
    "policy",
    "disjoint_proof",
)
_TECHNIQUE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_HAYSTACK_PHRASE = "not a source of true positives"


class ProvenanceError(ValueError):
    """A result is missing the provenance required to publish it."""

    def __init__(self, missing: str) -> None:
        super().__init__(missing)
        self.missing = missing


@dataclass(frozen=True)
class WindowSpec:
    corpus: str
    dataset_key: str
    start: float
    end: float
    sourcetypes: tuple[str, ...]
    role: str
    max_events: int
    note: str = ""

    def __post_init__(self) -> None:
        if self.role not in {"attack", "haystack"}:
            raise ValueError("window role must be attack or haystack")
        if (
            not self.corpus
            or not self.dataset_key
            or self.end <= self.start
            or self.max_events <= 0
        ):
            raise ValueError("window needs a corpus, dataset key, positive span, and max_events")
        if self.role == "haystack" and _HAYSTACK_PHRASE not in self.note:
            raise ValueError("haystack window must say it is not a source of true positives")


@dataclass(frozen=True)
class AttackLabel:
    corpus: str
    dataset_key: str
    techniques: tuple[str, ...]
    start: float
    end: float
    label_source: str
    event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.label_source not in {"data_yml", "orchestrator_episode"}:
            raise ValueError("label_source must be data_yml or orchestrator_episode")
        if self.label_source == "data_yml" and not self.techniques:
            raise ValueError("data_yml label has no technique")
        if self.end < self.start:
            raise ValueError("label end is before start")


@dataclass(frozen=True)
class ConcernHit:
    concern_id: str
    times: tuple[float, ...]
    event_ids: tuple[str, ...]


@dataclass(frozen=True)
class WindowObservation:
    events_reviewed: int
    units_scored: int
    benign_events: int
    concerns: tuple[ConcernHit, ...]
    units_built: int | None = None


@dataclass(frozen=True)
class WindowScore:
    corpus: str
    dataset_key: str
    role: str
    events_reviewed: int
    units_built: int
    units_scored: int
    concerns_raised: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    false_positive_rate: float | None
    benign_events: int
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Provenance:
    anchor_corpus: str
    search_corpus: str
    windows: tuple[WindowSpec, ...]
    anchor_set_id: str
    embedder_id: str
    policy: str
    alpha_unusual: float
    alpha_similar: float
    type_dataset_keys: tuple[str, ...]
    eval_dataset_keys: tuple[str, ...]
    disjoint_proof: str
    anchor_index_attached: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["windows"] = [asdict(window) for window in self.windows]
        return payload


@dataclass(frozen=True)
class HarnessResult:
    provenance: Provenance
    scores: tuple[WindowScore, ...]


def bind_split(anchor_keys: Sequence[str], search_keys: Sequence[str]) -> HeldOutSplit:
    """Anchor keys are the type half. Search keys that also anchor are contamination."""
    if not anchor_keys or not search_keys:
        raise ContaminationError("anchor and search dataset keys are both required")
    split = HeldOutSplit(frozenset(anchor_keys), frozenset(search_keys))
    assert_no_contamination(list(search_keys), split)
    return split


def split_pool(
    dataset_keys: Sequence[str], *, type_fraction: float = 0.5, seed: int = 0
) -> HeldOutSplit:
    """Held-out split of one pool. The eval half is the only half that may be searched."""
    split = split_datasets(list(dataset_keys), type_fraction=type_fraction, seed=seed)
    if not split.type_dataset_keys or not split.eval_dataset_keys:
        raise ContaminationError("split produced an empty half")
    assert_no_contamination(list(split.eval_dataset_keys), split)
    return split


def accept_window_count(count: int, max_events: int) -> None:
    """Refuse a window the caller did not budget for, before any event export."""
    if max_events <= 0:
        raise ValueError("max_events must be positive")
    if count <= 0:
        raise ValueError("window has no events")
    if count > max_events:
        raise ValueError(f"window has {count} events, above max_events {max_events}")


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _hits(concern: ConcernHit, label: AttackLabel) -> bool:
    if label.event_ids and set(concern.event_ids).intersection(label.event_ids):
        return True
    return any(label.start <= moment <= label.end for moment in concern.times)


def _check_window(
    window: WindowSpec, labels: Sequence[AttackLabel], observed: WindowObservation
) -> None:
    if window.role == "haystack" and labels:
        raise ValueError("a haystack window has no attack labels")
    if window.role == "attack" and not labels:
        raise ValueError("an attack window needs a label")
    if any(label.dataset_key != window.dataset_key for label in labels):
        raise ValueError("label dataset key does not match the window")
    if len({label.dataset_key for label in labels}) != len(labels):
        raise ValueError("duplicate label keys")
    built = observed.units_scored if observed.units_built is None else observed.units_built
    if (
        observed.events_reviewed <= 0
        or observed.units_scored < 0
        or built < observed.units_scored
        or observed.benign_events < 0
    ):
        raise ValueError("event and unit counts must be usable")
    if observed.benign_events > observed.events_reviewed:
        raise ValueError("known-benign events cannot exceed events reviewed")


def score_window(
    window: WindowSpec, labels: Sequence[AttackLabel], observed: WindowObservation
) -> WindowScore:
    """One window. Extra concerns on one labelled attack count as false positives."""
    _check_window(window, labels, observed)
    units_built = observed.units_scored if observed.units_built is None else observed.units_built
    matched: set[str] = set()
    hitting = 0
    for concern in observed.concerns:
        hit = False
        for label in labels:
            if _hits(concern, label):
                matched.add(label.dataset_key)
                hit = True
        if hit:
            hitting += 1
    true_positives = len(matched)
    false_positives = (len(observed.concerns) - hitting) + max(0, hitting - true_positives)
    false_negatives = len(labels) - true_positives
    return WindowScore(
        corpus=window.corpus,
        dataset_key=window.dataset_key,
        role=window.role,
        events_reviewed=observed.events_reviewed,
        units_built=units_built,
        units_scored=observed.units_scored,
        concerns_raised=len(observed.concerns),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=_ratio(true_positives, true_positives + false_positives),
        recall=_ratio(true_positives, true_positives + false_negatives),
        false_positive_rate=_ratio(false_positives, observed.benign_events),
        benign_events=observed.benign_events,
        note=window.note,
    )


def rollup(scores: Sequence[WindowScore]) -> dict[str, Any]:
    """Headline rates. The false-positive rate uses only windows that named benign events."""
    true_positives = sum(score.true_positives for score in scores)
    false_positives = sum(score.false_positives for score in scores)
    false_negatives = sum(score.false_negatives for score in scores)
    benign = sum(score.benign_events for score in scores)
    benign_false_positives = sum(
        score.false_positives for score in scores if score.benign_events > 0
    )
    return {
        "events_reviewed": sum(score.events_reviewed for score in scores),
        "units_built": sum(score.units_built for score in scores),
        "units_scored": sum(score.units_scored for score in scores),
        "concerns_raised": sum(score.concerns_raised for score in scores),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": _ratio(true_positives, true_positives + false_positives),
        "recall": _ratio(true_positives, true_positives + false_negatives),
        "false_positive_rate": _ratio(benign_false_positives, benign),
        "known_benign_events": benign,
    }


def _missing(provenance: Provenance) -> list[str]:
    missing = [name for name in _REQUIRED if not str(getattr(provenance, name)).strip()]
    if not provenance.windows:
        missing.append("windows")
    if not provenance.type_dataset_keys:
        missing.append("type_dataset_keys")
    if not provenance.eval_dataset_keys:
        missing.append("eval_dataset_keys")
    if provenance.disjoint_proof != PROOF and "disjoint_proof" not in missing:
        missing.append("disjoint_proof")
    if not math.isfinite(provenance.alpha_unusual) or not math.isfinite(provenance.alpha_similar):
        missing.append("alphas")
    return missing


def _row(window: WindowSpec, score: WindowScore, provenance: Provenance) -> dict[str, Any]:
    if score.dataset_key != window.dataset_key:
        raise ProvenanceError("score does not match its window")
    if score.dataset_key not in provenance.eval_dataset_keys:
        raise ContaminationError(f"window {score.dataset_key} is outside the eval half")
    row = score.to_dict()
    row["anchor_corpus"] = provenance.anchor_corpus
    row["search_corpus"] = window.corpus
    row["disjoint_proof"] = provenance.disjoint_proof
    return row


def publish(result: HarnessResult) -> dict[str, Any]:
    """Refuse a result that omits provenance or whose search keys also anchored."""
    missing = _missing(result.provenance)
    if missing:
        raise ProvenanceError(", ".join(missing))
    bind_split(result.provenance.type_dataset_keys, result.provenance.eval_dataset_keys)
    if len(result.scores) != len(result.provenance.windows):
        raise ProvenanceError("scores do not match windows")
    rows = [
        _row(window, score, result.provenance)
        for window, score in zip(result.provenance.windows, result.scores, strict=True)
    ]
    payload = rollup(result.scores)
    payload["windows"] = rows
    payload["provenance"] = result.provenance.to_dict()
    payload["definitions"] = DEFINITIONS
    payload["generalisation_measured"] = result.provenance.anchor_index_attached
    return payload


def _techniques(path: Path) -> tuple[str, ...] | None:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(document, dict):
        return None
    raw = document.get("mitre_technique") or ()
    if isinstance(raw, str):
        raw = (raw,)
    found = sorted({str(item).strip() for item in raw if _TECHNIQUE.fullmatch(str(item).strip())})
    return tuple(found) if found else None


def labels_from_attack_data(
    root: Path,
    *,
    corpus: str,
    publisher: str,
    item_id: Callable[[str, str], str],
) -> tuple[AttackLabel, ...]:
    """One label per data.yml. The technique list is the label; prose files are ignored."""
    if not corpus or not publisher:
        raise ValueError("corpus and publisher are required")
    checkout = canonical_attack_data_root(root)
    datasets_root = checkout / "datasets"
    labels: list[AttackLabel] = []
    for path in sorted(datasets_root.rglob("data.yml")):
        techniques = _techniques(path)
        if techniques is None:
            continue
        test_id = attack_data_test_id(path.parent, checkout)
        identifier = item_id(publisher, test_id)
        labels.append(
            AttackLabel(
                corpus=corpus,
                dataset_key=f"{corpus}/{identifier}",
                techniques=techniques,
                start=0.0,
                end=0.0,
                label_source="data_yml",
            )
        )
    return tuple(labels)


def labels_from_episodes(
    corpus: str, records: Sequence[Mapping[str, Any]]
) -> tuple[AttackLabel, ...]:
    """portal5_lab ground truth is the episode id and its attack window, not a write-up."""
    labels: list[AttackLabel] = []
    for record in records:
        episode_id = str(record.get("episode_id") or "")
        if not episode_id or "start" not in record or "end" not in record:
            raise ValueError("episode label needs episode_id, start, and end")
        labels.append(
            AttackLabel(
                corpus=corpus,
                dataset_key=f"{corpus}/{episode_id}",
                techniques=(),
                start=float(record["start"]),
                end=float(record["end"]),
                label_source="orchestrator_episode",
            )
        )
    return tuple(labels)


def observation_from_review(result: Any, *, benign_events: int) -> WindowObservation:
    """Counts and concern times from a real ``run_review`` result. No second scorer."""
    fetched = int(result.fingerprint["fetched_events"])
    receipt = next((item for item in result.receipts if item.name == "funnel.scored"), None)
    if receipt is None:
        raise ValueError("review result has no funnel.scored receipt")
    units = int(receipt.resolved)
    built = int(receipt.examined)
    concerns = tuple(
        ConcernHit(
            str(concern.concern_id),
            tuple(float(item.time) for item in concern.evidence if item.time is not None),
            tuple(str(item.event_id) for item in concern.evidence),
        )
        for concern in result.concerns
    )
    return WindowObservation(fetched, units, benign_events, concerns, built)
