"""The tool-surface proxy: a production prompt may name a tool the eval scope does not
serve (ready4_mellum_20261105 fed Mellum "ERROR: unknown tool explore_repository" on 8/16
tasks while kat, which ignored the instruction, was unpenalized). The harness answers such
calls with a defined, namespace-scoped result and records the proxy in the row."""

from __future__ import annotations

import json

import pytest

from tests.wfe import campaign, eval_mode, runner
from tests.wfe.runner import Sandbox, workspace_context

FAST_REPAIR = "auto-coding::fast-repair"


@pytest.fixture
def out_root(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path / "AI_Output")
    return tmp_path / "AI_Output"


def _prepare_fast_repair(out_root, task):
    wsc = workspace_context(FAST_REPAIR)
    return eval_mode.prepare(
        True,
        {"run_id": f"{FAST_REPAIR}|m|s|t|r0", "workspace": FAST_REPAIR},
        {"campaign_id": "c"},
        task,
        wsc,
        {},
    )


def test_prepare_serves_the_prompt_named_tool_the_allowlist_lacks(out_root):
    task, _wsc, ctx = _prepare_fast_repair(out_root, {"id": "t"})
    assert "explore_repository" in ctx["proxy_fns"]
    assert ctx["proxy_tools"] == sorted(ctx["proxy_fns"])
    assert task["_eval"] is ctx


def test_a_sandbox_row_gets_no_proxy(out_root):
    _, _, ctx = eval_mode.prepare(
        True,
        {"run_id": "auto-coding|m|s|t|r0", "workspace": "auto-coding", "tool_mode": "sandbox"},
        {"campaign_id": "c"},
        {"id": "t"},
        {"system_prompt_pipeline": "p", "system_prompt_base": "b"},
        {},
    )
    assert ctx["production"] is False and "proxy_fns" not in ctx


def test_explore_repository_is_no_more_helpful_than_production(out_root):
    """Production's explorer cannot see uploads, so even a query that names the staged file's
    content returns no citations — the proxy must not hand the arm a capability users lack."""
    task = {"id": "t", "seed": {"notes.txt": "ship it\nTODO fix the parser\nclean line\n"}}
    _, _, ctx = _prepare_fast_repair(out_root, task)
    out = json.loads(ctx["proxy_fns"]["explore_repository"]({"query": "where are TODO lines"}))
    assert out["model"] == "wfe_eval_namespace_proxy" and out["citations"] == []
    assert "/workspace/uploads" in out["note"]


def test_explore_repository_rejects_arguments_like_production(out_root):
    _, _, ctx = _prepare_fast_repair(out_root, {"id": "t"})
    answer = ctx["proxy_fns"]["explore_repository"]
    rejected = json.loads(answer({"path": "/workspace/uploads/realuse_v1/ru-v1-046/notes.txt"}))
    assert rejected["error"] == "Tool 'explore_repository' rejected the arguments"
    assert "unexpected keyword argument(s) ['path']" in rejected["detail"]
    missing = json.loads(answer({}))
    assert "missing required argument(s) ['query']" in missing["detail"]


def test_an_unmatched_query_matches_production_for_out_of_repo_material(out_root):
    _, _, ctx = _prepare_fast_repair(out_root, {"id": "t"})
    out = json.loads(ctx["proxy_fns"]["explore_repository"]({"query": "zzz_nothing_matches"}))
    assert out["citations"] == [] and "not part of the repository" in out["note"]


def test_a_named_tool_without_a_handler_gets_a_defined_not_served_result(out_root):
    """The default is a defined payload naming the tool — never the sandbox's 'unknown tool'."""
    _, _, ctx = _prepare_fast_repair(out_root, {"id": "t"})
    out = json.loads(ctx["proxy_fns"]["remember"]({}))
    assert out["error"].startswith("Tool 'remember' is declared by the workspace")
    assert "not served by this evaluation's tool surface" in out["error"]


def test_sandbox_dispatch_serves_the_proxy_and_marks_the_log(tmp_path):
    sb = Sandbox(tmp_path, proxy={"explore_repository": lambda a: json.dumps({"citations": []})})
    assert sb.dispatch("explore_repository", {}) == '{"citations": []}'
    assert sb.dispatch("nope", {}) == "ERROR: unknown tool nope"
    calls = [{"function": {"name": "explore_repository", "arguments": json.dumps({"query": "x"})}}]
    log: list = []
    errors = runner._execute_calls(calls, 0, sb, log, [])
    assert log[0]["proxy"] is True and log[0]["error"] is False and errors == 0


def test_a_proxied_error_payload_counts_as_a_tool_error(tmp_path):
    sb = Sandbox(
        tmp_path, proxy={"remember": lambda a: json.dumps({"error": "not served in this eval"})}
    )
    log: list = []
    errors = runner._execute_calls(
        [{"function": {"name": "remember", "arguments": "{}"}}], 0, sb, log, []
    )
    assert log[0]["proxy"] is True and log[0]["error"] is True and errors == 1


def test_run_task_hands_the_row_proxy_to_its_sandbox(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(runner, "chat", boom)
    sb = Sandbox(tmp_path / "sb")
    proxy = {"explore_repository": lambda a: "{}"}
    out = runner.run_task(
        "m", "sp", {"id": "t", "instruction": "x", "_eval": {"proxy_fns": proxy}}, sb, 1, 30, True
    )
    assert sb.proxy == proxy and out["outcome"] == "HARNESS_ERROR"


def test_prompt_surface_report_passes_the_proxied_workspace(tmp_path):
    plan = tmp_path / "p.yaml"
    plan.write_text(
        f"workloads:\n  {FAST_REPAIR}:\n    tool_mode: production\n    home: s\n    discovery: []\n"
    )
    checked, failures = campaign.prompt_tool_surface_report(plan)
    assert checked == 1 and not any(FAST_REPAIR in f for f in failures)


def test_prompt_surface_report_fails_naming_workspace_and_tool(tmp_path, monkeypatch):
    plan = tmp_path / "p.yaml"
    plan.write_text(
        f"workloads:\n  {FAST_REPAIR}:\n    tool_mode: production\n    home: s\n    discovery: []\n"
    )
    monkeypatch.setattr(eval_mode, "PROXY_TOOLS", {})
    checked, failures = campaign.prompt_tool_surface_report(plan)
    assert checked == 1
    assert failures == [
        f"workspace {FAST_REPAIR}: prompt names tool(s) not served: ['explore_repository']"
    ]


def test_the_preflight_refuses_a_plan_whose_prompt_names_an_unserved_tool(tmp_path, monkeypatch):
    plan = tmp_path / "p.yaml"
    plan.write_text(
        f"workloads:\n  {FAST_REPAIR}:\n    tool_mode: production\n    home: s\n    discovery: []\n"
    )
    monkeypatch.setattr(eval_mode, "PROXY_TOOLS", {})
    with pytest.raises(campaign.GateRefused) as exc:
        campaign._realuse_tool_preflight(plan)
    assert FAST_REPAIR in str(exc.value) and "explore_repository" in str(exc.value)


def test_the_preflight_passes_committed_plans_that_serve_their_prompts():
    campaign._realuse_tool_preflight(campaign.REPO / "tests/wfe/plans/decision_run_v1.yaml")
    campaign._realuse_tool_preflight(campaign.REPO / "tests/wfe/plans/realuse_v1_s8.yaml")


def test_finish_records_the_proxied_tools_in_the_row_evidence(out_root, tmp_path):
    _, _, ctx = _prepare_fast_repair(out_root, {"id": "t"})
    row = {"run_id": "r", "workspace": FAST_REPAIR}
    out = eval_mode.finish(ctx, {"outcome": "PASS", "evidence": {}}, tmp_path, row)
    assert "explore_repository" in out["evidence"]["proxied_tools"]
