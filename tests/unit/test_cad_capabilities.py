"""Capability probes (no engine, no OpenSCAD required)."""

from portal.modules.cad.tools import capabilities as caps


def test_reports_arch_and_probe_keys():
    caps.cad_capabilities.cache_clear()
    c = caps.cad_capabilities()
    for key in ("openscad_bin", "openscad_version", "openscad_backend", "build123d_mcp", "arch"):
        assert key in c
    assert "platform" not in c


def test_status_engine_false_without_bridge():
    assert caps.cad_status()["engine"] is False
