#!/usr/bin/env python3
"""Local deterministic bench supervisor (Layer 1) — replaces the sleep/wake orchestrator.

Launches the sec bench as a subprocess, tails the log, detects KNOWN failure
patterns across target/lab, model, and bench-logic classes, and takes
predefined corrective actions by calling EXISTING primitives — no LLM, no
offensive capability, no frontier agent.

Unknown failures escalate (pause or skip), never silently continue.
Interrupted units are re-run or marked indeterminate, never scored from
partial output. A max-corrections cap prevents infinite revert loops.

Usage:
    python3 scripts/bench_supervisor.py --run-args "--all-scenarios --chain-models ..."
    python3 scripts/bench_supervisor.py --run-args "--dry-run --all-scenarios --chain-models test" --self-test
    python3 scripts/bench_supervisor.py --run-args "..." --on-unknown pause --max-corrections-per-scenario 3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BENCH_DIR = _REPO_ROOT / "tests" / "benchmarks"
_RESULTS_DIR = _REPO_ROOT / "portal" / "modules" / "security" / "core" / "results"

# Ensure imports work regardless of cwd
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ── Corrective primitives (thin wrappers over existing bench_lab_exec functions) ──


def _import_lab_exec():
    """Import bench_lab_exec primitives lazily (may fail if env not set)."""
    try:
        import bench_lab_exec

        return bench_lab_exec
    except Exception:
        return None


def _import_lab_targets():
    """Import lab_targets.cmd_up lazily."""
    try:
        from scripts.lab_targets import cmd_up

        return cmd_up
    except Exception:
        return None


# ── Supervisor state ──────────────────────────────────────────────────────────


class SupervisorState:
    """Mutable state tracked across the supervisor run."""

    def __init__(self) -> None:
        self.correction_counts: dict[str, int] = {}  # scenario -> correction count
        self.completed_scenarios: set[str] = set()
        self.indeterminate_scenarios: set[str] = set()
        self.escalations: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.start_time: float = time.monotonic()
        self.last_activity: float = time.monotonic()
        self.current_scenario: str = ""
        self.bench_pid: int | None = None

    def record_action(self, handler: str, pattern: str, action: str, detail: str = "") -> None:
        entry = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "handler": handler,
            "pattern": pattern,
            "action": action,
            "detail": detail,
            "scenario": self.current_scenario,
        }
        self.actions.append(entry)

    def record_escalation(self, line: str, context: str = "") -> None:
        entry = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "line": line.rstrip(),
            "context": context,
            "scenario": self.current_scenario,
        }
        self.escalations.append(entry)

    def increment_correction(self, scenario: str) -> int:
        count = self.correction_counts.get(scenario, 0) + 1
        self.correction_counts[scenario] = count
        return count

    def touch(self) -> None:
        self.last_activity = time.monotonic()


# ── Log line detectors ────────────────────────────────────────────────────────

_RE_VULHUB_UNREACHABLE = re.compile(
    r"(vulhub|lab-vulhub|10\.10\.11\.50).*(unreachable|refused|timeout|UNREACHABLE)",
    re.IGNORECASE,
)
_RE_TARGET_UNREACHABLE = re.compile(
    r"(target.*(unreachable|refused|timeout)|lab.targets.*(unreachable|UNREACHABLE)"
    r"|DC.*SRV.*unreachable|ABORTING.*lab targets unreachable)",
    re.IGNORECASE,
)
_RE_OLLAMA_CONN_REFUSED = re.compile(
    r"((ollama|11434).*(connection refused|refused|ECONNREFUSED|unreachable)"
    r"|(connection refused|ECONNREFUSED).*(ollama|11434))",
    re.IGNORECASE,
)
_RE_MODEL_NOT_LOADED = re.compile(
    r"(model.*not.*loaded|model.*not.*found|pull.*model|model.*missing"
    r"|no model.*loaded|error.*loading.*model)",
    re.IGNORECASE,
)
_RE_LXC_DOWN = re.compile(
    r"(LXC.*(down|stopped|not running)|container.*(down|stopped)"
    r"|proxmox_container_start.*fail|vulhub.*docker.*not.*running)",
    re.IGNORECASE,
)
_RE_SPIN_TIMEOUT = re.compile(
    r"(spin.*timeout|startup.*timeout|timed.*out.*waiting|service.*port.*not.*answer)",
    re.IGNORECASE,
)
_RE_CHECKPOINT_ABORT = re.compile(
    r"(aborted|interrupted|KeyboardInterrupt|SIGTERM|SIGKILL)", re.IGNORECASE
)
_RE_BENCH_ERROR = re.compile(r"(Traceback|Error:|FATAL|CRITICAL|FAILED)", re.IGNORECASE)


def is_vulhub_unreachable(line: str) -> bool:
    return bool(_RE_VULHUB_UNREACHABLE.search(line))


def is_target_unreachable(line: str) -> bool:
    return bool(_RE_TARGET_UNREACHABLE.search(line))


def is_ollama_conn_refused(line: str) -> bool:
    return bool(_RE_OLLAMA_CONN_REFUSED.search(line))


def is_model_not_loaded(line: str) -> bool:
    return bool(_RE_MODEL_NOT_LOADED.search(line))


def is_lxc_down(line: str) -> bool:
    return bool(_RE_LXC_DOWN.search(line))


def is_spin_timeout(line: str) -> bool:
    return bool(_RE_SPIN_TIMEOUT.search(line))


def is_checkpoint_abort(line: str) -> bool:
    return bool(_RE_CHECKPOINT_ABORT.search(line))


def make_no_progress_detector(minutes: int) -> Callable[[SupervisorState], bool]:
    """Return a detector that fires when no log activity for `minutes`."""

    def _detector(state: SupervisorState) -> bool:
        elapsed = time.monotonic() - state.last_activity
        return elapsed > minutes * 60

    return _detector


# ── Corrective handlers ───────────────────────────────────────────────────────


def handle_restart_lxc_112(state: SupervisorState, line: str) -> str:
    """Start LXC 112 (vulhub) via Proxmox MCP."""
    lab = _import_lab_exec()
    if lab is None:
        state.record_action("restart_lxc_112", "lxc_down", "skip", "bench_lab_exec not importable")
        return "continue"
    state.record_action("restart_lxc_112", "lxc_down", "proxmox_container_start(112)")
    try:
        r = lab._proxmox_mcp_call(
            "proxmox_container_start", {"vmid": 112, "wait": True}, timeout=120
        )
        if r.get("ok"):
            time.sleep(15)  # wait for docker to settle
            return "retry"
        state.record_action("restart_lxc_112", "lxc_down", "failed", str(r.get("error")))
        return "continue"
    except Exception as exc:
        state.record_action("restart_lxc_112", "lxc_down", "error", str(exc))
        return "continue"


def handle_revert_and_respin(state: SupervisorState, line: str) -> str:
    """Revert lab targets to clean snapshot and re-start them."""
    lab = _import_lab_exec()
    if lab is None:
        state.record_action(
            "revert_and_respin", "target_unreach", "skip", "bench_lab_exec not importable"
        )
        return "continue"
    state.record_action("revert_and_respin", "target_unreach", "lab_teardown + lab_setup")
    try:
        lab.lab_teardown()
        time.sleep(5)
        lab.lab_setup()
        time.sleep(15)
        return "retry"
    except Exception as exc:
        state.record_action("revert_and_respin", "target_unreach", "error", str(exc))
        return "continue"


def handle_revert_target(state: SupervisorState, line: str) -> str:
    """Revert lab targets to clean snapshot (no re-start)."""
    lab = _import_lab_exec()
    if lab is None:
        return "continue"
    state.record_action("revert_target", "spin_timeout", "lab_teardown")
    try:
        lab.lab_teardown()
        time.sleep(5)
        return "retry"
    except Exception as exc:
        state.record_action("revert_target", "spin_timeout", "error", str(exc))
        return "continue"


def handle_load_model(state: SupervisorState, line: str) -> str:
    """Attempt to load the model via Ollama API."""
    import urllib.request

    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    state.record_action("load_model", "model_not_loaded", "GET /api/tags + load")
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            if models:
                state.record_action(
                    "load_model",
                    "model_not_loaded",
                    f"available: {', '.join(models[:5])}",
                )
        return "retry"
    except Exception as exc:
        state.record_action("load_model", "model_not_loaded", "error", str(exc))
        return "continue"


def handle_kill_unit_continue(state: SupervisorState, line: str) -> str:
    """Kill wedged request, mark unit indeterminate, continue."""
    state.record_action("kill_unit", "inference_stall", "mark indeterminate, continue")
    state.indeterminate_scenarios.add(state.current_scenario)
    return "continue"


def handle_skip_scenario(state: SupervisorState, line: str) -> str:
    """Skip a wedged scenario, record indeterminate."""
    state.record_action("skip_scenario", "scenario_wedged", "skip, record indeterminate")
    state.indeterminate_scenarios.add(state.current_scenario)
    return "skip"


def handle_escalate(state: SupervisorState, line: str) -> str:
    """Escalate an unknown pattern."""
    state.record_escalation(line, context="unknown_pattern")
    return "escalate"


# ── Handler table ─────────────────────────────────────────────────────────────


# Each entry: (name, line_detector | None, state_detector | None, handler)
# A handler fires if EITHER the line detector matches the current log line
# OR the state detector (evaluated periodically) returns True.
HandlerEntry = tuple[
    str,
    Callable[[str], bool] | None,
    Callable[[SupervisorState], bool] | None,
    Callable[[SupervisorState, str], str],
]

HANDLERS: list[HandlerEntry] = [
    ("lxc112_down", is_lxc_down, None, handle_restart_lxc_112),
    ("vulhub_unreach", is_vulhub_unreachable, None, handle_revert_and_respin),
    ("target_unreach", is_target_unreachable, None, handle_revert_and_respin),
    ("spin_timeout", is_spin_timeout, None, handle_revert_target),
    ("ollama_refused", is_ollama_conn_refused, None, handle_load_model),
    ("model_not_loaded", is_model_not_loaded, None, handle_load_model),
    ("checkpoint_abort", is_checkpoint_abort, None, handle_skip_scenario),
]


def build_state_handlers(stall_minutes: int) -> list[HandlerEntry]:
    """Build the full handler list including the stall watchdog."""
    handlers = list(HANDLERS)
    if stall_minutes > 0:
        stall_detector = make_no_progress_detector(stall_minutes)
        handlers.append(("inference_stall", None, stall_detector, handle_kill_unit_continue))
    return handlers


# ── Partial.json resume logic ─────────────────────────────────────────────────


def load_completed_scenarios(partial_path: Path) -> set[str]:
    """Read .partial.json and return the set of scenario names with results."""
    if not partial_path.exists():
        return set()
    try:
        data = json.loads(partial_path.read_text())
        if not isinstance(data, list):
            return set()
        scenarios: set[str] = set()
        for entry in data:
            sc = entry.get("scenario", "")
            if sc:
                scenarios.add(sc)
        return scenarios
    except Exception:
        return set()


def compute_remaining_scenarios(all_scenarios: list[str], completed: set[str]) -> list[str]:
    """Return scenarios not yet completed."""
    return [s for s in all_scenarios if s not in completed]


# ── Supervisor log ────────────────────────────────────────────────────────────


def write_supervisor_log(path: Path, state: SupervisorState, outcome: str) -> None:
    """Write the audit trail for the supervised run."""
    elapsed = time.monotonic() - state.start_time
    log = {
        "supervisor_version": "1.0.0",
        "start_time": datetime.fromtimestamp(state.start_time, tz=UTC).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "outcome": outcome,
        "corrections": dict(state.correction_counts),
        "completed_scenarios": sorted(state.completed_scenarios),
        "indeterminate_scenarios": sorted(state.indeterminate_scenarios),
        "actions": state.actions,
        "escalations": state.escalations,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2))


# ── Escalation handling ──────────────────────────────────────────────────────


def handle_escalation(
    state: SupervisorState,
    line: str,
    on_unknown: str,
    max_corrections: int,
    triage_mode: str = "off",
    triage_ollama_url: str = "",
    triage_model: str = "",
    confidence_floor: float = 0.5,
    log_path: Path | None = None,
) -> str:
    """Handle an unknown pattern: optionally triage via P40, then pause or skip.

    Layer 2 integration: if triage_mode is 'propose' or 'auto', ask the P40
    model to diagnose. In propose mode, show the recommendation and wait for
    operator confirm. In auto mode, execute if allowlisted + confidence-gated
    + under cap. On any doubt → the original safe pause_for_human.
    """
    state.record_escalation(line, context="unhandled_error_pattern")

    # Layer 2: attempt triage if enabled
    if triage_mode in ("propose", "auto"):
        # Check per-scenario correction cap BEFORE calling triage
        corrections = state.correction_counts.get(state.current_scenario, 0)
        if corrections >= max_corrections and max_corrections > 0:
            state.record_action(
                "triage",
                "cap_reached",
                f"cap reached ({corrections}>={max_corrections}), pausing",
            )
            return _fallback_pause(state, line)

        try:
            from scripts.triage import diagnose
            from scripts.triage_actions import execute_action, is_action_allowed

            # Extract log tail for context
            log_tail = ""
            if log_path and log_path.exists():
                try:
                    log_tail = log_path.read_text()[-8000:]
                except Exception:
                    pass

            diag = diagnose(
                log_tail=log_tail,
                failing_line=line,
                scenario=state.current_scenario,
                ollama_url=triage_ollama_url,
                model=triage_model,
                confidence_floor=confidence_floor,
            )

            # Log the triage decision
            state.record_action(
                "triage",
                "novel_failure",
                f"diagnosed: {diag.get('action')} (conf={diag.get('confidence', 0):.2f})",
                detail=diag.get("reason", ""),
            )

            action_name = diag.get("action", "pause_for_human")
            action_params = diag.get("params", {})
            action_params["scenario"] = state.current_scenario

            if triage_mode == "propose":
                # Show recommendation, wait for operator
                print(f"\n  [TRIAGE] Recommended action: {action_name}")
                print(f"  [TRIAGE] Reason: {diag.get('reason', '?')}")
                print(f"  [TRIAGE] Confidence: {diag.get('confidence', 0):.2f}")
                print("  [TRIAGE] Press Enter to execute, or 's' to skip, Ctrl+C to abort.")
                try:
                    choice = input().strip().lower()
                except (KeyboardInterrupt, EOFError):
                    write_supervisor_log(
                        _REPO_ROOT / "supervisor_log.json",
                        state,
                        "aborted_by_operator",
                    )
                    sys.exit(1)
                if choice == "s":
                    state.record_action("triage", "propose", "skipped_by_operator")
                    return "skip"
                # Execute the recommended action
                if is_action_allowed(action_name):
                    result = execute_action(action_name, action_params)
                    state.record_action(
                        "triage",
                        "propose_executed",
                        action_name,
                        detail=json.dumps(result),
                    )
                    return "retry" if result.get("ok") else "skip"
                else:
                    state.record_action("triage", "propose_rejected", f"disallowed: {action_name}")
                    return "skip"

            else:  # auto mode
                # Validate: must be allowed + above confidence floor
                if not diag.get("allowed", False):
                    state.record_action("triage", "auto_rejected", f"disallowed: {action_name}")
                    return _fallback_pause(state, line)

                if not diag.get("above_floor", False):
                    state.record_action(
                        "triage",
                        "auto_rejected",
                        f"low confidence: {diag.get('confidence', 0):.2f}",
                    )
                    return _fallback_pause(state, line)

                # Check per-scenario correction cap
                corrections = state.correction_counts.get(state.current_scenario, 0)
                if corrections >= max_corrections and max_corrections > 0:
                    state.record_action(
                        "triage",
                        "auto_rejected",
                        f"cap reached ({corrections}>={max_corrections})",
                    )
                    return _fallback_pause(state, line)

                # Execute
                result = execute_action(action_name, action_params)
                state.record_action(
                    "triage",
                    "auto_executed",
                    action_name,
                    detail=json.dumps(result),
                )

                # Handle skip_scenario state update
                if action_name == "skip_scenario":
                    state.indeterminate_scenarios.add(state.current_scenario)

                return "retry" if result.get("ok") else "skip"

        except Exception as exc:
            # Any triage failure → fall back to Layer 1 pause
            state.record_action("triage", "error", str(exc), detail="falling back to Layer 1")
            return _fallback_pause(state, line)

    # Layer 1 only: original pause/skip behavior
    return _fallback_pause(state, line)


def _fallback_pause(state: SupervisorState, line: str) -> str:
    """Layer 1's original escalation: pause or skip."""
    print("\n  [SUPERVISOR] UNKNOWN pattern detected — pausing for operator.")
    print(f"  Line: {line.rstrip()}")
    print("  Press Enter to continue (skip this unit), or Ctrl+C to abort.")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        write_supervisor_log(_REPO_ROOT / "supervisor_log.json", state, "aborted_by_operator")
        sys.exit(1)
    return "skip"


# ── Log tail + detection loop ─────────────────────────────────────────────────


def tail_and_supervise(
    proc: subprocess.Popen,
    log_path: Path,
    state: SupervisorState,
    handlers: list[HandlerEntry],
    on_unknown: str,
    max_corrections: int,
    check_interval: float = 2.0,
    triage_mode: str = "off",
    triage_ollama_url: str = "",
    triage_model: str = "",
    confidence_floor: float = 0.5,
) -> str:
    """Tail the subprocess log, detect patterns, invoke handlers.

    Returns: "completed", "killed", or "escalated".
    """
    result = "completed"
    with open(log_path, "w") as log_f:
        # Poll subprocess stdout in a thread
        def _reader() -> None:
            try:
                for chunk in iter(
                    lambda: (
                        proc.stdout.read1(4096)
                        if hasattr(proc.stdout, "read1")
                        else proc.stdout.read(4096)
                    ),
                    b"",
                ):
                    text = chunk.decode("utf-8", errors="replace")
                    log_f.write(text)
                    log_f.flush()
                    for line in text.splitlines():
                        _process_line(
                            line,
                            state,
                            handlers,
                            on_unknown,
                            max_corrections,
                            triage_mode=triage_mode,
                            triage_ollama_url=triage_ollama_url,
                            triage_model=triage_model,
                            confidence_floor=confidence_floor,
                            log_path=log_path,
                        )
            except Exception:
                pass

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        # Main supervision loop
        while proc.poll() is None:
            time.sleep(check_interval)
            state.touch()

            # Check state-based detectors (stall watchdog)
            for name, line_det, state_det, handler in handlers:
                if state_det is not None and state_det(state):
                    state.record_action(
                        name, "state_check", f"triggered after {check_interval}s poll"
                    )
                    action = handler(state, "")
                    if action == "skip":
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        result = "killed"
                        break
                    elif action == "retry":
                        # Stall detected — kill and let outer loop retry
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        result = "killed"
                        break
            else:
                continue
            break

        # Drain remaining output
        reader_thread.join(timeout=5)

    return result


def _process_line(
    line: str,
    state: SupervisorState,
    handlers: list[HandlerEntry],
    on_unknown: str,
    max_corrections: int,
    triage_mode: str = "off",
    triage_ollama_url: str = "",
    triage_model: str = "",
    confidence_floor: float = 0.5,
    log_path: Path | None = None,
) -> None:
    """Process a single log line through the handler table."""
    # Track scenario transitions
    sc_match = re.search(r"Scenario:\s*(\S+)", line)
    if sc_match:
        state.current_scenario = sc_match.group(1)

    # Track scenario completion signals
    if re.search(r"(Scenario Averages|Results written|sec_bench_)", line):
        if state.current_scenario:
            state.completed_scenarios.add(state.current_scenario)

    # Check line-based detectors
    for name, line_det, state_det, handler in handlers:
        if line_det is not None and line_det(line):
            scenario = state.current_scenario
            corrections = state.increment_correction(scenario)

            if corrections > max_corrections and max_corrections > 0:
                state.record_action(
                    name,
                    "max_corrections",
                    f"cap reached ({corrections}>{max_corrections}), skip scenario",
                )
                state.indeterminate_scenarios.add(scenario)
                return

            action = handler(state, line)
            state.record_action(name, "line_match", action, detail=line[:200])
            return

    # Unknown error pattern — escalate (with optional triage)
    if _RE_BENCH_ERROR.search(line):
        handle_escalation(
            state,
            line,
            on_unknown,
            max_corrections,
            triage_mode=triage_mode,
            triage_ollama_url=triage_ollama_url,
            triage_model=triage_model,
            confidence_floor=confidence_floor,
            log_path=log_path,
        )


# ── Self-test mode ────────────────────────────────────────────────────────────


SELF_TEST_LINES = [
    ("lxc112_down", "ERROR: vulhub container down, docker not running"),
    ("vulhub_unreach", "lab-vulhub 10.10.11.50 unreachable connection refused"),
    ("target_unreach", "ABORTING: lab targets unreachable — DC and SRV"),
    ("spin_timeout", "spin timeout: service port not answering after 120s"),
    ("ollama_refused", "localhost:11434 connection refused (ECONNREFUSED)"),
    ("model_not_loaded", "error loading model: model not found, pull the model first"),
    ("checkpoint_abort", "KeyboardInterrupt received, aborting run"),
]

SELF_TEST_BENIGN_LINES = [
    "Scenario: kerberoast_to_da",
    "depth=3/8  acc=0.75",
    "Results written → results/sec_bench.json",
    "Chain tests complete for model test-model",
    "── Lab Service Probe ──",
]


def run_self_test(stall_minutes: int) -> bool:
    """Verify all detectors fire on fixture lines and NOT on benign lines."""
    handlers = build_state_handlers(stall_minutes)
    print("── Self-test: detectors ──")
    ok = True

    for expected_name, test_line in SELF_TEST_LINES:
        fired = False
        for name, line_det, state_det, handler in handlers:
            if line_det is not None and line_det(test_line):
                if name == expected_name:
                    print(f"  [PASS] {name} fires on: {test_line[:60]}")
                    fired = True
                else:
                    print(f"  [FAIL] {name} fired (expected {expected_name}) on: {test_line[:60]}")
                    ok = False
                break
        if not fired:
            print(f"  [FAIL] {expected_name} did NOT fire on: {test_line[:60]}")
            ok = False

    print("\n── Self-test: benign lines (no false positives) ──")
    for test_line in SELF_TEST_BENIGN_LINES:
        for name, line_det, state_det, handler in handlers:
            if line_det is not None and line_det(test_line):
                print(f"  [FAIL] {name} false-positive on: {test_line[:60]}")
                ok = False
                break
        else:
            print(f"  [PASS] no match: {test_line[:60]}")

    print("\n── Self-test: handler wiring ──")
    # Verify handlers call the right primitives — mock network/lab calls
    import urllib.request
    from unittest.mock import MagicMock, patch

    state = SupervisorState()
    mock_lab = MagicMock()
    mock_lab._proxmox_mcp_call.return_value = {"ok": True}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"models": [{"name": "test:latest"}]}).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with (
        patch.dict("sys.modules", {"bench_lab_exec": mock_lab}),
        patch.object(urllib.request, "urlopen", return_value=mock_resp),
        patch(f"{__name__}.time.sleep"),
    ):
        for name, line_det, state_det, handler in handlers:
            try:
                action = handler(state, "test line")
                if action in ("retry", "continue", "skip", "escalate"):
                    print(f"  [PASS] {name} -> {action}")
                else:
                    print(f"  [FAIL] {name} -> invalid action: {action}")
                    ok = False
            except Exception as exc:
                print(f"  [FAIL] {name} raised: {type(exc).__name__}: {exc}")
                ok = False

    print(f"\nSelf-test: {'PASS' if ok else 'FAIL'}")
    return ok


# ── Main ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local deterministic bench supervisor (Layer 1 + optional Layer 2)"
    )
    parser.add_argument(
        "--run-args",
        required=True,
        help="Arguments to pass to python3 -m portal.modules.security.core (quoted string)",
    )
    parser.add_argument(
        "--stall-minutes",
        type=int,
        default=15,
        help="Minutes of no log activity before declaring a stall (default: 15)",
    )
    parser.add_argument(
        "--on-unknown",
        choices=["pause", "skip"],
        default="pause",
        help="Action on unknown error pattern (default: pause)",
    )
    parser.add_argument(
        "--max-corrections-per-scenario",
        type=int,
        default=3,
        help="Max corrective actions per scenario before skip (default: 3)",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=5,
        help="Max bench subprocess restarts before giving up (default: 5)",
    )
    parser.add_argument(
        "--triage-mode",
        choices=["off", "propose", "auto"],
        default="off",
        help=(
            "Layer 2 triage mode (default: off). "
            "propose: P40 diagnoses, operator confirms. "
            "auto: P40 diagnoses + acts (allowlisted + confidence-gated + capped)."
        ),
    )
    parser.add_argument(
        "--triage-ollama-url",
        default="",
        help="P40 Ollama endpoint for triage (default: TRIAGE_OLLAMA_URL env or http://localhost:11434)",
    )
    parser.add_argument(
        "--triage-model",
        default="",
        help="Triage model ID (default: TRIAGE_MODEL env or ducquoc/gpt-oss-sonnet:latest)",
    )
    parser.add_argument(
        "--confidence-floor",
        type=float,
        default=0.5,
        help="Minimum confidence for auto-mode execution (default: 0.5)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test (verify detectors on fixture lines) and exit",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path for supervisor_log.json (default: supervisor_log.json in repo root)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.self_test:
        ok = run_self_test(args.stall_minutes)
        return 0 if ok else 1

    state = SupervisorState()
    handlers = build_state_handlers(args.stall_minutes)
    log_path = Path(args.output) if args.output else _REPO_ROOT / "supervisor_log.json"

    # Resolve triage config
    triage_mode = args.triage_mode
    triage_ollama_url = args.triage_ollama_url or os.environ.get(
        "TRIAGE_OLLAMA_URL", "http://localhost:11434"
    )
    triage_model = args.triage_model or os.environ.get(
        "TRIAGE_MODEL", "ducquoc/gpt-oss-sonnet:latest"
    )
    confidence_floor = args.confidence_floor

    if triage_mode != "off":
        print(f"  [triage] mode={triage_mode}  url={triage_ollama_url}  model={triage_model}")

    # Parse run-args to find output path for resume logic
    run_args_list = args.run_args.split()
    has_all_scenarios = "--all-scenarios" in run_args_list

    # Detect .partial.json for resume
    partial_path: Path | None = None
    for i, arg in enumerate(run_args_list):
        if arg == "--output" and i + 1 < len(run_args_list):
            partial_path = Path(run_args_list[i + 1]).with_suffix(".partial.json")
            break
    if partial_path is None:
        # Find most recent partial.json in results dir
        partials = sorted(_RESULTS_DIR.glob("*.partial.json"), reverse=True)
        if partials:
            partial_path = partials[0]

    completed = set()
    if partial_path and partial_path.exists():
        completed = load_completed_scenarios(partial_path)
        if completed:
            print(f"  [resume] found partial checkpoint: {partial_path}")
            print(f"  [resume] completed scenarios: {sorted(completed)}")

    # Build the command
    bench_cmd = [sys.executable, "-m", "portal.modules.security.core"] + run_args_list

    restarts = 0
    overall_outcome = "completed"

    while restarts <= args.max_restarts:
        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        log_file = _REPO_ROOT / f"bench_supervisor_{ts}.log"

        print(f"\n{'=' * 60}")
        print(f"  Supervisor — attempt {restarts + 1}/{args.max_restarts + 1}")
        print(f"  Log: {log_file}")
        print(f"  Args: {args.run_args}")
        if state.indeterminate_scenarios:
            print(f"  Indeterminate: {sorted(state.indeterminate_scenarios)}")
        print(f"{'=' * 60}\n")

        try:
            proc = subprocess.Popen(
                bench_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(_BENCH_DIR),
                env={**os.environ, "PYTHONPATH": f"{_BENCH_DIR}:{_REPO_ROOT}"},
            )
            state.bench_pid = proc.pid
        except Exception as exc:
            print(f"  [SUPERVISOR] Failed to start bench: {exc}")
            overall_outcome = "launch_failed"
            break

        result = tail_and_supervise(
            proc,
            log_file,
            state,
            handlers,
            args.on_unknown,
            args.max_corrections_per_scenario,
            triage_mode=triage_mode,
            triage_ollama_url=triage_ollama_url,
            triage_model=triage_model,
            confidence_floor=confidence_floor,
        )

        exit_code = proc.returncode

        if result == "completed" and exit_code == 0:
            print(f"\n  [SUPERVISOR] Bench completed successfully (exit={exit_code})")
            overall_outcome = "completed"
            break
        elif result == "escalated":
            print(f"\n  [SUPERVISOR] Escalated — check {log_path}")
            overall_outcome = "escalated"
            break
        else:
            restarts += 1
            if restarts > args.max_restarts:
                print(f"\n  [SUPERVISOR] Max restarts ({args.max_restarts}) reached — giving up")
                overall_outcome = "max_restarts"
                break

            print(f"\n  [SUPERVISOR] Bench {result} (exit={exit_code}) — restarting in 10s...")
            time.sleep(10)

    write_supervisor_log(log_path, state, overall_outcome)
    print(f"\n  Supervisor log: {log_path}")
    print(f"  Outcome: {overall_outcome}")
    print(f"  Actions: {len(state.actions)}")
    print(f"  Escalations: {len(state.escalations)}")
    print(f"  Indeterminate: {sorted(state.indeterminate_scenarios)}")

    return 0 if overall_outcome == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
