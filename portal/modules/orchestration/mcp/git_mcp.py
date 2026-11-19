"""Git MCP for the Pipeline tool loop (:8950, host-native).

``git_status`` / ``git_log`` / ``git_diff`` are read-only; ``git_commit`` and
``git_push`` are confirm-gated by the Jarvis personal policy. The server never
operates on the live Portal checkout it is deployed from — Jarvis git work
belongs in worktrees and other repos, and the guard makes that a server-side
rule, not a caller promise. Optional ``GIT_MCP_ALLOW_ROOT`` narrows every call
to one directory tree.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

GIT_MCP_PORT = int(os.getenv("GIT_MCP_PORT", "8950"))
_CALL_TIMEOUT_S = float(os.getenv("GIT_MCP_CALL_TIMEOUT_S", "60"))
_FIELD_SEP = "\x1f"
_IDENTITY = ("-c", "user.name=jarvis-git-mcp", "-c", "user.email=jarvis@portal5.local")


class _TypedMCPServer(MCPServer):
    def custom_route(
        self,
        path: str,
        methods: list[str],
        name: str | None = None,
        include_in_schema: bool = True,
    ) -> Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]]:
        return cast(
            Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
            super().custom_route(path, methods, name=name, include_in_schema=include_in_schema),
        )


mcp = _TypedMCPServer("git")


def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def _err(exc: Exception) -> dict[str, Any]:
    return {"success": False, "error": str(exc)}


def _live_checkout() -> Path:
    """The Portal checkout this server is deployed from (holds config/portal.yaml)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "portal.yaml").is_file():
            return parent
    return Path(__file__).resolve().parents[4]


def _resolve_repo(repo_path: str) -> Path:
    """One caller-named repo path, or ValueError. Never the live checkout."""
    path = Path(repo_path).expanduser()
    if not path.is_absolute():
        raise ValueError("repo_path must be absolute")
    resolved = path.resolve()
    live = _live_checkout().resolve()
    if resolved == live or resolved.is_relative_to(live):
        raise ValueError("the git MCP never operates on the live Portal checkout")
    allow = os.getenv("GIT_MCP_ALLOW_ROOT", "")
    if allow:
        root = Path(allow).expanduser().resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"repo_path outside GIT_MCP_ALLOW_ROOT {root}")
    return resolved


def _safe(value: str) -> str:
    """Reject argument values that could read as a git flag."""
    if not value or value.startswith("-"):
        raise ValueError(f"invalid git argument: {value!r}")
    return value


async def _git(repo: Path, *args: str) -> dict[str, Any]:
    """Run one git command in the repo and wrap its result."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(repo),
        *_IDENTITY,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CALL_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        return {"success": False, "error": f"git {' '.join(args)} timed out"}
    if proc.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        return {"success": False, "error": detail[-400:] or f"git exit {proc.returncode}"}
    return {"success": True, "data": stdout.decode(errors="replace")}


async def _run_repo_tool(
    repo_path: str, run: Callable[[Path], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    try:
        return await run(_resolve_repo(repo_path))
    except (ValueError, OSError) as exc:
        return _err(exc)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "git-mcp", "port": GIT_MCP_PORT})


# ── Read-only tools (open to Jarvis; no confirm) ──────────────────────────────


@mcp.tool()
async def git_status(repo_path: str) -> dict[str, Any]:
    """
    Working-tree status of one repository: branch line plus porcelain entries.

    Args:
        repo_path: Absolute path of the git repository to inspect.
    """
    return await _run_repo_tool(
        repo_path, lambda repo: _git(repo, "status", "--porcelain=v1", "-b")
    )


@mcp.tool()
async def git_log(repo_path: str, max_count: int = 10) -> dict[str, Any]:
    """
    Recent commits as sha / author / date / subject records.

    Args:
        repo_path: Absolute path of the git repository to inspect.
        max_count: How many commits to return (default 10).
    """
    count = max(1, min(int(max_count), 100))

    async def run(repo: Path) -> dict[str, Any]:
        result = await _git(
            repo,
            "log",
            f"-n{count}",
            f"--format=%H{_FIELD_SEP}%an{_FIELD_SEP}%ad{_FIELD_SEP}%s",
        )
        if not result["success"]:
            return result
        commits = []
        for line in str(result["data"]).splitlines():
            if not line.strip():
                continue
            sha, author, date, subject = line.split(_FIELD_SEP, 3)
            commits.append({"sha": sha, "author": author, "date": date, "subject": subject})
        return _ok(commits)

    return await _run_repo_tool(repo_path, run)


@mcp.tool()
async def git_diff(repo_path: str) -> dict[str, Any]:
    """
    Combined staged and unstaged diff of the working tree against HEAD.

    Args:
        repo_path: Absolute path of the git repository to inspect.
    """
    return await _run_repo_tool(repo_path, lambda repo: _git(repo, "diff", "HEAD"))


# ── Confirm-gated tools (the Jarvis policy asks before these run) ───────────


@mcp.tool()
async def git_commit(
    repo_path: str, message: str, files: list[str] | None = None
) -> dict[str, Any]:
    """
    Stage the named files (optional) and commit the repository.

    Args:
        repo_path: Absolute path of the git repository to change.
        message: Commit message; required and non-empty.
        files: Optional paths (repo-relative) to stage before committing.
    """

    async def run(repo: Path) -> dict[str, Any]:
        if not message.strip():
            return _err(ValueError("message must be non-empty"))
        for name in files or []:
            _safe(name)
        if files:
            staged = await _git(repo, "add", "--", *files)
            if not staged["success"]:
                return staged
        return await _git(repo, "commit", "-m", message)

    return await _run_repo_tool(repo_path, run)


@mcp.tool()
async def git_push(repo_path: str, remote: str = "origin", branch: str = "") -> dict[str, Any]:
    """
    Push the current HEAD of one repository to a remote.

    Args:
        repo_path: Absolute path of the git repository to push.
        remote: Remote name (default origin).
        branch: Optional target branch; HEAD is pushed to this branch name.
    """

    async def run(repo: Path) -> dict[str, Any]:
        target = f"HEAD:refs/heads/{_safe(branch)}" if branch else "HEAD"
        return await _git(repo, "push", _safe(remote), target)

    return await _run_repo_tool(repo_path, run)


if __name__ == "__main__":
    # Same direct-kwargs pattern every other MCP server in this repo uses.
    mcp.run(transport="streamable-http", host="0.0.0.0", port=GIT_MCP_PORT)
