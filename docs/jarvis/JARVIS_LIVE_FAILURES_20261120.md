# Jarvis Local — the 2026-11-19/20 live failures, what they were, what changed

Read from the operator's own queue, not from a fixture: `~/AI_Output/generated/tasks/`
(`personal_tasks.sqlite3` plus each `pt-<id>/attempts/*/receipt.json`), and the dispatcher
registry `~/.claude/orchestrate/registry.json`. No live task was submitted or re-run by this
lane; the one live receipt that was replayed was replayed against a **copy** of the queue.

## What the six live tasks actually did

| Task | Request | What the receipts show |
|---|---|---|
| `pt-64e4e4751602` | Portal pipeline status / loaded models | local-1 `acceptance: plan step 0 not satisfied: workspace_files` after calling `recall`+`queue_status`; local-2 seven `kb_search` calls, `unknown kb_id 'portal_pipeline_status'`; then `handed-to-cloud` with `final_text: "Dispatched to the personal cloud lane."` while the lane's own `## RESULT` (a full, correct answer) sat in the same receipt. |
| `pt-b98b0f89a626` | Proxmox stopped VMs | `pending` — a confirm row for a read-only ask; local-1 died on `RemoteProtocolError` (Pipeline mid-rebuild). |
| `pt-56d4acbfe892` | One-page Word doc of the sweep | local-1 `unknown kb_id 'security_sweeps'`; retry planned only `workspace_files`, so the model answered "the plan does not include any steps for creating a Word document" and **passed acceptance** (`done`) with no document. |
| `pt-351e3eeac094` | "clean things up" | planned `workspace_files`, listed 200 files, asked "Would you like me to proceed" — `done`. |
| `pt-f77f9d0555f0` | code review of `scripts/engine_install_plan.py` | planned `workspace_files`, reported honestly that the file is not in `/workspace` — `done`. |
| (intake) | `docker compose down -v` | no row at all. Intake had no refusal path: the message never reached a task, and the operator was told nothing. |

## The five defects and what changed

1. **The cloud result never came back** (`_cloud_result` success branch). The lane's answer was
   thrown away and the row parked at `handed-to-cloud`. Now the lane's own `## RESULT` block is
   the task's `final_text` (`done` when the block says done, otherwise `blocked` with the block),
   it is sent to Telegram, and the row reaches a terminal state.
2. **The cloud lane held the whole runner** for 857 s (`ProcessDispatcher.run` blocks).
   `ProcessDispatcher` gained `start`/`outcome`/`alive`/`result`: the runner launches the lane
   detached, writes `cloud-running` with the role and its run-count, and every poll collects
   finished lanes through the dispatcher's own registry and `dispatch.py result`. Local tasks
   behind a lane now run in the same poll.
3. **Wrong tools.** `auto-daily::fast` had no pipeline status tool, so the planner invented a
   `kb_id`. It now carries `get_pipeline_status` and `get_loaded_models` (the Pipeline's own
   tools, discovered from the `pipeline` MCP at :8928), the planner prompt names them, and a
   Pipeline tool that is handed back to the runner is a retryable fault, not a deny.
4. **Wrong escalation kind.** Every personal escalation went `--kind code`. A personal task now
   carries its kind: `security` on the existing classifier, else `review`, `research` (a
   question) or `code`.
5. **Intake refusals were silent.** `refusal_reason` is checked before a row is written
   (`docker compose down`, docker prune, `rm -rf`, `launch.sh down`, a force push) and the reply
   is the reason; a row that still reaches the runner is denied before any tool call with the
   same reason. A question *about* such a command is not refused.

Also: `/jarvis do` now replies with the task's queue position, a read-only `proxmox_*` tool no
longer asks for a confirm while every mutating one still does, and an ambiguous request may be
answered with one question (`{"action": "ask"}`) instead of a guessed action.

## The `<ifm…` planner tail — root cause (already fixed on main before this lane)

`pt-762f21e03768` failed at 11:52 CST with

```
planner response must be a JSON object; planner tail: I'll store this memory for you.
<ifm|tool_calls> <ifm|tool_call>remember …
```

Root cause: the planner seat is K2-Horizon-MoVA (IFM lineage), which writes tool calls as
`<ifm|tool_call>` text whenever its chat template is in tool mode; the planner turn is toolless
(`portal_no_tools`) so nothing parsed them, and at that hour the request carried no JSON decoding
constraint. Commit `45dc9499a` (14:37 CST the same day) added `response_format: json_object`,
`portal_no_tools`, and one corrective retry; `0ef51a03e` salvages the IFM format in the tool
loop. The exact captured tail is now a regression test
(`tests/unit/test_jarvis_r6_planner_retry.py::test_the_named_live_planner_tail_is_retried_then_reported`).

## Evidence the replay works (offline, on a copy)

Replaying the live queue copy through `reconcile_cloud_lanes`:

```
in flight: [('pt-64e4e4751602', 'handed-to-cloud')]
collected: PersonalRun(task_id='pt-64e4e4751602', status='done')
notice pt-64e4e4751602 -> ## RESULT | done — the request is answered from live read-only observation …
```

The row, the receipt (`final_text` = the block) and the Telegram notice all carry the answer the
operator never got.

## Not fixed here (out of this lane's scope, and live only)

- **browser/proxmox MCP URLs from inside the Pipeline.** The cloud lane that answered
  `pt-64e4e4751602` found `deploy/portal-5/docker-compose.yml` sets `MCP_*_URL` for every fleet
  MCP except browser (:8923) and proxmox (:8927), so the container probes `localhost` and reports
  both down; their tools are undiscoverable from the Pipeline. Proxmox scenarios 2–4 depend on
  that fix. It is a compose + rebuild change, not a Jarvis change.
- **No local file-content read outside the tasks dir.** `workspace_files` lists names and sizes
  only, so "tonight's sweep numbers" has no local source; the Word-document scenario can only
  produce the numbers if some exposed tool returns them, otherwise it escalates.
