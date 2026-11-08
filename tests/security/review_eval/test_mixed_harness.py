"""The mixed-corpus harness refuses a contaminated episode and an unprovenanced result."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully.unit_measurement import (
    ContaminationError,
    assert_no_contamination,
)
from portal.modules.security.core.review_eval.guards import disallowed_imports
from portal.modules.security.core.review_eval.mixed import (
    AttackLabel,
    ConcernHit,
    HarnessResult,
    Provenance,
    ProvenanceError,
    WindowObservation,
    WindowSpec,
    accept_window_count,
    bind_split,
    labels_from_attack_data,
    labels_from_episodes,
    observation_from_review,
    publish,
    score_window,
    split_pool,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "detection_harness_mixed.py"
ALLOWED_IMPORTS = (
    "portal.modules.security.core.review.service",
    "portal.modules.security.core.review.window",
    "portal.modules.security.core.review.reference",
    "portal.modules.security.core.review.funnel",
    "portal.modules.security.core.review_eval",
)
HAYSTACK = "no reliable per-event label; not a source of true positives"


def _window(role: str, key: str = "labelled_corpus/item-b", note: str = "") -> WindowSpec:
    return WindowSpec(
        corpus=key.split("/", 1)[0],
        dataset_key=key,
        start=100.0,
        end=160.0,
        sourcetypes=("wineventlog:security",),
        role=role,
        max_events=200,
        note=note,
    )


def _label(key: str = "labelled_corpus/item-b") -> AttackLabel:
    return AttackLabel(
        corpus="labelled_corpus",
        dataset_key=key,
        techniques=("T1003.001",),
        start=100.0,
        end=160.0,
        label_source="data_yml",
    )


def _provenance(**overrides: object) -> Provenance:
    split = bind_split(("labelled_corpus/item-a",), ("labelled_corpus/item-b",))
    window = _window("attack")
    base: dict[str, object] = {
        "anchor_corpus": "labelled_corpus",
        "search_corpus": "labelled_corpus",
        "windows": (window,),
        "anchor_set_id": "set-1",
        "embedder_id": "embedder-1",
        "policy": "alpha_unusual=0.2;alpha_similar=0.2",
        "alpha_unusual": 0.2,
        "alpha_similar": 0.2,
        "type_dataset_keys": tuple(sorted(split.type_dataset_keys)),
        "eval_dataset_keys": tuple(sorted(split.eval_dataset_keys)),
        "disjoint_proof": "assert_no_contamination:ok",
        "anchor_index_attached": False,
    }
    base.update(overrides)
    return Provenance(**base)  # type: ignore[arg-type]


def _result(**overrides: object) -> HarnessResult:
    observed = WindowObservation(10, 4, 0, ())
    score = score_window(_window("attack"), (_label(),), observed)
    return HarnessResult(provenance=_provenance(**overrides), scores=(score,))


def test_same_episode_anchor_and_search_is_refused() -> None:
    with pytest.raises(ContaminationError):
        bind_split(("labelled_corpus/item-a",), ("labelled_corpus/item-a",))


def test_split_pool_uses_the_existing_checker() -> None:
    split = split_pool(("a", "b", "c", "d"), type_fraction=0.5, seed=0)
    assert split.type_dataset_keys.isdisjoint(split.eval_dataset_keys)
    assert_no_contamination(list(split.eval_dataset_keys), split)
    with pytest.raises(ContaminationError):
        assert_no_contamination(list(split.type_dataset_keys), split)


def test_missing_provenance_is_not_publishable() -> None:
    with pytest.raises(ProvenanceError, match="embedder_id"):
        publish(_result(embedder_id=""))


def test_overlapping_datasets_are_not_publishable() -> None:
    with pytest.raises(ContaminationError):
        publish(
            _result(
                type_dataset_keys=("labelled_corpus/item-b",),
                eval_dataset_keys=("labelled_corpus/item-b",),
            )
        )


def test_a_flood_of_concerns_is_not_one_detection() -> None:
    concerns = tuple(ConcernHit(f"c{i}", (120.0,), ()) for i in range(134))
    score = score_window(
        _window("attack"),
        (_label(),),
        WindowObservation(475, 80, 0, concerns),
    )
    assert score.events_reviewed == 475
    assert score.units_scored == 80
    assert score.concerns_raised == 134
    assert score.true_positives == 1
    assert score.false_positives == 133
    assert score.false_negatives == 0
    assert score.precision == pytest.approx(1 / 134)
    assert score.recall == 1.0
    assert score.false_positive_rate is None


def test_a_missed_attack_is_a_false_negative() -> None:
    score = score_window(_window("attack"), (_label(),), WindowObservation(40, 6, 0, ()))
    assert score.true_positives == 0
    assert score.false_positives == 0
    assert score.false_negatives == 1
    assert score.precision is None
    assert score.recall == 0.0


def test_a_concern_outside_the_label_is_a_false_positive() -> None:
    score = score_window(
        _window("attack"),
        (_label(),),
        WindowObservation(40, 6, 10, (ConcernHit("c", (10.0,), ()),)),
    )
    assert score.true_positives == 0
    assert score.false_positives == 1
    assert score.false_negatives == 1
    assert score.precision == 0.0
    assert score.false_positive_rate == pytest.approx(0.1)


def test_haystack_counts_every_concern_as_a_false_positive() -> None:
    window = _window("haystack", "botsv3/slice-1", HAYSTACK)
    score = score_window(
        window,
        (),
        WindowObservation(100, 12, 100, (ConcernHit("c", (1.0,), ()),) * 3),
    )
    assert score.true_positives == 0
    assert score.false_positives == 3
    assert score.false_negatives == 0
    assert score.recall is None
    assert score.precision == 0.0
    assert score.false_positive_rate == pytest.approx(0.03)
    published = publish(
        HarnessResult(
            provenance=_provenance(
                anchor_corpus="labelled_corpus",
                search_corpus="botsv3",
                windows=(window,),
                type_dataset_keys=("labelled_corpus/item-a",),
                eval_dataset_keys=("botsv3/slice-1",),
            ),
            scores=(score,),
        )
    )
    assert published["windows"][0]["search_corpus"] == "botsv3"
    assert published["windows"][0]["disjoint_proof"] == "assert_no_contamination:ok"
    assert "not a source of true positives" in published["windows"][0]["note"]
    assert published["false_positive_rate"] == pytest.approx(0.03)
    assert published["recall"] is None


def test_data_yml_technique_is_the_label(tmp_path: Path) -> None:
    item = tmp_path / "datasets" / "T1003.001" / "atomic_red_team"
    item.mkdir(parents=True)
    (item / "data.yml").write_text("mitre_technique:\n  - T1003.001\n", encoding="utf-8")
    (item / "note.txt").write_text("the write-up says T9999.001\n", encoding="utf-8")
    labels = labels_from_attack_data(
        tmp_path,
        corpus="labelled_corpus",
        publisher="attack_data",
        item_id=lambda publisher, test_id: f"{publisher}:{test_id}",
    )
    assert len(labels) == 1
    assert labels[0].techniques == ("T1003.001",)
    assert labels[0].label_source == "data_yml"
    assert "T9999" not in labels[0].dataset_key


def test_episode_window_is_the_portal_label() -> None:
    labels = labels_from_episodes(
        "portal5_lab",
        ({"episode_id": "ep-1", "start": 10.0, "end": 20.0},),
    )
    assert labels[0].dataset_key == "portal5_lab/ep-1"
    assert labels[0].label_source == "orchestrator_episode"
    assert labels[0].techniques == ()
    with pytest.raises(ValueError):
        labels_from_episodes("portal5_lab", ({"episode_id": "ep-1"},))


def test_units_built_come_from_the_review_receipt() -> None:
    result = SimpleNamespace(
        fingerprint={"fetched_events": "5"},
        receipts=[SimpleNamespace(name="funnel.scored", examined=7, resolved=2)],
        concerns=[],
    )
    observed = observation_from_review(result, benign_events=0)
    assert observed.units_built == 7
    assert observed.units_scored == 2


def test_window_above_the_cap_is_refused() -> None:
    with pytest.raises(ValueError, match="max_events"):
        accept_window_count(201, 200)


def test_runner_stays_on_the_public_review_path_and_off_the_bots_key() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    library = (ROOT / "portal/modules/security/core/review_eval/mixed.py").read_text(
        encoding="utf-8"
    )
    assert disallowed_imports(source, allowed_prefixes=ALLOWED_IMPORTS) == []
    assert "run_review" in source
    assert "BOTS_ANSWER_KEY" not in source
    assert "bots_answer_key" not in source + library
    assert "save_reference" not in source
    assert "AI_Output" not in source
