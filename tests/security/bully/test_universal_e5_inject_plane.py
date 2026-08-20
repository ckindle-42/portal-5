"""E.5 -- generate/inject/capture live plural data plane, fail-closed.
TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1.

Unit-suite-safe: no network, no real lab/Splunk. Exercises both the
fail-closed path (lab genuinely unavailable in CI) AND the live-success
path (`lab_available`, `lab.dispatch_lab_tool`, `live_connect.connect_lab_splunk`
mocked so the "live" branches themselves run, not just the fallback --
this environment has no lab credentials, so this is the only way that code
runs at all short of a real lab)."""

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


# ── live-success path, mocked lab/Splunk plumbing ───────────────────────────
# Exercises the "live" branches themselves (not just the fail-closed
# fallback), since this environment has no real lab credentials.


def test_generate_reaches_live_plane_and_dispatches_every_step(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    dispatched: list[dict] = []

    def _fake_dispatch(tool_name: str, arguments: dict) -> dict:
        dispatched.append({"tool_name": tool_name, "arguments": arguments})
        return {"ok": True, "output": "fake lab output", "elapsed_s": 0.1}

    from portal.modules.security.core import lab as lab_module

    monkeypatch.setattr(lab_module, "dispatch_lab_tool", _fake_dispatch)

    report = ip.generate_labelled_activity()
    assert report.plane == "live"
    assert report.succeeded is True
    total_steps = sum(len(chain["steps"]) for chain in ip._LIVE_CHAINS)
    assert len(report.steps) == total_steps
    assert len(dispatched) == total_steps
    for step in report.steps:
        assert step.ok
        assert step.family
        assert step.technique
        assert step.chain_id


def test_generate_reports_a_failed_step_honestly(monkeypatch) -> None:
    """A dispatch failure must surface as step.ok == False, not be
    swallowed into a false `succeeded`."""
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    from portal.modules.security.core import lab as lab_module

    monkeypatch.setattr(
        lab_module,
        "dispatch_lab_tool",
        lambda tool_name, arguments: {"ok": False, "output": "connection refused"},
    )

    report = ip.generate_labelled_activity()
    assert report.plane == "live"
    assert report.succeeded is False
    assert all(not s.ok for s in report.steps)


def _fake_connect_lab_splunk(plane, *, sample_limit=100, **_kwargs):
    from portal.modules.security.core.bully.connectors import IterableIngestConnector

    records = [
        {
            "eventName": "AssumeRole",
            "userIdentity": {"arn": "arn:aws:iam::111122223333:user/attacker"},
            "eventTime": "2024-01-01T00:00:00Z",
            "awsRegion": "us-east-1",
        },
        {
            "eventName": "ListBuckets",
            "userIdentity": {"arn": "arn:aws:iam::111122223333:user/attacker"},
            "eventTime": "2024-01-01T00:00:40Z",
            "awsRegion": "us-east-1",
        },
    ]
    connector = IterableIngestConnector("lab-splunk", records)
    profile = plane.connect(
        "lab-splunk",
        connector,
        connector.records,
        source_meta={
            "record_class": "telemetry",
            "capabilities": {"queryable_in_place": True, "benign_present": True},
        },
    )
    return profile, {"source_id": "lab-splunk", "records": len(records)}


def test_capture_reaches_live_plane_and_tags_source_id(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    from portal.modules.security.core.bully import live_connect

    monkeypatch.setattr(live_connect, "connect_lab_splunk", _fake_connect_lab_splunk)

    report = ip.capture_records()
    assert report.plane == "live"
    assert report.reason == ""
    assert len(report.records) == 2
    for record in report.records:
        assert record["__source_id"] == "lab-splunk"
        # captured records are raw and untagged (Q3) -- no provenance label
        assert "family" not in record
        assert "injected" not in record


def test_run_inject_capture_reaches_live_plane_and_seals_ground_truth(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    from portal.modules.security.core import lab as lab_module
    from portal.modules.security.core.bully import live_connect

    monkeypatch.setattr(
        lab_module,
        "dispatch_lab_tool",
        lambda tool_name, arguments: {"ok": True, "output": "fake", "elapsed_s": 0.1},
    )
    monkeypatch.setattr(live_connect, "connect_lab_splunk", _fake_connect_lab_splunk)

    run = ip.run_inject_capture(ledger_root=tmp_path)
    assert run.plane == "live"
    assert run.reason == ""
    assert len(run.records) == 2
    total_steps = sum(len(chain["steps"]) for chain in ip._LIVE_CHAINS)
    assert run.sealed_count == total_steps

    ledger = specimen_ledger.SpecimenLedger(tmp_path)
    sealed = ledger.records()
    assert len(sealed) == total_steps
    assert all(row["source_lane"] == "live_lab" for row in sealed)
    assert all(row["provenance"]["injected"] is True for row in sealed)
