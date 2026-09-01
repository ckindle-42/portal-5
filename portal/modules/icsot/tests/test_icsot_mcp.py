"""Acceptance: protocol table, Modbus dissection + TTP tagging on a synthetic PCAP."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.icsot.tools.icsot_mcp")


def test_protocol_table():
    out = mod.list_ics_protocols()
    ports = {p["port"] for p in out["protocols"]}
    assert 502 in ports and 20000 in ports and 102 in ports
    tiers = {p["protocol"]: p["tier"] for p in out["protocols"]}
    assert tiers["Modbus/TCP"] == "full"
    assert tiers["DNP3"] == "identify"


def test_tools_manifest_matches_dispatch():
    manifest_names = {t["function"]["name"] for t in mod.TOOLS_MANIFEST}
    assert manifest_names == set(mod._DISPATCH)


def test_modbus_dissection_tags_write(tmp_path):
    pytest.importorskip("scapy.all")
    from scapy.all import IP, TCP, wrpcap
    from scapy.contrib import modbus

    # a Modbus write-single-coil (fc=5) request 10.10.11.9 -> 10.10.11.21:502
    pkt = (
        IP(src="10.10.11.9", dst="10.10.11.21")
        / TCP(sport=50000, dport=502)
        / modbus.ModbusADURequest()
        / modbus.ModbusPDU05WriteSingleCoilRequest()
    )
    p = tmp_path / "mb.pcap"
    wrpcap(str(p), [pkt])
    out = mod.dissect_pcap(str(p))
    assert any("Modbus" in k for k in out["protocols"])
    assert any(t["id"] == "T1692.001" for t in out["attack_ics_ttps"])  # Command Message


def test_dissect_missing_pcap_is_graceful():
    out = mod.dissect_pcap("/nonexistent/path.pcap")
    assert "error" in out


def test_mitre_mcp_resolves_ics_technique():
    m = importlib.import_module("portal.modules.security.tools.mitre_mcp")
    m._ensure_loaded()
    res = m.mitre_technique_lookup("T0836")
    assert res.get("matrix") == "ics"
    assert res["name"] == "Modify Parameter"
    ent = m.mitre_technique_lookup("T1190")
    assert ent.get("matrix") == "enterprise"
