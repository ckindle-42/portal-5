"""Production tool mode serves the tools a production prompt names.

execute_python is a real sandbox call under the row scope. web_search is a real
SearXNG read, and the query is stored on the row. A tool that cannot run without
the operator store or an unscoped write returns a defined payload and the row is
BLOCKED — excluded from scoring, not FAIL.
"""

from __future__ import annotations

import ast
import json
import urllib.error

import pytest

from tests.wfe import campaign, eval_mode, runner
from tests.wfe import production_surface as surface
from tests.wfe.checkers import CheckContext
from tests.wfe.runner import workspace_context

CAD = "auto-coding::cad"
SECURITY = "auto-security"
COMPLIANCE = "auto-compliance"


@pytest.fixture
def out_root(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path / "AI_Output")
    return tmp_path / "AI_Output"


def _prepare(out_root, workspace: str, task: dict | None = None):
    return eval_mode.prepare(
        True,
        {"run_id": f"{workspace}|m|s|t|r0", "workspace": workspace},
        {"campaign_id": "c"},
        task or {"id": "t"},
        workspace_context(workspace),
        {},
    )


def test_the_named_tools_are_on_the_proxy_surface():
    for name in (
        "execute_python",
        "web_search",
        *surface.UNSAFE_REASONS,
    ):
        assert name in eval_mode.PROXY_TOOLS


def test_parameter_lists_track_the_production_signatures():
    """Importing the sandbox module creates data/sandbox, so the lock reads source."""
    repo = campaign.REPO

    def params(path: str, name: str) -> tuple[str, ...]:
        tree = ast.parse((repo / path).read_text())
        fn = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name
        )
        return tuple(arg.arg for arg in fn.args.args)

    assert params("portal/modules/coding/tools/code_sandbox_mcp.py", "execute_python") == (
        surface.EXECUTE_PYTHON_PARAMS
    )
    assert params("portal/modules/research/tools/web_search_mcp.py", "web_search") == (
        surface.WEB_SEARCH_PARAMS
    )


def test_execute_python_calls_the_sandbox_with_the_row_scope(out_root, monkeypatch):
    seen: dict = {}

    def fake(url: str, name: str, arguments: dict, scope: dict) -> dict:
        seen.update(url=url, name=name, arguments=arguments, scope=scope)
        return {"success": True, "stdout": "3"}

    monkeypatch.setattr(surface, "scoped_mcp_call", fake)
    _, _, ctx = _prepare(out_root, CAD)
    out = json.loads(ctx["proxy_fns"]["execute_python"]({"code": "print(1+2)"}))
    assert out["stdout"] == "3"
    assert seen["name"] == "execute_python"
    assert seen["arguments"] == {"code": "print(1+2)"}
    assert seen["scope"] == ctx["scope"]
    assert seen["url"].startswith("http://localhost:")
    assert "scoring_excluded" not in ctx


def test_execute_python_rejects_bad_arguments_without_calling(out_root, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("sandbox was called")

    monkeypatch.setattr(surface, "scoped_mcp_call", boom)
    _, _, ctx = _prepare(out_root, CAD)
    rejected = json.loads(ctx["proxy_fns"]["execute_python"]({"path": "/tmp/x"}))
    assert rejected["error"] == "Tool 'execute_python' rejected the arguments"
    assert "unexpected keyword argument(s) ['path']" in rejected["detail"]
    missing = json.loads(ctx["proxy_fns"]["execute_python"]({}))
    assert "missing required argument(s) ['code']" in missing["detail"]


def test_an_unreachable_sandbox_excludes_the_row(out_root, monkeypatch):
    def down(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(surface, "scoped_mcp_call", down)
    _, _, ctx = _prepare(out_root, CAD)
    out = json.loads(ctx["proxy_fns"]["execute_python"]({"code": "print(1)"}))
    assert out["excluded_from_scoring"] is True
    assert ctx["scoring_excluded"][0]["tool"] == "execute_python"


def test_web_search_records_the_query_and_returns_searxng(out_root, monkeypatch):
    def fake(query: str, num_results: int, time_range: str) -> dict:
        assert (query, num_results, time_range) == ("cip-007", 3, "week")
        return {"query": query, "num_results": 1, "results": [{"title": "CIP"}]}

    monkeypatch.setattr(surface, "searxng_search", fake)
    _, _, ctx = _prepare(out_root, SECURITY)
    out = json.loads(
        ctx["proxy_fns"]["web_search"]({"query": "cip-007", "num_results": 3, "time_range": "week"})
    )
    assert out["results"][0]["title"] == "CIP"
    assert ctx["web_search_queries"] == ["cip-007"]
    assert "scoring_excluded" not in ctx


def test_an_unreachable_searxng_still_records_the_query_and_excludes(out_root, monkeypatch):
    def down(*_a, **_k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(surface, "searxng_search", down)
    _, _, ctx = _prepare(out_root, SECURITY)
    out = json.loads(ctx["proxy_fns"]["web_search"]({"query": "cve-2024-1"}))
    assert out["excluded_from_scoring"] is True
    assert ctx["web_search_queries"] == ["cve-2024-1"]
    assert ctx["scoring_excluded"][0]["tool"] == "web_search"


def test_unsafe_tools_are_a_defined_exclusion_not_a_scored_failure(out_root):
    task = {
        "id": "t",
        "instruction": "x",
        "checker": {"type": "answer_contains", "patterns": ["missing-token"]},
    }
    task, _, ctx = _prepare(out_root, COMPLIANCE, task)
    for name in (
        "compliance_ask",
        "compliance_context",
        "compliance_conflicts",
        "compliance_review_decide_batch",
        "compliance_review_list",
    ):
        payload = json.loads(ctx["proxy_fns"][name]({}))
        assert payload["excluded_from_scoring"] is True
        assert payload["error"].startswith(f"Tool '{name}' is not executed")
    cad_task, _, cad = _prepare(out_root, CAD, {"id": "t"})
    for name in ("generate_part", "render_openscad"):
        payload = json.loads(cad["proxy_fns"][name]({}))
        assert payload["excluded_from_scoring"] is True
    # The checker would FAIL. The row must not be scored as a model failure.
    outcome, notes, evidence = runner._classify(
        task, CheckContext(final_text="no", task=task), [], None, [], 0
    )
    assert outcome is runner.Outcome.BLOCKED
    assert outcome is not runner.Outcome.FAIL
    assert "excluded from scoring" in notes
    assert {item["tool"] for item in evidence["scoring_excluded"]} >= {
        "compliance_ask",
        "compliance_context",
        "compliance_conflicts",
        "compliance_review_decide_batch",
        "compliance_review_list",
    }
    # A checker PASS is excluded too: the stub must not count as a real tool result.
    passing = {**cad_task, "checker": {"type": "answer_contains"}}
    passed, _, _ = runner._classify(
        passing, CheckContext(final_text="done", task=passing), [], None, [], 0
    )
    assert passed is runner.Outcome.BLOCKED


def test_finish_persists_queries_and_blocks_a_row_the_runner_left_as_fail(out_root, tmp_path):
    _, _, ctx = _prepare(out_root, SECURITY)
    ctx["web_search_queries"] = ["cip-007"]
    ctx["scoring_excluded"] = [{"tool": "web_search", "reason": "SearXNG unreachable: down"}]
    row = {"run_id": "r", "workspace": SECURITY}
    out = eval_mode.finish(
        ctx, {"outcome": "FAIL", "notes": "answer missing", "evidence": {}}, tmp_path, row
    )
    assert out["outcome"] == "BLOCKED"
    assert out["evidence"]["web_search_queries"] == ["cip-007"]
    assert out["evidence"]["scoring_excluded"][0]["tool"] == "web_search"


def test_fast_repair_explore_step_sends_uploads_to_execute_bash():
    append = workspace_context("auto-coding::fast-repair")["system_prompt_append"]
    assert "ls, cat, rg under /workspace/uploads" in append
    assert "Call explore_repository only" in append
    assert "call explore_repository('what you need to find') first" not in append
    assert "2. READ:" in append and "6. REPORT:" in append
    other = workspace_context("auto-coding::uncensored-agentic")["system_prompt_append"]
    assert "call explore_repository('what you need to find') first" in other


def test_requests_offer_the_production_schemas_for_compliance_and_security(out_root):
    """Offered prompt-named tools equal the workspace's production list of those tools."""
    import yaml

    from portal.platform.inference.tool_registry import ToolDefinition

    portal = yaml.safe_load((campaign.REPO / "config/portal.yaml").read_text())
    modes = yaml.safe_load((campaign.REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    raw = json.loads(
        (campaign.REPO / "config/inference/tools_manifest_compliance_mcp.json").read_text()
    )
    entry = next(item["function"] for item in raw if item["function"]["name"] == "compliance_ask")
    rendered = ToolDefinition(
        name=entry["name"],
        description=entry["description"],
        parameters=entry["parameters"],
        server_id="compliance",
        server_url="",
    ).to_openai_tool()
    assert surface.production_schema("compliance_ask") == rendered
    for workspace in (COMPLIANCE, SECURITY):
        _task, wsc, ctx = _prepare(out_root, workspace)
        declared = list(portal["workspaces"][workspace]["tools"])
        allow = list(modes[workspace]["allow"])
        production = sorted(set(declared) & set(surface.PROMPT_NAMED_TOOLS))
        offered = sorted(set(wsc["tool_surface"]) & set(surface.PROMPT_NAMED_TOOLS))
        assert offered == production
        request_names = [t["function"]["name"] for t in ctx["offered_schemas"]]
        assert request_names == sorted(set(production) - set(allow))
        assert ctx["offered_schemas"] == surface.offered_schemas(declared, allow)
        _, payload, _ = runner._build_pipeline(
            workspace,
            [{"role": "user", "content": "q"}],
            "none",
            {},
            ctx["offered_schemas"],
            "default",
            False,
            None,
            ctx["scope"],
        )
        assert payload["tools"] == ctx["offered_schemas"]
        assert "portal_client_tools_only" not in payload
        assert payload["portal_eval"]["allow"] == sorted(allow)
        assert set(request_names) <= set(ctx["proxy_fns"])
        wired = [t["function"]["name"] for t in runner._request_schemas(wsc["tool_surface"], _task)]
        assert request_names == [name for name in wired if name in surface.PROMPT_NAMED_TOOLS]


def test_web_search_schema_is_the_research_tools_list_schema():
    import asyncio

    from portal.modules.research.tools.web_search_mcp import mcp
    from portal.platform.inference.tool_registry import ToolDefinition

    tool = next(item for item in asyncio.run(mcp.list_tools()) if item.name == "web_search")
    rendered = ToolDefinition(
        name=tool.name,
        description=tool.description or "",
        parameters=dict(tool.input_schema),
        server_id="research",
        server_url="",
    ).to_openai_tool()
    assert surface.production_schema("web_search") == rendered


def test_every_committed_plan_serves_the_tools_its_prompt_names():
    failures = []
    plans = sorted((campaign.REPO / "tests/wfe/plans").glob("*.yaml"))
    assert plans
    for plan in plans:
        _checked, bad = campaign.prompt_tool_surface_report(plan)
        failures.extend(f"{plan.name}: {item}" for item in bad)
    assert failures == []
