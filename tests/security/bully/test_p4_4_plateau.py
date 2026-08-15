"""P4.4 -- PLT statistical plateau + resets (I-12).

Hermetic (no network, no SQL -- pure compute over injected trial data).
FINAL_VALIDATION C10 PLT: <8 valid trials or <2 dimensions -> no plateau;
blocked trials excluded; embedding-cluster-stable but discovery-positive
series does NOT stop; a version change resets the neighborhood.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import plateau


def _trial(i, *, dim="A", **overrides):
    base = {
        "trial_id": f"t-{i}",
        "neighborhood": "nbhd-1",
        "mutation_dim": dim,
        "valid": True,
        "promoted": False,
        "response_state": f"state-{i}",
        "discovery_positive": False,
        "version": "v1",
    }
    return {**base, **overrides}


def _exhausted_series(n=8, version="v1"):
    """A genuinely exhausted series: >=2 dims, no promotions, repeated
    response states (no marginal gain), no discovery in the window."""
    trials = []
    dims = ["A", "B"]
    for i in range(n):
        trials.append(
            _trial(
                i,
                dim=dims[i % 2],
                response_state="state-repeat",  # same state every time -- zero marginal gain
                promoted=False,
                discovery_positive=False,
                version=version,
            )
        )
    return trials


def test_fewer_than_8_valid_trials_is_insufficient_keep_hunting():
    trials = _exhausted_series(n=5)
    decision = plateau.evaluate("nbhd-1", trials, window=10)
    assert decision.decision == "INSUFFICIENT"
    assert decision.action == "continue"


def test_fewer_than_2_mutation_dimensions_is_insufficient():
    trials = [_trial(i, dim="A", response_state="state-repeat") for i in range(10)]
    decision = plateau.evaluate("nbhd-1", trials, window=10)
    assert decision.decision == "INSUFFICIENT"
    assert decision.action == "continue"


def test_blocked_trials_are_excluded_from_every_denominator():
    trials = _exhausted_series(n=8)
    # Pad with a bunch of invalid/blocked trials -- must not count toward
    # the >=8 threshold or shift the window's real content.
    trials = [_trial(100 + i, valid=False) for i in range(20)] + trials
    decision = plateau.evaluate("nbhd-1", trials, window=8)
    assert decision.decision == "PLATEAU"
    assert len(decision.qualifying_trial_ids) == 8


def test_genuinely_exhausted_series_plateaus():
    trials = _exhausted_series(n=8)
    decision = plateau.evaluate("nbhd-1", trials, window=8)
    assert decision.decision == "PLATEAU"
    assert decision.promotions == 0


def test_a_single_promotion_prevents_plateau():
    trials = _exhausted_series(n=8)
    trials[-1] = {**trials[-1], "promoted": True}
    decision = plateau.evaluate("nbhd-1", trials, window=8)
    assert decision.decision == "CONTINUE"
    assert decision.action == "continue"


def test_discovery_positive_series_does_not_stop_even_if_cluster_stable():
    """Embedding-cluster stability (repeated response_state -- the
    'cluster-stable' proxy this build has) is explicitly NOT a stop signal
    on its own: a series that is response-state-stable but still
    discovery-positive must not plateau."""
    trials = []
    dims = ["A", "B"]
    for i in range(10):
        trials.append(
            _trial(
                i,
                dim=dims[i % 2],
                response_state="state-repeat",  # cluster-stable
                discovery_positive=True,  # but still finding novel value
            )
        )
    decision = plateau.evaluate("nbhd-1", trials, window=10)
    assert decision.decision == "CONTINUE"


def test_version_change_resets_the_neighborhood():
    old = _exhausted_series(n=8, version="v1")
    new = [
        _trial(200 + i, dim=["A", "B"][i % 2], response_state="state-repeat", version="v2")
        for i in range(3)
    ]
    trials = old + new
    decision = plateau.evaluate("nbhd-1", trials, window=11)
    assert decision.reset_trigger == "version_change"
    assert decision.reset_version == "v2"
    # Only the 3 post-reset trials qualify -- below the 8-trial floor.
    assert decision.decision == "INSUFFICIENT"
    assert len(decision.qualifying_trial_ids) == 3


def test_rotate_vs_stop_boundary():
    trials = _exhausted_series(n=8)
    rotate = plateau.evaluate("nbhd-1", trials, window=8, has_other_neighborhoods=True)
    stop = plateau.evaluate("nbhd-1", trials, window=8, has_other_neighborhoods=False)
    assert rotate.decision == "PLATEAU" and rotate.action == "rotate"
    assert stop.decision == "PLATEAU" and stop.action == "stop"


def test_neighborhood_locality_ignores_other_neighborhoods():
    trials_a = _exhausted_series(n=8)
    trials_b = [{**t, "trial_id": f"b-{t['trial_id']}", "neighborhood": "nbhd-2"} for t in trials_a]
    decision = plateau.evaluate("nbhd-1", trials_a + trials_b, window=8)
    assert decision.neighborhood == "nbhd-1"
    assert all(tid.startswith("t-") for tid in decision.qualifying_trial_ids)


def test_override_is_a_recorded_policy_exception_with_expiry():
    trials = _exhausted_series(n=8)
    decision = plateau.evaluate(
        "nbhd-1",
        trials,
        window=8,
        override={"reason": "operator wants one more pass", "expiry": 9999999999.0},
        now=1000.0,
    )
    assert decision.decision == "CONTINUE"
    assert decision.action == "continue"
    assert decision.override is not None
    assert decision.expiry == 9999999999.0


def test_expired_override_does_not_suppress_the_plateau():
    trials = _exhausted_series(n=8)
    decision = plateau.evaluate(
        "nbhd-1",
        trials,
        window=8,
        override={"reason": "stale exception", "expiry": 500.0},
        now=1000.0,  # now is past expiry
    )
    assert decision.decision == "PLATEAU"
    assert decision.override is None


def test_override_requires_a_reason_and_expiry():
    trials = _exhausted_series(n=8)
    with pytest.raises(ValueError):
        plateau.evaluate("nbhd-1", trials, window=8, override={"reason": "x"})
    with pytest.raises(ValueError):
        plateau.evaluate("nbhd-1", trials, window=8, override={"expiry": 9999999999.0})
