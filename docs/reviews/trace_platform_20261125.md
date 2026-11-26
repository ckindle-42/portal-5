# Platform trace — 2026-11-25

Scope is the pipeline platform: router, catalog merge, aliases, seeding, sync-config, launch wiring, pipeline MCP `:8928`, proxmox MCP `:8927`, data MCP `:8939`, and the Open WebUI task-router seat. Counts below were taken from `config/portal.yaml`, `config/bench_workspaces.yaml`, `config/personas/`, and `@mcp.tool` defs. No live stack was exercised.

Derived inventory: 22 workspace keys in `portal.yaml` (21 user engines plus `task-router`), 28 bench workspaces, 16 aliases, 13 pipeline tools, 36 proxmox tools, 4 data tools. `workspace_routing` has the same 50 ids and no extras. Every alias `to:` is a production `engine::variant`.

Seat column is the effective `model_hint`. Fallback is the `workspace_routing` group order (oMLX alias first when the backend declares one, else the next healthy group, else `general`). Coverage names the QAT/UAT case when one exists.

| Item | Entry | Seat / model | Fallback | Tools | Trace | Coverage | Status |
|---|---|---|---|---|---|---|---|
| router_pipe shim | OWUI `model` → `router_pipe.app` re-export | n/a | n/a | n/a | route spans live in `router/handlers.py` | unit routing tests | OK |
| catalog merge | `load_portal_config` | bench lanes only if eval or `PORTAL_ENABLE_EVAL` / `PORTAL_BENCH_WORKSPACES` | collision raises | n/a | n/a | `tests/unit` config schema | OK |
| aliases (16) | deprecated id → `engine::variant` | target variant hint | target's groups | target's tools | alias hit counter | `test_math_alias_is_removed_from_router_labels` | OK |
| openwebui_init | persona YAML → OWUI model | workspace of `workspace_model` + `variant` | seat fallback | `resolve_preset_tools` | n/a | seed is live-only | OK |
| sync-config | `portal.yaml` → routing, `.mcp.json`, presets | routing kept for eval ids even when eval is off | n/a | fleet ports | n/a | emitter unit tests | OK |
| launch wiring | `./launch.sh up` | pipeline-mcp and data-mcp host-native; proxmox `mcp-proxmox` container | n/a | ports 8928 / 8939 / 8927 | n/a | none in unit | OK |
| task-router | OWUI `TASK_MODEL_EXTERNAL=task-router` | `gemma-4-E4B-it-OBLITERATED` `Q4_K_M-ctx2k`, ctx 2048, temp 0.2, think false | routing group `general` | none | route span once the seat is addressable | excluded from designed QAT (`test_config_and_scenarios`) | OK (fixed this lane) |
| hint mismatch trace | served model ≠ `model_hint` | whatever the backend substituted | metric `portal5_hint_fallback_total` | n/a | span `model.hint_mismatch` | `test_hint_mismatch_trace` | OK (fixed this lane) |
| auto-research::data | persona `variant: data` or `auto-research::data` | `Qwen3.6-35B-A3B` `UD-Q4_K_XL-ctx32k` | research groups `reasoning`, `general` | execute_python, create_excel, kb_search, attach_source, run_sql, profile_table, list_session | tool spans if the loop runs | UAT `s5-data-sql` grades prose for totals 133 and 76 | GAP |
| dataanalyst | slug → `auto-research` variant `data` | same seat | same | same; prompt says to print SQL | same | same UAT, not the persona prompt | DEFECT |
| datascientist, databasearchitect, machinelearningengineer, dataextractor, dashboardarchitect, statistician | same variant `data` | same seat | same | inherit the variant; prompts do not name the DuckDB tools | same | none per persona | GAP |
| auto-coding | OWUI coding engine | `Qwen3.8-27B` `Q4_K_M-ctx96k` | groups `coding`, `general` | base list includes all 36 proxmox tools | tool name + outcome | UAT `s5-proxmox-readonly` markers only | DEFECT |
| auto-coding personas without `tools_allow` (23) | persona slug → `auto-coding` | coding seat | coding groups | inherit the 36 proxmox tools | same | none | DEFECT |
| bugdiscoverycodeassistant, e2edebugger | `tools_allow` | coding seat | coding groups | proxmox stripped | same | none | OK |
| auto-daily::fast | General · Fast, Jarvis `FAST_WORKSPACE` | `Qwen3.6-35B-A3B` `UD-Q4_K_XL-ctx96k` | daily group `general` | read-only repo tools, all 36 proxmox tools, git commit/push, `get_pipeline_status`, `get_loaded_models` | tool spans | UAT `s5-proxmox-readonly` and `s5-platform-introspection-and-git`, marker grader | DEFECT |
| auto-coding::laguna | `codingagentic` variant `laguna` | Laguna seat on the coding groups | coding groups | explore_repository, read_text_file, list_directory, search_files, write_file | explorer citations | no dedicated scenario | OK |
| get_pipeline_status | pipeline MCP | n/a | HTTP to `:9099` | schema: no args | not a chat trace | UAT marker case on `auto-daily::fast` | OK |
| list_workspaces | pipeline MCP | n/a | pipeline HTTP | `filter` | n/a | none | GAP |
| get_loaded_models | pipeline MCP | n/a | Ollama `/api/ps` | no args | n/a | UAT marker case | GAP |
| get_metrics_summary | pipeline MCP | n/a | pipeline metrics | no args | n/a | none | GAP |
| get_workspace_recommendation | pipeline MCP | n/a | local catalog | `task` | n/a | none | GAP |
| explore_repository | pipeline MCP | explorer model env, default `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | n/a | `query`, `max_turns` | citations only | none | OK (confine fixed) |
| trigger_backend_warmup | pipeline MCP | default workspace `codingagentic` (persona → laguna) | chat completions | `workspace` | a real chat trace | none | OK |
| jarvis_submit | pipeline MCP | plugin `jarvis_submit` | error if the plugin is absent | `text`, `user_id` | n/a | jarvis unit tests, not this tool | OK |
| arm_queue_task | pipeline MCP | plugin `arm_queue_task` | error if orchestration is off | task_id, discipline, template_key, parameters, source_dir | n/a | orchestration unit tests | OK |
| read_text_file | pipeline MCP | n/a | repo or `/tmp` | path, line range | n/a | none | OK |
| list_directory | pipeline MCP | n/a | repo or `/tmp` | path | n/a | none | OK |
| search_files | pipeline MCP | n/a | repo or `/tmp` | pattern, path, glob | n/a | none | OK |
| write_file | pipeline MCP | n/a | repo root only (`/tmp` is not writable) | path, content | n/a | none | OK |
| attach_source | data MCP `:8939` | n/a | file under `DATA_MCP_ROOT` (default `AI_OUTPUT_DIR`) | session_id, path, table | tool error string | UAT `s5-data-sql` | OK |
| run_sql | data MCP | n/a | session DB, external access off | session_id, sql, max_rows | error string | UAT prose totals | OK |
| profile_table | data MCP | n/a | session DB | session_id, table | error string | UAT asks for a mean; grader ignores it | GAP |
| list_session | data MCP | n/a | session DB | session_id | error string | UAT asks; grader ignores it | GAP |
| close_session | not a tool; `POST /eval/close_session` | n/a | eval scope only | n/a | n/a | data module tests | OK |
| proxmox read tools (18): list/status/config/find/tasks/storage/networks/agent_info | `:8927` REST | n/a | Proxmox API, 30s HTTP client | see each schema | `{success, data}` or `{success:false, error}` | UAT uses 3 of them, marker grader | OK |
| proxmox power/snapshot/clone/delete (16) | `:8927` REST | n/a | UPID + `_wait_task` 120s | vmid, node, wait | success true even when task status is `timeout` | forbidden-tool list on the read-only UAT only | GAP |
| proxmox_exec_vm | guest agent | n/a | poll default 30s | command list | timeout still `success: true` | none | DEFECT |
| proxmox_container_exec | SSH `pct exec` | n/a | SSH timeout arg | command | `success` follows `ok` | none | OK |
| proxmox_node_exec | SSH on the Proxmox host | n/a | SSH timeout arg | command | `success` follows `ok` | none | OK (fixed this lane) |
| proxmox_deploy_ctf_lab | SSH, git allowlist of one URL | n/a | 300s per step | vmid, lab, git_url | always `success: true`; `containers_up` is a substring check | none | DEFECT |

## Findings

### F1 — task-router 404 while eval is off (fixed)

`config/portal.yaml` `task-router` is `module: eval`. `modules.eval.enabled` is false. `get_workspace_dict` dropped eval workspaces, and `is_workspace_disabled` (`portal/platform/wiki/adapters/modules.py`) returned true, so `handlers._reject_disabled_workspace` answered HTTP 404. OWUI is seeded with `TASK_MODEL_EXTERNAL=task-router` (`scripts/openwebui_init.py`). Title, tag, and follow-up calls never reached the 2048-ctx resident model; they failed before routing. That is the failure the seat's own description says it prevents (a task call loading or evicting a large chat model).

Severity: breaks-results. Confidence: high (control flow, not a live call).

Fix this lane: the seat stays in the runtime catalog and is not module-disabled; `router: false` keeps it out of `_VALID_WORKSPACE_IDS`. It stays `expose_to_owui: false`, so sync-config still does not emit a user preset. `portal_channels/dispatcher.py` `VALID_WORKSPACES` lists it the same way as `hunt-reasoning`: the channel roster must match the pipeline catalog, and Telegram `/workspace` will show the id. A channel message addressed to it is a direct completion, not an auto-router label.

Live check: with eval left off, `POST http://127.0.0.1:9099/v1/chat/completions` body `{"model":"task-router","messages":[{"role":"user","content":"title: hello"}],"max_tokens":16,"stream":false}` and header `Authorization: Bearer $PIPELINE_API_KEY`. Worked: HTTP 200, `model` is the ctx2k gemma tag (or its oMLX alias), and `GET /v1/trace/{id}` has `workspace` `task-router`. Did not work: HTTP 404 `module not enabled`, or a 200 whose model is a different seat.

### F2 — explorer READ followed absolute paths (fixed)

`pipeline_mcp._dispatch_fastcontext_tool` READ did `REPO_ROOT / path`. An absolute path replaces the root (`Path(repo) / "/etc/passwd"` is `/etc/passwd`). `../` resolved outside the repo. `read_text_file` already confines; the explorer path did not. `explore_repository` is on `auto-coding::laguna`. A query that makes the explorer emit `READ /…` returned host file bytes.

Severity: stability. Confidence: high.

Fix this lane: repo-relative paths only, after `resolve()`, must stay under `REPO_ROOT`. GLOB and GREP reject absolute patterns and `..`.

Live check: call pipeline MCP `explore_repository` is the long path. The direct check is unnecessary if the unit test is accepted; a live one is `read_text_file` with path `/etc/passwd` (already blocked) versus a tool-level READ through a one-turn coding request that asks the explorer to read `/etc/passwd`. Worked: the tool result contains `read blocked` or `glob blocked` and no passwd line. Did not work: file contents from outside the repo.

### F3 — proxmox_node_exec reported SSH failure as success (fixed)

`proxmox_container_exec` maps `ok: false` to `success: false`. `proxmox_node_exec` wrapped the same SSH dict in `_ok`, so `success` stayed true when `PROXMOX_SSH_HOST` was unset or the command timed out. Jarvis `personal_policy` treats only `success is False` or `error` as failure.

Severity: breaks-results. Confidence: high.

Live check: on `:8927`, call `proxmox_node_exec` with a command and a bad `PROXMOX_SSH_HOST` (or stop ssh). Worked: `success` false and `error` set. Did not work: `success` true with `data.ok` false.

### F4 — hint substitution was a counter and a log line (fixed)

Non-streaming (`non_streaming.py` hint mismatch branch) and streaming (`streaming.py` the same branch) increment `portal5_hint_fallback_total` and log. `/v1/trace` did not record hinted versus served. The streaming failover path does record `backend.selected` with `fallback: true` for a later candidate; the first-candidate hint swap did not.

Severity: missing-feature. Confidence: high.

Live check: point a workspace hint at a tag no healthy backend serves, send one chat completion, `GET /v1/trace/{id}`. Worked: a span `model.hint_mismatch` with `hinted` and `served` different. Did not work: a 200 whose trace model differs from the seat hint and no such span.

### F5 — destructive Proxmox on chat seats, confirm gate only in the Jarvis runner

`auto-coding` `tools:` lists all 36 proxmox tools, including `proxmox_delete_vm`, `proxmox_node_exec`, and `proxmox_deploy_ctf_lab`. Twenty-three `auto-coding` personas with no `tools_allow` inherit that list (`bugdiscoverycodeassistant` and `e2edebugger` strip it). `auto-daily::fast` repeats the same 36 plus `git_commit` / `git_push`. `personal_policy.py` confirms mutating proxmox and unifi for the Jarvis runner only. The pipeline chat path dispatches whatever the workspace grants.

Failure: a General · Fast or Portal Coding chat calls `proxmox_delete_vm` or `proxmox_node_exec` and the MCP performs it. No second confirmation in `router/tools.py`.

Severity: stability. Confidence: high on the grant; the live call was not made.

Live check: `GET /v1/models` entry `auto-daily::fast` (and `auto-coding`) `tools` contains `proxmox_delete_vm`. Then a tool-forced completion must not be required to see the grant. Did not work as a safe seat: the tool is absent from the served list. Worked as the current (unsafe) config: the name is present.

### F6 — proxmox_exec_vm and proxmox_deploy_ctf_lab stay successful on failure

`proxmox_exec_vm` (`proxmox_mcp.py` around the poll deadline) returns `_ok` with `status: timeout`. `proxmox_deploy_ctf_lab` returns `_ok` even when SSH steps fail; `containers_up` is true if the lab name appears in any stdout tail.

Severity: breaks-results. Confidence: high. Not changed this lane: the return shape is shared with the power tools' task payload, and deploy's partial success needs a stated rule.

Live check: guest-agent exec with `poll_timeout: 1` against a VM that does not exit. Worked: `success` false. Did not work: `success` true and `data.status` `timeout`.

### F7 — data personas do not tell the model to use the data tools

Seven personas set `workspace_model: auto-research` and `variant: data` (`dataanalyst`, `datascientist`, `databasearchitect`, `machinelearningengineer`, `dataextractor`, `dashboardarchitect`, `statistician`). The variant grants `attach_source`, `run_sql`, `profile_table`, `list_session`, and `require_tool_before_answer`. `dataanalyst`'s prompt says to print SQL/Python for the user. `databasearchitect` asks the user to run `EXPLAIN`. None of the seven name the DuckDB tools.

Severity: missing-feature. Confidence: medium (schemas are still injected, so a model may call them anyway).

Live check: select the Data Analyst persona, ask for the sum of a CSV under the data root, read `/v1/trace`. Worked: a `run_sql` or `attach_source` span whose rows match a hand-computed total. Did not work: an answer that only contains a SQL string and no tool span.

### F8 — UAT coverage does not grade the tool payload

`s5-data-sql` (`tests/qat/uat_behavioral.py`) checks that the answer text contains `133` and `76`. It does not read the tool result. `s5-proxmox-readonly` and `s5-platform-introspection-and-git` use `_grade_markers_case` (words such as "cluster" and "commit"). `profile_table`'s mean and `list_session` are requested and not graded. No QAT case calls `explore_repository`, `write_file`, `proxmox_node_exec`, or `task-router`. `tests/qat/tests/test_config_and_scenarios.py` asserts `task-router` is not a designed scenario.

Severity: missing-feature (harness). Confidence: high.

### F9 — write_file docstring claimed `/tmp`

The implementation's write root is the repo only. The docstring said repo and `/tmp`. Corrected in the confine change. Reads of `/tmp` remain allowed. Severity was a nit.

## Proposed briefs

1. Split lab mutation off `auto-coding` and `auto-daily::fast`. Keep the read-only proxmox bundle from `personal_policy.PROXMOX_READ_TOOLS` on those seats. Put delete, exec, power, and `proxmox_deploy_ctf_lab` behind the Jarvis confirm path only.
2. Make `proxmox_exec_vm` timeout and `proxmox_deploy_ctf_lab` step failure return `success: false`, with the raw payload still attached.
3. Rewrite the seven `variant: data` prompts so the first step is `attach_source` / `run_sql` / `execute_python`, and extend the `s5-data-sql` grader to assert those tool results, not only the prose totals.
