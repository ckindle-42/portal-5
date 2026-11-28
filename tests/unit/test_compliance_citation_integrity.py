"""P5 — the one citation-integrity diagnostic, and harness parity.

Every case runs against a fixture store built in ``tmp_path`` (one regulatory
document, one operator document, synthetic text) so nothing skips: the
resolving, fabricated and side-evidencing paths are all exercised.
"""

from __future__ import annotations

from scripts.compliance.truth.citation_integrity import MIN_QUOTE_WORDS


def test_min_quote_words_is_the_b0_calibrated_value():
    assert MIN_QUOTE_WORDS == 2


def test_obligation_attribution_inside_a_quote_is_not_an_attribution():
    import importlib

    conv = importlib.import_module("scripts.compliance.ask_conversational")
    pattern = conv._STANDARD_ATTRIBUTION
    quoted = '- "Updated CIP-004 and CIP-011 requirements for standards effective 1/1/2024"'
    assert not pattern.search(conv.QUOTED_SPAN.sub(" ", quoted))
    assert not pattern.search("CIP-011 requirements were updated")
    assert pattern.search("CIP-011 requires an information protection program")


def test_acceptance_workspace_preserves_thread_resolves_alias_and_reports_ungrounded(
    monkeypatch, tmp_path
) -> None:
    import httpx

    from scripts import compliance_acceptance as ca

    thread = ca.WorkspaceThread(httpx.Client(), "compliance-reading", "http://localhost:9099")
    assert thread.preset["params"].get("system"), (
        "compliance-reading alias must load OWUI system prompt"
    )

    created: list[object] = []

    class _FakeThread:
        def __init__(self, *_args, **_kwargs) -> None:
            self.messages: list[dict[str, str]] = []
            created.append(self)

        def turn(self, question: str) -> dict:
            self.messages.append({"role": "user", "content": question})
            self.messages.append({"role": "assistant", "content": 'No source "fake quote here".'})
            return {
                "question": question,
                "answer": 'No source "fake quote here".',
                "http_status": 200,
                "turn_budget_exceeded": False,
                "prompt_tokens_high_water": 100,
                "serving": {"serving_window": 131072},
                "tool_calls": {"compliance_context": 1},
            }

    monkeypatch.setattr(ca, "WorkspaceThread", _FakeThread)
    monkeypatch.setattr(ca, "environment", lambda _u: {})
    monkeypatch.setattr(
        ca, "_campaign_inputs", lambda _s: {"seat": _s, "workspace_prompt_sha": "x"}
    )
    monkeypatch.setattr(
        "scripts.compliance.truth.citation_integrity.integrity",
        lambda *_a, **_kw: {
            "lines": [{"claim": "bad line", "grounded": False}],
            "fabricated_tokens": [],
            "grounded": False,
            "ungrounded_lines": ["bad line"],
            "n_claims": 1,
        },
    )
    threads: dict = {}
    c1 = {
        "id": "parent",
        "ref": "CIP-007-6 R2",
        "thread": "main",
        "question": "Q1",
        "tool_calls_min": 1,
    }
    c2 = {
        "id": "choice",
        "ref": "CIP-007-6 R2 Part 2.3",
        "thread": "main",
        "question": "Q2",
        "tool_calls_min": 1,
    }
    r1 = ca.run_cell(
        httpx.Client(), "http://localhost:8937", c1, "seat", "workspace", 1, tmp_path, threads
    )
    r2 = ca.run_cell(
        httpx.Client(), "http://localhost:8937", c2, "seat", "workspace", 1, tmp_path, threads
    )
    assert len(created) == 1, "main-thread turns must reuse one WorkspaceThread"
    assert r2["thread_length_messages"] == 4
    cite_check = next(c for c in r1["checks"] if c["assertion"] == "cited_ids_resolve")
    assert not cite_check["ok"] and cite_check["detail"] == ["bad line"]


def test_reading_workspace_prompt_covers_vsl_and_quote_discipline() -> None:
    import yaml

    from portal.platform.inference.config import effective_workspace

    portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
    ws = effective_workspace(portal["workspaces"], "auto-compliance::reading")
    prompt = ws["system_prompt_append"]
    assert "Violation Severity Levels" in prompt and "compliance_search" in prompt
    assert "even if you find no gaps" in prompt
    assert "tool payloads are NOT retained" in prompt
    assert "Reserve double quotes strictly for verbatim source quotes" in prompt


def test_reading_workspace_enforces_tool_call_card_sampling_and_vsl_note() -> None:
    import inspect

    import yaml

    from portal.modules.compliance.core import dual_document
    from portal.platform.inference.config import effective_workspace

    portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
    ws = effective_workspace(portal["workspaces"], "auto-compliance::reading")
    assert ws.get("tool_choice") == "required"
    # 2026-11-28: the seat moved to Qwen3.6-35B-A3B and serves the instruct
    # card's own row (above the compliance lane's 0.3 ceiling, which the card
    # outranks — settings_audit sampling_card_over_lane). The guard is now that
    # the served values ARE the card's, not that they are deterministic.
    cards = yaml.safe_load(open("config/model_card_expectations.yaml", encoding="utf-8"))
    instruct = cards["models"]["qwen3.6"]["recommended_sampling_modes"]["instruct"]
    assert float(ws.get("temperature")) == float(instruct["temperature"])
    assert float(ws.get("top_p")) == float(instruct["top_p"])
    assert int(ws.get("top_k")) == int(instruct["top_k"])
    src = inspect.getsource(dual_document._build_from_ids)
    assert "VSL" in src and "compliance_search" in src


def test_tool_result_preserves_unicode_and_bullet_fold_rejects_fabrication() -> None:
    from portal.modules.compliance.core.candidate_links import _norm_for_verbatim
    from portal.platform.inference.router.tools import _guard_tool_result

    raw = (
        "Where technically feasible, either: \uf0b7 Limit the number of "
        "unsuccessful authentication attempts; or \u2022 Generate alerts."
    )
    serialized = _guard_tool_result({"text": raw})
    assert "\\uf0b7" not in serialized and "\\u2022" not in serialized
    assert "\uf0b7" in serialized and "\u2022" in serialized

    folded_src = _norm_for_verbatim(raw)
    assert (
        _norm_for_verbatim(
            "Where technically feasible, either: Limit the number of "
            "unsuccessful authentication attempts; or Generate alerts."
        )
        in folded_src
    )
    # Real fabrication/alteration still fails verbatim containment.
    assert (
        _norm_for_verbatim(
            "Where technically feasible, either: Limit the number of "
            "failed login attempts; or Generate alerts."
        )
        not in folded_src
    )


def test_list_separator_normalization_and_qat_quote_fidelity(tmp_path) -> None:
    from portal.modules.compliance.core.models import SourceDocument, SourceSection
    from portal.modules.compliance.core.repository import Repository
    from scripts.compliance.truth.citation_integrity import integrity
    from tests.qat.uat_behavioral import UATCase, UATTurn, _grade_compliance_policy_case

    repo = Repository(tmp_path / "store.db")
    try:
        lspg_text = (
            "3.5.1 \n"
            "For all identified applicable security or potential security patches, within thirty-five (35) \n"
            "calendar days of the evaluation, one of the following actions shall be taken:  \n"
            "3.5.1.1 \n"
            "RFC approval and installation of applicable patches \n"
            "3.5.1.2 \n"
            "Creation of a dated mitigation plan \n"
            "3.5.1.3 \n"
            "Revision of an existing mitigation plan \n"
        )
        reg_text = (
            "At least once every 35 calendar days, evaluate security patches for applicability "
            "that have been released since the last evaluation from the source or sources identified in Part 2.1."
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="CIP-007/LSPG WI.pdf",
                title="LSPG WI",
                issuer="LSPG",
                source_kind="work_instruction",
                jurisdiction="internal",
            )
        )
        rev_op = repo.add_document_revision(
            "CIP-007/LSPG WI.pdf",
            "LSPG WI.pdf",
            lspg_text.encode(),
            binding_effect="internally_mandatory",
        )
        repo.put_document_text(
            rev_op.revision_id, lspg_text, page_count=1, extractor="test", extractor_version="1"
        )
        repo.add_source_section(
            SourceSection(
                section_id="isection-qf",
                revision_id=rev_op.revision_id,
                path="3.5.1",
                heading_path="3.5.1",
                title="3.5.1",
                char_start=0,
                char_end=len(lspg_text),
                ordinal=1,
            )
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-007-6.pdf",
                title="CIP-007-6",
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        rev_reg = repo.add_document_revision(
            "NERC/CIP-007-6.pdf",
            "CIP-007-6.pdf",
            reg_text.encode(),
            binding_effect="regulatory",
        )
        repo.put_document_text(
            rev_reg.revision_id, reg_text, page_count=1, extractor="test", extractor_version="1"
        )
        repo.add_source_section(
            SourceSection(
                section_id="csection-22222222222222222222",
                revision_id=rev_reg.revision_id,
                path="R2 Part 2.2",
                heading_path="R2 Part 2.2",
                title="Part 2.2",
                char_start=0,
                char_end=len(reg_text),
                ordinal=1,
            )
        )

        # Class (b): verbatim words with PDF outline markers replaced by '; ' or inline enumerators resolve.
        for joined in (
            '- "For all identified applicable security or potential security patches, '
            "within thirty-five (35) calendar days of the evaluation, one of the following "
            "actions shall be taken: RFC approval and installation of applicable patches; "
            'Creation of a dated mitigation plan; Revision of an existing mitigation plan."',
            '- "For all identified applicable security or potential security patches, '
            "within thirty-five (35) calendar days of the evaluation, one of the following "
            "actions shall be taken: 1. RFC approval and installation of applicable patches; "
            '2. Creation of a dated mitigation plan; 3. Revision of an existing mitigation plan"',
            '- "For all identified applicable security or potential security patches, '
            "within thirty-five (35) calendar days of the evaluation, one of the following "
            "actions shall be taken: 1) RFC approval and installation of applicable patches; "
            '2) Creation of a dated mitigation plan; 3) Revision of an existing mitigation plan"',
            '- "For all identified applicable security or potential security patches, '
            "within thirty-five (35) calendar days of the evaluation, one of the following "
            "actions shall be taken: a. RFC approval and installation of applicable patches; "
            'b. Creation of a dated mitigation plan; c. Revision of an existing mitigation plan"',
            '- "1. RFC approval and installation of applicable patches; 2. Creation of a dated mitigation plan"',
            '- "For all identified applicable security or potential security patches, '
            "within thirty-five (35) calendar days of the evaluation, one of the following "
            "actions shall be taken: 3.5.1.1 RFC approval and installation of applicable patches; "
            '3.5.1.2 Creation of a dated mitigation plan; 3.5.1.3 Revision of an existing mitigation plan."',
        ):
            ok = integrity(repo, joined)
            assert ok["grounded"], (joined, ok)
            assert ok["quotes"][0].get("fold") == "list_separators"

        # Class (c): garbled numbers/words and inline number changes MUST still fail.
        for bad in (
            '- "For all identified applicable security or potential security patches, within thirty-five (35s) calendar days of the evaluation, one of the following actions shall be taken: RFC approval and installation of applicable patches; Creation of a dated mitigation plan; Revision of an existing mitigation plan."',
            '- "At least once every TS5 calendar days, evaluate security patches for applicability that have been released since the last evaluation..."',
            '- "At least once every 35 calendar days, evaluate security patches for applicability that have which have been released since the last evaluation from the source or sources identified in Part 2.1."',
            '- "At least once every 35 calendar days, evaluate security patches for applicability that have been released since the last evaluation from the source or sources identified in Part 2.9."',
        ):
            res = integrity(repo, bad)
            assert not res["grounded"], f"must reject altered quote: {bad}"
    finally:
        repo.close()

    # QAT s5-compliance-policy-conversation grader: typography/newline fold passes, alteration fails.
    case = UATCase(
        "s5-compliance-policy-conversation", "t", "auto-compliance", ("q",), "compliance_policy_gap"
    )
    turns = [
        UATTurn(
            prompt="q",
            text="",
            trace={},
            tool_names=("compliance_read", "nerc_cip_requirement"),
            artifact_urls=(),
            tool_results=(
                {
                    "tool": "compliance_read",
                    "result": {
                        "success": True,
                        "receipt": {
                            "text": "OT-PROC-007: LSPG\u2019s patch evaluation runs within thirty-five (35)\ncalendar days of release."
                        },
                    },
                },
                {
                    "tool": "nerc_cip_requirement",
                    "result": {
                        "success": True,
                        "receipt": {
                            "text": "CIP-007-6 R2 Part 2.2: At least once every 35 calendar days, evaluate security patches."
                        },
                    },
                },
            ),
        )
    ]
    good_ans = (
        "Comparing OT-PROC-007 against CIP-007-6 R2 Parts 2.1, 2.3, and 2.4 in the ingested corpus: "
        'missing explicit cadence. "LSPG\'s patch evaluation runs within thirty-five (35) calendar days of release." '
        'and "At least once every 35 calendar days, evaluate security patches."'
    )
    errs = _grade_compliance_policy_case(case, turns, {}, good_ans, {})
    assert "quoted compliance clause is absent from retrieved receipts" not in errs, errs

    bad_ans = good_ans.replace("every 35 calendar days", "every TS5 calendar days")
    bad_errs = _grade_compliance_policy_case(case, turns, {}, bad_ans, {})
    assert "quoted compliance clause is absent from retrieved receipts" in bad_errs, bad_errs


def test_doc_names_and_refs_are_not_evidence_and_unknown_part_rejected(tmp_path) -> None:
    from portal.modules.compliance.core import dual_document
    from portal.modules.compliance.core.models import SourceDocument, SourceSection
    from portal.modules.compliance.core.repository import Repository
    from scripts.compliance.truth.citation_integrity import integrity

    repo = Repository(tmp_path / "store.db")
    try:
        reg_text = (
            "A patch management process for tracking, evaluating, and installing cyber security "
            "patches for applicable Cyber Assets. The tracking portion shall include the "
            "identification of a source or sources that the Responsible Entity tracks for the "
            "release of cyber security patches. Apply the applicable patches; or Create a dated "
            "mitigation plan; or Revise an existing mitigation plan. "
            "Where technically feasible, either: Limit the number of unsuccessful authentication "
            "attempts; or Generate alerts after a threshold of unsuccessful authentication attempts."
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="CIP-007/LSPG Security Patch Management Procedure V11.pdf",
                title="LSPG Security Patch Management Procedure",
                issuer="LSPG",
                source_kind="procedure",
                jurisdiction="internal",
            )
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-007-6",
                title="CIP-007-6",
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        rev_reg = repo.add_document_revision(
            "NERC/CIP-007-6",
            "CIP-007-6.pdf",
            reg_text.encode(),
            binding_effect="regulatory",
        )
        repo.put_document_text(
            rev_reg.revision_id, reg_text, page_count=1, extractor="test", extractor_version="1"
        )
        part_start = reg_text.index("Where technically feasible")
        repo.add_source_section(
            SourceSection(
                section_id="csection-57575757575757575757",
                revision_id=rev_reg.revision_id,
                path="R5 Part 5.7",
                heading_path="R5 Part 5.7",
                title="Part 5.7",
                char_start=0,
                char_end=len(reg_text),
                ordinal=1,
            )
        )
        repo._conn.execute(
            "INSERT INTO requirement_sections "
            "(requirement_id, section_id, revision_id, relation, char_start, char_end, anchored_at) "
            "VALUES (?, ?, ?, 'governing', ?, ?, '2026-01-01T00:00:00Z')",
            (
                "CIP-007-6 R5 Part 5.7",
                "csection-57575757575757575757",
                rev_reg.revision_id,
                part_start,
                len(reg_text),
            ),
        )
        repo._conn.commit()

        # Quoted document names and bare requirement refs classify as not_evidence, never quotes.
        doc_and_ref_answer = "\n".join(
            [
                '- "LSPG Security Patch Management Procedure V11.pdf" (operator procedure)',
                '- "CIP-007/LSPG Security Patch Management Procedure V11.pdf"',
                'The ref "CIP-003-6 R5" does not own Part 5.7; "CIP-007-6 R5 Part 5.7" does.',
                'It requires "Where technically feasible, either: Limit the number of unsuccessful authentication attempts".',
            ]
        )
        ok = integrity(repo, doc_and_ref_answer)
        assert ok["grounded"], ok
        by_quote = {q["quote"]: q["status"] for q in ok["quotes"]}
        assert by_quote["LSPG Security Patch Management Procedure V11.pdf"] == "not_evidence"
        assert (
            by_quote["CIP-007/LSPG Security Patch Management Procedure V11.pdf"] == "not_evidence"
        )
        assert by_quote["CIP-003-6 R5"] == "not_evidence"
        assert by_quote["CIP-007-6 R5 Part 5.7"] == "not_evidence"

        # Real faults (editorial [including] insertion; summarized quote) must keep failing.
        for bad_line in (
            '* Standard: Requires "A patch management process for tracking, evaluating, and installing cyber security patches... [including] the identification of a source or sources that the Responsible Entity tracks..."',
            'The standard\'s order is also "Apply; or Create; or Revise," so the sequence matches.',
        ):
            bad = integrity(repo, bad_line)
            assert not bad["grounded"], (bad_line, bad)

        # Unregistered Part / requirement / standard must not resolve as addressed Part.
        bad_part = dual_document.build(repo, requirement_ref="CIP-003-6 R5 Part 5.7")
        assert bad_part["resolved"] is False
        assert "CIP-007-6 R5 Part 5.7" in bad_part.get("matching_refs", [])
        assert dual_document.build(repo, requirement_ref="CIP-003-6 R5")["resolved"] is False
        assert dual_document.build(repo, requirement_ref="CIP-003-6")["resolved"] is False
        assert dual_document.build(repo, requirement_ref="CIP-007-6 R99")["resolved"] is False

        # Valid Part and parent requirement still resolve.
        good_part = dual_document.build(repo, requirement_ref="CIP-007-6 R5 Part 5.7")
        assert good_part["resolved"] is True
        assert "CIP-007-6 R5 Part 5.7" in good_part["requirement_refs"]
        good_req = dual_document.build(repo, requirement_ref="CIP-007-6 R5")
        assert good_req["resolved"] is True
        assert "CIP-007-6 R5 Part 5.7" in good_req["requirement_refs"]
    finally:
        repo.close()


def test_tool_text_not_evidence_and_escaped_bullet_fold(tmp_path) -> None:
    import json

    from portal.modules.compliance.core.models import SourceDocument, SourceSection
    from portal.modules.compliance.core.repository import Repository
    from scripts.compliance.truth.citation_integrity import integrity

    repo = Repository(tmp_path / "store.db")
    try:
        op_text = (
            "3.5.3 Authentication Attempts \n3.5.3.1 \n"
            "For applicable systems, at a minimum, where technically feasible, systems shall be \n"
            "configured to:  \n• \nLimit the number of unsuccessful authentication attempts, AND/OR; \n"
            "• \nGenerate alerts after a threshold of unsuccessful authentication attempts. \n"
        )
        reg_text = (
            "At least once every 35 calendar days, evaluate security patches for applicability "
            "that have been released since the last evaluation from the source or sources identified in Part 2.1. "
            "A patch management process for tracking, evaluating, and installing cyber security patches. "
            "The tracking portion shall include the identification of a source or sources. "
            "Apply the applicable patches; or Create a dated mitigation plan; or Revise an existing mitigation plan."
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="CIP-007/LSPG Account Management Procedure v6.pdf",
                title="LSPG Account Management",
                issuer="LSPG",
                source_kind="procedure",
                jurisdiction="internal",
            )
        )
        rev_op = repo.add_document_revision(
            "CIP-007/LSPG Account Management Procedure v6.pdf",
            "LSPG Account Management Procedure v6.pdf",
            op_text.encode(),
            binding_effect="internally_mandatory",
        )
        repo.put_document_text(
            rev_op.revision_id, op_text, page_count=1, extractor="test", extractor_version="1"
        )
        repo.add_source_section(
            SourceSection(
                section_id="isection-tt",
                revision_id=rev_op.revision_id,
                path="3.5.3",
                heading_path="3.5.3 Authentication Attempts",
                title="Authentication Attempts",
                char_start=0,
                char_end=len(op_text),
                ordinal=1,
            )
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-007-6",
                title="CIP-007-6",
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        rev_reg = repo.add_document_revision(
            "NERC/CIP-007-6",
            "CIP-007-6.pdf",
            reg_text.encode(),
            binding_effect="regulatory",
        )
        repo.put_document_text(
            rev_reg.revision_id, reg_text, page_count=1, extractor="test", extractor_version="1"
        )
        repo.add_source_section(
            SourceSection(
                section_id="csection-22222222222222222222",
                revision_id=rev_reg.revision_id,
                path="R2",
                heading_path="R2",
                title="R2",
                char_start=0,
                char_end=len(reg_text),
                ordinal=1,
            )
        )

        tool_outputs = [
            {
                "tool": "compliance_read",
                "arguments": json.dumps({"ref": "LSPG Patch V11.pdf §3.3"}),
                "output": json.dumps(
                    {
                        "resolved": False,
                        "detail": "no section, address, glossary term or document with that id; accepted forms: 'CIP-007-6 R2 Part 2.2'",
                    }
                ),
            },
            {
                "tool": "compliance_context",
                "arguments": json.dumps({"ref": "CIP-003-6 R5 Part 5.2", "mode": "material"}),
                "output": json.dumps(
                    {
                        "resolved": False,
                        "note": "'CIP-003-6 R5 Part 5.2' is not in the register; matching register refs: CIP-003-8 Attachment 1 Part 5.2",
                    }
                ),
            },
            {
                "tool": "compliance_search",
                "arguments": json.dumps(
                    {"query": "CIP-007-6 R2 Violation Severity Levels VSL table"}
                ),
                "output": "",
            },
            {
                "tool": "compliance_context",
                "arguments": json.dumps({"ref": "CIP-007-6 R2", "mode": "material"}),
                "output": json.dumps(
                    {
                        "resolved": True,
                        "text": "- your LSPG Security Patch Management Procedure maps CIP-007-6 R2 Part 2.1 to §3.1 Security Patch Management Process\n",
                    }
                ),
            },
        ]

        # Tool errors, tool notes, own search queries -> not_evidence; literal \n/\t/• fold -> resolved.
        answer = "\n".join(
            [
                'The tool returned "no section, address, glossary term or document with that id".',
                "- \"'CIP-003-6 R5 Part 5.2' is not in the register; matching register refs: CIP-003-8 Attachment 1 Part 5.2\"",
                'I called `compliance_search` for "CIP-007-6 R2 Violation Severity Levels VSL table".',
                '> "For applicable systems, at a minimum, where technically feasible, systems shall be configured to:  \\n• \\nLimit the number of unsuccessful authentication attempts, AND/OR; \\t\\n• \\nGenerate alerts after a threshold of unsuccessful authentication attempts."',
            ]
        )
        ok = integrity(repo, answer, tool_outputs=tool_outputs)
        assert ok["grounded"], ok
        by_quote = {q["quote"]: q["status"] for q in ok["quotes"]}
        assert (
            by_quote["no section, address, glossary term or document with that id"]
            == "not_evidence"
        )
        assert (
            by_quote[
                "'CIP-003-6 R5 Part 5.2' is not in the register; matching register refs: CIP-003-8 Attachment 1 Part 5.2"
            ]
            == "not_evidence"
        )
        assert by_quote["CIP-007-6 R2 Violation Severity Levels VSL table"] == "not_evidence"
        assert ok["quote_classes"].get("resolved") == 1

        # Without tool_outputs, the same tool error string is NOT excused by word patterns.
        without = integrity(
            repo, 'The tool returned "no section, address, glossary term or document with that id".'
        )
        assert not without["grounded"]

        # Real faults MUST keep failing: TS5, (35s), [including], summarized quote, and run3 mapping lines.
        for bad_line in (
            '- "At least once every TS5 calendar days, evaluate security patches for applicability"',
            '- "At least once every (35s) calendar days, evaluate security patches for applicability"',
            '- "A patch management process for tracking, evaluating, and installing cyber security patches... [including] the identification of a source or sources"',
            '- "Apply; or Create; or Revise,"',
            '- "The LSPG Security Patch Management Procedure maps CIP-007-6 R2 Part 2.1 to §3.1 Security Patch Management Process"',
        ):
            bad = integrity(repo, bad_line, tool_outputs=tool_outputs)
            assert not bad["grounded"], (bad_line, bad)
    finally:
        repo.close()


def test_inline_dash_bullet_fold_and_unregistered_ref_guidance(tmp_path) -> None:
    import yaml

    from portal.modules.compliance.core import dual_document
    from portal.modules.compliance.core.models import SourceDocument, SourceSection
    from portal.modules.compliance.core.repository import Repository
    from portal.platform.inference.config import effective_workspace
    from scripts.compliance.truth.citation_integrity import integrity

    repo = Repository(tmp_path / "store.db")
    try:
        reg_text = (
            "5.2.1 Use one or a combination of the following prior to connecting the "
            "Transient Cyber Asset to a low impact BES Cyber System (per Transient Cyber "
            "Asset capability):\n"
            "Review of antivirus update level;\n"
            "Review of antivirus update process used by the party;\n"
            "Review use of live operating system and software executable only from read-only media;\n"
            "or\n"
            "Other method(s) to mitigate the introduction of malicious code.\n"
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-003-9",
                title="CIP-003-9",
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        rev = repo.add_document_revision(
            "NERC/CIP-003-9", "CIP-003-9.pdf", reg_text.encode(), binding_effect="regulatory"
        )
        repo.put_document_text(
            rev.revision_id, reg_text, page_count=1, extractor="test", extractor_version="1"
        )
        # Split across adjacent sections, matching how CIP-003-9 stores Part 5.2.1 bullets.
        lines = reg_text.splitlines(keepends=True)
        offset = 0
        for idx, line in enumerate(lines, start=1):
            repo.add_source_section(
                SourceSection(
                    section_id=f"csection-p{idx}",
                    revision_id=rev.revision_id,
                    path=f"Att1-5.2.1-{idx}",
                    heading_path="Attachment 1 Part 5.2.1",
                    title="Part 5.2.1",
                    char_start=offset,
                    char_end=offset + len(line),
                    ordinal=idx,
                )
            )
            offset += len(line)
        repo._conn.execute(
            "INSERT INTO requirement_sections "
            "(requirement_id, section_id, revision_id, relation, char_start, char_end, anchored_at) "
            "VALUES (?, ?, ?, 'governing', ?, ?, '2026-01-01T00:00:00Z')",
            (
                "CIP-003-9 Attachment 1 Part 5.2",
                "csection-p1",
                rev.revision_id,
                0,
                len(reg_text),
            ),
        )
        repo._conn.commit()

        verbatim_dash_quote = (
            '- "Use one or a combination of the following prior to connecting the '
            "Transient Cyber Asset to a low impact BES Cyber System (per Transient Cyber "
            "Asset capability): - Review of antivirus update level; - Review of antivirus "
            "update process used by the party; - Review use of live operating system and "
            "software executable only from read\u2010only media; or - Other method(s) to "
            'mitigate the introduction of malicious code."'
        )
        ok = integrity(repo, verbatim_dash_quote)
        assert ok["grounded"], ok
        assert ok["quotes"][0].get("fold") == "list_separators"

        altered_dash_quote = verbatim_dash_quote.replace("antivirus", "malware")
        bad = integrity(repo, altered_dash_quote)
        assert not bad["grounded"], bad

        unreg = dual_document.build(repo, requirement_ref="CIP-003-6 R5 Part 5.2")
        assert unreg["resolved"] is False
        assert "CIP-003-9 Attachment 1 Part 5.2" in unreg.get("matching_refs", [])
        assert "compliance_context" in str(unreg.get("error", ""))
        assert "matching_refs" in str(unreg.get("error", ""))
    finally:
        repo.close()

    portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
    prompt = effective_workspace(portal["workspaces"], "auto-compliance::reading")[
        "system_prompt_append"
    ]
    assert "matching_refs" in prompt
    assert "Never narrate planned or failed tool calls" in prompt


def test_post_period_outline_and_open_circle_bullet_fold(tmp_path) -> None:
    from portal.modules.compliance.core.models import SourceDocument, SourceSection
    from portal.modules.compliance.core.repository import Repository
    from scripts.compliance.truth.citation_integrity import integrity

    repo = Repository(tmp_path / "store.db")
    try:
        reg_lines = [
            "5.2 For Transient Cyber Asset(s) managed by a party other than the Responsible Entity, if any:\n",
            "5.2.1 Use one or a combination of the following prior to connecting the Transient Cyber Asset:\n",
            "Review of antivirus update level;\n",
            "Review of system hardening used by the party; or\n",
            "Other method(s) to mitigate the introduction of malicious code.\n",
            "5.2.2 For any method used pursuant to 5.2.1, Responsible Entities shall determine whether any additional mitigation actions are necessary.\n",
            "At least once every 35 calendar days, evaluate security patches for applicability. "
            "Apply the applicable patches; or Create a dated mitigation plan; or Revise an existing mitigation plan.\n",
        ]
        reg_text = "".join(reg_lines)
        op_text = (
            "For Transient Cyber Assets managed by a party other than LSPG (e.g. vendor) - Use \n"
            "one or a combination of the following prior to connecting the TCA (Att. 1 Section 5.2): \n"
            "o \nReview of antivirus update level; \n"
            "o \nReview of system hardening used by the party; or \n"
            "o \nOther method(s) to mitigate the introduction of malicious code. \n"
        )
        repo.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-003-8",
                title="CIP-003-8",
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        rev_reg = repo.add_document_revision(
            "NERC/CIP-003-8", "CIP-003-8.pdf", reg_text.encode(), binding_effect="regulatory"
        )
        repo.put_document_text(
            rev_reg.revision_id, reg_text, page_count=1, extractor="test", extractor_version="1"
        )
        offset = 0
        for idx, line in enumerate(reg_lines, start=1):
            repo.add_source_section(
                SourceSection(
                    section_id=f"csection-r{idx}",
                    revision_id=rev_reg.revision_id,
                    path=f"Att1-5.2-{idx}",
                    heading_path="Attachment 1 Part 5.2",
                    title="Part 5.2",
                    char_start=offset,
                    char_end=offset + len(line),
                    ordinal=idx,
                )
            )
            offset += len(line)

        repo.upsert_source_document(
            SourceDocument(
                logical_id="CIP-003/LSPG Policy.pdf",
                title="LSPG Policy",
                issuer="LSPG",
                source_kind="policy",
                jurisdiction="internal",
            )
        )
        rev_op = repo.add_document_revision(
            "CIP-003/LSPG Policy.pdf",
            "LSPG Policy.pdf",
            op_text.encode(),
            binding_effect="internally_mandatory",
        )
        repo.put_document_text(
            rev_op.revision_id, op_text, page_count=1, extractor="test", extractor_version="1"
        )
        repo.add_source_section(
            SourceSection(
                section_id="isection-o1",
                revision_id=rev_op.revision_id,
                path="3.7.4.2",
                heading_path="3.7.4.2",
                title="3.7.4.2",
                char_start=0,
                char_end=len(op_text),
                ordinal=1,
            )
        )

        # Fold gap 1: inline multi-level outline label after sentence-ending period (5.2.2) across contiguous sections.
        q_reg = (
            '- "For Transient Cyber Asset(s) managed by a party other than the Responsible Entity, if any: '
            "5.2.1 Use one or a combination of the following prior to connecting the Transient Cyber Asset: "
            "• Review of antivirus update level; • Review of system hardening used by the party; or "
            "• Other method(s) to mitigate the introduction of malicious code. "
            "5.2.2 For any method used pursuant to 5.2.1, Responsible Entities shall determine whether "
            'any additional mitigation actions are necessary."'
        )
        res_reg = integrity(repo, q_reg)
        assert res_reg["grounded"], res_reg
        assert res_reg["quotes"][0].get("fold") == "list_separators"

        # Fold gap 2: Word/PDF line-leading open-circle 'o' sub-bullets stripped from store text.
        q_op = (
            '- "For Transient Cyber Assets managed by a party other than LSPG (e.g. vendor) - Use '
            "one or a combination of the following prior to connecting the TCA (Att. 1 Section 5.2): "
            "Review of antivirus update level; Review of system hardening used by the party; or "
            'Other method(s) to mitigate the introduction of malicious code."'
        )
        res_op = integrity(repo, q_op)
        assert res_op["grounded"], res_op
        assert res_op["quotes"][0].get("fold") == "list_separators"

        # Real faults MUST keep failing: TS5, (35s), [including], summarized quote, traceability line, altered in-prose ref.
        for bad_line in (
            '- "At least once every TS5 calendar days, evaluate security patches for applicability."',
            '- "At least once every (35s) calendar days, evaluate security patches for applicability."',
            '- "For any method used pursuant to 5.2.1, Responsible Entities shall [including] determine whether any additional mitigation actions are necessary."',
            '- "Apply; or Create; or Revise,"',
            '- "your LSPG Security Patch Management Procedure maps CIP-007-6 R2 Part 2.3 to §3.5 Patch Implementation Process"',
            '- "For any method used pursuant to 5.2.9, Responsible Entities shall determine whether any additional mitigation actions are necessary."',
        ):
            bad = integrity(repo, bad_line)
            assert not bad["grounded"], (bad_line, bad)
    finally:
        repo.close()
