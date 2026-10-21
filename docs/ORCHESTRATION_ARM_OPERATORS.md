# Orchestration arm operator guide

The `orchestration` module is disabled by default. Enable it when the Pipeline and its seated models are already available:

```bash
uv run portal module enable orchestration --yes
```

Set the Pipeline endpoint and the measured model digests in the shell that runs `portal arm`. The model IDs stay fixed to the existing Fast and Deep seats; load-plan IDs are read from `config/orchestration_arm.yaml`.

```bash
export PORTAL_ARM_PIPELINE_URL=http://127.0.0.1:9099
export PIPELINE_API_KEY='<pipeline api key>'
export PORTAL_ARM_FAST_DIGEST='<fast model content digest>'
export PORTAL_ARM_DEEP_DIGEST='<deep model content digest>'
```

Submit a YAML or JSON hand-written plan. The task directory defaults to `get_generated_dir("tasks")` (`~/AI_Output/generated/tasks/` with the default workspace root). `--tasks-dir` changes it, and `--source-dir` sets the base for relative input paths.

```bash
uv run portal arm submit plan.yaml
uv run portal arm status <task-id>
uv run portal arm resume <task-id>
uv run portal arm resume <task-id> --override
```

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

The offline rig uses no live stack or model. Run it with:

```bash
uv run python tests/wfe/e2e/rig_orchestration_arm.py
```

The rig prints its `receipt.json` path. Block notices go to a stub interface in this phase; no Telegram message is sent.
