# Portal orchestration arm

## Scope

The Phase 1 arm runs hand-written bite plans through the Pipeline's OpenAI-compatible chat endpoint. Each attempt starts with fresh messages and selects the existing `auto-daily::fast` or `auto-daily::deep` seat. MCP tool calls stay inside the Pipeline tool loop; the arm passes `portal_bite_tools` so that each request can expose only the current bite's tools. The local `finish` client tool ends the bite and writes its checked output.

The scheduler, SQLite ledger, planner, reviewer, and deterministic checker live in `portal/modules/orchestration/`. This is a separate module package because `portal/platform/agent/` is platform core and owns Security's `run_loop`; the arm does not import or wrap that goal loop. The module is registered as `orchestration` and is disabled by default. `portal arm goal` asks the Deep seat for a plan, validates it before creating task state, and then runs the bite contracts through the existing arm service. Open WebUI enqueues a stored plan template through `portal/modules/orchestration/owui_entry.py`, which calls `QueueLedger.enqueue` (the same path as `portal arm enqueue-template`). The pipeline MCP tool is `arm_queue_task`, resolved through the platform's module plugin seam, so platform code never imports the module.

## Worker and checks

The worker sends one streaming Pipeline request for each bite attempt. It records the request and SSE events as JSONL, keeps reasoning enabled, applies the attempt's time and output-token budgets, and requires one `finish` call. A malformed finish argument gets one repair request when the bite budget allows it. Pipeline-dispatched tool errors remain structured tool results in the Pipeline loop. A finish call that is missing, refused, malformed, over budget, or outside the allowed tool set is discarded.

After a valid finish, the arm checks the output schema and runs the bite's deterministic acceptance checks. The SQLite transition history records build SHA, model tag and digest, elapsed time, and details. Resume returns unfinished bites to `ready` and refuses changed build or model identities unless the caller explicitly supplies `--override`.

## Scheduling and recovery

`config/orchestration_arm.yaml` carries the operator-owned residency mode (default `swap`) and model identities used by `POST /admin/load-plan`, plus policy rendered from `config/portal.yaml`. The scheduler runs one bite at a time. Before a request, it asks the Pipeline load guard whether that seat fits; actual model loads happen through the Pipeline transport, whose load guard serializes cold loads. In swap mode, ready Fast bites run first unless a Deep bite unlocks more downstream work than the current Fast queue.

Stored plan templates live under each discipline's `plan_templates` in `config/portal.yaml`. Instantiation substitutes declared string parameters, assigns the task ID, and runs the Phase 2 plan validator before the plan enters the queue. The durable queue lives in `queue.sqlite3` under the task root; each task still uses its own append-only `ledger.db` and `receipt.json`.

The overnight queue runs one task at a time. Before each bite it yields to a live PID in the memory-safety WFE file, a live PID in any file under `queue.yield_lock_dir`, or a Pipeline `/admin/load-plan` result reporting active traffic or no fit. Every model request continues through the Pipeline load guard. Queue status remains waiting until the gate clears, then resume uses the task ledger.

The failure ladder retries Fast twice after its initial attempt, tries one Deep attempt, then marks the bite `blocked` and calls a notice interface. The default notice sink is an in-process stub. Independent branches continue after a bite blocks.

## Phase 2 planning and review

The planner prompt and plan validator enforce check-or-review coverage, the configured comfortable Fast context budget, separate read/action bites, and an assembly bite followed by final review. Discipline tool allowlists and read/action tool classes are rendered from `config/portal.yaml` by `sync-config`. The first non-security discipline is `test_fixing`: existing coding WFE repair tasks already use hidden pytest tests as hard graders, so they can measure correctness without relying on model review. Its bite suite uses that same grader shape, with pass criteria fixed in the source config before any model run. The second candidate is `detection-engineering`, the design's starting candidate because lab-run SPL queries can be checked against hard known-answer rows. Its bite, planner, and checker suites plus pass criteria are present, while its model bindings and calibration rates remain unset until live Fast and Deep bite-suite rates satisfy those criteria. The orchestration module remains disabled in `config/portal.yaml` during this offline phase.

High-risk criteria, Deep vote count, and approval quorum are configuration values. High-risk bites receive Deep votes after deterministic checks; a configured majority is required. High-risk writes pause at a Telegram gate. The arm writes gate requests to the AI_Output SQLite outbox; the existing `portal_channels.telegram.bot` sends the buttons and records an authorized approve or deny callback. A pending request leaves the bite ready and the receipt `WAITING`. Block notices use the same outbox.

Gate C calibration uses discipline/seat WFE pass probabilities and mean seconds to project remaining task odds and cost after the configured number of completed bites. `minimum_pass_probability` is intentionally `null` until Phase 0 rates exist; unattended CLI runs reject that configuration. When a populated threshold is crossed, the receipt is `PAUSED_FOR_REPLAN` and no further bite runs.

Task artifacts use `get_generated_dir("tasks")`, which defaults to `~/AI_Output/generated/tasks/`: each task contains `ledger.db`, normalized `plan.json`, resolved `inputs.json`, per-attempt transcripts and checks, output files, and `receipt.json`. The receipt follows the WFE rig shape: `head`, `utc`, `results`, and `workdir`-style task evidence.

## Principle checks

`scripts/validation/orchestration_arm.py` carries the arm's mechanically checkable principles into `validate_system.py`:

- `arm_reading_no_write` — a configured discipline's read and action tool classes are disjoint and complete, and the plan validator rejects a bite that mixes them or reads untrusted content while holding an action tool.
- `arm_thinking_on` — no arm config or request body suppresses reasoning, and the Pipeline keeps thinking on for a request carrying `portal_bite_tools` even when the seat's workspace card says `think: false`. Production seats without bite tools are out of scope.
- `arm_discipline_suites` — every configured discipline declares non-empty bite, planner and checker suites plus written pass criteria.
- `arm_gate_c_threshold` — `calibration.minimum_pass_probability` is null or a probability in [0, 1], and a null value refuses unattended runs while interactive runs stay available.
- `arm_least_agency` — a request mounts exactly the bite's tools and turn budget, and the planner rejects a tool outside the discipline allowlist.
- `arm_pull_notes` — bite inputs reach the worker as paths, never pre-packed contents, and the procedure rides in the system prompt.

## Offline verification boundary

`tests/wfe/e2e/rig_orchestration_arm.py` runs the arm against a fake OpenAI-compatible Pipeline API on an ephemeral local port. It covers a happy path, red-flag retry, budget exhaustion, wandering, Pipeline failure, SIGTERM resume, identity mismatch refusal, a blocked bite alongside an independent pass, four planner rejections, a split Deep vote, a Telegram deny before dispatch, and the unseated detection template's no-rate refusal plus offline pass. `tests/unit/test_orchestration_arm.py` also instantiates the detection-engineering template, validates its read/action split, and executes the plan through that fake API. `tests/unit/test_orchestration_phase2.py` checks the planner/checker WFE fixtures, calibration projection, and the fake Telegram outbox round trip. These tests prove the offline arm only; no live model or stack is started by this phase.
