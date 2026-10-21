# Portal orchestration arm

## Scope

The Phase 1 arm runs hand-written bite plans through the Pipeline's OpenAI-compatible chat endpoint. Each attempt starts with fresh messages and selects the existing `auto-daily::fast` or `auto-daily::deep` seat. MCP tool calls stay inside the Pipeline tool loop; the arm passes `portal_bite_tools` so that each request can expose only the current bite's tools. The local `finish` client tool ends the bite and writes its checked output.

The scheduler, SQLite ledger and deterministic checker live in `portal/modules/orchestration/`. This is a separate module package because `portal/platform/agent/` is platform core and owns Security's `run_loop`; the arm does not import or wrap that goal loop. The module is registered as `orchestration` and is disabled by default. Phase 1 adds no planner, Open WebUI entry point, Deep review, or Telegram transport.

## Worker and checks

The worker sends one streaming Pipeline request for each bite attempt. It records the request and SSE events as JSONL, keeps reasoning enabled, applies the attempt's time and output-token budgets, and requires one `finish` call. A malformed finish argument gets one repair request when the bite budget allows it. Pipeline-dispatched tool errors remain structured tool results in the Pipeline loop. A finish call that is missing, refused, malformed, over budget, or outside the allowed tool set is discarded.

After a valid finish, the arm checks the output schema and runs the bite's deterministic acceptance checks. The SQLite transition history records build SHA, model tag and digest, elapsed time, and details. Resume returns unfinished bites to `ready` and refuses changed build or model identities unless the caller explicitly supplies `--override`.

## Scheduling and recovery

`config/orchestration_arm.yaml` sets residency mode (default `swap`) and the underlying model identities used by `POST /admin/load-plan`. The scheduler runs one bite at a time. Before a request, it asks the Pipeline load guard whether that seat fits; actual model loads happen through the Pipeline transport, whose load guard serializes cold loads. In swap mode, ready Fast bites run first unless a Deep bite unlocks more downstream work than the current Fast queue.

The failure ladder retries Fast twice after its initial attempt, tries one Deep attempt, then marks the bite `blocked` and calls a notice interface. The default notice sink is an in-process stub. Independent branches continue after a bite blocks.

Task artifacts use `get_generated_dir("tasks")`, which defaults to `~/AI_Output/generated/tasks/`: each task contains `ledger.db`, normalized `plan.json`, resolved `inputs.json`, per-attempt transcripts and checks, output files, and `receipt.json`. The receipt follows the WFE rig shape: `head`, `utc`, `results`, and `workdir`-style task evidence.

## Offline verification boundary

`tests/wfe/e2e/rig_orchestration_arm.py` runs the arm against a fake OpenAI-compatible Pipeline API on an ephemeral local port. It covers a happy path, red-flag retry, budget exhaustion, wandering, Pipeline failure, SIGTERM resume, identity mismatch refusal, and a blocked bite alongside an independent pass. `tests/unit/test_orchestration_arm.py` adds scope and checker adversarial tests, including plausible-but-wrong outputs. These tests prove the offline arm only; no live model or stack is started by Phase 1.
