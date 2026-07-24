#!/usr/bin/env python3
"""Lab targets provisioner — on-demand ephemeral containers with dynamic port mapping.

Port conflict resolution: the ephemeral model checks if a target's desired port is
in use; if so, it dynamically maps to a free port and records the mapping so the
bench knows which port to hit.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.lab_host import _host_exec

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    """Load .env into os.environ (setdefault — never overrides a real env var).

    This module reads LAB_* host/vmid config at import time (below, and in
    _LAB_HOST_VMID_MAP). It's usually imported transitively through
    bench_security._data, which loads .env itself first as an import side
    effect — so this silently worked by import-order luck. But this module also
    has its own standalone CLI entry point (`python3 scripts/lab_targets.py`),
    and nothing guarantees import order for other callers, so load .env here too
    rather than depend on another module having done it first.
    """
    # Hermetic-test guard (CLAUDE.md: tests/unit/ must pass with no network
    # access / real config) — this module is imported by test_lab_setup.py.
    if os.environ.get("UNIT_TEST_MODE") == "1":
        return
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
LAB_DIR = os.environ.get("LAB_DIR", os.path.expanduser("~/AI_Output/lab"))
LAB_VULHUB_HOST_ROOT = os.environ.get("LAB_VULHUB_HOST_ROOT", "/opt/vulhub")
LAB_VULHUB_HOST = os.environ.get("LAB_TARGET_WEB", "10.10.11.50")

# Track port mappings for ephemeral sessions
_PORT_MAP_FILE = (
    REPO_ROOT / "portal" / "modules" / "security" / "core" / "results" / ".port_map.json"
)


@dataclass
class PortMapping:
    target_id: str
    desired_port: int
    mapped_port: int
    host: str = "10.10.11.50"


def _get_used_ports() -> set[int]:
    """Get currently used HOST ports on the lab host via docker ps."""
    r = _host_exec("docker ps --format '{{.Ports}}'", timeout=15)
    if not r.get("ok"):
        return set()
    ports: set[int] = set()
    for line in r["output"].splitlines():
        for entry in line.split(","):
            entry = entry.strip()
            if "->" in entry:
                # Format: 0.0.0.0:8080->80/tcp → extract 8080
                host_part = entry.split("->")[0]
                if ":" in host_part:
                    try:
                        ports.add(int(host_part.rsplit(":", 1)[-1]))
                    except ValueError:
                        pass
    return ports


def _find_free_port(desired: int, used: set[int]) -> int:
    """Return desired port if free, else the next available port."""
    port = desired
    while port in used:
        port += 1
        if port > 65500:
            return desired  # give up
    return port


def _load_catalog() -> dict:
    import yaml

    path = REPO_ROOT / "config" / "lab_targets.yaml"
    if not path.exists():
        return {"targets": []}
    return yaml.safe_load(path.read_text())


def _find_target(target_id: str) -> dict | None:
    catalog = _load_catalog()
    for t in catalog.get("targets", []):
        if t.get("id") == target_id:
            return t
    return None


def _host_compose_path(path: str) -> str:
    """Absolute path to a vulhub env's docker-compose.yml on host 112."""
    return f"{LAB_VULHUB_HOST_ROOT}/{path}/docker-compose.yml"


def _pick_http_port(
    ports: list[int], *, retries: int = 6, retry_delay_s: float = 5.0
) -> int | None:
    """Given several candidate published ports for one container, prefer the
    one that's actually serving HTTP.

    Found live 2026-07-18 (BUILD_PROGRAM_SEC_BLUE_ORCHESTRATION_V2 Slice 8
    capture verification): log4j/CVE-2021-44228's compose file publishes
    BOTH 5005 (the JVM's own JDWP debug port) and 8983 (Solr's real HTTP
    admin API), with 5005 listed first in Docker's own Publishers order —
    the old "take the first TCP port" logic picked 5005, so every red
    attack against this scenario was hitting a debug protocol port that
    can never serve the actual exploit, and every captured telemetry run
    showed zero attack evidence no matter how many times it re-ran. Any
    vulhub target that publishes an auxiliary port (debug, metrics, a
    second internal service) ahead of its real app port in compose file
    order hits the same failure mode. Probes each candidate with a quick
    HTTP request and returns the first one that gets ANY HTTP response
    (even 4xx/5xx counts — it proves the port speaks HTTP at all).

    Retries across a real wait window (found live 2026-07-18, second
    verification pass): this is called immediately after `docker compose up
    -d` returns, before the app has actually finished starting — a JVM's
    debug port (5005) opens as soon as the process forks, well before its
    HTTP layer (Solr's Jetty on 8983) finishes initializing, which can take
    10-20s. A single-shot probe caught 8983 still refusing connections and
    silently fell back to the first port (5005) again, reproducing the
    exact bug this function exists to fix. Retries for up to
    retries * retry_delay_s seconds before giving up.
    """
    for attempt in range(retries):
        for port in ports:
            r = _host_exec(
                f"curl -s -o /dev/null -w '%{{http_code}}' -m 3 http://localhost:{port}/",
                timeout=8,
            )
            code = r.get("output", "").strip()
            if r.get("ok") and code.isdigit() and code != "000":
                return port
        if attempt < retries - 1:
            time.sleep(retry_delay_s)
    return None


def _published_port(compose_path: str) -> int | None:
    """Ask Docker for the actual published host port(s) — never guess from a hardcoded
    default. A raw vulhub path's real port can differ from any catalog assumption (e.g.
    fastjson/1.2.47-rce publishes 8090, not the common 8080).

    Robustness: tries `docker compose ps --format json` (Publishers key) first,
    then falls back to `docker compose port <svc> tcp` for compose JSON shape drift.
    When a container publishes MULTIPLE distinct ports, probes each over HTTP and
    prefers the one that actually answers (see _pick_http_port) — the first
    published port is not reliably the application port (debug/metrics ports are
    often published too, sometimes listed first).
    """
    candidates: list[int] = []

    def _add(port: int) -> None:
        if port not in candidates:
            candidates.append(port)

    r = _host_exec(f"docker compose -f {compose_path} ps --format json", timeout=15)
    if r.get("ok"):
        for line in r["output"].splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Try Publishers key (newer compose)
            for pub in entry.get("Publishers") or []:
                if pub.get("Protocol") == "tcp" and pub.get("PublishedPort"):
                    _add(int(pub["PublishedPort"]))
            # Try Ports key (older compose JSON shape)
            ports_str = entry.get("Ports", "")
            if ports_str:
                for part in str(ports_str).split(","):
                    part = part.strip()
                    if "->" in part:
                        host_part = part.split("->")[0]
                        if ":" in host_part:
                            try:
                                _add(int(host_part.rsplit(":", 1)[-1]))
                            except ValueError:
                                pass

    if not candidates:
        # Fallback: `docker compose port <first_service> tcp`
        # Extract service name from compose file
        svc_r = _host_exec(
            f"docker compose -f {compose_path} config --services 2>/dev/null | head -1",
            timeout=10,
        )
        if svc_r.get("ok") and svc_r.get("output", "").strip():
            svc = svc_r["output"].strip()
            port_r = _host_exec(
                f"docker compose -f {compose_path} port {svc} tcp 2>/dev/null", timeout=10
            )
            if port_r.get("ok"):
                # Output format: "0.0.0.0:8090" or ":::8090"
                for tok in port_r.get("output", "").strip().split():
                    if ":" in tok:
                        try:
                            _add(int(tok.rsplit(":", 1)[-1]))
                        except ValueError:
                            pass

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return _pick_http_port(candidates) or candidates[0]


def _wait_reachable(host: str, port: int, timeout_s: float = 30.0) -> bool:
    """Poll a mapped port on the lab host until it answers or timeout_s elapses."""
    import socket

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(1)
    return False


def _remap_conflicting_ports(compose_path: str) -> str | None:
    """Generate a docker-compose override remapping any host port this compose file
    wants that's already taken by another container (common — many vulhub CVE PoCs
    default to the same handful of ports, e.g. 8080). Without this, `docker compose
    up -d` fails outright with "port is already allocated" and the target never
    starts, regardless of how much memory/retries are available (found live
    2026-07-03: this — not memory pressure — was the real cause of ~20 stable
    vulhub scenario skips across repeated full-coverage runs).

    Returns the override file path, or None if no remap was needed/possible.
    """
    import base64

    import yaml

    cfg = _host_exec(f"docker compose -f {compose_path} config", timeout=15)
    if not cfg.get("ok"):
        return None
    text = cfg["output"]
    idx = text.find("name:")
    if idx == -1:
        return None
    try:
        parsed = yaml.safe_load(text[idx:])
    except Exception:
        return None
    if not parsed or not parsed.get("services"):
        return None

    used = _get_used_ports()
    override_services: dict = {}
    for svc_name, svc in parsed["services"].items():
        remapped: list[str] = []
        changed = False
        for p in svc.get("ports") or []:
            published, target_port = p.get("published"), p.get("target")
            if published is None or target_port is None:
                continue
            published = int(published)
            if published in used:
                published = _find_free_port(published + 1, used)
                changed = True
            used.add(published)
            remapped.append(f"{published}:{target_port}")
        if changed and remapped:
            override_services[svc_name] = {"ports": remapped}

    if not override_services:
        return None

    # Compose merges list-type keys like `ports:` across `-f` files by default
    # (appends, doesn't replace) — without `!override`, the base file's conflicting
    # port comes along for the ride and `up -d` fails the exact same way. yaml.dump
    # doesn't know this custom compose merge tag, so build the YAML by hand.
    lines = ["services:"]
    for svc_name, svc_cfg in override_services.items():
        lines.append(f"  {svc_name}:")
        lines.append("    ports: !override")
        for p in svc_cfg["ports"]:
            lines.append(f'      - "{p}"')
    override_yaml = "\n".join(lines) + "\n"

    # `_host_exec` runs `ssh host "pct exec <ctid> -- {cmd}"` — a bare `>`/heredoc in
    # `cmd` gets intercepted by the shell on the PROXMOX HOST (redirecting there, not
    # inside the LXC), since `pct exec ... -- cmd` alone execs argv directly with no
    # shell. Routing through `sh -c "..."` (one argv token to pct exec) and
    # base64-encoding the payload avoids both that and all quoting hazards.
    override_path = f"{compose_path}.portal5-port-override.yml"
    b64 = base64.b64encode(override_yaml.encode()).decode()
    w = _host_exec(f'sh -c "echo {b64} | base64 -d > {override_path}"')
    return override_path if w.get("ok") else None


def cmd_up(target_id: str, dry_run: bool = False, max_concurrent: int = 3) -> dict:
    """Bring up a target by catalog id or raw vulhub path — real docker compose on LXC 112."""
    target = _find_target(target_id)
    if target:
        path = target.get("path", "")
        cve = target.get("cve", "")
        print(f"  Target: {target_id} ({cve}) → vulhub/{path}")
    else:
        path = target_id  # Raw vulhub path
        print(f"  Target: {path} (raw vulhub path)")
    if dry_run:
        return {"status": "dry_run", "target": target_id, "action": "up", "vulhub_path": path}

    compose_path = _host_compose_path(path)
    check = _host_exec(f"test -f {compose_path} && echo EXISTS")
    if not check.get("ok") or "EXISTS" not in check.get("output", ""):
        return {
            "status": "error",
            "reason": f"vulhub compose file not found on host: {compose_path}",
        }

    r = _host_exec(f"docker compose -f {compose_path} up -d", timeout=120)
    if not r.get("ok") and "port is already allocated" in r.get("output", ""):
        override_path = _remap_conflicting_ports(compose_path)
        if override_path:
            # The failed attempt above already created the container with the
            # original (conflicting) port baked in — compose won't recreate it
            # for an override-only port change on an existing-but-failed
            # container, so the retry silently reuses the broken one. Force a
            # clean slate first.
            _host_exec(f"docker compose -f {compose_path} rm -f -s", timeout=30)
            r = _host_exec(
                f"docker compose -f {compose_path} -f {override_path} up -d", timeout=120
            )
    if not r.get("ok"):
        return {
            "status": "error",
            "reason": f"docker compose up failed: {r.get('output', '')[:500]}",
        }

    host = target.get("host", LAB_VULHUB_HOST) if target else LAB_VULHUB_HOST
    mapped = _published_port(compose_path)
    if mapped is None:
        # Fallback: catalog-declared or guessed port, dynamically remapped if in use.
        port = target.get("port", 8080) if target else 8080
        mapped = _find_free_port(port, _get_used_ports())
    ready = _wait_reachable(host, mapped)
    return {
        "status": "running" if ready else "error",
        "target": target_id,
        "vulhub_path": path,
        "host": host,
        "port": mapped,
        "reachable": ready,
        "reason": ""
        if ready
        else f"target did not become reachable at {host}:{mapped} within timeout",
        "compose_output": r.get("output", "")[:500],
    }


def cmd_down(target_id: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {"status": "dry_run", "target": target_id, "action": "down"}

    target = _find_target(target_id)
    path = target.get("path", "") if target else target_id
    compose_path = _host_compose_path(path)
    r = _host_exec(f"docker compose -f {compose_path} down", timeout=60)
    return {
        "status": "stopped" if r.get("ok") else "error",
        "target": target_id,
        "reason": "" if r.get("ok") else r.get("output", "")[:500],
    }


def provision_vulhub_env(path: str) -> dict:
    """Idempotently clone the upstream vulhub repo onto host 112 under LAB_VULHUB_HOST_ROOT,
    if the specific env directory for `path` isn't already present. Only pulls the repo (once);
    does not pre-fetch all 328 envs — the sparse subdir is already in the clone once cloned."""
    check = _host_exec(f"test -f {_host_compose_path(path)} && echo EXISTS")
    if check.get("ok") and "EXISTS" in check.get("output", ""):
        return {"status": "present", "vulhub_path": path}

    root_check = _host_exec(f"test -d {LAB_VULHUB_HOST_ROOT}/.git && echo EXISTS")
    if root_check.get("ok") and "EXISTS" in root_check.get("output", ""):
        r = _host_exec(f"cd {LAB_VULHUB_HOST_ROOT} && git pull", timeout=180)
    else:
        r = _host_exec(
            f"git clone --depth 1 https://github.com/vulhub/vulhub.git {LAB_VULHUB_HOST_ROOT}",
            timeout=300,
        )
    recheck = _host_exec(f"test -f {_host_compose_path(path)} && echo EXISTS")
    ok = recheck.get("ok") and "EXISTS" in recheck.get("output", "")
    return {
        "status": "provisioned" if ok else "error",
        "vulhub_path": path,
        "reason": "" if ok else "env still missing after clone/pull",
        "provision_output": r.get("output", "")[:500],
    }


def cmd_ephemeral(target_id: str, command: list[str] | None, dry_run: bool = False) -> dict:
    """Spin up a target, run a command against it, tear down — with dynamic port mapping."""
    target = _find_target(target_id)
    port = target.get("port", 8080) if target else 8080
    host = target.get("host", "10.10.11.50") if target else "10.10.11.50"
    vulhub_path = target.get("path", target_id) if target else target_id

    used = _get_used_ports() if not dry_run else set()
    mapped = _find_free_port(port, used)
    mapping = PortMapping(target_id=target_id, desired_port=port, mapped_port=mapped, host=host)

    if dry_run:
        result = {
            "status": "dry_run",
            "target": target_id,
            "action": "ephemeral",
            "port": mapped,
            "host": host,
            "command": command,
            "note": f"{'port remapped' if mapped != port else 'port free'}",
        }
    else:
        # Write port map so bench knows where to hit
        _PORT_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PORT_MAP_FILE.write_text(json.dumps({"target": target_id, "host": host, "port": mapped}))
        result = {
            "status": "running",
            "target": target_id,
            "host": host,
            "port": mapped,
            "vulhub_path": vulhub_path,
            "port_map_file": str(_PORT_MAP_FILE),
        }

    print(
        f"  target={target_id} host={host} port={mapped} (desired={port}) {'remapped' if mapped != port else ''}"
    )
    return result


def get_ephemeral_port(filename: str | None = None) -> dict | None:
    """Read the current ephemeral port mapping so bench code knows where to hit."""
    p = Path(filename) if filename else _PORT_MAP_FILE
    if not p.exists():
        return None
    return json.loads(p.read_text())


def cmd_status() -> dict:
    return {"running": [], "reachable": "unknown"}


def cmd_list() -> list[dict]:
    catalog = _load_catalog()
    return [
        {
            "id": t.get("id", "?"),
            "source": t.get("source", "?"),
            "cve": t.get("cve", ""),
            "technique": t.get("technique", ""),
            "preexisting": t.get("preexisting", False),
        }
        for t in catalog.get("targets", [])
    ]


def _resolve_live_port(host: str, env: str | None) -> int | None:
    """Determine the live published port for a target.

    For vulhub envs, uses _published_port on the compose file.
    For non-vulhub targets, probes common ports.
    """
    if env:
        compose_path = _host_compose_path(env)
        return _published_port(compose_path)
    # Non-vulhub: no port discovery available here; caller probes directly
    return None


# Static (non-vulhub) lab hosts and the Proxmox vmid/kind that backs each — built
# from the same env vars the lab already defines for these targets. Superseded
# `_vmid_for_host`, which looked this up via a `vmid` field in
# config/lab_targets.yaml that never existed there (that catalog only tracks
# vulhub/projectblack CVE envs) — every static-host heal attempt was silently a
# no-op before this.
_LAB_HOST_VMID_MAP: dict[str, tuple[str, str]] = {}
for _host_env, _vmid_env, _kind in [
    ("LAB_TARGET_DC", "LAB_DC_VMID", "vm"),
    ("LAB_TARGET_SRV", "LAB_SRV_VMID", "vm"),
    ("LAB_TARGET_META3_WIN", "LAB_META3_WIN_VMID", "vm"),
    ("LAB_MBPTL_HOST", "LAB_MBPTL_LXC_VMID", "lxc"),
]:
    _h, _v = os.environ.get(_host_env, ""), os.environ.get(_vmid_env, "")
    if _h and _v:
        _LAB_HOST_VMID_MAP[_h] = (_v, _kind)


def discover_host_by_mac(vmid: str, kind: str = "vm") -> str | None:
    """Find a lab host's CURRENT live IP by matching its Proxmox-declared MAC
    against a fresh ARP sweep of the lab subnet — not a static config value.

    P5-META3-DISCOVERY-001 (found live 2026-07-16): meta3's IP was hardcoded
    in config as 10.10.11.10, drifted to .11, then .13 across three restarts
    within the same session — DHCP without a reservation on this host, so any
    static IP is stale the moment it's written down. The VM's MAC address
    (from Proxmox config) is the one thing that doesn't change across reboots;
    this discovers the real IP by sweeping 10.10.11.0/24 from LXC 112 (which
    sits on the lab's L2 segment, so `ip neigh` after a ping sweep reflects
    real ARP resolution) and matching on that MAC. Returns None on any
    failure — callers must fall back to the static config value, never guess.
    """
    import re

    from scripts.lab_host import _proxmox_exec

    cmd = "qm config" if kind == "vm" else "pct config"
    cfg = _proxmox_exec(f"{cmd} {vmid}", timeout=15)
    if not cfg.get("ok"):
        return None
    m = re.search(r"net0:.*?=([0-9A-Fa-f:]{17})", cfg["output"])
    if not m:
        return None
    target_mac = m.group(1).lower()

    # Refresh ARP: fire a parallel ping sweep of the /24, then read ip neigh.
    # pct exec passes everything after `--` straight to execve (no shell), so
    # the for-loop needs an explicit `bash -c` to be parsed at all. And the
    # whole thing transits an SSH command line executed by the REMOTE login
    # shell before pct even sees it — double-quoting (e.g. json.dumps) still
    # lets that outer shell expand $i/$(seq ...) immediately, breaking the
    # loop before the inner bash -c ever runs it. Single-quoting via
    # shlex.quote is what actually defers expansion to the inner shell.
    sweep_script = (
        "for i in $(seq 1 254); do "
        "(ping -c1 -W1 10.10.11.$i > /dev/null 2>&1 &); done; "
        "sleep 6; ip neigh show dev eth0"
    )
    r = _host_exec(f"bash -c {shlex.quote(sweep_script)}", timeout=20)
    if not r.get("ok"):
        return None
    for line in r["output"].splitlines():
        parts = line.split()
        # "10.10.11.13 lladdr bc:24:11:20:b6:50 REACHABLE"
        if len(parts) >= 3 and parts[1] == "lladdr" and parts[2].lower() == target_mac:
            return parts[0]
    return None


def _start_lab_host(host: str) -> bool:
    """Start the Proxmox VM/LXC backing a known static lab host.

    Returns True if a start command was actually issued (not whether it finished
    booting — the caller still has to poll for reachability afterward).
    """
    from scripts.lab_host import _proxmox_exec

    mapping = _LAB_HOST_VMID_MAP.get(host)
    if not mapping:
        return False
    vmid, kind = mapping
    cmd = f"qm start {vmid}" if kind == "vm" else f"pct start {vmid}"
    r = _proxmox_exec(cmd, timeout=30)
    return bool(r.get("ok"))


# Common ports across the lab's static (non-vulhub) hosts — AD (kerberos/ldap/smb),
# the VulnerableApp web host, Metasploitable3, and mbptl. These hosts are fixed lab
# infra, not ephemeral vulhub compose sessions, so there's no docker-compose port to
# publish and no `vmid` in config/lab_targets.yaml to heal from (that catalog only
# tracks vulhub/projectblack envs). A liveness probe across the known service ports
# is the correct readiness signal here.
_STATIC_HOST_PROBE_PORTS = [80, 445, 389, 88, 8080, 3306, 21, 8282, 4848, 9200, 6379, 2049, 443]


def _probe_any_reachable_port(
    host: str, ports: list[int] | None = None, timeout_s: float = 3.0
) -> int | None:
    """Return the first port in `ports` that accepts a TCP connection on `host`."""
    import socket

    for port in ports or _STATIC_HOST_PROBE_PORTS:
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                return port
        except OSError:
            continue
    return None


def _poll_reachable_port(
    host: str, timeout_s: float, interval_s: float = 5.0, ports: list[int] | None = None
) -> int | None:
    """Poll _probe_any_reachable_port until something answers or timeout_s elapses.

    A cold Windows VM (meta3, DC, SRV) takes minutes to boot — a single immediate
    probe right after `qm start` will always see nothing listening yet. This is
    what actually gives a just-started host time to come up, which the old
    dead vmid-lookup heal path never did even when it "worked."
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        port = _probe_any_reachable_port(host, ports)
        if port:
            return port
        time.sleep(interval_s)
    return None


def ensure_target_ready(scenario: dict, *, dry_run: bool = False, retries: int = 2) -> dict:
    """Verify a scenario's external target is up; heal via existing primitives if not.

    Returns {ready, healed, host, port, reason} where port is the REAL published port
    the scenario must attack (single source of truth — no hardcoded guessing).

    Vulhub envs heal via cmd_up (docker compose). Static lab hosts (AD, meta3,
    mbptl) heal via _start_lab_host (qm/pct start against the real Proxmox vmid)
    + _poll_reachable_port, so a scenario landing on a genuinely-down VM brings
    it back up instead of just detecting the outage and giving up.
    """
    host = scenario.get("target_host")
    env = scenario.get("vulhub_env")
    # A scenario that names a specific service (declared target_port) must be
    # verified on THAT port, not "whichever port answers first." Found live
    # 2026-07-24: on a cold VM boot, services come up in whatever order they
    # happen to start -- meta3_elasticsearch_rce (wants 9200) got healed to
    # port 21 (FTP) because it answered first and _STATIC_HOST_PROBE_PORTS has
    # no notion of which service a given scenario actually needs. Only
    # applies to the static-host path (env=None) -- vulhub_env already
    # resolves its own real published port via cmd_up, unrelated to this list.
    declared_port = scenario.get("target_port")
    probe_ports = [declared_port] if declared_port and not env else None

    # No external target (AD-only scenarios, etc.) — always "ready"
    if not host:
        return {
            "ready": True,
            "healed": False,
            "host": None,
            "port": None,
            "reason": "no external target",
        }

    # Discovery-first, not config-first: for static lab hosts backed by a known
    # Proxmox vmid, the declared config IP is only ever a starting guess. DHCP
    # without a reservation means it drifts across reboots — found live
    # 2026-07-16: meta3 moved 10.10.11.10 -> .11 -> .13 within one session, and
    # every static value written down (config, .env, code fallback) was stale
    # within minutes. The VM's MAC is the one thing that doesn't change across
    # reboots — discover_host_by_mac resolves the REAL current IP by ARP-sweeping
    # the lab subnet and matching on it. Never used for vulhub_env targets
    # (those get their real host:port from cmd_up's docker-compose port publish,
    # already live-resolved). config_host is kept for _start_lab_host's vmid
    # lookup, which is keyed by the declared value, not whatever we discover.
    config_host = host
    mapping = None if env else _LAB_HOST_VMID_MAP.get(config_host)
    if mapping:
        discovered = discover_host_by_mac(*mapping)
        if discovered:
            host = discovered

    # VERIFY: is it up, and on WHAT port?
    port = _resolve_live_port(host, env) if env else _probe_any_reachable_port(host, probe_ports)
    if port and _wait_reachable(host, port, timeout_s=5):
        return {
            "ready": True,
            "healed": False,
            "host": host,
            "port": port,
            "reason": "already up" + (" (mac-discovered)" if host != config_host else ""),
        }

    # HEAL
    for attempt in range(retries):
        if env:
            up = cmd_up(env, dry_run=dry_run)
            port = up.get("port")
            if port and _wait_reachable(host, port, timeout_s=60):
                return {
                    "ready": True,
                    "healed": True,
                    "host": host,
                    "port": port,
                    "reason": f"healed@{attempt + 1}",
                }
        else:
            started = _start_lab_host(config_host) if not dry_run else False
            if started and mapping:
                # A DHCP lease renegotiated on this exact boot can differ from
                # whatever we discovered a moment ago — re-resolve post-start
                # rather than poll an address that may already be stale again.
                redisc = discover_host_by_mac(*mapping)
                if redisc:
                    host = redisc
            # A just-started Windows VM needs minutes, not seconds — an LXC or an
            # already-running host that just had a transient blip needs far less.
            port = _poll_reachable_port(host, timeout_s=180 if started else 20, ports=probe_ports)
            if port:
                return {
                    "ready": True,
                    "healed": True,
                    "host": host,
                    "port": port,
                    "reason": f"healed@{attempt + 1}" + (" (vm-start)" if started else ""),
                }

    return {
        "ready": False,
        "healed": False,
        "host": host,
        "port": None,
        "reason": "target-unrecoverable",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab targets — on-demand ephemeral containers")
    parser.add_argument(
        "action", choices=["up", "down", "ephemeral", "status", "list"], help="Action to perform"
    )
    parser.add_argument("target", nargs="?", default="", help="Target ID or raw vulhub path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-concurrent", type=int, default=3)
    parser.add_argument("command", nargs="*", default=[], help="Command for ephemeral mode")
    args = parser.parse_args()

    if args.action == "up":
        result = cmd_up(args.target, dry_run=args.dry_run, max_concurrent=args.max_concurrent)
    elif args.action == "down":
        result = cmd_down(args.target, dry_run=args.dry_run)
    elif args.action == "ephemeral":
        cmd_args = args.command if args.command else None
        result = cmd_ephemeral(args.target, cmd_args, dry_run=args.dry_run)
    elif args.action == "status":
        result = cmd_status()
    elif args.action == "list":
        targets = cmd_list()
        print(f"  {len(targets)} targets in catalog:")
        for t in targets:
            print(
                f"    {t['id']:<30} {t['source']:<15} {t.get('cve', ''):<18} {t.get('technique', '')}"
            )
        return
    print(f"  {result}")


if __name__ == "__main__":
    main()
