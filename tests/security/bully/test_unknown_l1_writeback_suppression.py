"""L.1 -- outcomes become types; suppression goes live (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_outcome as uo

_VERBS = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]


def _unit(entity: str) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(_VERBS)
    ]
    graph = ag.build_graph(records)
    return next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")


def test_seeded_repeated_benign_closed_unit_is_suppressed_on_second_appearance():
    library = anc.AnchorLibrary()
    baseline = bl.NormalBaseline(environment_id="e")
    baseline.fit([_unit(f"benign-{i}") for i in range(30)])

    first_unit = _unit("someone")
    first_outcome = uo.resolve_unit_outcome(first_unit, list(library.all()), baseline)
    # Nothing in the library yet -- either NOVEL (concern) or NORMAL, never
    # suppressed on the first sighting.
    assert first_outcome.outcome != "RECOGNIZED_NORMAL"

    uo.write_unit_outcome_as_anchor(
        library, first_outcome, source_id="analyst", analyst_disposition="BENIGN_CLOSE"
    )

    second_unit = _unit("someone-else")  # same shape/vocabulary, different entity
    second_outcome = uo.resolve_unit_outcome(second_unit, list(library.all()), baseline)
    assert second_outcome.outcome == "RECOGNIZED_NORMAL"
    assert second_outcome.outcome not in uo.CONCERN_OUTCOMES


def test_a_malicious_cousin_is_never_suppressed_by_a_benign_writeback():
    library = anc.AnchorLibrary()
    baseline = bl.NormalBaseline(environment_id="e")

    benign_unit = _unit("benign-actor")
    benign_outcome = uo.resolve_unit_outcome(benign_unit, list(library.all()), baseline)
    uo.write_unit_outcome_as_anchor(
        library, benign_outcome, source_id="analyst", analyst_disposition="BENIGN_CLOSE"
    )

    # A materially different chain -- not the same shape/vocabulary as the
    # benign-closed unit -- must not be suppressed by it.
    different_records = [
        {"eventName": v, "user": "attacker", "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(["Delete", "Remove", "Terminate", "Encrypt", "Exfiltrate"])
    ]
    graph = ag.build_graph(different_records)
    different_unit = next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")

    outcome = uo.resolve_unit_outcome(different_unit, list(library.all()), baseline)
    assert outcome.outcome != "RECOGNIZED_NORMAL"


def test_confirmed_malicious_writeback_becomes_known_instance_on_repeat():
    library = anc.AnchorLibrary()
    baseline = bl.NormalBaseline(environment_id="e")

    first_unit = _unit("attacker-1")
    first_outcome = uo.resolve_unit_outcome(first_unit, list(library.all()), baseline)
    uo.write_unit_outcome_as_anchor(
        library, first_outcome, source_id="analyst", analyst_disposition="CONFIRMED_MALICIOUS"
    )

    second_unit = _unit("attacker-2")
    second_outcome = uo.resolve_unit_outcome(second_unit, list(library.all()), baseline)
    assert second_outcome.outcome == "KNOWN_INSTANCE"


def test_unknown_analyst_disposition_rejected():
    library = anc.AnchorLibrary()
    baseline = bl.NormalBaseline(environment_id="e")
    outcome = uo.resolve_unit_outcome(_unit("x"), list(library.all()), baseline)
    try:
        uo.write_unit_outcome_as_anchor(
            library, outcome, source_id="analyst", analyst_disposition="MAYBE"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown analyst disposition")
