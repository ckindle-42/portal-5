"""Realuse fixtures are readable at the path the prompt names, in both tool modes."""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.mcp_host import eval_scope as es
from tests.wfe import eval_mode
from tests.wfe.realuse_paths import CHECKOUT, audit, named_paths, preflight
from tests.wfe.runner import REPO, Sandbox, load_suite

SUITE = REPO / "tests/wfe/suites/realuse_v1.jsonl"
PLAN = REPO / "tests/wfe/plans/realuse_v1_s8.yaml"
UPLOAD = "/workspace/uploads/realuse_v1/ru-v1-010/report.txt"


def _task(task_id: str) -> dict:
    return next(task for task in load_suite(SUITE) if task["id"] == task_id)


def _prepare(tmp_path: Path, monkeypatch, task: dict, workspace: str):
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(eval_mode, "cleanup_stores", lambda ctx: [])
    monkeypatch.setattr(eval_mode, "seed_stores", lambda scope, task: None)
    monkeypatch.setattr(eval_mode, "close_data_session", lambda scope: None)
    row = {
        "run_id": f"{workspace}|m|s|{task['id']}|r0",
        "workspace": workspace,
        "tool_mode": "production",
    }
    _task_out, _wsc, ctx = eval_mode.prepare(
        True,
        row,
        {"campaign_id": "realuse-paths"},
        task,
        {"system_prompt_pipeline": "p", "system_prompt_base": "b"},
        {},
    )
    return ctx


def test_prepare_stages_the_upload_tree_and_the_bare_name(tmp_path, monkeypatch):
    task = _task("ru-v1-010")
    ctx = _prepare(tmp_path, monkeypatch, task, "tools-specialist::fast")
    src = REPO / task["fixtures"][0]
    bare = ctx["root"] / "in" / "report.txt"
    tree = ctx["root"] / "in" / "realuse_v1" / "ru-v1-010" / "report.txt"
    mount = tmp_path / "uploads" / "realuse_v1" / "ru-v1-010" / "report.txt"
    assert bare.read_bytes() == src.read_bytes()
    assert tree.read_bytes() == src.read_bytes()
    assert mount.read_bytes() == src.read_bytes()
    assert es.confine(tmp_path, ctx["scope"], UPLOAD, sub="in") == tree
    assert ctx["root"] not in mount.resolve().parents

    eval_mode.cleanup(ctx, None, {"run_id": "x"})
    assert mount.is_file()
    assert not tree.exists()


def test_sandbox_file_read_opens_the_prompt_path(tmp_path, monkeypatch):
    from tests.wfe import runner as rn

    def fake_chat(model, messages, tools=True, tool_schemas=None, **kwargs):
        return {
            "message": {"content": "done"},
            "finish_reason": "stop",
            "economics": rn.Economics(),
            "served": {},
        }

    monkeypatch.setattr(rn, "chat", fake_chat)
    task = _task("ru-v1-015")
    sandbox = Sandbox(tmp_path / "sb")
    rn.run_task(
        "m",
        "sys",
        {
            "id": task["id"],
            "fixtures": task["fixtures"],
            "turns": [
                {"user": "count", "checks": [{"type": "answer_contains", "patterns": ["done"]}]}
            ],
        },
        sandbox,
        2,
        30,
        use_tools=True,
    )
    nested = sandbox.file_read("/workspace/uploads/realuse_v1/ru-v1-015/tests/t1.py")
    assert nested == (REPO / "tests/fixtures/realuse_v1/ru-v1-015/tests/t1.py").read_text()
    report = _task("ru-v1-010")
    rn.run_task(
        "m",
        "sys",
        {
            "id": report["id"],
            "fixtures": report["fixtures"],
            "turns": [
                {"user": "read", "checks": [{"type": "answer_contains", "patterns": ["done"]}]}
            ],
        },
        sandbox,
        2,
        30,
        use_tools=True,
    )
    assert "urgent: restock mugs" in sandbox.file_read(UPLOAD)


def test_read_pdf_and_read_word_resolve_inside_the_row(tmp_path, monkeypatch):
    from portal.modules.documents.tools import document_mcp

    pdf = _task("ru-v1-001")
    docx = _task("ru-v1-002")
    pdf_ctx = _prepare(tmp_path, monkeypatch, pdf, "auto-daily")
    docx_ctx = _prepare(tmp_path, monkeypatch, docx, "auto-daily")
    monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)

    def resolve(scope: dict, path: str) -> Path:
        token = es.EVAL_SCOPE.set(scope)
        try:
            return document_mcp._resolve_input_path(path)
        finally:
            es.EVAL_SCOPE.reset(token)

    bare = resolve(pdf_ctx["scope"], "final_invoice.pdf")
    full = resolve(pdf_ctx["scope"], "/workspace/uploads/realuse_v1/ru-v1-001/final_invoice.pdf")
    word = resolve(docx_ctx["scope"], "drive_notes.docx")
    assert bare.read_bytes() == (REPO / pdf["fixtures"][0]).read_bytes()
    assert full.read_bytes() == bare.read_bytes()
    assert word.read_bytes() == (REPO / docx["fixtures"][0]).read_bytes()
    for tool in (document_mcp.read_pdf, document_mcp.read_word_document, document_mcp.read_excel):
        assert "_resolve_input_path" in tool.__code__.co_names


def test_attach_source_and_run_sql_read_the_prompt_file(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    from portal.modules.data.tools import data_mcp

    task = _task("ru-v1-022")
    ctx = _prepare(tmp_path, monkeypatch, task, "auto-research::data")
    monkeypatch.setattr(data_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(data_mcp, "_SESS_DIR", tmp_path / "sessions")
    data_mcp._conns.clear()
    token = es.EVAL_SCOPE.set(ctx["scope"])
    try:
        bare = data_mcp.attach_source("ignored", "survey.csv", "ratings")
        sql = data_mcp.run_sql("ignored", "SELECT count(*) AS n FROM ratings")
        full = data_mcp.attach_source(
            "ignored",
            "/workspace/uploads/realuse_v1/ru-v1-022/survey.csv",
            "ratings_full",
        )
    finally:
        es.EVAL_SCOPE.reset(token)
        for con in list(data_mcp._conns.values()):
            con.close()
        data_mcp._conns.clear()
    assert "error" not in bare, bare
    assert "error" not in full, full
    assert bare["rows"] == full["rows"] > 0
    assert sql["rows"] == [[bare["rows"]]]


def test_named_paths_cover_upload_and_repo_fixtures():
    upload = named_paths(_task("ru-v1-010"))
    repo = named_paths(_task("ru-v1-012"))
    assert UPLOAD in upload
    assert "fixtures/realuse_v1/ru-v1-012/app.py" in repo
    assert all(not item.startswith("/workspace/") for item in repo)


def test_preflight_stages_the_selected_task_and_refuses_a_missing_one(tmp_path, capsys):
    out = tmp_path / "AI_Output"
    code = preflight(
        [
            "--preflight",
            "--plan",
            str(PLAN),
            "--tier",
            "realuse",
            "--workspace",
            "tools-specialist::fast",
            "--task",
            "ru-v1-010",
        ],
        output_root=out,
        repo=CHECKOUT,
    )
    assert code == 0, capsys.readouterr()
    staged = out / "uploads" / "realuse_v1" / "ru-v1-010" / "report.txt"
    assert (
        staged.read_bytes()
        == (CHECKOUT / "tests/fixtures/realuse_v1/ru-v1-010/report.txt").read_bytes()
    )
    assert "fixture preflight: PASS" in capsys.readouterr().out

    empty = tmp_path / "empty-repo"
    empty.mkdir()
    code = preflight(
        [
            "--plan",
            str(PLAN),
            "--tier",
            "realuse",
            "--workspace",
            "tools-specialist::fast",
            "--task",
            "ru-v1-010",
        ],
        output_root=tmp_path / "other",
        repo=empty,
    )
    failed = capsys.readouterr().out
    assert code == 1
    assert "unreadable: /workspace/uploads/realuse_v1/ru-v1-010/report.txt" in failed


def test_audit_names_an_unreadable_path_and_does_not_escape(tmp_path):
    out = tmp_path / "out"
    _count, failures = audit(
        [
            {
                "fixtures": ["tests/fixtures/realuse_v1/../../pyproject.toml"],
                "turns": [
                    {"user": "open /workspace/uploads/realuse_v1/ru-v1-010/missing.txt please"}
                ],
            }
        ],
        output_root=out,
        repo=CHECKOUT,
    )
    assert any("missing.txt" in line for line in failures)
    assert any("pyproject.toml" in line or "unreadable" in line for line in failures)
    assert not (out / "pyproject.toml").exists()
    assert not (CHECKOUT / "uploads").exists()


def test_laguna_repo_paths_stay_in_the_checkout(tmp_path):
    _count, failures = audit([_task("ru-v1-012")], output_root=tmp_path, repo=CHECKOUT)
    assert failures == []
    assert (CHECKOUT / "fixtures/realuse_v1/ru-v1-012/app.py").is_file()
    assert not (tmp_path / "uploads" / "realuse_v1" / "ru-v1-012" / "app.py").exists()
