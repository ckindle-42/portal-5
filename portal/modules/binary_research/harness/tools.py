"""Harness tools: read, write, edit, bash (container|host)."""

from __future__ import annotations

import os
import subprocess

from .policy import Policy
from .re_client import REClient, REClientError


def _tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "Read a text file under the project directory (offset/limit paging).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under the project dir.",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Start line (0-indexed).",
                            "default": 0,
                        },
                        "limit": {"type": "integer", "description": "Max lines.", "default": 200},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write",
                "description": "Create or overwrite a file under the project directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under the project dir.",
                        },
                        "content": {"type": "string", "description": "File content."},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit",
                "description": "Exact-string replace in a file. old_text must appear exactly once.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under the project dir.",
                        },
                        "old_text": {"type": "string", "description": "Exact text to find (once)."},
                        "new_text": {"type": "string", "description": "Replacement text."},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": (
                    "Run a shell command. target='container' (default) runs inside the RE toolchain "
                    "(radare2/binwalk/yara/readelf/LIEF/...) for ELF/PE/firmware/generic. target='host' "
                    "runs on the macOS host for Mach-O tools (otool/codesign/lipo) if policy allows."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command."},
                        "target": {
                            "type": "string",
                            "enum": ["container", "host"],
                            "description": "Where to run. Default 'container'.",
                            "default": "container",
                        },
                    },
                    "required": ["command"],
                },
            },
        },
    ]


def tool_read(policy: Policy, *, path: str, offset: int = 0, limit: int = 200) -> str:
    try:
        resolved = policy.resolve_path(path)
    except PermissionError as exc:
        return f"ERROR: {exc}"
    if not resolved.is_file():
        return f"ERROR: {path!r} is not a file or does not exist."
    try:
        lines = resolved.read_text(errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        return f"ERROR reading {path!r}: {exc}"
    selected = lines[offset : offset + limit]
    return policy.truncate(
        f"[{path}] lines {offset}–{offset + len(selected) - 1} of {len(lines)}\n"
        + "\n".join(selected)
    )


def tool_write(policy: Policy, *, path: str, content: str) -> str:
    try:
        resolved = policy.resolve_path(path)
    except PermissionError as exc:
        return f"ERROR: {exc}"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)
    return f"OK: wrote {len(content)} chars to {path}"


def tool_edit(policy: Policy, *, path: str, old_text: str, new_text: str) -> str:
    try:
        resolved = policy.resolve_path(path)
    except PermissionError as exc:
        return f"ERROR: {exc}"
    if not resolved.is_file():
        return f"ERROR: {path!r} does not exist."
    text = resolved.read_text()
    count = text.count(old_text)
    if count == 0:
        return f"ERROR: old_text not found in {path!r}."
    if count > 1:
        return f"ERROR: old_text appears {count} times in {path!r} (must be exactly 1)."
    resolved.write_text(text.replace(old_text, new_text, 1))
    return f"OK: replaced {len(old_text)} chars with {len(new_text)} chars in {path}"


def _bash_host(policy: Policy, command: str) -> str:
    if not policy.allow_host_exec:
        return (
            "DENIED: target='host' requires allow_host_exec policy (Mach-O escape hatch). "
            "Use target='container' for ELF/PE/firmware/generic analysis."
        )
    denial = policy.check_bash(command)
    if denial:
        return denial
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(policy.job_root),
            capture_output=True,
            text=True,
            timeout=policy.tool_timeout_sec,
            env={**os.environ, "LC_ALL": "C"},
        )
        parts = []
        if proc.stdout:
            parts.append(proc.stdout)
        if proc.stderr:
            parts.append(f"[stderr]\n{proc.stderr}")
        if proc.returncode != 0:
            parts.append(f"[exit code: {proc.returncode}]")
        return policy.truncate("\n".join(parts) if parts else "(no output)")
    except subprocess.TimeoutExpired:
        return f"TIMEOUT: host command exceeded {policy.tool_timeout_sec}s."
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


def _bash_container(policy: Policy, command: str, re_client: REClient, project: str) -> str:
    denial = policy.check_bash(command)
    if denial:
        return denial
    try:
        res = re_client.exec(command=command, project=project, timeout=policy.tool_timeout_sec)
    except REClientError as exc:
        return (
            f"ERROR: RE toolchain MCP unreachable ({exc}). Is the binresearch MCP up on port 8930? "
            f"Start the stack and run: ./launch.sh build-binresearch"
        )
    parts = []
    if res.get("stdout"):
        parts.append(res["stdout"])
    if res.get("stderr"):
        parts.append(f"[stderr]\n{res['stderr']}")
    if res.get("exit_code"):
        parts.append(f"[exit code: {res['exit_code']}]")
    return policy.truncate("\n".join(parts) if parts else "(no output)")


def tool_bash(
    policy: Policy,
    *,
    command: str,
    target: str = "container",
    re_client: REClient | None = None,
    project: str = "",
) -> str:
    if target == "host":
        return _bash_host(policy, command)
    if re_client is None:
        return "ERROR: container target requested but no RE client configured."
    return _bash_container(policy, command, re_client, project)


_DISPATCH = {"read": tool_read, "write": tool_write, "edit": tool_edit, "bash": tool_bash}


def run_tool(
    policy: Policy,
    name: str,
    arguments: dict,
    *,
    re_client: REClient | None = None,
    project: str = "",
) -> str:
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"ERROR: unknown tool {name!r}. Available: {sorted(_DISPATCH)}"
    if name == "bash":
        return tool_bash(policy, re_client=re_client, project=project, **arguments)
    return fn(policy, **arguments)


def get_schemas() -> list[dict]:
    return _tool_schemas()
