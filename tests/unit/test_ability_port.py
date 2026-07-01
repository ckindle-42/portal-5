"""Fidelity tests for ported ptai probes — real detect() functions, not stubs."""

from __future__ import annotations

import ast

import pytest

from tests.benchmarks.bench_security.ability_port import (
    SQL_ERROR_MARKERS,
    SSTI_EVAL_MARKERS,
    SSTI_ERROR_MARKERS,
    auth_bypass_detect,
    lfi_detect,
    nosql_detect,
    register_ported_oracles,
    sqli_detect,
    ssti_detect,
    xss_detect,
    xxe_detect,
)
from tests.benchmarks.bench_security.oracles import ORACLES


class TestSSTIDetect:
    def test_eval_marker_true(self):
        assert ssti_detect(200, {}, "result: 49", "result: ") is True

    def test_clean_baseline_false(self):
        assert ssti_detect(200, {}, "result: 49", "result: 49") is False

    def test_jinja2_traceback_true(self):
        body = "jinja2.exceptions.TemplateSyntaxError: unexpected '}'"
        assert ssti_detect(200, {}, body, "ok") is True

    def test_no_body_false(self):
        assert ssti_detect(200, {}, "", "") is False


class TestSQLiDetect:
    def test_mysql_error_true(self):
        body = "You have an error in your SQL syntax; check the manual"
        assert sqli_detect(200, {}, body, "ok") is True

    def test_baseline_false(self):
        body = "You have an error in your SQL syntax"
        assert sqli_detect(200, {}, body, body) is False

    def test_union_leak_true(self):
        assert sqli_detect(200, {}, '{"name":"2"}', '{"name":"1"}') is True

    def test_empty_body_false(self):
        assert sqli_detect(200, {}, "", "") is False


class TestXSSDetect:
    def test_payload_echoed_true(self):
        body = '<html><script>alert(\'ptai\')</script></html>'
        assert xss_detect(200, {}, body, "") is True

    def test_clean_body_false(self):
        assert xss_detect(200, {}, "clean page", "") is False


class TestLFIDetect:
    def test_passwd_content_true(self):
        body = "root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon"
        assert lfi_detect(200, {}, body, "") is True

    def test_clean_false(self):
        assert lfi_detect(200, {}, "no passwd here", "") is False


class TestXXEDetect:
    def test_entity_expansion_true(self):
        body = "root:x:0:0:root:/root:/bin/bash"
        assert xxe_detect(200, {}, body, "") is True

    def test_clean_false(self):
        assert xxe_detect(200, {}, "all clean", "") is False


class TestNoSQLDetect:
    def test_mongo_error_true(self):
        assert nosql_detect(200, {}, "MongoError: bad query", "ok") is True

    def test_clean_false(self):
        assert nosql_detect(200, {}, "clean", "") is False


class TestAuthBypassDetect:
    def test_dashboard_true(self):
        assert auth_bypass_detect(200, {}, "Welcome to dashboard", "login page") is True

    def test_login_page_false(self):
        assert auth_bypass_detect(200, {}, "login page", "login page") is False


class TestOracleRegistration:
    def test_ptai_oracles_registered(self):
        register_ported_oracles()
        ptai = [k for k in ORACLES if k.startswith("ptai_")]
        assert len(ptai) >= 20, f"expected >=20 ptai oracles, got {len(ptai)}: {ptai}"

    def test_ssti_oracle_check_runs(self):
        register_ported_oracles()
        o = ORACLES.get("ptai_ssti")
        assert o is not None
        assert o.check({"status": 200, "baseline": ""}, "result: 49", {}) is True


class TestAntiStub:
    def test_real_detect_functions_exist(self):
        src = open("tests/benchmarks/bench_security/ability_port.py").read()
        t = ast.parse(src)
        detect_funcs = [n.name for n in ast.walk(t) if isinstance(n, ast.FunctionDef) and "detect" in n.name]
        assert len(detect_funcs) >= 7, f"expected >=7 detect functions, got {detect_funcs}"

    def test_no_detect_sig_strings(self):
        src = open("tests/benchmarks/bench_security/ability_port.py").read()
        assert "detect_sig" not in src, "detect_sig stub field must not exist"
