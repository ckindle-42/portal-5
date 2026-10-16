"""The compliance evaluation instance (root-fix Part 2c-2): every path under its root, the
operator's private inputs unreachable, a store built from public material only, only verified
tools served, and scoped compliance calls routed to it or refused — never to the operator."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _py(code: str, env: dict) -> subprocess.CompletedProcess:
    """Compliance modules read their paths at import: test them in a fresh interpreter."""
    full = {**os.environ, **env, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, "-c", code],
        env=full,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_every_path_the_code_uses_is_under_the_root(tmp_path):
    from portal.modules.compliance.core.eval_instance import env_for

    env = env_for(tmp_path / "eval")
    r = _py(
        "from portal.modules.compliance.core.eval_instance import verify; import sys; print(verify(sys.argv[0]))".replace(
            "sys.argv[0]", repr(str(tmp_path / "eval"))
        ),
        env,
    )
    assert r.stdout.strip() == "[]", r.stderr[-400:]
    leaky = {**env, "COMPLIANCE_DB_PATH": str(tmp_path / "operator.db")}
    r = _py(
        f"from portal.modules.compliance.core.eval_instance import verify; print(verify({str(tmp_path / 'eval')!r}))",
        leaky,
    )
    assert "compliance store would be" in r.stdout


def test_private_inputs_follow_their_overrides(tmp_path):
    env = {
        "COMPLIANCE_OPERATOR_PROFILE": str(tmp_path / "p.json"),
        "COMPLIANCE_ORG_GRAPH": str(tmp_path / "g.json"),
    }
    r = _py(
        "from portal.modules.compliance.core import operator_profile as o, runtime_config as c;"
        "print(o.PROFILE_PATH, c._DEFAULT_ORG_GRAPH)",
        env,
    )
    assert r.stdout.split() == [str(tmp_path / "p.json"), str(tmp_path / "g.json")], r.stderr[-300:]


def test_the_store_is_built_from_the_public_register(tmp_path):
    from portal.modules.compliance.core.eval_instance import env_for

    code = (
        "from portal.modules.compliance.core.repository import Repository;"
        "from portal.modules.compliance.core.cip_register import Register;"
        "from portal.modules.compliance.core.migrate_legacy import import_register; import os;"
        "r = Repository(os.environ['COMPLIANCE_DB_PATH']); r.migrate();"
        "print(import_register(r, Register.load())['requirement_nodes_imported'])"
    )
    r = _py(code, env_for(tmp_path / "eval"))
    assert int(r.stdout.strip()) > 200 and (tmp_path / "eval" / "compliance_store.db").exists(), (
        r.stderr[-300:]
    )


@pytest.mark.parametrize(
    ("tool", "status"),
    [("lookup_control", 200), ("refresh_catalogs", 403), ("compliance_note", 403)],
)
def test_the_evaluation_instance_serves_only_verified_tools(monkeypatch, tool, status):
    from starlette.requests import Request

    from portal.modules.compliance.tools import compliance_mcp as cm

    monkeypatch.setenv("COMPLIANCE_EVAL_INSTANCE", "1")
    monkeypatch.setitem(cm._DISPATCH, tool, lambda **k: {"ok": True})

    async def receive():
        return {"type": "http.request", "body": json.dumps({"arguments": {}}).encode()}

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/tools/{tool}",
            "headers": [],
            "path_params": {"tool_name": tool},
        },
        receive,
    )
    served = sum(cm._EVAL_SERVED.values())
    resp = asyncio.run(cm.invoke_tool(req))
    assert resp.status_code == status
    assert sum(cm._EVAL_SERVED.values()) - served == (1 if status == 200 else 0)  # the health count


def test_scoped_compliance_calls_go_to_the_evaluation_instance_or_nowhere(monkeypatch):
    from portal.platform.inference import tool_registry as tr
    from portal.platform.mcp_host import eval_scope as es

    monkeypatch.setattr(tr, "_compliance_server_url", lambda: "http://host:8937")
    url = "http://host:8937/tools/compliance_read"
    assert tr._eval_route("http://host:8937", url) == url  # unscoped: unchanged
    token = es.EVAL_SCOPE.set(
        {"campaign": "wfe_" + "a" * 16, "run": "wfe_" + "b" * 40, "allow": []}
    )
    try:
        monkeypatch.delenv("MCP_COMPLIANCE_EVAL_URL", raising=False)
        assert tr._eval_route("http://host:8937", url) is None
        monkeypatch.setenv("MCP_COMPLIANCE_EVAL_URL", "http://host:8948")
        assert tr._eval_route("http://host:8937", url) == "http://host:8948/tools/compliance_read"
        assert (
            tr._eval_route("http://host:8913", "http://host:8913/tools/x")
            == "http://host:8913/tools/x"
        )
    finally:
        es.EVAL_SCOPE.reset(token)


def test_a_tilde_root_stages_under_the_home_dir_not_a_literal_tilde_directory(
    tmp_path, monkeypatch
):
    """Live 2026-10-15: the default root '~/.portal-data/compliance-eval' was staged into a
    literal './~/...' directory, ingest_folder (which expands '~') found nothing, and the
    store was built with zero documents while the build printed success."""
    from portal.modules.compliance.core import eval_instance

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    out = eval_instance._stage_planted("~/.portal-data/compliance-eval")
    assert out == tmp_path / ".portal-data" / "compliance-eval" / "planted_staged"
    assert out.is_dir() and any(out.glob("*.md"))
    assert not (tmp_path / "~").exists()


def test_build_fails_loudly_when_the_planted_corpus_does_not_ingest(tmp_path, monkeypatch):
    from portal.modules.compliance.core import eval_instance, ingest, migrate_legacy

    monkeypatch.setenv("COMPLIANCE_DB_PATH", str(tmp_path / "c.db"))

    async def nothing(*a, **k):
        return {"error": "directory not found: x"}

    monkeypatch.setattr(ingest, "ingest_folder", nothing)
    monkeypatch.setattr(migrate_legacy, "import_register", lambda *a, **k: {})
    with pytest.raises(RuntimeError, match="did not ingest"):
        eval_instance.build(tmp_path)
