"""B.3 -- observed investigation entry mode: observed runs never enter
MUTATION/EXECUTING; the provoked path is unregressed."""

from __future__ import annotations

from portal.modules.security.core.bully import contracts, observed_mode


class _Seed:
    seed_id = "seed-obs-1"


def test_observed_run_never_enters_mutation_or_executing():
    run = observed_mode.run_observed(
        _Seed(),
        scope_fn=lambda seed: {"seed_id": seed.seed_id, "records": []},
        relate_fn=lambda scope: {"verdict": "ANOMALOUS_UNCLASSIFIED"},
        investigate_fn=lambda scope, relation: {"note": "observed"},
        grade_fn=lambda scope, investigation: {"gate": "n/a"},
        promote_fn=lambda scope, grade: {"queued": False},
        compound_fn=lambda scope, promotion: {"anchor_written": False},
    )
    assert set(run.stages_entered).isdisjoint(observed_mode.FORBIDDEN_STAGES)
    assert run.stages_entered == [
        "SCOPING",
        "RELATING",
        "INVESTIGATING",
        "GRADING",
        "PROMOTING",
        "COMPOUNDING",
        "CLOSED",
    ]
    assert run.current_stage == "CLOSED"


def test_default_hooks_are_honest_noops_not_fabricated_results():
    run = observed_mode.run_observed(_Seed(), scope_fn=lambda seed: {"seed_id": seed.seed_id})
    assert run.evidence["relation"] is None
    assert run.evidence["investigation"] is None
    assert run.current_stage == "CLOSED"


def test_illegal_observed_transition_rejected():
    run = observed_mode.ObservedRun(run_id="obs-x", seed_id="s")
    run.enter("SCOPING")
    try:
        run.enter("PROMOTING")  # skip RELATING/INVESTIGATING/GRADING
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on illegal skip-ahead transition")


def test_provoked_hunt_stage_machine_is_unregressed():
    # B.3 adds a wholly separate observed stage machine; the provoked hunt
    # machine (contracts.HUNT_STAGES) still carries MUTATION_READY and
    # EXECUTING and its own legality function is untouched.
    assert "MUTATION_READY" in contracts.HUNT_STAGES
    assert "EXECUTING" in contracts.HUNT_STAGES
    assert contracts.is_legal_hunt_transition("TARGETED", "MUTATION_READY")
    assert contracts.is_legal_hunt_transition("MUTATION_READY", "EXECUTING")


def test_observed_and_provoked_stage_names_do_not_collide():
    assert set(observed_mode.OBSERVED_STAGES) & set(contracts.HUNT_STAGES) <= {
        "BLOCKED",
        "CANCELLED",
        "FAILED",
        "CLOSED",
        "PROMOTING",
        "COMPOUNDING",
    }
