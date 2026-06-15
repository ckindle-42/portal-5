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

mcp = FastMCP("code-sandbox", host="0.0.0.0")


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
        "name": "execute_powershell",
        "description": "Execute a PowerShell script in an isolated Docker container (pwsh on Alpine)",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "PowerShell script to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
            },
            "required": ["code"],
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

# Opt-in network access (DEFAULT OFF — production posture unchanged).
# Set SANDBOX_ALLOW_NETWORK=true ONLY for capability-probe test runs that need
# pip install / real dependencies (TASK_CODING_CAPABILITY_PROBE_V1 A2). When
# enabled the resource envelope is widened so pip has room; otherwise the
# sandbox is byte-for-byte its locked-down self.
SANDBOX_ALLOW_NETWORK = os.getenv("SANDBOX_ALLOW_NETWORK", "false").lower() == "true"
SANDBOX_NET_MEMORY = os.getenv("SANDBOX_NET_MEMORY", "1g")
SANDBOX_NET_CPUS = os.getenv("SANDBOX_NET_CPUS", "1.0")
SANDBOX_NET_TIMEOUT_MAX = int(os.getenv("SANDBOX_NET_TIMEOUT_MAX", "300"))

# PowerShell image — portal5-pwsh:latest is a native arm64 image built from
# Dockerfile.pwsh (ubuntu:22.04 + Microsoft pwsh apt package). Falls back to
# the amd64-only MCR Alpine image if the local build hasn't been done yet.
# Override with SANDBOX_PS_IMAGE env var.
PS_IMAGE = os.getenv("SANDBOX_PS_IMAGE", "portal5-pwsh:latest")

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
    command: list[str],
    code: str,
    timeout: int,
    extra_args: list[str] | None = None,
) -> dict:
    """Run code in a Docker container with isolation constraints."""
    run_id = uuid.uuid4().hex[:8]
    work_dir = SANDBOX_DIR / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Write code to temp file
    code_file = work_dir / "code"
    code_file.write_text(code, encoding="utf-8")

    # Network + resource envelope: locked down by default; widened only when
    # SANDBOX_ALLOW_NETWORK=true (capability-probe runs). See A2.
    _net = "bridge" if SANDBOX_ALLOW_NETWORK else "none"
    _cpus = SANDBOX_NET_CPUS if SANDBOX_ALLOW_NETWORK else "0.5"
    _mem = SANDBOX_NET_MEMORY if SANDBOX_ALLOW_NETWORK else "256m"
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        _net,  # "none" by default; "bridge" only under SANDBOX_ALLOW_NETWORK
        "--cpus",
        _cpus,  # 0.5 default; SANDBOX_NET_CPUS when network-enabled
        "--memory",
        _mem,  # 256m default; SANDBOX_NET_MEMORY when network-enabled
        "--pids-limit",
        "64",  # Max 64 processes
        "--security-opt",
        "no-new-privileges",  # Prevent privilege escalation
        "--cap-drop",
        "ALL",  # Drop all Linux capabilities
        "--read-only",  # Read-only root filesystem
        "--tmpfs",
        "/tmp:size=64m",  # 64MB /tmp
    ] + (
        # pip writes to /root/.local; needs a writable home when network-enabled.
        # PYTHONPATH set so user-installed packages are importable immediately
        # (user site isn't in sys.path at startup when the dir doesn't exist yet).
        [
            "--tmpfs", "/root:size=256m,exec",  # exec needed for C-extension .so files
            "--env", "PYTHONPATH=/root/.local/lib/python3.11/site-packages",
        ] if SANDBOX_ALLOW_NETWORK else []
    ) + (extra_args or []) + [
        "-v",
        f"{code_file.absolute()}:/code:ro",
        image,
    ] + command

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_get_docker_env(),
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
    timeout = min(timeout, SANDBOX_NET_TIMEOUT_MAX if SANDBOX_ALLOW_NETWORK else 120)
    # Use file-based execution to avoid shell escaping issues
    return await _run_in_docker(
        image=PYTHON_IMAGE,
        command=["python", "/code"],
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
    timeout = min(timeout, SANDBOX_NET_TIMEOUT_MAX if SANDBOX_ALLOW_NETWORK else 120)
    # Use file-based execution to avoid shell escaping issues
    return await _run_in_docker(
        image=NODE_IMAGE,
        command=["node", "/code"],
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
    # Use file-based execution to avoid shell escaping issues
    return await _run_in_docker(
        image=BASH_IMAGE,
        command=["sh", "/code"],
        code=code,
        timeout=timeout,
    )


@mcp.tool()
async def execute_powershell(
    code: str,
    timeout: int = 60,
) -> dict:
    """
    Execute a PowerShell script in an isolated Docker sandbox (pwsh on Ubuntu arm64).

    Uses portal5-pwsh:latest — a native arm64 image built from Dockerfile.pwsh
    (pwsh 7.4 LTS on Ubuntu 22.04). No Windows-specific subsystems (WMI, COM,
    registry) — cross-platform PS Core only. Same security constraints as
    execute_python: no network by default, 256MB RAM.

    Args:
        code: PowerShell script to execute
        timeout: Execution timeout in seconds (default 60, max 120)

    Returns:
        dict with success, stdout, stderr, exit_code, timed_out
    """
    timeout = min(timeout, SANDBOX_NET_TIMEOUT_MAX if SANDBOX_ALLOW_NETWORK else 120)
    return await _run_in_docker(
        image=PS_IMAGE,
        command=["pwsh", "-NonInteractive", "-File", "/code"],
        code=code,
        timeout=timeout,
        # pwsh writes cache/config to ~/.cache and ~/.config on startup;
        # these don't exist in a read-only root filesystem, so provide a
        # writable tmpfs for /root to prevent TypeInitializationException.
        extra_args=["--tmpfs", "/root:size=64m"],
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
        "ps_image": PS_IMAGE,
        "timeout_seconds": DEFAULT_TIMEOUT,
        "constraints": {
            "network": "bridge" if SANDBOX_ALLOW_NETWORK else "disabled",
            "memory_mb": 256,
            "cpu_fraction": 0.5,
            "pids_limit": 64,
            "security_opt": "no-new-privileges",
            "cap_drop": "ALL",
        },
    }


# ---------------------------------------------------------------------------
# REST dispatch endpoints — called by portal-pipeline tool_registry.py via
# POST /tools/<tool_name> with body {"arguments": {...}, "request_id": "..."}
# ---------------------------------------------------------------------------


@mcp.custom_route("/tools/execute_python", methods=["POST"])
async def execute_python_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    code = args.get("code", "")
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)
    timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), 120)
    result = await execute_python(code=code, timeout=timeout)
    return JSONResponse(result)


@mcp.custom_route("/tools/execute_nodejs", methods=["POST"])
async def execute_nodejs_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    code = args.get("code", "")
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)
    timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), 120)
    result = await execute_nodejs(code=code, timeout=timeout)
    return JSONResponse(result)


@mcp.custom_route("/tools/execute_bash", methods=["POST"])
async def execute_bash_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    # Accept both 'code' (FastMCP schema) and 'command' (legacy/GLM tool call format)
    code = args.get("code") or args.get("command", "")
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)
    timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), 60)
    # If the script is invoking Python directly, route to execute_python for
    # guaranteed Python availability (Alpine bash image lacks python3).
    stripped = code.strip()
    if stripped.startswith("python3 -c ") or stripped.startswith("python -c "):
        # Extract the inline code from the python3 -c "..." invocation
        import shlex

        try:
            parts = shlex.split(stripped)
            py_code = parts[2] if len(parts) >= 3 else ""
        except Exception:
            py_code = ""
        if py_code:
            result = await execute_python(code=py_code, timeout=min(timeout, SANDBOX_NET_TIMEOUT_MAX if SANDBOX_ALLOW_NETWORK else 120))
            return JSONResponse(result)
    result = await execute_bash(code=code, timeout=timeout)
    return JSONResponse(result)


@mcp.custom_route("/tools/execute_powershell", methods=["POST"])
async def execute_powershell_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    code = args.get("code", "")
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)
    timeout = min(int(args.get("timeout", 60)), 120)
    result = await execute_powershell(code=code, timeout=timeout)
    return JSONResponse(result)


@mcp.custom_route("/tools/sandbox_status", methods=["POST"])
async def sandbox_status_endpoint(request):
    result = await sandbox_status()
    return JSONResponse(result)


if __name__ == "__main__":
    port = int(os.getenv("SANDBOX_MCP_PORT", "8914"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
