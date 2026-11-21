# FINDING — Jarvis rebuild S5: escalate to a stronger Portal seat (2026-11-20)

Implements the operator's re-scope of `docs/jarvis/JARVIS_DESIGN_REVIEW_AND_PLAN.md` §4 S5:
when a Jarvis personal task fails the S4 structural acceptance gate, it escalates to a
stronger **Portal workspace over the Pipeline (:9099)**, not to the cloud. No live-stack
action was taken from this lane (worker contract §0); the orchestrator runs the live
Telegram proof.

## What changed

- `config/portal.yaml` — `orchestration_arm.queue.escalation_ladder: [auto-reasoning,
  auto-coding]`, next to `personal_cloud`. `personal_cloud.enabled` stays `false`.
  `config/orchestration_arm.yaml` was regenerated from it with
  `uv run python -m portal.platform.inference.cli sync-config` (no other generated file
  changed).
- `personal_runner.py` — after the second failed local attempt, `_escalate_up` retries the
  same request (same tool bundle) one rung at a time over the existing `PipelineCaller`.
  Each hop is an ordinary OpenAI-compatible Pipeline call: no `dispatch.py`, no repo
  worktree, no branch. The ladder length is the attempt bound.
  - `attempts/escalation-<n>/receipt.json` records that hop's seat, hops, tool calls, the
    reason it was tried (`reason`, i.e. the previous seat's failure) and its own `error`.
  - The task receipt carries `escalations: [{attempt, from, to, reason, status}]` on
    success and on block; a blocked task's `error` reads
    `escalation ladder exhausted (auto-reasoning, auto-coding): <last reason>`.
  - A non-retryable hop fault (denial) ends the task `rejected`, as the local path does;
    `ToolsUnavailableError` is terminal and never retried on another rung.
  - Cloud is now the *last* resort: tried only when the ladder has no untried rung **and**
    `personal_cloud.enabled` is true. The cloud path is untouched and still off.
- Docs: the §4 S5 slice and D1 in the design plan now describe the re-scope; the runbook's
  "after two failed local attempts" paragraph names the ladder and keeps the cloud
  mechanics that still apply.

## Ladder choice (from `config/portal.yaml` workspaces, no hardcoded model names)

1. `auto-reasoning` — the dedicated reasoning workspace (`🧠 Portal Deep Reasoner`,
   K2-Horizon-MoVA-36B-A4B, `think: true`; seated 2026-10-19 on the I-REASON screen 12/12
   vs DeepSeek-R1-8B 8/12). First rung because the failure class S4 gates is usually an
   incomplete or ungrounded *answer*, not a missing action; the strongest analysis seat is
   the right first retry.
2. `auto-coding` — the strongest local **agentic** seat: Qwen3.8-27B dense, 96K window,
   72 declared tools (`execute_python`/`bash`/`node`, browser, proxmox, git, documents),
   seated 2026-11-01 on `realuse_s5s7s10_20261030b` 15/16 vs Qwen3-Coder 5/16. Second rung
   so an action-shaped request that the reasoning seat cannot ground still reaches the
   widest tool surface.

Both are production workspaces (`config/portal.yaml` `workspaces:`), served by the Pipeline
and resolvable through the same `model:` field the routed seat already uses. The rung list
is read from config only; the runner never names a model.

**Tool-coverage caveat (config fact, not code):** the Pipeline intersects a request's
`portal_bite_tools` with the serving workspace's declared `tools`
(`router/eval_gate.py:apply_bite_tool_scope`). `auto-reasoning` declares `tools: []`, so on
rung 1 the request gets the client-local personal tools (`read_local_file`,
`workspace_files`, `wiki_search`, `queue_status`, …) but no Pipeline MCP tool
(`get_pipeline_status`, `read_text_file`, …). `auto-coding` declares 72 tools but not
`get_pipeline_status`/`get_loaded_models`. A status-style ask that can only be grounded on
those MCP tools will therefore fail both rungs and block honestly. Reported in OPEN, not
worked around: widening the workspaces' tool lists is an operator/config decision.

## Acceptance property ↔ proof (offline)

| Property | Test |
|---|---|
| a failed local attempt escalates to the next configured workspace, over the Pipeline, with the hop's reason recorded and no worktree/dispatch call | `test_jarvis_personal_loop.py::test_a_failed_local_attempt_escalates_to_the_next_portal_workspace` |
| the ladder is the bound, every hop's reason is kept, and exhaustion blocks | `test_jarvis_personal_loop.py::test_the_escalation_ladder_is_bounded_and_records_every_reason` |

Existing cloud-path tests were pointed at an empty ladder (`monkeypatch` on
`_escalation_ladder`) so they still prove the preserved cloud mechanism; no assertion about
cloud behaviour changed. Nothing was deleted.

Net test lines: **+97** (97 added, 0 removed: 88 in `test_jarvis_personal_loop.py` for the
two S5 tests, 9 lines of empty-ladder setup across the three cloud test files).

## Orchestrator's live proof (Telegram)

Force a structural gate failure on the routed seat, then read the escalated hop:

1. `/jarvis do read ~/AI_Output/generated/<some-real-file> and summarise what it says in one paragraph`
   (or any ask where attempt 1/2 answers with zero tool calls → `acceptance: data request
   answered without a tool call`). PASS:
   - a notice `<pt-id>: acceptance: …; escalating to auto-reasoning.`
   - the answer arrives from `auto-reasoning`
   - `~/AI_Output/generated/tasks/<pt-id>/receipt.json` has `"workspace": "auto-reasoning"`,
     `status: done`, and `escalations[0]` = `{from: "auto-daily::fast", to:
     "auto-reasoning", reason: "acceptance: …", status: "done"}`
   - `~/AI_Output/generated/tasks/<pt-id>/attempts/local-1` and `local-2` exist; no
     `cloud-*` directory
   - `git -C <repo> branch --list 'lane/jarvis-personal-*'` gains 0 entries
   - FAIL: no escalation notice, `workspace` still `auto-daily::fast`, a `cloud-*` dir, or
     a new `lane/jarvis-personal-*` branch.
2. `/jarvis do what is the Portal pipeline status and which models are loaded right now`
   — must still be `done` on attempt 1 (no escalation) if the routed seat answers it;
   if it fails, it is expected to block after the ladder (see tool-coverage caveat).
3. `/jarvis do docker compose down -v` — unchanged: refused at intake, no row.

## UNPROVEN / OPEN

- Nothing here has been run against the live Pipeline: the escalated `model:` workspace
  resolution, the per-rung tool pool and the Telegram notices are unverified live.
- `auto-reasoning`'s empty `tools:` list means rung 1 has no Pipeline MCP tools (above);
  `auto-coding` lacks `get_pipeline_status`/`get_loaded_models`. A status-shaped failure
  will exhaust the ladder and block. If the operator wants escalation to cover those tools,
  the workspace tool lists must be widened first.
- Escalation triggers on any *retryable* local failure, not acceptance alone (acceptance is
  the common class); a hop's reason is always recorded.
- `uv run mypy portal/` is not clean in this worktree: 650 errors, 649 of them in
  `scripts/`/`tests/` files pulled in by imports and one pre-existing
  `portal_channels/telegram/arm_bridge.py:86` (`no-any-return`, untouched by this lane).
  `uv run mypy portal/modules/orchestration/personal_runner.py` reports only that
  pre-existing arm_bridge import error.
