"""Triage action allowlist — the ONLY actions Layer 2 can trigger.

Each action maps to an EXISTING primitive (Proxmox MCP, lab_targets, Ollama API,
or supervisor state). Every action is reversible/safe — no action deletes data or
advances an attack. If triage returns an action not in ALLOWED_ACTIONS → reject,
log, pause_for_human.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

# ── Primitive wrappers (thin, parameterized) ──────────────────────────────────


def _proxmox_call(tool: str, args: dict[str, Any], timeout: int = 120) -> bool:
    """Call a Proxmox MCP tool via bench_lab_exec (lazy import)."""
    try:
        import bench_lab_exec

        r = bench_lab_exec._proxmox_mcp_call(tool, args, timeout=timeout)
        return bool(r.get("ok"))
    except Exception:
        return False


def _restart_lxc(params: dict[str, Any]) -> dict[str, Any]:
    """Start an LXC container via Proxmox MCP."""
    vmid = params.get("vmid", 112)
    ok = _proxmox_call("proxmox_container_start", {"vmid": int(vmid), "wait": True})
    if ok:
        time.sleep(15)  # wait for docker to settle
    return {"action": "restart_lxc", "vmid": vmid, "ok": ok}


def _restart_vm(params: dict[str, Any]) -> dict[str, Any]:
    """Start a VM via Proxmox MCP."""
    vmid = params.get("vmid", 0)
    ok = _proxmox_call("proxmox_vm_start", {"vmid": int(vmid), "wait": True})
    return {"action": "restart_vm", "vmid": vmid, "ok": ok}


def _revert_target(params: dict[str, Any]) -> dict[str, Any]:
    """Revert lab targets to clean snapshot (teardown only)."""
    try:
        import bench_lab_exec

        bench_lab_exec.lab_teardown()
        time.sleep(5)
        return {"action": "revert_target", "ok": True}
    except Exception as exc:
        return {"action": "revert_target", "ok": False, "error": str(exc)}


def _respin_target(params: dict[str, Any]) -> dict[str, Any]:
    """Revert + re-start lab targets (teardown + setup)."""
    try:
        import bench_lab_exec

        bench_lab_exec.lab_teardown()
        time.sleep(5)
        bench_lab_exec.lab_setup()
        time.sleep(15)
        return {"action": "respin_target", "ok": True}
    except Exception as exc:
        return {"action": "respin_target", "ok": False, "error": str(exc)}


def _skip_scenario(params: dict[str, Any]) -> dict[str, Any]:
    """Record scenario as indeterminate (caller handles state update)."""
    return {
        "action": "skip_scenario",
        "scenario": params.get("scenario", ""),
        "ok": True,
    }


def _reload_model(params: dict[str, Any]) -> dict[str, Any]:
    """Probe Ollama API for available models (triggers lazy load)."""
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
        return {"action": "reload_model", "models": models, "ok": True}
    except Exception as exc:
        return {"action": "reload_model", "ok": False, "error": str(exc)}


def _pause_for_human(params: dict[str, Any]) -> dict[str, Any]:
    """Safe default — signals that human intervention is needed."""
    return {"action": "pause_for_human", "ok": True}


# ── The allowlist — the ONLY actions triage can trigger ────────────────────────

ALLOWED_ACTIONS: dict[str, dict[str, Any]] = {
    "restart_lxc": {
        "fn": _restart_lxc,
        "description": "Start an LXC container via Proxmox MCP",
        "required_params": ["vmid"],
        "reversible": True,
    },
    "restart_vm": {
        "fn": _restart_vm,
        "description": "Start a VM via Proxmox MCP",
        "required_params": ["vmid"],
        "reversible": True,
    },
    "revert_target": {
        "fn": _revert_target,
        "description": "Revert lab targets to clean snapshot (teardown only)",
        "required_params": [],
        "reversible": True,
    },
    "respin_target": {
        "fn": _respin_target,
        "description": "Revert + re-start lab targets (full cycle)",
        "required_params": [],
        "reversible": True,
    },
    "skip_scenario": {
        "fn": _skip_scenario,
        "description": "Skip current scenario, mark indeterminate",
        "required_params": ["scenario"],
        "reversible": True,
    },
    "reload_model": {
        "fn": _reload_model,
        "description": "Probe Ollama API for available models",
        "required_params": [],
        "reversible": True,
    },
    "pause_for_human": {
        "fn": _pause_for_human,
        "description": "Pause for human intervention (safe default)",
        "required_params": [],
        "reversible": True,
    },
}


def is_action_allowed(action_name: str) -> bool:
    """Check if an action name is in the allowlist."""
    return action_name in ALLOWED_ACTIONS


def is_action_reversible(action_name: str) -> bool:
    """Check if an action is reversible (all currently are)."""
    entry = ALLOWED_ACTIONS.get(action_name)
    return bool(entry and entry.get("reversible", False))


def execute_action(action_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute an allowlisted action. Returns result dict.

    Raises KeyError if action_name is not in ALLOWED_ACTIONS.
    The caller (supervisor) should check is_action_allowed() first.
    """
    entry = ALLOWED_ACTIONS[action_name]
    fn = entry["fn"]
    return fn(params)


def get_action_menu_description() -> str:
    """Return a human-readable description of the action menu for prompts."""
    lines = []
    for name, entry in ALLOWED_ACTIONS.items():
        params = ", ".join(entry.get("required_params", [])) or "none"
        lines.append(f"  - {name}: {entry['description']} (params: {params})")
    return "\n".join(lines)
