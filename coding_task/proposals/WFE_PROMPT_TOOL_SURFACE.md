# WFE — the prompt names a tool the harness withholds (readiness pass 4, 2026-11-05)

Evidence base: `~/AI_Output/portal-data/tests/wfe/results/campaigns/ready4_mellum_20261105/rows/*.json`
(workspace `auto-coding::fast-repair`) and `ready4_autodaily_20261105` (Nemotron, `web_search` on
ru-v1-003).

## Findings

### 1. Where the surface narrows, and why

- The served surface of a production-tool-mode row is `tests/wfe/tool_modes.yaml`
  `<workspace>.allow` (`tests/wfe/eval_mode.py mode_for`). The pipeline offers and authorizes only
  that allowlist (`router/eval_gate.py apply_eval_scope`). For `auto-coding::fast-repair` the
  allow is `[execute_python, execute_bash, read_pdf]`; production (config/portal.yaml
  `workspaces.auto-coding.variants.fast-repair`) declares nine tools including
  `explore_repository`, and its `system_prompt_append` says "1. EXPLORE: call
  explore_repository(...) first".
- In production tool mode the client sends only `system_prompt_base`; the pipeline injects the
  append itself (`eval_mode.prepare`, campaign.py `sent_prompt`). The model is therefore
  instructed — by production's own append — to call a tool the row's surface does not carry.
- When the model obeys, the pipeline passes the call back to the client: `router/streaming.py`
  `client_owned = not all(name in effective_tools)` yields a passthrough of the raw tool_calls
  (the same rule as non_streaming.py's 2026-07-05 fix, so an undispatchable call is not consumed
  by a rejection loop). The harness then executed it in its sandbox:
  `tests/wfe/runner.py Sandbox.dispatch` → `"ERROR: unknown tool explore_repository"` — exactly
  the payload recorded on 8/16 Mellum rows (tool_call_log, error=true; 4 of them FAIL).
  kat, which ignored the EXPLORE instruction, was never penalized: the arm that obeys the
  production prompt is penalized, so the comparison is invalid.

### 2. What production's explore_repository actually does (checked in portal/)

- `portal/platform/mcp_host/pipeline_mcp.py _impl_explore_repository`: a FastContext subagent —
  it calls the explorer model (`PIPELINE_MCP_EXPLORER_MODEL`, default
  `qwen3-coder:30b-a3b-q4_K_M-ctx16k`) through live Ollama, then executes READ/GLOB/GREP via
  `_dispatch_fastcontext_tool`.
- All three operations are hardwired to `REPO_ROOT` (the portal-5 checkout): GLOB/GREP glob the
  repo only; READ resolves `REPO_ROOT / path`. For `/workspace/uploads/...` (an absolute path,
  which pathlib joins by replacement) it would read the host path `/workspace/uploads/...` —
  which does not exist on this host (`ls /workspace` → No such file or directory) — and return
  `ERROR: file not found: /workspace/uploads/...` to the explorer. **Production users of
  fast-repair therefore get an explorer that can never see their uploaded files**, and its
  schema takes `query`, not the `path` Mellum sent — production's own argument gate
  (`tool_registry._argument_error`) rejects that call with
  `unexpected keyword argument(s) ['path']; accepted: ['max_turns', 'query']`.
- Namespace scoping: the eval scope rides MCP call metadata (`eval_scope.EVAL_META_KEY`) and the
  sandbox/documents/memory MCPs honour it; pipeline_mcp's explorer consumes none of it, and
  `REPO_ROOT` is a process-global set at import. **The real tool cannot be namespace-scoped in
  eval, and serving it would also make each row depend on a live explorer model and expose
  portal-5 repo content (incl. `tests/wfe/`) to the row** — the repo-read leak the harness
  denies elsewhere.

### 3. The fix (harness-side; no production config or pipeline code touched)

`tests/wfe/eval_mode.py` now serves the production surface the prompt refers to:

- `PROXY_TOOLS` — harness-served proxies for named tools the allowlist lacks. For
  `explore_repository` the proxy validates the call against the production implementation's own
  signature (imported via `inspect.signature`, so it tracks pipeline_mcp changes) and rejects
  malformed args with production's exact registry wording; a valid query is answered by a
  deterministic, read-only GLOB/GREP-equivalent over the row's staged `in/` tree, citing files at
  the `/workspace/uploads/...` paths the task prompts use. Result shape matches production
  (`citations` / `turns_used` / `model` / `note`; `model: wfe_eval_namespace_proxy` marks it as
  the proxy, since no explorer model ran). Material outside the namespace → `citations: []`,
  production's out-of-repo behavior.
- Any other named-but-unserved tool (e.g. `web_search` on `auto-daily`) gets a **defined** JSON
  result — `{"error": "Tool 'X' is declared by the workspace but not served by this evaluation's
  tool surface"}` — never the sandbox's `"unknown tool"`.
- `eval_mode.prepare` attaches the proxy to the row's eval ctx (names also recorded in
  `evidence.proxied_tools`); `runner.run_task` hands it to the row's `Sandbox`;
  `Sandbox.dispatch` consults it before "unknown tool"; `_execute_calls` marks proxied entries
  `proxy: true` in `tool_call_log` and counts a proxied error payload as a tool error.
- The recorded `tool_surface` is unchanged (still the allowlist) and `tool_surface_proxy` stays
  the drift flag, so reuse fingerprints and the drift census are unaffected; the harness digest
  changes, which correctly refuses cross-harness row reuse.

### 4. Preflight

`campaign.prompt_tool_surface_report` checks every production-mode workload of a plan: served
prompt (base + pipeline-injected append) vs served surface (allow ∪ PROXY_TOOLS). A prompt that
names a tool the surface lacks FAILS the campaign's `tool surface preflight`, listing workspace +
tool. Sandbox-mode workspaces are exempt (their harness note declares the substitute surface).
Word-boundary matching against the config vocabulary follows `prompt_surface.py`'s convention
(only snake_case names count, so prose like "a failure to speak" is not a tool reference).

**Plans failing today (9 of 57 in tests/wfe/plans/):**

| plan | workspace | prompt names but surface lacks |
|---|---|---|
| cad_decision_v1.yaml | auto-coding::cad | execute_python, generate_part, render_openscad |
| compliance_decision_v1.yaml | auto-compliance | compliance_ask, compliance_context, compliance_review_decide_batch, compliance_review_list, web_search |
| qwen38_sampling_diag_v1.yaml | auto-compliance | (same five) |
| reading_decision_v1.yaml | auto-compliance::reading | compliance_conflicts, compliance_context |
| reading_long_screen.yaml | auto-compliance::reading | compliance_conflicts, compliance_context |
| realuse_sec_v1_seats.yaml | auto-compliance; auto-compliance::reading; auto-security; auto-security::blueteam | the four lists above |
| seat_card_sampling_ab_20261029.yaml | auto-compliance | (the five) |
| security_analysis_decision_v1.yaml | auto-security | web_search |
| sweep_from_queue_v1.yaml | auto-compliance | (the five) |

Every one of these workspaces has been running rows whose models could hit "unknown tool" for a
tool the production prompt/OWUI prompt names — the same defect class as fast-repair. Widening an
allowlist or rewording a workspace prompt is an instrument/seat decision, so this report stops at
the gate; opening any of these plans now refuses with the list above until the operator decides.

## What changed

- `tests/wfe/eval_mode.py` — PROXY_TOOLS registry + explore_repository namespace proxy;
  `known_tool_names()`; `proxy_tools()`; prepare/finish wiring + evidence.
- `tests/wfe/runner.py` — `workspace_context` also returns `system_prompt_append`;
  `Sandbox(proxy=...)`; `run_task` attaches the row proxy; `_execute_calls` marks/counts proxies.
- `tests/wfe/campaign.py` — `prompt_tool_surface_report`; `_realuse_tool_preflight` now runs the
  prompt check on every plan (the realuse task-tool check unchanged).
- `tests/wfe/tests/test_wfe_tool_surface_proxy.py` — 14 offline tests (proxy answers, production
  arg rejection, run wiring, preflight FAIL/PASS, row evidence).

## Deliberately NOT done

- No change to `config/portal.yaml` (production `system_prompt_append`, tools) or to
  `tool_modes.yaml` allowlists — both are instrument/seat decisions.
- No production prompt edit: **the fast-repair append is wrong for production too** — it orders
  "EXPLORE first" on uploaded sandbox files while `explore_repository` explores only the portal-5
  repo and can never see `/workspace/uploads`. Production users get either a live-model walk of
  portal-5 (irrelevant citations) or a file-not-found. Needs operator review: repoint the append's
  EXPLORE step at execute_bash/read flows for uploaded-material work, or give pipeline_mcp an
  uploads-aware explorer (would need REPO_ROOT-per-call scoping and a model budget).

## Verification

- `uv run pytest tests/wfe -q -n 2` → 1268 passed, 1 skipped.
- `uv run pytest tests/unit -q -n 2` → 4894 passed, 116 skipped.
- `uv run ruff check .` / `uv run ruff format --check .` → clean.
- `uv run mypy portal/` → Success (portal/ untouched).
- `python3 scripts/complexity_report.py --gate` → GATE OK.
- Preflight CLI: FAIL plan exits 4 listing workspace+tool on stderr, stdout clean; PASS plan
  prints `tool surface preflight: PASS (68 check(s))` to stderr and `--list-arms` stdout intact.
