"""
Code Execution Sandbox MCP Server
Runs Python, Node.js, and Bash code in Docker containers with isolation.

Security:
- Network disabled (network_mode: none)
- CPU and memory limits enforced
- Execution timeout (default 30s)
- No host filesystem access beyond /tmp

Requires: Docker running, SANDBOX_ENABLED=true in config
Start with: python -m mcp.execution.code_sandbox_mcp
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path

from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("code-sandbox")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "sandbox-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "execute_python",
        "description": "Execute Python code in an isolated Docker container",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["code"],
        },
    },
    {
        "name": "execute_nodejs",
        "description": "Execute Node.js code in an isolated Docker container",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Node.js code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["code"],
        },
    },
    {
        "name": "execute_bash",
        "description": "Execute Bash commands in an isolated Docker container",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "sandbox_status",
        "description": "Check if the code sandbox (Docker/DinD) is available",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


logger = logging.getLogger(__name__)

SANDBOX_DIR = Path(os.getenv("SANDBOX_DIR", "data/sandbox"))
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "30"))
PYTHON_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")
NODE_IMAGE = os.getenv("SANDBOX_NODE_IMAGE", "node:20-alpine")
BASH_IMAGE = os.getenv("SANDBOX_BASH_IMAGE", "alpine:latest")
MAX_OUTPUT_BYTES = 50_000  # 50KB output cap

# DOCKER_HOST — for DinD setups, use tcp://dind:2375
# The docker CLI automatically reads this env var
DOCKER_HOST = os.environ.get("DOCKER_HOST", "")


def _get_docker_env() -> dict:
    """Get environment for docker commands, including DOCKER_HOST if set."""
    env = os.environ.copy()
    if DOCKER_HOST:
        env["DOCKER_HOST"] = DOCKER_HOST
    return env


async def _run_in_docker(
    image: str,
    stdin_cmd: list[str],
    code: str,
    timeout: int,
) -> dict:
    """Run code in a Docker container with isolation constraints via stdin."""
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-i",  # stdin
        "--network",
        "none",  # No network access
        "--cpus",
        "0.5",  # Max 0.5 CPU
        "--memory",
        "256m",  # Max 256MB RAM
        "--pids-limit",
        "64",  # Max 64 processes
        "--security-opt",
        "no-new-privileges",  # Prevent privilege escalation
        "--cap-drop",
        "ALL",  # Drop all Linux capabilities
        "--read-only",  # Read-only root filesystem
        "--tmpfs",
        "/tmp:size=64m",  # 64MB /tmp
        image,
    ] + stdin_cmd

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            env=_get_docker_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=code.encode("utf-8")), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "exit_code": -1,
                "timed_out": True,
            }

        stdout_text = stdout[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        stderr_text = stderr[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        return {
            "success": proc.returncode == 0,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": proc.returncode,
            "timed_out": False,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Docker not found. Ensure Docker is installed and running.",
            "exit_code": -1,
            "timed_out": False,
        }


@mcp.tool()
async def execute_python(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute Python code in an isolated Docker sandbox.

    Security constraints: no network, 256MB RAM, 0.5 CPU, 30s timeout,
    read-only filesystem, no Linux capabilities, no privilege escalation.
    Python standard library only — no pip, no network, no third-party packages.

    Args:
        code: Python code to execute
        timeout: Execution timeout in seconds (default 30, max 120)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, 120)
    # Use stdin to avoid Linux Docker file-mount limitation
    return await _run_in_docker(
        image=PYTHON_IMAGE,
        stdin_cmd=["python3", "-c", "import sys; exec(sys.stdin.read())"],
        code=code,
        timeout=timeout,
    )


@mcp.tool()
async def execute_nodejs(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute JavaScript/Node.js code in an isolated Docker sandbox.

    Security constraints: no network, 256MB RAM, 0.5 CPU, 30s timeout,
    read-only filesystem, no Linux capabilities, no privilege escalation.
    Node.js standard libraries available; no npm packages.

    Args:
        code: JavaScript code to execute
        timeout: Execution timeout in seconds (default 30, max 120)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, 120)
    # Use stdin to avoid Linux Docker file-mount limitation
    return await _run_in_docker(
        image=NODE_IMAGE,
        stdin_cmd=["node", "-e", "eval(require('fs').readFileSync('/dev/stdin','utf8'))"],
        code=code,
        timeout=timeout,
    )


@mcp.tool()
async def execute_bash(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute a Bash script in an isolated Docker sandbox.

    Security constraints: no network, 256MB RAM, 0.5 CPU, 30s timeout,
    read-only filesystem, no Linux capabilities, no privilege escalation.
    Common Unix utilities available (Alpine-based). No sudo, no network.

    Args:
        code: Bash script to execute
        timeout: Execution timeout in seconds (default 30, max 60)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, 60)  # Stricter timeout for shell
    # Use stdin to avoid Linux Docker file-mount limitation
    return await _run_in_docker(
        image=BASH_IMAGE,
        stdin_cmd=["sh"],
        code=code,
        timeout=timeout,
    )


@mcp.tool()
async def sandbox_status() -> dict:
    """Check sandbox availability (Docker daemon and image availability)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_get_docker_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        docker_available = proc.returncode == 0
    except (FileNotFoundError, TimeoutError):
        docker_available = False

    return {
        "docker_available": docker_available,
        "docker_host": DOCKER_HOST or "unix:///var/run/docker.sock",
        "sandbox_enabled": os.getenv("SANDBOX_ENABLED", "false").lower() == "true",
        "python_image": PYTHON_IMAGE,
        "node_image": NODE_IMAGE,
        "bash_image": BASH_IMAGE,
        "timeout_seconds": DEFAULT_TIMEOUT,
        "constraints": {
            "network": "disabled",
            "memory_mb": 256,
            "cpu_fraction": 0.5,
            "pids_limit": 64,
            "security_opt": "no-new-privileges",
            "cap_drop": "ALL",
        },
    }


if __name__ == "__main__":
    port = int(os.getenv("SANDBOX_MCP_PORT", "8914"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
