# TASK_HOST_MEMORY_SAFETY_V1 — closeout

Closed 2026-10-07. Commits on `main`: `ba35ec5b` (W1), `a328776e` (W5), `25d8708e` (W4), `9f4fd77c` (W2), `c2114c9b` (W3), `e7bd3868` (W6), and this closeout. Evidence lives in `reports/host_memory_safety/`.

## Ledger

| Row | Disposition | Evidence |
|---|---|---|
| W1 multi-model guard | DONE (`ba35ec5b`, reviewer) | `tests/unit/test_load_guard.py`; W3 added lock release on cancel |
| W2 one guarded path to Ollama | DONE | `reports/host_memory_safety/W2.md`, `W2_live_watchdog.log` |
| W3.1 pipeline non-streaming cancel | DONE | `reports/host_memory_safety/W3.md` |
| W3.2 pipeline streaming cancel | DONE (measured; Starlette closes the generator, so no watcher was needed) | `W3.md` |
| W3.3 engines abort on close | DONE (measured; both abort, keep_alive unchanged) | `W3.md` |
| W3.4 compliance MCP cancel token | DONE (REST route); MCP-protocol path recorded as a known limitation | `W3.md`, `unit-known-limitations-compliance-mcp-protocol-calls-not-cancelled` |
| W3.5 council load-plan waves | REJECTED: the council asks seats sequentially; each cold load is already admitted by the guard with `X-Portal-Load-Wait` 900 s. Revisit if the council becomes concurrent | `W3.md` |
| W4 bounded logs | DONE (`25d8708e`) | `reports/host_memory_safety/W4.md` |
| W5 extraction model + env bindings | DONE (`a328776e`); live negative check added at closeout | `reports/host_memory_safety/W5.md`, below |
| W6 memory gate | DONE | `reports/host_memory_safety/W6.md`, `W6_watchdog.log` |
| §3 live-test watchdog | DONE, with the trip condition corrected | `W2.md` |

## Review corrections (this review pass)

The coding agent stopped W2 on a watchdog trip and left W2 uncommitted. The review found:

1. **The watchdog trip was a false positive.** It fired on low free swap alone. macOS adds swap in 1 GiB files on demand, so free swap under 1 GiB is routine: an idle host here read 983 MiB free swap at 84% free memory and normal pressure. The watchdog now trips on critical kernel pressure (`kern.memorystatus_vm_pressure_level`), or on low swap only while free memory is also low. It logs the top resident processes at a trip. Its Ollama unload resolves `host.docker.internal` to `localhost`, and its oMLX unload continues past a per-model error. The provisional known-limitation unit for the trip was withdrawn.
2. **A second, genuine trip** (14:09 UTC, memory free 43% → 18% in 4 s, pressure warning) was not attributable afterwards. A clean re-run of the unit suite under a 1 s sampler stayed at 63–75% free. The top-RSS logging above exists so the next trip can be attributed.
3. **W2:** the compliance `ollama-native` dialect read `/api/ps` without the bearer (401, `num_ctx_applied: 0`); fixed. The pinned router call was admitted as well as tracked, which put an `/api/ps` round-trip inside every routing deadline and made a router test order-dependent under xdist; it is now tracked only, as specified. A dead `OLLAMA_BASE` env entry on the pipeline service was removed.
4. **W3 (found only by live tests):** `CorrelationIdMiddleware` (a `BaseHTTPMiddleware`) hid every disconnect from `is_disconnected()`, and the native passthrough blocked in `send()` until Ollama finished. A cancel during guard admission would also have leaked the host-wide cold-load lock. All three are fixed, and each has a test that fails on the old code.
5. **W6:** the spawned uvicorn workers had no root log handler, so every `portal.*` INFO line from a worker was dropped. This predates the task; fixed in `router/app.py`.

## Phase 0 truths

From `reports/host_memory_safety/PHASE0.md` (HEAD `eed5b451`): `ollama.log` 3.3 GB; the memory MCP's `MEMORY_EXTRACT_MODEL=gemma4:e4b-it-q4_K_M` was not installed (extraction 404); `memory_pct()` in the pipeline container read 0.0; the direct-caller inventory matched the W2 list.

## W2 caller dispositions

Migrated to the passthrough: graph-memory extraction, RAG page transcription, compliance `OllamaNative` (`/chat`, `/show`, `/ps`), wiki adapter. Guarded in-process: tool preselector and startup warmup (admit + track), pinned router (track only). Reason-allowlisted in `config/ollama_direct_allowlist.yaml` and enforced by check `HM`: persona-matrix client, security operator/eval paths, tool-preselect CLI probe, `backend_introspect` unload control. Full list: `W2.md`.

## W3 measured engine abort behaviour

Ollama stops generating when the connection closes (`srv stop: cancel task`, GIN 499/500) and keeps the model resident. oMLX drops `active_requests` to 0 within 1 s. Timeline table: `W3.md`.

## W4 O_APPEND finding

launchd opens `StandardOutPath` in append mode. A truncated service log resumed at the new end, not at the old offset, and was not sparse. Copy-truncate is safe for every rotated writer; none needed a restart fallback (`W4.md`).

## W5 live negative check (closeout)

`MEMORY_EXTRACT_MODEL=gemma4:not-installed-tag uv run python scripts/check_model_bindings.py` → `FAIL — 1 orphaned binding(s) … NOT INSTALLED`, exit 1; unset → exit 0. Live extraction through the guarded path returned entities and a relation (`W2.md`).

## Re-anchored edits

`TASK_EMBEDDINGGEMMA2_PLATFORM_V1`, re-checked at `e7bd3868` from a fresh payload extraction: manifest 21/21 OK; `phase1_apply.py --check` gives 29 APPLY + 4 DELETE, 0 FAIL. The `phase2_apply.py` readiness-check letter now derives as `HN`, because W2 took `HM`; `--check` gives 5 APPLY. No payload or SHA change was needed. Only the EG2 prose that named `HM` was updated.

## Known limitations

- `unit-known-limitations-compliance-mcp-protocol-calls-not-cancelled`.

## Other findings (not fixed here, outside scope)

- Some unit tests reach a live `localhost:9099/ollama/{show,ps}` and get 401 (before W2 they reached `:11434`). They pass because an unreadable ceiling disables the check, but they breach the no-network rule for `tests/unit/`.
- A raw Ollama tag sent as `model` to `/v1/chat/completions` (`gemma4:e4b-it-qat-ctx8k`) was served by the default routing group's oMLX model (`gemma-4-26b`), without an error.
- Pipeline images rebuilt for this task: `portal-pipeline`, `mcp-memory`, `mcp-rag`. The compliance MCP was restarted for W3.

## Final gates

- `validate_system.py --skip-pytest`: 217 pass, 0 fail, 3 warn (BULLY trust-axis, NERC sync age, pre-service compliance windows), 4 skip.
- `smoke_stream.sh`: PASS on the final pipeline image.
- `ci_local.sh`: its strict mypy step fails on **5 errors in 4 files this task did not touch** (`security/core/exec_chain.py:2583`, `security/core/goal_decide.py:175`, `router/streaming.py:211`, `cad/tools/cad_render_mcp.py:387,393`). The 4 errors this task introduced (`payload["model"]` typed `object` in the preselector and warmup guard calls) were fixed. Because that step stops the script, its pytest stage was run directly: `pytest tests/unit portal/modules/security/tests -n auto` gave 4772 passed, 6 skipped.
