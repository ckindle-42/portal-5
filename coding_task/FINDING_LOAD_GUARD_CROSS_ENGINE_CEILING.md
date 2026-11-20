# FINDING — load_guard must charge an Ollama load against oMLX's ceiling

Lane `lane/load-guard-cross-engine`, base `ad7163296` (2026-11-20). Code, tests and docs are
complete and gate-green. Every live claim below is for the orchestrator to re-prove; this lane
ran no stack, no model load and no `launch.sh`.

## What oMLX 0.8.0 actually exposes (read-only GETs, 2026-11-20)

| endpoint | ceiling-ish fields | notes |
| --- | --- | --- |
| `GET /v1/models/status` | `final_ceiling`, `current_model_memory`, per-model `estimated_size`/`actual_size`/`loaded`/`is_loading`/`pinned` | the one the guard already reads. `final_ceiling` is the engine's **hard limit** — `min(static_ceiling, dynamic_ceiling, metal_cap)` (`engine_pool.get_status()` → `process_memory_enforcer._get_ceiling_breakdown`). |
| `GET /api/status` | `model_memory_max` (= the same `final_ceiling`), `model_memory_used` | no per-model rows, no breakdown. |
| `GET /health` | `engine_pool.final_ceiling`, `engine_pool.current_model_memory` | same number. |

**Neither endpoint exposes `dynamic_ceiling_bytes`, `static_ceiling_bytes`, `reserve_bytes`,
the phys footprint, or `other_app_reclaim_ratio`.** `ProcessMemoryEnforcer.get_status()` computes
all of them (`~/omlx-live/venv/lib/python3.13/site-packages/omlx/process_memory_enforcer.py`
lines 2068-2130) but no route serialises it (`/admin/api/stats` only reports
`memory_pressure.{current,soft,hard}`). So the cross-engine projection has to start from
`final_ceiling` and take the reclaim share from the engine's settings file, not from the status
body.

Recorded payload: `tests/unit/fixtures/omlx_status_080.json` (three of the 35 model rows kept
verbatim; `final_ceiling` 32,872,507,814 B, `current_model_memory` 16,389,280,502 B, loaded
`gemma-4-26b-a4b-it-QAT-4bit` at `actual_size` 16,344,771,024 B). The full live body is in
`coding_task/scratch/omlx_v1_models_status_20261120.json` (scratch, not committed).

## The arithmetic

oMLX's ceiling terms (`process_memory_enforcer._dynamic_ceiling_terms`):

```
dynamic = omlx_phys + free + inactive + file_cache
          + reclaim_ratio * other_apps_active - tier_reserve
```

An Ollama resident of `N` bytes leaves `free`/`inactive` and enters `other_apps_active`, so the
ceiling it leaves behind is `C' = C - (1 - ratio) * N`. The guard requires the loaded seats to
keep their prefill share (`C' * zone - margin - used >= 0`), which solves for the largest
admissible load:

```
N <= (C * zone - margin - used) / (zone * (1 - ratio))
```

`zone` is the engine's `memory.prefill_safe_zone_ratio` (0.8 here), already read by the guard.
`ratio` is `other_app_reclaim_ratio` for the memory-guard tier (`safe` 0, `balanced` 0.25,
`aggressive` 0.5; a `custom` ceiling is fixed, ratio 1). The host runs `balanced`, so with the
recorded status and the 15.2 GiB loaded seat: room 7.27 GiB → **cap 12.12 GiB**. A 12.5 GiB
Ollama load fits the raw 13.4 GiB headroom (margin counted) but would take the seat under its
share, so it is refused (test `test_an_ollama_load_that_would_squeeze_the_loaded_seat_is_refused`).

## Which loaded seats are charged for

`_omlx_kept_seats` charges only seats the guard may **not** free: busy, active elsewhere,
pinned, loading, failover-protected (`LOAD_GUARD_FAILOVER_PROTECT_S`), and the incoming Ollama
model's other-engine copy (`_counterpart_models`). An idle, freely-evictable oMLX seat is not
charged: if the load needs its bytes the existing free path evicts it (property 1's "or
evicts"), and if the load fits anyway its prefill room is restored at request time by the
existing `_free_for_resident_omlx` path (2026-11-19). This is why the keeper test
(`test_ollama_load_spares_a_protected_omlx_resident_when_idle_memory_fits`) still spares an idle
preferred resident rather than refusing the load.

## What changed

- `portal/platform/inference/load_guard.py:157` — `_omlx_reclaim_ratio()`: env
  `OMLX_OTHER_APP_RECLAIM_RATIO`, else `OMLX_MEMORY_GUARD_TIER`, else the engine's
  `~/.omlx/settings.json` (`memory.memory_guard_tier`). `None` when unreadable.
- `:532` — `_omlx_ollama_load_cap()`: the cap above; `None` when there is no kept seat, no
  prefill zone, or no reclaim share.
- `:2023` — `_omlx_kept_seats()` / `:2052` `_hold_seat_prefill_room()`: hold headroom back and
  log it (`load_guard: <model> may add X GiB of ollama headroom; Y GiB is held so the loaded
  oMLX seat (<id>, Z GiB) keeps a 80% prefill share`).
- `:2139` — `_admit_ollama_locked` caps `available` at that number, so the existing
  free-idle → wait → refuse machinery runs against it; `:1328` names the reserve in the
  `projected-exceeds` refusal.
- `:2129` — unreadable oMLX status logs `load_guard: oMLX status unreadable for <model>;
  admitting on the fail-open path` and admits (property 3).
- Property 2 was already enforced through the live ceiling (`_check_omlx_ollama_capacity` →
  `_advance_omlx_ollama_capacity`); two tests now pin both halves (pinned resident ⇒ refuse;
  idle resident ⇒ evict, then admit).
- `scripts/lib/util.sh:339` `export_omlx_memory_settings` (was `export_omlx_prefill_zone`) also
  exports `OMLX_MEMORY_GUARD_TIER`; `launch.sh:69` calls it; `deploy/portal-5/docker-compose.yml:111`
  passes it; `.env.example:259` documents it.
- Docs: `portal_wiki/canonical/unit-ADMIN_GUIDE-load-guard-model-memory.md` and the generated
  `docs/ADMIN_GUIDE.md` (identical edits).

## What proves it live (orchestrator)

1. Restart the pipeline so the container holds this code (`./launch.sh rebuild && ./launch.sh up`,
   then `docker exec portal5-pipeline grep -n _omlx_ollama_load_cap /app/portal/platform/inference/load_guard.py`
   — the image is baked, this confirms the rebuild landed).
2. `docker exec portal5-pipeline env | grep OMLX_MEMORY_GUARD_TIER` → `balanced` (from the new
   `up` export).
3. Load an oMLX seat and send it a request (so it is in `failover_protected` or is the seat
   copy), then route a large Ollama cold load. Expect either
   `load_guard: <gguf> may add N GiB of ollama headroom; M GiB is held so the loaded oMLX seat
   (<id>, S GiB) keeps a 80% prefill share`
   followed by evictions and admission, or the same line followed by
   `Cannot load <gguf>: projected memory ... held for the loaded oMLX seat ...`.
4. If oMLX is stopped: `load_guard: oMLX status unreadable for <model>; admitting on the
   fail-open path`.

A run that shows the *old* unconditional admission has no `held so the loaded oMLX seat` line at
all, and (the 2026-11-20 failure) oMLX logs `prefill memory guard rejected` again within the
failover window.

## Not done / open

- `plan()` / `seat_fit()` are advisory snapshots and still measure the current ceiling only; an
  Ollama row there does not report the seat cap it would hit. Out of the brief's scope.
- The tier→ratio table (`safe` 0, `balanced` 0.25, `aggressive` 0.5) is copied from the engine's
  `_OTHER_APP_RECLAIM_RATIO`; 0.8.0 does not expose it on any unauthenticated route. If oMLX
  changes it, `OMLX_OTHER_APP_RECLAIM_RATIO` is the override.
- `final_ceiling` is a `min()`, so when the static or Metal cap is binding the projection
  over-charges (it still subtracts `(1-ratio)*N`). That errs toward refusing/evicting, never
  toward the incident; a fixed `LOAD_GUARD_CEILING_GB` gets the same conservative treatment.
- The engine's prefill guard compares `current` = phys footprint (22.15 GB in the incident) with
  a limit derived from the dynamic ceiling, while the pipeline charges
  `current_model_memory` (21.16 GB). That gap is pre-existing and untouched here.
