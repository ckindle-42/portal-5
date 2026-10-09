"""Intake on production-SHAPED multi-source windows, and the anchor index.

Each test exists because the thing it checks was once silently wrong: one role map for a whole
window, entities that never linked across sources, and a 512-unit cap hidden behind a
docstring that said "never an arbitrary subset"."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.review import intake, knowledge

from ._fakes import HashEmbedder, three_source_window, windows_records


def test_every_source_gets_its_own_roles_and_none_is_blind() -> None:
    result = intake.build_window_units(three_source_window(seed=2, n=300))
    assert result.blind_sources == []
    sources = [r for r in result.receipts if r.name == "intake.sources"][0]
    assert (sources.examined, sources.resolved) == (3, 3)


def test_units_are_not_capped_at_the_library_default() -> None:
    n = ag.MAX_UNITS_PER_LEVEL + 188  # 700 > 512
    result = intake.build_window_units({"wineventlog": windows_records(n, seed=5)})
    level_one = [u for u in result.units if u.unit.level == "L1_ARTIFACT"]
    assert len(level_one) == n  # the library default would have returned 512
    receipt = [r for r in result.receipts if r.name == "intake.units"][0]
    assert receipt.examined == n and "uncapped" in receipt.note


def test_entities_link_across_differently_named_fields() -> None:
    result = intake.build_window_units(three_source_window(seed=4, n=300))
    cross = [u for u in result.units if u.unit.level == "L2_ENTITY" and len(u.source_ids) > 1]
    assert cross, "host/hostname share values; value-based resolution must link them"


def test_every_unit_event_id_resolves_to_a_rendered_event() -> None:
    result = intake.build_window_units(three_source_window(seed=6, n=200, attacker="evil"))
    for unit in result.units:
        assert unit.event_ids
        for event_id in unit.event_ids:
            view = result.events[event_id]
            assert view.text and view.source_id == event_id.rsplit(":", 1)[0]


def test_unit_cards_are_content_first_and_label_free() -> None:
    result = intake.build_window_units(three_source_window(seed=8, n=300, attacker="evil"))
    attack = [u for u in result.units if any("certutil" in t for t in u.terms)]
    assert attack, "the attack's command line must reach the card as a masked value term"
    assert all(u.card.startswith("sources: ") for u in result.units)
    assert "values:" in attack[0].card


def test_compress_classes_is_bounded() -> None:
    text = intake.compress_classes(["other"] * 500 + ["execute"] * 3, max_runs=12)
    assert text == "other*500 > execute*3"
    many = intake.compress_classes([str(i) for i in range(40)], max_runs=12)
    assert many.endswith("(+28 runs)")


def test_event_id_ignores_internal_keys_and_is_stable() -> None:
    a = intake.event_id_for("s", {"x": 1, "__source_id": "s"})
    b = intake.event_id_for("s", {"x": 1})
    assert a == b and intake.event_id_for("s", {"x": 2}) != a


def test_anchor_index_search_and_exclusion() -> None:
    embedder = HashEmbedder()
    cards = [
        knowledge.AnchorCard(
            "a1", "attack_episode", "cred-dump", "malicious", "certutil urlcache payload", {}
        ),
        knowledge.AnchorCard(
            "a2", "benign_pattern", "browser", "benign", "chrome renderer sandbox", {}
        ),
    ]
    index = knowledge.AnchorIndex.build(cards, embedder)
    queries = knowledge.embed_texts(embedder, ["certutil urlcache download", "chrome renderer"])
    hits = index.search(queries, k=2)
    assert hits[0][0][0].anchor_id == "a1" and hits[1][0][0].anchor_id == "a2"
    excluded = index.search(queries[:1], k=2, exclude=[frozenset({"a1"})])
    assert [c.anchor_id for c, _ in excluded[0]] == ["a2"]
    assert index.population == 2 and index.kinds == ("attack_episode", "benign_pattern")


def test_quarantined_anchors_are_not_knowledge() -> None:
    class Fake:
        def __init__(self, quarantined: bool) -> None:
            self.anchor_id = "x"
            self.kind = "attack_episode"
            self.malice = "malicious"
            self.record = {"card": "some card text"}
            self.quarantined = quarantined

    assert knowledge.cards_from_anchors([Fake(True)]) == []
    assert len(knowledge.cards_from_anchors([Fake(False)])) == 1


def test_the_classifier_is_an_explicit_arm() -> None:
    window = three_source_window(seed=12, n=200)
    default = intake.build_window_units(window)
    none = intake.build_window_units(window, classifier=intake.NoClassifier())
    default_classes = {
        c for u in default.units for c in u.unit.structural_signature.get("class_sequence") or ()
    }
    none_classes = {
        c for u in none.units for c in u.unit.structural_signature.get("class_sequence") or ()
    }
    assert none_classes == {"unclassified"}
    assert default_classes != {"unclassified"}  # the curated default classifies something
    assert len(none.units) == len(default.units)  # classes change shape tokens, not the unit set
