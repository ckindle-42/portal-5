"""FastContext repo tools stay inside the repository."""

from __future__ import annotations

from portal.platform.mcp_host.pipeline_mcp import _dispatch_fastcontext_tool


def test_read_rejects_absolute_and_parent_escape() -> None:
    absolute = _dispatch_fastcontext_tool("READ", {"path": "/etc/passwd"})
    assert absolute.startswith("ERROR: read blocked")
    assert "root:" not in absolute
    escaped = _dispatch_fastcontext_tool("READ", {"path": "../../../../../../etc/passwd"})
    assert escaped.startswith("ERROR: read blocked")


def test_read_allows_a_repo_relative_file() -> None:
    body = _dispatch_fastcontext_tool("READ", {"path": "CLAUDE.md", "end_line": 1})
    assert body.startswith("1\t")
    assert "ERROR" not in body


def test_glob_and_grep_reject_absolute_patterns() -> None:
    globbed = _dispatch_fastcontext_tool("GLOB", {"pattern": "/etc/*"})
    assert globbed.startswith("ERROR: glob blocked")
    grepped = _dispatch_fastcontext_tool("GREP", {"pattern": "root", "glob": "/etc/passwd"})
    assert grepped.startswith("ERROR: glob blocked")
