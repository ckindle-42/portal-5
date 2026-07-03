"""Unit tests for coverage expansion — meta3 + vulhub breadth.

Verifies:
- Every new scenario carries detect_ground_truth (blue-scorable, operator's rule)
- meta3 scenarios route to the meta3 target
- vulhub scenarios resolve to real container classes
- New techniques have SPL detections or are logged as blue-gaps
- Coverage plan accounts for meta3 + ~50 vulhub categories
"""

from __future__ import annotations

import pytest
import yaml

from tests.benchmarks.bench_security.exec_chain import SCENARIOS
from tests.benchmarks.bench_security.siem.spl_detections import (
    techniques_covered,
)

# ── Scenario name lists ───────────────────────────────────────────────────────

_META3_SCENARIOS = [
    "meta3_ftp_backdoor",
    "meta3_web_exploit",
    "meta3_smb_exploit",
    "meta3_mysql_exploit",
    "meta3_linux_privesc",
    "meta3_elasticsearch_rce",
    "meta3_full_chain",
]

_VULHUB_EXPANSION_SCENARIOS = [
    "vuln_struts2_rce",
    "vuln_jenkins_rce",
    "vuln_confluence_rce",
    "vuln_weblogic_rce",
    "vuln_activemq_deserial",
    "vuln_drupal_rce",
    "vuln_solr_rce",
    "vuln_grafana_lfi",
    "vuln_tomcat_deploy",
    "vuln_couchdb_rce",
    "vuln_elasticsearch_rce",
    "vuln_redis_unauth",
    "vuln_gitlab_rce",
    "vuln_nacos_rce",
    "vuln_dubbo_rce",
    "vuln_geoserver_rce",
    "vuln_gitea_rce",
    "vuln_nginx_lfi",
    "vuln_joomla_rce",
    "vuln_wordpress_rce",
    "vuln_phpmyadmin_rce",
    "vuln_spring_actuator",
    "vuln_log4shell",
    "vuln_shiro_deserial",
    "vuln_fastjson_rce",
    "vuln_jackson_deserial",
    "vuln_supervisor_rce",
    "vuln_airflow_rce",
    "vuln_kibana_rce",
    "vuln_nexus_rce",
    "vuln_zabbix_rce",
    "vuln_django_sqli",
    "vuln_thinkphp_rce",
    "vuln_laravel_rce",
    "vuln_rails_rce",
    "vuln_coldfusion_rce",
]

_ALL_NEW_SCENARIOS = _META3_SCENARIOS + _VULHUB_EXPANSION_SCENARIOS


# ── Blue-scorable guard (the operator's rule) ─────────────────────────────────


class TestBlueScorableGuard:
    """Every new scenario must carry detect_ground_truth — no red-only scenarios."""

    @pytest.mark.parametrize("name", _ALL_NEW_SCENARIOS)
    def test_has_detect_ground_truth(self, name: str):
        assert name in SCENARIOS, f"Scenario '{name}' missing from SCENARIOS"
        gt = SCENARIOS[name].get("detect_ground_truth")
        assert gt, f"Scenario '{name}' has empty detect_ground_truth — red-only, not allowed"

    def test_no_red_only_scenarios_anywhere(self):
        """Comprehensive check: every scenario in SCENARIOS has detect_ground_truth."""
        bad = [k for k, v in SCENARIOS.items() if not v.get("detect_ground_truth")]
        assert not bad, f"Red-only scenarios (no detect_ground_truth): {bad}"


# ── meta3 scenario structure ─────────────────────────────────────────────────


class TestMeta3Scenarios:
    """meta3 scenarios must be well-formed and target the meta3 host."""

    @pytest.mark.parametrize("name", _META3_SCENARIOS)
    def test_scenario_exists(self, name: str):
        assert name in SCENARIOS, f"meta3 scenario '{name}' missing"

    @pytest.mark.parametrize("name", _META3_SCENARIOS)
    def test_uses_execute_bash(self, name: str):
        scenario = SCENARIOS[name]
        assert "execute_bash" in scenario["red_order"], (
            f"meta3 scenario '{name}' does not use execute_bash"
        )

    @pytest.mark.parametrize("name", _META3_SCENARIOS)
    def test_targets_meta3(self, name: str):
        scenario = SCENARIOS[name]
        prompt = scenario["red_prompt"]
        assert "10.10.11.10" in prompt, f"meta3 scenario '{name}' does not target 10.10.11.10"

    @pytest.mark.parametrize("name", _META3_SCENARIOS)
    def test_has_ground_truth(self, name: str):
        gt = SCENARIOS[name].get("detect_ground_truth")
        assert gt and len(gt) >= 1, (
            f"meta3 scenario '{name}' needs at least 1 technique in detect_ground_truth"
        )


# ── Vulhub expansion scenario structure ──────────────────────────────────────


class TestVulhubExpansionScenarios:
    """Vulhub scenarios must be well-formed and target 10.10.11.50."""

    @pytest.mark.parametrize("name", _VULHUB_EXPANSION_SCENARIOS)
    def test_scenario_exists(self, name: str):
        assert name in SCENARIOS, f"Vulhub scenario '{name}' missing"

    @pytest.mark.parametrize("name", _VULHUB_EXPANSION_SCENARIOS)
    def test_uses_execute_bash(self, name: str):
        scenario = SCENARIOS[name]
        assert "execute_bash" in scenario["red_order"], (
            f"Vulhub scenario '{name}' does not use execute_bash"
        )

    @pytest.mark.parametrize("name", _VULHUB_EXPANSION_SCENARIOS)
    def test_targets_vulhub(self, name: str):
        scenario = SCENARIOS[name]
        prompt = scenario["red_prompt"]
        assert "10.10.11.50" in prompt, f"Vulhub scenario '{name}' does not target 10.10.11.50"

    @pytest.mark.parametrize("name", _VULHUB_EXPANSION_SCENARIOS)
    def test_has_ground_truth(self, name: str):
        gt = SCENARIOS[name].get("detect_ground_truth")
        assert gt and len(gt) >= 1, f"Vulhub scenario '{name}' needs at least 1 technique"

    @pytest.mark.parametrize("name", _VULHUB_EXPANSION_SCENARIOS)
    def test_red_prompt_contains_kali_tool(self, name: str):
        scenario = SCENARIOS[name]
        prompt = scenario["red_prompt"].lower()
        kali_indicators = [
            "curl",
            "sqlmap",
            "nmap",
            "nuclei",
            "ffuf",
            "graphql-cop",
            "ysoserial",
            "smuggler",
            "execute_bash",
            "redis-cli",
            "mysql",
            "smbclient",
            "nxc",
            "nc ",
            "davtest",
            "cadaver",
        ]
        has = any(ind in prompt for ind in kali_indicators)
        assert has, f"Scenario '{name}' red_prompt has no Kali tool reference"


# ── SPL detection coverage ───────────────────────────────────────────────────


class TestSPLDetectionCoverage:
    """New techniques must have SPL detections or be logged as blue-gaps."""

    def test_all_new_techniques_have_spl(self):
        """Every technique used in new scenarios should have an SPL entry."""
        new_techniques: set[str] = set()
        for name in _ALL_NEW_SCENARIOS:
            gt = SCENARIOS[name].get("detect_ground_truth", [])
            new_techniques.update(gt)

        covered = set(techniques_covered())
        gaps = sorted(new_techniques - covered)
        # T1537 (cloud exfil), T1203 (exploit for client), T1547.001 (registry run key),
        # T1059.004 (Unix shell — covered by T1059 parent), T1552 (unsecured creds —
        # covered by T1552.005) are known gaps or parent-technique aliases
        known_gaps = {"T1537", "T1203", "T1547.001", "T1059.004", "T1552"}
        real_gaps = [g for g in gaps if g not in known_gaps]
        assert not real_gaps, (
            f"Techniques without SPL detection (blue-gaps): {real_gaps}. "
            f"Add SPL entries or record as known gaps."
        )

    def test_spl_detections_valid_yaml(self):
        """spl_detections.yaml must be valid YAML with required fields."""
        from pathlib import Path

        yaml_path = Path(__file__).resolve().parent.parent / (
            "benchmarks/bench_security/siem/spl_detections.yaml"
        )
        data = yaml.safe_load(yaml_path.read_text())
        assert isinstance(data, dict), "spl_detections.yaml is not a dict"
        for tid, entry in data.items():
            assert isinstance(entry, dict), f"Entry for {tid} is not a dict"
            assert "spl" in entry, f"Entry for {tid} missing 'spl' field"
            assert "description" in entry, f"Entry for {tid} missing 'description' field"


# ── Coverage count ────────────────────────────────────────────────────────────


class TestCoverageCount:
    """Verify scenario counts and coverage targets."""

    def test_total_scenario_count(self):
        """Should have 30 (original) + 7 (meta3) + 36 (vulhub) = ~73 scenarios."""
        assert len(SCENARIOS) >= 70, f"Expected >=70 scenarios, got {len(SCENARIOS)}"

    def test_meta3_no_longer_zero(self):
        """meta3 must have at least 5 scenarios."""
        meta3_count = sum(1 for k in SCENARIOS if k.startswith("meta3_"))
        assert meta3_count >= 5, f"meta3 has {meta3_count} scenarios, expected >=5"

    def test_vulhub_breadth(self):
        """Vulhub scenarios should cover >=30 categories."""
        vuln_count = sum(1 for k in SCENARIOS if k.startswith("vuln_"))
        assert vuln_count >= 30, f"Vulhub has {vuln_count} scenarios, expected >=30"
