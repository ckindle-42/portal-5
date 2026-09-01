"""Acceptance: sandbox guard, recon disabled-by-default, lab-CIDR refusal."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.netforensics.tools.netforensics_mcp")


def test_path_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_ROOT", tmp_path.resolve())
    with pytest.raises(ValueError):
        mod._resolve("../../etc/passwd")


def test_recon_disabled_by_default(monkeypatch):
    monkeypatch.setattr(mod, "_RECON_ENABLED", False)
    out = mod.recon_scan("10.10.11.5")
    assert out["refused"] and "disabled" in out["reason"]


def test_recon_refuses_outside_lab(monkeypatch):
    monkeypatch.setattr(mod, "_RECON_ENABLED", True)
    out = mod.recon_scan("8.8.8.8")
    assert out["refused"] and "outside authorized lab" in out["reason"]


def test_recon_refuses_cidr_outside_lab(monkeypatch):
    monkeypatch.setattr(mod, "_RECON_ENABLED", True)
    out = mod.recon_scan("192.168.0.0/24")
    assert out["refused"]


def test_lab_cidr_reuses_security_guard(monkeypatch):
    monkeypatch.delenv("PORTAL_LAB_CIDR", raising=False)
    from portal.modules.security.core.perception import LAB_CIDR

    assert mod._lab_cidr() == LAB_CIDR


def test_conversations_rejects_bad_kind():
    out = mod.conversations("x.pcap", kind="bogus")
    assert "unsupported kind" in out.get("error", "")


def test_tools_manifest_matches_dispatch():
    assert {t["function"]["name"] for t in mod.TOOLS_MANIFEST} == set(mod._DISPATCH)
