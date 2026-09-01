"""Acceptance: Sigma convert/validate, YARA compile, sandbox guard. Live SIEM = smoke only."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.detection.tools.detection_mcp")

SIGMA = """
title: Suspicious Whoami
logsource: {product: windows, category: process_creation}
detection:
  sel: {Image|endswith: '\\\\whoami.exe'}
  condition: sel
level: low
"""


def test_validate_sigma_ok():
    pytest.importorskip("sigma.collection")
    out = mod.validate_sigma(SIGMA)
    assert out["valid"] and out["rule_count"] == 1


def test_validate_sigma_rejects_garbage():
    pytest.importorskip("sigma.collection")
    out = mod.validate_sigma("not: a: valid: sigma: rule")
    assert not out["valid"]


def test_convert_sigma_splunk():
    pytest.importorskip("sigma.backends.splunk")
    out = mod.convert_sigma(SIGMA, target="splunk")
    assert out["valid"] and out["queries"]
    assert "whoami.exe" in out["queries"][0]


def test_convert_sigma_unknown_target():
    out = mod.convert_sigma(SIGMA, target="nope")
    assert "error" in out


def test_yara_compile_and_sandbox():
    pytest.importorskip("yara")
    ok = mod.compile_yara('rule t { strings: $a = "mz" condition: $a }')
    assert ok["valid"]
    bad = mod.compile_yara("rule broken {")
    assert not bad["valid"]
    esc = mod.scan_yara("rule t { condition: true }", "../../../etc/passwd")
    assert "escapes sandbox" in esc.get("error", "")


def test_query_splunk_rejects_subsearch():
    out = mod.query_splunk("index=x [ search foo ]")
    assert "rejected" in out.get("error", "")


def test_tools_manifest_matches_dispatch():
    assert {t["function"]["name"] for t in mod.TOOLS_MANIFEST} == set(mod._DISPATCH)
