"""The attainability check for the planted determinations: every deciding fact is recorded, the
check fails when a fact, the address or the normative text is unreachable, and it fails when the
answer key is reachable. The live pass is `python -m tests.wfe.e2e.compliance_attainability`."""

from __future__ import annotations

import re

from tests.wfe.e2e import compliance_attainability as att
from tests.wfe.suites import build_compliance_production as gen


def test_every_determination_records_deciding_facts_from_both_sides():
    targets = gen.determination_targets()
    assert len(targets) == 12
    for t in targets:
        facts = gen.DECIDING_FACTS[t["doc"]]
        tools = {f.tool for f in facts}
        assert "compliance_read" in tools, t["doc"]  # the document's own language
        assert "nerc_cip_requirement" in tools or "compliance_requirement" in tools, t["doc"]
        for f in facts:
            re.compile(f.pattern)
            assert f.why


def test_deciding_fact_tools_are_served_by_the_evaluation_instance():
    from portal.modules.compliance.core.eval_instance import VERIFIED_TOOLS

    for facts in gen.DECIDING_FACTS.values():
        for f in facts:
            assert f.tool in VERIFIED_TOOLS


def test_an_empty_store_fails_every_task_on_facts_and_on_coverage():
    result = att.check_all(lambda tool, args: "{}")
    assert len(result) == 12 and all(result.values())
    sample = result["OT-POL-007"]
    assert any(m.startswith("fact not exposed") for m in sample)
    assert any("no sections of the standard" in m for m in sample)
    assert any("no normative text" in m for m in sample)


def test_a_double_prefixed_address_error_is_reported():
    def call(tool, args):
        return '{"dual_document": {"error": "x is not a regulatory address"}}'

    failures = att.check_task("OT-POL-007", "CIP-007-6 R2 Part 2.2", call)
    assert any("rejects the fully qualified address" in m for m in failures)


def test_a_reachable_answer_key_fails_the_check():
    def call(tool, args):
        return '{"expected_coverage": "FULL"}'

    failures = att.check_task("OT-POL-007", "CIP-007-6 R2 Part 2.2", call)
    assert any(m.startswith("answer key reachable") for m in failures)


def test_a_failed_call_is_a_failure_not_a_pass():
    def call(tool, args):
        raise OSError("down")

    assert att.check_task("OT-POL-007", "CIP-007-6 R2 Part 2.2", call)


def test_the_future_effective_task_names_its_as_of_date():
    tasks = {t["id"]: t for t in gen.determinations()}
    (task,) = [t for k, t in tasks.items() if "future-effective" in k]
    assert "as of 2024-01-01" in task["instruction"]
