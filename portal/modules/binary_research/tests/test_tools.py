"""Tool tests: read/write/edit + bash routing (container via stub, host gate)."""

from pathlib import Path

import pytest

from portal.modules.binary_research.harness.policy import Policy
from portal.modules.binary_research.harness.tools import (
    get_schemas,
    run_tool,
    tool_bash,
    tool_edit,
    tool_read,
    tool_write,
)


@pytest.fixture
def policy(tmp_path: Path) -> Policy:
    return Policy(job_root=tmp_path)


class _StubRE:
    """Stub RE client — records the last exec, returns canned output."""

    def __init__(self):
        self.last = None

    def exec(self, command: str, project: str = "", timeout: int = 120) -> dict:
        self.last = {"command": command, "project": project}
        return {"exit_code": 0, "stdout": f"ran: {command}", "stderr": ""}


def test_read_write_edit(policy: Policy, tmp_path: Path):
    assert "OK" in tool_write(policy, path="a.txt", content="line0\nline1\n")
    assert "line1" in tool_read(policy, path="a.txt")
    assert "OK" in tool_edit(policy, path="a.txt", old_text="line1", new_text="X")
    assert "X" in (tmp_path / "a.txt").read_text()


def test_edit_multiple_matches(policy: Policy, tmp_path: Path):
    (tmp_path / "d.txt").write_text("aa\naa\n")
    assert "2 times" in tool_edit(policy, path="d.txt", old_text="aa", new_text="b")


def test_bash_container_routes_to_re(policy: Policy):
    stub = _StubRE()
    out = tool_bash(
        policy, command="readelf -h x", target="container", re_client=stub, project="j1"
    )
    assert "ran: readelf -h x" in out
    assert stub.last == {"command": "readelf -h x", "project": "j1"}


def test_bash_host_denied_by_default(policy: Policy):
    out = tool_bash(policy, command="otool -l x", target="host")
    assert "DENIED" in out and "allow_host_exec" in out


def test_bash_host_allowed_when_enabled(tmp_path: Path):
    pol = Policy(job_root=tmp_path, allow_host_exec=True)
    out = tool_bash(pol, command="echo hi", target="host")
    assert "hi" in out


def test_bash_container_no_client(policy: Policy):
    out = tool_bash(policy, command="x", target="container", re_client=None)
    assert "ERROR" in out


def test_dispatch_unknown(policy: Policy):
    assert "unknown tool" in run_tool(policy, "nope", {})


def test_schemas(policy: Policy):
    names = {s["function"]["name"] for s in get_schemas()}
    assert names == {"read", "write", "edit", "bash"}
    bash_schema = next(s for s in get_schemas() if s["function"]["name"] == "bash")
    assert "target" in bash_schema["function"]["parameters"]["properties"]
