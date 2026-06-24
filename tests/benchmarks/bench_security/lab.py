"""Lab lifecycle — probing, snapshot/restore, tool dispatch, stealth queries.

Imports from ``_data`` for lab constants and from ``_config`` for BenchConfig.
No imports from chain, blue, or cli modules.
"""

from __future__ import annotations

import json as _json
import os
import re
import sys
import time

from ._data import (
    _LAB_ADMIN_PASS,
    _LAB_CLEAN_SNAPSHOT,
    _LAB_DC,
    _LAB_DC_VMID,
    _LAB_EXEC_AVAILABLE,
    _LAB_SERVICE_PROBES,
    _LAB_SRV,
    _LAB_SRV_VMID,
    _LAB_WEB,
    _STEALTH_EVENT_IDS,
    _STEALTH_QUERY_TIMEOUT,
    CHAIN_INHERITANCE,
    _chain_artifacts,
    _lab_mcp_call,
    _proxmox_mcp_call,
)

# ── Sandbox output parsing ───────────────────────────────────────────────────


def parse_sandbox_output(raw: str) -> tuple[bool, str]:
    """Extract clean terminal text from the MCP sandbox JSON envelope.

    Returns (success, human-readable output).
    """
    try:
        d = _json.loads(raw)
        ok = d.get("success", False)
        stdout = d.get("stdout", "").strip()
        stderr = d.get("stderr", "").strip()
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr] {stderr}")
        if not parts:
            parts.append(f"[exit_code={d.get('exit_code', '?')}]")
        return ok, "\n".join(parts)
    except Exception:
        return bool(raw.strip()), raw


# ── Lab service probing ──────────────────────────────────────────────────────


def probe_lab_services(
    target_dc: str = "",
    target_web: str = "",
    dry_run: bool = False,
) -> dict[str, bool]:
    """Probe which lab services are reachable before running chains.

    Returns a dict mapping service name to reachable (bool).
    """
    if not _LAB_EXEC_AVAILABLE:
        return {}
    dc = target_dc or _LAB_DC or "10.10.11.21"
    web = target_web or _LAB_WEB or "10.10.11.50"
    meta3 = os.environ.get("LAB_TARGET_META3_WIN", "10.10.11.10")
    results: dict[str, bool] = {}
    if dry_run:
        for svc in _LAB_SERVICE_PROBES:
            results[svc] = True
        return results
    for svc_name, (_port, cmd_template, exp_keywords) in _LAB_SERVICE_PROBES.items():
        if svc_name.startswith("meta3_"):
            host = meta3
        elif (
            svc_name.startswith("vulnapp_")
            or svc_name.startswith("http_")
            or svc_name == "redis"
            or svc_name == "nfs"
        ):
            host = web
        else:
            host = dc
        cmd = cmd_template.replace("${host}", host)
        try:
            r = _lab_mcp_call(cmd, timeout=15)
            ok, out = parse_sandbox_output(r.get("output", ""))
            reachable = ok and any(k.lower() in out.lower() for k in exp_keywords)
        except Exception:
            reachable = False
        results[svc_name] = reachable
    return results


def print_lab_probe_report(probe: dict[str, bool]) -> None:
    """Print a human-readable lab service probe report."""
    print("\n── Lab Service Probe ──")
    reachable = [s for s, ok in probe.items() if ok]
    unreachable = [s for s, ok in probe.items() if not ok]
    for s in sorted(reachable):
        print(f"  [UP]    {s}")
    for s in sorted(unreachable):
        print(f"  [DOWN]  {s}")
    print(f"  {len(reachable)}/{len(probe)} services reachable\n")


# ── Proxmox snapshot/restore lifecycle ───────────────────────────────────────


def snapshot_lab_vms(snapname: str = "", dry_run: bool = False) -> bool:
    """Create a named snapshot of all lab VMs via Proxmox MCP before chain run."""
    if not _LAB_EXEC_AVAILABLE or not _LAB_DC_VMID:
        return True
    snapname = snapname or f"prechain-{int(time.monotonic())}"
    if dry_run:
        print(f"  [proxmox] DRY-RUN snapshot '{snapname}' for vmid={_LAB_DC_VMID},{_LAB_SRV_VMID}")
        return True
    ok = True
    for vmid, label in [(_LAB_DC_VMID, "dc01"), (_LAB_SRV_VMID, "srv01")]:
        if not vmid:
            continue
        print(f"  [proxmox] snapshot {label} (vmid={vmid}) → {snapname} ...", end=" ", flush=True)
        try:
            r = _proxmox_mcp_call(
                "proxmox_create_snapshot",
                {"vmid": int(vmid), "snapname": snapname, "description": "pre-bench-chain"},
                timeout=120,
            )
            if r["ok"]:
                print("OK")
            else:
                print(f"FAIL: {r.get('error')}")
                ok = False
        except Exception as exc:
            print(f"ERR: {exc}")
            ok = False
    return ok


def restore_lab_vms(snapname: str = "", dry_run: bool = False) -> bool:
    """Restore all lab VMs to a named snapshot via Proxmox MCP after chain run."""
    if not _LAB_EXEC_AVAILABLE or not _LAB_DC_VMID:
        return True
    snapname = snapname or _LAB_CLEAN_SNAPSHOT
    if dry_run:
        print(f"  [proxmox] DRY-RUN restore to snapshot '{snapname}'")
        return True
    ok = True
    for vmid, label in [(_LAB_DC_VMID, "dc01"), (_LAB_SRV_VMID, "srv01")]:
        if not vmid:
            continue
        print(f"  [proxmox] restore {label} (vmid={vmid}) → {snapname} ...", end=" ", flush=True)
        try:
            r = _proxmox_mcp_call(
                "proxmox_rollback_snapshot",
                {"vmid": int(vmid), "snapname": snapname},
                timeout=240,
            )
            if r["ok"]:
                print("OK")
            else:
                print(f"FAIL: {r.get('error')}")
                ok = False
        except Exception as exc:
            print(f"ERR: {exc}")
            ok = False
    if ok:
        print("  [proxmox] waiting 15s for VMs to boot ...", end=" ", flush=True)
        time.sleep(15)
        print("ok")
    return ok


# ── Stealth queries ──────────────────────────────────────────────────────────


def query_stealth_events(step_name: str, target_dc: str = "") -> dict:
    """Query the lab DC Security event log for indicators of a technique."""
    event_ids = _STEALTH_EVENT_IDS.get(step_name, [])
    if not event_ids or not _LAB_EXEC_AVAILABLE:
        return {"step": step_name, "event_ids_queried": event_ids, "total_events": 0, "per_id": {}}
    dc = target_dc or _LAB_DC or "10.10.11.21"
    per_id: dict[int, int] = {}
    total = 0
    for eid in event_ids:
        cmd = (
            f"nxc smb {dc} -u Administrator -p '{_LAB_ADMIN_PASS}' "
            f"-x 'wevtutil qe Security /q:\"*[System[(EventID={eid})]]\" /c:50 /rd:true /f:text 2>&1 | wc -l'"
        )
        try:
            r = _lab_mcp_call(cmd, timeout=_STEALTH_QUERY_TIMEOUT)
            ok, out = parse_sandbox_output(r.get("output", ""))
            count = int(out.strip()) if out.strip().isdigit() else 0
        except Exception:
            count = -1
        per_id[eid] = count
        if count > 0:
            total += count
    return {
        "step": step_name,
        "event_ids_queried": event_ids,
        "total_events": total,
        "per_id": per_id,
    }


# ── Blue active response dispatch ────────────────────────────────────────────


def dispatch_blue_response(
    tool_name: str,
    arguments: dict,
    dc: str = "",
) -> dict:
    """Execute a blue team active response tool in the lab sandbox."""
    if not _LAB_EXEC_AVAILABLE:
        return {"ok": False, "output": "lab exec not available", "elapsed_s": 0.0}
    dc = dc or _LAB_DC or "10.10.11.21"
    try:
        if tool_name == "block_ip":
            ip = arguments.get("ip", "")
            if not ip:
                return {"ok": False, "output": "ip required", "elapsed_s": 0.0}
            cmd = f"nxc smb {dc} -u Administrator -p '{_LAB_ADMIN_PASS}' -x 'netsh advfirewall firewall add rule name=\"Block_Attacker\" dir=in remoteip={ip} action=block' 2>&1"
            r = _lab_mcp_call(cmd, timeout=30)
            ok, out = parse_sandbox_output(r.get("output", ""))
            return {"ok": ok, "output": out, "elapsed_s": r.get("elapsed_s", 0.0)}
        elif tool_name == "disable_account":
            username = arguments.get("username", "")
            if not username:
                return {"ok": False, "output": "username required", "elapsed_s": 0.0}
            cmd = f"nxc smb {dc} -u Administrator -p '{_LAB_ADMIN_PASS}' -x 'net user {username} /active:no' 2>&1"
            r = _lab_mcp_call(cmd, timeout=30)
            ok, out = parse_sandbox_output(r.get("output", ""))
            return {"ok": ok, "output": out, "elapsed_s": r.get("elapsed_s", 0.0)}
        elif tool_name == "revoke_tgt":
            cmd = (
                f"nxc smb {dc} -u Administrator -p '{_LAB_ADMIN_PASS}' "
                f"-x 'powershell -c \"Reset-ComputerMachinePassword; klist purge\"' 2>&1"
            )
            r = _lab_mcp_call(cmd, timeout=30)
            ok, out = parse_sandbox_output(r.get("output", ""))
            return {"ok": ok, "output": out, "elapsed_s": r.get("elapsed_s", 0.0)}
        else:
            return {"ok": False, "output": f"unknown blue tool: {tool_name}", "elapsed_s": 0.0}
    except Exception as exc:
        return {"ok": False, "output": str(exc), "elapsed_s": 0.0}


# ── Time sync ────────────────────────────────────────────────────────────────

_lab_time_synced = False


def ensure_lab_time_sync() -> None:
    """Sync container clock with DC once per bench run via ntpdate."""
    global _lab_time_synced
    if _lab_time_synced:
        return
    _lab_time_synced = True
    try:
        dc = os.environ.get("LAB_TARGET_DC", "")
        if not dc:
            return
        import subprocess

        result = subprocess.run(
            [
                "docker",
                "exec",
                "portal5-dind",
                "docker",
                "run",
                "--rm",
                "--net",
                "bridge",
                "portal5-attack:latest",
                "sh",
                "-c",
                f"ntpdate -qu {dc} 2>&1",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (result.stdout + result.stderr).strip()
        if out:
            print(f"  [lab-time-sync] {out[:80]}", file=sys.stderr)
    except Exception as e:
        print(f"  [lab-time-sync] skipped: {e}", file=sys.stderr)


# ── Lab tool dispatch ────────────────────────────────────────────────────────


def dispatch_lab_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a model-emitted tool call in the real lab sandbox."""
    try:
        if tool_name == "execute_bash":
            cmd = arguments.get("cmd", "").strip()
            if not cmd:
                return {"ok": False, "output": "(empty cmd)", "elapsed_s": 0.0}
            ensure_lab_time_sync()
            r = _lab_mcp_call(cmd, timeout=90)  # type: ignore[misc]
            ok, clean = parse_sandbox_output(r.get("output", ""))
            return {"ok": ok, "output": clean, "elapsed_s": r.get("elapsed_s", 0.0)}
        elif tool_name == "execute_python":
            code = arguments.get("code", "").strip()
            if not code:
                return {"ok": False, "output": "(empty code)", "elapsed_s": 0.0}
            import shlex

            py_cmd = f"echo {shlex.quote(code)} | python3 2>&1 | head -200"
            r = _lab_mcp_call(py_cmd, timeout=90)  # type: ignore[misc]
            ok, clean = parse_sandbox_output(r.get("output", ""))
            return {"ok": ok, "output": clean, "elapsed_s": r.get("elapsed_s", 0.0)}
        else:
            return {
                "ok": True,
                "output": f"[{tool_name}: not dispatched in lab-exec mode]",
                "elapsed_s": 0.0,
            }
    except Exception as exc:
        return {"ok": False, "output": f"[dispatch error: {exc}]", "elapsed_s": 0.0}


# ── Artifact injection ──────────────────────────────────────────────────────


def extract_chain_artifacts(
    prompt_key: str,
    chain_results: list[dict],
) -> dict[str, str]:
    """Extract reusable artifacts (hashes, creds, paths) from chain output."""
    artifacts: dict[str, str] = {}
    all_output = ""
    for r in chain_results:
        if r.get("_blue_defender"):
            continue
        for lo in r.get("lab_outputs", []):
            all_output += lo.get("output", "") + "\n"
    if not all_output:
        return artifacts
    for m in re.findall(r"[0-9a-fA-F]{32}:[0-9a-fA-F]{32}", all_output):
        artifacts.setdefault("ntlm_hash", m)
    for m in re.findall(r"\$krb5tgs\$23\$\*[^\s]{20,}", all_output):
        artifacts.setdefault("krb5tgs_hash", m)
    for m in re.findall(r"(svc_\w+)\b.*?password\s*[=:]\s*(\S+)", all_output, re.IGNORECASE):
        artifacts.setdefault(f"credential_{m[0]}", f"{m[0]}:{m[1]}")
    for m in re.findall(r"/tmp/[a-zA-Z0-9_\-\.]+", all_output):
        artifacts.setdefault("hash_path", m)
    _chain_artifacts[prompt_key] = artifacts
    return artifacts


def inject_chain_artifacts(prompt_key: str, start_prompt: str) -> str:
    """If this prompt inherits from prior runs, inject their artifacts."""
    inherited = CHAIN_INHERITANCE.get(prompt_key, [])
    if not inherited:
        return start_prompt
    inject_lines: list[str] = []
    for ancestor in inherited:
        artifacts = _chain_artifacts.get(ancestor, {})
        if artifacts:
            inject_lines.append(f"\n[Inherited artifacts from '{ancestor}' chain:]")
            for k, v in artifacts.items():
                inject_lines.append(f"  {k}: {v}")
    if inject_lines:
        return start_prompt + "\n".join(inject_lines)
    return start_prompt


# ── Step dependency DAG ──────────────────────────────────────────────────────


def build_step_dag(seq: list[dict]) -> dict[str, list[str]]:
    """Build an adjacency list DAG from step dependencies."""
    dag: dict[str, list[str]] = {}
    prev: str | None = None
    for step in seq:
        name = step["step"]
        deps = step.get("depends_on", [])
        if deps:
            dag[name] = list(deps)
        elif prev:
            dag[name] = [prev]
        else:
            dag[name] = []
        prev = name
    return dag


def dag_parallel_groups(dag: dict[str, list[str]]) -> list[list[str]]:
    """Partition steps into parallel groups (topological levels)."""
    completed: set[str] = set()
    remaining = set(dag.keys())
    groups: list[list[str]] = []
    while remaining:
        ready = [s for s in remaining if all(d in completed for d in dag.get(s, []))]
        if not ready:
            groups.append(sorted(remaining))
            break
        groups.append(sorted(ready))
        completed.update(ready)
        remaining -= set(ready)
    return groups


# ── Lab dispatch for synthetic chain ─────────────────────────────────────────


def lab_dispatch(fn_name: str, fn_args: dict, dry_run: bool = False) -> str:
    """Dispatch a synthetic chain tool call to the real lab or return synthetic result.

    This is the bridge between the chain test's tool calls and the lab sandbox.
    In synthetic mode, returns canned responses. In lab-exec mode, runs real commands.
    """
    if not _LAB_EXEC_AVAILABLE:
        return f"OK: {fn_name} completed (synthetic)."

    # Map chain tool names to real lab commands
    dc = _LAB_DC or "10.10.11.21"
    srv = _LAB_SRV or "10.10.11.33"

    if fn_name == "start_lab_target":
        return "Lab target started (synthetic)."
    elif fn_name == "run_nmap_scan":
        target = fn_args.get("target", dc)
        cmd = f"nmap -sV -sC {target} 2>&1 | head -30"
    elif fn_name == "check_cve":
        host = fn_args.get("host", dc)
        port = fn_args.get("port", 445)
        cve = fn_args.get("cve_id", "CVE-2017-0144")
        cmd = f"echo 'Checking {cve} on {host}:{port}' && nmap -p {port} --script smb-vuln-ms17-010 {host} 2>&1 | head -10"
    elif fn_name == "exploit_service":
        host = fn_args.get("host", dc)
        port = fn_args.get("port", 445)
        cmd = f"echo 'Exploiting {host}:{port}' && echo 'shell obtained'"
    elif fn_name == "establish_persistence":
        cmd = f"echo 'persistence established on {dc}'"
    elif fn_name == "lateral_move":
        cmd = f"echo 'lateral move to {srv}' && echo 'session 1 opened'"
    elif fn_name == "exfiltrate_data":
        cmd = f"echo 'exfiltrating from {dc}' && cat /etc/hostname"
    elif fn_name == "revert_lab_target":
        return "Lab targets reverted (synthetic)."
    else:
        return f"OK: {fn_name} completed (synthetic)."

    if dry_run:
        return f"[DRY-RUN] would run: {cmd}"

    try:
        r = _lab_mcp_call(cmd, timeout=90)  # type: ignore[misc]
        ok, clean = parse_sandbox_output(r.get("output", ""))
        return clean
    except Exception as exc:
        return f"[lab error: {exc}]"
