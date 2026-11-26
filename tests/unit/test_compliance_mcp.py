"""Compliance MCP conversation surface: context material serialization.

Hermetic: no network, no models, no retrieval; repository and runtime config
are monkeypatched.
"""

from __future__ import annotations

import sqlite3

from portal.modules.compliance.core import section_index
from portal.modules.compliance.tools import compliance_mcp


def _alias_repo() -> object:
    """In-memory store: one operator doc (current + superseded revision) and
    two docs sharing a filename stem, exercising the alias fallback for real
    (only source_documents/document_revisions are needed)."""

    class _Repo:
        def __init__(self) -> None:
            self._conn = sqlite3.connect(":memory:")
            self._conn.row_factory = sqlite3.Row
            self._conn.execute(
                "CREATE TABLE source_documents (logical_id TEXT, title TEXT, jurisdiction TEXT)"
            )
            self._conn.execute(
                """CREATE TABLE document_revisions (revision_id TEXT, logical_id TEXT,
                   document_number TEXT, effective_date TEXT, inactive_date TEXT,
                   retrieved_at TEXT)"""
            )
            self._conn.executemany(
                "INSERT INTO source_documents VALUES (?,?,?)",
                [
                    ("CIP-007/LSPG ADM CIP007SPM.pdf", "Patch Management Procedure", "internal"),
                    ("CIP-007/Access Review.pdf", "Access Review Worksheet", "internal"),
                    ("CIP-008/Access Review.pdf", "Access Review Worksheet", "internal"),
                ],
            )
            self._conn.executemany(
                "INSERT INTO document_revisions VALUES (?,?,?,?,?,?)",
                [
                    # governing revision of the patch-management doc
                    (
                        "rev-spm-2",
                        "CIP-007/LSPG ADM CIP007SPM.pdf",
                        "OT-POL-007",
                        "2026-01-01",
                        None,
                        "2026-01-02T00:00:00",
                    ),
                    # superseded revision carrying a different doc_no — must not match
                    (
                        "rev-spm-1",
                        "CIP-007/LSPG ADM CIP007SPM.pdf",
                        "OT-OLD-007",
                        "2020-01-01",
                        None,
                        "2020-01-02T00:00:00",
                    ),
                    (
                        "rev-ar7",
                        "CIP-007/Access Review.pdf",
                        "OT-POL-010",
                        "2026-01-01",
                        None,
                        "2026-01-02T00:00:00",
                    ),
                    (
                        "rev-ar8",
                        "CIP-008/Access Review.pdf",
                        "OT-POL-011",
                        "2026-01-01",
                        None,
                        "2026-01-02T00:00:00",
                    ),
                ],
            )

        def close(self) -> None:
            # no-op: compliance_read closes the repo per call; the in-memory
            # store is reused across calls within one test.
            self._conn.commit()

    return _Repo()


def _patch_resolution(monkeypatch, logical_ids: dict[str, list[str]], entry_text: str) -> None:
    """Stub the section-resolution layer (needs source_sections/register tables
    the in-memory store does not create) while the alias matching runs for real."""

    def _fake_sections_in_scope(repo, *, logical_id="", **_kw):
        return logical_ids.get(logical_id, [])

    logical_ids_values = {sid for ids in logical_ids.values() for sid in ids}

    def _resolve(repo, ids):
        out = {}
        for sid in ids:
            if sid in logical_ids_values:
                out[sid] = {
                    "section_id": sid,
                    "logical_id": "CIP-007/LSPG ADM CIP007SPM.pdf",
                    "document_title": "Patch Management Procedure",
                    "jurisdiction": "internal",
                    "text": entry_text,
                    "ordinal": 1,
                }
        return out

    monkeypatch.setattr(section_index, "sections_in_scope", _fake_sections_in_scope)
    monkeypatch.setattr(section_index, "resolve_sections", _resolve)
    monkeypatch.setattr(compliance_mcp, "_resolve_by_address", lambda repo, ref: {})


def test_compliance_read_resolves_doc_no_case_insensitively(monkeypatch):
    """A doc_no the seat naturally names ("OT-POL-007") reads the document
    directly instead of failing flat, echoing the logical_id for the next call."""
    repo = _alias_repo()
    monkeypatch.setattr(compliance_mcp, "_repo", lambda: repo)
    _patch_resolution(
        monkeypatch, {"CIP-007/LSPG ADM CIP007SPM.pdf": ["isection-spm-1"]}, "policy body"
    )

    out = compliance_mcp.compliance_read("ot-pol-007")
    assert out["resolved"] is True
    assert out["document_match"]["logical_id"] == "CIP-007/LSPG ADM CIP007SPM.pdf"
    assert out["document_match"]["matched_by"] == "document_number"
    assert "policy body" in out["units"][0]["text"]

    # the superseded revision's doc_no matches nothing
    out_old = compliance_mcp.compliance_read("OT-OLD-007")
    assert out_old["resolved"] is False
    assert "available_matches" not in out_old


def test_compliance_read_filename_stem_reads_unique_and_lists_ambiguous(monkeypatch):
    """A PDF filename the seat copied resolves the unique doc and lists the
    candidates when two active documents share the stem."""
    repo = _alias_repo()
    monkeypatch.setattr(compliance_mcp, "_repo", lambda: repo)
    _patch_resolution(
        monkeypatch, {"CIP-007/LSPG ADM CIP007SPM.pdf": ["isection-spm-1"]}, "policy body"
    )

    unique = compliance_mcp.compliance_read("lspg adm cip007spm.pdf")
    assert unique["resolved"] is True
    assert unique["document_match"]["matched_by"] == "filename"
    assert unique["document_match"]["logical_id"] == "CIP-007/LSPG ADM CIP007SPM.pdf"

    ambiguous = compliance_mcp.compliance_read("Access Review.pdf")
    assert ambiguous["resolved"] is False
    assert sorted(m["logical_id"] for m in ambiguous["available_matches"]) == [
        "CIP-007/Access Review.pdf",
        "CIP-008/Access Review.pdf",
    ]


def test_compliance_context_material_is_json(monkeypatch):
    """mode=material once returned render()'s in-process AnswerContract and
    failed serialization on every call (PIPELINE_ALIGNMENT_V1 §13); the DD3
    builder is JSON by construction and its payload passes through whole."""
    import json

    from portal.modules.compliance.core import dual_document, runtime_config

    class _Repo:
        def close(self) -> None:
            pass

    monkeypatch.setattr(compliance_mcp, "_repo", _Repo)
    monkeypatch.setattr(
        runtime_config,
        "reading_context_limits",
        lambda: {"context_limit": 131072, "predict_limit": 24576},
    )
    monkeypatch.setattr(runtime_config, "reading_route_ceiling", lambda: 262144)
    monkeypatch.setattr(
        dual_document,
        "build",
        lambda repo, **kw: {
            "mode": "dual_document",
            "ref": kw["requirement_ref"],
            "text": "payload",
            "window": {
                "context_limit": kw["context_limit"],
                "served_ceiling": kw["served_ceiling"],
                "fits": True,
            },
            "documents_included": [{"title": "doc"}],
        },
    )

    out = compliance_mcp.compliance_context("CIP-007-6 R2 Part 2.3", mode="material")
    assert out["mode"] == "dual_document" and out["text"] == "payload"
    json.dumps(out)


def test_compliance_read_arguments_never_reject_at_the_sdk_boundary():
    """QAT cfe67a16e run 140220Z, 14:49:23Z: `compliance_read error=Tool
    'compliance_read' returned an MCP tool error` x2. The compliance MCP log
    (~/.portal5/logs/compliance-mcp.log, server.py:450) names the actual
    exception: `Tool 'compliance_read' rejected arguments: ['neighbors']` —
    pydantic rejected the call at the SDK boundary before the body ran, so a
    valid section reference surfaced as an opaque error. The SDK redacts the
    value, so these are the shapes a "batched reads" attempt emits; none of
    them may reject."""
    tool = compliance_mcp.mcp._tool_manager.get_tool("compliance_read")
    assert tool is not None
    for bad in (None, ["R-abc123", "R-def456"], {"ref": "x"}, "the retention sections"):
        validated = tool.fn_metadata.validate_arguments(
            {"ref": "CIP-007-6 Requirement 2 Part 2.2", "neighbors": bad}
        )
        assert isinstance(validated["neighbors"], bool)
    validated = tool.fn_metadata.validate_arguments(
        {"ref": "csection-abc123", "neighbors": "true", "max_chars": None}
    )
    assert validated["neighbors"] is True
    assert validated["max_chars"] == 6000
    # the advertised schema is unchanged: the model still sees a plain boolean
    assert tool.parameters["properties"]["neighbors"]["type"] == "boolean"


def test_compliance_read_reads_with_a_misspelled_flag(monkeypatch):
    """Body level: a non-bool flag value still reads the (valid) reference."""
    repo = _alias_repo()
    monkeypatch.setattr(compliance_mcp, "_repo", lambda: repo)
    _patch_resolution(
        monkeypatch, {"CIP-007/LSPG ADM CIP007SPM.pdf": ["isection-spm-1"]}, "policy body"
    )
    monkeypatch.setattr(
        compliance_mcp,
        "_neighbors",
        lambda repo, entry, max_chars: {"heading_path": "", "siblings": []},
    )
    out = compliance_mcp.compliance_read("ot-pol-007", neighbors=["R-abc123"])
    assert out["resolved"] is True
    assert "policy body" in out["units"][0]["text"]


def test_compliance_read_invalid_ref_gets_a_specific_message(monkeypatch):
    """An unresolvable reference names what IS accepted instead of failing flat."""
    repo = _alias_repo()
    monkeypatch.setattr(compliance_mcp, "_repo", lambda: repo)
    _patch_resolution(monkeypatch, {}, "")
    out = compliance_mcp.compliance_read("CIP-007-6 Requirement Twenty-Two")
    assert out["resolved"] is False
    assert "accepted forms" in out["detail"]
    assert "CIP-007-6 R2 Part 2.2" in out["detail"]
