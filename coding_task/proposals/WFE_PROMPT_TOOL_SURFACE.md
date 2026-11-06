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
  malformed args with production's exact registry wording; a valid query returns production's
  answer for uploads work: `citations: []` with a note that `/workspace/uploads` is outside the
  repository the explorer searches (`model: wfe_eval_namespace_proxy`). Reviewer change
  2026-11-05: the lane's first version keyword-searched the staged uploads and cited them — a
  capability production users do not have, so the proxy would have measured a kinder world.
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

## Round 2 — serve the named tools; reword fast-repair EXPLORE (2026-11-05)

Round 1 stopped at the gate and left `config/portal.yaml` and the nine named-but-unserved tools
for an operator decision ("Deliberately NOT done" above). The operator delegated that decision:
a production-mode workload is served the tools its production prompt and `tools:` name, and the
fast-repair EXPLORE step is reworded. `tests/wfe/tool_modes.yaml` allowlists are still unchanged.
The nine tools are harness proxies (`PROXY_TOOLS`), the same pattern as `explore_repository`, so
the recorded `tool_surface` stays the allowlist.

### Decision

| tool | choice | why |
|---|---|---|
| execute_python | (a) real call | Native sandbox MCP `:8914` with `portal5/eval` metadata, so the sandbox confines `/workspace`. The REST route does not bind eval. Arguments are checked against the production parameter list without importing `code_sandbox_mcp` (that import creates `data/sandbox`). A transport failure excludes the row; a returned payload, including `success: false`, is scored. |
| generate_part | (c) exclude | Writes the shared `models3d` directory and publishes to Open WebUI. `cad_render_mcp` does not read the eval scope. |
| render_openscad | (c) exclude | Runs host OpenSCAD into that same shared directory. No eval scope. |
| compliance_ask | (c) exclude | Not in the eval instance's `VERIFIED_TOOLS` (`:8948` returns 403). It calls the reading model and writes a derived source (`store=True`) or a receipt (`store=False`). An in-process `_repo()` opens the operator compliance store. |
| compliance_context | (c) exclude | Not verified. An in-process call opens the operator database. The 403 is not bypassed. |
| compliance_conflicts | (c) exclude | Same as `compliance_context`. |
| compliance_review_list | (c) exclude | Reads the operator Lance review queue. The eval instance refuses it. |
| compliance_review_decide_batch | (c) exclude | Writes the mapping store and requires a reviewer token. The eval instance refuses it. |
| web_search | (b) real SearXNG | Direct GET of SearXNG `/search` (engines pin matches `web_search_mcp._SEARXNG_ENGINES`). Not `web_search()`, not `_searxng_search` (those can use Brave or the browser and swallow errors). Every attempted query is stored on the row, including the unreachable path. Unreachable excludes the row; a completed search, including an empty result list, is scored. Bad arguments are a tool error the model can fix. Production may lead with Brave when `BRAVE_API_KEY` is set; this eval serves SearXNG only. |

An excluded call returns `{"error": "Tool '<name>' is not executed in this evaluation", "excluded_from_scoring": true, "reason": ...}` and appends `{tool, reason}` to the row. The runner and `eval_mode.finish` mark that row `BLOCKED` (an instrument outcome, kept out of quality rates) unless the outcome is already `HARNESS_ERROR`. The checker's verdict is kept as `checker_outcome`.

`execute_python` and `web_search` attach only where the allowlist lacks them (`auto-coding::cad` for the sandbox; compliance and security for search). Workspaces that already allow the tool keep the pipeline path.

### Preflight

`campaign._realuse_tool_preflight` on every file in `tests/wfe/plans/`: **PASS 59 / 59, FAIL 0.**
The nine plans round 1 refused (`cad_decision_v1`, `compliance_decision_v1`, `qwen38_sampling_diag_v1`,
`reading_decision_v1`, `reading_long_screen`, `realuse_sec_v1_seats`, `seat_card_sampling_ab_20261029`,
`security_analysis_decision_v1`, `sweep_from_queue_v1`) pass. The plan directory now holds 59 files
(round 1 counted 57).

Passing plans: `advance_gemma_qat_plain_20261029`, `advance_seat_card_screen_20261029`,
`audio_decision_v1`, `auto_coding_next_screen_20261019`, `auto_daily_quant_screen_20261019`,
`cad_decision_v1`, `coding_decision_v1`, `compliance_decision_v1`, `data_decision_v1`,
`decision_run_v1`, `documents_decision_v1`, `documents_h2h_v1`, `engine_ab_compliance`,
`engine_ab_ollama`, `engine_ab_omlx`, `extract_decision_v1`, `gemma_qat_vs_plain_ab_20261029`,
`general_decision_v1`, `general_fast_k2_screen_20261019`, `laguna21_omlx`, `mimo_fit`,
`mimo_fit_omlx`, `p2a_acceptance`, `prompt_surface_rebaseline`,
`prompt_surface_rebaseline_v2_r6_noformat`, `prompt_surface_rebaseline_v2_r6_think`,
`qwen38_sampling_diag_v1`, `reading_decision_v1`, `reading_long_screen`, `realuse_sec_v1_seats`,
`realuse_v1_autocoding_ab`, `realuse_v1_autodaily_confirm`, `realuse_v1_autodaily_gemma_think`,
`realuse_v1_autodaily_incumbent`, `realuse_v1_documents`, `realuse_v1_mellum`, `realuse_v1_reruns`,
`realuse_v1_s5s7s10`, `realuse_v1_s8`, `realuse_v1_s8_rerun`, `realuse_v1_tool_carry_ab`,
`reasoning_hard_screen`, `reasoning_math_decision_v1`, `research_decision_v1`,
`research_nex25_screen`, `routing_decision_v1`, `s2_laguna_rerun_omlx`,
`s8_fast_incumbent_baseline_20261029`, `s8_flint_coding_screen_20261029`,
`s8_lfm25_general_screen_20261029`, `s8_lfm3_fast_screen_20261029`,
`s8_mellum_fast_repair_screen_20261029`, `saluki_spike`, `seat_baseline_v3`,
`seat_card_sampling_ab_20261029`, `security_analysis_decision_v1`, `sweep_from_queue_v1`,
`tools_specialist_decision_v1`, `vision_decision_v1`.

### Fast-repair prompt

`workspaces.auto-coding.variants.fast-repair.system_prompt_append` only. Steps 2–6 and HARD
CONSTRAINTS are unchanged. Decoded append is 888 characters. `uncensored-agentic` and the
`read_text_file` loop are untouched.

```diff
-1. EXPLORE: call explore_repository('what you need to find') first.
-   It returns exact file paths and line numbers — use these, do not guess paths.
+1. EXPLORE: list and read uploaded or sandbox files with execute_bash
+   (ls, cat, rg under /workspace/uploads). Call explore_repository only
+   for a repository question; it cannot see /workspace/uploads.
```

`uv run python -m portal.platform.inference.cli sync-config` reported no change to
`backends.yaml` workspace_routing, `.mcp.json`, `workspaces_all.json`,
`imports/openwebui/workspaces/`, `config/orchestration_arm.yaml`, or
`config/modules.generated.yaml`. The append is pipeline-injected from `portal.yaml`; those
derived files do not carry it.

### What changed

- `tests/wfe/production_surface.py` — handlers for the nine tools: scoped sandbox MCP,
  SearXNG GET, and defined exclusion payloads.
- `tests/wfe/eval_mode.py` — registers those handlers on `PROXY_TOOLS`; `finish` persists
  `web_search_queries` and `scoring_excluded` and marks the row `BLOCKED`.
- `tests/wfe/runner.py` — `_unscored_tool_row` applies the same exclusion at every `_classify`
  return. `HARNESS_ERROR` is preserved.
- `tests/wfe/tests/test_wfe_production_surface.py` — stubs, no network: served tools, argument
  rejection, unreachable sandbox and SearXNG, exclusion versus a checker FAIL and a checker
  PASS, `finish`, the fast-repair sentence, and `prompt_tool_surface_report` on every plan.
- `config/portal.yaml` — the fast-repair step 1 above.
- This proposal.

### Residuals

- The pipeline still does not offer these nine tools in the request `tools` array when they
  are off the allowlist. It returns the call and the harness executes it. Measurement matches
  execution of a named tool, not the offered schema.
- `execute_python` session directories under the sandbox data dir are shared across rows, the
  same as production allowlisted `execute_python`.
- `--rerun-failed` re-offers `BLOCKED` rows (`campaign._arm_todo` retry states include
  `BLOCKED`). An excluded row will be run again.
- The eval `web_search` path is SearXNG-only even when production would use Brave.
