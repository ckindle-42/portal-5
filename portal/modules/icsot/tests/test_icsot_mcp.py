"""Acceptance: protocol table, Modbus dissection + TTP tagging on a synthetic PCAP."""

import importlib

mod = importlib.import_module("portal.modules.icsot.tools.icsot_mcp")


def test_protocol_table() -> None:
    out = mod.list_ics_protocols()
    ports = {p["port"] for p in out["protocols"]}
    assert 502 in ports and 20000 in ports and 102 in ports
    tiers = {p["protocol"]: p["tier"] for p in out["protocols"]}
    assert tiers["Modbus/TCP"] == "full"
    assert tiers["DNP3"] == "identify"


def test_registered_tools_are_served_natively() -> None:
    import asyncio

    assert {tool.name for tool in asyncio.run(mod.mcp.list_tools())} == {
        "asset_inventory",
        "correlate_advisories",
        "dissect_pcap",
        "list_ics_protocols",
    }


def test_dissect_missing_pcap_is_graceful() -> None:
    out = mod.dissect_pcap("/nonexistent/path.pcap")
    assert "error" in out


def test_mitre_mcp_resolves_ics_technique() -> None:
    m = importlib.import_module("portal.modules.security.tools.mitre_mcp")
    m._ensure_loaded()
    res = m.mitre_technique_lookup("T0836")
    assert res.get("matrix") == "ics"
    assert res["name"] == "Modify Parameter"
    ent = m.mitre_technique_lookup("T1190")
    assert ent.get("matrix") == "enterprise"
