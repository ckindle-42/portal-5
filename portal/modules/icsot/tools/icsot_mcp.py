"""Portal 5 — ICS/OT Protocol & Asset Intelligence MCP.

Passive, read-only. Dissects provided ICS traffic (PCAP or hex payloads),
inventories ICS assets from captured conversations, and correlates observed
behavior to MITRE ATT&CK for ICS. Does NOT transmit ICS frames or poll PLCs.

Port: 8936 (ICSOT_MCP_PORT or MCP_PORT env override).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.platform.data_loader import load_data

logger = logging.getLogger(__name__)

_port = int(os.environ.get("ICSOT_MCP_PORT") or os.environ.get("MCP_PORT", "8936"))
mcp = MCPServer(
    "icsot",
    instructions="Passive read-only ICS/OT protocol dissection (Modbus via scapy; "
    "port/header identification for DNP3/S7comm/EtherNet-IP/BACnet), ICS asset inventory "
    "from captured traffic, and MITRE ATT&CK-for-ICS correlation. Never transmits ICS frames.",
)

# Well-known ICS ports -> (protocol, dissection tier). "full" = structured
# dissector; "identify" = port/header identification with extension hook.
_ICS_PORTS = {
    502: ("Modbus/TCP", "full"),
    20000: ("DNP3", "identify"),
    102: ("S7comm (ISO-TSAP)", "identify"),
    44818: ("EtherNet/IP (explicit)", "identify"),
    2222: ("EtherNet/IP (implicit/CIP I/O)", "identify"),
    47808: ("BACnet/IP", "identify"),
    1911: ("Niagara Fox", "identify"),
    9600: ("OMRON FINS", "identify"),
}

# Behavior -> ATT&CK-for-ICS technique bridge the dissector emits so a single
# observation is already technique-tagged. IDs are the current (non-revoked)
# ATT&CK-for-ICS set; the full matrix is resolvable through mitre_mcp.
_ICS_BEHAVIOR_TTP = {
    "modbus_write_coil": ("T1692.001", "Command Message"),
    "modbus_write_register": ("T0836", "Modify Parameter"),
    "modbus_read": ("T0801", "Monitor Process State"),
    "dnp3_traffic": ("T0885", "Commonly Used Port"),
    "s7comm_traffic": ("T0869", "Standard Application Layer Protocol"),
    "point_and_click_scan": ("T0842", "Network Sniffing"),
}


def _scapy():
    import scapy.all as s
    from scapy.contrib import modbus

    return s, modbus


def _modbus_ttp_for_fc(fc: int) -> tuple[str, str] | None:
    """Map a Modbus function code to its ATT&CK-for-ICS behavior tag."""
    if fc in (5, 15):
        return _ICS_BEHAVIOR_TTP["modbus_write_coil"]
    if fc in (6, 16):
        return _ICS_BEHAVIOR_TTP["modbus_write_register"]
    if fc in (1, 2, 3, 4):
        return _ICS_BEHAVIOR_TTP["modbus_read"]
    return None


@mcp.tool()
def list_ics_protocols() -> dict:
    """Enumerate the ICS protocols this server recognizes and the dissection tier for each."""
    return {
        "protocols": [
            {"port": p, "protocol": n, "tier": t} for p, (n, t) in sorted(_ICS_PORTS.items())
        ]
    }


@mcp.tool()
def dissect_pcap(pcap_path: str, max_packets: int = 5000) -> dict:
    """Passively dissect an ICS PCAP.

    Returns per-protocol packet counts, a Modbus function-code breakdown,
    top conversations, and behavior -> ATT&CK-for-ICS technique tags.

    Args:
        pcap_path: path to a .pcap/.pcapng file on the host.
        max_packets: cap on packets to read.
    """
    try:
        s, modbus = _scapy()
    except Exception as e:  # noqa: BLE001
        return {"error": f"scapy unavailable ({e}); install the icsot module dependencies"}
    try:
        pkts = s.rdpcap(pcap_path)
    except FileNotFoundError:
        return {"error": f"pcap not found: {pcap_path}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"scapy read failed: {e}"}

    proto_counts: dict = defaultdict(int)
    modbus_funcs: dict = defaultdict(int)
    endpoints: dict = defaultdict(int)
    ttps: set = set()
    n = 0
    for pkt in pkts:
        if n >= max_packets:
            break
        n += 1
        if not pkt.haslayer(s.TCP) and not pkt.haslayer(s.UDP):
            continue
        l4 = pkt[s.TCP] if pkt.haslayer(s.TCP) else pkt[s.UDP]
        dport, sport = int(l4.dport), int(l4.sport)
        hit = _ICS_PORTS.get(dport) or _ICS_PORTS.get(sport)
        if not hit:
            continue
        name, _tier = hit
        proto_counts[name] += 1
        if pkt.haslayer(s.IP):
            endpoints[f"{pkt[s.IP].src}->{pkt[s.IP].dst}"] += 1
        if name.startswith("Modbus") and pkt.haslayer(modbus.ModbusADURequest):
            fc = int(getattr(pkt[modbus.ModbusADURequest], "funcCode", 0))
            modbus_funcs[fc] += 1
            ttp = _modbus_ttp_for_fc(fc)
            if ttp:
                ttps.add(ttp)
        elif name == "DNP3":
            ttps.add(_ICS_BEHAVIOR_TTP["dnp3_traffic"])
        elif name.startswith("S7"):
            ttps.add(_ICS_BEHAVIOR_TTP["s7comm_traffic"])
    return {
        "pcap": pcap_path,
        "packets_read": n,
        "protocols": dict(proto_counts),
        "modbus_function_codes": {str(k): v for k, v in modbus_funcs.items()},
        "top_conversations": sorted(endpoints.items(), key=lambda kv: -kv[1])[:15],
        "attack_ics_ttps": [{"id": t[0], "name": t[1]} for t in sorted(ttps)],
        "note": (
            "Passive dissection only. Non-'full'-tier protocols are identified by port; "
            "structured payload parsing for DNP3/S7comm/EtherNet-IP is an extension hook."
        ),
    }


@mcp.tool()
def asset_inventory(pcap_path: str, max_packets: int = 5000) -> dict:
    """Derive an ICS asset inventory (hosts, roles, protocols seen) from a PCAP.

    Heuristic role inference: a host that answers on an ICS port is a likely
    device/PLC endpoint; a host that initiates reads/writes is a likely HMI/EWS.
    """
    try:
        s, _ = _scapy()
    except Exception as e:  # noqa: BLE001
        return {"error": f"scapy unavailable ({e}); install the icsot module dependencies"}
    try:
        pkts = s.rdpcap(pcap_path)
    except FileNotFoundError:
        return {"error": f"pcap not found: {pcap_path}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"scapy read failed: {e}"}
    assets: dict = defaultdict(lambda: {"protocols": set(), "role_hints": set()})
    n = 0
    for pkt in pkts:
        if n >= max_packets:
            break
        n += 1
        if not pkt.haslayer(s.IP) or not (pkt.haslayer(s.TCP) or pkt.haslayer(s.UDP)):
            continue
        l4 = pkt[s.TCP] if pkt.haslayer(s.TCP) else pkt[s.UDP]
        for host, port, initiating in (
            (pkt[s.IP].dst, int(l4.dport), True),
            (pkt[s.IP].src, int(l4.sport), False),
        ):
            hit = _ICS_PORTS.get(port)
            if not hit:
                continue
            assets[host]["protocols"].add(hit[0])
            assets[host]["role_hints"].add(
                "HMI/EWS (initiator)" if initiating else "device/PLC (responder)"
            )
    return {
        "pcap": pcap_path,
        "asset_count": len(assets),
        "assets": [
            {
                "host": h,
                "protocols": sorted(v["protocols"]),
                "role_hints": sorted(v["role_hints"]),
            }
            for h, v in sorted(assets.items())
        ],
    }


@mcp.tool()
def correlate_advisories(vendor: str, days: int = 90) -> dict:
    """Cross-reference an observed ICS vendor to recent CISA ICS advisories (via vulnintel)."""
    try:
        from portal.modules.vulnintel.tools.vulnintel_mcp import ics_advisories  # T1 dependency

        return ics_advisories(vendor=vendor, days=days)
    except Exception as e:  # noqa: BLE001
        return {"error": f"vulnintel unavailable ({e}); ensure T1 landed and running"}


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_icsot_mcp")

_DISPATCH = {
    "list_ics_protocols": list_ics_protocols,
    "dissect_pcap": dissect_pcap,
    "asset_inventory": asset_inventory,
    "correlate_advisories": correlate_advisories,
}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "icsot-mcp", "port": _port})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(request):
    ok = True
    try:
        _scapy()
    except Exception:  # noqa: BLE001
        ok = False
    return JSONResponse({"port": _port, "scapy_available": ok})


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
