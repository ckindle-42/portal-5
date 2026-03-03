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


async def _run_in_docker(
    image: str,
    command: list[str],
    code: str,
    timeout: int,
) -> dict:
    """Run code in a Docker container with isolation constraints."""
    run_id = uuid.uuid4().hex[:8]
    work_dir = SANDBOX_DIR / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Write code to temp file
    code_file = work_dir / "code"
    code_file.write_text(code, encoding="utf-8")

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",  # No network access
        "--cpus",
        "0.5",  # Max 0.5 CPU
        "--memory",
        "256m",  # Max 256MB RAM
        "--pids-limit",
        "64",  # Max 64 processes
        "--read-only",  # Read-only root filesystem
        "--tmpfs",
        "/tmp:size=64m",  # 64MB /tmp
        "-v",
        f"{code_file.absolute()}:/code:ro",
        image,
    ] + command

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
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
    finally:
        # Clean up temp files
        try:
            code_file.unlink(missing_ok=True)
            work_dir.rmdir()
        except OSError:
            pass


@mcp.tool()
async def run_python(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute Python code in an isolated Docker sandbox.

    Security constraints: no network, 256MB RAM, 0.5 CPU, 30s timeout.
    Standard library available; no third-party packages by default.
    Use run_python_with_packages for code requiring external libraries.

    Args:
        code: Python code to execute
        timeout: Execution timeout in seconds (default 30, max 120)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, 120)
    # Use file-based execution to avoid shell escaping issues
    return await _run_in_docker(
        image=PYTHON_IMAGE,
        command=["python", "/code"],
        code=code,
        timeout=timeout,
    )


@mcp.tool()
async def run_node(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute JavaScript/Node.js code in an isolated Docker sandbox.

    Security constraints: no network, 256MB RAM, 0.5 CPU, 30s timeout.
    Node.js standard libraries available; no npm packages.

    Args:
        code: JavaScript code to execute
        timeout: Execution timeout in seconds (default 30, max 120)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, 120)
    # Use file-based execution to avoid shell escaping issues
    return await _run_in_docker(
        image=NODE_IMAGE,
        command=["node", "/code"],
        code=code,
        timeout=timeout,
    )


@mcp.tool()
async def run_bash(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute a Bash script in an isolated Docker sandbox.

    Security constraints: no network, 256MB RAM, 0.5 CPU, 30s timeout.
    Common Unix utilities available (Alpine-based). No sudo, no network.

    Args:
        code: Bash script to execute
        timeout: Execution timeout in seconds (default 30, max 60)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, 60)  # Stricter timeout for shell
    # Use file-based execution to avoid shell escaping issues
    return await _run_in_docker(
        image=BASH_IMAGE,
        command=["sh", "/code"],
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
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        docker_available = proc.returncode == 0
    except (FileNotFoundError, TimeoutError):
        docker_available = False

    return {
        "docker_available": docker_available,
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
        },
    }


if __name__ == "__main__":
    port = int(os.getenv("SANDBOX_MCP_PORT", "8914"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
