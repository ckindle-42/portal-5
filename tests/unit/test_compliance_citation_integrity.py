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


def test_reading_workspace_enforces_tool_call_deterministic_sampling_and_vsl_note() -> None:
    import inspect

    import yaml

    from portal.modules.compliance.core import dual_document
    from portal.platform.inference.config import effective_workspace

    portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
    ws = effective_workspace(portal["workspaces"], "auto-compliance::reading")
    assert ws.get("tool_choice") == "required"
    assert float(ws.get("temperature")) <= 0.3
    override = ws.get("sampling_override") or {}
    assert override.get("reason") and override.get("evidence")
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
