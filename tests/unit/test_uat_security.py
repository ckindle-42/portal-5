"""Unit tests for scripts/uat_security.py — the security lane's one-shot
speed/design UAT. Hermetic: a synthetic PortalConfig (no portal.yaml read)
and mocked httpx.AsyncClient (no network), per CLAUDE.md's tests/unit/ rule.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import uat_security as uat

from portal.platform.inference.config import (
    ModuleToggle,
    PortalConfig,
    WorkspaceAlias,
    WorkspaceSpec,
)


def _config() -> PortalConfig:
    return PortalConfig(
        mcp_fleet=[],
        modules={
            "security": ModuleToggle(enabled=True),
            "security_redteam": ModuleToggle(enabled=False),
            "general": ModuleToggle(enabled=True),
        },
        workspaces={
            "auto-security": WorkspaceSpec(
                name="Security",
                description="d",
                module="security",
                variants={
                    "blueteam": {"model_hint": "x"},
                    "redteam": {"module": "security_redteam", "model_hint": "y"},
                },
            ),
            "security-reviewer": WorkspaceSpec(name="Review", description="d", module="security"),
            "auto-daily": WorkspaceSpec(
                name="Daily",
                description="d",
                module="general",
                variants={"quick": {"model_hint": "z"}},
            ),
        },
        aliases={
            "sec-alias": WorkspaceAlias(
                to="auto-security::blueteam", remove_after=date(2099, 1, 1), reason="test"
            ),
            "daily-alias": WorkspaceAlias(
                to="auto-daily::quick", remove_after=date(2099, 1, 1), reason="test"
            ),
        },
    )


def test_security_ids_finds_base_and_variants_with_enabled_state():
    ids = uat.security_ids(_config())
    assert ("auto-security", True) in ids
    assert ("auto-security::blueteam", True) in ids
    assert ("auto-security::redteam", False) in ids
    assert ("security-reviewer", True) in ids
    assert not any(wid == "auto-daily" for wid, _ in ids)


def test_security_ids_sorted_base_then_variants():
    ids = [wid for wid, _ in uat.security_ids(_config())]
    assert ids.index("auto-security") < ids.index("auto-security::blueteam")


def test_security_aliases_only_includes_security_targets():
    aliases = uat.security_aliases(_config())
    assert aliases == [("sec-alias", "auto-security::blueteam")]


def test_split_id_splits_variant():
    assert uat._split_id("auto-security::redteam") == ("auto-security", "redteam")
    assert uat._split_id("auto-security") == ("auto-security", None)


def test_scrape_counter_sums_matching_labels():
    text = (
        'portal5_router_layer_total{layer="router_handoff_gate",workspace="auto-daily"} 3.0\n'
        'portal5_router_layer_total{layer="router_handoff_gate",workspace="auto-coding"} 9.0\n'
        'portal5_router_layer_total{layer="llm",workspace="auto-daily"} 1.0\n'
    )
    assert (
        uat._scrape_counter(
            text, "portal5_router_layer_total", layer="router_handoff_gate", workspace="auto-daily"
        )
        == 3.0
    )


def test_scrape_counter_no_match_is_zero():
    assert uat._scrape_counter("", "portal5_router_layer_total", layer="x", workspace="y") == 0.0


def _mock_response(status_code: int, json_body: dict, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.headers = headers or {}
    return resp


@pytest.mark.asyncio
async def test_request_success_parses_route_and_content():
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_mock_response(
            200,
            {"choices": [{"message": {"content": "pong"}}]},
            {"x-portal-route": "auto-security;ollama-1;vulnllm-r-7b"},
        )
    )
    status, headers, seconds, content, error = await uat._request(client, "auto-security", "ping")
    assert status == 200
    assert content == "pong"
    assert error == ""
    assert headers["x-portal-route"] == "auto-security;ollama-1;vulnllm-r-7b"
    assert seconds >= 0

    call = client.post.call_args
    assert call.kwargs["json"]["model"] == "auto-security"
    assert call.kwargs["params"] is None


@pytest.mark.asyncio
async def test_request_forwards_variant_as_query_param():
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_mock_response(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    await uat._request(client, "auto-security", "ping", variant="redteam")
    assert client.post.call_args.kwargs["params"] == {"variant": "redteam"}


@pytest.mark.asyncio
async def test_request_disabled_workspace_returns_detail_as_error():
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_mock_response(
            404, {"detail": "Workspace 'auto-security::redteam' is disabled (module not enabled)."}
        )
    )
    status, _headers, _seconds, content, error = await uat._request(
        client, "auto-security", "ping", "redteam"
    )
    assert status == 404
    assert content == ""
    assert "disabled" in error.lower()


@pytest.mark.asyncio
async def test_request_transport_error_is_caught():
    import httpx

    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    status, headers, _seconds, content, error = await uat._request(client, "auto-security", "ping")
    assert status is None
    assert headers == {}
    assert content == ""
    assert "refused" in error


def test_shot_ok_for_enabled_requires_200_and_nonempty():
    assert uat.Shot(id="x", enabled=True, status=200, non_empty=True).ok
    assert not uat.Shot(id="x", enabled=True, status=200, non_empty=False).ok
    assert not uat.Shot(id="x", enabled=True, status=404, non_empty=True).ok


def test_shot_ok_for_disabled_requires_404_with_disabled_message():
    assert uat.Shot(
        id="x", enabled=False, status=404, error="Workspace 'x' is disabled (module not enabled)."
    ).ok
    assert not uat.Shot(id="x", enabled=False, status=200, error="").ok
    assert not uat.Shot(id="x", enabled=False, status=404, error="not found").ok


@pytest.mark.asyncio
async def test_run_shots_respects_only_filter():
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_mock_response(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    ids = [("auto-security", True), ("auto-security::redteam", False)]
    shots = await uat.run_shots(client, ids, only="auto-security")
    assert [s.id for s in shots] == ["auto-security"]


@pytest.mark.asyncio
async def test_run_design_checks_auto_security_isolation_pass_and_fail():
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(text=""))
    client.post = AsyncMock(
        return_value=_mock_response(
            200,
            {"choices": [{"message": {"content": "please pick the security workspace"}}]},
            {"x-portal-route": "auto-daily;ollama-1;granite"},
        )
    )
    checks = await uat.run_design_checks(client, aliases=[], shots_by_id={})
    isolation = next(c for c in checks if "never auto-routed" in c.name)
    assert isolation.passed


@pytest.mark.asyncio
async def test_run_design_checks_flags_auto_security_leak():
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(text=""))
    client.post = AsyncMock(
        return_value=_mock_response(
            200,
            {"choices": [{"message": {"content": "oops"}}]},
            {"x-portal-route": "auto-security;ollama-1;vulnllm"},
        )
    )
    checks = await uat.run_design_checks(client, aliases=[], shots_by_id={})
    isolation = next(c for c in checks if "never auto-routed" in c.name)
    assert not isolation.passed


@pytest.mark.asyncio
async def test_run_design_checks_alias_mismatch_fails():
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(text=""))

    responses = {
        "auto": _mock_response(
            200, {"choices": [{"message": {"content": "x"}}]}, {"x-portal-route": "auto-daily;b;m"}
        ),
        "auto-security": _mock_response(
            200,
            {"choices": [{"message": {"content": "x"}}]},
            {"x-portal-route": "auto-security;b;m"},
        ),
        "sec-alias": _mock_response(
            200, {"choices": [{"message": {"content": "x"}}]}, {"x-portal-route": "DIFFERENT;b;m"}
        ),
    }

    async def fake_post(url, json, headers, params):  # noqa: ANN001 - test double
        return responses[json["model"]]

    client.post = AsyncMock(side_effect=fake_post)
    checks = await uat.run_design_checks(
        client, aliases=[("sec-alias", "auto-security")], shots_by_id={}
    )
    alias_check = next(c for c in checks if "sec-alias" in c.name)
    assert not alias_check.passed


def test_main_dry_run_lists_ids_without_network(capsys, monkeypatch):
    monkeypatch.setattr(uat, "load_portal_config", _config)
    rc = uat.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auto-security (enabled)" in out
    assert "auto-security::redteam (disabled, not tested)" in out


def test_main_dry_run_only_filters_to_one_id(capsys, monkeypatch):
    monkeypatch.setattr(uat, "load_portal_config", _config)
    rc = uat.main(["--dry-run", "--only", "security-reviewer"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "security-reviewer (enabled)" in out
    assert "auto-security (enabled)" not in out
    assert "Would run design checks" not in out
