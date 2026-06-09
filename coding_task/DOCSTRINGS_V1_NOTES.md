# DOCSTRINGS_V1_NOTES.md — Out-of-scope findings from TASK_DOCSTRINGS_PIPELINE_V1

The following were surfaced during the docstring pass on the four pipeline-critical
files. They are real findings that warrant follow-up tasks but are explicitly
out of scope for the docstring task. Each entry names the file, line, and what
to do later.

## REAL BUGS (priority)

1. **`portal_pipeline/router_pipe.py:2898–2903`** — indentation bug in
   `_stream_or_fallback`. The `for j, fb in enumerate(remaining):` loop body
   is empty; the `_try_non_streaming` call below it sits at the outer
   indentation. Effect: in the multi-candidate streaming fallback chain,
   only the LAST element of `remaining` is ever tried. A 3-candidate
   workspace where the first fails streaming, the second is healthy, and
   the third is unhealthy will skip the healthy second candidate silently.
   Reproducer and fix are mechanical (indent the call into the loop).
   ~~Recommend follow-up: `TASK_FIX_STREAM_FALLBACK_INDENT_V1`.~~
   **RESOLVED** by TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS.

## DEAD CODE (cleanup candidates)

2. **`portal_pipeline/router/workspaces.py:693`** — `_resolve_persona_browser_policy`
   has zero callers in the active codebase. Persona YAMLs do declare
   `browser_policy:` blocks matching its shape, suggesting either an
   incomplete feature (the pipeline→browser-MCP plumbing was never
   finished) or vestigial code (the wiring existed and was removed).
   Recommend follow-up to either wire it through to `browser_mcp.py`
   or remove and update `config/personas/` schema accordingly.

3. **`portal_pipeline/router_pipe.py:375`** — `watts_seconds_to_cost_usd`
   has zero callers. Likely scaffolded for a `/metrics` cost endpoint or
   Grafana panel that didn't land. The `_energy_consumed_ws_total`
   counter is the correct input. Recommend follow-up to wire as a
   derived gauge or remove.

4. **`portal_pipeline/router_pipe.py:3465 + 3481–3483`** —
   `_stream_from_backend_guarded`'s `sem: asyncio.Semaphore | None`
   parameter is dead. The only caller (`_stream_with_preamble:3450`)
   always passes `sem=None`; the `if sem is not None: sem.release()`
   branch is unreachable at HEAD. **RESOLVED** by
   TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS.

## LAYERING / STYLE

5. **`portal_pipeline/router_pipe.py:1419`** — `_validate_workspace_hints`
   reaches into `registry._workspace_routes`, a name-mangled-style private
   attribute of `BackendRegistry`. **RESOLVED** by
   TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS.

6. **`portal_pipeline/router_pipe.py:1814–1850`** — `health_all` keeps a
   hard-coded MCP catalogue listing 7 of the 12 model-facing MCPs in
   `tool_registry.MCP_SERVERS`. Missing: `memory`, `rag`, `research`,
   `music`, plus the correct `code-sandbox` URL. **RESOLVED** by
   TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS.

7. **`portal_pipeline/router_pipe.py:1838`** — `health_all` opens a fresh
   `httpx.AsyncClient(timeout=3)` per probe. The shared `_http_client`
   has a 300s timeout (designed for inference cold loads) which would
   make one down MCP hang the endpoint for 5 minutes. **RESOLVED** by
   TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS — probes now share one
   ``httpx.AsyncClient(timeout=3)`` via ``asyncio.gather``.

8. **`portal_pipeline/router_pipe.py:380–408`** — `_power_polling_loop`
   has `except Exception: pass` swallowing silently. Adding a
   `logger.debug("power polling error: %s", e)` would help operators
   debug socket-payload issues. Acceptable as degrade-gracefully behaviour;
   only a debug log addition needed.

9. **`portal_pipeline/router_pipe.py:1452–1458`** — `_model_supports_tools`
   doesn't early-return after finding a match. Models are unique in the
   registry; an early return inside the inner `for` would be marginally
   cheaper. Not a bug. **RESOLVED** by
   TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS.

10. **`portal_pipeline/router_pipe.py:1273–1276`** — the redteam-vs-security
    tiebreak in `_detect_workspace` embeds the literal `5`. Recommend
    lifting to a module-level constant if the tiebreak is ever touched.

11. **`portal_pipeline/router_pipe.py:2029`** — `list_backends_endpoint` has
    a `_endpoint` suffix because `_list_backends` was historically used
    elsewhere. Recommend rename to `list_backends` once history is
    reconciled.

## SEMANTIC GOTCHAS (document, don't fix)

12. **`portal_pipeline/router/workspaces.py:676`** — `_resolve_persona_tools`
   has a footgun: `tools_allow: []` in a persona YAML falls through to
   the workspace default rather than yielding "no tools." A persona
   that wants zero tools must enumerate them all in `tools_deny:`.
   **RESOLVED** by TASK_ROUTER_BACKEND_REVIEW_AND_IMPROVEMENTS — absent-vs-empty
   semantics restored (absent → workspace default; explicit `[]` → no tools).

## CONSISTENCY OBSERVATIONS (no action)

13. The `_record_*` dual-bookkeeping pattern in `router_pipe.py` (lines 72,
    79, 411, 507) maintains parallel Prometheus counters and plain dicts
    for the notification scheduler's daily-summary diffing. If a future
    refactor moves to "Prometheus only, derive summary from /metrics",
    all four functions can shed their dict half.
