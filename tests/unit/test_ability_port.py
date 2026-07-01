"""Fidelity tests for ported ptai probes — real detect() functions, not stubs."""

from __future__ import annotations

import ast

from tests.benchmarks.bench_security.ability_port import (
    SQL_ERROR_MARKERS,
    register_ported_oracles,
    sqli_detect,
    ssti_detect,
)
from tests.benchmarks.bench_security.oracles import ORACLES


class TestSSTIDetect:
    def test_eval_marker_true(self):
        assert ssti_detect(200, {}, "result: 49", "result: ") is True
    def test_clean_baseline_false(self):
        assert ssti_detect(200, {}, "result: 49", "result: 49") is False
    def test_jinja2_traceback_true(self):
        assert ssti_detect(200, {}, "jinja2.exceptions.TemplateSyntaxError: unexpected '}'", "ok") is True
    def test_no_body_false(self):
        assert ssti_detect(200, {}, "", "") is False


class TestSQLiDetect:
    def test_mysql_error_true(self):
        assert sqli_detect(200, {}, "You have an error in your SQL syntax", "ok") is True
    def test_baseline_false(self):
        body = "You have an error in your SQL syntax"
        assert sqli_detect(200, {}, body, body) is False
    def test_union_leak_true(self):
        assert sqli_detect(200, {}, '{"name":"2"}', '{"name":"1"}') is True
    def test_empty_body_false(self):
        assert sqli_detect(200, {}, "", "") is False


class TestPortedOraclesViaRegistry:
    """Test ported probes through the oracle registry (all 54 probes use lambda-based check)."""
    @classmethod
    def setup_class(cls):
        register_ported_oracles()

    def test_all_ptai_oracles_registered(self):
        ptai = [k for k in ORACLES if k.startswith("ptai_")]
        assert len(ptai) >= 53, f"expected >=53, got {len(ptai)}: {sorted(ptai)}"

    def test_ssti_oracle_check(self):
        o = ORACLES["ptai_ssti"]
        assert o.check({"status": 200, "baseline": ""}, "result: 49", {}) is True

    def test_sqli_oracle_check(self):
        o = ORACLES["ptai_sqli"]
        assert o.check({}, "You have an error in your SQL syntax", {}) is True

    def test_xss_oracle_check(self):
        o = ORACLES["ptai_xss"]
        assert o.check({"baseline": ""}, "<script>alert('ptai')</script>", {}) is True

    def test_lfi_oracle_check(self):
        o = ORACLES["ptai_lfi"]
        assert o.check({"baseline": ""}, "root:x:0:0:root:/root:/bin/bash", {}) is True

    def test_nosql_oracle_check(self):
        o = ORACLES["ptai_nosql"]
        assert o.check({"baseline": ""}, "MongoError: bad query", {}) is True

    def test_graphql_oracle_check(self):
        o = ORACLES["ptai_graphql"]
        assert o.check({"baseline": ""}, '{"__schema":{"queryType":{"name":"Query"}}}', {}) is True

    def test_proto_pollution_oracle_check(self):
        o = ORACLES["ptai_proto_pollution"]
        assert o.check({"baseline": ""}, '{"isAdmin":true}', {}) is True

    def test_idor_oracle_check(self):
        o = ORACLES["ptai_idor_auth"]
        assert o.check({"baseline": ""}, '{"userId":2,"username":"other"}', {}) is True

    def test_stored_xss_oracle_check(self):
        o = ORACLES["ptai_stored_xss"]
        assert o.check({"baseline": ""}, "<script>alert('ptai-stored')</script>", {}) is True


class TestAntiStub:
    def test_module_has_detect_logic(self):
        """Module has real detect functions (named or lambda) — no detect_sig stubs."""
        src = open("tests/benchmarks/bench_security/ability_port.py").read()
        assert "detect_sig" not in src, "detect_sig stub field must not exist"
        # At minimum the two reference implementations exist as named functions
        assert "def ssti_detect" in src
        assert "def sqli_detect" in src

    def test_oracles_registered_at_least_53(self):
        register_ported_oracles()
        ptai = [k for k in ORACLES if k.startswith("ptai_")]
        assert len(ptai) >= 53, f"got {len(ptai)}"
