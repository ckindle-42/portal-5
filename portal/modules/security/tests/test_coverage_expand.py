"""Unit tests for coverage expansion — meta3 + vulhub breadth.

Verifies:
- Every new scenario carries detect_ground_truth (blue-scorable, operator's rule)
- meta3 scenarios route to the meta3 target
- vulhub scenarios resolve to real container classes
- New techniques have SPL detections or are logged as blue-gaps
- Coverage plan accounts for meta3 + ~50 vulhub categories
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest
import yaml

from portal.modules.security.core._data import EXEC_SEQUENCES
from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.siem.spl_detections import (
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
    "meta3_winrm_weakpass",
    "meta3_tomcat_manager",
    "meta3_jenkins_rce",
    "meta3_glassfish_deploy",
    "meta3_struts_rce",
    "meta3_iis_http",
    "meta3_psexec",
    "meta3_ssh_brute",
    "meta3_manageengine",
    "meta3_axis2_deploy",
    "meta3_webdav_upload",
    "meta3_snmp_enum",
    "meta3_jmx_rce",
    "meta3_wordpress_ninja",
    "meta3_phpmyadmin_rce",
    "meta3_rails_console_rce",
    "meta3_rdp_standard_auth",
]

_VULHUB_EXPANSION_SCENARIOS = [
    "vuln_struts2_rce",
    "vuln_hugegraph_rce",
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
    "vuln_druid_rce",
    "vuln_gitea_rce",
    "vuln_nginx_lfi",
    "vuln_joomla_rce",
    "vuln_wordpress_rce",
    "vuln_phpmyadmin_rce",
    "vuln_spring_actuator",
    "vuln_shellshock_rce",
    "vuln_shiro_deserial",
    "vuln_fastjson_rce",
    "vuln_jackson_deserial",
    "vuln_jimureport_rce",
    "vuln_ajreport_rce",
    "vuln_spring4shell_rce",
    "vuln_nexus_rce",
    "vuln_zabbix_rce",
    "vuln_django_sqli",
    "vuln_thinkphp_rce",
    "vuln_laravel_rce",
    "vuln_rails_rce",
    "vuln_docker_api_rce",
    "vuln_adminer_ssrf_recon",
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
        # De-hardcoded: uses $TARGET_HOST variable, not literal IP
        assert "$TARGET_HOST" in prompt or "10.10.11.10" in prompt, (
            f"meta3 scenario '{name}' does not target $TARGET_HOST or 10.10.11.10"
        )

    @pytest.mark.parametrize("name", _META3_SCENARIOS)
    def test_has_ground_truth(self, name: str):
        gt = SCENARIOS[name].get("detect_ground_truth")
        assert gt and len(gt) >= 1, (
            f"meta3 scenario '{name}' needs at least 1 technique in detect_ground_truth"
        )

    def test_catalog_has_no_linux_only_payloads(self):
        """The Win2k8 catalog must not retain Metasploitable2/Linux payloads."""
        prompts = "\n".join(
            str(scenario["red_prompt"])
            for name, scenario in SCENARIOS.items()
            if name.startswith("meta3_")
        ).lower()
        for invalid in ("port 6200", "udf.so", "/etc/passwd", "/etc/shadow"):
            assert invalid not in prompts, f"Linux-only meta3 payload remains: {invalid}"

    def test_documented_windows_surface_coverage(self):
        assert {
            "meta3_phpmyadmin_rce",
            "meta3_rails_console_rce",
            "meta3_rdp_standard_auth",
        }.issubset(SCENARIOS)

    def test_rdp_technique_has_detection(self):
        assert "T1021.001" in techniques_covered()

    def test_new_surface_steps_use_installed_sandbox_tools(self):
        """The attack image contract includes canonical modules and RDP."""
        ftp = SCENARIOS["meta3_ftp_backdoor"]["red_prompt"]
        phpmyadmin = SCENARIOS["meta3_phpmyadmin_rce"]["red_prompt"]
        rails = SCENARIOS["meta3_rails_console_rce"]["red_prompt"]
        rdp = SCENARIOS["meta3_rdp_standard_auth"]["red_prompt"]
        assert "msfconsole" in phpmyadmin
        assert "phpmyadmin_preg_replace" in phpmyadmin
        assert "msfconsole" in rails
        assert "rails_web_console_v2_code_exec" in rails
        assert "nxc rdp" in rdp
        for prompt in (ftp, rdp):
            assert "$LAB_META3_USER" in prompt
            assert "$LAB_META3_PASS" in prompt

    def test_attack_image_installs_required_meta3_tools(self):
        dockerfile = (Path(__file__).resolve().parents[4] / "Dockerfile.attack").read_text()
        assert "metasploit-framework" in dockerfile
        assert "command -v msfconsole" in dockerfile
        assert "phpmyadmin_preg_replace.rb" in dockerfile
        assert "rails_web_console_v2_code_exec.rb" in dockerfile


class TestLabExerciseImageContract:
    """Executable exercises and the attack image are one enforced contract."""

    @staticmethod
    def _contract() -> dict:
        root = Path(__file__).resolve().parents[4]
        return json.loads((root / "config" / "attack_image_contract.json").read_text())

    @staticmethod
    def _exec_command_heads() -> set[str]:
        heads: set[str] = set()
        for sequence in EXEC_SEQUENCES.values():
            for step in sequence:
                if not isinstance(step, dict) or step.get("tool") != "execute_bash":
                    continue
                lexer = shlex.shlex(
                    step.get("tool_hint", ""), posix=True, punctuation_chars="|&;()<>"
                )
                lexer.whitespace_split = True
                try:
                    tokens = list(lexer)
                except ValueError:
                    continue
                expect_command = True
                for token in tokens:
                    if token in {"&&", "||", ";", "|"}:
                        expect_command = True
                        continue
                    if token in {"&", ">", ">>", "<", "<<", ">&", "(", ")"}:
                        continue
                    if expect_command and token.isdigit():
                        continue
                    if not expect_command:
                        continue
                    if token in {"for", "do", "then"}:
                        continue
                    if token in {"done", "fi"}:
                        expect_command = False
                        continue
                    if "=" in token and token.split("=", 1)[0].replace("_", "").isalnum():
                        continue
                    heads.add(token.rsplit("/", 1)[-1])
                    expect_command = False
        return heads

    def test_contract_is_lab_exercise_only(self):
        assert self._contract()["mode"] == "lab-exercise"
        for theory_only in ("cron_privesc", "container_escape", "kernel_exploit_chain"):
            assert theory_only not in EXEC_SEQUENCES

    def test_all_executable_sequence_command_heads_are_declared(self):
        shell_syntax = {"echo", "export", "false", "null", "sleep", "true", "web_search"}
        undeclared = self._exec_command_heads() - set(self._contract()["tools"]) - shell_syntax
        assert not undeclared, f"lab commands absent from image contract: {sorted(undeclared)}"

    def test_scenario_entry_commands_are_declared(self):
        command_heads = {
            command.rsplit("/", 1)[-1]
            for scenario in SCENARIOS.values()
            for command in re.findall(r"cmd='([A-Za-z0-9_./-]+)", scenario["red_prompt"])
        }
        shell_syntax = {"echo", "for"}
        undeclared = command_heads - set(self._contract()["tools"]) - shell_syntax
        assert not undeclared, f"scenario commands absent from image contract: {sorted(undeclared)}"

    def test_previously_missing_tools_are_hard_requirements(self):
        required = {
            "cadaver",
            "davtest",
            "graphql-cop",
            "nuclei",
            "proxychains",
            "snmpwalk",
            "sshpass",
        }
        assert required.issubset(self._contract()["tools"])

    def test_stale_target_mismatches_cannot_return_to_execution(self):
        corpus = "\n".join(
            step.get("tool_hint", "")
            for sequence in EXEC_SEQUENCES.values()
            for step in sequence
            if isinstance(step, dict)
        ).lower()
        for stale in (
            "port 6200",
            "udf.so",
            "secretsdump.py administrator:<pass>",
            "/usr/share/wordlists/dirb/common.txt",
            "pspy64",
            "docker run -v /:/host",
        ):
            assert stale not in corpus


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
        # De-hardcoded: uses $TARGET_HOST variable, not literal IP
        assert "$TARGET_HOST" in prompt or "10.10.11.50" in prompt, (
            f"Vulhub scenario '{name}' does not target $TARGET_HOST or 10.10.11.50"
        )

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
        yaml_path = (
            Path(__file__).resolve().parents[4]
            / "portal/modules/security/core/siem/spl_detections.yaml"
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
        """The expanded scenario catalog remains broad."""
        assert len(SCENARIOS) >= 70, f"Expected >=70 scenarios, got {len(SCENARIOS)}"

    def test_meta3_no_longer_zero(self):
        """All 24 reconciled Windows scenarios are present."""
        meta3_count = sum(1 for k in SCENARIOS if k.startswith("meta3_"))
        assert meta3_count >= 24, f"meta3 has {meta3_count} scenarios, expected >=24"

    def test_vulhub_breadth(self):
        """Vulhub scenarios should cover >=30 categories."""
        vuln_count = sum(1 for k in SCENARIOS if k.startswith("vuln_"))
        assert vuln_count >= 30, f"Vulhub has {vuln_count} scenarios, expected >=30"
