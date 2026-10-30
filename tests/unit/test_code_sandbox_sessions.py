import pytest

from portal.modules.coding.tools import code_sandbox_mcp as sandbox


class _DockerProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


async def _capture_docker_argv(monkeypatch, **kwargs):
    commands = []

    async def capture(*command, **_options):
        commands.append(command)
        return _DockerProcess()

    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", capture)
    await sandbox._run_in_docker("python:test", ["python3", "/code"], "pass", 1, **kwargs)
    return list(commands[0])


def _volumes(argv):
    return [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-v"]


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


@pytest.mark.asyncio
async def test_scoped_docker_mounts_only_the_row_input(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path / "sandbox")
    monkeypatch.setattr(sandbox, "SANDBOX_WORKSPACE_DIR", "/dind/workspace")
    scope = {
        "campaign": "wfe_0123456789abcdef",
        "run": "wfe_0123456789abcdef0123456789abcdef01234567",
        "allow": ["execute_python"],
    }
    token = sandbox.EVAL_SCOPE.set(scope)
    try:
        argv = await _capture_docker_argv(monkeypatch)
    finally:
        sandbox.EVAL_SCOPE.reset(token)

    mounts = _volumes(argv)
    row_input = (
        "/dind/workspace/wfe/wfe_0123456789abcdef/wfe_0123456789abcdef0123456789abcdef01234567/in"
    )
    assert f"{row_input}:/workspace:ro" in mounts
    assert f"{row_input}:/workspace/uploads:ro" in mounts
    assert not any(
        "/dind/workspace:" in mount
        and mount
        not in {
            f"{row_input}:/workspace:ro",
            f"{row_input}:/workspace/uploads:ro",
        }
        for mount in mounts
    )


@pytest.mark.asyncio
async def test_production_docker_mounts_only_resolved_uploads(tmp_path, monkeypatch):
    workspace = tmp_path / "ai-output"
    uploads = workspace / "uploads"
    uploads.mkdir(parents=True)
    allowed = uploads / "file-id_report.csv"
    allowed.write_text("a,b\n1,2\n")
    unrelated = uploads / "other-id_private.csv"
    unrelated.write_text("secret\n")
    outside = tmp_path / "outside.csv"
    outside.write_text("secret\n")
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path / "sandbox")
    monkeypatch.setattr(sandbox, "SANDBOX_WORKSPACE_DIR", "/dind/workspace")
    resolve = sandbox.resolve_upload_path

    def resolve_reference(reference):
        return outside if reference == "outside" else resolve(reference)

    monkeypatch.setattr(sandbox, "resolve_upload_path", resolve_reference)
    argv = await _capture_docker_argv(monkeypatch, workspace_upload_refs=("file-id", "outside"))

    mounts = _volumes(argv)
    assert any(mount.endswith(":/workspace:rw") for mount in mounts)
    assert (
        "/dind/workspace/uploads/file-id_report.csv:/workspace/uploads/file-id_report.csv:ro"
        in mounts
    )
    assert not any("other-id_private.csv" in mount or "outside.csv" in mount for mount in mounts)
    assert any(mount.endswith(":/out") for mount in mounts)


@pytest.mark.asyncio
async def test_production_docker_mounts_no_user_uploads_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ai-output"))
    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path / "sandbox")
    monkeypatch.setattr(sandbox, "SANDBOX_WORKSPACE_DIR", "/dind/workspace")

    argv = await _capture_docker_argv(monkeypatch)

    mounts = _volumes(argv)
    assert sum(mount.endswith(":/workspace:rw") for mount in mounts) == 1
    assert not any("/dind/workspace" in mount for mount in mounts)
    assert any(mount.endswith(":/out") for mount in mounts)


@pytest.mark.asyncio
async def test_production_docker_mounts_the_requests_attached_uploads(tmp_path, monkeypatch):
    # The pipeline forwards OWUI's body["files"] ids; only those uploads are mounted.
    from portal.platform.mcp_host.eval_scope import ATTACHED_UPLOADS

    workspace = tmp_path / "ai-output"
    uploads = workspace / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "file-id_report.csv").write_text("a,b\n")
    (uploads / "other-id_private.csv").write_text("secret\n")
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(sandbox, "SANDBOX_DIR", tmp_path / "sandbox")
    monkeypatch.setattr(sandbox, "SANDBOX_WORKSPACE_DIR", "/dind/workspace")
    token = ATTACHED_UPLOADS.set(("file-id",))
    try:
        argv = await _capture_docker_argv(monkeypatch)
    finally:
        ATTACHED_UPLOADS.reset(token)

    mounts = _volumes(argv)
    assert (
        "/dind/workspace/uploads/file-id_report.csv:/workspace/uploads/file-id_report.csv:ro"
        in mounts
    )
    assert not any("other-id_private.csv" in mount for mount in mounts)
