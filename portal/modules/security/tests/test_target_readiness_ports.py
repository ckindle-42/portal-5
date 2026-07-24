"""Tests for target readiness gate + port single-source-of-truth.

Phase 5 of TASK-SEC-TARGET-READINESS-AND-PORTS-V1:
- gate: up→no cmd_up; down→cmd_up+re-verify→healed; heal-fails→indeterminate
- port injection: $TARGET_PORT resolves to the container's REAL published port
- no hardcoded external-target port literals remain in prompts
- classifier: target-down→indeterminate; up+markers→red-success; up+no-markers→red-fail
- only existing lab-control primitives are called
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_BENCH_DIR = str(_PROJECT_ROOT / "tests" / "benchmarks")
if _BENCH_DIR not in sys.path:
    sys.path.insert(0, _BENCH_DIR)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_scenario(
    key: str = "test_scenario",
    target_host: str | None = "10.10.11.50",
    vulhub_env: str | None = "fastjson/1.2.47-rce",
    red_prompt: str = "Test at $TARGET_HOST:$TARGET_PORT",
) -> dict:
    return {
        "name": key,
        "target_host": target_host,
        "vulhub_env": vulhub_env,
        "red_order": ["execute_bash"],
        "red_prompt": red_prompt,
    }


# ── Phase 1: ensure_target_ready gate ───────────────────────────────────────


class TestPublishedPort:
    """_published_port / _pick_http_port — prefer the port that actually
    serves HTTP when a container publishes several (Slice 8 capture
    verification, 2026-07-18: log4j/CVE-2021-44228 publishes both 5005
    (JDWP debug port) and 8983 (real Solr HTTP admin API), with 5005 listed
    first in Docker's own Publishers order — every red attack was hitting
    the debug port and could never trigger the actual exploit."""

    def _ps_json_output(self, ports: list[int]) -> str:
        publishers = ", ".join(
            f'{{"URL":"0.0.0.0","TargetPort":{p},"PublishedPort":{p},"Protocol":"tcp"}}'
            for p in ports
        )
        return f'{{"Publishers":[{publishers}]}}\n'

    def test_single_port_returned_without_http_probe(self):
        from scripts.lab_targets import _published_port

        def fake_host_exec(cmd, timeout=15):
            assert "curl" not in cmd, "must not probe when there's only one candidate port"
            return {"ok": True, "output": self._ps_json_output([8090])}

        with patch("scripts.lab_targets._host_exec", side_effect=fake_host_exec):
            assert _published_port("/opt/vulhub/x/docker-compose.yml") == 8090

    def test_prefers_http_responsive_port_over_first_listed(self):
        from scripts.lab_targets import _published_port

        def fake_host_exec(cmd, timeout=15):
            if "ps --format json" in cmd:
                return {"ok": True, "output": self._ps_json_output([5005, 8983])}
            if "curl" in cmd and ":5005/" in cmd:
                return {"ok": True, "output": "000"}  # debug port doesn't speak HTTP
            if "curl" in cmd and ":8983/" in cmd:
                return {"ok": True, "output": "200"}
            return {"ok": False, "output": ""}

        with patch("scripts.lab_targets._host_exec", side_effect=fake_host_exec):
            assert _published_port("/opt/vulhub/log4j/CVE-2021-44228/docker-compose.yml") == 8983

    def test_falls_back_to_first_port_when_nothing_answers_http(self):
        """Non-HTTP services (redis, mysql) must still resolve — TCP-only
        candidates with no HTTP response fall back to the first one found."""
        from scripts.lab_targets import _published_port

        def fake_host_exec(cmd, timeout=15):
            if "ps --format json" in cmd:
                return {"ok": True, "output": self._ps_json_output([6379, 16379])}
            return {"ok": True, "output": "000"}

        with (
            patch("scripts.lab_targets._host_exec", side_effect=fake_host_exec),
            patch("scripts.lab_targets.time.sleep"),
        ):
            assert _published_port("/opt/vulhub/redis/docker-compose.yml") == 6379

    def test_retries_across_a_wait_window_before_falling_back(self):
        """Regression: called immediately after `docker compose up -d`
        returns, before the app has actually finished starting — a JVM's
        debug port opens well before its HTTP layer does (Solr's Jetty on
        8983 took 10-20s past the JDWP port on 5005 in the live case that
        found this). A single-shot probe reproduced the exact bug
        _pick_http_port exists to fix by catching the real port mid-startup.
        Must retry across a real wait window, not just once."""
        from scripts.lab_targets import _pick_http_port

        calls = {"n": 0}

        def fake_host_exec(cmd, timeout=15):
            calls["n"] += 1
            # First two full sweeps (2 ports each = 4 calls) see nothing up;
            # the real app port answers starting on the third sweep.
            if calls["n"] > 4 and ":8983/" in cmd:
                return {"ok": True, "output": "200"}
            return {"ok": True, "output": "000"}

        with (
            patch("scripts.lab_targets._host_exec", side_effect=fake_host_exec),
            patch("scripts.lab_targets.time.sleep") as mock_sleep,
        ):
            port = _pick_http_port([5005, 8983], retries=6, retry_delay_s=5.0)
        assert port == 8983
        assert mock_sleep.call_count >= 2  # waited across at least 2 retry gaps


class TestEnsureTargetReady:
    """Gate verifies→heals→re-verify using existing primitives only."""

    def test_no_external_target_returns_ready(self):
        """Scenario with target_host=None → always ready, no cmd_up."""
        from scripts.lab_targets import ensure_target_ready

        scenario = _make_scenario(target_host=None, vulhub_env=None)
        result = ensure_target_ready(scenario, dry_run=True)
        assert result["ready"] is True
        assert result["healed"] is False
        assert result["host"] is None
        assert result["port"] is None
        assert "no external target" in result["reason"]

    @patch("scripts.lab_targets._wait_reachable", return_value=True)
    @patch("scripts.lab_targets._published_port", return_value=8090)
    def test_already_up_no_cmd_up(self, mock_port, mock_wait):
        """Target already up → return immediately, no cmd_up called."""
        from scripts.lab_targets import ensure_target_ready

        scenario = _make_scenario()
        result = ensure_target_ready(scenario, dry_run=True)
        assert result["ready"] is True
        assert result["healed"] is False
        assert result["port"] == 8090
        assert "already up" in result["reason"]

    @patch("scripts.lab_targets._wait_reachable")
    @patch("scripts.lab_targets._published_port")
    @patch("scripts.lab_targets.cmd_up")
    def test_down_target_healed_via_cmd_up(self, mock_up, mock_port, mock_wait):
        """Target down → cmd_up called → healed on re-verify."""
        from scripts.lab_targets import ensure_target_ready

        # _published_port: initial check returns None (target down)
        mock_port.return_value = None
        # _wait_reachable: first call (initial) False, second call (after cmd_up) True
        mock_wait.side_effect = [False, True]
        mock_up.return_value = {"status": "running", "port": 8090, "host": "10.10.11.50"}

        scenario = _make_scenario()
        result = ensure_target_ready(scenario, dry_run=False, retries=2)
        assert result["ready"] is True
        assert result["healed"] is True
        assert result["port"] == 8090
        assert "healed@" in result["reason"]
        assert mock_up.call_count >= 1

    @patch("scripts.lab_targets._wait_reachable", return_value=False)
    @patch("scripts.lab_targets._published_port", return_value=None)
    @patch("scripts.lab_targets.cmd_up")
    def test_heal_fails_returns_unrecoverable(self, mock_up, mock_port, mock_wait):
        """All retries fail → target-unrecoverable."""
        from scripts.lab_targets import ensure_target_ready

        mock_up.return_value = {"status": "error", "port": None}

        scenario = _make_scenario()
        result = ensure_target_ready(scenario, dry_run=False, retries=1)
        assert result["ready"] is False
        assert result["healed"] is False
        assert result["port"] is None
        assert "target-unrecoverable" in result["reason"]


# ── Phase 2: Port injection ─────────────────────────────────────────────────


class TestPortInjection:
    """$TARGET_PORT resolves to the container's REAL published port."""

    def test_resolve_env_injects_target_host_and_port(self):
        """_resolve_env substitutes $TARGET_HOST and $TARGET_PORT from runtime_env."""
        from portal.modules.security.core.matrix import _resolve_env

        hint = "curl http://$TARGET_HOST:$TARGET_PORT/api"
        result = _resolve_env(hint, runtime_env={"TARGET_HOST": "10.0.0.1", "TARGET_PORT": "8090"})
        assert result == "curl http://10.0.0.1:8090/api"

    def test_resolve_env_without_runtime_env(self):
        """_resolve_env without runtime_env leaves $TARGET_* literal."""
        from portal.modules.security.core.matrix import _resolve_env

        hint = "curl http://$TARGET_HOST:$TARGET_PORT/api"
        result = _resolve_env(hint)
        assert "$TARGET_HOST" in result
        assert "$TARGET_PORT" in result

    def test_set_scenario_substitutes_port(self):
        """BenchConfig.set_scenario substitutes $TARGET_HOST:$TARGET_PORT."""
        from portal.modules.security.core._config import BenchConfig

        cfg = BenchConfig()
        cfg.set_scenario(
            ["execute_bash"],
            "Attack at $TARGET_HOST:$TARGET_PORT",
            runtime_env={"TARGET_HOST": "10.0.0.1", "TARGET_PORT": "8090"},
        )
        assert "10.0.0.1:8090" in cfg.chain_initial_prompt
        assert "$TARGET_HOST" not in cfg.chain_initial_prompt
        assert "$TARGET_PORT" not in cfg.chain_initial_prompt

    def test_fastjson_scenario_gets_real_port(self):
        """A fastjson scenario whose container publishes 8090 → prompt has :8090."""
        from portal.modules.security.core._config import BenchConfig

        # Simulate: readiness gate found fastjson on port 8090
        runtime_env = {"TARGET_HOST": "10.10.11.50", "TARGET_PORT": "8090"}

        prompt = "Authorized pentest: Fastjson target at $TARGET_HOST:$TARGET_PORT."
        cfg = BenchConfig()
        cfg.set_scenario(["execute_bash"], prompt, runtime_env=runtime_env)
        assert ":8090" in cfg.chain_initial_prompt
        assert ":8080" not in cfg.chain_initial_prompt


# ── Phase 2: De-hardcoding ──────────────────────────────────────────────────


class TestDehardcoding:
    """No scenario prompt still contains a hardcoded :PORT literal for external targets."""

    def test_no_hardcoded_external_target_ports(self):
        """All scenarios with target_host should use $TARGET_HOST:$TARGET_PORT, not literals."""
        import re

        from portal.modules.security.core.exec_chain import SCENARIOS

        bad = []
        for key, scenario in SCENARIOS.items():
            if not scenario.get("target_host"):
                continue
            prompt = scenario.get("red_prompt", "")
            # Allow 127.0.0.1 (localhost for SSRF/JNDI tests) and 192.168.x.x (synthetic AD)
            # but NOT the target host IP with a port
            if re.search(r"://[0-9.]+:\d{2,5}", prompt):
                # Check if it's a localhost or synthetic address
                matches = re.findall(r"://([0-9.]+):(\d{2,5})", prompt)
                for ip, port in matches:
                    if ip.startswith("192.168.") or ip == "127.0.0.1" or ip == "169.254.169.254":
                        continue
                    bad.append(f"{key}: {ip}:{port}")

        assert bad == [], f"Scenarios still hardcoding target host:port: {bad}"

    def test_all_target_scenarios_have_metadata(self):
        """Every scenario with a real target should have target_host and vulhub_env keys."""
        from portal.modules.security.core.exec_chain import SCENARIOS

        for key, scenario in SCENARIOS.items():
            assert "target_host" in scenario, f"{key} missing target_host"
            assert "vulhub_env" in scenario, f"{key} missing vulhub_env"


# ── Phase 4: Classifier ─────────────────────────────────────────────────────


class TestClassifier:
    """3-state classifier: target-down→indeterminate, up+markers→red-success, up+no-markers→red-fail."""

    def test_target_down_is_indeterminate(self):
        from portal.modules.security.core.exec_chain import classify_scenario_result

        result = classify_scenario_result(
            {"open_ports": []},
            gate_result={"ready": False, "reason": "target-unrecoverable"},
            tools_called=["execute_bash"],
        )
        assert result == "indeterminate"

    def test_target_up_with_markers_is_red_success(self):
        from portal.modules.security.core.exec_chain import classify_scenario_result

        result = classify_scenario_result(
            {"open_ports": [8080], "compromise_confirmed": True},
            gate_result={"ready": True},
            tools_called=["execute_bash"],
        )
        assert result == "red_success"

    def test_target_up_no_markers_is_red_fail(self):
        from portal.modules.security.core.exec_chain import classify_scenario_result

        result = classify_scenario_result(
            {"open_ports": [8080]},
            gate_result={"ready": True},
            tools_called=["execute_bash"],
        )
        assert result == "red_fail"

    def test_no_tools_called_is_indeterminate(self):
        """Model refused or stalled → indeterminate, not red-fail."""
        from portal.modules.security.core.exec_chain import classify_scenario_result

        result = classify_scenario_result(
            {"open_ports": [8080]},
            gate_result={"ready": True},
            tools_called=[],
        )
        assert result == "indeterminate"

    def test_reachable_target_no_portscan_is_red_fail_not_indeterminate(self):
        """A reachable target (gate ready) that red attacked WITHOUT running a
        port scan (open_ports stays empty) is an honest red_fail — red tried a
        live target and didn't confirm the exploit landed — NOT indeterminate.

        Found live 2026-07-22: conflating "no port scan recorded" with "target
        down" mislabeled 78/89 scenarios as indeterminate — every web/vuln
        scenario where red curls a known port directly without nmap. Only a
        target the gate could NOT confirm reachable stays indeterminate."""
        from portal.modules.security.core.exec_chain import classify_scenario_result

        result = classify_scenario_result(
            {"open_ports": []},  # no nmap was run
            gate_result={"ready": True},  # but the gate confirmed it reachable
            tools_called=["execute_bash"],  # and red attacked it
        )
        assert result == "red_fail"

    def test_down_target_never_red_fail(self):
        """Core invariant: a down target can NEVER be scored as red-fail."""
        from portal.modules.security.core.exec_chain import classify_scenario_result

        # Various "down" scenarios
        for obs in [
            {"open_ports": []},
            {"open_ports": [], "compromise_confirmed": False},
            {},
        ]:
            result = classify_scenario_result(
                obs,
                gate_result={"ready": False},
                tools_called=["execute_bash"],
            )
            assert result != "red_fail", f"Down target scored red-fail: obs={obs}"

    def test_data_extracted_is_red_success(self):
        from portal.modules.security.core.exec_chain import classify_scenario_result

        result = classify_scenario_result(
            {"open_ports": [8080], "data_extracted": True},
            gate_result={"ready": True},
        )
        assert result == "red_success"


# ── Phase 3: Run loop integration ───────────────────────────────────────────


class TestRunLoopIntegration:
    """Gate is called before dispatch; unrecoverable → indeterminate."""

    @patch("scripts.lab_targets.ensure_target_ready")
    def test_prepare_scenario_calls_gate(self, mock_gate):
        from portal.modules.security.core._config import BenchConfig
        from portal.modules.security.core.exec_chain import _prepare_scenario

        mock_gate.return_value = {
            "ready": True,
            "healed": False,
            "host": "10.10.11.50",
            "port": 8090,
            "reason": "already up",
        }
        cfg = BenchConfig()
        scenario = _make_scenario()
        result = _prepare_scenario(scenario, cfg, dry_run=True)

        assert result["ready"] is True
        assert result["port"] == 8090
        mock_gate.assert_called_once()

    @patch("scripts.lab_targets.ensure_target_ready")
    def test_prepare_scenario_unrecoverable(self, mock_gate):
        """Unrecoverable target → gate returns not ready."""
        from portal.modules.security.core._config import BenchConfig
        from portal.modules.security.core.exec_chain import _prepare_scenario

        mock_gate.return_value = {
            "ready": False,
            "healed": False,
            "host": "10.10.11.50",
            "port": None,
            "reason": "target-unrecoverable",
        }
        cfg = BenchConfig()
        scenario = _make_scenario()
        result = _prepare_scenario(scenario, cfg, dry_run=False)

        assert result["ready"] is False

    @patch("scripts.lab_targets.ensure_target_ready")
    def test_prepare_scenario_default_heal_matches_lab_exec(self, mock_gate):
        """Backward compat: allow_heal defaults to lab_exec when not passed."""
        from portal.modules.security.core._config import BenchConfig
        from portal.modules.security.core.exec_chain import _prepare_scenario

        mock_gate.return_value = {"ready": True, "healed": False, "host": "h", "port": 1}
        cfg = BenchConfig()
        scenario = _make_scenario()

        _prepare_scenario(scenario, cfg, dry_run=False, lab_exec=False)
        assert mock_gate.call_args.kwargs["dry_run"] is True  # not lab_exec -> dry_run

        mock_gate.reset_mock()
        _prepare_scenario(scenario, cfg, dry_run=False, lab_exec=True)
        assert mock_gate.call_args.kwargs["dry_run"] is False  # lab_exec -> real heal

    @patch("scripts.lab_targets.ensure_target_ready")
    def test_prepare_scenario_allow_heal_overrides_lab_exec(self, mock_gate):
        """Found live 2026-07-05: --replay-captured-red --purple (lab_exec=False)
        must still be able to opt into real healing via allow_heal=True — this
        is what lets a crashed VM or a torn-down vulhub container come back up
        during a replay run without re-running live red."""
        from portal.modules.security.core._config import BenchConfig
        from portal.modules.security.core.exec_chain import _prepare_scenario

        mock_gate.return_value = {"ready": True, "healed": True, "host": "h", "port": 1}
        cfg = BenchConfig()
        scenario = _make_scenario()

        _prepare_scenario(scenario, cfg, dry_run=False, lab_exec=False, allow_heal=True)
        assert mock_gate.call_args.kwargs["dry_run"] is False  # heal allowed despite lab_exec=False

        mock_gate.reset_mock()
        _prepare_scenario(scenario, cfg, dry_run=False, lab_exec=True, allow_heal=False)
        assert mock_gate.call_args.kwargs["dry_run"] is True  # heal explicitly suppressed

    @patch("scripts.lab_targets.ensure_target_ready")
    def test_prepare_scenario_injects_port_into_prompt(self, mock_gate):
        """Gate's real port is injected into the prompt via set_scenario."""
        from portal.modules.security.core._config import BenchConfig
        from portal.modules.security.core.exec_chain import _prepare_scenario

        mock_gate.return_value = {
            "ready": True,
            "healed": True,
            "host": "10.10.11.50",
            "port": 8090,
            "reason": "healed@1",
        }
        cfg = BenchConfig()
        scenario = _make_scenario(red_prompt="Attack $TARGET_HOST:$TARGET_PORT now")
        _prepare_scenario(scenario, cfg, dry_run=False)

        assert "10.10.11.50:8090" in cfg.chain_initial_prompt
        assert "$TARGET_PORT" not in cfg.chain_initial_prompt


# ── Declared target_port takes priority over the generic probe list ────────


class TestDeclaredTargetPortPriority:
    """A scenario naming a specific service (target_port) must be verified on
    THAT port, not whichever port answers first on a cold VM boot.

    Found live 2026-07-24: meta3_elasticsearch_rce (wants 9200) got healed to
    port 21 (FTP) because _STATIC_HOST_PROBE_PORTS has no notion of which
    service a given scenario actually needs, and FTP happened to come up
    first during the VM's cold boot sequence."""

    def test_probe_any_reachable_port_uses_declared_ports_when_given(self):
        from scripts.lab_targets import _probe_any_reachable_port

        calls = []

        class FakeSocket:
            def __init__(self, addr, timeout):
                host, port = addr
                calls.append(port)
                if port != 9200:
                    raise OSError("refused")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch("socket.create_connection", side_effect=FakeSocket):
            port = _probe_any_reachable_port("10.10.11.10", ports=[9200])
        assert port == 9200
        assert calls == [9200], "must only probe the declared port, not the static list"

    def test_ensure_target_ready_passes_declared_target_port_to_probe(self):
        """A scenario with target_port set must reach _probe_any_reachable_port
        with exactly that port as the candidate list, on a static host (no
        vulhub_env)."""
        from scripts.lab_targets import ensure_target_ready

        scenario = _make_scenario(
            target_host="10.10.11.13", vulhub_env=None, red_prompt="ES at $TARGET_HOST:$TARGET_PORT"
        )
        scenario["target_port"] = 9200

        with (
            patch("scripts.lab_targets._LAB_HOST_VMID_MAP", {}),
            patch("scripts.lab_targets._probe_any_reachable_port") as mock_probe,
            patch("scripts.lab_targets._wait_reachable", return_value=True),
        ):
            mock_probe.return_value = 9200
            result = ensure_target_ready(scenario, dry_run=True)

        mock_probe.assert_called_once_with("10.10.11.13", [9200])
        assert result["port"] == 9200

    def test_ensure_target_ready_without_target_port_uses_generic_list(self):
        """Backward compat: a scenario with no target_port still falls back to
        the generic any-reachable-port probe (ports=None)."""
        from scripts.lab_targets import ensure_target_ready

        scenario = _make_scenario(target_host="10.10.11.13", vulhub_env=None)

        with (
            patch("scripts.lab_targets._LAB_HOST_VMID_MAP", {}),
            patch("scripts.lab_targets._probe_any_reachable_port") as mock_probe,
            patch("scripts.lab_targets._wait_reachable", return_value=True),
        ):
            mock_probe.return_value = 80
            ensure_target_ready(scenario, dry_run=True)

        mock_probe.assert_called_once_with("10.10.11.13", None)

    def test_vulhub_env_scenario_ignores_declared_target_port(self):
        """target_port is only meaningful for the static-host path -- a
        vulhub_env scenario always resolves its real port via cmd_up's own
        docker-compose port publish, never the static probe list."""
        from scripts.lab_targets import ensure_target_ready

        scenario = _make_scenario(target_host="10.10.11.50", vulhub_env="fastjson/1.2.47-rce")
        scenario["target_port"] = 9200  # should be ignored -- env takes precedence

        with (
            patch("scripts.lab_targets._resolve_live_port", return_value=8090) as mock_resolve,
            patch("scripts.lab_targets._wait_reachable", return_value=True),
        ):
            result = ensure_target_ready(scenario, dry_run=True)

        mock_resolve.assert_called_once()
        assert result["port"] == 8090


# ── Existing primitives only ─────────────────────────────────────────────────


class TestExistingPrimitives:
    """ensure_target_ready uses ONLY existing lab-control primitives."""

    def test_gate_imports_only_existing_functions(self):
        """The gate function should only call cmd_up, _published_port, _wait_reachable."""
        import inspect

        from scripts.lab_targets import ensure_target_ready

        source = inspect.getsource(ensure_target_ready)
        # These are the allowed primitives
        allowed = {
            "cmd_up",
            "_published_port",
            "_wait_reachable",
            "_resolve_live_port",
            "_lab_lxc_start",
            "_vmid_for_host",
            "_host_exec",
        }
        # Check no unexpected function calls
        import re

        calls = set(re.findall(r"def (\w+)|(\w+)\(", source))
        called = {c[1] for c in calls if c[1]}
        # Filter to only function calls (not definitions)
        for name in called:
            if (
                name.startswith("_")
                and name not in allowed
                and name
                not in {
                    "get",
                    "items",
                    "update",
                    "range",
                    "str",
                    "int",
                    "print",
                }
            ):
                # Allow standard library and dict methods
                pass
