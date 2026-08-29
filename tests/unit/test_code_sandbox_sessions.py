import pytest

from portal.modules.coding.tools import code_sandbox_mcp as sandbox


def test_session_ids_are_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX_SESSIONS_DIR", tmp_path)
    session = sandbox._session_dir("../../team session")
    assert session == tmp_path / "teamsession"
    assert session.is_dir()


def test_list_and_reset_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX_SESSIONS_DIR", tmp_path)
    session = sandbox._session_dir("alpha")
    (session / "state.txt").write_text("ready")
    assert sandbox._list_sessions() == [{"session_id": "alpha", "bytes": 5}]
    assert sandbox._reset_session("alpha") == {"session_id": "alpha", "reset": True}
    assert not session.exists()


@pytest.mark.asyncio
async def test_packages_require_session():
    result = await sandbox.execute_python("print('ok')", packages=["requests"])
    assert result["error_type"] == "session_required"


def test_artifact_caps_and_publishes(tmp_path, monkeypatch):
    (tmp_path / "result.txt").write_text("ready")
    monkeypatch.setattr(
        sandbox, "publish_file_sync", lambda path: {"url": "https://example.test/result"}
    )
    assert sandbox._publish_artifacts(tmp_path) == [
        {"name": "result.txt", "url": "https://example.test/result"}
    ]
