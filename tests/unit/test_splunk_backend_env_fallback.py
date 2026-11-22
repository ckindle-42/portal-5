"""SplunkBackend .env fallback — launchd runs detection-mcp without sourcing .env."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from portal.modules.security.core.siem import spl_backend
from portal.modules.security.core.siem.spl_backend import SplunkBackend

_KEYS = ("LAB_SPLUNK_URL", "LAB_SPLUNK_USER", "LAB_SPLUNK_PASSWORD", "LAB_SPLUNK_INDEX")
_DOTENV_TEXT = (
    "LAB_SPLUNK_URL=https://10.9.8.7:8089\n"
    "LAB_SPLUNK_USER=labuser\n"
    "LAB_SPLUNK_PASSWORD=labpass\n"
    "LAB_SPLUNK_INDEX=labindex\n"
)


@pytest.fixture(autouse=True)
def _launchd_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_env(tmp_path: Path, text: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(text, encoding="utf-8")
    return env_file


def _point_at(monkeypatch: pytest.MonkeyPatch, env_file: Path | None) -> None:
    monkeypatch.setattr(spl_backend, "_repo_env_file", lambda: env_file)


def test_absent_env_loads_lab_coordinates_from_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_at(monkeypatch, _write_env(tmp_path, _DOTENV_TEXT))
    be = SplunkBackend()
    assert be.url == "https://10.9.8.7:8089"
    assert be.user == "labuser"
    assert be.pw == "labpass"
    assert be.index == "labindex"
    for key in _KEYS:
        assert key not in os.environ


def test_env_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, _write_env(tmp_path, _DOTENV_TEXT))
    monkeypatch.setenv("LAB_SPLUNK_URL", "https://env-host:8089")
    monkeypatch.setenv("LAB_SPLUNK_USER", "envuser")
    monkeypatch.setenv("LAB_SPLUNK_PASSWORD", "envpass")
    monkeypatch.setenv("LAB_SPLUNK_INDEX", "envindex")
    be = SplunkBackend()
    assert be.url == "https://env-host:8089"
    assert be.user == "envuser"
    assert be.pw == "envpass"
    assert be.index == "envindex"


def test_blank_env_falls_back_to_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, _write_env(tmp_path, _DOTENV_TEXT))
    monkeypatch.setenv("LAB_SPLUNK_URL", "")
    monkeypatch.setenv("LAB_SPLUNK_USER", "   ")
    be = SplunkBackend()
    assert be.url == "https://10.9.8.7:8089"
    assert be.user == "labuser"


def test_missing_dotenv_degrades_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, None)
    be = SplunkBackend()
    assert be.url == "https://portal5-lab-splunk:8089"
    assert be.user == "admin"
    assert be.pw == ""
    assert be.index == "portal5_lab"


def test_unreadable_dotenv_degrades_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"LAB_SPLUNK_URL=\xff\xfe\n")
    _point_at(monkeypatch, env_file)
    be = SplunkBackend()
    assert be.url == "https://portal5-lab-splunk:8089"
    assert be.user == "admin"


def test_partial_dotenv_keeps_defaults_for_absent_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_at(monkeypatch, _write_env(tmp_path, "LAB_SPLUNK_URL=https://10.9.8.7:8089\n"))
    be = SplunkBackend()
    assert be.url == "https://10.9.8.7:8089"
    assert be.user == "admin"
    assert be.pw == ""
    assert be.index == "portal5_lab"


def test_quotes_comments_and_first_occurrence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = (
        "# LAB_SPLUNK_URL=https://commented:8089\n"
        'LAB_SPLUNK_URL="https://quoted:8089"\n'
        "LAB_SPLUNK_URL=https://second:8089\n"
        "LAB_SPLUNK_PASSWORD='p@ss=word'\n"
    )
    _point_at(monkeypatch, _write_env(tmp_path, text))
    be = SplunkBackend()
    assert be.url == "https://quoted:8089"
    assert be.pw == "p@ss=word"


def test_password_never_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _point_at(monkeypatch, _write_env(tmp_path, "LAB_SPLUNK_PASSWORD=supersecret\n"))
    with caplog.at_level(logging.DEBUG):
        SplunkBackend()
    assert "supersecret" not in caplog.text


def test_repo_env_file_walks_up_from_module_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = tmp_path / "portal" / "modules" / "security" / "core" / "siem"
    nested.mkdir(parents=True)
    module_file = nested / "spl_backend.py"
    module_file.write_text("", encoding="utf-8")
    _write_env(tmp_path, _DOTENV_TEXT)
    monkeypatch.setattr(spl_backend, "__file__", str(module_file))
    found = spl_backend._repo_env_file()
    assert found is not None
    assert found == tmp_path / ".env"


def test_repo_env_file_absent_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_file = tmp_path / "spl_backend.py"
    module_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(spl_backend, "__file__", str(module_file))
    assert spl_backend._repo_env_file() is None
