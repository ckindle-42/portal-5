"""Binary Research toolchain MCP server (port 8930).

Owns portal5-binresearch and exposes the static-RE toolchain to the harness.
The harness bash tool (target=container) POSTs here; commands run inside the
container with the named project bind-mounted at /work.

Projects live under BINRESEARCH_JOBS_DIR on DinD's filesystem (the host
projects root is bind-mounted into DinD read-write by docker-compose). Mounting
by name means a brand-new project is immediately usable — no per-project wiring.

Static analysis only. Network disabled. No emulation tools in the image.
Start with: python -m portal.modules.binary_research.tools.binresearch_mcp
"""

from __future__ import annotations

import asyncio
import logging
import os

from mcp.server import MCPServer
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

mcp = MCPServer("binresearch")

BINRESEARCH_IMAGE = os.getenv("BINRESEARCH_IMAGE", "portal5-binresearch:latest")
BINRESEARCH_MEMORY = os.getenv("BINRESEARCH_MEMORY", "4g")
BINRESEARCH_CPUS = os.getenv("BINRESEARCH_CPUS", "2.0")
BINRESEARCH_TIMEOUT = int(os.getenv("BINRESEARCH_TIMEOUT", "120"))
BINRESEARCH_TIMEOUT_MAX = int(os.getenv("BINRESEARCH_TIMEOUT_MAX", "600"))
BINRESEARCH_OUTPUT_MAX = int(os.getenv("BINRESEARCH_OUTPUT_MAX", "1000000"))
# Projects root on DinD's filesystem (host root bind-mounted here by compose).
BINRESEARCH_JOBS_DIR = os.getenv("BINRESEARCH_JOBS_DIR", "/binresearch-projects")
DOCKER_HOST = os.environ.get("DOCKER_HOST", "")

_DECLARED_TOOLS = [
    "radare2",
    "rizin",
    "objdump",
    "nm",
    "readelf",
    "strings",
    "size",
    "llvm-objdump",
    "file",
    "xxd",
    "binwalk",
    "unblob",
    "unsquashfs",
    "yara",
    "ssdeep",
    "apktool",
    "jadx",
    "openssl",
    "hashdeep",
    "python3",
]
_DECLARED_PYLIBS = ["lief", "capstone", "pefile", "macholib", "ropper", "tlsh"]


def _docker_env() -> dict:
    env = os.environ.copy()
    if DOCKER_HOST:
        env["DOCKER_HOST"] = DOCKER_HOST
    return env


def _safe_project(name: str) -> str:
    """Reject path traversal in the project name (mounted into the container)."""
    if not name:
        return ""
    if "/" in name or "\\" in name or name.startswith(".."):
        raise ValueError(f"unsafe project name: {name!r}")
    return name


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok", "service": "binresearch-mcp", "image": BINRESEARCH_IMAGE})


@mcp.custom_route("/ready", methods=["GET"])
async def ready(request):
    return JSONResponse({"ready": True})


async def _docker_run(inner: list[str], timeout: int, project: str | None) -> dict:
    """Run one command in the RE container. project mounts <root>/<project> rw."""
    run_args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        BINRESEARCH_CPUS,
        "--memory",
        BINRESEARCH_MEMORY,
        "--pids-limit",
        "128",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
    ]
    if project:
        src = f"{BINRESEARCH_JOBS_DIR}/{project}"
        run_args += ["-v", f"{src}:/work:rw", "-w", "/work"]
    run_args += [BINRESEARCH_IMAGE, *inner]

    try:
        proc = await asyncio.create_subprocess_exec(
            *run_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_docker_env(),
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "exit_code": proc.returncode,
            "stdout": out.decode(errors="replace")[:BINRESEARCH_OUTPUT_MAX],
            "stderr": err.decode(errors="replace")[:BINRESEARCH_OUTPUT_MAX],
        }
    except TimeoutError:
        return {"exit_code": -1, "stdout": "", "stderr": f"TIMEOUT after {timeout}s"}
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": -1, "stdout": "", "stderr": f"ERROR: {exc}"}


@mcp.tool()
async def re_exec(command: str, project: str = "", timeout: int = BINRESEARCH_TIMEOUT) -> dict:
    """Run a shell command inside the RE toolchain container against a project."""
    try:
        p = _safe_project(project)
    except ValueError as exc:
        return {"exit_code": -1, "stdout": "", "stderr": f"ERROR: {exc}"}
    t = min(int(timeout), BINRESEARCH_TIMEOUT_MAX)
    return await _docker_run(["bash", "-lc", command], t, p or None)


@mcp.tool()
async def re_python(code: str, project: str = "", timeout: int = BINRESEARCH_TIMEOUT) -> dict:
    """Run Python inside the RE container (LIEF/capstone/pefile available)."""
    try:
        p = _safe_project(project)
    except ValueError as exc:
        return {"exit_code": -1, "stdout": "", "stderr": f"ERROR: {exc}"}
    t = min(int(timeout), BINRESEARCH_TIMEOUT_MAX)
    return await _docker_run(["python3", "-c", code], t, p or None)


@mcp.tool()
async def re_tools() -> dict:
    """Verify the declared toolchain is present inside the container."""
    check = "; ".join(
        [f"command -v {t} >/dev/null && echo '{t}:yes' || echo '{t}:no'" for t in _DECLARED_TOOLS]
        + [
            f"python3 -c 'import {lib}' 2>/dev/null && echo 'py:{lib}:yes' || echo 'py:{lib}:no'"
            for lib in _DECLARED_PYLIBS
        ]
    )
    res = await _docker_run(["bash", "-lc", check], 60, None)
    present, missing = [], []
    for line in res["stdout"].splitlines():
        if line.endswith(":yes"):
            present.append(line.rsplit(":", 1)[0])
        elif line.endswith(":no"):
            missing.append(line.rsplit(":", 1)[0])
    return {"image": BINRESEARCH_IMAGE, "present": present, "missing": missing}


@mcp.custom_route("/tools/re_exec", methods=["POST"])
async def re_exec_endpoint(request):
    args = (await request.json()).get("arguments", {})
    command = args.get("command", "")
    if not command:
        return JSONResponse({"error": "command is required"}, status_code=400)
    return JSONResponse(
        await re_exec(
            command=command,
            project=args.get("project", ""),
            timeout=int(args.get("timeout", BINRESEARCH_TIMEOUT)),
        )
    )


@mcp.custom_route("/tools/re_python", methods=["POST"])
async def re_python_endpoint(request):
    args = (await request.json()).get("arguments", {})
    code = args.get("code", "")
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)
    return JSONResponse(
        await re_python(
            code=code,
            project=args.get("project", ""),
            timeout=int(args.get("timeout", BINRESEARCH_TIMEOUT)),
        )
    )


@mcp.custom_route("/tools/re_tools", methods=["POST"])
async def re_tools_endpoint(request):
    return JSONResponse(await re_tools())


if __name__ == "__main__":
    port = int(os.getenv("BINRESEARCH_MCP_PORT", "8930"))
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
