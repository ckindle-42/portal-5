# MCP standard evaluation — 2026-10-23

## Scope and verified baseline

The repository lock pins `mcp==2.3.0` for Portal's Python MCP services; the Python SDK v2 line implements the `2026-07-28` protocol and remains dual-era for clients negotiating `2025-11-25` and earlier. Open WebUI v0.12.3 pins `mcp==1.27.2`; its client calls `session.initialize()`, uses the v1 Streamable HTTP client, and therefore negotiates `2025-11-25`. Its tool listing currently ignores `outputSchema`, while its call path consumes `structuredContent` and adds it as JSON text when needed. Portal's generated Open WebUI registration sets `type: "mcp"` and `path: "mcp"`.

Sources: [`uv.lock`](../uv.lock), [MCP Python SDK v2 migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md), [Open WebUI v0.12.3 requirements](https://raw.githubusercontent.com/open-webui/open-webui/v0.12.3/backend/requirements.txt), [Open WebUI v0.12.3 MCP client](https://raw.githubusercontent.com/open-webui/open-webui/v0.12.3/backend/open_webui/utils/mcp/client.py), [Portal Open WebUI registration](../scripts/openwebui_init.py).

The wiki search/get/explain tools and Context7 were unavailable in this worker session; local `portal` CLI has no wiki command. Fleet discovery below is grounded in the current config, code, lock, and test files, not a runtime probe.

## Part 1 — changes from 2025-11-25 to 2026-07-28

| Change | Portal fleet use or need | Reachable through Open WebUI v0.12.3 / MCP 2025-11-25? |
|---|---|---|
| Stateless protocol era: 2026 removes `initialize` / `initialized` and `Mcp-Session-Id`; each request carries protocol version, client identity, and capabilities in `_meta`. `server/discover` is available but optional. | Portal servers use SDK 2.3.0 and can serve the 2025 legacy path or modern 2026 path. The Pipeline currently bypasses MCP with REST. A native Pipeline client must send the selected protocol metadata on each request; it does not need a session for the modern path. | No modern wire exchange. The bundled SDK initializes a 2025 session; the dual-era Portal servers continue to accept it. |
| Streamable HTTP standard headers and routing: modern POSTs carry `MCP-Protocol-Version`, `Mcp-Method`, and, where applicable, `Mcp-Name`. `x-mcp-header` can mirror selected string/integer/boolean inputs into `Mcp-Param-*`. | Needed by a hand-written current client. No Portal MCP input schema uses `x-mcp-header`; routing headers provide no current tool behavior. | No modern header contract. The client uses the legacy session binding. |
| Tool output: `outputSchema` and `structuredContent` now support any JSON Schema 2020-12 / JSON value in 2026; the 2025-era contract is object-shaped. | Portal SDK 2 infers output schemas and structured values from typed return annotations. Most typed `dict[str, Any]` tools return an object and remain compatible. Bare `dict` return annotations do not infer structured output. | `structuredContent` is read by Open WebUI and appended as JSON text when needed. Its tool mapping has a TODO for `outputSchema`, so schemas are not propagated to the model. 2026-only array/scalar shapes are not usable over its legacy session. |
| Long-running calls: `2025-11-25` had experimental task augmentation. The 2026 `io.modelcontextprotocol/tasks` extension uses `tasks/get`, `tasks/update`, and `tasks/cancel`; it is not wire-compatible with the prior experiment. Progress notifications remain available when requested with a progress token. | No Portal server declares task support. Long operations still use synchronous tool calls or explicit start/status/result tools. A task extension could help long media generation, but SDK 2.3.0's migration guide says that extension is not implemented in the Python SDK. The Pipeline sends no progress token today. | The v1 SDK contains experimental task types, but Open WebUI's call path does not request or poll tasks and has no progress callback. Task execution/progress is not surfaced through this client path. |
| Elicitation and server-to-client requests: 2025 clients receive pushed `elicitation/create` (form or URL). Modern clients receive `input_required` and retry the original request with `inputResponses`; 2026 has no server-initiated JSON-RPC requests. Sampling and Roots likewise move to the multi-round-trip model. | Portal tools do not call elicitation, roots, or sampling APIs. No current need is established. | Open WebUI's v1.27 client has an elicitation callback and UI event path for the legacy protocol. It cannot handle 2026 `input_required` / MRTR. |
| Authorization: 2026 requires issuer validation and binds credentials to their issuer; Client ID Metadata Documents replace Dynamic Client Registration as the preferred registration path, and DCR is deprecated. | Portal's configured MCP fleet is local/internal and has no OAuth-protected MCP endpoint in `mcp_fleet`. Do not add OAuth machinery to the Pipeline pilot. Revisit if protected remote servers enter the fleet. | Open WebUI v0.12.3 has legacy OAuth support. It does not use 2026 issuer-binding or modern registration behavior. |
| Cancellation: modern Streamable HTTP cancels an in-flight request by closing that request's response stream; legacy cancellation uses `notifications/cancelled`. | Current REST calls have no MCP cancellation message. A native HTTP call can be cancelled by cancelling/closing its request; timeout and task cancellation must propagate. | The SDK supports legacy cancellation. Application-level cancellation depends on the Open WebUI call lifecycle; the Portal Pipeline REST path does not speak it. |
| Notifications, subscriptions, and cache behavior: change notifications move to `subscriptions/listen`; list/read results gain `ttlMs` and `cacheScope`, and servers should return stable tool order. Trace context conventions are documented in `_meta`. | Portal currently relies on periodic Pipeline refresh and does not use MCP resource subscriptions or trace propagation. Stable list order and cache hints are useful for future tool cache work. | Not reachable as 2026 behavior. The current periodic tool-list refresh remains the active cache path. |
| Deprecations/removals: HTTP+SSE is deprecated; Roots, Sampling, and Logging are deprecated; DCR is deprecated; modern connections remove sessions and server-initiated requests. | The Portal HTTP services use Streamable HTTP, not HTTP+SSE. A source scan found no first-party use of `FastMCP`, `mcp.server.fastmcp`, `get_context()`, deprecated experimental Tasks runtime, or old client transport aliases. The Portal code uses `MCPServer`, `@mcp.tool()`, and `streamable-http`. | Legacy behavior remains available on 2025 sessions, so these deprecations do not block the current Open WebUI connection. |

The 2025-11-25 revision itself added URL-mode elicitation, tool calling during sampling, experimental Tasks, OIDC authorization-server discovery, and recommended Client ID Metadata Documents. Those are distinct from the 2026 stateless/MRTR changes above. Official references: [2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog), [2026-07-28 release notes](https://blog.modelcontextprotocol.io/posts/2026-07-28/), [2026 current changelog](https://modelcontextprotocol.io/specification/draft/changelog), [versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [Tasks extension](https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks), and [Python SDK migration](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md).

## Part 2 — fleet audit

The inventory is the 33 entries under `config/portal.yaml:mcp_fleet`. “REST shim” means a Pipeline-compatible HTTP discovery route plus tool POST route; “partial” means only one side is present. For Portal Python servers, output schemas are inferred by SDK 2.3.0 from return type annotations; they are not manually passed as `output_schema=` on the tool decorator. Return types below were checked in each implementation file.

| Fleet ID | SDK / transport | REST shim | Native output schema / structured content | Deprecated APIs |
|---|---|---|---|---|
| `filesystem` | Upstream Node MCP package, version floating via `npx`; stdio | No | Upstream-dependent; not declared in Portal source | Not auditable from the floating package manifest |
| `fetch` | Python MCP SDK v1 (`mcp<2.0.0`); stdio | No | Upstream-dependent; not declared in Portal source | Portal does not own upstream implementation |
| `git` | Python MCP SDK v1 (`mcp<2.0.0`); stdio | No | Upstream-dependent; not declared in Portal source | Portal does not own upstream implementation |
| `serena` | Git-installed upstream Python server; stdio; SDK/version not pinned in Portal config | No | Upstream-dependent; not declared in Portal source | Cannot verify without resolving the unpinned Git command |
| `docker` | Upstream Node package, version floating via `npx`; stdio | No | Upstream-dependent; not declared in Portal source | Not auditable from the floating package manifest |
| `music-minimax` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `mflux` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `video_mlx` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `documents` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object/list outputs | None found |
| `execution` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object/list outputs | None found |
| `whisper` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `tts` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `security` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `memory` | Python `mcp==2.3.0`; Streamable HTTP | Yes, REST-only tool routes | None; no native `@mcp.tool()` registrations | None found |
| `rag` | Python `mcp==2.3.0`; Streamable HTTP | Yes, REST-only tool routes | None; no native `@mcp.tool()` registrations | None found |
| `research` | Python `mcp==2.3.0`; Streamable HTTP | Yes, REST-only tool routes | None; no native `@mcp.tool()` registrations | None found |
| `browser` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `mlx_transcribe` | Python `mcp==2.3.0`; Streamable HTTP mounted at `/mcp` | Yes, FastAPI discovery and dispatch routes | No; both tool functions return bare `dict` | None found |
| `cad_render` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `proxmox` | Python `mcp==2.3.0`; Streamable HTTP | Partial: GET `/tools`, no REST tool POST | Yes; inferred object outputs | None found |
| `pipeline` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object/list outputs | None found |
| `mitre` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `detections` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `wiki` | Python `mcp==2.3.0`; Streamable HTTP | Partial: GET `/tools`, no REST tool POST | No; three tools return bare `dict` | None found |
| `binresearch` | Python `mcp==2.3.0`; Streamable HTTP | Partial: explicit tool POSTs, no GET `/tools` | Yes; inferred object outputs | None found |
| `vulnintel` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `icsot` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `compliance` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `detection` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `context7` | Upstream Node MCP package, version floating via `npx`; stdio | No | Upstream-dependent; not declared in Portal source | Not auditable from the floating package manifest |
| `data` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `netforensics` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |
| `review` | Python `mcp==2.3.0`; Streamable HTTP | Yes | Yes; inferred object outputs | None found |

Key audit consequences:

- The three REST-only servers (`memory`, `rag`, and `research`) expose no native MCP tools to Open WebUI despite having `/mcp` endpoints. Their current model-facing tools exist only on custom REST routes.
- `wiki` and `binresearch` have an incomplete Pipeline REST pair; `proxmox` is not exposed to Pipeline and only has REST discovery. These are not suitable early migration targets.
- Native typed outputs are usually compatible with 2025 clients because the SDK returns an object-shaped `structuredContent` and matching text. `wiki` and `mlx_transcribe` use bare `dict` annotations and do not receive SDK-inferred output schemas. Open WebUI currently ignores the schema even where the server publishes it.
- `Dockerfile.pipeline` does not install `mcp`; it currently installs `fastapi`, `uvicorn`, `httpx`, `pyyaml`, `prometheus-client`, and `APScheduler`. The first four-package list in rule 9 describes the intended floor, while the current file includes the last two existing runtime dependencies.

Repository anchors: [fleet config](../config/portal.yaml#L304), [Pipeline ToolRegistry](../portal/platform/inference/tool_registry.py), [Pipeline MCP](../portal/platform/mcp_host/pipeline_mcp.py), [security REST parity tests](../tests/unit/test_security_mcp_rest_dispatch.py), [Pipeline REST parity tests](../tests/unit/test_pipeline_mcp_rest.py), [Open WebUI MCP registration](../scripts/openwebui_init.py), and [Pipeline image](../Dockerfile.pipeline).

## Part 3 — Pipeline decision

| Option | Correctness against 2026-07-28 | Image | Maintenance |
|---|---|---|---|
| **(a) Small httpx client** | A carefully bounded client can correctly implement JSON-RPC request IDs, per-request `_meta`, required HTTP headers, JSON and request-scoped SSE responses, error bodies, timeout, and cancellation-by-closing the HTTP request. The modern protocol has no session handshake. The first slice can pin 2026-07-28 for the current Python SDK 2.3 pilot; before other servers are enabled, add modern/legacy detection and `2025-11-25` initialization fallback. It does not implement OAuth, elicitation, tasks, or subscriptions. | No added dependency; `httpx` is already in the Pipeline image. | Highest protocol ownership. Keep scope narrow, add contract tests, and pin the supported protocol subset. |
| **(b) Add `mcp` SDK** | Best standard coverage and dual-era negotiation, response decoding, and future SDK fixes. The official SDK handles details that are easy to get wrong in handwritten transport code. `mcp==2.3.0` does not yet implement the new Tasks extension. | Adds `mcp`, `mcp-types`, `httpx2`, `jsonschema`, `opentelemetry-api`, `pyjwt[crypto]`, `python-multipart`, `sse-starlette`, and associated dependencies; exact installed image delta is not measured. It changes the deliberate minimal Pipeline image boundary. | Lower protocol-specific code burden; upgrades must track SDK API and image dependency changes. |
| **(c) Keep the REST shim** | Correct only for Portal's custom JSON bodies. It skips MCP lifecycle/version negotiation, standard error semantics, cancellation, structured output, and progress. | No added dependency. | Lowest immediate work, but duplicates manifests, dispatch wrappers, and parity suites indefinitely. |

**Recommendation: (a), with explicit scope and rollout gates.** The Pipeline only needs tool listing and calls, and its image already contains `httpx`. A small client keeps rule 9 intact while using the modern current protocol against SDK 2.3.0 servers. It should not pretend to be a general-purpose MCP client: no OAuth, Tasks, elicitation, resources, prompts, subscriptions, or stdio support. A version-fallback phase is required before enabling it for servers that may be SDK v1 / 2025-only.

Phased plan:

1. **Pilot (this slice):** add the stateless 2026-07-28 HTTP path behind `PIPELINE_NATIVE_MCP_CLIENT=1`, restricted to the `pipeline` server; test JSON/SSE, required metadata and headers, error mapping, cancellation, pagination, and timeout using `httpx.MockTransport`. Keep the current REST path as the default and retain the REST parity tests.
2. **Dual-era client:** add protocol detection and legacy `initialize` / `notifications/initialized` / `Mcp-Session-Id` handling. Add server-by-server opt-in only after native `tools/list` schemas and `tools/call` results pass offline parity and one controlled live-route check. Preserve WFE compliance isolation and any per-server authorization behavior.
3. **Fleet migration:** move each Pipeline-exposed service independently, carrying forward circuit-breaker behavior, eval scoping, explicit long-call timeout policy, and user-visible error shape. Keep rollback to REST per server until parity is established. Resolve the REST-only `memory`, `rag`, and `research` servers by registering native tools before migrating them.
4. **Removal:** after every exposed tool is served and called natively, remove custom REST manifests/routes and their parity tests. Replace parity assertions with native MCP `tools/list` / `tools/call` contract tests, and verify the served Pipeline route with current fleet identities before deleting the fallback flag.

## Part 4 — first slice

Implemented `portal/platform/inference/mcp_http.py` and wired the Pipeline `ToolRegistry` to use it only when `PIPELINE_NATIVE_MCP_CLIENT=1` and `server_id == "pipeline"`. The native path is stateless 2026-07-28 only, handles paged `tools/list`, JSON or SSE responses, per-request metadata and headers, JSON-RPC errors, timeouts, and cancellation. The REST path remains the default for every server; no live service or Docker command was run.
