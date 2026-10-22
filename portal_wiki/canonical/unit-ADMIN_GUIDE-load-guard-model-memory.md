---
id: unit-ADMIN_GUIDE-load-guard-model-memory
kind: why
title: "ADMIN_GUIDE — Load guard: model memory admission and tuning"
sources:
- type: code
  path: portal/platform/inference/load_guard.py
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: config/backends.yaml
- type: code
  path: config/grafana/dashboards/portal5_model_management.json
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1792684036
updated_at: 1792684036
---

#### Load guard: model memory admission and tuning

The load guard (`portal/platform/inference/load_guard.py`) is the Pipeline's host-memory admission control for model loads on both engines. Ollama and oMLX draw from one unified-memory pool but each engine admits a load from its own view; the 2026-10-07 watchdog reset (`docs/reports/INCIDENT_20261007_WATCHDOG_RESET.md`) is what happens without a shared gate. Every Pipeline request to either engine reports through it, so it counts in-flight requests per (engine, model), serialises cold loads behind one host-wide lock, and frees idle models rather than admitting a load that fits only by evicting a model that is serving a sibling request. An Ollama cold load that does not fit waits inside the caller's load budget: a free the guard issues stays pending until Ollama's `/api/ps` drops the model and headroom covers its bytes, and the request is refused HTTP 507 only when that budget runs out (the router cascades a 507 as a capacity rejection). When oMLX's status cannot be read the guard fails open and admits, logging loudly. Resident models — the router model, task routers, warm seats — never wait.

#### Knobs

`.env` values, passed into the Pipeline container by `deploy/portal-5/docker-compose.yml`; restart the pipeline container to apply.

- `LOAD_GUARD` (default 1): 0 disables admission entirely; in-flight tracking stays on. Change it only to confirm a refusal is the guard's.
- `LOAD_GUARD_FACTOR` (default 1.25): projected footprint = weights on disk × factor, because weights understate the loaded footprint (KV cache, compute buffers); a footprint observed the last time the model was resident overrides the projection. Raise it if large cold loads repeatedly stall near the limit; lower it only against measured footprints.
- `LOAD_GUARD_MARGIN_GB` (default 2): memory kept free after an admitted load, for everything on the host that is not a model. Raise it when non-model processes grow (bigger caches, parallel test workers).
- `LOAD_GUARD_CEILING_GB` (default 0): 0 budgets against oMLX's live `final_ceiling`, which the balanced tier derives from host free memory, so the same load's verdict can change through the night (P5-OMLX-CEILING-001). Set a fixed GiB budget to make the verdict a property of the model set rather than of the moment; the cap governs Ollama admission only — oMLX's own guard never sees it.
- `LOAD_GUARD_WAIT_S` (default 120): how long an interactive cold load waits for memory before HTTP 507. Batch callers override it per request with the header `X-Portal-Load-Wait: <seconds>` (capped at one hour); compliance's pipeline calls send their own larger budget via `COMPLIANCE_LOAD_WAIT_S`.
- `defaults.hot_seat_protect_s` in `config/backends.yaml` (default 0 = off): seconds after an oMLX model's last request during which a *different* oMLX model's request is steered to another candidate instead of deep-resetting the seat's warm prefix cache (P5-OMLX-PREFIX-CACHE-001). Turn it on when two seats share the oMLX engine and one keeps re-paying a cold prefix; it never denies service, never reorders a pinned `::model=` request, and each Pipeline worker tracks its own seats.

#### Watching it work

Admissions, wait seconds, unloads, and refusals are Prometheus counters and histograms (`portal5_load_guard_admissions_total`, `portal5_load_guard_wait_seconds`, `portal5_load_guard_unloads_total`, `portal5_load_guard_refusals_total`), and the headroom and ceiling at the last decision are gauges (`portal5_load_guard_headroom_bytes`, `portal5_load_guard_ceiling_bytes`). The Grafana dashboard `config/grafana/dashboards/portal5_model_management.json` ("Portal 5 — Model Management (Load Guard)") charts them. Refusals bucket by reason: `projected-exceeds` (the load will not fit), `transition-active` (oMLX mid-swap for the whole wait), `quiet` (nothing in flight could free the memory — waiting cannot help until something else changes), and `deadline` (another cold load held the lock). A turn no candidate could serve is counted separately in `portal5_no_answer_total`. Batch work can ask `POST /admin/load-plan` whether a set of models fits together right now, and run in fit-sized waves instead of discovering the answer as refusals.

#### Why

Two engines, one memory pool, and no engine that can see the other's view is exactly the shape that produced the watchdog reset: each engine admits from its own number, and both are right at the moment they ask. The guard makes admission a property of the host by serialising the loads and charging them against one measured budget, and it makes refusals rare by freeing idle memory and waiting inside the request's own budget first. That is why the knobs are memory figures and wait budgets rather than concurrency limits: the failure being prevented is running the machine out of swap, not overloading a server. The fixed ceiling exists because a verdict that moves with free memory cannot be reasoned about at all — an operator who wants the same answer for the same load all night buys that by fixing the budget, at the cost of also fixing what everything else on the host may use.
