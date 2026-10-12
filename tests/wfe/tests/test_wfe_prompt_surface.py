"""Prompt/tool-surface consistency checks (tests/wfe/prompt_surface.py)."""

from __future__ import annotations

from tests.wfe.prompt_surface import prompt_tool_mismatches, suite_warnings, taxonomy_conflicts

HARNESS = {"file_read", "file_list", "repo_search", "file_write", "http_get", "pytest_run"}


def test_flags_compliance_tools_the_harness_does_not_offer() -> None:
    prompt = "Begin with nerc_cip_requirement; then use compliance_ask. Use file_read for packets."
    assert prompt_tool_mismatches(prompt, HARNESS) == ["compliance_ask", "nerc_cip_requirement"]


def test_clean_prompt_has_no_mismatch() -> None:
    assert prompt_tool_mismatches("Read packet.json with file_read.", HARNESS) == []


def test_taxonomy_conflict_detected() -> None:
    system = "Coverage: one of Full / Partial / None / Ambiguous."
    user = "Reply with a single JSON object: determination (SUPPORTED, PARTIAL, ABSENT)."
    assert taxonomy_conflicts(system, user) == ["coverage", "determination"]


def test_single_taxonomy_is_not_a_conflict() -> None:
    assert taxonomy_conflicts("Use Full or None.", "Say what you found.") == []


def test_suite_warnings_reports_both_kinds() -> None:
    warnings = suite_warnings(
        "Use nerc_cip_currency. Coverage: Full | Partial.",
        "Reply with determination SUPPORTED or ABSENT.",
        HARNESS,
    )
    assert any("nerc_cip_currency" in w for w in warnings)
    assert any("taxonomy conflict" in w for w in warnings)
