"""X.5 -- the generator implants BOTH known-bad and unknown-cousin classes,
sealed per-artifact, leave-one-family-out for the unknown class
(TASK_BULLY_ANALYST_LOOP_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import universe as uv
from portal.modules.security.core.bully.anchors import AnchorLibrary

_KNOWN_SPEC = {
    "chain_id": "cousin-known",
    "parent_family": "known-family",
    "parent_technique": "T1059",
    "behavioural_spine": ["auth", "enumerate", "execute"],
    "implant_class": "known_bad",
}

_UNKNOWN_SPEC = {
    "chain_id": "cousin-unknown",
    "parent_family": "held-out-family",
    "parent_technique": "T1548",
    "behavioural_spine": ["auth", "escalate", "collect"],
    "implant_class": "unknown_cousin",
}


def _build_lot():
    return uv.build_universe(
        n_sources=6,
        background_n=20,
        cousins=[_KNOWN_SPEC, _UNKNOWN_SPEC],
        seed=42,
    )


def test_both_classes_are_sealed_per_artifact():
    lot = _build_lot()
    classes = {t["chain_id"]: t["implant_class"] for t in lot.sealed_truth}
    assert classes == {"cousin-known": "known_bad", "cousin-unknown": "unknown_cousin"}


def test_families_helper_partitions_by_implant_class():
    lot = _build_lot()
    assert lot.families("known_bad") == {"known-family"}
    assert lot.families("unknown_cousin") == {"held-out-family"}


def test_unknown_implant_class_is_rejected():
    import pytest

    bad_spec = dict(_KNOWN_SPEC, implant_class="maybe_bad")
    with pytest.raises(ValueError):
        uv.build_universe(n_sources=4, background_n=5, cousins=[bad_spec], seed=1)


def test_held_out_family_is_absent_from_the_library_the_grader_receives():
    """The seeded proof: a library built to know only the known-bad family
    genuinely never saw the held-out family's technique -- leave-one-
    family-out, not merely a mislabelled entry."""
    lot = _build_lot()
    held_out = lot.families("unknown_cousin")
    known = lot.families("known_bad")
    assert held_out.isdisjoint(known)

    library = AnchorLibrary()
    for t in lot.sealed_truth:
        if t["family"] in held_out:
            continue  # leave-one-family-out: never load the held-out family
        library.load_attack_episode(
            source_id="attack_data",
            record={"action_sequence": t["behavioural_spine"]},
            techniques=(t["technique"],),
        )

    library_techniques = {
        m.get("technique_id") for rec in library.records() for m in rec.get("attack_mappings") or []
    }
    assert "T1059" in library_techniques  # known_bad technique present
    assert "T1548" not in library_techniques  # unknown_cousin technique absent
