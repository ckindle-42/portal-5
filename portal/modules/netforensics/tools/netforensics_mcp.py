"""Portal 5 — Network Forensics MCP.

Passive PCAP analysis via tshark (+ optional Zeek), plus a gated, lab-scoped
structured recon surface. Analysis is file-based and read-only; active recon is
refused outside the authorized lab CIDR and is off by default.

Port: 8941 (NETFORENSICS_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import shutil
import subprocess
from pathlib import Path

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)
_port = int(os.environ.get("NETFORENSICS_MCP_PORT") or os.environ.get("MCP_PORT", "8941"))
mcp = MCPServer(
    "netforensics",
    instructions="Passive PCAP analysis via tshark (protocol hierarchy, conversations, "
    "field extraction) with an ICS hand-off to the icsot module, plus a gated, "
    "lab-CIDR-restricted structured nmap recon surface that is off by default.",
)

_ROOT = Path(os.environ.get("NETFORENSICS_ROOT", os.path.expanduser("~/AI_Output"))).resolve()
_RECON_ENABLED = os.environ.get("NETFORENSICS_RECON_ENABLED", "0") == "1"
_ICS_PORTS = {502, 20000, 102, 44818, 2222, 47808, 1911, 9600}
_TIMEOUT = int(os.environ.get("NETFORENSICS_TSHARK_TIMEOUT", "120"))


def _lab_cidr() -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    # single source of truth for the lab invariant — the security module's guard
    override = os.environ.get("PORTAL_LAB_CIDR")
    if override:
        return ipaddress.ip_network(override)
    from portal.modules.security.core.perception import LAB_CIDR

    return LAB_CIDR


def _resolve(path: str) -> Path:
    p = Path(path).resolve() if os.path.isabs(path) else (_ROOT / path).resolve()
    if p != _ROOT and _ROOT not in p.parents:
        raise ValueError(f"path escapes root {_ROOT}: {path}")
    if not p.exists():
        raise FileNotFoundError(path)
    return p


def _tshark() -> str:
    exe = shutil.which("tshark")
    if not exe:
        raise RuntimeError("tshark not installed (./launch.sh install-netforensics)")
    return exe


def _target_in_lab(target: str, cidr) -> str | None:
    """Return a refusal reason if any token in `target` is outside `cidr`, else None."""
    for host in target.replace(",", " ").split():
        try:
            addr = ipaddress.ip_address(host)
            if addr not in cidr:
                return f"{host} outside authorized lab {cidr}"
        except ValueError:
            try:
                net = ipaddress.ip_network(host, strict=False)
            except ValueError:
                return f"unparseable target: {host!r}"
            if not net.subnet_of(cidr):
                return f"{host} outside authorized lab {cidr}"
    return None


@mcp.tool()
def protocol_hierarchy(pcap_path: str) -> dict:
    """tshark protocol hierarchy (-qz io,phs) for a PCAP; flags ICS ports for icsot."""
    try:
        p = _resolve(pcap_path)
        phs = subprocess.run(
            [_tshark(), "-r", str(p), "-qz", "io,phs"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        ports = subprocess.run(
            [_tshark(), "-r", str(p), "-T", "fields", "-e", "tcp.dstport", "-e", "udp.dstport"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        seen = {
            int(tok) for line in ports.stdout.splitlines() for tok in line.split() if tok.isdigit()
        }
        ics = sorted(seen & _ICS_PORTS)
        return {
            "pcap": str(p),
            "hierarchy": phs.stdout,
            "ics_ports_present": ics,
            "hint": (
                "ICS ports present — hand this PCAP to icsot.dissect_pcap for protocol-level analysis"
                if ics
                else ""
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def extract_fields(pcap_path: str, display_filter: str, fields: list) -> dict:
    """Extract chosen tshark fields under a display filter (e.g. dns.qry.name, http.host)."""
    try:
        p = _resolve(pcap_path)
        cmd = [_tshark(), "-r", str(p), "-Y", display_filter, "-T", "fields"]
        for f in fields:
            cmd += ["-e", str(f)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
        rows = [line.split("\t") for line in r.stdout.splitlines() if line.strip()][:1000]
        return {
            "pcap": str(p),
            "filter": display_filter,
            "fields": fields,
            "row_count": len(rows),
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def conversations(pcap_path: str, kind: str = "tcp") -> dict:
    """tshark conversation statistics (-qz conv,<kind>) — top talkers."""
    try:
        if kind not in ("tcp", "udp", "ip", "eth"):
            return {"error": f"unsupported kind {kind!r}; use tcp|udp|ip|eth"}
        p = _resolve(pcap_path)
        r = subprocess.run(
            [_tshark(), "-r", str(p), "-qz", f"conv,{kind}"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        return {"pcap": str(p), "kind": kind, "conversations": r.stdout}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@mcp.tool()
def recon_scan(target: str, ports: str = "top-1000") -> dict:
    """[GATED] Structured nmap scan. Refused unless recon is enabled AND target is in the lab CIDR."""
    try:
        if not _RECON_ENABLED:
            return {
                "refused": True,
                "reason": "active recon disabled (set NETFORENSICS_RECON_ENABLED=1 to enable)",
            }
        cidr = _lab_cidr()
        # lab-scope invariant — runs first, always
        reason = _target_in_lab(target, cidr)
        if reason:
            return {"refused": True, "reason": reason}
        exe = shutil.which("nmap")
        if not exe:
            return {"error": "nmap not installed"}
        args = [exe, "-oX", "-", "-Pn"]
        args += ["--top-ports", "1000"] if ports == "top-1000" else ["-p", ports]
        args += target.split()
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
        return {
            "target": target,
            "xml": r.stdout[:20000],
            "note": "nmap XML; parse client-side",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_netforensics_mcp")

_DISPATCH = {
    "protocol_hierarchy": protocol_hierarchy,
    "extract_fields": extract_fields,
    "conversations": conversations,
    "recon_scan": recon_scan,
}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "netforensics-mcp", "port": _port})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(request):
    return JSONResponse(
        {
            "port": _port,
            "tshark": bool(shutil.which("tshark")),
            "recon_enabled": _RECON_ENABLED,
            "lab_cidr": str(_lab_cidr()),
        }
    )


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
    name = request.path_params.get("tool_name", "")
    fn = _DISPATCH.get(name)
    if fn is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = body.get("arguments", body) if isinstance(body, dict) else {}
    try:
        return JSONResponse(fn(**args))
    except TypeError as e:
        return JSONResponse({"error": f"bad params: {e}"}, status_code=400)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
