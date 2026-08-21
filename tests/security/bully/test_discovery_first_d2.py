"""D.2 -- `resolve_unit_outcome` resolves discovery-first
(TASK_BULLY_DISCOVERY_FIRST_V1). The library never triggers a concern by
itself (D1); it only suppresses (RECOGNIZED_NORMAL) or floors
(KNOWN_INSTANCE), both accumulated knowledge, never a catalogue lookup."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_outcome as uo
from tests.security.bully.test_unknown_v2_unit_outcome import (
    _benign_l4_units,
    _empty_baseline,
    _unit,
)

_ATTACKER_VERBS = [
    "AssumeRole",
    "GetSessionToken",
    "AttachUserPolicy",
    "PutBucketPolicy",
    "DeleteBucket",
    "PutObject",
    "AssumeRole",
    "AttachUserPolicy",
    "DeleteBucket",
]


def _populated_baseline(*, steps: int) -> bl.NormalBaseline:
    model = bl.NormalBaseline(environment_id="env")
    model.fit(_benign_l4_units(50, steps=steps))
    return model


def test_remarkable_coherent_unit_matching_nothing_is_surfaced():
    """Under the old library-first order this was only ever reachable via
    the fallback, and never at all once the library matched everything
    elsewhere in the run. Discovery-first surfaces it unconditionally."""
    model = _populated_baseline(steps=len(_ATTACKER_VERBS))
    unit = _unit(_ATTACKER_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, [], model)
    assert outcome.outcome == "NOVEL"
    assert outcome.outcome in uo.CONCERN_OUTCOMES
    assert outcome.brief is not None


def test_known_bad_but_unremarkable_surfaces_at_the_floor_never_the_headline():
    """A unit matching a known-bad type but unremarkable for THIS
    environment is still KNOWN_INSTANCE -- an already-actioned instance is
    accumulated knowledge, not a discovery decision (P1) -- but it must
    never outrank a genuine concern in report order."""
    library = anc.AnchorLibrary()
    library.load_detection_coverage(source_id="det", detection_id="det-1")
    library._anchors["det-1"].record.update({"action_sequence": _ATTACKER_VERBS})
    known_unit = _unit(_ATTACKER_VERBS, "known-attacker")
    known_outcome = uo.resolve_unit_outcome(known_unit, list(library.all()), _empty_baseline())
    assert known_outcome.outcome == "KNOWN_INSTANCE"

    model = _populated_baseline(steps=len(_ATTACKER_VERBS))
    novel_outcome = uo.resolve_unit_outcome(_unit(_ATTACKER_VERBS, "novel"), [], model)
    assert novel_outcome.outcome == "NOVEL"

    ranked = uo.sort_for_report([known_outcome, novel_outcome])
    assert ranked[0].outcome != "KNOWN_INSTANCE"
    assert ranked[-1].outcome == "KNOWN_INSTANCE"


def test_library_match_alone_never_triggers_a_concern():
    """D1: no code path may make surfacing conditional on a catalogue match
    alone. An EXACT library match on a unit that is unremarkable for this
    environment must resolve NORMAL, not UNKNOWN_SAME/COUSIN."""
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _ATTACKER_VERBS}, techniques=("T1078",)
    )
    unit = _unit(_ATTACKER_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, list(library.all()), _empty_baseline())
    assert outcome.outcome == "NORMAL"
    assert outcome.brief is None
