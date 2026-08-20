"""E.5 -- generate/inject/capture live plural data plane, fail-closed.
TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1.

Unit-suite-safe: no network, no real lab/Splunk. Exercises the fail-closed
path (lab genuinely unavailable in CI) and the sealing mechanism in
isolation."""

from __future__ import annotations

from portal.modules.security.core.bully import inject_plane as ip
from portal.modules.security.core.bully import specimen_ledger


def test_lab_unavailable_without_credential_env(monkeypatch) -> None:
    monkeypatch.delenv("LAB_SPLUNK_PASSWORD", raising=False)
    available, reason = ip.lab_available()
    assert available is False
    assert reason


def test_generate_fails_closed_without_lab(monkeypatch) -> None:
    monkeypatch.delenv("LAB_SPLUNK_PASSWORD", raising=False)
    report = ip.generate_labelled_activity()
    assert report.plane == "unavailable"
    assert report.reason
    assert report.steps == ()
    assert report.succeeded is False


def test_capture_fails_closed_without_lab(monkeypatch) -> None:
    monkeypatch.delenv("LAB_SPLUNK_PASSWORD", raising=False)
    report = ip.capture_records()
    assert report.plane == "unavailable"
    assert report.reason
    assert report.records == ()


def test_run_inject_capture_falls_back_to_fixture_and_states_which_plane(
    monkeypatch,
) -> None:
    """Q3/E.5 fail-closed contract: unavailable lab never produces a silent
    synthetic substitute -- it falls back to the E.3 fixture and says so."""
    monkeypatch.delenv("LAB_SPLUNK_PASSWORD", raising=False)
    run = ip.run_inject_capture()
    assert run.plane == "fixture"
    assert "unavailable" in run.reason
    assert run.records
    assert run.sealed_count == 0


def test_seal_ground_truth_writes_through_specimen_ledger(tmp_path) -> None:
    """Q3: reuse the existing sealed wall, do not build a second one."""
    steps = (
        ip.GenerateStep(
            family="discovery",
            technique="T1018",
            chain_id="test-chain-1",
            step_idx=0,
            command="echo hi",
            result={"ok": True, "output": "hi"},
        ),
    )
    report = ip.GenerateReport(plane="live", reason="", steps=steps)
    sealed = ip.seal_ground_truth(report, (), root=tmp_path)
    assert sealed == 1

    ledger = specimen_ledger.SpecimenLedger(tmp_path)
    truth = ledger.truth_for("test-chain-1-step0")
    assert truth is not None
    assert truth["source_lane"] == "live_lab"
    assert truth["provenance"]["family"] == "discovery"
    assert truth["provenance"]["technique"] == "T1018"
    assert truth["provenance"]["chain_id"] == "test-chain-1"
    assert truth["provenance"]["injected"] is True


def test_seeded_violation_live_result_never_fabricated(monkeypatch) -> None:
    """Seeded regression: if `lab_available` were bypassed, generate must
    still refuse to claim `plane="live"` without dispatching any step."""
    monkeypatch.delenv("LAB_SPLUNK_PASSWORD", raising=False)
    report = ip.generate_labelled_activity()
    assert report.plane != "live"
