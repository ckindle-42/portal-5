"""Regression test — run_purple_tests(replay_captured_red=True) must not crash
when no captured red evidence exists for a scenario.

Found live 2026-07-05 during the E2E system replay (EXEC_SEC_E2E_SYSTEM_V1):
`vuln_weblogic_rce`'s vulhub CVE stack is permanently unreachable on this lab
(SKIP: target-unrecoverable even during live capture), so it never gets red
evidence no matter how many times capture/replay runs. Previously, hitting
this case during --all-scenarios crashed the ENTIRE run with an unhandled
KeyError (red_cache[rm] where rm was never inserted) — aborting every
remaining scenario's results, not just the one with missing evidence. The fix
returns one honest UNAVAILABLE record per requested blue model instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from portal.modules.security.core._config import BenchConfig
from portal.modules.security.core.blue import run_purple_tests


class TestReplayCapturedRedNoEvidence:
    def test_no_crash_when_no_evidence_exists(self):
        """A scenario name guaranteed to have no capture/evidence on disk must
        return honest UNAVAILABLE results, never raise."""
        scenario = {
            "name": "test_scenario_definitely_has_no_captured_evidence_xyz",
            "detect_ground_truth": ["T9999.999"],
            "persistence_technique": "",
            "target_host": None,
        }
        cfg = BenchConfig()

        results = run_purple_tests(
            ["some-red-model"],
            ["some-blue-model"],
            scenario,
            cfg,
            dry_run=False,
            lab_exec=False,
            replay_captured_red=True,
        )

        assert len(results) == 1
        rec = results[0]
        assert rec["capability_verdict"] == "UNAVAILABLE"
        assert rec["blue_model"] == "some-blue-model"
        assert rec["match_grade"] == "NONE"
        assert rec["telemetry_collection_error"] == "NO_CAPTURED_RED_EVIDENCE"

    def test_multiple_blue_models_each_get_a_record(self):
        scenario = {
            "name": "test_scenario_definitely_has_no_captured_evidence_xyz",
            "detect_ground_truth": ["T9999.999"],
            "persistence_technique": "",
            "target_host": None,
        }
        cfg = BenchConfig()

        results = run_purple_tests(
            ["some-red-model"],
            ["blue-a", "blue-b"],
            scenario,
            cfg,
            dry_run=False,
            lab_exec=False,
            replay_captured_red=True,
        )

        assert {r["blue_model"] for r in results} == {"blue-a", "blue-b"}
        assert all(r["capability_verdict"] == "UNAVAILABLE" for r in results)

    def test_unavailable_never_masquerades_as_proven(self):
        scenario = {
            "name": "test_scenario_definitely_has_no_captured_evidence_xyz",
            "detect_ground_truth": ["T9999.999"],
            "persistence_technique": "",
            "target_host": None,
        }
        cfg = BenchConfig()
        results = run_purple_tests(["m"], ["m"], scenario, cfg, replay_captured_red=True)
        assert all(r["capability_verdict"] != "PROVEN" for r in results)
