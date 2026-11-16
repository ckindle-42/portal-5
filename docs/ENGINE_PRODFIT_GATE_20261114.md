# Production-fit gate for engine candidates — 2026-11-14

Status: implements the operator's production-fit gate (operator, 2026-11-14:
"can they be used in our setup?"). Speed and quality alone do not qualify an engine.

The question is per (engine, mode, seat): a candidate that wins a speed or quality cell
still cannot take a seat unless it runs beside production without disturbing it, can be
unloaded and reloaded under the Pipeline's control, and can be operated as a service.
`tests/benchmarks/engine_eval_runner.py prodfit` answers it and writes one receipt per
cell.

## Command

```bash
# one cell (canary first: a cell whose canary was not valid on this build has no
# production-fit question to answer)
uv run python -m tests.benchmarks.engine_eval_runner canary --cell ENGINE:MODE:SEAT
uv run python -m tests.benchmarks.engine_eval_runner prodfit --cell ENGINE:MODE:SEAT

# e.g.
uv run python -m tests.benchmarks.engine_eval_runner prodfit --cell mlx-serve:plain:coding
```

`PORTAL_DATA_ROOT` is required and must be outside the repository. The receipt lands at
`$PORTAL_DATA_ROOT/engine_eval/prodfit/<build>/<engine>--<mode>--<seat>.json`, where
`<build>` is `git rev-parse HEAD` (`--build` overrides it). Exit code is 0 on PASS, 2
otherwise; the printed line names the verdict, the failed items and the receipt path.
A cell whose registry argv cannot be rendered or whose engine is not installed gets a
`BLOCKED` receipt (`failed_items: ["preflight"]`) instead of a missing file.

## Registry data (`tests/benchmarks/engine_h2h.yaml` `prodfit:`)

`production_seats` names the seats a candidate must co-reside beside. Each entry carries
the oMLX checkpoint the seat decision is about, the bench `workspace` + `backend` that
loads that checkpoint through the Pipeline, the `production_route` users actually reach,
and the `fallback_backend` behind it. `stack` lists the host services that must be up for
the whole cell. `autoupdate_channels` records each engine's install channel, so the
operations receipt can say whether `scripts/engine_autoupdate.py` could ever drive it.
Nothing here changes production config, workspaces or launchd.

One fact the registry records rather than hides: production serves the daily-MoE seat on
`ollama-general` (the GGUF tag), because `omlx-general` does not alias it
(`ENGINE_EVAL_MATRIX_20261113.md` §Daily MoE). The oMLX `NVIDIA-Nemotron-3.5-Lightning-
30B-A3B-oQ4e-mtp` checkpoint is still the model that seat's MLX decision is about, so a
code candidate is measured against it loaded on oMLX through `bench-engine-daily-moe`.

## The receipt — three blocks, PASS/FAIL per item with evidence

**co-residence** (the load-bearing one). The other production seats are warmed through the
Pipeline and confirmed resident on oMLX *before* the candidate starts, so a candidate that
evicts one is visible rather than masked. While those seats stay resident and the stack is
up, the candidate runs on its seat and the run drives one request per seat, then the
candidate's seat under `concurrency` concurrent requests.
Recorded: vm_stat wired/free and page counts around the candidate's own load and the mixed
load, swap used and growth, `memory_pressure`
free percentage and `kern.memorystatus_vm_pressure_level`, oMLX `final_ceiling` /
`current_model_memory` and its loaded set before and after, Ollama `/api/ps`, the
Pipeline load guard's `POST /admin/load-plan` verdict for the resident seat set,
`portal5_load_guard_*` counter deltas, candidate pid and log OOM hits. FAIL when the
stack is down, a production seat asks for something and does not get it, the candidate's
requests do not reach its pinned backend, a production seat is missing from oMLX's loaded
set afterwards, or swap exceeds `engine_h2h.yaml` `guard:` (`max_swap_growth_mb`,
`max_start_swap_used_mb`). Recorded but not failed: critical memory pressure, a guard
unload or refusal during the window, a suspiciously slow production seat (cold reload).

How production budgets memory (what the receipt reads): the Pipeline load guard admits
every Ollama and oMLX load against one host budget. With `LOAD_GUARD_CEILING_GB` unset,
headroom is oMLX's live `final_ceiling` minus its residents, plus idle Ollama residents,
minus `LOAD_GUARD_MARGIN_GB`; a fixed `LOAD_GUARD_CEILING_GB` replaces the ceiling
(`docs/ADMIN_GUIDE.md`, `portal/platform/inference/load_guard.py`). The receipt records
both numbers and derives which budget applied. A candidate engine on its own port is not
visible to the guard at all — it is charged by the host — which is exactly what the vm_stat
and swap readings are for.

**lifecycle**. oMLX's control path is `POST /admin/api/models/{id}/unload` (load_guard)
or `POST /v1/models/{id}/unload` (harness), with reload on the next request. A managed
candidate has no HTTP unload route: the Pipeline-side control is stopping the owned
process group and relaunching the registry argv. The run measures stop seconds, whether
the port is free, cold-load seconds (`ready_s` from launch) and the first request after
reload. While the candidate is down it asks the seat's `production_route` and its
`fallback_backend`, and it sends the pinned bench-workspace request to prove what that
path does. FAIL when the stop leaves the port held, the reload does not serve, the
production route or the Ollama fallback does not answer, or the exclusive request never
returns. The `bench-engine-*` workspaces are exclusive by design
(`config/bench_engines.yaml` `exclusive_workspaces`), so a pinned request while the
candidate is down returns an error instead of falling through — that is recorded, and the
route users reach is the fallback this item proves.

**operations** — one PASS/FAIL per checklist item, each with its own evidence:
launchd-able (a plist built from the registry argv with `KeepAlive` and absolute logs,
`plutil -lint` clean, never installed), health endpoint (the registry `health_path`
answers 200 and resolves the seat id, or the listing is declared not to be the served
set), version detectable (a non-interactive probe returns a parseable version and the
engine has a declared install channel; `engine_autoupdate.py` itself covers ollama and
omlx only), arm64 (host, the launcher chain, and the executable `ps` reports for the
process serving the seat — every Mach-O arm64 or universal; a cell whose engine is not
running gets no arm64 claim), and config surface (a `config/backends.yaml`-shaped entry:
url, `health_path`, reserved eval port matching the registry, seat model id in `models`).

The overall `verdict` is PASS only when all three blocks and the final shutdown pass.
A co-residence FAIL is a recorded result, not a dropped engine.

## Limits

- The gate runs live and belongs to the orchestrator: it starts a managed engine, drives
  LLM requests through the Pipeline and stops the engine. The unit tests mock every
  endpoint and every process.
- The daily-MoE seat is warmed through `bench-engine-daily-moe` +
  `eval-openai-omlx-incumbent`, so the Pipeline must have the eval backends registered
  (`PORTAL_ENABLE_EVAL`, `PORTAL_BENCH_WORKSPACES` or the eval module) for that one warm;
  the coding and hunt seats warm on their production workspaces. Without them the
  co-residence item fails at `other_seats_loaded_before` and the receipt says so.
- All values above are produced by the run; nothing here is claimed from an offline read.
  Endpoints the gate relies on are the ones the canary already reads
  (`/v1/backends`, `/v1/chat/completions` with `x-portal-route`, `/metrics`,
  `/admin/load-plan`, oMLX `/v1/models/status`, Ollama `/api/ps`) plus the vendor health
  path; any of them returning something unexpected is recorded in the receipt.
