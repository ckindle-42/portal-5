#!/usr/bin/env python3
"""Run a Caldera adversary operation against the lab and feed its telemetry to
Splunk through the same collect -> ship -> wait path the bench already uses.

This is the *live* lane. The corpora in ``scripts/corpus_ingest.py`` and
``scripts/lab_bots_install.py`` are finite and pre-labeled — every event already
carries the answer. Caldera generates fresh, unlabeled activity on demand against
owned lab targets, which is the only lane that produces genuine novel-threat
signal for discovery / ``ANOMALOUS_UNCLASSIFIED`` work.

Unlike corpus events, these ship **with an episode_id** (the Caldera operation
id), so they are episode-scoped exactly like bench telemetry and are retrievable
via ``SplunkBackend.query_episode(<operation_id>)``. Provenance is
``evidence_origin='live:caldera:<profile>'``.

Usage::

    # list what is available, then run one profile against the 'red' agent group
    python3 scripts/caldera_emulate.py --list
    python3 scripts/caldera_emulate.py --adversary "Portal5 Linux Discovery" --group red

Environment: ``CALDERA_URL`` (default http://10.10.11.60:8888), ``CALDERA_API_KEY``
(default ADMIN123), plus the usual ``LAB_SPLUNK_*`` contract used by hec_ship.

Authorized-use note: this drives adversary emulation only against the operator's
own isolated lab range (``LAB_TARGET_NETWORK``). It refuses to target a host
outside that network.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.siem.collect import collect_target  # noqa: E402
from portal.modules.security.core.siem.hec_ship import ship_batch  # noqa: E402
from portal.modules.security.core.siem.index_wait import wait_indexed  # noqa: E402

CALDERA_URL = os.environ.get("CALDERA_URL", "http://10.10.11.60:8888").rstrip("/")
CALDERA_KEY = os.environ.get("CALDERA_API_KEY", "ADMIN123")
LAB_NETWORK = os.environ.get("LAB_TARGET_NETWORK", "10.10.11.0/24")

# Agent host -> (collect_target kind, Proxmox LXC id) for the lab's known targets.
# 'kind' selects which log surfaces collect_target scrapes; see siem/collect.py.
HOST_COLLECTORS: dict[str, tuple[str, str | None]] = {
    os.environ.get("LAB_TARGET_WEB", "10.10.11.50"): ("web", "112"),
    os.environ.get("LAB_MBPTL_HOST", "10.0.1.140"): ("linux", "300"),
    os.environ.get("LAB_TARGET_DC", "10.10.11.21"): ("windows", None),
    os.environ.get("LAB_TARGET_SRV", "10.10.11.33"): ("windows", None),
}


def api(path: str, method: str = "GET", body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed lab http endpoint
        f"{CALDERA_URL}/api/v2/{path.lstrip('/')}",
        data=data,
        method=method,
        headers={"KEY": CALDERA_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read().decode() or "null")


def in_lab(host: str) -> bool:
    """Refuse to emulate against anything outside the owned lab range."""
    try:
        return ipaddress.ip_address(host) in ipaddress.ip_network(LAB_NETWORK)
    except ValueError:
        return False


def resolve_agent_hosts(group: str) -> list[str]:
    """IPs of checked-in agents in ``group``, restricted to the lab network."""
    hosts: list[str] = []
    for agent in api("agents") or []:
        if group and agent.get("group") != group:
            continue
        for addr in agent.get("host_ip_addrs") or []:
            if in_lab(addr) and addr not in hosts:
                hosts.append(addr)
    return hosts


def wait_for_operation(op_id: str, timeout_s: int) -> dict:
    """Poll until Caldera reports the operation finished, or the budget expires."""
    deadline = time.time() + timeout_s
    operation: dict = {}
    while time.time() < deadline:
        operation = api(f"operations/{op_id}") or {}
        state = operation.get("state")
        chain = operation.get("chain") or []
        done = sum(1 for link in chain if link.get("status") == 0)
        print(f"  [{state}] {done}/{len(chain)} links complete", flush=True)
        if state in ("finished", "cleanup"):
            return operation
        time.sleep(10)
    print("  [warn] operation did not report finished within budget — collecting anyway")
    return operation


def collect_and_ship(hosts: list[str], since: float, op_id: str, profile: str) -> int:
    """collect_target -> ship_batch(episode_id) -> wait_indexed, per exercised host.

    Mirrors blue.py::collect_and_ship_scenario_telemetry's contract deliberately:
    same primitives, same episode scoping — the difference is only provenance,
    so live emulation data is consumable by exactly the same blue/purple paths.
    """
    shipped_total = 0
    for host in hosts:
        kind, lxc = HOST_COLLECTORS.get(host, ("linux", None))
        try:
            telemetry = collect_target(host, kind, since_epoch=since, lxc_id=lxc)
        except Exception as exc:
            print(f"  [collect-fail] {host} ({kind}): {exc}")
            continue
        shipped_host = 0
        for sourcetype, lines in telemetry.items():
            if not lines:
                continue
            # Plain strings, never a {"raw": ...} envelope — a JSON wrapper
            # defeats Splunk's key=value extraction and the SPL library then
            # matches nothing (see siem/capture_store.py::replay_capture).
            result = ship_batch(
                list(lines),
                sourcetype=sourcetype,
                host=host,
                event_time=since,
                evidence_origin=f"live:caldera:{profile}",
                episode_id=op_id,
            )
            if result.get("ok"):
                shipped_host += len(lines)
            else:
                print(f"  [ship-fail] {host} {sourcetype}: {result}")
        print(f"  {host} ({kind}): shipped {shipped_host} events")
        shipped_total += shipped_host
        if shipped_host:
            indexed = wait_indexed(host=host, since_epoch=since, expect_min=1, episode_id=op_id)
            print(f"  {host}: indexed_confirmed={indexed}")
    return shipped_total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adversary", help="adversary profile name or id")
    ap.add_argument("--group", default="red", help="Caldera agent group (default: red)")
    ap.add_argument("--list", action="store_true", help="list adversaries and agents, then exit")
    ap.add_argument("--timeout", type=int, default=600, help="operation wait budget, seconds")
    args = ap.parse_args()

    try:
        health = api("health")
    except (urllib.error.URLError, OSError) as exc:
        print(f"[FAIL] Caldera unreachable at {CALDERA_URL}: {exc}")
        return 2
    print(f"Caldera {health.get('version')} at {CALDERA_URL}")

    if args.list or not args.adversary:
        print("\nadversaries:")
        for a in api("adversaries") or []:
            print(f"  {a['adversary_id']}  {a['name']}")
        print("\nagents:")
        for a in api("agents") or []:
            print(f"  {a['paw']}  {a.get('host')}  {a.get('platform')}  group={a.get('group')}")
        return 0

    adversaries = api("adversaries") or []
    match = next(
        (a for a in adversaries if args.adversary in (a["name"], a["adversary_id"])),
        None,
    )
    if not match:
        print(f"[FAIL] no adversary named/id '{args.adversary}' — try --list")
        return 2

    hosts = resolve_agent_hosts(args.group)
    if not hosts:
        print(f"[FAIL] no checked-in agents in group '{args.group}' inside {LAB_NETWORK}")
        return 2
    print(f"targets in {LAB_NETWORK}: {', '.join(hosts)}")

    since = time.time()
    operation = api(
        "operations",
        method="POST",
        body={
            "name": f"p5-{match['name'].replace(' ', '-').lower()}-{int(since)}",
            "adversary": {"adversary_id": match["adversary_id"]},
            "group": args.group,
            "auto_close": True,
            "planner": {"id": "atomic"},
        },
    )
    op_id = operation["id"]
    print(f"operation {op_id} started ({match['name']})")

    wait_for_operation(op_id, args.timeout)
    profile = match["name"].replace(" ", "_").lower()
    shipped = collect_and_ship(hosts, since, op_id, profile)

    print(
        f"\nshipped {shipped} events as evidence_origin=live:caldera:{profile}, episode_id={op_id}"
    )
    print("verify:")
    print(
        f'  index=$LAB_SPLUNK_INDEX evidence_origin="live:caldera:*" episode_id="{op_id}" '
        "| stats count by sourcetype, host"
    )
    return 0 if shipped else 1


if __name__ == "__main__":
    sys.exit(main())
