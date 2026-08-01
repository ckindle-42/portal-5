#!/usr/bin/env python3
"""Capture replayable lab data with deterministic, machine-checked recipes."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portal.modules.security.core.blue import collect_and_ship_scenario_telemetry
from portal.modules.security.core.capture_recipes import (
    CAPTURE_RECIPES,
    render_host_command,
    render_postcondition_command,
    render_recipe_command,
)
from portal.modules.security.core.episode import new_episode_id
from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.lab import lab_dispatch
from portal.modules.security.core.siem.capture_store import capture_replay_issues
from portal.modules.security.core.siem.network_capture import (
    start_network_capture,
    stop_network_capture,
)
from scripts.lab_host import _host_exec
from scripts.lab_targets import cmd_down, ensure_target_ready


def run_recipe(name: str, *, dry_run: bool = False) -> dict:
    """Run one recipe and return its independently checked capture result."""
    if name not in CAPTURE_RECIPES:
        raise KeyError(f"no deterministic capture recipe for {name}")
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name}")

    scenario = dict(SCENARIOS[name])
    gate = ensure_target_ready(scenario, dry_run=dry_run)
    result: dict = {"scenario": name, "gate": gate, "recipe_success": False}
    if not gate.get("ready"):
        result["error"] = "TARGET_UNAVAILABLE"
        if scenario.get("vulhub_env") and not dry_run:
            with suppress(Exception):
                result["teardown"] = cmd_down(str(scenario["vulhub_env"]))
        return result
    host, port = gate.get("host"), gate.get("port")
    if not host or not port:
        result["error"] = "TARGET_ADDRESS_UNRESOLVED"
        return result

    scenario["target_host"] = str(host)
    scenario["gate_port"] = int(port)
    episode_id = new_episode_id(name)
    result["episode_id"] = episode_id
    command = render_recipe_command(CAPTURE_RECIPES[name], host=str(host), port=int(port))
    if dry_run:
        result.update({"recipe_success": True, "command": command})
        return result

    output = ""
    observed_telemetry: dict[str, list[str]] = {}
    postcondition_success = not CAPTURE_RECIPES[name].postcondition_command
    postcondition_output = ""
    host_setup_success = not CAPTURE_RECIPES[name].host_setup_command
    host_setup_output = ""
    if CAPTURE_RECIPES[name].host_setup_command:
        # Target-establishment (install wizards, user/repo provisioning, readiness
        # polling) must complete BEFORE the capture window opens. Found live
        # 2026-07-31: running setup inside the capture window buried the actual
        # exploit request under 20+ install-wizard requests in the same
        # container's access log, and the T1190 evidence-selection pass never
        # surfaced it — a "recipe_success: true" capture came back
        # CAPTURE_GROUND_TRUTH_INVALID. Setup is a precondition, not part of the
        # attack episode; it must never share the episode's telemetry window.
        setup = _host_exec(
            render_host_command(
                CAPTURE_RECIPES[name].host_setup_command,
                host=str(host),
                port=int(port),
            ),
            timeout=30,
        )
        host_setup_output = setup.get("output", "").strip()
        host_setup_success = bool(
            setup.get("ok")
            and re.search(CAPTURE_RECIPES[name].host_setup_pattern, host_setup_output)
        )
        if not host_setup_success:
            result.update(
                {
                    "error": f"HOST_SETUP_FAILED: {host_setup_output}",
                    "host_setup_success": False,
                    "host_setup_output": host_setup_output,
                }
            )
            if scenario.get("vulhub_env"):
                with suppress(Exception):
                    result["teardown"] = cmd_down(str(scenario["vulhub_env"]))
            return result

    started = time.time()
    capture = start_network_capture(episode_id, str(host))
    try:
        output = lab_dispatch("execute_bash", {"cmd": command}, dry_run=False)
        if CAPTURE_RECIPES[name].postcondition_command:
            for _attempt in range(5):
                probe = _host_exec(
                    render_postcondition_command(
                        CAPTURE_RECIPES[name], port=int(port), host=str(host)
                    ),
                    timeout=30,
                )
                postcondition_output = probe.get("output", "").strip()
                postcondition_success = bool(
                    probe.get("ok")
                    and re.search(CAPTURE_RECIPES[name].postcondition_pattern, postcondition_output)
                )
                if postcondition_success:
                    break
                time.sleep(1)
            if postcondition_output:
                observed_telemetry["target:postcondition"] = [postcondition_output]
    finally:
        capture = stop_network_capture(capture)
        if CAPTURE_RECIPES[name].host_cleanup_command:
            with suppress(Exception):
                _host_exec(
                    render_host_command(
                        CAPTURE_RECIPES[name].host_cleanup_command,
                        host=str(host),
                        port=int(port),
                    ),
                    timeout=30,
                )

    recipe_success = bool(
        host_setup_success
        and re.search(CAPTURE_RECIPES[name].success_pattern, output)
        and postcondition_success
    )
    result.update(
        {
            "recipe_success": recipe_success,
            "output_tail": output[-4000:],
            "network_capture_error": capture.error,
            "host_setup_success": host_setup_success,
            "host_setup_output": host_setup_output,
            "postcondition_success": postcondition_success,
            "postcondition_output": postcondition_output,
            "pcap_path": capture.local_pcap_path,
        }
    )
    try:
        capture_path, indexed, collection_error = collect_and_ship_scenario_telemetry(
            scenario,
            started,
            lab_exec=True,
            episode_id=episode_id,
            network_telemetry=capture.telemetry,
            observed_telemetry=observed_telemetry,
            pcap_path=capture.local_pcap_path,
        )
        result.update(
            {
                "capture_path": capture_path,
                "indexed_confirmed": indexed,
                "collection_error": collection_error,
            }
        )
        if capture_path:
            payload = json.loads(Path(capture_path).read_text())
            result["validity"] = payload.get("validity")
            result["replay_issues"] = capture_replay_issues(payload, require_pcap=True)
    finally:
        if scenario.get("vulhub_env"):
            with suppress(Exception):
                result["teardown"] = cmd_down(str(scenario["vulhub_env"]))

    result["certified"] = bool(
        recipe_success
        and result.get("indexed_confirmed")
        and not result.get("replay_issues", ["NO_CAPTURE"])
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", choices=sorted(CAPTURE_RECIPES))
    parser.add_argument("--all", action="store_true", help="Run every deterministic recipe")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    names = sorted(CAPTURE_RECIPES) if args.all else list(args.scenario or [])
    if not names:
        parser.error("pass --all or at least one --scenario")

    results = []
    for name in names:
        print(f"\n── deterministic capture: {name} ──", flush=True)
        try:
            result = run_recipe(name, dry_run=args.dry_run)
        except Exception as exc:
            result = {"scenario": name, "certified": False, "error": str(exc)}
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)
        if args.output:
            args.output.write_text(json.dumps(results, indent=2))
    return 0 if all(item.get("certified") or args.dry_run for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
