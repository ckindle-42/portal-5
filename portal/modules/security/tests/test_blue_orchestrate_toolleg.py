"""Tests for blue_orchestrate.py's tool section (Retriever) — Slice 2."""

from __future__ import annotations

from portal.modules.security.core import blue_orchestrate as bo
from portal.modules.security.core.agentic_blue_eval import Episode


def _episode(telemetry: dict[str, list[str]]) -> Episode:
    return Episode(
        scenario="asrep_to_lateral",
        target_host="dc01",
        techniques=["T1558.004"],
        telemetry=telemetry,
    )


def test_build_tool_request_defaults_prefer_broad_true() -> None:
    req = bo.build_tool_request("investigate suspicious kerberos activity")
    assert req.prefer_broad is True
    assert req.spec == "investigate suspicious kerberos activity"


def test_dry_run_narrow_empty_broadens_and_tags_live_broad_fallback() -> None:
    ep = _episode({"windows:security": ["EventCode=4768 some AS-REP event"]})
    req = bo.build_tool_request("look for anything unusual")
    result = bo.run_tool_model(req, tool_model="unused", episode=ep, dry_run=True)
    assert result.provenance == "live-broad-fallback"
    assert "4768" in result.raw_summary
    assert "Representative records:" in result.raw_summary


def test_dry_run_prefer_broad_false_stays_empty() -> None:
    ep = _episode({})
    req = bo.ToolRequest(spec="look for anything", window="", prefer_broad=False)
    result = bo.run_tool_model(req, tool_model="unused", episode=ep, dry_run=True)
    assert result.provenance == "empty"
    assert result.rows == []


def test_dry_run_no_telemetry_at_all_stays_empty_even_with_broaden() -> None:
    ep = _episode({})
    req = bo.build_tool_request("look for anything unusual")
    result = bo.run_tool_model(req, tool_model="unused", episode=ep, dry_run=True)
    assert result.provenance == "empty"


def test_broad_preview_is_bounded_and_label_blind() -> None:
    events = [f"EventCode=4688 sequence={i} command=whoami" for i in range(20)]
    preview = bo._broad_retrieval_preview(_episode({"windows:security": events}))
    assert "20 events:" in preview
    assert preview.count("[windows:security]") == bo._BROAD_PREVIEW_EVENT_LIMIT
    assert "T1558.004" not in preview


def test_stringify_query_args_flattens_lists_and_numbers() -> None:
    assert bo._stringify_query_args({"event_ids": [4769, 4776]}) == {"event_ids": "4769 4776"}
    assert bo._stringify_query_args({"n": 5}) == {"n": "5"}
    assert bo._stringify_query_args({"spl_query": "already a string"}) == {
        "spl_query": "already a string"
    }


def test_freetext_narrow_finds_matching_lines_without_eventcode() -> None:
    """Regression: _query_real_telemetry's own keyword extraction is
    Windows-EventCode/technique-ID-centric only — a free-text filter like
    'Tomcat manager interface access' never narrows web/ftp/other log types
    at all (live-verified on meta3_tomcat_manager, 2026-07-17: always fell
    through to the generic cross-sourcetype summary). _freetext_narrow is the
    additive fallback confined to blue_orchestrate.py."""
    ep = _episode(
        {
            "windows:security": [
                "EventCode=4688 NewProcessName=powershell.exe CommandLine=whoami Account=vagrant",
                "EventCode=4624 unrelated logon event",
            ]
        }
    )
    narrowed = bo._freetext_narrow({"filter": "PowerShell process creation command line"}, ep)
    assert narrowed is not None
    assert "powershell.exe" in narrowed
    assert "unrelated logon event" not in narrowed


def test_freetext_narrow_returns_none_when_nothing_matches() -> None:
    ep = _episode({"windows:security": ["EventCode=4624 unrelated logon event"]})
    assert bo._freetext_narrow({"filter": "kerberos ticket roasting"}, ep) is None


def test_retrieval_tool_schemas_excludes_report_detection() -> None:
    schemas = bo._retrieval_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "report_detection" not in names
    assert names == set(bo._RETRIEVAL_TOOL_NAMES)


def test_verdict_prompts_treat_authorized_dual_use_as_counter_evidence() -> None:
    policy = bo._VERDICT_GROUNDING_POLICY
    assert "dual-use primitive" in policy
    assert "change tickets" in policy
    assert "use RULED_OUT" in policy
    assert "could theoretically be abused" in policy
    assert policy in bo._HUNTER_OUTPUT_FORMAT_INSTRUCTIONS
    assert policy in bo._EXPERT_SYSTEM_PROMPT
    assert policy in bo._MERGED_SYSTEM_PROMPT
