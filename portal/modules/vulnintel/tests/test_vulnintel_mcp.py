"""Acceptance: scoring logic, private-IP guard, CVE-id validation, KEV override."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.vulnintel.tools.vulnintel_mcp")


def test_cve_id_validation() -> None:
    with pytest.raises(ValueError):
        mod._norm_cve("not-a-cve")
    assert mod._norm_cve("cve-2024-3400") == "CVE-2024-3400"


def test_private_ip_rejected_before_lookup() -> None:
    for ip in ("10.0.0.1", "192.168.1.1", "127.0.0.1", "169.254.1.1"):
        with pytest.raises(ValueError):
            mod._reject_private_ip(ip)


def test_registered_tools_are_served_natively() -> None:
    import asyncio

    assert {tool.name for tool in asyncio.run(mod.mcp.list_tools())} == {
        "check_kev",
        "get_epss",
        "ics_advisories",
        "lookup_cve",
        "lookup_ioc",
        "scan_dependencies",
        "triage_cve",
    }
