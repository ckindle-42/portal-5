"""LabPerception — bounded live-state enumerator (DESIGN_EMERGENT_LAB_AGENT_V2 Δ1).

Populates observations from the *live* lab surface (services up, reachability,
deltas since last turn) instead of pre-declared seeds. The single hard rule
(invariant I1): every target is inside the lab CIDR or it is rejected in code.
The actual probing is injected (bound to the Proxmox/lab MCP at wiring time) so
the guard and the delta shape stay unit-testable without the lab up.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass, field

LAB_CIDR = ipaddress.ip_network("10.10.11.0/24")


class OutOfScopeError(Exception):
    """Raised when a target outside LAB_CIDR is passed to perception/execution."""


def assert_in_lab(target_ip: str) -> None:
    """Hard scope guard. Non-lab target => OutOfScopeError (never a soft skip)."""
    try:
        addr = ipaddress.ip_address(target_ip)
    except ValueError as exc:
        raise OutOfScopeError(f"unparseable target: {target_ip!r}") from exc
    if addr not in LAB_CIDR:
        raise OutOfScopeError(f"target {target_ip} outside lab scope {LAB_CIDR}")


def in_lab(target_ip: str) -> bool:
    try:
        assert_in_lab(target_ip)
        return True
    except OutOfScopeError:
        return False


@dataclass
class PerceptionDelta:
    """Observation delta folded into the loop's obs each turn. Ground truth only."""

    services: list[dict] = field(default_factory=list)  # [{host, port, service, up}]
    reachable: list[dict] = field(default_factory=list)  # [{from_host, to_host}]
    changed: list[str] = field(default_factory=list)  # host ids changed since last turn
    source: str = "live_perception"  # provenance; never "prior"

    def to_observation(self) -> dict:
        return {
            "services": self.services,
            "reachable": self.reachable,
            "changed": self.changed,
            "_source": self.source,
        }


class LabPerception:
    """Enumerates live lab state via an injected prober, scope-guarded to the lab."""

    def __init__(self, prober: Callable[[list[str]], dict]):
        # prober(hosts) -> raw dict; bound to lab MCP at wiring time.
        self._prober = prober
        self._last: dict[str, dict] = {}

    def enumerate(self, hosts: list[str]) -> PerceptionDelta:
        for h in hosts:
            assert_in_lab(h)  # I1: reject before any probe leaves the box
        raw = self._prober(hosts)
        services = raw.get("services", [])
        reachable = raw.get("reachable", [])
        changed = [h for h in hosts if raw.get("state", {}).get(h) != self._last.get(h)]
        self._last = dict(raw.get("state", {}))
        return PerceptionDelta(services=services, reachable=reachable, changed=changed)
