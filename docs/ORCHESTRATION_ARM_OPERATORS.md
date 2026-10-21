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

Open WebUI queues through the same path via the pipeline MCP tool `arm_queue_task(task_id, goal, discipline, source_dir=None)`. It answers the queued task's `receipt.json` path, refuses while the module is disabled, and is dispatched through the platform's module plugin seam rather than a module import. Add `arm_queue_task` to a workspace's `tools:` list in `config/portal.yaml` to make it callable from that workspace's chat.

The offline rig uses no live stack or model. Run it with:

```bash
uv run python tests/wfe/e2e/rig_orchestration_arm.py
```

The rig prints its `receipt.json` path. Block notices go to a stub interface in this phase; no Telegram message is sent.
