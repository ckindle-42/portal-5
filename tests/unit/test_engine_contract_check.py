"""engine_contract_check version identity — mocked HTTP, no engines."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import engine_contract_check as ecc


class _Resp:
    def __init__(self, payload: dict, status_error: Exception | None = None) -> None:
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error:
            raise self._status_error

    def json(self) -> dict:
        return self._payload


def test_omlx_version_is_the_status_payload_not_the_keg(monkeypatch):
    def fake_get(url: str, **kwargs):
        assert url == f"{ecc.OMLX}/api/status"
        assert kwargs.get("timeout") == 5
        return _Resp({"version": "0.7.3"})

    def _no_keg(_path: str) -> str:
        raise AssertionError("brew keg symlink was consulted")

    monkeypatch.setattr(ecc.httpx, "get", fake_get)
    monkeypatch.setattr(ecc.os, "readlink", _no_keg)
    monkeypatch.setattr(ecc, "_omlx_installed_version", lambda: "0.7.3")
    assert ecc._omlx_version() == ("0.7.3", "0.7.3")


def test_omlx_status_without_version_cannot_run(monkeypatch):
    monkeypatch.setattr(ecc.httpx, "get", lambda *_a, **_k: _Resp({}))
    monkeypatch.setattr(ecc, "_omlx_installed_version", lambda: "0.7.2")
    with pytest.raises(ecc.CannotRunError, match="version"):
        ecc._omlx_version()


def test_installed_version_follows_the_active_package(monkeypatch):
    import scripts.engine_autoupdate as eu

    monkeypatch.setattr(eu, "omlx_running", lambda: "0.7.3")
    assert ecc._omlx_installed_version() == "0.7.3"


def test_missing_package_does_not_replace_the_served_version(monkeypatch):
    import scripts.engine_autoupdate as eu

    def gone() -> str:
        raise OSError("no keg")

    monkeypatch.setattr(eu, "omlx_running", gone)
    monkeypatch.setattr(ecc.httpx, "get", lambda *_a, **_k: _Resp({"version": "0.7.3"}))
    assert ecc._omlx_version() == ("0.7.3", None)


def _verified(tmp_path, version: str) -> None:
    state = {
        "omlx": {
            "version": version,
            "ok": True,
            "verified_utc": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }
    }
    (tmp_path / "engine_contract.json").write_text(json.dumps(state))


def test_matching_served_version_still_skips(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ecc, "STATE", tmp_path / "engine_contract.json")
    _verified(tmp_path, "0.7.3")
    monkeypatch.setattr(ecc, "_omlx_version", lambda: ("0.7.3", "0.7.3"))
    called = []

    async def check(_models):
        called.append(True)
        return [ecc.Result("probe", True, "ok")]

    monkeypatch.setitem(ecc.ENGINES, "omlx", (ecc._omlx_version, check))
    assert ecc.main(["--if-changed", "omlx"]) == 0
    out = capsys.readouterr().out
    assert "[SKIP] omlx 0.7.3:" in out
    assert called == []


def test_installed_and_served_drift_is_not_a_skip(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ecc, "STATE", tmp_path / "engine_contract.json")
    _verified(tmp_path, "0.7.3")
    monkeypatch.setattr(ecc, "_omlx_version", lambda: ("0.7.3", "0.7.2"))

    async def check(_models):
        return [ecc.Result("probe", True, "ok")]

    monkeypatch.setitem(ecc.ENGINES, "omlx", (ecc._omlx_version, check))
    assert ecc.main(["--if-changed", "omlx"]) == 0
    out = capsys.readouterr().out
    assert "[SKIP]" not in out
    assert "0.7.3" in out and "0.7.2" in out
    assert "changed — needs verify/restart" in out
    saved = json.loads((tmp_path / "engine_contract.json").read_text())
    assert saved["omlx"]["version"] == "0.7.3"
