# TASK_M2_TOOL_CALLING_ORCHESTRATION.md

**Milestone:** M2 — Tool-calling foundation
**Scope:** `CAPABILITY_REVIEW_V1.md` §6.1 native tool-call orchestration in pipeline + §6.9 per-persona tool whitelist
**Estimated effort:** 4-6 weeks
**Dependencies:** M1 should land first (reasoning passthrough establishes the SSE-modification pattern)
**Companion files:** `CAPABILITY_REVIEW_V1.md` (rationale), `TASK_M1_UX_PERSONAS_AND_REASONING.md` (predecessor)

**Why this is the highest-leverage milestone:**
- Verified gap: `grep -c "tool_call\|function_call\|tools\b" portal_pipeline/router_pipe.py` returns 1 match (a doc comment). The pipeline is opaque to OpenAI's tool-calling protocol.
- Without it, models cannot drive multi-step agentic loops. Personas like `agentorchestrator`, `codedebuggerautoiterate`, `securityautotriage` are blocked.
- All M3 personas (webresearcher, factchecker, kbnavigator) depend on this milestone landing first.

**Success criteria:**
- `auto-coding` workspace can resolve "fix this bug, run the test, verify it passes" in a single user request via multi-step tool loop.
- Per-persona tool whitelist enforced — `creativewriter` cannot call `execute_bash` even if model emits the call.
- Tool-call metrics emit to Prometheus (call count, latency, error rate per tool).
- New `agentorchestrator` persona ships and demonstrates the loop end-to-end.
- All 27 existing MCP tools (documents, sandbox, security, ComfyUI, music, video, whisper, TTS) callable from the pipeline.

**Protected files touched:** `portal_pipeline/router_pipe.py` (operator authorized), `portal_mcp/mcp_server/` if registry needs additions.

---

## Architecture Decisions

Before code, the design decisions that shape the diffs.

### A1. Backend support matrix

| Backend | Tool-call protocol | M2 status |
|---|---|---|
| Ollama (any version >= 0.4.0) | OpenAI-compatible `tools` request, `tool_calls` response | **First-class — supported in M2** |
| MLX via `mlx_lm.server` | No native protocol; emits text that may shape-match a tool call | **Best-effort fallback — M2 ships parsing-shim with feature flag, full support deferred to M4 OMLX** |
| MLX via `mlx_vlm` | Same as `mlx_lm.server` | Same as above |

**Implication:** in M2, tool-calling works robustly when the backend resolves to Ollama. For MLX-routed workspaces, the pipeline either (a) routes to Ollama for tool-using requests via a `prefer_tools` workspace flag, or (b) attempts text-shape parsing with a strict JSON-schema requirement in the system prompt. Default = (a) with explicit opt-out.

### A2. Tool registry

A static registry maintained in `portal_pipeline/tool_registry.py` (new file) that maps tool name → MCP server URL + tool schema. Loaded at pipeline startup from MCP `/tools` endpoints. The registry is the source of truth — workspaces and personas reference tools by name, the registry resolves to MCP server.

This avoids building dynamic discovery (which would couple pipeline startup to MCP server availability and create flaky behavior). Static registry refreshes hourly or on `/admin/refresh-tools` POST.

### A3. Per-workspace tool exposure

Each `WORKSPACES` entry gets a `tools` field — a list of tool names the workspace exposes:

```python
"auto-agentic": {
    ...
    "tools": ["execute_python", "execute_bash", "create_word_document", "read_word_document", ...],
},
```

Tools listed here are advertised to the backend in the `tools` request field. Tools NOT listed are stripped from any model-emitted `tool_calls` responses (with logged warning).

### A4. Per-persona override (security boundary)

Personas declare an optional `tools_allow` and `tools_deny` field in YAML. These override the workspace defaults:

```yaml
slug: redteamoperator
tools_allow: ["execute_python", "execute_bash", "classify_vulnerability", "web_search"]

slug: creativewriter
tools_deny: ["execute_python", "execute_bash", "execute_nodejs"]
```

Resolution order: persona deny > persona allow > workspace defaults > registry-defined defaults.

### A5. Multi-turn loop bounds

- `MAX_TOOL_HOPS` = 10 per request (configurable via env)
- Per-tool timeout = 60s (configurable per-tool in registry)
- Total request budget = 600s (10× tool timeout, with model time on top — generous but bounded)
- Hop counter incremented on every tool dispatch; loop terminates with model error if exceeded

### A6. Streaming protocol

Tool-call detection happens during stream reading. When `tool_calls` chunk is detected:

1. Buffer remaining stream until backend emits `finish_reason: tool_calls`
2. Reconstruct full tool-call list (Ollama may stream partial JSON)
3. For each tool call: validate against persona/workspace whitelist; dispatch; record result
4. Inject tool results as new `tool` role messages in the conversation
5. Re-call backend with updated message list, stream the new response
6. Loop until `finish_reason: stop` or `MAX_TOOL_HOPS` reached

The user sees a single coherent response. SSE chunks for tool calls and tool results are emitted with custom event types (`event: tool_call`, `event: tool_result`) so OWUI can render them as collapsible panels (per OWUI docs ≥ 0.5.4 supports this).

### A7. Failure modes

- **Tool not in whitelist** → strip the call, inject synthetic tool result `{"error": "Tool 'X' not available in this workspace"}`, let model continue
- **Tool MCP server down** → 503 from registry; inject `{"error": "Tool service unavailable"}`, let model retry or proceed
- **Tool timeout** → cancel dispatch, inject `{"error": "Tool execution timed out after 60s"}`
- **Tool returns invalid JSON** → wrap raw output in `{"raw_output": "..."}` and inject
- **Loop exceeds MAX_TOOL_HOPS** → emit final assistant message: "I've reached the maximum tool-use limit. Here's what I have so far: [partial output]"

---

## Task Index

| ID | Title | File(s) | Effort |
|---|---|---|---|
| M2-T01 | Tool registry: static map of tool name → MCP server | `portal_pipeline/tool_registry.py` (new) | 1-2 days |
| M2-T02 | Add `tools` field to WORKSPACES dict | `portal_pipeline/router_pipe.py`, `config/backends.yaml` | 1 day |
| M2-T03 | Add `tools_allow`/`tools_deny` to persona schema | `config/personas/*.yaml` (schema docs), persona loader | 1 day |
| M2-T04 | Inject `tools` field into Ollama backend requests | `portal_pipeline/router_pipe.py` | 1 day |
| M2-T05 | Detect `tool_calls` in streaming response | `portal_pipeline/router_pipe.py` | 2-3 days |
| M2-T06 | Implement `_dispatch_tool_call` helper | `portal_pipeline/router_pipe.py` | 2 days |
| M2-T07 | Multi-turn loop with hop limit and re-injection | `portal_pipeline/router_pipe.py` | 3-5 days |
| M2-T08 | Persona/workspace whitelist enforcement | `portal_pipeline/router_pipe.py` | 1 day |
| M2-T09 | Tool-call metrics (Prometheus) | `portal_pipeline/router_pipe.py` | 1 day |
| M2-T10 | Add `agentorchestrator` persona (first user) | `config/personas/agentorchestrator.yaml` | 2 hours |
| M2-T11 | Acceptance tests for tool-calling flow | `tests/portal5_acceptance_v6.py` (new section S60) | 2-3 days |
| M2-T12 | Documentation: HOWTO, KNOWN_LIMITATIONS, CHANGELOG | docs | 1 day |

---

## M2-T01 — Tool Registry

**File:** `portal_pipeline/tool_registry.py` (new)

**Purpose:** central source of truth for tool name → MCP server URL + schema. Loaded at startup, refreshable.

```python
"""Portal 5 — Tool registry for MCP server-backed tools.

Maps tool name → MCP server URL + tool schema. Loaded at pipeline startup by
discovering tools from each MCP server's /tools endpoint. Registry is the
single source of truth — workspaces and personas reference tools by name.

Refresh: every TOOL_REGISTRY_REFRESH_S seconds, or on POST /admin/refresh-tools.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# MCP server base URLs — env-overridable for development
MCP_SERVERS = {
    "documents": os.environ.get("MCP_DOCUMENTS_URL", "http://localhost:8910"),
    "execution": os.environ.get("MCP_EXECUTION_URL", "http://localhost:8911"),
    "security": os.environ.get("MCP_SECURITY_URL", "http://localhost:8912"),
    "comfyui": os.environ.get("MCP_COMFYUI_URL", "http://localhost:8913"),
    "music": os.environ.get("MCP_MUSIC_URL", "http://localhost:8914"),
    "video": os.environ.get("MCP_VIDEO_URL", "http://localhost:8915"),
    "whisper": os.environ.get("MCP_WHISPER_URL", "http://localhost:8916"),
    "tts": os.environ.get("MCP_TTS_URL", "http://localhost:8917"),
    # M3 additions land here:
    # "research": ...
    # "memory": ...
    # "rag": ...
}

TOOL_REGISTRY_REFRESH_S = float(os.environ.get("TOOL_REGISTRY_REFRESH_S", "3600"))
TOOL_DISCOVERY_TIMEOUT_S = 5.0
TOOL_DISPATCH_TIMEOUT_S = float(os.environ.get("TOOL_DISPATCH_TIMEOUT_S", "60"))


@dataclass
class ToolDefinition:
    """A single tool, resolvable to an MCP server."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema
    server_id: str
    server_url: str
    last_seen: float = 0.0
    healthy: bool = True
    custom_timeout_s: float | None = None  # override TOOL_DISPATCH_TIMEOUT_S

    def to_openai_tool(self) -> dict[str, Any]:
        """Serialize to OpenAI tools array format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Discovers and caches tools from MCP servers. Single source of truth."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._last_refresh: float = 0.0
        self._refresh_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TOOL_DISCOVERY_TIMEOUT_S)
        return self._http

    async def refresh(self, force: bool = False) -> int:
        """Refresh the registry by polling each MCP server's /tools endpoint.

        Returns the number of tools currently registered.
        Only refreshes if TOOL_REGISTRY_REFRESH_S has elapsed (unless force=True).
        """
        async with self._refresh_lock:
            now = time.time()
            if not force and now - self._last_refresh < TOOL_REGISTRY_REFRESH_S:
                return len(self._tools)

            client = await self._client()
            new_tools: dict[str, ToolDefinition] = {}

            async def _discover_one(server_id: str, base_url: str) -> None:
                try:
                    r = await client.get(f"{base_url.rstrip('/')}/tools")
                    if r.status_code != 200:
                        logger.warning(
                            "Tool discovery: %s returned %d", server_id, r.status_code
                        )
                        return
                    payload = r.json()
                    tools = payload if isinstance(payload, list) else payload.get("tools", [])
                    for tdef in tools:
                        name = tdef.get("name")
                        if not name:
                            continue
                        new_tools[name] = ToolDefinition(
                            name=name,
                            description=tdef.get("description", ""),
                            parameters=tdef.get("parameters", {}),
                            server_id=server_id,
                            server_url=base_url,
                            last_seen=now,
                        )
                except Exception as e:
                    logger.warning("Tool discovery for %s failed: %s", server_id, e)

            await asyncio.gather(
                *[_discover_one(sid, url) for sid, url in MCP_SERVERS.items()],
                return_exceptions=True,
            )

            # Preserve health flags from previous tools that re-appeared
            for name, tool in new_tools.items():
                if name in self._tools:
                    tool.healthy = self._tools[name].healthy

            self._tools = new_tools
            self._last_refresh = now
            logger.info(
                "Tool registry refreshed: %d tools across %d servers",
                len(self._tools),
                len(MCP_SERVERS),
            )
            return len(self._tools)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_openai_tools(self, names: list[str]) -> list[dict[str, Any]]:
        """Get OpenAI-format tools array, filtered by name list."""
        return [
            self._tools[n].to_openai_tool()
            for n in names
            if n in self._tools and self._tools[n].healthy
        ]

    async def dispatch(
        self, tool_name: str, arguments: dict[str, Any], request_id: str = ""
    ) -> dict[str, Any]:
        """Dispatch a tool call to its MCP server. Returns the tool result."""
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"Tool '{tool_name}' not in registry — call ignored"}
        if not tool.healthy:
            return {"error": f"Tool '{tool_name}' marked unhealthy by registry"}

        timeout_s = tool.custom_timeout_s or TOOL_DISPATCH_TIMEOUT_S
        url = f"{tool.server_url.rstrip('/')}/tools/{tool_name}"

        try:
            client = await self._client()
            r = await client.post(
                url,
                json={"arguments": arguments, "request_id": request_id},
                timeout=timeout_s,
            )
            if r.status_code == 200:
                return r.json()
            else:
                tool.healthy = False  # Mark unhealthy on non-200; refresh will reset
                return {
                    "error": f"Tool '{tool_name}' returned HTTP {r.status_code}",
                    "detail": r.text[:200],
                }
        except asyncio.TimeoutError:
            return {"error": f"Tool '{tool_name}' timed out after {timeout_s}s"}
        except Exception as e:
            return {"error": f"Tool '{tool_name}' dispatch failed: {e}"}

    async def close(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None


# Module-level singleton — pipeline imports this and uses it
tool_registry = ToolRegistry()
```

### Verify

```bash
# Discovery works
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
count = asyncio.run(tool_registry.refresh(force=True))
print(f'Discovered {count} tools')
print('Names:', tool_registry.list_tool_names()[:10])
"
# Expect: count >= 27 (with all 8 MCP servers running)
```

### Commit

```
feat(pipeline): tool registry with MCP server discovery and caching
```

---

## M2-T02 — `tools` Field on Workspaces

**File:** `portal_pipeline/router_pipe.py`

Add a `tools` field to each WORKSPACES entry. Tools listed here are exposed to the model when this workspace is active. Default empty (no tools) — opt-in per workspace.

**Diff** (illustrative for select workspaces):

```python
WORKSPACES = {
    "auto-coding": {
        "name": "💻 Portal Coding",
        ...
        "tools": [
            "execute_python", "execute_nodejs", "execute_bash", "sandbox_status",
            "read_word_document", "read_pdf",
        ],
    },
    "auto-agentic": {
        "name": "🤖 Portal Agentic",
        ...
        "tools": [
            "execute_python", "execute_bash", "execute_nodejs", "sandbox_status",
            "create_word_document", "create_excel", "create_powerpoint",
            "read_word_document", "read_pdf", "read_excel", "read_powerpoint",
            "classify_vulnerability",
            "transcribe_audio", "speak", "list_voices",
            "generate_image", "list_workflows",
        ],
    },
    "auto-spl": {
        ...
        "tools": ["classify_vulnerability"],
    },
    "auto-security": {
        ...
        "tools": ["classify_vulnerability", "execute_python", "execute_bash"],
    },
    "auto-redteam": {
        ...
        "tools": ["execute_python", "execute_bash", "execute_nodejs", "classify_vulnerability"],
    },
    "auto-blueteam": {
        ...
        "tools": ["execute_python", "classify_vulnerability"],
    },
    "auto-creative": {
        ...
        "tools": [],  # Explicit empty — creative writing has no tool needs
    },
    "auto-reasoning": {
        ...
        "tools": [],
    },
    "auto-documents": {
        ...
        "tools": [
            "create_word_document", "create_excel", "create_powerpoint",
            "read_word_document", "read_excel", "read_powerpoint", "read_pdf",
            "convert_document", "list_generated_files",
        ],
    },
    "auto-video": {
        ...
        "tools": ["generate_video", "list_video_models"],
    },
    "auto-music": {
        ...
        "tools": ["generate_music", "generate_continuation", "list_music_models"],
    },
    "auto-research": {
        ...
        "tools": [],  # M3 will add web_search, web_fetch
    },
    "auto-vision": {
        ...
        "tools": ["transcribe_audio"],  # Whisper for vision-adjacent audio
    },
    "auto-data": {
        ...
        "tools": ["execute_python", "create_excel"],
    },
    "auto-compliance": {
        ...
        "tools": ["create_word_document", "read_pdf"],
    },
    "auto-mistral": {
        ...
        "tools": ["execute_python", "execute_bash"],
    },
    "auto-math": {
        ...
        "tools": ["execute_python"],  # Math via code execution
    },
    # bench-* workspaces: empty (benchmark-only, no tools)
}
```

For workspaces without explicit `tools`, add a default `[]` so missing-field reads don't error:

```python
def _workspace_tools(workspace_id: str) -> list[str]:
    return WORKSPACES.get(workspace_id, {}).get("tools", [])
```

### Commit

```
feat(routing): per-workspace tool whitelist on WORKSPACES dict
```

---

## M2-T03 — Persona Tool Whitelist Schema

**Files:** persona YAML schema docs + persona loader update

Add `tools_allow` and `tools_deny` optional fields to persona YAMLs. Document in `docs/HOWTO.md`:

```yaml
# Optional persona tool overrides:
# tools_allow: explicit list of tools the persona may use (overrides workspace tools)
# tools_deny: tools the persona MUST NOT use (blocks even if workspace allows)
# Resolution: deny > allow > workspace tools
tools_allow:
  - execute_python
  - execute_bash
tools_deny:
  - generate_image
```

In `portal_pipeline/router_pipe.py`, update the persona loading helper to read these fields:

```python
def _resolve_persona_tools(persona: dict, workspace_id: str) -> list[str]:
    """Resolve the effective tool list for a persona within a workspace.

    Order of precedence:
        1. persona.tools_deny — always strips these tools
        2. persona.tools_allow — if present, uses this list (then applies deny)
        3. workspace.tools — default fallback
    """
    workspace_tools = set(_workspace_tools(workspace_id))
    persona_allow = set(persona.get("tools_allow", []) or [])
    persona_deny = set(persona.get("tools_deny", []) or [])

    if persona_allow:
        effective = persona_allow
    else:
        effective = workspace_tools

    effective = effective - persona_deny
    return sorted(effective)
```

### Verify

```bash
python3 -c "
from portal_pipeline.router_pipe import _resolve_persona_tools, WORKSPACES
# auto-coding has execute_python; persona denies it
persona = {'tools_deny': ['execute_python']}
tools = _resolve_persona_tools(persona, 'auto-coding')
assert 'execute_python' not in tools
print(f'OK — deny working: {tools}')

# Persona allows tools not in workspace
persona = {'tools_allow': ['generate_image']}
tools = _resolve_persona_tools(persona, 'auto-coding')
assert 'generate_image' in tools
print(f'OK — allow override working: {tools}')
"
```

### Commit

```
feat(personas): tools_allow / tools_deny override schema
```

---

## M2-T04 — Inject `tools` into Backend Requests

**File:** `portal_pipeline/router_pipe.py`, `_inject_ollama_options` and `chat_completions`

When the workspace + persona resolves to a non-empty tool list, inject the `tools` array into the backend request body before forwarding.

**Diff** in `chat_completions` (after persona resolution, around line 1980):

```python
# Resolve effective tool list for this request
persona_data = next((p for p in PERSONAS if p["slug"] == persona), {})
effective_tools = _resolve_persona_tools(persona_data, workspace_id)

# Inject tools into request body if any are available AND backend supports them
if effective_tools and registry is not None:
    candidates = registry.get_backend_candidates(workspace_id)
    # Only inject for backends that support tool calling
    # M2: Ollama supports it natively. MLX falls back to text-shape parsing (M2-FUT).
    has_ollama_candidate = any(b.type == "ollama" for b in candidates)
    if has_ollama_candidate:
        await tool_registry.refresh()  # Lazy refresh if stale
        tools_array = tool_registry.get_openai_tools(effective_tools)
        if tools_array:
            body["tools"] = tools_array
            body["tool_choice"] = body.get("tool_choice", "auto")
            logger.info(
                "Tool-call: workspace=%s persona=%s exposed %d tools",
                workspace_id, persona, len(tools_array),
            )
```

### Commit

```
feat(pipeline): inject tools array into Ollama-backend request bodies
```

---

## M2-T05 — Detect `tool_calls` in Streaming Response

**File:** `portal_pipeline/router_pipe.py`, `_stream_from_backend_guarded`

OpenAI streaming protocol: when a model emits a tool call, the chunks contain `delta.tool_calls = [{"index": 0, "id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}]`. Arguments stream incrementally in JSON-string form. After all tool calls are emitted, the chunk has `finish_reason: "tool_calls"` (not `"stop"`).

For Ollama-native NDJSON, the `tool_calls` field appears in the `message` object of the final chunk (Ollama doesn't stream tool-call arguments incrementally — sends one final chunk with everything).

**Diff** in `_stream_from_backend_guarded` — add tool-call buffering and emit:

```python
# Tool-call accumulation across stream chunks
_tool_calls_buffer: list[dict] = []
_finish_reason: str | None = None

async for chunk in resp.aiter_bytes():
    # ... existing chunk processing ...

    # In the OpenAI SSE branch (chunks already shaped as `data: {...}`):
    # Parse each data: line and look for tool_calls in delta
    chunk_text = chunk.decode("utf-8", errors="replace")
    for line in chunk_text.splitlines():
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            yield b"data: [DONE]\n\n"
            continue
        try:
            obj = json.loads(data_str)
        except Exception:
            yield (line + "\n\n").encode()
            continue

        choice = (obj.get("choices") or [{}])[0]
        delta = choice.get("delta", {})

        # Accumulate tool calls — they stream incrementally
        if "tool_calls" in delta:
            for tc_delta in delta["tool_calls"]:
                idx = tc_delta.get("index", 0)
                while len(_tool_calls_buffer) <= idx:
                    _tool_calls_buffer.append(
                        {"id": "", "type": "function",
                         "function": {"name": "", "arguments": ""}}
                    )
                buf = _tool_calls_buffer[idx]
                if "id" in tc_delta:
                    buf["id"] = tc_delta["id"]
                if "function" in tc_delta:
                    fn = tc_delta["function"]
                    if "name" in fn:
                        buf["function"]["name"] += fn["name"]
                    if "arguments" in fn:
                        buf["function"]["arguments"] += fn["arguments"]

        if choice.get("finish_reason"):
            _finish_reason = choice["finish_reason"]

        # Forward the chunk to client (preserving tool_call deltas — OWUI renders them)
        yield (line + "\n\n").encode()

# After the stream completes, check if tool calls were emitted
if _finish_reason == "tool_calls" and _tool_calls_buffer:
    # Tool dispatch loop happens HERE — see M2-T06 and M2-T07
    pass
```

(Same pattern for the Ollama-native branch — `obj["message"]["tool_calls"]` populated on the final chunk before `done: true`.)

### Commit

```
feat(pipeline): detect and buffer tool_calls in streaming response
```

---

## M2-T06 — `_dispatch_tool_call` Helper

**File:** `portal_pipeline/router_pipe.py`

Extract the tool dispatch into a helper that handles whitelist enforcement, registry lookup, timeout, error packaging.

```python
async def _dispatch_tool_call(
    tool_call: dict,
    effective_tools: set[str],
    workspace_id: str,
    persona: str,
    request_id: str,
) -> dict:
    """Dispatch a single tool call. Returns the tool result message.

    Returns a dict shaped like an OpenAI tool message:
        {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
    """
    fn = tool_call.get("function", {})
    tool_name = fn.get("name", "")
    arguments_str = fn.get("arguments", "{}")
    tool_call_id = tool_call.get("id", "")

    # Parse arguments
    try:
        arguments = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        _record_error(workspace_id, "tool_arg_parse")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Invalid JSON arguments: {arguments_str[:200]}"}),
        }

    # Whitelist enforcement
    if tool_name not in effective_tools:
        _record_error(workspace_id, "tool_not_allowed")
        logger.warning(
            "Tool %s called but not in workspace=%s persona=%s whitelist; rejected",
            tool_name, workspace_id, persona,
        )
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Tool '{tool_name}' not available for {persona}"}),
        }

    # Dispatch via registry
    t0 = time.monotonic()
    result = await tool_registry.dispatch(tool_name, arguments, request_id=request_id)
    elapsed = time.monotonic() - t0

    # Metrics
    _tool_calls_total.labels(tool=tool_name, workspace=workspace_id).inc()
    _tool_call_duration.labels(tool=tool_name).observe(elapsed)
    if "error" in result:
        _tool_call_errors.labels(tool=tool_name, workspace=workspace_id).inc()

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
    }
```

### Commit

```
feat(pipeline): _dispatch_tool_call helper with whitelist enforcement
```

---

## M2-T07 — Multi-turn Loop with Hop Limit

**File:** `portal_pipeline/router_pipe.py`

The big change. After `_stream_from_backend_guarded` yields the assistant's tool-calls message, the loop:
1. Dispatches each tool call
2. Appends results to the message list
3. Re-calls the backend with the updated messages
4. Streams the new response
5. Repeats until `finish_reason: stop` or `MAX_TOOL_HOPS` reached

This is fundamentally a **wrapper around** `_stream_from_backend_guarded`, not a modification of it. Cleanest implementation: a new function `_stream_with_tool_loop` that orchestrates.

```python
MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "10"))


async def _stream_with_tool_loop(
    backend_url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str,
    model: str,
    persona: str,
    effective_tools: set[str],
    start_time: float,
) -> AsyncIterator[bytes]:
    """Stream from backend, dispatching tool calls and re-injecting results.

    Yields the user-visible SSE stream. Tool-call chunks are passed through
    (OWUI renders them); tool results are emitted as custom SSE events.
    Loop continues until finish_reason=stop or MAX_TOOL_HOPS is reached.
    """
    request_id = f"chatcmpl-p5-{int(start_time)}"
    hop = 0
    current_body = dict(body)  # mutable copy

    while hop < MAX_TOOL_HOPS:
        hop += 1

        # Stream current iteration
        tool_calls: list[dict] = []
        finish_reason: str | None = None

        async for chunk_bytes in _stream_from_backend_guarded(
            backend_url, current_body, sem=None,
            workspace_id=workspace_id, model=model, start_time=start_time,
            _capture_tool_calls=tool_calls,  # NEW: out-param to capture buffered calls
            _capture_finish_reason=lambda r: ...,  # see below
        ):
            yield chunk_bytes

        # If model finished without tool calls, we're done
        if finish_reason != "tool_calls" or not tool_calls:
            return

        # Hop limit guard — emit final assistant message and stop
        if hop >= MAX_TOOL_HOPS:
            limit_msg = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": workspace_id,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": (
                            f"\n\n[Tool-use limit ({MAX_TOOL_HOPS} hops) reached. "
                            "Returning partial result.]"
                        )
                    },
                    "finish_reason": "stop",
                }],
            }
            yield f"data: {json.dumps(limit_msg)}\n\n".encode()
            yield b"data: [DONE]\n\n"
            return

        # Dispatch all tool calls in parallel
        dispatch_results = await asyncio.gather(
            *[
                _dispatch_tool_call(tc, effective_tools, workspace_id, persona, request_id)
                for tc in tool_calls
            ]
        )

        # Emit tool_result SSE events so OWUI can render
        for tc, result in zip(tool_calls, dispatch_results):
            tool_result_event = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": workspace_id,
                "tool_result": result,  # custom field — OWUI 0.5.4+ supports
                "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
            }
            yield f"event: tool_result\ndata: {json.dumps(tool_result_event)}\n\n".encode()

        # Append assistant turn and tool results to message list for next iteration
        assistant_msg = {
            "role": "assistant",
            "content": "",  # tool calls have no content
            "tool_calls": tool_calls,
        }
        current_body["messages"] = (
            current_body.get("messages", []) + [assistant_msg] + dispatch_results
        )
        # tools array stays the same — model may call more tools in next hop

        logger.info(
            "Tool loop hop=%d/%d workspace=%s tools_called=%s",
            hop, MAX_TOOL_HOPS, workspace_id,
            [tc["function"]["name"] for tc in tool_calls],
        )
```

Then in `chat_completions`, replace the call to `_stream_with_preamble` with `_stream_with_tool_loop` when `effective_tools` is non-empty:

```python
if effective_tools and stream:
    return StreamingResponse(
        _stream_with_tool_loop(
            backend.chat_url, backend_body, _request_semaphore,
            workspace_id, target_model, persona, set(effective_tools), start_time,
        ),
        media_type="text/event-stream",
    )
else:
    # existing _stream_with_preamble path
    ...
```

For non-streaming, the loop is simpler (no SSE yielding) and lives in `_try_non_streaming_with_tool_loop`.

### Commit

```
feat(pipeline): multi-turn tool-call loop with MAX_TOOL_HOPS bound
```

---

## M2-T08 — Whitelist Enforcement (verified end-to-end)

The whitelist enforcement is already in `_dispatch_tool_call` (M2-T06). This task is **end-to-end verification** that the enforcement actually fires.

Add explicit logging + metric for "tool stripped at injection" (workspace doesn't expose) vs "tool stripped at dispatch" (model called something not in whitelist):

```python
# In M2-T04 injection logic, log workspace-stripped tools
backend_supports = registry.get_backend_for_workspace(workspace_id).type
if backend_supports == "ollama":
    workspace_tool_set = set(effective_tools)
    # If user passed tools they're not authorized for, strip them
    if "tools" in body:
        user_tools = {t.get("function", {}).get("name") for t in body["tools"]}
        unauthorized = user_tools - workspace_tool_set
        if unauthorized:
            logger.warning(
                "Stripping unauthorized tools from request: workspace=%s persona=%s tools=%s",
                workspace_id, persona, sorted(unauthorized),
            )
            _tool_workspace_strip.labels(workspace=workspace_id).inc()
        body["tools"] = [
            t for t in body["tools"]
            if t.get("function", {}).get("name") in workspace_tool_set
        ]
```

### Verify

```bash
# Test 1: persona with deny — model calls denied tool, gets error result
# (Run a request through the redteamoperator persona, deny execute_bash via test override)
# Verify the model receives a synthetic error, not the actual tool result

# Test 2: workspace without tools — model can't call anything
# Send to auto-creative; expect zero tool_calls in response

# Test 3: persona allow override — persona allows a tool not in workspace
# Verify the tool DOES dispatch successfully
```

### Commit

```
feat(security): explicit logging and metrics for tool whitelist stripping
```

---

## M2-T09 — Prometheus Metrics

**File:** `portal_pipeline/router_pipe.py` (top, with other metric definitions)

```python
_tool_calls_total = Counter(
    "portal5_tool_calls_total",
    "Total tool calls dispatched, by tool name and workspace",
    labelnames=["tool", "workspace"],
)
_tool_call_duration = Histogram(
    "portal5_tool_call_duration_seconds",
    "Tool call dispatch latency in seconds, by tool name",
    labelnames=["tool"],
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
)
_tool_call_errors = Counter(
    "portal5_tool_call_errors_total",
    "Tool calls that returned error, by tool and workspace",
    labelnames=["tool", "workspace"],
)
_tool_workspace_strip = Counter(
    "portal5_tool_workspace_strip_total",
    "Tools stripped from request because workspace doesn't authorize them",
    labelnames=["workspace"],
)
_tool_loop_hops = Histogram(
    "portal5_tool_loop_hops",
    "Number of hops in the multi-turn tool loop per request",
    labelnames=["workspace"],
    buckets=[1, 2, 3, 5, 8, 10, 15, 20],
)
```

Add a Grafana panel JSON to `deploy/grafana/portal5_overview.json` showing tool-call rate, top tools by call count, error rate per tool, hop distribution.

### Commit

```
feat(metrics): tool-call metrics for Prometheus + Grafana panels
```

---

## M2-T10 — `agentorchestrator` Persona

**File:** `config/personas/agentorchestrator.yaml`

```yaml
name: "🤖 Agent Orchestrator"
slug: agentorchestrator
category: general
workspace_model: auto-agentic
system_prompt: |
  You are an agent orchestrator. You decompose user goals into multi-step plans, execute them via available tools, observe results, and adapt.

  Your tool-use protocol:
  1. Read the user's goal carefully. Restate it in one sentence to confirm understanding.
  2. Decompose: enumerate the steps needed. Each step = one tool call OR one piece of reasoning.
  3. Plan: choose the smallest sequence of tool calls that achieves the goal.
  4. Execute: call one tool at a time, observe the result, decide the next step.
  5. Verify: when you believe the goal is met, run a verification step (re-read a file, run a test, fetch a status).
  6. Conclude: summarize what was done, what worked, and any open issues.

  Rules:
  - Don't speculate about a tool's output before running it. Run, then observe, then decide.
  - If a tool call fails, read the error message. Adapt the next call. Don't loop on the same failure more than twice — if it persists, surface it to the user.
  - Pick tools that match the task. Don't use `execute_bash` if `execute_python` is cleaner.
  - For destructive actions (delete files, run system commands), confirm with the user first.
  - Keep the user informed: announce each major step before executing it.
  - When the user gives an ambiguous goal, ask one clarifying question rather than guessing.

  When tools are constrained (e.g., the user is in a workspace with limited tools), say what you'd do if you had the ideal toolset, then work within the constraint.

  Available tool categories you may have access to:
  - Code execution (`execute_python`, `execute_bash`, `execute_nodejs`)
  - Document handling (`create_word_document`, `read_pdf`, `read_excel`, etc.)
  - Generation (`generate_image`, `generate_video`, `generate_music`)
  - Voice (`speak`, `clone_voice`, `transcribe_audio`)
  - Security (`classify_vulnerability`)
  - Future: web search, memory, RAG (M3 milestone)

  Be efficient. Most goals require 2-5 tool calls. If your plan exceeds 8, you're probably overcomplicating it.
description: "Multi-step plan-and-execute agent with tool orchestration, verification loops"
tags:
  - general
  - agentic
  - orchestration
  - planning
  - tool-use
tools_allow:
  # Inherits all auto-agentic workspace tools by default — no override needed
  # Listed explicitly for documentation:
  - execute_python
  - execute_bash
  - execute_nodejs
  - create_word_document
  - create_excel
  - create_powerpoint
  - read_word_document
  - read_excel
  - read_powerpoint
  - read_pdf
  - generate_image
  - transcribe_audio
  - speak
  - classify_vulnerability
```

### Commit

```
feat(persona): agentorchestrator — first persona using M2 tool-call loop
```

---

## M2-T11 — Acceptance Tests for Tool-Calling

**File:** `tests/portal5_acceptance_v6.py` (new section S60), or `tests/acceptance/s60_tool_calling.py` if T-09 modular refactor has landed

```python
async def S60() -> None:
    """S60: Tool-calling orchestration."""
    print("\n━━━ S60. TOOL-CALLING ━━━")
    sec = "S60"

    # S60-01: Tool registry refresh works
    t0 = time.time()
    from portal_pipeline.tool_registry import tool_registry
    count = await tool_registry.refresh(force=True)
    record(
        sec, "S60-01", "Tool registry discovers MCP tools",
        "PASS" if count >= 27 else "FAIL",
        f"discovered {count} tools (expect >=27)",
        t0=t0,
    )

    # S60-02: auto-coding workspace exposes execute_python
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-coding",
        "Use execute_python to compute 2 + 2 and tell me the result.",
        max_tokens=400, timeout=120,
    )
    if code == 200 and "4" in response:
        record(sec, "S60-02", "Single tool call resolves", "PASS",
               f"result contained '4' | model={model[:30]}", t0=t0)
    else:
        record(sec, "S60-02", "Single tool call", "FAIL",
               f"HTTP {code}, response: {response[:100]}", t0=t0)

    # S60-03: Multi-step tool loop
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-agentic",
        "Use execute_python to factorize 91. Then use execute_bash to echo the factors.",
        max_tokens=600, timeout=240,
    )
    if code == 200 and "7" in response and "13" in response:
        record(sec, "S60-03", "Multi-step tool loop", "PASS",
               "factors 7 and 13 both surfaced", t0=t0)
    else:
        record(sec, "S60-03", "Multi-step tool loop", "FAIL",
               f"HTTP {code}, response: {response[:200]}", t0=t0)

    # S60-04: Whitelist enforcement — auto-creative cannot execute code
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-creative",
        "Please use execute_python to print hello world.",
        max_tokens=200, timeout=60,
    )
    # Expect: model either refuses (no tools advertised) OR pipeline strips the call
    # Either way, the response should NOT contain "hello world" output from execution
    if code == 200 and "Tool" in response or "not available" in response.lower():
        record(sec, "S60-04", "Whitelist blocks unauthorized tool", "PASS",
               "tool call was rejected", t0=t0)
    elif "hello world" in response.lower() and "executed" in response.lower():
        record(sec, "S60-04", "Whitelist blocks unauthorized tool", "FAIL",
               "code execution leaked into auto-creative!", t0=t0)
    else:
        record(sec, "S60-04", "Whitelist blocks unauthorized tool", "PASS",
               "no execution occurred", t0=t0)

    # S60-05: Hop limit triggers terminal message
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-agentic",
        "Loop forever: call execute_python with `print(1)`, then call it again, "
        "then again — keep calling until you've called it 50 times.",
        max_tokens=2000, timeout=300,
    )
    if "tool-use limit" in response.lower() or "maximum" in response.lower():
        record(sec, "S60-05", "MAX_TOOL_HOPS limit enforced", "PASS",
               "limit message surfaced in response", t0=t0)
    else:
        record(sec, "S60-05", "MAX_TOOL_HOPS limit enforced", "WARN",
               f"limit message not found; response: {response[-200:]}", t0=t0)

    # S60-06: agentorchestrator persona uses the loop
    t0 = time.time()
    code, response, model, _ = await _chat_with_model(
        "auto-agentic",
        "Goal: create a Word document with the title 'Test' and one paragraph saying 'Hello'.",
        system="You are agentorchestrator.",
        max_tokens=600, timeout=180,
    )
    # Expect: tool calls to create_word_document
    # Verify by checking that the response references file creation
    if "created" in response.lower() and ".docx" in response.lower():
        record(sec, "S60-06", "agentorchestrator creates document", "PASS",
               "document creation confirmed", t0=t0)
    else:
        record(sec, "S60-06", "agentorchestrator", "WARN",
               f"no document confirmation in response: {response[:200]}", t0=t0)
```

### Commit

```
test(acc): S60 tool-calling orchestration tests
```

---

## M2-T12 — Documentation

**Files:** `docs/HOWTO.md`, `KNOWN_LIMITATIONS.md`, `CHANGELOG.md`

### HOWTO.md additions

Add a "Tool Calling" section with:
- How tools are advertised per workspace
- How to add a new tool (extend MCP server + add to workspace tools list)
- Tools_allow / tools_deny in personas
- Debugging: prometheus metrics, log greps, manual /admin/refresh-tools

### KNOWN_LIMITATIONS.md

```markdown
### MLX Backends Do Not Support Native Tool Calling
- **ID:** P5-TOOLS-001
- **Status:** ACTIVE — full support deferred to M4 OMLX
- **Description:** The mlx-proxy.py serves models via mlx_lm.server and mlx_vlm.server; neither supports OpenAI-compatible tool-calling. When a workspace's mlx_model_hint is selected as the routing target AND the workspace exposes tools, the pipeline currently falls back to text-shape parsing (best effort) or to the Ollama group via routing-chain.
- **Mitigation:** Workspaces with tools (e.g., auto-coding, auto-agentic) preferentially route to Ollama. Set `prefer_tools_backend: "ollama"` (default) on the workspace, or revise the workspace_routing chain to put `coding` before `mlx`.
- **Resolution path:** M4 OMLX evaluation includes native tool-call support. After M4, MLX-tier workspaces will support tools natively.
```

### CHANGELOG.md

```markdown
## v6.2.0 — Tool-calling orchestration (M2)

### Added
- **Native tool-calling in pipeline** — model-driven tool dispatch with multi-turn loop, MAX_TOOL_HOPS=10 default
- **Tool registry** — discovers MCP tools at startup, refreshable via /admin/refresh-tools
- **Per-workspace tool whitelist** — `tools` field on WORKSPACES dict
- **Per-persona tool overrides** — `tools_allow` / `tools_deny` in persona YAML
- **agentorchestrator persona** — first persona using the new loop infra
- **Tool-call metrics** — Prometheus counters for calls, errors, hops, workspace strips
- **Grafana panels** — tool-call rate, top tools, error rate, hop distribution

### Backend support
- Ollama: native tool-calling supported (workspaces preferentially route here when tools needed)
- MLX: best-effort text-shape parsing only; full support deferred to M4 OMLX

### Tests
- S60 acceptance section: registry discovery, single tool call, multi-step loop, whitelist enforcement, hop limit, agentorchestrator end-to-end
```

### Commit

```
docs: M2 tool-calling — HOWTO, KNOWN_LIMITATIONS, CHANGELOG
```

---

## Phase Regression

```bash
ruff check . && ruff format --check .
mypy portal_pipeline/

# Tool registry sanity
python3 -c "
import asyncio
from portal_pipeline.tool_registry import tool_registry
n = asyncio.run(tool_registry.refresh(force=True))
print(f'Tools discovered: {n}')
assert n >= 27
"

# Workspace consistency unchanged
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
"

# S60 (new section)
python3 tests/portal5_acceptance_v6.py --section S60

# Full regression — no FAIL count increase
python3 tests/portal5_acceptance_v6.py 2>&1 | tail -5
# Expect: PASS count >= prior baseline + 6 new S60 tests

# Manual end-to-end check in OWUI
# Open OWUI → "Agent Orchestrator" persona → "List the files in /tmp"
# Expect: agent calls execute_bash, returns file listing, summarizes
```

---

## Pre-flight checklist

- [ ] M1 has shipped (reasoning passthrough establishes streaming-modification pattern)
- [ ] OWUI version ≥ 0.5.4 (for tool_call rendering in chat panel)
- [ ] Ollama version ≥ 0.4.0 (for native tool-call protocol)
- [ ] All 8 MCP servers running (verify via `./launch.sh status`) — registry depends on them
- [ ] Operator has time for a 2-3 hour calibration session after M2 lands; this is the highest-impact change of the year and benefits from manual quality inspection

## Post-M2 success indicators

- agentorchestrator persona resolves "create a doc, save it, read it back" in one user turn
- auto-coding workspace runs `pytest` and reports failures via execute_bash
- Prometheus tool-call rate metric > 0 in Grafana within 1 hour of normal usage
- No security regressions: `creativewriter` persona cannot trigger code execution under any prompt

---

*End of M2. Next milestone: `TASK_M3_INFORMATION_ACCESS_MCPS.md`. M3 is gated on M2 — its new MCP servers (web_search, memory, RAG) are only useful with the tool-call loop in place.*
