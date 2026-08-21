"""E.5 -- generate/inject/capture live plural data plane, fail-closed.
TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1.

Unit-suite-safe: no network, no real lab/Splunk. Exercises both the
fail-closed path (lab genuinely unavailable in CI) AND the live-success
path (`lab_available`, `lab.dispatch_lab_tool`, `live_connect.lab_splunk_connector`
mocked so the "live" branches themselves run, not just the fallback).
This plane has also been run for real against the live lab (see
docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.md) when `LAB_SPLUNK_PASSWORD` and
the other lab-exec prerequisites are present in the environment; these
mocked tests keep the live branches covered in CI, where they are not."""

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
    (row,) = ledger.records()
    assert row["specimen_id"].startswith("test-chain-1-step0-run")
    assert row["source_lane"] == "live_lab"
    assert row["provenance"]["family"] == "discovery"
    assert row["provenance"]["technique"] == "T1018"
    assert row["provenance"]["chain_id"] == "test-chain-1"
    assert row["provenance"]["injected"] is True


def test_seal_ground_truth_is_run_scoped_and_does_not_collide_across_runs(
    tmp_path,
) -> None:
    """Seeded regression: `_LIVE_CHAINS`' chain ids are fixed literals, so a
    bare chain_id/step_idx specimen_id would collide with -- and be
    correctly refused by -- a previous run's already-sealed entry every
    time this permanent, run-repeatedly infrastructure runs again."""
    steps = (
        ip.GenerateStep(
            family="discovery",
            technique="T1018",
            chain_id="repeat-chain",
            step_idx=0,
            command="echo hi",
            result={"ok": True, "output": "hi"},
        ),
    )
    report = ip.GenerateReport(plane="live", reason="", steps=steps)
    ip.seal_ground_truth(report, (), root=tmp_path)
    # A second run of the exact same chain must not raise -- it seals under
    # its own run-scoped specimen_id instead of colliding with the first.
    ip.seal_ground_truth(report, (), root=tmp_path)

    ledger = specimen_ledger.SpecimenLedger(tmp_path)
    rows = ledger.records()
    assert len(rows) == 2
    assert len({r["specimen_id"] for r in rows}) == 2


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


def _fake_lab_splunk_connector(*, source_id="lab-splunk", index=None):
    """Mimics `live_connect.lab_splunk_connector`'s real contract: a
    connector whose `.read()` returns the Splunk-wrapper shape
    `SplunkBackend._run_search` actually produces (`_time`/`host` promoted
    out of `fields`), so `capture_records`' unwrap-and-tag logic is
    genuinely exercised, not bypassed."""
    from portal.modules.security.core.bully.connectors import (
        QUERY_IN_PLACE_MODE,
        NativeQuery,
        QueryResult,
    )

    class _FakeConnector:
        source_id = "lab-splunk-plural"
        mode = QUERY_IN_PLACE_MODE

        def translate(self, intent):
            return NativeQuery(self.source_id, "SPL", {"search": "search index=*"}, intent)

        def read(self, intent):
            records = (
                {
                    "_time": 1_700_000_000.0,
                    "host": "10.10.11.21",
                    "raw": "{}",
                    "fields": {
                        "sourcetype": "windows:security",
                        "EventCode": "4624",
                        "TargetUserName": "attacker",
                    },
                },
                {
                    "_time": 1_700_000_040.0,
                    "host": "10.10.11.33",
                    "raw": "{}",
                    "fields": {
                        "sourcetype": "windows:sysmon",
                        "EventID": "1",
                        "Computer": "SRV01.corp.local",
                    },
                },
            )
            return QueryResult(self.source_id, self.mode, self.translate(intent), records, 0.0, 0.0)

    return _FakeConnector()


def test_capture_reaches_live_plane_and_tags_source_id(monkeypatch) -> None:
    monkeypatch.setattr(ip, "lab_available", lambda: (True, ""))

    from portal.modules.security.core.bully import live_connect

    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_lab_splunk_connector)

    report = ip.capture_records(indexes=("portal5_lab",))
    assert report.plane == "live"
    assert report.reason == ""
    assert len(report.records) == 2
    assert report.schemas_present == {"windows:security", "windows:sysmon"}
    for record in report.records:
        assert record["__source_id"].startswith("lab-splunk:")
        assert record.get("host")
        assert record.get("_time")
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
    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_lab_splunk_connector)

    run = ip.run_inject_capture(ledger_root=tmp_path)
    assert run.plane == "live"
    assert run.reason == ""
    # capture now reads every corpus lane (C.3) -- the fake connector returns
    # the same 2 fixture records per index, times 4 default indexes.
    from portal.modules.security.core.bully import corpus_bed as cb

    assert len(run.records) == 2 * len(cb.resolve_indexes())
    total_steps = sum(len(chain["steps"]) for chain in ip._LIVE_CHAINS)
    assert run.sealed_count == total_steps

    ledger = specimen_ledger.SpecimenLedger(tmp_path)
    sealed = ledger.records()
    assert len(sealed) == total_steps
    assert all(row["source_lane"] == "live_lab" for row in sealed)
    assert all(row["provenance"]["injected"] is True for row in sealed)
