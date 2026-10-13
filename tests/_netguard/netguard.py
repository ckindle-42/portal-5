"""Unit-test offline boundary (cause C5); see docs/WFE_ROOT_CAUSES_20261013.md,
"Offline boundary"."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HITS: list[tuple[str, int]] = []
_installed = False


def service_ports() -> frozenset[int]:
    ports = {9099, 11434}
    for name in ("portal.yaml", "backends.yaml"):
        try:
            text = (REPO / "config" / name).read_text()
        except OSError:
            continue
        ports.update(int(p) for p in re.findall(r"\bport:\s*(\d+)", text))
        ports.update(
            int(p)
            for p in re.findall(r"(?:localhost|127\.0\.0\.1|host\.docker\.internal):(\d+)", text)
        )
    return frozenset(ports)


SERVICE_PORTS = service_ports()


def _is_loopback(host: str) -> bool:
    if host in ("localhost", "0.0.0.0", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False  # any other hostname is treated as remote


def refused(addr) -> bool:
    if not (isinstance(addr, tuple) and len(addr) >= 2):
        return False
    host, port = str(addr[0]), int(addr[1])
    return not _is_loopback(host) or port in SERVICE_PORTS


def _record(addr) -> None:
    hit = (str(addr[0]), int(addr[1]))
    HITS.append(hit)
    log = os.environ.get("PORTAL_NETGUARD_LOG")
    if log:
        try:
            with open(log, "a") as fh:
                fh.write(f"{hit[0]} {hit[1]} pid={os.getpid()}\n")
        except OSError:
            pass


def install() -> None:
    global _installed
    if _installed:
        return
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def connect(self, addr):
        if refused(addr):
            _record(addr)
            raise ConnectionRefusedError(f"unit tests may not reach {addr[0]}:{addr[1]}")
        return real_connect(self, addr)

    def connect_ex(self, addr):
        if refused(addr):
            _record(addr)
            return 111
        return real_connect_ex(self, addr)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    _installed = True
