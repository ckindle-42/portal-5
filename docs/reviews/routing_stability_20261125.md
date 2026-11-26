# Routing, placement, load guard and failover stability review

Reviewed the lane HEAD based on `origin/main` (`688fdb86`) on 2026-11-25. This is a source, configuration, history and receipt review. No live service or engine was contacted. The wiki fact-unit tools were unavailable in this worker session; `WORKER_CONTRACT.md`, `CLAUDE.md`, `KNOWN_LIMITATIONS.md`, `docs/MODEL_SEAT_PROCESS.md`, and the engine-order audit receipt were read before source inspection.

## Ranked findings

### 1. A clean stream close without the engine terminal frame could certify a partial answer — fixed

- **File:** `portal/platform/inference/router/streaming.py:2065`, `portal/platform/inference/router/streaming.py:2213`.
- **Claim:** The backend iterator previously treated normal HTTP EOF as successful completion even when the engine had not sent `data: [DONE]`. The router then synthesized its own finish frame and `[DONE]`, so a cleanly truncated stream could appear complete. The backend line wrapper now raises on EOF without the engine marker. Before visible output the fallback driver can try another candidate; after visible output it ends with an error notice rather than a successful partial answer.
- **Failure scenario:** oMLX emits one content delta, then closes the response cleanly before its terminal frame. The old path returned that delta with a router-generated success terminator. The new path treats the close as a stream error.
- **Severity / confidence:** `breaks-results`; high confidence from the iterator control flow.
- **Live check:** After the Pipeline image is rebuilt, exercise a real request through `/v1/chat/completions` and confirm a normal stream includes content and one `[DONE]`. A controlled engine exit after a real first delta should produce the router's error ending; it must not turn the partial delta into a successful completion. Do not treat this unit regression test as live proof.

### 2. Native Ollama passthrough split admission from its activity lease — fixed

- **Files:** `portal/platform/inference/router/ollama_passthrough.py:168`; `portal/platform/inference/load_guard.py:2058`.
- **Claim:** The native passthrough called `guard.admit()` and only then `guard.begin()`. The guard already has `admit_and_begin_ollama()`, which reserves the cross-worker activity lock and rechecks residency between admission and lease installation. The passthrough now uses that method.
- **Failure scenario:** A resident model passes the first `/api/ps` check. A concurrent eviction obtains the operation lock before `begin()`, unloads the model, then the native request acquires its activity lease and sends an inference without rerunning admission. That load no longer has the guard's memory decision.
- **Severity / confidence:** `stability`; high confidence that the old call sequence bypassed the recheck. The user impact depends on the unload/request interleaving.
- **Live check:** With the selected Ollama model resident, exercise `/ollama/api/chat` while a separate real request makes the guard unload an idle resident. Verify the in-flight lease blocks the unload, or that admission rechecks and accounts for a model that was unloaded before the request is sent.

### 3. A multi-candidate oMLX capacity refusal could run two independent free-and-retry loops — fixed

- **Files:** `portal/platform/inference/router/streaming.py:2174`; `portal/platform/inference/router/streaming.py:3267`.
- **Claim:** The guarded stream retried a 400/507 after freeing idle Ollama memory. The multi-candidate wrapper also owned a capacity retry. If the first retry still returned a capacity refusal, it could trigger another free pass and another oMLX attempt before trying the next candidate. The guarded stream now leaves this retry to the outer wrapper while it is driving a cascade; single-candidate streams retain their one local retry.
- **Failure scenario:** oMLX returns 507, one Ollama resident is freed, and the retried request still returns 507 because the remaining headroom is insufficient or the memory counter has not settled. Previously the wrapper could free again and issue a further oMLX request, delaying fallback and potentially evicting additional Ollama residents.
- **Severity / confidence:** `stability`; high confidence from the nested retry control flow.
- **Live check:** On a real multi-candidate request that receives an oMLX capacity 400/507, confirm there is at most one guard-directed idle-Ollama free pass and one same-seat retry before the route either succeeds or falls through to the next backend. Check the route trace and load-guard unload/admission logs.

### 4. The 300-second failover shield is worker-local while the service defaults to two workers

- **Files:** `portal/platform/inference/load_guard.py:540`, `portal/platform/inference/load_guard.py:671`, `portal/platform/inference/load_guard.py:891`, `portal/platform/inference/load_guard.py:911`; `deploy/portal-5/docker-compose.yml:124`.
- **Claim:** `FAILOVER_PROTECT_S` is 300 seconds, but `_failover_protected` is an in-memory field on each `LoadGuard`. The deployment defaults `PIPELINE_WORKERS` to 2. Activity leases are coordinated across workers with file locks, but the failover deadline is not shared.
- **Failure scenario:** Worker A fails over to Ollama model M and protects M. After that request ends, worker B admits a large load before the 300 seconds expire. Its guard has no protection entry for M and can select M as an idle eviction candidate, causing the next request to cold-load it again or fail for capacity.
- **Severity / confidence:** `stability`; high confidence in the local state and default worker count. Whether a live admission evicts M depends on the active memory state.
- **Live check:** Run a real failover on one worker, let its request finish, then cause memory pressure through a request handled by the other worker inside the 300-second window. Confirm whether the served fallback model remains excluded from the unload list. This needs a proposed follow-up for shared protection state; no worker or service setting was changed here.

### 5. Busy-aware routing sees engine requests, not the guard's pre-request cold-load queue

- **Files:** `portal/platform/inference/router/handlers.py:743`, `portal/platform/inference/load_guard.py:1244`, `portal/platform/inference/load_guard.py:1886`, `portal/platform/inference/load_guard.py:2711`.
- **Claim:** Busy-aware placement calls `omlx_engine_busy()`. That method counts begun pipeline activity and oMLX `active_requests` / `waiting_requests`. A cold oMLX request first waits in `admit_omlx()` for the guard's per-process or shared cold-load lock; `begin(OMLX, model)` is installed after admission. The busy check does not include that admission wait, although `has_activity()` does inspect the guard locks.
- **Failure scenario:** One large oMLX cold load is still in guard admission and has not reached the engine. A second request has a warm idle Ollama copy. Its placement check can see oMLX as not busy, leave oMLX first, then wait behind the cold-load lock instead of taking the resident Ollama path. The default load wait is 120 seconds; streaming emits heartbeat comments while waiting, while non-streaming callers see no response body during that wait.
- **Severity / confidence:** `stability`; high confidence in the check ordering. A live route decision depends on the exact timing and resident set.
- **Live check:** With a real same-hint Ollama resident, start two different cold oMLX seat requests so one holds the cold-load admission lock before its upstream request starts. Inspect the second request's `x-portal-route`, trace, and guard wait duration. Determine whether it queues on oMLX or takes the idle Ollama resident.

### 6. oMLX idle eviction has a check-to-unload window

- **Files:** `portal/platform/inference/load_guard.py:1127`, `portal/platform/inference/load_guard.py:1257`, `portal/platform/inference/load_guard.py:1289`, `portal/platform/inference/load_guard.py:2112`.
- **Claim:** `_omlx_idle_models()` snapshots resident models and checks activity, then `_free_omlx()` posts unloads. Unlike the Ollama unload path, this oMLX pass does not reserve the model's cross-worker activity lock between the idle check and unload POST. Resident oMLX requests can install their activity lease without taking the cold-load lock.
- **Failure scenario:** Worker A sees oMLX seat B idle and chooses it for unload. Before its POST lands, worker B starts serving B. If oMLX accepts the unload while B is serving, the response can be interrupted or the model can be unloaded under new work. If the engine refuses active unloads, the result is instead a failed reclaim and another pass/refusal.
- **Severity / confidence:** `stability`; medium confidence on outcome because the live oMLX unload behavior decides whether the request is rejected or interrupted.
- **Live check:** During a real reclaim, start a request for the oMLX resident selected for unload between the status snapshot and unload POST. Confirm the engine refuses/defers unload while the activity lease is held, or observe whether the request is interrupted. This needs a targeted coordination fix if reproduced.

### 7. Load admission uses useful estimates and counters that still diverge from resident memory

- **Files:** `portal/platform/inference/load_guard.py:954`, `portal/platform/inference/load_guard.py:958`, `portal/platform/inference/load_guard.py:423`, `portal/platform/inference/load_guard.py:575`; `KNOWN_LIMITATIONS.md:162`.
- **Claim:** Ollama resident accounting begins with `/api/ps` `size`; the requested footprint is weights plus a KV estimate from `/api/show`, with a 1.25 weight multiplier when geometry is unavailable. The known limitation records Ollama 0.40 reporting 1.8 GB for a `devstral-small-2` runner whose child RSS was about 15 GB. The guard mitigates this for reclamation by requesting unload and remeasuring through oMLX, but the initial counterfactual headroom is still based on the reported sizes. Separately, `final_ceiling` follows host free memory when `LOAD_GUARD_CEILING_GB` is zero; compose supplies zero by default, so an unchanged model set can receive different decisions as host pressure moves.
- **Failure scenario:** `/api/ps` under-reports an idle resident or another process reduces oMLX's dynamic ceiling. A plan based on the earlier readings can predict a different fit than the next real load; the guard may wait and refuse, or unload a resident and then discover that the new headroom is smaller than expected.
- **Severity / confidence:** `stability`; high confidence in the inputs and formulas. The historical under-report measurement is dated and is not a current host measurement from this lane.
- **Live check:** Capture `/api/ps`, oMLX `current_model_memory` / `final_ceiling`, the process RSS for the corresponding Ollama runner, and the guard's admission decision at one request boundary. Repeat after an idle-model unload. Compare predicted need/headroom with actual RSS and the post-unload counter. Do not infer current values from the dated limitation entry.

## Scenario outcomes

- **Mid-stream engine death:** A transport exception or timeout becomes an error frame. Before any content, the multi-candidate wrapper can fall through to another backend. Once content, reasoning or tool calls reached the client, it ends with an error rather than appending a different answer. The new terminal-frame check also covers a clean EOF without the engine's `[DONE]`.
- **507 or prefill abort:** A pre-dispatch capacity refusal can free idle Ollama residents and retry once. In-band oMLX memory aborts also free and retry once only before output. A persistent refusal in a multi-candidate route falls through to another candidate; after output, fallback is suppressed to avoid joining two answers.
- **Client disconnect:** The standard stream path detaches the `RequestSlot` to the stream generator and releases it in `finally`; the native Ollama relay closes the upstream response and both guard callbacks in its `finally`. The source shows cleanup paths; transport closure under the real server remains a live check.
- **Two large models requested back-to-back:** Cold loads serialize through the load guard's cold-load lock. The default wait is 120 seconds and the resident-detection task can wait up to 600 seconds, unless the request ends first. A later load may wait behind the earlier admission or be refused and cascade. Streaming sends a heartbeat comment every 10 seconds; a non-streaming request can look blank until fallback or refusal. These are bounded waits in the code paths reviewed, not an observed live latency claim.
- **Hot-seat ordering:** `hot_seat_protect_s` is configured to 900 seconds. The tracker is process-local (`placement.py:65`, `placement.py:133`), so one worker does not know another worker's most recently touched hot seat. The 2026-11-25 engine-order receipt records the settled priority policy for resolvable oMLX hints; this review does not propose changing that policy. The receipt is an offline ordering analysis, not live routing evidence.

## Orchestrator runs

After merging the source changes, rebuild and restart through the launch script, then run the live streaming gate:

```bash
./launch.sh rebuild && ./launch.sh up
SMOKE_STREAM_TIMEOUT=180 ./scripts/smoke_stream.sh
```

The smoke command passes only when it reports `PASS — ... SSE chunk(s) ... [DONE] received`; HTTP failure, an error envelope, no token delta, or no terminal frame is a failure. The 180-second timeout accommodates a real cold load while still bounding the check.

For the configured `auto-coding` route, capture the served backend and terminal frames directly:

```bash
curl -sS -N -D - --max-time 180 \
  -H "Authorization: Bearer ${PIPELINE_API_KEY:?set from the orchestrator environment}" \
  -H "Content-Type: application/json" \
  http://localhost:9099/v1/chat/completions \
  -d '{"model":"auto-coding","messages":[{"role":"user","content":"Reply with OK only."}],"stream":true,"max_tokens":64}'
```

Success is HTTP 200 with `x-portal-route`, a non-empty answer, one finish frame and one `[DONE]`. A fallback request should show the actual backend in `x-portal-route` and the trace; a persistent 507 should show the refusal or user-facing no-answer path, not a false success. For the native admission change, use a real resident Ollama model on `POST /ollama/api/chat` while a separate real admission tries to reclaim memory, and inspect the guard/unload logs as described in Finding 2. Fault and race checks require the controlled real engine states above; the unit suite is only the regression gate.

## Unproven / open

- No HTTP route, engine queue, memory reading, runner RSS, unload, failover window, or disconnect was observed live in this worker session.
- The guarded retry, EOF, and native admission fixes passed unit regression tests, but their effect on the running stack is unproven until the orchestrator rebuilds and runs the commands above.
- Cross-worker failover protection, cold-admission visibility to busy-aware routing, and the oMLX unload interleaving need live reproduction before their proposed fixes are designed.
- The documented Ollama `/api/ps` size and dynamic-ceiling observations are historical inputs; this review did not confirm current values or environment overrides.
- No operator-controlled routing or memory-budget configuration was changed.
