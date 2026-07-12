"""Portal 5 — Pipeline Status MCP Server.

Gives coding tools (Claude Code, opencode) live introspection of the Portal 5
stack: workspace catalog, backend health, loaded models, and request metrics.

Port: 8928 (configurable via PIPELINE_MCP_PORT env var)

All data is read by calling the pipeline's own HTTP endpoints — this server has
zero imports from portal/platform/inference/. It is registered in .mcp.json so
Claude Code and opencode pick it up automatically when opening the portal-5 project.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PIPELINE_MCP_PORT", 8928))
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
# parents[3]: pipeline_mcp.py → mcp_host/ → platform/ → portal/ → portal-5/
REPO_ROOT = pathlib.Path(
    os.environ.get("PIPELINE_MCP_REPO_ROOT", pathlib.Path(__file__).parents[3])
).resolve()

_FASTCONTEXT_MODEL = "hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M"
_FASTCONTEXT_MAX_TURNS = 6
_FASTCONTEXT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "READ",
            "description": "Return line-numbered contents of a file in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative file path"},
                    "start_line": {
                        "type": "integer",
                        "description": "First line to return (1-indexed, inclusive)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to return (inclusive); omit for entire file",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GLOB",
            "description": "List files matching a glob pattern under the repository root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py' or 'portal/platform/inference/**'",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GREP",
            "description": "Search for a regex pattern across repository files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Python regex pattern to search for",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Limit search to files matching this glob, e.g. '**/*.py'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max matching lines to return (default 40)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]

mcp = FastMCP("portal-pipeline")


def _pipeline_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PIPELINE_API_KEY}"} if PIPELINE_API_KEY else {}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Any) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "pipeline-mcp", "port": PORT})


# ── REST discovery manifest (consumed by portal.platform.inference ToolRegistry) ────────
# The pipeline discovers tools via GET /tools and dispatches via
# POST /tools/{name} with body {"arguments": {...}, "request_id": "..."}.
# This manifest MUST stay in sync with the @mcp.tool() functions below and the
# POST /tools/{name} routes — tests/unit/test_pipeline_mcp_rest.py enforces parity.
TOOLS_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "get_pipeline_status",
        "description": "Return Portal 5 pipeline health: backend count, workspace count, version.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_workspaces",
        "description": "List all Portal 5 workspaces (AI models) with routing metadata. Optional substring filter.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Substring to filter by id or name"}
            },
            "required": [],
        },
    },
    {
        "name": "get_loaded_models",
        "description": "Return which Ollama models are currently loaded in VRAM/RAM with size and expiry.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_metrics_summary",
        "description": "Return key Portal 5 operational metrics from Prometheus (requests, tool calls, errors, TPS).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_workspace_recommendation",
        "description": "Suggest the best Portal 5 workspace for a plain-English task description.",
        "parameters": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Plain-English task"}},
            "required": ["task"],
        },
    },
    {
        "name": "explore_repository",
        "description": "Locate relevant code via the FastContext-4B explorer subagent. Returns file+line citations. Call before editing.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to find in the repo"},
                "max_turns": {"type": "integer", "description": "Exploration turns (default 6)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "trigger_backend_warmup",
        "description": "Pre-load a workspace model into VRAM before a long session.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {
                    "type": "string",
                    "description": "Workspace id (default auto-coding-agentic)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "read_text_file",
        "description": "Read a file from the host filesystem. Accepts absolute paths or repo-relative paths. Returns line-numbered content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or repo-relative file path"},
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-indexed, inclusive)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return (inclusive); omit for entire file",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories at the given path. Returns [FILE]/[DIR] prefixed entries.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or repo-relative directory path",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for a regex pattern across project files. Returns file:line matches.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex or literal string to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search (default: repo root)",
                },
                "glob": {
                    "type": "string",
                    "description": "File glob filter, e.g. '**/*.py' (default: all files)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max matching lines to return (default 50)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file on the host filesystem. Constrained to the repo root and /tmp.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or repo-relative file path to write",
                },
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools_manifest(request: Any) -> JSONResponse:
    return JSONResponse(TOOLS_MANIFEST)


# ── Tools ────────────────────────────────────────────────────────────────────


async def _impl_get_pipeline_status() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{PIPELINE_URL}/health", headers=_pipeline_headers())
            result: dict[str, Any] = r.json()
            return result
        except Exception as e:
            return {"error": str(e), "pipeline_url": PIPELINE_URL}


@mcp.tool()
async def get_pipeline_status() -> dict[str, Any]:
    """Return Portal 5 pipeline health: backend count, workspace count, version.

    Use this before starting any coding task to confirm the stack is up and
    all backends are healthy.
    """
    return await _impl_get_pipeline_status()


@mcp.custom_route("/tools/get_pipeline_status", methods=["POST"])
async def get_pipeline_status_endpoint(request: Any) -> JSONResponse:
    return JSONResponse(await _impl_get_pipeline_status())


async def _impl_list_workspaces(filter: str = "") -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(f"{PIPELINE_URL}/v1/models", headers=_pipeline_headers())
            models = r.json().get("data", [])
            results = []
            for m in models:
                mid = m.get("id", "")
                name = m.get("name", mid)
                desc = (m.get("description") or "")[:120]
                if (
                    filter
                    and filter.lower() not in mid.lower()
                    and filter.lower() not in name.lower()
                ):
                    continue
                results.append({"id": mid, "name": name, "description": desc})
            return sorted(results, key=lambda x: x["id"])
        except Exception as e:
            return [{"error": str(e)}]


@mcp.tool()
async def list_workspaces(filter: str = "") -> list[dict[str, Any]]:
    """List all Portal 5 workspaces (AI models) with their routing metadata.

    Args:
        filter: Optional substring to filter by workspace ID or name
                (e.g. "coding", "security", "agentic")

    Returns list of {id, name, description_snippet} sorted by ID.
    Use this to pick the right workspace for a task before calling the pipeline.
    """
    return await _impl_list_workspaces(filter)


@mcp.custom_route("/tools/list_workspaces", methods=["POST"])
async def list_workspaces_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(await _impl_list_workspaces(args.get("filter", "")))


async def _impl_get_loaded_models() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/ps")
            models = r.json().get("models", [])
            return [
                {
                    "name": m.get("name"),
                    "size_gb": round(m.get("size", 0) / 1e9, 1),
                    "vram_size_gb": round(m.get("size_vram", 0) / 1e9, 1),
                    "expires_at": m.get("expires_at", "")[:19],
                }
                for m in models
            ]
        except Exception as e:
            return [{"error": str(e)}]


@mcp.tool()
async def get_loaded_models() -> list[dict[str, Any]]:
    """Return which Ollama models are currently loaded in VRAM/RAM.

    Shows model name, size, and expiry time. Use this to check if the model
    you need is warm (fast response) or cold (will take time to load).
    """
    return await _impl_get_loaded_models()


@mcp.custom_route("/tools/get_loaded_models", methods=["POST"])
async def get_loaded_models_endpoint(request: Any) -> JSONResponse:
    return JSONResponse(await _impl_get_loaded_models())


async def _impl_get_metrics_summary() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{PIPELINE_URL}/metrics", headers=_pipeline_headers())
            lines = r.text.splitlines()
            summary: dict[str, Any] = {}
            for ln in lines:
                if ln.startswith("#"):
                    continue
                if "portal5_requests_total" in ln and "{" not in ln:
                    summary["requests_total"] = _parse_metric(ln)
                elif "portal5_tool_calls_total{" in ln:
                    key = f"tool_calls__{_extract_label(ln, 'tool')}__{_extract_label(ln, 'workspace')}"
                    summary[key] = _parse_metric(ln)
                elif "portal5_errors_total" in ln and "{" not in ln:
                    summary["errors_total"] = _parse_metric(ln)
                elif "portal5_tps" in ln and "workspace" not in ln and "{" not in ln:
                    summary["avg_tps"] = _parse_metric(ln)
            return summary
        except Exception as e:
            return {"error": str(e)}


@mcp.tool()
async def get_metrics_summary() -> dict[str, Any]:
    """Return key Portal 5 operational metrics from Prometheus.

    Returns request totals, tool call counts, error rates, and TPS.
    Use this to verify that a tool call was dispatched (tool_calls_total
    should increment after a workspace request that invokes execute_bash).
    """
    return await _impl_get_metrics_summary()


@mcp.custom_route("/tools/get_metrics_summary", methods=["POST"])
async def get_metrics_summary_endpoint(request: Any) -> JSONResponse:
    return JSONResponse(await _impl_get_metrics_summary())


async def _impl_get_workspace_recommendation(task: str) -> dict[str, Any]:
    """Suggest the best Portal 5 workspace for a given task description.

    Args:
        task: Plain-English description of the task
              (e.g. "fix a bug in router_pipe.py", "analyze a CVE",
               "generate a Word document", "run a port scan on the lab DC")

    Returns the recommended workspace ID and model, with reasoning.
    """
    task_lower = task.lower()

    rules = [
        (
            [
                "fix",
                "refactor",
                "maintain",
                "advance",
                "run tests",
                "edit",
                "update code",
                "feature",
            ],
            "auto-coding-agentic",
            "Devstral 24B — agentic loop (read→edit→verify)",
        ),
        (
            ["generate code", "write a function", "implement", "one-shot", "snippet"],
            "auto-coding",
            "Qwen3-Coder 30B — one-shot code generation",
        ),
        (
            ["heavy", "codebase", "multi-file", "long-horizon", "swe-agent"],
            "auto-agentic",
            "Qwen3-Coder-Next 80B — full SWE-agent stack",
        ),
        (
            ["pentest", "kerberoast", "impacket", "nmap", "exploit", "attack chain"],
            "auto-purpleteam-exec",
            "SuperGemma4 26B — live execution, calls execute_bash",
        ),
        (
            ["cve", "vulnerability", "security", "threat"],
            "auto-security",
            "BaronLLM — security analysis",
        ),
        (
            ["detect", "sigma", "siem", "blue team", "incident response"],
            "auto-blueteam",
            "Foundation-Sec 8B — detection & IR",
        ),
        (
            ["word document", "excel", "powerpoint", "pdf"],
            "auto-daily",
            "Qwen3-Coder — general + document tools",
        ),
        (
            ["reason", "think", "complex", "math", "proof"],
            "auto-reasoning",
            "Qwopus 27B — extended reasoning",
        ),
        (
            ["splunk", "spl", "tstats", "search"],
            "auto-spl",
            "Qwen3-Coder-Next abliterated — SPL generation",
        ),
    ]

    for keywords, workspace, model_desc in rules:
        if any(kw in task_lower for kw in keywords):
            return {
                "workspace": workspace,
                "model": model_desc,
                "reason": f"matched keywords from task: {[k for k in keywords if k in task_lower]}",
                "pipeline_model_id": workspace,
            }

    return {
        "workspace": "auto-coding-agentic",
        "model": "Devstral 24B (default for portal-5 maintenance)",
        "reason": "no specific keyword match — defaulting to agentic coding workspace",
        "pipeline_model_id": "auto-coding-agentic",
    }


@mcp.tool()
async def get_workspace_recommendation(task: str) -> dict[str, Any]:
    """Suggest the best Portal 5 workspace for a given task description.

    Args:
        task: Plain-English description of the task
              (e.g. "fix a bug in router_pipe.py", "analyze a CVE",
               "generate a Word document", "run a port scan on the lab DC")

    Returns the recommended workspace ID and model, with reasoning.
    """
    return await _impl_get_workspace_recommendation(task)


@mcp.custom_route("/tools/get_workspace_recommendation", methods=["POST"])
async def get_workspace_recommendation_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(await _impl_get_workspace_recommendation(args.get("task", "")))


async def _impl_explore_repository(query: str, max_turns: int = 6) -> dict[str, Any]:
    """Locate relevant code using the FastContext-4B Explorer SubAgent.

    FastContext issues parallel READ/GLOB/GREP tool calls to find relevant
    files and line ranges, then returns compact citations. Use this before
    making code changes — pass the task description, get back the exact
    files and lines you need to read or edit.

    Args:
        query: What you're looking for, e.g. "where is SSE streaming implemented",
               "find the workspace routing logic", "where are tool calls dispatched"
        max_turns: Exploration turns allowed before forcing a final answer (default 6)

    Returns dict with:
        citations: list of {path, start_line, end_line, note}
        turns_used: how many exploration turns FastContext took
        model: the explorer model used
        error: set if FastContext is not available (pull the model first)
    """
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a repository exploration agent for the portal-5 codebase. "
                "Your ONLY job: find the relevant files and line ranges for the user's query. "
                "Issue parallel READ/GLOB/GREP tool calls each turn. "
                "When you have found the answer, respond with a <final_answer> block:\n"
                "<final_answer>\n"
                "path/to/file.py:10-45 — brief note about what is here\n"
                "path/to/other.py:120-180 — brief note\n"
                "</final_answer>\n"
                "Do not explain, plan, or respond in prose. Only tool calls or final_answer."
            ),
        },
        {"role": "user", "content": f"Find relevant code for: {query}"},
    ]

    turns_used = 0
    async with httpx.AsyncClient(timeout=120) as client:
        for _turn in range(min(max_turns, _FASTCONTEXT_MAX_TURNS)):
            turns_used += 1
            try:
                resp = await client.post(
                    f"{OLLAMA_URL}/v1/chat/completions",
                    json={
                        "model": _FASTCONTEXT_MODEL,
                        "messages": messages,
                        "tools": _FASTCONTEXT_TOOLS,
                        "tool_choice": "auto",
                        "stream": False,
                    },
                )
                if resp.status_code != 200:
                    return {
                        "error": f"FastContext not available (HTTP {resp.status_code}). "
                        f"Pull the model first: ollama pull {_FASTCONTEXT_MODEL}",
                        "citations": [],
                    }
                data = resp.json()
            except Exception as e:
                return {"error": str(e), "citations": []}

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            finish = choice.get("finish_reason", "")

            # Check for final_answer in content
            content = msg.get("content") or ""
            if "<final_answer>" in content:
                citations = _parse_fastcontext_citations(content)
                return {
                    "citations": citations,
                    "turns_used": turns_used,
                    "model": _FASTCONTEXT_MODEL,
                    "raw_answer": content,
                }

            # Execute tool calls
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                # Model stopped without final_answer — extract any file refs from content
                citations = _parse_fastcontext_citations(content)
                return {
                    "citations": citations,
                    "turns_used": turns_used,
                    "model": _FASTCONTEXT_MODEL,
                    "note": "model stopped without final_answer block",
                }

            messages.append({"role": "assistant", "tool_calls": tool_calls, "content": content})

            # Dispatch all tool calls (parallel results fed back as tool messages)
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                fn_name = tc.get("function", {}).get("name", "")
                try:
                    fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                except Exception:
                    fn_args = {}
                result = _dispatch_fastcontext_tool(fn_name, fn_args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result,
                    }
                )

            if finish == "stop":
                break

    # Exhausted turns — collect any citations from last assistant message
    last_content = (
        messages[-1].get("content", "") if messages[-1].get("role") == "assistant" else ""
    )
    return {
        "citations": _parse_fastcontext_citations(last_content),
        "turns_used": turns_used,
        "model": _FASTCONTEXT_MODEL,
        "note": f"max turns ({max_turns}) reached",
    }


@mcp.tool()
async def explore_repository(query: str, max_turns: int = 6) -> dict[str, Any]:
    """Locate relevant code using the FastContext-4B Explorer SubAgent.

    Issues parallel READ/GLOB/GREP tool calls to find relevant files and line
    ranges, then returns compact citations. Call before making code changes.

    Args:
        query: What you're looking for in the repo.
        max_turns: Exploration turns before forcing a final answer (default 6).
    """
    return await _impl_explore_repository(query, max_turns)


@mcp.custom_route("/tools/explore_repository", methods=["POST"])
async def explore_repository_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    query = args.get("query", "")
    max_turns = int(args.get("max_turns", 6))
    if not query:
        return JSONResponse({"error": "query required", "citations": []}, status_code=400)
    return JSONResponse(await _impl_explore_repository(query, max_turns))


async def _impl_trigger_backend_warmup(workspace: str = "auto-coding-agentic") -> dict[str, Any]:
    warmup_payload = {
        "model": workspace,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 1,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                json=warmup_payload,
                headers=_pipeline_headers(),
            )
            return {
                "status": "ok" if r.status_code < 400 else "error",
                "workspace": workspace,
                "http_status": r.status_code,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


@mcp.tool()
async def trigger_backend_warmup(workspace: str = "auto-coding-agentic") -> dict[str, Any]:
    """Trigger a warmup request for the specified workspace to pre-load its model.

    Call this before starting a long coding session so the model is already
    loaded in VRAM when you send your first real request.

    Args:
        workspace: The workspace ID to warm up (default: auto-coding-agentic)
    """
    return await _impl_trigger_backend_warmup(workspace)


@mcp.custom_route("/tools/trigger_backend_warmup", methods=["POST"])
async def trigger_backend_warmup_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(
        await _impl_trigger_backend_warmup(args.get("workspace", "auto-coding-agentic"))
    )


# ── Filesystem tools (host-native; used by auto-coding-agentic via pipeline) ──

_READ_ALLOWED_ROOTS = (REPO_ROOT.resolve(), pathlib.Path("/tmp").resolve())
_WRITE_ALLOWED_ROOTS = (REPO_ROOT.resolve(),)  # /tmp intentionally excluded from writes


def _resolve_path(path: str) -> pathlib.Path:
    """Resolve to an absolute, symlink-resolved path (repo-relative or absolute input)."""
    p = pathlib.Path(path)
    unresolved = p if p.is_absolute() else REPO_ROOT / p
    return unresolved.resolve()


def _check_read_allowed(resolved: pathlib.Path) -> bool:
    return any(resolved == root or resolved.is_relative_to(root) for root in _READ_ALLOWED_ROOTS)


def _check_write_allowed(resolved: pathlib.Path) -> bool:
    return any(resolved == root or resolved.is_relative_to(root) for root in _WRITE_ALLOWED_ROOTS)


def _impl_read_text_file(
    path: str, start_line: int | None = None, end_line: int | None = None
) -> dict[str, Any]:
    try:
        resolved = _resolve_path(path)
        if not _check_read_allowed(resolved):
            return {"error": f"read blocked: path must be under {REPO_ROOT} or /tmp"}
        lines = resolved.read_text(errors="replace").splitlines()
        start = max(1, start_line or 1) - 1
        end = end_line if end_line is not None else len(lines)
        chunk = lines[start:end]
        numbered = "\n".join(f"{start + i + 1}\t{ln}" for i, ln in enumerate(chunk))
        return {"content": numbered, "path": str(resolved), "lines": len(chunk)}
    except FileNotFoundError:
        return {"error": f"file not found: {path}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def read_text_file(
    path: str, start_line: int | None = None, end_line: int | None = None
) -> dict[str, Any]:
    """Read a file from the host filesystem with optional line range.

    Accepts absolute paths (e.g. /Users/chris/projects/portal-5/foo.py)
    or repo-relative paths (e.g. portal/platform/inference/router/streaming.py).
    Returns line-numbered content. Use this — not execute_bash cat — to read
    project files; execute_bash runs in an isolated container with no host access.

    Args:
        path: Absolute or repo-relative file path.
        start_line: First line to return (1-indexed, inclusive).
        end_line: Last line to return (inclusive); omit for full file.
    """
    return _impl_read_text_file(path, start_line, end_line)


@mcp.custom_route("/tools/read_text_file", methods=["POST"])
async def read_text_file_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(
        _impl_read_text_file(
            args.get("path", ""),
            args.get("start_line"),
            args.get("end_line"),
        )
    )


def _impl_list_directory(path: str) -> dict[str, Any]:
    try:
        resolved = _resolve_path(path)
        if not _check_read_allowed(resolved):
            return {"error": f"read blocked: path must be under {REPO_ROOT} or /tmp"}
        entries = []
        for item in sorted(resolved.iterdir()):
            prefix = "[DIR]" if item.is_dir() else "[FILE]"
            entries.append(f"{prefix} {item.name}")
        return {"path": str(resolved), "entries": entries}
    except FileNotFoundError:
        return {"error": f"directory not found: {path}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def list_directory(path: str) -> dict[str, Any]:
    """List files and directories at the given path.

    Args:
        path: Absolute or repo-relative directory path.
    """
    return _impl_list_directory(path)


@mcp.custom_route("/tools/list_directory", methods=["POST"])
async def list_directory_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(_impl_list_directory(args.get("path", ".")))


def _impl_search_files(
    pattern: str,
    path: str = "",
    glob: str = "**/*",
    max_results: int = 50,
) -> dict[str, Any]:
    try:
        base = _resolve_path(path) if path else REPO_ROOT.resolve()
        if not _check_read_allowed(base):
            return {"error": f"read blocked: path must be under {REPO_ROOT} or /tmp"}
        compiled = re.compile(pattern)
        _skip = {".git", "__pycache__", ".mypy_cache", "node_modules", ".ruff_cache", ".venv"}
        hits: list[str] = []
        cap = min(max_results, 200)
        for p in sorted(base.glob(glob)):
            if any(part in _skip for part in p.parts):
                continue
            if not p.is_file():
                continue
            try:
                for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                    if compiled.search(line):
                        rel = (
                            str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else str(p)
                        )
                        hits.append(f"{rel}:{i}: {line.rstrip()}")
                        if len(hits) >= cap:
                            return {"matches": hits, "truncated": True}
            except Exception:
                continue
        return {"matches": hits, "truncated": False}
    except re.error as e:
        return {"error": f"invalid regex: {e}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def search_files(
    pattern: str,
    path: str = "",
    glob: str = "**/*",
    max_results: int = 50,
) -> dict[str, Any]:
    """Search for a regex pattern across project files.

    Args:
        pattern: Regex or literal string to search for.
        path: Directory to search (default: repo root).
        glob: File glob filter, e.g. '**/*.py' (default: all files).
        max_results: Max matching lines to return (default 50).
    """
    return _impl_search_files(pattern, path, glob, max_results)


@mcp.custom_route("/tools/search_files", methods=["POST"])
async def search_files_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(
        _impl_search_files(
            args.get("pattern", ""),
            args.get("path", ""),
            args.get("glob", "**/*"),
            int(args.get("max_results", 50)),
        )
    )


def _impl_write_file(path: str, content: str) -> dict[str, Any]:
    try:
        resolved = _resolve_path(path)
        if not _check_write_allowed(resolved):
            return {"error": f"write blocked: path must be under {REPO_ROOT}"}
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return {"status": "ok", "path": str(resolved), "bytes": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def write_file(path: str, content: str) -> dict[str, Any]:
    """Write or overwrite a file on the host filesystem.

    Writes are constrained to the repo root and /tmp. Creates parent
    directories as needed.

    Args:
        path: Absolute or repo-relative file path to write.
        content: Full file content to write.
    """
    return _impl_write_file(path, content)


@mcp.custom_route("/tools/write_file", methods=["POST"])
async def write_file_endpoint(request: Any) -> JSONResponse:
    body = await request.json()
    args = body.get("arguments", {})
    return JSONResponse(_impl_write_file(args.get("path", ""), args.get("content", "")))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _dispatch_fastcontext_tool(name: str, args: dict[str, Any]) -> str:
    """Execute one of FastContext's three read-only repo tools."""
    if name == "READ":
        path = REPO_ROOT / args.get("path", "")
        try:
            lines = path.read_text(errors="replace").splitlines()
            start = max(1, int(args.get("start_line", 1))) - 1
            end = int(args.get("end_line", len(lines)))
            chunk = lines[start:end]
            return "\n".join(f"{start + i + 1}\t{ln}" for i, ln in enumerate(chunk))
        except FileNotFoundError:
            return f"ERROR: file not found: {args.get('path')}"
        except Exception as e:
            return f"ERROR: {e}"

    elif name == "GLOB":
        pattern = args.get("pattern", "**/*")
        try:
            # Exclude common noise
            _skip = {".git", "__pycache__", ".mypy_cache", "node_modules", ".ruff_cache"}
            results = []
            for p in sorted(REPO_ROOT.glob(pattern)):
                if any(part in _skip for part in p.parts):
                    continue
                results.append(str(p.relative_to(REPO_ROOT)))
                if len(results) >= 200:
                    results.append("... (truncated at 200)")
                    break
            return "\n".join(results) if results else "(no matches)"
        except Exception as e:
            return f"ERROR: {e}"

    elif name == "GREP":
        pattern = args.get("pattern", "")
        glob_filter = args.get("glob", "**/*.py")
        max_results = min(int(args.get("max_results", 40)), 100)
        try:
            compiled = re.compile(pattern)
            _skip = {".git", "__pycache__", ".mypy_cache", "node_modules", ".ruff_cache"}
            hits: list[str] = []
            for p in sorted(REPO_ROOT.glob(glob_filter)):
                if any(part in _skip for part in p.parts):
                    continue
                if not p.is_file():
                    continue
                try:
                    for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                        if compiled.search(line):
                            rel = str(p.relative_to(REPO_ROOT))
                            hits.append(f"{rel}:{i}: {line.rstrip()}")
                            if len(hits) >= max_results:
                                return "\n".join(hits) + f"\n... (truncated at {max_results})"
                except Exception:
                    continue
            return "\n".join(hits) if hits else "(no matches)"
        except re.error as e:
            return f"ERROR: invalid regex: {e}"
        except Exception as e:
            return f"ERROR: {e}"

    return f"ERROR: unknown tool {name}"


def _parse_fastcontext_citations(content: str) -> list[dict[str, Any]]:
    """Extract file+line citations from a FastContext <final_answer> block."""
    citations: list[dict[str, Any]] = []
    block_match = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
    source = block_match.group(1) if block_match else content
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # e.g. "portal/platform/inference/router/streaming.py:45-120 — SSE loop"
        m = re.match(
            r"([^\s:]+\.(?:py|yaml|json|sh|md|txt|js|ts))(?::(\d+)(?:-(\d+))?)?(?:\s+[—-]\s+(.*))?",
            line,
        )
        if m:
            path, start, end, note = m.group(1), m.group(2), m.group(3), m.group(4)
            citations.append(
                {
                    "path": path,
                    "start_line": int(start) if start else None,
                    "end_line": int(end) if end else None,
                    "note": (note or "").strip(),
                }
            )
    return citations


def _parse_metric(line: str) -> float:
    try:
        return float(line.rsplit(" ", 1)[-1])
    except ValueError:
        return 0.0


def _extract_label(line: str, label: str) -> str:
    import re

    m = re.search(rf'{label}="([^"]+)"', line)
    return m.group(1) if m else "unknown"


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    logger.info("Pipeline MCP server starting on port %d", PORT)
    logger.info("Proxying pipeline at %s", PIPELINE_URL)
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=PORT)
