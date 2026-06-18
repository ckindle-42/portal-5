"""Portal 5 — Pipeline Status MCP Server.

Gives coding tools (Claude Code, opencode) live introspection of the Portal 5
stack: workspace catalog, backend health, loaded models, and request metrics.

Port: 8928 (configurable via PIPELINE_MCP_PORT env var)

All data is read by calling the pipeline's own HTTP endpoints — this server has
zero imports from portal_pipeline/. It is registered in .mcp.json so Claude Code
and opencode pick it up automatically when opening the portal-5 project.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PIPELINE_MCP_PORT", 8928))
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
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
                        "description": "Glob pattern, e.g. '**/*.py' or 'portal_pipeline/**'",
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


def _pipeline_headers() -> dict:
    return {"Authorization": f"Bearer {PIPELINE_API_KEY}"} if PIPELINE_API_KEY else {}


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "pipeline-mcp", "port": PORT})


# ── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool()
async def get_pipeline_status() -> dict:
    """Return Portal 5 pipeline health: backend count, workspace count, version.

    Use this before starting any coding task to confirm the stack is up and
    all backends are healthy.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{PIPELINE_URL}/health", headers=_pipeline_headers())
            return r.json()
        except Exception as e:
            return {"error": str(e), "pipeline_url": PIPELINE_URL}


@mcp.tool()
async def list_workspaces(filter: str = "") -> list[dict]:
    """List all Portal 5 workspaces (AI models) with their routing metadata.

    Args:
        filter: Optional substring to filter by workspace ID or name
                (e.g. "coding", "security", "agentic")

    Returns list of {id, name, description_snippet} sorted by ID.
    Use this to pick the right workspace for a task before calling the pipeline.
    """
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
async def get_loaded_models() -> list[dict]:
    """Return which Ollama models are currently loaded in VRAM/RAM.

    Shows model name, size, and expiry time. Use this to check if the model
    you need is warm (fast response) or cold (will take time to load).
    """
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
async def get_metrics_summary() -> dict:
    """Return key Portal 5 operational metrics from Prometheus.

    Returns request totals, tool call counts, error rates, and TPS.
    Use this to verify that a tool call was dispatched (tool_calls_total
    should increment after a workspace request that invokes execute_bash).
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{PIPELINE_URL}/metrics", headers=_pipeline_headers())
            lines = r.text.splitlines()
            summary: dict = {}
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
async def get_workspace_recommendation(task: str) -> dict:
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
async def explore_repository(query: str, max_turns: int = 6) -> dict:
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
    messages: list[dict] = [
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
                    fn_args = __import__("json").loads(
                        tc.get("function", {}).get("arguments", "{}")
                    )
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
async def trigger_backend_warmup(workspace: str = "auto-coding-agentic") -> dict:
    """Trigger a warmup request for the specified workspace to pre-load its model.

    Call this before starting a long coding session so the model is already
    loaded in VRAM when you send your first real request.

    Args:
        workspace: The workspace ID to warm up (default: auto-coding-agentic)
    """
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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _dispatch_fastcontext_tool(name: str, args: dict) -> str:
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


def _parse_fastcontext_citations(content: str) -> list[dict]:
    """Extract file+line citations from a FastContext <final_answer> block."""
    citations: list[dict] = []
    block_match = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
    source = block_match.group(1) if block_match else content
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # e.g. "portal_pipeline/router/streaming.py:45-120 — SSE loop"
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
