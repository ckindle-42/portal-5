"""publish_file under launchd — host-native services never source the repo
.env, so OWUI_API_KEY / OPENWEBUI_URL / PORTAL_PUBLIC_URL must fall back to
it (key-only read, os.environ wins, os.environ never mutated, no secret in
errors). The live s2-p6-auto-audio-stt gap: the host :8924 transcript URLs
are not OWUI download links and the launchd env carries no publish key.
Hermetic: tmp .env, mocked httpx.Client, no network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from portal.platform.mcp_host import owui_files

KEYS = ("OWUI_API_KEY", "OPENWEBUI_URL", "PORTAL_PUBLIC_URL")


@pytest.fixture()
def dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# publish config\n"
        'OWUI_API_KEY="sk-dotenv-test"\n'
        "PORTAL_PUBLIC_URL=http://localhost:8080\n"
        "UNRELATED_KEY=do-not-read\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(owui_files, "_repo_env_file", lambda: env)
    return env


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"id": "file-123"}


class _FakeClient:
    captured: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        _FakeClient.captured = {"url": url, **kwargs}
        return _FakeResponse()


def test_dotenv_key_and_public_url_used_when_env_absent(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(owui_files.httpx, "Client", _FakeClient)
    f = tmp_path / "transcript_abc.docx"
    f.write_bytes(b"docx")
    out = owui_files.publish_file_sync(f)
    assert out["url"] == "http://localhost:8080/api/v1/files/file-123/content/transcript_abc.docx"
    assert _FakeClient.captured["url"] == "http://localhost:8080/api/v1/files/"
    headers = _FakeClient.captured["headers"]
    assert headers["Authorization"] == "Bearer sk-dotenv-test"
    # key-only read: never exported into the process environment
    assert "OWUI_API_KEY" not in os.environ
    assert "PORTAL_PUBLIC_URL" not in os.environ


def test_environ_wins_over_dotenv(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OWUI_API_KEY", "sk-env-wins")
    monkeypatch.setenv("OPENWEBUI_URL", "http://open-webui:8080")
    monkeypatch.setattr(owui_files.httpx, "Client", _FakeClient)
    f = tmp_path / "a.wav"
    f.write_bytes(b"wav")
    owui_files.publish_file_sync(f)
    assert _FakeClient.captured["url"] == "http://open-webui:8080/api/v1/files/"
    assert _FakeClient.captured["headers"]["Authorization"] == "Bearer sk-env-wins"


def test_blank_environ_counts_as_absent(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OWUI_API_KEY", "  ")
    monkeypatch.setattr(owui_files.httpx, "Client", _FakeClient)
    f = tmp_path / "a.wav"
    f.write_bytes(b"wav")
    out = owui_files.publish_file_sync(f)
    assert "error" not in out
    assert _FakeClient.captured["headers"]["Authorization"] == "Bearer sk-dotenv-test"


def test_missing_key_everywhere_is_an_error_not_a_call(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv.write_text("UNRELATED_KEY=x\n", encoding="utf-8")
    monkeypatch.setattr(owui_files.httpx, "Client", _FakeClient)
    _FakeClient.captured = {}
    f = tmp_path / "a.wav"
    f.write_bytes(b"wav")
    out = owui_files.publish_file_sync(f)
    assert "error" in out and "OWUI_API_KEY" in out["error"]
    assert _FakeClient.captured == {}


def test_no_dotenv_file_keeps_container_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(owui_files, "_repo_env_file", lambda: None)
    assert owui_files._owui_url() == "http://open-webui:8080"
    f = tmp_path / "a.wav"
    f.write_bytes(b"wav")
    out = owui_files.publish_file_sync(f)
    assert "error" in out
