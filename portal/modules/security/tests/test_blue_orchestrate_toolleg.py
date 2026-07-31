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


def test_build_tool_request_defaults_prefer_broad_true():
    req = bo.build_tool_request("investigate suspicious kerberos activity")
    assert req.prefer_broad is True
    assert req.spec == "investigate suspicious kerberos activity"


def test_dry_run_narrow_empty_broadens_and_tags_live_broad_fallback():
    ep = _episode({"windows:security": ["EventCode=4768 some AS-REP event"]})
    req = bo.build_tool_request("look for anything unusual")
    result = bo.run_tool_model(req, tool_model="unused", episode=ep, dry_run=True)
    assert result.provenance == "live-broad-fallback"
    assert "4768" in result.raw_summary
    assert "Representative records:" in result.raw_summary


def test_dry_run_prefer_broad_false_stays_empty():
    ep = _episode({})
    req = bo.ToolRequest(spec="look for anything", window="", prefer_broad=False)
    result = bo.run_tool_model(req, tool_model="unused", episode=ep, dry_run=True)
    assert result.provenance == "empty"
    assert result.rows == []


def test_dry_run_no_telemetry_at_all_stays_empty_even_with_broaden():
    ep = _episode({})
    req = bo.build_tool_request("look for anything unusual")
    result = bo.run_tool_model(req, tool_model="unused", episode=ep, dry_run=True)
    assert result.provenance == "empty"


def test_live_tool_call_dispatches_and_returns_matched_exact(monkeypatch):
    ep = _episode({"windows:security": ["EventCode=4768 AS-REP roasting event for user svc-web"]})

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "query_windows_events",
                        "arguments": {"event_ids": [4768]},
                    }
                }
            ]
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    req = bo.build_tool_request("check AS-REP roasting event 4768")
    result = bo.run_tool_model(req, tool_model="granite4.1:8b-ctx8k", episode=ep)
    assert result.provenance == "matched-exact"
    assert result.rows
    assert result.rows[0]["tool"] == "query_windows_events"
    assert "AS-REP" in result.rows[0]["result"] or "4768" in result.rows[0]["result"]


def test_live_tool_call_ignores_non_retrieval_tool_calls(monkeypatch):
    ep = _episode({"windows:security": ["EventCode=4768 event"]})

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "report_detection",
                        "arguments": {"technique_id": "T1558.004"},
                    }
                }
            ]
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    req = bo.build_tool_request("investigate")
    result = bo.run_tool_model(req, tool_model="m", episode=ep)
    # report_detection is not a retrieval tool -> nothing dispatched from the
    # model's call -> the empty-result path broadens instead (prefer_broad default).
    assert all(r["tool"] != "report_detection" for r in result.rows)
    assert result.provenance == "live-broad-fallback"


def test_targeted_miss_broadens_to_model_visible_raw_evidence(monkeypatch):
    """A non-empty 'No matching' notice is not evidence and must broaden.

    The V5 corpus audit found 11/12 affected raw episodes contained their
    expected discriminator, but the model-visible trace held only this miss
    notice or a count summary.
    """
    ep = _episode(
        {
            "windows:security": [
                "EventCode=4698 TaskName=Updater Account=svc-task",
                "EventCode=4624 unrelated logon",
            ]
        }
    )

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "query_windows_events",
                        "arguments": {"event_ids": [4769]},
                    }
                }
            ]
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    result = bo.run_tool_model(
        bo.build_tool_request("check Kerberos ticket events"),
        tool_model="m",
        episode=ep,
    )
    assert result.provenance == "live-broad-fallback"
    assert "EventCode=4698" in result.raw_summary
    assert "No matching Windows events" not in result.raw_summary


def test_broad_preview_is_bounded_and_label_blind():
    events = [f"EventCode=4688 sequence={i} command=whoami" for i in range(20)]
    preview = bo._broad_retrieval_preview(_episode({"windows:security": events}))
    assert "20 events:" in preview
    assert preview.count("[windows:security]") == bo._BROAD_PREVIEW_EVENT_LIMIT
    assert "T1558.004" not in preview


def test_live_tool_call_with_string_encoded_arguments_does_not_crash(monkeypatch):
    """Regression: granite4.1:8b-ctx8k, live end-to-end (Slice 7), returned
    tool-call `arguments` as a JSON-encoded string instead of a dict,
    crashing _query_real_telemetry's `.values()` call downstream."""
    ep = _episode({"windows:security": ["EventCode=4768 AS-REP roasting event for svc-web"]})

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "query_windows_events",
                        "arguments": '{"event_ids": [4768]}',
                    }
                }
            ]
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    req = bo.build_tool_request("check AS-REP roasting event 4768")
    result = bo.run_tool_model(req, tool_model="granite4.1:8b-ctx8k", episode=ep)
    assert result.provenance == "matched-exact"
    assert result.rows[0]["args"] == {"event_ids": [4768]}


def test_list_valued_event_ids_actually_narrow_the_query(monkeypatch):
    """Regression: query_windows_events's OWN tool schema types event_ids as
    an array of integers, but _query_real_telemetry's keyword extraction only
    scans string-valued query_args — a well-formed structured call therefore
    silently returned the same generic broad summary every round regardless
    of which event_ids were requested (root cause of every live Hunter
    candidate's non-convergence in the Slice 8 pre-screen, 2026-07-17)."""
    ep = _episode(
        {
            "windows:security": [
                "EventCode=4769 kerberos ticket request for svc-web",
                "EventCode=4624 unrelated logon event",
            ]
        }
    )

    def fake_call_model(model, messages, tools=None, max_tokens=2000, extra_options=None):
        return {
            "tool_calls": [
                {"function": {"name": "query_windows_events", "arguments": {"event_ids": [4769]}}}
            ]
        }

    monkeypatch.setattr(bo, "_call_model", fake_call_model)
    req = bo.build_tool_request("give me AS-REP roasting events")
    result = bo.run_tool_model(req, tool_model="m", episode=ep)
    assert result.provenance == "matched-exact"
    assert "4769" in result.rows[0]["result"]
    assert "4624" not in result.rows[0]["result"]  # narrowed, not the generic broad summary


def test_stringify_query_args_flattens_lists_and_numbers():
    assert bo._stringify_query_args({"event_ids": [4769, 4776]}) == {"event_ids": "4769 4776"}
    assert bo._stringify_query_args({"n": 5}) == {"n": "5"}
    assert bo._stringify_query_args({"spl_query": "already a string"}) == {
        "spl_query": "already a string"
    }


def test_freetext_narrow_finds_matching_lines_without_eventcode():
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


def test_freetext_narrow_returns_none_when_nothing_matches():
    ep = _episode({"windows:security": ["EventCode=4624 unrelated logon event"]})
    assert bo._freetext_narrow({"filter": "kerberos ticket roasting"}, ep) is None


def test_dispatch_tool_call_falls_back_to_freetext_when_broad_summary(monkeypatch):
    ep = _episode(
        {
            "web:access": [
                "10.10.11.13 POST /manager/html deploy war payload.jsp 200",
                "10.10.11.13 GET / 200 unrelated",
            ]
        }
    )
    result = bo._dispatch_tool_call("query_web_logs", {"filter": "manager deploy war"}, ep)
    assert "manager/html" in result
    assert "unrelated" not in result


def test_retrieval_tool_schemas_excludes_report_detection():
    schemas = bo._retrieval_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "report_detection" not in names
    assert names == set(bo._RETRIEVAL_TOOL_NAMES)


def test_verdict_prompts_treat_authorized_dual_use_as_counter_evidence():
    policy = bo._VERDICT_GROUNDING_POLICY
    assert "dual-use primitive" in policy
    assert "change tickets" in policy
    assert "use RULED_OUT" in policy
    assert "could theoretically be abused" in policy
    assert policy in bo._HUNTER_OUTPUT_FORMAT_INSTRUCTIONS
    assert policy in bo._EXPERT_SYSTEM_PROMPT
    assert policy in bo._MERGED_SYSTEM_PROMPT
