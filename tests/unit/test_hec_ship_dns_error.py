"""HEC ship failures must name LAB_SPLUNK_HEC_URL when the host cannot resolve.

Live 2026-11-07: the module-default HEC_URL is the container name
portal5-lab-splunk; shipping from the Mac host died with a bare
`[Errno 8] nodename nor servname provided`. Hermetic: httpx.post is faked,
no network, no Splunk.
"""

from __future__ import annotations

import socket

import httpx

from portal.modules.security.core.siem import hec_ship


class _FakeResponse:
    status_code = 200


def _dns_post(url, **kwargs):
    raise httpx.ConnectError("all connection attempts failed") from socket.gaierror(
        8, "nodename nor servname provided, or not known"
    )


def _refused_post(url, **kwargs):
    raise ConnectionRefusedError("connection refused")


def _ok_post(url, **kwargs):
    return _FakeResponse()


def test_ship_dns_failure_names_env_var_and_host(monkeypatch):
    monkeypatch.setattr(hec_ship, "HEC_URL", "https://portal5-lab-splunk:8088")
    monkeypatch.setattr(hec_ship, "HEC_TOKEN", "token")
    monkeypatch.setattr(hec_ship.httpx, "post", _dns_post)
    result = hec_ship.ship({"k": "v"}, sourcetype="aws:cloudtrail", host="h")
    assert result["ok"] is False
    assert "LAB_SPLUNK_HEC_URL" in result["error"]
    assert "portal5-lab-splunk" in result["error"]


def test_ship_batch_dns_failure_names_env_var_and_host(monkeypatch):
    monkeypatch.setattr(hec_ship, "HEC_URL", "https://portal5-lab-splunk:8088")
    monkeypatch.setattr(hec_ship, "HEC_TOKEN", "token")
    monkeypatch.setattr(hec_ship.httpx, "post", _dns_post)
    result = hec_ship.ship_batch([{"k": "v"}], sourcetype="aws:cloudtrail", host="h")
    assert result["ok"] is False
    assert "LAB_SPLUNK_HEC_URL" in result["error"]
    assert "portal5-lab-splunk" in result["error"]


def test_non_dns_connect_failure_keeps_plain_error(monkeypatch):
    monkeypatch.setattr(hec_ship, "HEC_URL", "https://splunk.example:8088")
    monkeypatch.setattr(hec_ship, "HEC_TOKEN", "token")
    monkeypatch.setattr(hec_ship.httpx, "post", _refused_post)
    result = hec_ship.ship({"k": "v"}, sourcetype="aws:cloudtrail", host="h")
    assert result["ok"] is False
    assert result["error"] == "connection refused"
    assert "LAB_SPLUNK_HEC_URL" not in result["error"]


def test_success_path_untouched(monkeypatch):
    monkeypatch.setattr(hec_ship, "HEC_URL", "https://splunk.example:8088")
    monkeypatch.setattr(hec_ship, "HEC_TOKEN", "token")
    monkeypatch.setattr(hec_ship.httpx, "post", _ok_post)
    result = hec_ship.ship_batch([{"k": "v"}], sourcetype="aws:cloudtrail", host="h")
    assert result["ok"] is True
