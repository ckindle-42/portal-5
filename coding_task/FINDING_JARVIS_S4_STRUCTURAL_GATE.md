# FINDING — Jarvis rebuild S4: structural acceptance gate (2026-11-20)

Implements `docs/jarvis/JARVIS_DESIGN_REVIEW_AND_PLAN.md` §4 Slice S4. No live-stack action
was taken from this lane (worker contract §0): the code and the offline gates are here; the
orchestrator runs the live Telegram proof.

## What changed

`acceptance_failure()` (`portal/modules/orchestration/personal_policy.py`) now decides a
finished local attempt on structure alone, in this order:

1. **non-empty answer** → `acceptance: empty final answer` (unchanged).
2. **unrecovered tool error** → `acceptance: tool error: …`. An error is fatal only when no
   later tool result arrived; an error the model recovered from by calling another tool no
   longer fails a run that otherwise answered.
3. **`hops >= 1` for any routed data/action request** → `acceptance: data request answered
   without a tool call`. `_execute_route` passes `hops` and `requires_tools=bool(route.tools)`,
   so a 0-hop hallucinated answer can no longer be recorded `done`. The `ask` route never
   reaches this gate (it returns a question with 0 hops by design).
4. **document creation delivered** → if any of `create_word_document`, `create_excel`,
   `create_powerpoint` was called, its own output must name a file (`path`, `filename`,
   `download_url`, `url`) and not be an error / `success: false` → else
   `acceptance: document tool returned no path`.

Removed: `_WORD_DOC_REQUEST`, `_REPO_FILE` (`_repo_file_missing`, `_repo_file_read`),
`_LARGEST_REQUEST` (`_omitted_largest_size`, `_file_rows`) and the now-unused `request=`
parameter. `_unsatisfied_step` was already gone from this tree.

Kept: `_FABRICATED_ANSWER` (placeholder/refusal phrases such as `[Insert MAL Count]`,
"cannot fulfill"). It is not task-specific and was not in the slice's removal list; the slice
spec says "structural checks only", so a reviewer may want it removed — see OPEN.

## Acceptance property ↔ proof (offline)

| Property | Test |
|---|---|
| unrecovered tool error rejected, recovered error passes | `test_jarvis_personal_loop.py::test_acceptance_rejects_only_an_unrecovered_tool_error` |
| 0-hop answer to a data request rejected (wired through `_execute_route`) | `test_jarvis_personal_loop.py::test_acceptance_rejects_a_zero_hop_answer_to_a_data_request` |
| created document must report its own path; placeholder answer rejected | `test_jarvis_personal_loop.py::test_acceptance_requires_a_created_document_to_report_its_path` |
| arbitrary new task classes (Excel, PDF, UniFi) pass with no new regex | `test_jarvis_personal_loop.py::test_arbitrary_task_classes_pass_the_structural_gate` |
| empty answer still retryable (pre-existing) | `test_jarvis_personal_loop.py::test_empty_answer_is_a_retryable_failure_that_reaches_cloud_handoff` |

Superseded tests deleted: the five `_REPO_FILE`/`_WORD_DOC_REQUEST` tests in
`test_jarvis_live_fails_r2.py`, `test_an_answer_that_omits_the_largest_size_is_not_done`
(`test_jarvis_r5_recall_workspace.py`), the combined `test_acceptance_check_flags_the_three_real_failures`
and the now-duplicate `test_a_dispatched_tool_error_is_a_retryable_failure`
(`test_jarvis_personal_loop.py`). The reminder-queue test in `test_jarvis_personal_intake.py`
carried a stale planner-shaped first reply; it now returns a routed tool call then the answer.

Net test lines: **-123** (42 added, 165 removed).

## Orchestrator's live proof (Telegram)

1. `/jarvis do what is the Portal pipeline status and which models are loaded right now`
   - PASS: `status: done`, `hops >= 1`, `tool_calls` contains `get_pipeline_status` and/or
     `get_loaded_models`, counts match live `GET :9099/health` and `GET :11434/api/ps`.
   - FAIL: `status: blocked`/`retrying`, `hops: 0`, or a hop count that does not match the
     live endpoints.
2. `/jarvis do docker compose down -v`
   - PASS: refused at intake with the refusal reason; no row in `personal_tasks.sqlite3`;
     `docker inspect` start times unchanged. (Unchanged by S4 — proves the gate did not widen.)
3. Regression check for the removed regexes: `/jarvis do write a one-page Word document …`
   and `/jarvis do list the three largest files in /workspace/generated …` must still reach
   `done` on attempt 1 — property 4 now covers the first structurally; the second is no
   longer checked for size content, only that it was grounded in a tool call.
