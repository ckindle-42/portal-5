# Orchestration arm operator guide

The `orchestration` module is disabled by default. Enable it when the Pipeline and its seated models are already available:

```bash
uv run portal module enable orchestration --yes
```

Set the Pipeline endpoint and the measured model digests in the shell that runs `portal arm`. The model IDs stay fixed to the existing Fast and Deep seats; load-plan IDs are read from `config/orchestration_arm.yaml`.
Set `PORTAL_ARM_APPROVAL_TTL_SECONDS` in this shell and `.env` to the same value to configure approval expiry; the default is 1800 seconds.

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

`detection-engineering` is an unseated candidate. Its hard-check bite suite, planner suite, checker controls, and stored authoring template are ready for offline validation, but it has no model binding or calibration rates. The module remains disabled, and unattended runs for this discipline stay unavailable until live Fast and Deep suite rates meet its fixed pass criteria.

A resume without `--override` refuses a changed build SHA or model digest. Review the task artifacts before explicitly adopting a changed identity. `receipt.json` reports `PASS` only when every bite passes; exhausted bites are `BLOCKED`. The scheduler reads its residency mode and the load-guard model identities from `config/orchestration_arm.yaml`.

Queue a hand-written plan or instantiate a configured template. Template parameters use repeated `--param name=value` options and are checked by the same Phase 2 plan validator as planner output:

```bash
uv run portal arm enqueue plan.yaml
uv run portal arm enqueue-template <task-id> test_fixing repair_with_tests \
  --param source_file=/path/to/module.py \
  --param test_file=/path/to/test_module.py \
  --param 'expected_behavior=value returns 2'
uv run portal arm queue-status
uv run portal arm queue-run
```

The queue waits while a WFE run has a live PID in `/tmp/portal5-memory-safety-test-pids`, while a configured yield lock has a live PID, or while the Pipeline load plan reports busy/no fit. Bench and UAT runners can opt into the same convention by writing their PID as the only line in a file under `~/.portal5/locks/` and removing the file on exit. Set `queue.yield_lock_dir` in `config/portal.yaml` to use another directory. The queue records plans and state in `queue.sqlite3`; interrupted bites resume from their task ledger after restart.

Open WebUI uses that same queue. The pipeline MCP tool `arm_queue_task(task_id, discipline, template_key, parameters, source_dir=None)` renders a stored plan template and calls `QueueLedger.enqueue`; it does not plan on the Deep seat and does not need the digest variables above. It returns the `receipt.json` path under `get_generated_dir("tasks")`. `portal arm queue-run` writes that file. The tool refuses while the module is disabled. `source_dir` must be an existing directory under the workspace root or the repository; omitted, it is the uploads directory. Template parameters that name host paths are held to those same roots. The tool is dispatched through the platform's module plugin seam rather than a module import. Add `arm_queue_task` to a workspace's `tools:` list in `config/portal.yaml`, then restart the pipeline MCP (:8928), before a chat can call it.

The offline rig uses no live stack or model. Run it with:

```bash
uv run python tests/wfe/e2e/rig_orchestration_arm.py
```

The rig prints its `receipt.json` path. Block notices go to a stub interface in this phase; no Telegram message is sent.

`scripts/orchestration_acceptance.py` is the operator-facing harness. `--dry-run` runs its scenarios against the same fake Pipeline; live mode needs `PIPELINE_API_KEY` plus both seat digests and re-checks WFE before every scenario. Its shared host-quiet preflight blocks below `UAT_MIN_HOST_HEADROOM_GIB` (default 1.5 GiB), on a live entry in `/tmp/portal5-memory-safety-test-pids`, or when detected pytest/xdist processes exceed `UAT_MAX_PYTEST_PROCESSES` (default 4). Dispatch lane jobs and Pipeline busy requests are recorded in `host_quiet.start/end` and in the receipt; lane jobs are listed under `other_heavy_processes`, busy requests under `busy_requests`, and neither blocks. It writes `acceptance_receipt.json` and `.md` under `<tasks dir>/arm-acceptance/` by default. It is a smoke/wiring harness, not Gate B/C exit evidence: scenarios that need controllable model output report `SKIP` with `required: true`, and `SKIP` exits non-zero.

`scripts/gate_c_calculator.py` reads arm task receipts together with their `plan.json`, reports per-discipline/seat rates plus the WFE `rates_by_discipline` block, evaluates the fixed `pass_criteria`, and prints the task-level `calibration.minimum_pass_probability` floor. It never writes config.

Run a live suite trial against one Pipeline workspace or persona. Planner and checker results stay in the receipt; Gate C counts only final bite-suite rows. The default receipt directory is `get_generated_dir("tasks")/orchestration-bite-suite/`.

```bash
uv run python scripts/orchestration_bite_suite.py \
  --discipline detection-engineering --seat splunkdetectionauthor \
  --suite bite --repeats 2
uv run python scripts/orchestration_bite_suite.py \
  --discipline test_fixing --seat auto-coding --suite all --dry-run
```

Live mode uses the shared host-quiet preflight and `PIPELINE_API_KEY`. Dry-run targets the fake Pipeline rig and marks the receipt as non-gating.
