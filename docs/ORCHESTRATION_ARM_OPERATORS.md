# Orchestration arm operator guide

The `orchestration` module is enabled in the repo; it runs once the Pipeline and its seated models are available. To turn it off or back on:

```bash
uv run portal module enable orchestration --yes
```

Set the Pipeline endpoint and the measured model digests in the shell that runs `portal arm`. The model IDs stay fixed to the existing Fast and Deep seats; load-plan IDs are read from `config/orchestration_arm.yaml`.
Set `PORTAL_ARM_APPROVAL_TTL_SECONDS` in this shell and `.env` to the same value to configure approval expiry; the default is 1800 seconds.

The worker supplies each bite's declared tool schemas plus `finish`. `file_read`, `file_write`, and `pytest_run` run in the task directory; `pytest_run` is time-limited and runs only when the host network and writes outside the task directory can be sandboxed. External input files are copied under each task's `inputs/` directory before the worker sees their relative paths.

```bash
export PORTAL_ARM_PIPELINE_URL=http://127.0.0.1:9099
export PIPELINE_API_KEY='<pipeline api key>'
export PORTAL_ARM_FAST_DIGEST='<fast model content digest>'
export PORTAL_ARM_DEEP_DIGEST='<deep model content digest>'
export PORTAL_ARM_APPROVAL_TTL_SECONDS=1800
```

Submit a YAML or JSON hand-written plan. The task directory defaults to `get_generated_dir("tasks")` (`~/AI_Output/generated/tasks/` with the default workspace root). `--tasks-dir` changes it, and `--source-dir` sets the base for relative input paths.

```bash
uv run portal arm submit plan.yaml
uv run portal arm status <task-id>
uv run portal arm resume <task-id>
uv run portal arm resume <task-id> --override
```

`detection-engineering` is an unseated candidate. Its hard-check bite suite, planner suite, checker controls, and stored authoring template are ready for offline validation, but it has no model binding or calibration rates. The module is enabled, but unattended runs for this discipline stay unavailable until live Fast and Deep suite rates meet its fixed pass criteria.

A resume without `--override` refuses a changed build SHA or model digest. Review the task artifacts before explicitly adopting a changed identity. `receipt.json` reports `PASS` only when every bite passes; exhausted bites are `BLOCKED`. The scheduler reads its residency mode and the load-guard model identities from `config/orchestration_arm.yaml`.

Queue a hand-written plan or instantiate a configured template. Template parameters use repeated `--param name=value` options and are checked by the same Phase 2 plan validator as planner output:

```bash
uv run portal arm enqueue plan.yaml
uv run portal arm enqueue-template <task-id> test_fixing repair_with_tests \
  --param source_file=/path/to/module.py \
  --param test_file=/path/to/test_module.py \
  --param 'expected_behavior=value returns 2'
uv run portal arm queue-status
uv run portal arm queue-run            # keeps polling when the queue is empty
uv run portal arm queue-run --drain    # exits once the queue is empty
```

The queue waits while a WFE run has a live PID in `/tmp/portal5-memory-safety-test-pids`, while a configured yield lock has a live PID, or while the Pipeline load plan reports busy/no fit. Bench and UAT runners can opt into the same convention by writing their PID as the only line in a file under `~/.portal5/locks/` and removing the file on exit. Set `queue.yield_lock_dir` in `config/portal.yaml` to use another directory. The queue records plans and state in `queue.sqlite3`; interrupted bites resume from their task ledger after restart.

## Unattended runner (com.portal5.arm-queue)

`queue-run` is designed to run for many hours with nobody watching. The launchd agent `com.portal5.arm-queue` keeps it alive across crashes, logouts and reboots:

```bash
./launch.sh install-arm-queue      # render + bootstrap the KeepAlive agent
./launch.sh uninstall-arm-queue    # stop it for maintenance; jobs resume on restart
```

The agent runs `uv run portal arm queue-run --poll-seconds 60` from the repo, takes only `PIPELINE_API_KEY` from `.env` (never the whole file: container hostnames and paths break host runners; seat digests come from `~/.portal5/arm_digests.env`), restarts under launchd `KeepAlive` with a 60 s throttle, and logs to `arm-queue.launchd.log` under the tasks directory (`~/AI_Output/generated/tasks/` with the default workspace root). Enroll that log in the hourly rotation by adding `~/AI_Output/generated/tasks/arm-queue*.log` to `LOG_ROTATE_FILES` in `.env`.

Exactly one runner may hold the queue. A second `queue-run` copy — a manual one while the agent runs, or a launchd respawn racing the old process — exits cleanly (status 0) while the live runner holds `<tasks dir>/queue-runner.lock`; the pid-plus-start-time identity means a crashed runner's lock is never mistaken for a live one. Inside the queue the existing BUSY guard refuses to claim a second task while one runs. For maintenance, stop the agent with `./launch.sh uninstall-arm-queue` (or `launchctl bootout gui/$(id -u)/com.portal5.arm-queue`); a job mid-step is adopted from its recorded pid and start time when the runner returns.

Notices go to the portal5-telegram bot through the arm outbox. A finished job's notice names the failing (or last) step and its state, the last stdout line of that step — the `CAMPAIGN <id>: complete|stopped … rows n/m` line, or the `CANARY <id>: SETUP …` verdict — the report path when a `-report` step ran, and the next queued job. A canary SETUP stop is worded as a harness failure (the rows never ran), not a model verdict. A memory-safety trip, an orphaned-step adoption after a runner restart, and every runner start each send their own notice.

A daily digest is sent once per UTC day (state in `<tasks dir>/queue-digest.json`), and on demand with:

```bash
uv run portal arm queue-digest             # print + queue for Telegram
uv run portal arm queue-digest --no-send   # print only
```

The digest reports jobs done/blocked/queued/running with blocked reasons, the rows measured (summed from the jobs' CAMPAIGN lines), and any job that has waited on a precondition for more than an hour, with the recorded wait reason and how long it has waited (measured from the current WAITING episode in the queue event history).

Cancelling a job (`portal arm queue-cancel`) releases the quiet-host window claim (`~/.claude/orchestrate/state/jarvis_local_window.json`) when it names the cancelled job — even while the runner pid that wrote it is still alive. While the queue is idle, a claim whose job no longer exists or is finished is treated as stale and removed; a claim naming a queued (waiting) job is kept, because holding the window while waiting for lanes is the documented behavior.

Open WebUI uses that same queue. The pipeline MCP tool `arm_queue_task(task_id, discipline, template_key, parameters, source_dir=None)` renders a stored plan template and calls `QueueLedger.enqueue`; it does not plan on the Deep seat and does not need the digest variables above. It returns the `receipt.json` path under `get_generated_dir("tasks")`. `portal arm queue-run` writes that file. The tool is active when the module is enabled. `source_dir` must be an existing directory under the workspace root or the repository; omitted, it is the uploads directory. Template parameters that name host paths are held to those same roots. The tool is dispatched through the platform's module plugin seam rather than a module import. Add `arm_queue_task` to a workspace's `tools:` list in `config/portal.yaml`, then restart the pipeline MCP (:8928), before a chat can call it.

The offline rig uses no live stack or model. Run it with:

```bash
uv run python tests/wfe/e2e/rig_orchestration_arm.py
```

The rig prints its `receipt.json` path. Block notices go to a stub interface in this phase; no Telegram message is sent.

`scripts/orchestration_acceptance.py` is the operator-facing harness. `--dry-run` runs its scenarios against the same fake Pipeline; live mode needs `PIPELINE_API_KEY` plus both seat digests and re-checks WFE before every scenario. Its shared host-quiet preflight blocks below `UAT_MIN_HOST_HEADROOM_GIB` (default 1.5 GiB), on a live entry in `/tmp/portal5-memory-safety-test-pids`, or when detected pytest/xdist processes exceed `UAT_MAX_PYTEST_PROCESSES` (default 5). `--wait-for-quiet` polls those transient blockers every 30 seconds for up to 20 minutes (`--quiet-poll-seconds`, `--quiet-max-wait-seconds`) before refusing; without the flag the refusal is immediate. Dispatch lane jobs and Pipeline busy requests are recorded in `host_quiet.start/end` and in the receipt; lane jobs are listed under `other_heavy_processes`, busy requests under `busy_requests`, and neither blocks. It writes `acceptance_receipt.json` and `.md` under `<tasks dir>/arm-acceptance/` by default. It is a smoke/wiring harness, not Gate B/C exit evidence: scenarios that need controllable model output report `SKIP` with `required: true`, and `SKIP` exits non-zero.

`scripts/gate_c_calculator.py` reads arm task receipts together with their `plan.json`, reports per-discipline/seat rates plus the WFE `rates_by_discipline` block, evaluates the fixed `pass_criteria`, and prints the task-level `calibration.minimum_pass_probability` floor. It never writes config. Planner and checker rows stay in the receipt. Gate C counts only final bite-suite rows (`passed`, `blocked`, `failed`). A `HARNESS_ERROR` row is excluded.

Run a suite trial against one Pipeline workspace or persona. The default receipt directory is `get_generated_dir("tasks")/orchestration-bite-suite/`. Dry-run completes without a live model or stack.

```bash
uv run python scripts/orchestration_bite_suite.py \
  --discipline detection-engineering --seat splunkdetectionauthor \
  --suite bite --repeats 2
uv run python scripts/orchestration_bite_suite.py \
  --discipline test_fixing --seat auto-coding --suite all --dry-run
```

Live mode uses the shared host-quiet preflight and `PIPELINE_API_KEY`. Dry-run targets the fake Pipeline rig and marks the receipt as non-gating.

## Local escalation

Jarvis Local can ask a cloud lane to repair a blocked job without the orchestrator in the loop. The switch is `queue.escalation.enabled` under `orchestration_arm.queue` in `config/portal.yaml`. It defaults to false. `portal arm queue-run` and `portal arm escalate` read it when they start. Leaving it false changes nothing.

A job is escalated only when it finishes blocked for a canary SETUP verdict, a `HARNESS_ERROR`, a step failure, or a memory-safety trip. A job the operator cancelled is left alone. The runner writes a brief to `coding_task/escalations/<job>-<n>.md` and calls `dispatch.py`. Attempts 1 and 2 use `--tier auto`. Attempt 3 uses `--tier escalate`, which walks the dispatcher's `ESCALATION` ladder and takes the first seat with headroom, one effort step up and never at max effort. Security, compliance, and detection jobs pass `--kind security`.

Auto-merge happens only when every changed path is under `tests/wfe/`, `tests/wfe/plans/`, `config/arm_jobs/`, or `coding_task/`, and a throwaway worktree passes `uv run pytest tests/unit tests/wfe/tests -q` plus `uv run ruff check .` and `uv run ruff format --check .`. The runner then merges to local `main` with no push, moves the snapshot worktree to that commit, re-runs the job's canary, and re-queues the job only if the canary passes. A diff that touches `portal/`, `config/` outside `config/arm_jobs/`, `scripts/`, or a Dockerfile is not merged. The branch stays, and Telegram gets the branch, a one-line summary, and why it was held. The live stack is not rebuilt or restarted.

Two routed attempts and one escalated attempt are the limit. If none of them produces a merged re-queue or a held branch, the job stays blocked with reason `escalation exhausted: <lane ids>` and the queue moves on. Each step (dispatched, result, merged, held, parked) is a Telegram notice, a row in the job receipt's `escalations` list, and a row in `<tasks dir>/escalation.sqlite3`.

To turn it on, set `queue.escalation.enabled` to true in `config/portal.yaml` and refresh the generated arm config. Do not start it from a worktree with `./launch.sh`.

```bash
uv run python -m portal.platform.inference.cli sync-config
uv run portal arm escalate <job-id>     # one blocked job
uv run portal arm queue-run             # escalates eligible blocks as it drains
```

To stop it, set the flag back to false and end the `portal arm queue-run` process. That does not restart the stack. A lane that already started runs until it exits; if the queue runner is gone, its branch is left unmerged. `portal arm escalate` refuses while the flag is false.
