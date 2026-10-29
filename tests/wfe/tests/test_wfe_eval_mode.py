"""Production tool mode (root-fix Part 2a): tokens, staging, receipts, cleanup, payload, gate."""

from __future__ import annotations

import contextlib
import json

import pytest

from portal.platform.mcp_host import eval_scope as es
from tests.wfe import campaign, eval_mode, runner


@pytest.fixture
def out_root(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path / "AI_Output")
    monkeypatch.setattr(eval_mode, "close_data_session", lambda scope: None)
    return tmp_path / "AI_Output"


def _row(rid="auto-documents|hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k@card-1|s|t|r0"):
    return {"run_id": rid, "workspace": "auto-documents"}


def test_tokens_are_valid_distinct_and_deterministic():
    ids = ["w|hf.co/a/B:Q4|s|t|r0", "w|hf.co/a/B:Q4|s|t|r1", "w|x" + "y" * 300 + "|s|t|r0"]
    toks = [eval_mode.tokens("camp-1", i) for i in ids]
    assert all(es.TOKEN.match(c) and es.TOKEN.match(r) for c, r in toks)
    assert len({r for _, r in toks}) == 3 and toks[0] == eval_mode.tokens("camp-1", ids[0])


def test_prepare_scopes_the_row_and_drops_the_harness_note(out_root):
    h, wsc = (
        {},
        {
            "system_prompt_pipeline": "base + NOTE",
            "system_prompt_base": "base",
            "tool_surface": ["file_read"],
        },
    )
    task = {"id": "t", "seed": {"q.csv": "a\n1\n"}}
    t2, w2, ctx = eval_mode.prepare(True, _row(), {"campaign_id": "c"}, task, wsc, h)
    assert h["pipeline_eval"]["allow"] == sorted(eval_mode.mode_for("auto-documents")["allow"])
    assert w2["system_prompt_pipeline"] == "base" and "file_read" not in w2["tool_surface"]
    assert (ctx["root"] / "in" / "q.csv").read_text() == "a\n1\n" and t2["_eval"] is ctx
    assert eval_mode.prepare(False, _row(), {"campaign_id": "c"}, task, wsc, {})[2] is None
    sandbox = eval_mode.prepare(
        True,
        {**_row(), "workspace": "auto-coding", "tool_mode": "sandbox"},
        {"campaign_id": "c"},
        task,
        wsc,
        {},
    )
    assert sandbox[2]["production"] is False and sandbox[2]["scope"]["allow"] == []


def test_receipts_reject_preexisting_changed_and_outside_files(out_root):
    _, _, ctx = eval_mode.prepare(
        True,
        _row(),
        {"campaign_id": "c"},
        {"id": "t", "seed": {"old.docx": "x"}},
        {"system_prompt_pipeline": "", "system_prompt_base": ""},
        {},
    )
    out = ctx["root"] / "out"
    out.mkdir()
    good, changed = out / "good.docx", out / "changed.docx"
    for f in (good, changed):
        f.write_bytes(b"doc")
        es.receipt(eval_mode.OUTPUT_ROOT, ctx["scope"], "Document", f)
    changed.write_bytes(b"tampered")
    with (ctx["root"] / ".receipts.jsonl").open("a") as fh:
        fh.write(
            json.dumps(
                {"tool": "x", "path": str(ctx["root"] / "in" / "old.docx"), "sha256": "", "size": 1}
            )
            + "\n"
        )
    v = {r["path"].rsplit("/", 1)[-1]: r["valid"] for r in eval_mode.receipts(ctx)}
    assert v == {
        "good.docx": True,
        "changed.docx": "changed after creation",
        "old.docx": "outside out/ or missing",
    }


def test_finish_keeps_receipted_artifacts_and_cleans_only_the_row(out_root, tmp_path):
    foreign = out_root / "wfe" / ("wfe_" + "f" * 16) / "keep.txt"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("other campaign")
    (out_root / "operator.docx").write_text("operator file")
    r = _row()
    _, _, ctx = eval_mode.prepare(
        True,
        r,
        {"campaign_id": "c"},
        {"id": "t"},
        {"system_prompt_pipeline": "", "system_prompt_base": ""},
        {},
    )
    (ctx["root"] / "out").mkdir()
    f = ctx["root"] / "out" / "r.docx"
    f.write_bytes(b"doc")
    es.receipt(eval_mode.OUTPUT_ROOT, ctx["scope"], "Document", f)
    cd = tmp_path / "campaign"
    out = eval_mode.finish(ctx, {"outcome": "PASS", "evidence": {}}, cd, r)
    assert (
        out["evidence"]["tool_mode"] == "production"
        and out["evidence"]["receipts"][0]["valid"] is True
    )
    assert not ctx["root"].parent.exists() and (out_root / "wfe").is_dir()
    assert list((cd / "artifacts").rglob("r.docx")) and not ctx["root"].exists()
    assert foreign.exists() and (out_root / "operator.docx").exists()
    assert json.loads((cd / "cleanup" / f"{ctx['scope']['run']}.json").read_text())["files"]


def test_pipeline_payload_carries_the_scope_and_no_sandbox_tools():
    scope = {"campaign": "wfe_" + "a" * 16, "run": "wfe_" + "b" * 40, "allow": ["run_sql"]}
    _, payload, _ = runner._build_pipeline(
        "auto-research::data",
        [{"role": "user", "content": "q"}],
        "none",
        {},
        None,
        "default",
        False,
        None,
        scope,
    )
    assert (
        payload["portal_eval"] == scope
        and "tools" not in payload
        and "portal_client_tools_only" not in payload
    )


def test_gate_checks_production_rows_against_the_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    suite = tmp_path / "s.jsonl"
    suite.write_text(
        json.dumps(
            {
                "id": "t1",
                "instruction": "i",
                "requires_tools": ["run_sql"],
                "checks": [{"type": "answer_contains", "patterns": ["x"]}],
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "t2",
                "instruction": "i",
                "requires_tools": ["web_search"],
                "checks": [{"type": "answer_contains", "patterns": ["x"]}],
            }
        )
        + "\n"
    )
    rows = [
        {
            "run_id": f"auto-research::data|a|s|{t}|r0",
            "workspace": "auto-research::data",
            "suite": "s",
            "suite_path": str(suite),
            "task_id": t,
            "overrides": {},
        }
        for t in ("t1", "t2")
    ]
    assert campaign.tool_gaps(rows) == [
        "s:t2 in auto-research::data: needs tools not offered ['web_search']"
    ]


def test_a_pipeline_call_without_tools_says_so():
    msgs = [{"role": "user", "content": "Reply with the word ready."}]
    _, p, _ = runner._build_pipeline(
        "auto-compliance", msgs, "none", {}, None, "default", False, "m"
    )
    assert p.get("portal_no_tools") is True and "tools" not in p
    _, p, _ = runner._build_pipeline(
        "auto-compliance",
        msgs,
        "none",
        {},
        [{"function": {"name": "file_read"}}],
        "default",
        False,
        "m",
    )
    assert p.get("portal_client_tools_only") is True and "portal_no_tools" not in p


def test_a_receipt_from_a_container_view_is_resolved_on_the_host(out_root):
    """The documents MCP runs in Docker: its receipt path is /app/data/generated/wfe/...;
    the harness must resolve the receipt's run-relative `rel` against its own root."""
    _, _, ctx = eval_mode.prepare(
        True,
        _row(),
        {"campaign_id": "c"},
        {"id": "t"},
        {"system_prompt_pipeline": "", "system_prompt_base": ""},
        {},
    )
    (ctx["root"] / "out").mkdir()
    f = ctx["root"] / "out" / "r.docx"
    f.write_bytes(b"doc")
    rec = es.receipt(eval_mode.OUTPUT_ROOT, ctx["scope"], "Document", f)
    rec["path"] = "/app/data/generated/wfe/container_view/" + rec["rel"]
    (ctx["root"] / ".receipts.jsonl").write_text(json.dumps(rec) + "\n")
    [got] = eval_mode.receipts(ctx)
    assert got["valid"] is True and got["host_path"] == str(f.resolve())


def test_settings_resolve_like_the_services(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nexport AI_OUTPUT_DIR='/srv/ai'\nOTHER=1\n")
    monkeypatch.delenv("AI_OUTPUT_DIR", raising=False)
    assert eval_mode.setting("AI_OUTPUT_DIR", "/srv/x/AI_Output", env) == "/srv/ai"
    monkeypatch.setenv("AI_OUTPUT_DIR", "/from/env")
    assert eval_mode.setting("AI_OUTPUT_DIR", "/srv/x/AI_Output", env) == "/from/env"
    assert eval_mode.setting("MISSING", "dflt", env) == "dflt"


def test_a_sandbox_row_gets_an_empty_scope_and_its_stores_cleaned(out_root, monkeypatch):
    calls = []
    monkeypatch.setattr(
        eval_mode, "eval_post", lambda url, body: calls.append(url.rsplit("/", 2)[-2:]) or None
    )
    h = {}
    wsc = {"system_prompt_pipeline": "p", "system_prompt_base": "b", "tool_surface": ["file_read"]}
    task, w2, ctx = eval_mode.prepare(
        True,
        {**_row(), "workspace": "auto-coding", "tool_mode": "sandbox"},
        {"campaign_id": "c"},
        {"id": "t"},
        wsc,
        h,
    )
    assert h["pipeline_eval"]["allow"] == [] and w2 is wsc and ctx["production"] is False
    out = eval_mode.finish(ctx, {"outcome": "PASS", "evidence": {}}, out_root, _row())
    assert out["evidence"]["tool_mode"] == "sandbox" and out["outcome"] == "PASS"
    assert calls.count(["eval", "forget_scope"]) == 2 and calls.count(["eval", "drop_kb"]) == 2


def test_production_seeds_memory_and_kb_and_a_seed_failure_is_an_instrument_error(
    out_root, monkeypatch
):
    calls = []

    def post(url, body):
        calls.append((url.rsplit("/", 2)[-2:], body.get("eval", {}).get("run")))
        return "embedder down" if url.endswith("/tools/remember") and fail else None

    monkeypatch.setattr(eval_mode, "eval_post", post)
    task = {"id": "t", "memory_seed": ["a fact", "another"], "kb_seed": {"k.md": "kb text"}}
    wsc = {"system_prompt_pipeline": "", "system_prompt_base": ""}
    row = {**_row(), "workspace": "auto-research::data"}
    for fail in (False, True):
        calls.clear()
        _, _, ctx = eval_mode.prepare(True, row, {"campaign_id": "c"}, task, wsc, {})
        run = ctx["scope"]["run"]
        if not fail:
            assert (
                calls.count((["tools", "remember"], run)) == 2
                and (["eval", "seed_kb"], run) in calls
            )
        out = eval_mode.finish(ctx, {"outcome": "PASS", "evidence": {}}, out_root, row)
        assert (out["outcome"] == "HARNESS_ERROR") is fail


@pytest.mark.parametrize(
    ("ws", "task", "tools_on", "allow_empty"),
    [
        ("auto-coding", {"id": "t"}, True, True),
        ("auto-coding", {"id": "t", "no_tools": True}, False, True),
        ("auto-documents", {"id": "t"}, False, False),
    ],
)
def test_run_row_keeps_sandbox_tools_and_sends_the_scope(
    tmp_path, monkeypatch, out_root, ws, task, tools_on, allow_empty
):
    from tests.wfe.runner import workspace_context

    class SentError(Exception):
        pass

    seen = {}

    def fake_run_task(*a, **k):
        seen.update(k)
        raise SentError

    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(campaign, "make_sandbox", lambda *a, **k: None)
    monkeypatch.setattr(campaign, "run_task", fake_run_task)
    wsc = workspace_context(ws)
    row = {
        "run_id": f"{ws}|m|s|t|r0",
        "workspace": ws,
        "arm": wsc["model"],
        "arm_role": "incumbent",
        "suite": "s",
        "task_id": "t",
        "repeat": 0,
        "overrides": {},
        **({"tool_mode": "sandbox"} if ws == "auto-coding" else {}),
    }
    with contextlib.suppress(Exception):  # the fake raises, or run_row records it
        campaign.run_row(
            tmp_path, {"campaign_id": "c", "env": {}}, row, wsc, task, 1, 1, None, False
        )
    assert seen["use_tools"] is tools_on
    assert (seen["harness"]["pipeline_eval"]["allow"] == []) is allow_empty


def test_mcp_addresses_follow_the_deployments_host_ports(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("MEMORY_MCP_HOST_PORT=18920\n")
    monkeypatch.setattr(eval_mode, "REPO", tmp_path)
    monkeypatch.delenv("WFE_MEMORY_MCP_URL", raising=False)
    monkeypatch.delenv("MEMORY_MCP_HOST_PORT", raising=False)
    real = eval_mode.setting
    monkeypatch.setattr(eval_mode, "setting", lambda k, d, env_file=env: real(k, d, env_file))
    assert (
        eval_mode.mcp_url("WFE_MEMORY_MCP_URL", "MEMORY_MCP_HOST_PORT", 8920)
        == "http://localhost:18920"
    )
    monkeypatch.setenv("WFE_MEMORY_MCP_URL", "http://mem:1/")
    assert eval_mode.mcp_url("WFE_MEMORY_MCP_URL", "MEMORY_MCP_HOST_PORT", 8920) == "http://mem:1"


def test_every_production_allowlist_is_the_workspaces_own_tools():
    """An allowlist can only narrow a workspace's real tools; auto-compliance's must also be
    tools proven safe on the compliance evaluation instance."""
    import yaml

    from portal.modules.compliance.core.eval_instance import VERIFIED_TOOLS
    from portal.platform.inference.config import effective_workspace

    ws = yaml.safe_load((eval_mode.REPO / "config/portal.yaml").read_text())["workspaces"]
    modes = yaml.safe_load(eval_mode.TOOL_MODES.read_text())["workspaces"]
    for name, m in modes.items():
        assert set(m["allow"]) <= set(effective_workspace(ws, name).get("tools") or []), name
    assert (
        modes["auto-compliance"]["allow"]
        and set(modes["auto-compliance"]["allow"]) <= VERIFIED_TOOLS
    )


def _plan_with(tmp_path, ws, mode, home="compliance_agentic_full"):
    p = tmp_path / "plan.yaml"
    mode_line = f"    tool_mode: {mode}\n" if mode else ""
    p.write_text(
        f"workloads:\n  {ws}:\n{mode_line}    home: {home}\n    discovery: []\n"
        "    arms: {incumbent: hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k, challengers: []}\n"
    )
    return p


def test_a_plan_chooses_the_tool_mode_and_bad_choices_fail_at_expansion(tmp_path):
    rows = campaign.expand_matrix(_plan_with(tmp_path, "auto-compliance", "sandbox"), 1)
    assert rows and {r["tool_mode"] for r in rows} == {"sandbox"}
    assert eval_mode.mode_for("auto-compliance", "sandbox") is None
    assert eval_mode.mode_for("auto-compliance")["tool_mode"] == "production"
    with pytest.raises(ValueError, match="sandbox or production"):
        campaign.expand_matrix(_plan_with(tmp_path, "auto-compliance", "both"), 1)
    with pytest.raises(ValueError, match="no allowlist"):
        campaign.expand_matrix(
            _plan_with(tmp_path, "auto-no-production-tools", "production", home="research"), 1
        )


def test_the_gate_refuses_packet_tasks_in_production_and_allows_them_in_sandbox(
    tmp_path, monkeypatch
):
    """Not vacuous: without the plan's sandbox choice, every packet task (file_read) is refused."""
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    prod = campaign.tool_gaps(
        campaign.expand_matrix(_plan_with(tmp_path, "auto-compliance", None), 1)
    )
    sandbox = campaign.tool_gaps(
        campaign.expand_matrix(_plan_with(tmp_path, "auto-compliance", "sandbox"), 1)
    )
    assert len(prod) == 30 and all("file_read" in g for g in prod) and sandbox == []
    real = campaign.tool_gaps(
        campaign.expand_matrix(eval_mode.REPO / "tests/wfe/plans/decision_run_v1.yaml", 1)
    )
    assert real == []


def test_a_sandbox_declared_row_keeps_its_sandbox_tools(tmp_path, monkeypatch, out_root):
    from tests.wfe.runner import workspace_context

    class SentError(Exception):
        pass

    seen = {}

    def fake_run_task(*a, **k):
        seen.update(k)
        raise SentError

    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(campaign, "make_sandbox", lambda *a, **k: None)
    monkeypatch.setattr(campaign, "run_task", fake_run_task)
    wsc = workspace_context("auto-compliance")
    row = {
        "run_id": "auto-compliance|m|s|t|r0",
        "workspace": "auto-compliance",
        "arm": wsc["model"],
        "arm_role": "incumbent",
        "suite": "s",
        "task_id": "t",
        "repeat": 0,
        "overrides": {},
        "tool_mode": "sandbox",
    }
    with contextlib.suppress(Exception):
        campaign.run_row(
            tmp_path, {"campaign_id": "c", "env": {}}, row, wsc, {"id": "t"}, 1, 1, None, False
        )
    assert seen["use_tools"] is True and seen["harness"]["pipeline_eval"]["allow"] == []


def test_a_no_tools_task_gets_no_tools_in_production_mode(out_root):
    """rig_short-style tasks in a production workspace: no allowlisted tools, no client tools."""
    h = {}
    wsc = {"system_prompt_pipeline": "p", "system_prompt_base": "b"}
    _, _, ctx = eval_mode.prepare(
        True,
        {**_row(), "workspace": "auto-compliance"},
        {"campaign_id": "c"},
        {"id": "t", "no_tools": True},
        wsc,
        h,
    )
    assert (
        h["pipeline_eval"]["allow"] == []
        and ctx["use_tools"] is False
        and ctx["production"] is False
    )


def test_seed_b64_stages_binary_fixtures_byte_exact(out_root, tmp_path):
    import base64

    from tests.wfe import controls
    from tests.wfe.runner import Sandbox

    blob = bytes(range(256)) + b"PK\x03\x04"
    task = {"id": "t", "seed_b64": {"sub/a.docx": base64.b64encode(blob).decode()}}
    wsc = {"system_prompt_pipeline": "", "system_prompt_base": ""}
    _, _, ctx = eval_mode.prepare(True, _row(), {"campaign_id": "c"}, task, wsc, {})
    assert (ctx["root"] / "in" / "sub" / "a.docx").read_bytes() == blob
    # the sandbox path writes the same bytes, confined to the sandbox
    sb = Sandbox(tmp_path)
    sb.file_write_bytes("sub/a.docx", blob)
    assert (tmp_path / "sub" / "a.docx").read_bytes() == blob
    with pytest.raises(ValueError):
        sb.file_write_bytes("../escape.bin", blob)
    assert "seed_b64" in controls.TASK_KEYS
