"""Unit tests for the candidate intake pipeline.

After M6-B1, the implementation lives in bench_security.intake.
Monkeypatches must target bench_security.intake (the module where the
functions are actually defined) rather than the chain re-export shim.
"""


def test_run_candidate_intake_dry_run() -> None:
    from portal.modules.security.core.chain import run_candidate_intake

    results = run_candidate_intake(["fake/model-a", "fake/model-b"], dry_run=True)
    assert len(results) == 2
    assert all(r["queued"] for r in results)
    assert all(r["skip_reason"] is None for r in results)


def test_tps_floor_constant() -> None:
    from portal.modules.security.core.chain import TPS_FLOOR

    assert TPS_FLOOR == 20.0


def test_pull_timeout_constant() -> None:
    from portal.modules.security.core.chain import PULL_TIMEOUT_S

    assert PULL_TIMEOUT_S == 900.0
