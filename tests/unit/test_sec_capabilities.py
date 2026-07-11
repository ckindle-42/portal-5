"""Tests for Phase 2-4 capability modules (synthetic/dry-run only)."""

from __future__ import annotations


class TestCTFBench:
    def test_flag_oracle_matches(self):
        from portal.modules.security.core.ctf_bench import flag_oracle

        assert flag_oracle("flag{correct}", "flag{correct}") is True
        assert flag_oracle("wrong", "flag{correct}") is False

    def test_dry_run_plans(self):
        from portal.modules.security.core.ctf_bench import bench_ctf

        result = bench_ctf("/tmp/challenge", dry_run=True)
        assert result["status"] == "dry_run"


class TestDecisionEngine:
    def test_select_tools_with_observations(self):
        from portal.modules.security.core.decision_engine import select_tools

        result = select_tools(
            {"open_ports": True},
            ["run_nmap_scan", "check_cve", "exploit_service"],
        )
        assert len(result) > 0

    def test_select_tools_empty_observations(self):
        from portal.modules.security.core.decision_engine import select_tools

        result = select_tools({}, ["run_nmap_scan", "check_cve"])
        assert len(result) > 0


class TestLLMRedTeam:
    def test_dry_run_plans(self):
        from portal.modules.security.core.llm_redteam import bench_llm_redteam

        result = bench_llm_redteam("auto-security", dry_run=True)
        assert result["status"] == "dry_run"


class TestBenchIntegration:
    def test_full_expanded_runs(self):
        from portal.modules.security.core.bench_integration import run_full_expanded_bench

        result = run_full_expanded_bench(dry_run=True)
        assert result["status"] == "dry_run"
        assert "steps" in result


class TestFirmwareRE:
    def test_dry_run_plans(self):
        from portal.modules.security.core.re_firmware import bench_firmware_extract

        result = bench_firmware_extract("/tmp/fw.bin", dry_run=True)
        assert result["status"] == "dry_run"
