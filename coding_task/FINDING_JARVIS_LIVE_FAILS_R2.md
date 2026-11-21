# FINDING — Jarvis personal lane, live round 2 (2026-11-20)

Five live Telegram tasks on the arm runner at `69f9bf0ad` (includes the merged
`lane/jarvis-wrong-answers`, `2129309ea`). Receipts read from
`~/AI_Output/generated/tasks/<id>/`; notices from `~/AI_Output/.portal_arm/telegram.sqlite3`.
This file records the root cause of each failure, the fix, and what the operator must do
to make it land live. No live-stack action was taken from this lane (worker contract §0).

> **Superseded in part (slice S4):** the task-specific regexes this finding added —
> `_REPO_FILE`/`_repo_file_read`, `_WORD_DOC_REQUEST`, `_LARGEST_REQUEST` — were removed in
> favour of a structural acceptance gate. See
> `coding_task/FINDING_JARVIS_S4_STRUCTURAL_GATE.md`. The repo-read tools added here remain.

## 1. `pt-46b3e7c492af` — a repo path answered "does not exist in the workspace", accepted as done

**Root cause (two defects).**

1. The personal lane has no read path to the repository. Its only file tool is
   `workspace_files`, which lists `~/AI_Output` (`get_workspace_root()`), so the planner
   planned a workspace listing for a repo path.
2. The guard added in `ac86f160e` (`_repo_file_missing`) grounds a repo path by searching
   the *joined tool-output blob* for the path string. `_workspace_files` echoes the
   requested path back in its own result envelope — the receipt's call was
   `workspace_files {"path": "scripts/engine_install_plan.py"}`, whose result carries
   `"path": "scripts/engine_install_plan.py"` with `"count": 0`. The guard therefore found
   the path in the tool result that *proved the file missing*, and `done` was recorded.
   Nothing in the offline test caught it because that test's tool output has no `path` key.

**Fix.** Add the host-native Pipeline MCP repo readers (`read_text_file`, `search_files`,
`list_directory`) to the personal read allowlist and to the `auto-daily::fast` tool list —
a bite-only tool is dropped by `apply_bite_tool_scope` unless the serving workspace lists
it. The planner prompt now routes `scripts/…`, `portal/…`, `tests/…`, `config/…`,
`docs/…` to those readers and says `workspace_files` cannot see the repo. The guard now
requires a *read*: a tool result with non-empty `content` whose `path` ends with the
requested path, or a `search_files` hit line starting with it. A listing that echoes the
path no longer grounds anything.

Offline proof of the old and new verdicts on the identical tool output
(`run_read_tool("workspace_files", {"path": "scripts/engine_install_plan.py"}, root)`):

```
tool output: {"count": 0, "files": [], "path": "scripts/engine_install_plan.py", "root": "/Users/chris/AI_Output", ...}
old guard sees the path in the blob: True   → old verdict: done
new verdict: acceptance: repository file not in tool results: scripts/engine_install_plan.py
```

**Tests.** `test_a_workspace_listing_that_echoes_the_path_does_not_ground_it`,
`test_a_repository_read_grounds_the_answer`, `test_a_failed_repository_read_is_not_grounding`,
`test_a_search_hit_grounds_the_file_it_names`,
`test_the_live_code_review_task_is_no_longer_accepted_as_done` (replays the receipt),
`test_the_personal_lane_can_read_the_repository`,
`test_the_fast_workspace_serves_the_repository_read_tools`.

## 2. `pt-7447e778ecd5` — Telegram got the cloud lane's worker report

**Root cause.** `_deliver_cloud_result` took the lane's whole `## RESULT` block — verdict,
`## WHAT CHANGED`, `## EVIDENCE` (with `uv run pytest`), `## ORCHESTRATOR RUNS`,
`## UNPROVEN`, `## OPEN / RISK` — and used it verbatim as the task's answer and as the
Telegram notice. `_cloud_brief` said nothing about who reads the reply, so the lane followed
`WORKER_CONTRACT.md` and ran the repo gates for a document task.

**Fix.** `user_answer()` keeps only the answer-bearing sections (`ANSWER`, `RESULT`,
`SUMMARY`, `DELIVERABLE`, `WHAT CHANGED`), strips the leading verdict word, and drops every
other block; a scaffold-only report delivers an honest "no user-facing answer" line instead.
`_cloud_brief` now states that the operator reads the reply in Telegram, that the answer
(plus file path or download link) belongs under `## ANSWER`, and that a personal task runs
no repository gates and touches no repo files. The cap-reached branch (a lane that exits
non-zero after writing a report) uses the same extraction, so the failure notice does not
paste the report either.

On the live receipt the operator would now receive exactly:

```
- Created `/Users/chris/AI_Output/generated/security_sweep_summary.docx` — one-page Word document summarizing the 2026-11-19 security sweep
```

**Tests.** `test_the_operator_gets_the_answer_and_the_file_path_only` (the live report text),
`test_an_answer_section_is_preferred_when_the_lane_writes_one`,
`test_a_lane_that_writes_no_scaffolding_still_reaches_the_operator`,
`test_a_personal_cloud_brief_forbids_the_repository_gates`,
`test_a_blocked_cloud_lane_does_not_paste_its_report_at_the_cap`.

## 3. `pt-b540a922c5c3` — no `proxmox_list_vms` call, handed to the cloud lane

**Root cause.** The plan was right (`proxmox_list_vms`) and needed no confirm; the tool was
never reachable. `get_pipeline_mcp_servers` falls back to `http://localhost:<port>` for every
`expose_to_pipeline` fleet member without an `MCP_<ID>_URL` override, and
`deploy/portal-5/docker-compose.yml` omitted `MCP_PROXMOX_URL` and `MCP_BROWSER_URL`. Inside
the pipeline container `localhost` is the container, so discovery failed, the model was
offered no proxmox (or browser) schema at all, and `hops: 0` was recorded. The receipt's
`tool_calls: ["recall"]` is **not** a model call: `recall` is the runner's own memory
preamble recorded by `_CheckIn`, so the local model called nothing.

**Fix.** `MCP_PROXMOX_URL=http://portal5-mcp-proxmox:8927` and
`MCP_BROWSER_URL=http://browser-mcp:8923` in the pipeline service's environment (compose
service DNS, the same pattern as `MCP_DOCUMENTS_URL` / `BROWSER_MCP_URL`).

**Tests.** `test_every_pipeline_exposed_mcp_has_a_pipeline_url` (fails for any future
fleet member without a pipeline URL), `test_proxmox_and_browser_urls_point_at_their_compose_services`,
`test_the_personal_lane_reads_proxmox_without_a_confirm`,
`test_the_vm_request_fails_loudly_when_no_proxmox_tool_ran` (the receipt's hops-0 shape).

## 4. `pt-7447e778ecd5` — the local model never called `create_word_document`

**Root cause.** The tool *is* exposed: `create_word_document` is in `auto-daily::fast`'s
`tools` and in `_personal_available_tools()`, so `validate_personal_plan` accepts it. The
counts are not reachable: nothing in the personal allowlist can read the sweep report
(`~/.portal5/security/security_sweep_YYYYMMDD.md`), and `read_text_file` is confined to the
repo and `/tmp`. So the plan could not be grounded, the planner planned a workspace search,
and the plan never named the create tool. `_execute_plan` trusts the planner's tool list and
the executor is told to use only those tools, so `create_word_document` was never offered.
Acceptance then correctly refused the answer (`acceptance: word document was not created`)
— which is why the task fell to the cloud lane.

**Fix.** New read-only local tool `security_sweep`: the newest report's summary bullets
(MAL, CRITICAL, findings), the delta line (new/carried/resolved), the CRITICAL table rows,
the report path and its date. The planner prompt names it. `plan_gap()` adds a planner
post-condition: a Word-document request whose plan names neither `create_word_document` nor
`read_word_document` is rejected and gets the existing one corrective retry, so the create
step cannot silently disappear.

**Tests.** `test_the_personal_path_exposes_the_word_document_tool`,
`test_the_sweep_read_returns_the_counts_the_document_needs`,
`test_the_sweep_read_is_a_read_tool_and_errors_without_a_report`,
`test_a_document_plan_without_the_create_tool_is_replanned_once`,
`test_a_document_read_plan_is_not_forced_to_create_one`,
`test_a_corrected_document_plan_reaches_done_with_the_real_counts`.

## 5. Stale memory ("line_count: Unable to locate /workspace/report.txt…")

**Root cause.** `_memory_text` filtered only on vector similarity (≥ 0.65), and the
operator's store still carries tool-scratch rows written before the R5 placeholder gate:
`row count is <output of previous execution>` (angle form without an underscore, so
`unfilled_placeholder` never matched it) and `line_count: Unable to locate
/workspace/report.txt; line count could not be determined.` The receipt shows both injected
into the plan's `_memory_context`, and the plan then searched the workspace — the scratch
steered the planner.

**Fix.** A memory that records a failed lookup or an unresolved template is tool scratch,
not a preference: `_memory_text` drops "unable to locate", "could not be determined" and
"output of previous execution" before injection. Real preferences still pass. On the
receipt's own two lines the rendered memory is now empty:

```
- row count is <output of previous execution>
- line_count: Unable to locate /workspace/report.txt; line count could not be determined.
→ kept after the veto: ''
```

**Tests.** `test_recalled_tool_scratch_is_dropped_and_a_preference_is_kept` (the two exact
strings), `test_the_planner_never_sees_the_scratch_it_used_to`.

## What the live stack needs

- `config/portal.yaml` changed (`auto-daily::fast` tools) — it is baked into the pipeline
  image: `./launch.sh rebuild && ./launch.sh up`.
- `deploy/portal-5/docker-compose.yml` changed (two `MCP_*_URL` env values) — the pipeline
  container must be recreated: `./launch.sh up`.
- The arm queue runner reads repo code and `config/portal.yaml` from the checkout; it
  restarts itself on a code change ("runner code changed … restarting" in
  `~/AI_Output/generated/tasks/arm-queue.launchd.log`).
- No MCP restart: `portal5-mcp-proxmox` and `browser-mcp` are already running containers.

## Re-test in Telegram (pass criteria)

1. `/jarvis do review scripts/engine_install_plan.py and report every code path that can downgrade a package, with line numbers`
   — PASS: `receipt.json` `status: done`, `tool_calls` contains `read_text_file` (or
   `search_files`), and the answer cites real line numbers from the file. A "does not exist
   in the workspace" answer must appear only as `status: retrying` with
   `acceptance: repository file not in tool results: scripts/engine_install_plan.py`.
2. `/jarvis do write a one-page Word document summarising tonight's security sweep: MAL count, critical count, and what is still open`
   — PASS: `status: done`, `tool_calls` contains `security_sweep` **and**
   `create_word_document`, the delivered Telegram text is a sentence or two plus the
   `.docx` path, and it contains none of `## RESULT`, `## EVIDENCE`, `ORCHESTRATOR RUNS`,
   `uv run pytest`.
3. `/jarvis do list the Proxmox VMs that are currently stopped`
   — PASS: `status: done`, `hops >= 1`, `tool_calls` contains `proxmox_list_vms`, and the
   reply lists the stopped VMs with vmids. The old failure shape is `hops: 0` with only
   `recall` in `tool_calls`.

Memory (check within test 1): the receipt's `plan._memory_context` must contain neither
"Unable to locate /workspace/report.txt" nor "output of previous execution".

## Known gaps left in place

- Junk rows remain in the live memory store. `scripts/cleanup_junk_memories.py --apply`
  matches only placeholder forms; the row `row count is <output of previous execution>` is
  now dropped at recall, and could also be removed by the operator.
- A failed local attempt's receipt still records `plan: null` (`_record_local_failure` reads
  `task.plan_json`, which is only persisted on confirm), so the plan that failed is lost.
