"""Unit tests for web-exploit scenario coverage.

Verifies:
- New web scenarios have valid structure (execute_bash in red_order, detect_ground_truth)
- Each scenario's red_prompt contains a real Kali command
- Coverage crediting works for bash-achieved steps (parity with wrappers)
- No tools proliferated beyond execute_bash/execute_python
"""

from __future__ import annotations

import pytest

from tests.benchmarks.bench_security.exec_chain import (
    _BASH_TECHNIQUE_SIGNALS,
    CHAIN_TOOLS_BASE,
    INLINE_TOOLS,
    SCENARIOS,
)
from tests.benchmarks.bench_security.scoring import accumulate_observations

# ── Web scenario structure ────────────────────────────────────────────────────

_WEB_SCENARIO_NAMES = [
    "web_sqli_dump",
    "web_graphql_introspect",
    "web_deserial_rce",
    "web_nosql_inject",
    "web_path_traversal",
    "web_reflected_xss",
    "web_cors",
    "web_open_redirect",
    "web_forced_error",
    "web_asset_discovery",
    "web_smuggling",
    "web_ssti",
    "web_upload_bypass",
    "web_idor",
    "web_ssrf",
    "web_ssti_stored",
    "web_header_injection",
    "web_cache_deception",
    "web_nuclei_scan",
]


class TestWebScenarioStructure:
    """Each web scenario must have valid structure."""

    @pytest.mark.parametrize("name", _WEB_SCENARIO_NAMES)
    def test_scenario_exists(self, name: str):
        assert name in SCENARIOS, f"Scenario '{name}' missing from SCENARIOS"

    @pytest.mark.parametrize("name", _WEB_SCENARIO_NAMES)
    def test_uses_execute_bash(self, name: str):
        scenario = SCENARIOS[name]
        assert "execute_bash" in scenario["red_order"], (
            f"Scenario '{name}' does not use execute_bash"
        )

    @pytest.mark.parametrize("name", _WEB_SCENARIO_NAMES)
    def test_has_detect_ground_truth(self, name: str):
        scenario = SCENARIOS[name]
        assert scenario.get("detect_ground_truth"), f"Scenario '{name}' has no detect_ground_truth"

    @pytest.mark.parametrize("name", _WEB_SCENARIO_NAMES)
    def test_red_prompt_contains_kali_command(self, name: str):
        """Every scenario's red_prompt must mention a real Kali tool or command."""
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
        ]
        has_indicator = any(ind in prompt for ind in kali_indicators)
        assert has_indicator, f"Scenario '{name}' red_prompt contains no Kali tool reference"

    @pytest.mark.parametrize("name", _WEB_SCENARIO_NAMES)
    def test_targets_lxc_112(self, name: str):
        """All web scenarios must target 10.10.11.50 (LXC 112)."""
        scenario = SCENARIOS[name]
        assert "10.10.11.50" in scenario["red_prompt"], (
            f"Scenario '{name}' does not target 10.10.11.50"
        )


# ── Coverage crediting parity ─────────────────────────────────────────────────


class TestCoverageCrediting:
    """Steps achieved via execute_bash get coverage credit (parity with wrappers)."""

    def test_exploit_via_bash_gets_credit(self):
        """A step in chain_expected_order achieved via execute_bash with real
        success output should be credited — parity with calling exploit_service."""
        obs: dict = {}
        accumulate_observations(
            "execute_bash",
            "Shell obtained: root@10.10.11.50 — session 1 opened",
            obs,
        )
        assert obs.get("compromise_confirmed") is True

    def test_nmap_via_bash_gets_credit(self):
        """Port scan via execute_bash should populate open_ports."""
        obs: dict = {}
        accumulate_observations(
            "execute_bash",
            "22/tcp open ssh\n80/tcp open http\n445/tcp open smb",
            obs,
        )
        assert 22 in obs.get("open_ports", [])
        assert 80 in obs.get("open_ports", [])
        assert 445 in obs.get("open_ports", [])

    def test_sqlmap_via_bash_gets_credit(self):
        """SQL dump via execute_bash should set data_extracted."""
        obs: dict = {}
        accumulate_observations(
            "execute_bash",
            "Database: webapp\nTable: users\n[5 rows dumped]",
            obs,
        )
        assert obs.get("data_extracted") is True

    def test_bash_signal_mapping_covers_expected_steps(self):
        """_BASH_TECHNIQUE_SIGNALS covers the key chain steps."""
        expected_steps = {
            "run_nmap_scan",
            "check_cve",
            "exploit_service",
            "establish_persistence",
            "lateral_move",
            "exfiltrate_data",
            "exploit_binary_service",
            "run_sqlmap",
            "upload_webshell",
            "webshell_exec",
        }
        mapped = set(_BASH_TECHNIQUE_SIGNALS.keys())
        missing = expected_steps - mapped
        assert not missing, f"Steps missing from _BASH_TECHNIQUE_SIGNALS: {missing}"


# ── Honesty guard: no-credit without real output ─────────────────────────────


class TestNoCreditWithoutOutput:
    """Coverage credit must NOT be given for bare execute_bash calls."""

    def test_empty_bash_gives_no_compromise(self):
        obs: dict = {}
        accumulate_observations("execute_bash", "", obs)
        assert "compromise_confirmed" not in obs

    def test_error_bash_gives_no_compromise(self):
        obs: dict = {}
        accumulate_observations("execute_bash", "command not found: sqlmap", obs)
        assert "compromise_confirmed" not in obs

    def test_empty_bash_gives_no_ports(self):
        obs: dict = {}
        accumulate_observations("execute_bash", "", obs)
        assert "open_ports" not in obs

    def test_empty_bash_gives_no_cve(self):
        obs: dict = {}
        accumulate_observations("execute_bash", "", obs)
        assert "confirmed_cve" not in obs

    def test_empty_bash_gives_no_data(self):
        obs: dict = {}
        accumulate_observations("execute_bash", "", obs)
        assert "data_extracted" not in obs


# ── No tool proliferation ─────────────────────────────────────────────────────


class TestNoProliferation:
    """No new exec tools beyond execute_bash/execute_python."""

    def test_only_two_new_tools_added(self):
        original_wrappers = {
            "start_lab_target",
            "run_nmap_scan",
            "check_cve",
            "exploit_service",
            "establish_persistence",
            "lateral_move",
            "exfiltrate_data",
            "revert_lab_target",
            "web_request",
            "run_sqlmap",
            "upload_webshell",
            "webshell_exec",
            "exploit_binary_service",
        }
        all_names = {t["function"]["name"] for t in CHAIN_TOOLS_BASE}
        new_tools = all_names - original_wrappers
        assert new_tools == {"execute_bash", "execute_python"}, (
            f"Unexpected new tools: {new_tools - {'execute_bash', 'execute_python'}}"
        )

    def test_inline_tools_unchanged(self):
        """INLINE_TOOLS should still only have execute_bash, execute_python, web_search."""
        names = {t["function"]["name"] for t in INLINE_TOOLS}
        assert names == {"execute_bash", "execute_python", "web_search"}
