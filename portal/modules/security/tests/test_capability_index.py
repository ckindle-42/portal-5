"""Tests for the capability index (TASK_SEC_CAPABILITY_INDEX_V1).

The hard invariant: every capability's tools/oracle references something
real. An orphan reference (a tool not in the catalog, an oracle not in
ORACLES) is a build-time bug, not a runtime surprise — this is enforced
both inside build_index() itself and independently here.
"""

from __future__ import annotations

import subprocess
import sys

from portal.modules.security.core.capability.index import (
    Capability,
    build_index,
    query,
)
from portal.modules.security.core.capability.render import (
    render_capabilities,
    render_tool_arsenal,
)
from portal.modules.security.core.capability.tool_inventory import (
    load_tool_catalog,
    tools_for_phase,
    tools_for_service,
    verify_tools_present,
)
from portal.modules.security.core.oracles import ORACLES


class TestToolInventory:
    def test_catalog_loads(self):
        tools = load_tool_catalog()
        assert len(tools) > 0
        for t in tools:
            assert "name" in t
            assert "phase" in t

    def test_tools_for_service(self):
        smb_tools = tools_for_service("smb")
        assert any(t["name"] == "nxc" for t in smb_tools)

    def test_tools_for_phase(self):
        recon_tools = tools_for_phase("recon")
        assert all(t["phase"] == "recon" for t in recon_tools)

    def test_verify_tools_present_dry_run_is_all_unknown(self):
        presence = verify_tools_present(dry_run=True)
        assert presence
        assert all(v is None for v in presence.values())


class TestBuildIndex:
    def test_returns_capabilities(self):
        caps = build_index()
        assert len(caps) > 0
        assert all(isinstance(c, Capability) for c in caps)

    def test_sources_present(self):
        caps = build_index()
        sources = {c.source for c in caps}
        assert "service_probe" in sources
        assert "challenge_class" in sources
        assert "lab_target" in sources

    def test_no_orphan_tool_references(self):
        """Every capability's tools must resolve to a real catalog entry."""
        catalog_names = {t["name"] for t in load_tool_catalog()}
        caps = build_index()
        for cap in caps:
            for tool in cap.tools:
                assert tool in catalog_names, f"{cap.id} references unknown tool {tool!r}"

    def test_no_orphan_oracle_references(self):
        """Every capability's oracle (when set) must resolve to a registered oracle."""
        caps = build_index()
        for cap in caps:
            if cap.oracle is not None:
                assert cap.oracle in ORACLES, f"{cap.id} references unknown oracle {cap.oracle!r}"

    def test_every_capability_has_a_source(self):
        caps = build_index()
        assert all(c.source and c.source != "unknown" for c in caps)

    def test_is_cached(self):
        assert build_index() is build_index()


class TestQuery:
    def test_phase_filter(self):
        results = query({}, phase="recon", limit=100)
        assert all(c.phase == "recon" for c in results)

    def test_domain_filter(self):
        results = query({}, domain="ad", limit=100)
        assert all(c.domain == "ad" for c in results)

    def test_applies_when_matches_observations(self):
        results = query({"open_ports": [445]}, limit=100)
        assert any(c.id == "smb_probe" for c in results)

    def test_applies_when_excludes_non_matching(self):
        results = query({"open_ports": [9999]}, phase="recon", limit=100)
        assert not any(c.id == "smb_probe" for c in results)

    def test_empty_applies_when_always_matches(self):
        # challenge_class-derived capabilities have applies_when={} — always applicable
        results = query({}, domain="ad", limit=100)
        assert any(c.source == "challenge_class" for c in results)

    def test_goal_filter_substring(self):
        results = query({}, goal="kerberos", limit=100)
        assert len(results) > 0
        assert all("kerberos" in c.id.lower() or "kerberos" in c.technique.lower() for c in results)

    def test_limit_respected(self):
        results = query({}, limit=3)
        assert len(results) <= 3

    def test_returns_capability_instances(self):
        results = query({}, limit=5)
        assert all(isinstance(c, Capability) for c in results)


class TestRender:
    def test_render_capabilities_nonempty(self):
        caps = build_index()[:3]
        text = render_capabilities(caps)
        assert caps[0].id in text

    def test_render_capabilities_empty(self):
        assert "no capabilities" in render_capabilities([]).lower()

    def test_render_tool_arsenal_nonempty(self):
        text = render_tool_arsenal()
        assert "nmap" in text

    def test_render_tool_arsenal_service_filter(self):
        text = render_tool_arsenal(service="smb")
        assert "nxc" in text


class TestCapabilityCLI:
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "portal.modules.security.core", "capability", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_list_json(self):
        result = self._run("list", "--phase", "recon", "--json")
        assert result.returncode == 0
        assert result.stdout.strip().startswith("[")

    def test_query_json(self):
        result = self._run("query", "--observations", '{"open_ports": [445]}', "--json")
        assert result.returncode == 0
        assert "smb_probe" in result.stdout

    def test_tools(self):
        result = self._run("tools", "--service", "smb")
        assert result.returncode == 0
        assert "nxc" in result.stdout

    def test_arsenal(self):
        result = self._run("arsenal", "--phase", "recon")
        assert result.returncode == 0
        assert "nmap" in result.stdout
