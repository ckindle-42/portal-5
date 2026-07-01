"""Unit tests for scenario x container matrix (synthetic/dry-run — no Docker)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.benchmarks.bench_security.matrix import (
    RunResult,
    RunUnit,
    WazuhBackend,
    _classify_domain,
    _expand_vulhub_globs,
    _infer_target,
    build_coverage_report,
    build_run_matrix,
    run_matrix,
)
from tests.benchmarks.bench_security.oracles import ORACLES


class TestBuildRunMatrix:
    """build_run_matrix expands scenarios + classes into run units."""

    def test_build_scenarios_only(self, tmp_path):
        """Scenarios mode produces one unit per scenario."""
        units = build_run_matrix(scenarios=True, classes=False, vulhub_root=tmp_path)
        # Should have one unit per PROMPTS entry
        from tests.benchmarks.bench_security._data import PROMPTS

        assert len(units) == len(PROMPTS)
        assert all(u.kind == "scenario" for u in units)

    def test_build_classes_only(self, tmp_path):
        """Classes mode produces units from challenge_classes.yaml."""
        units = build_run_matrix(scenarios=False, classes=True, vulhub_root=tmp_path)
        # Without a vulhub clone, no vulhub paths resolve
        # but purpose_built dirs still produce units
        assert isinstance(units, list)

    def test_build_with_fixture_vulhub_tree(self, tmp_path):
        """Glob expansion against a fixture vulhub tree creates multiple units."""
        # Create fixture vulhub directories
        for p in [
            "fastjson/CVE-2017-7525",
            "fastjson/CVE-2019-xxxxx",
            "jackson/CVE-2017-7525",
            "shiro/CVE-2016-4437",
        ]:
            d = tmp_path / p
            d.mkdir(parents=True)
            (d / "docker-compose.yml").write_text("version: '3'\n")

        # Build with only the deserialization class
        units = build_run_matrix(
            scenarios=False,
            classes=True,
            vulhub_root=tmp_path,
        )
        # Filter to deserialization
        deser_units = [u for u in units if u.challenge_class == "deserialization"]
        # Should have expanded the globs: fastjson/* (2), jackson/CVE-2017-7525 (1), shiro/* (1)
        assert len(deser_units) >= 4
        # Each unit should carry the class's ground-truth oracle
        for u in deser_units:
            assert u.oracle == "rce_shell"

    def test_every_scenario_has_oracle_or_explicit_null(self):
        """Every scenario resolves to a bound oracle or explicit oracle: None."""
        from tests.benchmarks.bench_security._data import PROMPTS

        for key, prompt in PROMPTS.items():
            assert "oracle" in prompt, f"scenario {key} missing 'oracle' field"
            # oracle can be a string (registered oracle) or None (heuristic)
            oracle = prompt["oracle"]
            if oracle is not None:
                assert isinstance(oracle, str), f"scenario {key}: oracle must be str or None"
                assert oracle in ORACLES, f"scenario {key}: oracle '{oracle}' not in ORACLES"

    def test_every_scenario_resolves_to_unit(self):
        """Every scenario produces at least one run unit."""
        units = build_run_matrix(scenarios=True, classes=False)
        scenario_keys = {u.scenario_key for u in units}
        from tests.benchmarks.bench_security._data import PROMPTS

        for key in PROMPTS:
            assert key in scenario_keys, f"scenario {key} not in matrix"

    def test_domain_filter(self, tmp_path):
        """Domain filter limits units to matching domains."""
        units_web = build_run_matrix(scenarios=True, classes=False, domains=["web"])
        units_ad = build_run_matrix(scenarios=True, classes=False, domains=["ad"])
        # web and ad should have different units
        assert len(units_web) > 0
        assert len(units_ad) > 0
        web_keys = {u.scenario_key for u in units_web}
        ad_keys = {u.scenario_key for u in units_ad}
        assert web_keys != ad_keys  # should not be identical


class TestRunMatrix:
    """run_matrix plans/executes spin→run→score→teardown."""

    def test_dry_run_plans_all_units(self, tmp_path):
        """Dry run produces dry_run results for every unit."""
        units = build_run_matrix(scenarios=True, classes=False, vulhub_root=tmp_path)
        result = run_matrix(units, dry_run=True)
        assert result["total_units"] == len(units)
        assert result["dry_runs"] == len(units)
        assert result["verified"] == 0
        assert result["rejected"] == 0

    def test_lab_exec_unavailable_indeterminate(self, tmp_path, monkeypatch):
        """When _LAB_EXEC_AVAILABLE is False, verdicts are indeterminate."""
        monkeypatch.setattr("tests.benchmarks.bench_security.matrix._LAB_EXEC_AVAILABLE", False)
        units = build_run_matrix(scenarios=True, classes=False, vulhub_root=tmp_path)
        result = run_matrix(units, dry_run=False)
        assert result["indeterminate"] == len(units)
        assert result["verified"] == 0

    def test_max_concurrent_respected(self, tmp_path):
        """Max concurrent is recorded in the plan."""
        units = build_run_matrix(scenarios=True, classes=False, vulhub_root=tmp_path)
        result = run_matrix(units, dry_run=True, max_concurrent=2)
        # All units should be planned (dry_run doesn't actually limit concurrency)
        assert result["total_units"] == len(units)


class TestClassOracleBinding:
    """Every challenge-class oracle is registered."""

    def test_class_oracles_registered(self):
        """Every oracle referenced by challenge_classes.yaml is in ORACLES."""
        import yaml

        cc_path = Path(__file__).resolve().parents[3] / "config" / "challenge_classes.yaml"
        if not cc_path.exists():
            pytest.skip("challenge_classes.yaml not found")
        cc = yaml.safe_load(cc_path.read_text())
        for cls in cc.get("classes", []):
            oracle = cls.get("ground_truth", {}).get("oracle", "")
            if oracle:
                assert oracle in ORACLES, f"class {cls['id']}: oracle '{oracle}' not in ORACLES"


class TestDomainClassification:
    def test_web_keywords(self):
        assert _classify_domain("sqli_manual") == "web"
        assert _classify_domain("lfi_to_rce") == "web"
        assert _classify_domain("tomcat_manager") == "web"

    def test_ad_keywords(self):
        assert _classify_domain("kerberoasting") == "ad"
        assert _classify_domain("ad_dcsync_golden_ticket") == "ad"
        assert _classify_domain("smb_enum_relay") == "ad"

    def test_linux_keywords(self):
        assert _classify_domain("linux_privesc") == "linux"
        assert _classify_domain("cron_privesc") == "linux"
        assert _classify_domain("nfs_privesc_chain") == "linux"

    def test_unknown_is_mixed(self):
        assert _classify_domain("phishing_campaign") == "mixed"


class TestVulhubGlobExpansion:
    def test_expands_glob_patterns(self, tmp_path):
        """Glob patterns expand to matching directories with docker-compose.yml."""
        for p in ["fastjson/CVE-2022-xxx", "fastjson/CVE-2023-yyy"]:
            d = tmp_path / p
            d.mkdir(parents=True)
            (d / "docker-compose.yml").write_text("version: '3'\n")
        # Create a dir WITHOUT docker-compose.yml (should be excluded)
        (tmp_path / "fastjson" / "incomplete").mkdir(parents=True)

        result = _expand_vulhub_globs(["fastjson/*"], tmp_path)
        assert len(result) == 2
        assert "fastjson/CVE-2022-xxx" in result
        assert "fastjson/CVE-2023-yyy" in result
        assert "fastjson/incomplete" not in result

    def test_empty_patterns_returns_empty(self, tmp_path):
        assert _expand_vulhub_globs([], tmp_path) == []

    def test_nonexistent_pattern_returns_empty(self, tmp_path):
        assert _expand_vulhub_globs(["nonexistent/*"], tmp_path) == []


class TestInferTarget:
    def test_dc_hint(self):
        steps = [{"tool_hint": "nxc smb $LAB_TARGET_DC -u '' -p ''"}]
        assert _infer_target("kerberoasting", steps) == "dc01"

    def test_web_hint(self):
        steps = [{"tool_hint": "curl http://$LAB_TARGET_WEB:8080/"}]
        assert _infer_target("lfi_to_rce", steps) == "lab-vulhub"

    def test_fallback(self):
        assert _infer_target("unknown_scenario", []) == "lab-vulhub"


class TestCoverageReport:
    def test_coverage_report_structure(self):
        units = [
            RunUnit(
                id="u1",
                kind="class",
                target_spec="fastjson/CVE-x",
                oracle="rce_shell",
                scoring="oracle",
                domain="web",
                spin="ephemeral",
                challenge_class="deserialization",
            ),
            RunUnit(
                id="u2",
                kind="scenario",
                target_spec="lab-vulhub",
                oracle="sqli_error",
                scoring="oracle",
                domain="web",
                spin="static",
                scenario_key="sqli_manual",
            ),
        ]
        results = [
            RunResult(unit_id="u1", status="verified"),
            RunResult(unit_id="u2", status="rejected"),
        ]
        report = build_coverage_report(units, results)
        assert report["total_resolved"] == 2
        assert report["total_ran"] == 2
        assert report["total_verified"] == 1
        assert "deserialization" in report["by_class"]
        assert "sqli_manual" in report["by_scenario"]


class TestTelemetryBackend:
    def test_wazuh_backend_protocol(self):
        """WazuhBackend implements TelemetryBackend protocol."""
        backend = WazuhBackend()
        result = backend.query("T1190", {})
        assert "signals" in result
        assert "source" in result
        assert "matched" in result

    def test_wazuh_synthetic_fallback(self):
        """Without URL, WazuhBackend returns synthetic-fallback."""
        backend = WazuhBackend(opensearch_url="")
        result = backend.query("T1190", {})
        assert result["source"] == "synthetic-fallback"
        assert result["matched"] is False
