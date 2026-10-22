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

The offline rig uses no live stack or model. Run it with:

```bash
uv run python tests/wfe/e2e/rig_orchestration_arm.py
```

The rig prints its `receipt.json` path. Block notices go to a stub interface in this phase; no Telegram message is sent.

`scripts/orchestration_acceptance.py` is the operator-facing harness. `--dry-run` runs its scenarios against the same fake Pipeline; live mode needs `PIPELINE_API_KEY` plus both seat digests, refuses to start while a WFE sweep is registered in `/tmp/portal5-memory-safety-test-pids` or running as `tests.wfe.campaign`, and re-checks before every scenario. It writes `acceptance_receipt.json` and `.md` under `<tasks dir>/arm-acceptance/` by default. It is a smoke/wiring harness, not Gate B/C exit evidence: scenarios that need controllable model output report `SKIP` with `required: true`, and `SKIP` exits non-zero.

`scripts/gate_c_calculator.py` reads arm task receipts together with their `plan.json`, reports per-discipline/seat rates plus the WFE `rates_by_discipline` block, evaluates the fixed `pass_criteria`, and prints the task-level `calibration.minimum_pass_probability` floor. It never writes config.
