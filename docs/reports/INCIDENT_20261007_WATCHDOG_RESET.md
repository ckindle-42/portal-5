# Incident — Mac hung and watchdog-reset (2026-10-07 00:12–00:16 CDT)

## What happened

The Mac stopped logging at 00:12:43, and the hardware watchdog rebooted it at 00:16:41.
The boot record reads `Boot faults: wdog,reset_in_1` (`ResetCounter-2026-10-07-001642.diag`).
There was no kernel panic and no process was OOM-killed: the system ran out of pageable
memory and swap, and stalled.

| Time | Evidence |
|---|---|
| 00:01:36 | Ollama log: `free_swap="0 B"`; swap was already exhausted (5 GB) |
| 00:08:50 | oMLX loads `granite-4.1-30b-4bit` (16.8 GB) for a compliance council seat |
| 00:11:37 | oMLX refuses `Qwen3.8-27B-oQ4e-mtp` (507: projected 37.5 GB > ceiling 25.6 GB). In the same second, Ollama starts loading a 22.7 GiB model with 10 GiB system-free (`predicted to exceed available memory, evicting`) |
| 00:12:02–08 | oMLX's dynamic ceiling collapses 24.5 → 21.6 GB in 6 s; its enforcer aborts and unloads granite |
| 00:12:10 | oMLX starts loading Qwen3.8-27B into the freed space |
| 00:12:14–41 | Jetsam storm (`OS_REASON_JETSAM` 0xd, low swap) kills system daemons |
| 00:12:43 → 00:16:41 | No log output; watchdog reset |

## Why

1. **Trigger.** `tests/acceptance/test_compliance_reasoning_v2_questions.py` ran the live
   multi-model compliance council whenever `:8937` answered. It was therefore part of the
   mandated pre-push `pytest tests/`, run on the production Mac while compliance is still
   pre-service. Its 90 s client timeouts left the council running server-side, so requests
   piled up.
2. **No host-wide memory admission.** oMLX and Ollama share one unified-memory pool, and
   each admits loads from its own view. When oMLX refused, the request cascaded to Ollama,
   which loaded anyway while oMLX loaded too.
3. **The pipeline's memory gate was inert.** `MEMORY_GATE_PCT` reads `vm_stat`, which does
   not exist in the pipeline container, so it always read 0 %.

## Fixes

- The live council acceptance test is opt-in (`COMPLIANCE_LIVE=1`; the closeout verifier
  already sets it).
- `portal/platform/inference/load_guard.py` sits in the Ollama native transport. Before
  any pipeline request reaches Ollama for a model that is not resident, it:
  1. serialises cold loads host-wide;
  2. waits while oMLX is mid-load;
  3. if the load does not fit and oMLX is idle, unloads oMLX's idle models, least
     recently used first;
  4. otherwise refuses with HTTP 507, which the router handles as a capacity rejection.

  Verified live: with oMLX holding 24.4 GiB idle, an `auto-research` request freed oMLX to
  4.2 GiB and loaded Nex-N2-mini (21.4 GiB), which answered. A forced oversize was refused
  and the lock was released. Resident models (the router, `task-router`) pass ungated.

## Residual

- Readings the compliance module sends straight to Ollama's `/api/chat` do not pass
  through the pipeline, so the guard does not cover them. They run one at a time
  (`SWEEP_CONCURRENCY=1`).
- Client timeouts still do not cancel server-side work through the compliance MCP. The
  guard bounds the memory effect, but the wasted compute remains.
- `/opt/homebrew/var/log/ollama.log` is 3.3 GB and has no rotation.
