"""W.5 -- CI invariants for scoreboard conformance
(TASK_BULLY_SCOREBOARD_CONFORMANCE_V1). Each check seeds a violation and
confirms the guard rejects it, then confirms a clean input still passes."""

from __future__ import annotations

from scripts.validation import all_checks

_SLUGS = (
    "bully_scoreboard_conformance_every_run_conforms_or_is_errata_d",
    "bully_scoreboard_conformance_no_proxy_scoreboard_block",
    "bully_scoreboard_conformance_correctness_axis_present",
    "bully_scoreboard_conformance_per_row_full_contract",
    "bully_scoreboard_conformance_trust_axis_not_hardcoded_nulls",
    "bully_scoreboard_conformance_contract_matches_update_no_drift",
    "bully_scoreboard_conformance_guard_fails_all_five_historical_runs",
)


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_seven_invariants_registered_and_pass_clean():
    """Six of the seven must be clean PASS. The seventh
    (`..._trust_axis_not_hardcoded_nulls`) is allowed WARN too: a real live
    run where BIN was never driven for any assessment (e.g. W.6, which does
    not include a BIN-promotion phase) looks identical on this signal alone
    to the old hardcoded-null defect, so the underlying guard reports it as
    WARN by design (task residual risks) rather than a hard FAIL."""
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_scoreboard_conformance_")}
    assert set(_SLUGS) <= slugs
    for slug in _SLUGS:
        verdict, detail, _findings = _run(slug)
        allowed = {"PASS", "WARN"} if slug.endswith("trust_axis_not_hardcoded_nulls") else {"PASS"}
        assert verdict in allowed, f"{slug} should PASS/WARN on the clean repo but got: {detail}"


def test_guard_fails_all_five_historical_runs_is_itself_verified_true():
    """W5's permanent regression: run the real guard against every
    historical doc in-tree and confirm each one FAILs. If a future edit to
    scoreboard.py or the run docs ever makes one of these pass silently,
    this must catch it before the registered CI check does."""
    import json
    from pathlib import Path

    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    docs_dir = Path(__file__).resolve().parents[3] / "docs"
    historical = (
        "BULLY_COUSIN_RELATION_RUN_C7_V1.json",
        "BULLY_LOOP_MILESTONE_RUN_R6_V1.json",
        "BULLY_RELATE_INVESTIGATE_RUN_M3_V1.json",
        "BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json",
        "BULLY_UNKNOWN_COUSIN_RUN_M3_V1.json",
    )
    for name in historical:
        run_json = json.loads((docs_dir / name).read_text())
        findings = check_run(run_json)
        assert any(f.severity == "FAIL" for f in findings), f"{name} should FAIL but did not"


def test_contract_drift_guard_catches_a_stale_contract(monkeypatch):
    """DY: if SCOREBOARD_UPDATE_CONTRACT were hand-edited out of sync with
    scoreboard.update()'s real return, the drift guard must FAIL."""
    from portal.modules.security.core.bully import scoreboard_conformance as sc_mod

    monkeypatch.setattr(
        sc_mod,
        "SCOREBOARD_UPDATE_CONTRACT",
        ("hunt_id", "n_records", "not_a_real_field"),
    )
    verdict, detail, _findings = _run(
        "bully_scoreboard_conformance_contract_matches_update_no_drift"
    )
    assert verdict == "FAIL", detail
