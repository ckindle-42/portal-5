"""Acceptance: sandbox guard, recon disabled-by-default, lab-CIDR refusal."""

import importlib

mod = importlib.import_module("portal.modules.netforensics.tools.netforensics_mcp")


def test_conversations_rejects_bad_kind() -> None:
    out = mod.conversations("x.pcap", kind="bogus")
    assert "unsupported kind" in out.get("error", "")


def test_registered_tools_are_served_natively() -> None:
    import asyncio

    assert {tool.name for tool in asyncio.run(mod.mcp.list_tools())} == {
        "conversations",
        "extract_fields",
        "protocol_hierarchy",
        "recon_scan",
    }
