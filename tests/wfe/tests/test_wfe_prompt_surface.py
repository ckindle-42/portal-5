from __future__ import annotations

from tests.wfe.prompt_surface import (
    HARNESS_NOTE_MARKER,
    harness_note,
    production_tool_names,
    prompt_tool_mismatches,
    suite_warnings,
    taxonomy_conflicts,
)
from tests.wfe.runner import TOOL_NAMES, workspace_context

HARNESS = {"file_read", "file_list", "repo_search", "file_write", "http_get", "pytest_run"}
KNOWN = {"nerc_cip_requirement", "compliance_ask", "nerc_cip_currency", "file_read"}


def test_flags_production_tools_the_harness_does_not_offer() -> None:
    prompt = "Begin with nerc_cip_requirement; then use compliance_ask. Use file_read for packets."
    assert prompt_tool_mismatches(prompt, HARNESS, KNOWN) == [
        "compliance_ask",
        "nerc_cip_requirement",
    ]


def test_clean_prompt_has_no_mismatch_and_no_note() -> None:
    prompt = "Read packet.json with file_read."
    assert prompt_tool_mismatches(prompt, HARNESS, KNOWN) == []
    assert harness_note(prompt, sorted(HARNESS), KNOWN) == ""


def test_production_tool_names_skips_plain_words() -> None:
    portal = {"workspaces": {"a": {"tools": ["web_search", "neighbors"]}, "b": {}}}
    assert production_tool_names(portal) == {"web_search"}


def test_note_declares_the_surface_and_silences_both_warnings() -> None:
    prompt = "Use nerc_cip_currency. Coverage: Full | Partial."
    user = "Reply with determination SUPPORTED or ABSENT."
    note = harness_note(prompt, sorted(HARNESS), KNOWN)
    assert HARNESS_NOTE_MARKER in note and "file_read" in note
    assert suite_warnings(prompt + note, user, HARNESS, KNOWN) == []


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
        KNOWN,
    )
    assert any("nerc_cip_currency" in w for w in warnings)
    assert any("taxonomy conflict" in w for w in warnings)


def test_auto_compliance_is_served_with_the_note() -> None:
    ctx = workspace_context("auto-compliance")
    assert ctx["harness_note"] is True
    assert ctx["system_prompt"].rstrip().endswith("described above.")
    assert set(ctx["tool_surface"]) <= set(TOOL_NAMES)
