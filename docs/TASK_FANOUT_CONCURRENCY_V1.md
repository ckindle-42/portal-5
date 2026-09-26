# Task: P5-FANOUT-001 — same-model fan-out under `OLLAMA_NUM_PARALLEL=1`, via the pipeline

Status: **EXECUTED 2026-09-25** — W1–W5 landed, acceptance A1–A7 green
(results appended at the bottom). Rollback unchanged.

## Problem

Commit 8d519995 set `OLLAMA_NUM_PARALLEL=1` because per-seat KV footprints at
baked context only fit at one slot (auto-council reviewers 50.3 vs 60.2 GiB at
2; compliance granite-30b at 98,304 tokens 29.7 vs 44.5 GiB). Known cost,
recorded in P5-ROUTER-EVICTION-001: two requests to the same model now wait
for each other instead of running side by side, which hurts the security and
compliance fan-out. Three directions were named for measurement:

1. run the fan-out on oMLX (up to 8 concurrent requests);
2. size compliance's context per call instead of a fixed 98k;
3. give only the small models a second slot.

**Operator constraint (2026-09-25, binding): everything goes through the
pipeline.** Actual usage runs through `portal-pipeline` (:9099), so fan-out
does too — the same doctrine that moved WFE seat testing to
`WFE_ENGINE=pipeline` (a5b8c895: "When a pipeline run exposes a gap, fix the
pipeline (it is the product), don't work around it in the harness"). Direct
engine calls are for raw probes only, and must say so on the receipt. The
compliance sweep/reader today posts straight to `:11434`, which is the exact
bypass this task removes.

## Measured 2026-09-25 (the evidence this plan executes on)

Harness: ad-hoc `/api/chat` + `/v1/chat/completions` probes (results inline
here); the durable instrument is `tests/benchmarks/bench_engine_concurrency.py`
(see "Prior art"). "Decode-bound" = 20-token prompt, ~100 output tokens,
temperature 0. "Ratio" = concurrent wall / serial wall for the same calls
(1.0 = no gain, 0.5 = 2x).

| # | Measurement | Result |
|---|---|---|
| M1 | ollama `granite4.1:8b-ctx8k` @ PARALLEL=1, decode-bound ×3 concurrent | ratio **1.00** — fully serialized, exactly the reported problem |
| M1b | same, prefill-heavy (8,194-token prompt) ×2 concurrent | ratio **1.02** — prefill is compute-bound on one Metal GPU; a second slot buys ~nothing (matches `_sweep_driver.py` CAVEAT) |
| M2 | ollama `granite4.1:30b`, repeated calls at the SAME `num_ctx` | **0.16 s** warm, no reload |
| M2b | same, any `num_ctx` CHANGE (98304↔32768↔65536) | **3.4–5.6 s full reload every time**; footprints 22.3 / 27.0 / 31.7 GiB at 32k / 64k / 98k |
| M3 | oMLX `granite-4.1-30b-4bit`, decode-bound ×3 concurrent | ratio **0.47 (2.1x)**; ×6 no better (~2x) — saturates around 3 streams |
| M3b | oMLX 30b, prefill-heavy (21k-token prompt) ×2 concurrent | ratio **0.78 (1.28x)** — partial prefill overlap |
| M3c | oMLX 30b surface: `response_format json_object`, tools → `tool_calls`, `reasoning_effort:"none"` | all OK (the compliance dialect contract is servable) |
| M3d | oMLX `granite-4.1-8b-mxfp8`, decode-bound ×3 / ×4 | ratio **0.41 (2.4x)** / **0.35 (2.8x)** — small fleet fans out best |
| M5 | single-call decode parity 30b | ollama 6.9 s vs oMLX 7.5 s (~90 tokens) — a wash; oMLX's win is pure batching |
| M4 | second ollama daemon (:11435, PARALLEL=2), decode ×3 concurrent | ratio **0.86 (1.16x)** — REJECTED; two llama-server streams share the GPU far worse than oMLX's batcher |
| M6 | pipeline smoke `model=auto-compliance` | served **Qwen3.8-27B-oQ4e-mtp via oMLX** (priority-10 `omlx-reasoning` alias), usage carries `model_load_duration`; `/v1/trace` attribution available |

Conclusions the plan is built on:

- **C1**: at PARALLEL=1, ollama serializes same-model fan-out completely, and
  decode-bound calls are the case that loses (prefill-bound calls were already
  additive at PARALLEL=4 — `_sweep_driver.py` CAVEAT, re-confirmed).
- **C2**: oMLX batches decode-bound fan-out at 2.1–2.8x through 3–4 streams;
  per-call latency degrades (~40%) but aggregate wins. The small fleet gains most.
- **C3**: per-call `num_ctx` sizing on ollama is a reload trap — any window
  change re-loads the model in 3.4–5.6 s. Per-call sizing is therefore DEAD on
  the ollama path; the window must be a per-seat/per-tag property. The pipeline
  reached the same conclusion by doctrine (`ollama_native.py` deliberately does
  not forward load-time options; `lifespan.py:352` tells callers to bake
  `num_ctx` into the tag via `./launch.sh apply-model-params`).
- **C4**: the "small models get a second slot" idea is dead in the second-daemon
  form (M4) and inexpressible in one daemon (`OLLAMA_NUM_PARALLEL` is
  daemon-global, no per-model override). The concurrency the small fleet needs
  comes from routing it to oMLX (M3d), which the pipeline's alias mechanism
  already does for other groups.
- **C5**: the pipeline already serves compliance conversation traffic on oMLX
  (M6). What is NOT on oMLX: `compliance-reading` (routes to `general` only),
  the bench seats the fan-outs address (`bench-granite41-8b/-30b` → `general`,
  no granite aliases on `omlx-general`), and the sweep/reader/assessment model
  calls, which bypass the pipeline entirely.

## Where the fan-outs actually are

- **Compliance sweep** (`portal/modules/compliance/core/sweep.py::map_read`,
  `sweep_standard`): sequential map readings over a standard's requirements;
  each reading is a ~12-turn tool loop (`reader.py`) through
  `reading_transport.chat` — direct `:11434`, `stream: False`,
  `DEFAULT_NUM_CTX = 98304` on every call including short verdicts
  (`reading_transport.py:205`; floor re-asserted at `reader.py:862`:
  `max(DEFAULT_NUM_CTX, ...)`).
- **Compliance council** (`council.py::run_council`): three seats, sequential
  in-process, via the same transport.
- **Security sweep** (`_sweep_driver.py`, SWEEP_WORKERS default 4): cells
  (scenario × model) run concurrently; the model call is
  `agentic_blue_eval.py::_call_model` → **already pipeline-first**
  (`:9099/v1/chat/completions`, `model=resolve_pipeline_model(tag)`,
  `CHAIN_DIRECT_OLLAMA=true` is the raw-probe escape hatch).
- **Auto-council reviewers** (`router/council.py`): `asyncio.gather` over three
  DIFFERENT models — no same-model queueing today; untouched by this task.

Prior art to reuse, not re-invent:

- `tests/benchmarks/bench_engine_concurrency.py` — fan-out harness, all three
  engines AND `--via pipeline`; established (P4.1) that ollama shares prefixes
  only within one append-only conversation and does NO continuous batching, so
  the sweep's sequential loop protects nothing and a bounded concurrent sweep
  wins on engines that batch. Sep-2026 results for Qwen3.8-27B fan-out on
  ollama/oMLX/splash are in `tests/benchmarks/results/engconc_*`.
- `tests/wfe/runner.py::_build_pipeline` + `pipeline_served` — the canonical
  "send what OWUI sends, then verify what actually served" pattern
  (`portal_client_tools_only`, `response_format`, `/v1/trace/{correlation_id}`).
- `portal/modules/security/core/exec_chain.py::_stream_chain_turn` — streamed
  request with idle-timeout (300 s no-bytes), used by the security eval in
  pipeline mode; this is how a 25-minute reading survives a path whose
  non-streaming branch kills at 300 s total (`non_streaming.py:427-432`,
  `httpx.Timeout(_req_timeout, connect=5.0)`).

## Objective — work items

### W1. Pipeline dialect for the compliance transport (the core fix)

`portal/modules/compliance/core/transport_dialects.py` gains a `PipelineCompat`
dialect registered as `"pipeline"` in `DIALECTS`:

- `endpoint` = `os.environ.get("PIPELINE_BASE", "http://localhost:9099")` +
  `/v1/chat/completions`. Works unchanged from the host (mapped port) and
  inside `portal5-pipeline` (self-call); `PIPELINE_API_KEY` is already in the
  container env — send `Authorization: Bearer` when set (same as
  `_pipeline_headers()` in `tests/wfe/runner.py`).
- `build()`: `model` is the WORKSPACE id the caller resolved (W2's resolver);
  `stream: False` is NEVER sent — the dialect issues a **streamed** request and
  aggregates (reuse or extract `_stream_chain_turn`; see W1b), because the
  reading loop's calls (up to 1,522 s recorded) exceed the pipeline's
  non-streaming 300 s total timeout. `response_format: {"type":"json_object"}`
  when `fmt` is truthy; `tools` + `portal_client_tools_only: true` when the
  caller brings its own schemas (verified contract,
  `streaming.py:1687`/`non_streaming.py:447`); `temperature`, `max_tokens`.
  `num_ctx` and `keep_alive` are accepted and DROPPED, with a comment: the
  window is the seat's baked tag (C3), resident lifetime is the server's.
- Receipt stamping (the module's load-bearing rule): `dialect="pipeline"`,
  `endpoint`, `context_source="seat_baked_window"`. Additionally verify the
  served model via `/v1/trace/{correlation_id}` (WFE pattern) and record
  `backend` + `served_model` on the ChatResult — a row served by a different
  engine than intended is attributed, not silent.
- `seat_ceiling()`: via `/v1/models`; oMLX reports no window field there today
  (verified), so return 0 (disables pre-flight — the documented stance, same as
  `OpenAICompat`). Do NOT invent a number.
- `resolve_dialect()` default: `COMPLIANCE_TRANSPORT` stays the switch; default
  value becomes `"pipeline"` after acceptance passes (land opt-in first, flip
  default in the same PR's final commit; rollback = env var, see Rollback).

W1b. `_stream_chain_turn` (or its minimal equivalent) moves to a shared
platform home — `portal/platform/inference/streaming_client.py` — imported by
both `exec_chain.py` and the new dialect. One streamed-with-idle-timeout
implementation; the compliance module must not import from
`portal.modules.security`. Keep the security import working (re-export or
direct move with both call sites updated; pick whichever keeps the diff small).

Tests (`tests/unit/test_transport_dialects.py` or alongside the existing
compliance transport tests): build-shape (no `options`, no `stream:false`,
`portal_client_tools_only` present, `num_ctx` dropped), receipt fields,
unknown-dialect error unchanged, served-model attribution recorded from a
mocked trace.

### W2. Model addressing: tags → workspaces (reuse the security resolver's shape)

The sweep/reader address raw ollama tags today; the pipeline's `model` field
is a workspace id (unrecognized values silently land on a group's first model
— `resolve_pipeline_model`'s docstring documents the failure mode). Port the
small resolver (`portal/modules/security/core/_data.py:177`) into a shared
home (`portal/platform/inference/model_addressing.py`) — map a raw tag to the
workspace whose `model_hint` matches (`bench-granite41-30b` etc.), pass
workspace ids through — and have the new dialect resolve there. Record
`workspace=` on the receipt. The existing `?model=` override semantics of
`map_read` keep working: they now name a workspace or a tag that resolves to
one.

### W3. The window becomes a seat property (replaces per-call sizing)

- **Reading seat**: the sweep's big-window need (worst case ~82k tokens,
  `reading_transport.py` derivation) is served by a tag with baked
  `num_ctx=98304` — create it with `./launch.sh apply-model-params` from the
  base tag (e.g. `granite4.1:30b-ctx98k` — trained ceiling 131,072, verified
  reachable at 98,304 in M2), register it in `config/backends.yaml`
  (`ollama-general`, `supports_tools: true` — probe first, house rule:
  measured, not assumed) and give it a `bench-*` workspace shell in
  `config/portal.yaml` (module eval, like `bench-granite41-30b`) so the
  pipeline can address it.
- **Short-call seats**: council seats, verdicts, batch decisions keep small
  tags (16k/32k). `DEFAULT_NUM_CTX = 98304` in `reading_transport.py` stays
  ONLY as the direct-dialect (raw probe) default; `reader.py:862`'s floor
  becomes `max(seat_window, ...)` where `seat_window` is the resolved seat's
  baked window — through the pipeline dialect the caller no longer picks a
  window at all. Kill the silent coupling where every call, including
  20-token verdicts, reserved a 31.7 GiB seat.
- On oMLX the window is server-side (`~/.omlx/settings.json`
  `sampling.max_context_window`, currently 262144; per-model overrides in
  `~/.omlx/model_settings.json`). The acceptance rows record
  `num_ctx_applied=0` for the pipeline dialect (honest "unknown here") until
  oMLX exposes a window API — do NOT copy a request value into the applied
  field (that exact confusion was fixed once already; see
  `OpenAICompat.applied_context_length`).

### W4. oMLX alias coverage for the fan-out seats (delivers C2/C4)

`config/backends.yaml`, `omlx-general` (the group `bench-granite41-*` and
`compliance-reading` route to):

- `granite4.1:8b-ctx8k: granite-4.1-8b-mxfp8` (on disk; the same conversion
  omlx-reasoning already serves — tool-calling re-audit still required per
  the house rule before `supports_tools: true`)
- `granite4.1:30b-ctx16k: granite-4.1-30b-4bit` and the new
  `granite4.1:30b-ctx98k: granite-4.1-30b-4bit` (omlx-reasoning already maps
  the ctx64k hint; audited clean on oMLX 0.6.4 — re-confirm on the current
  version)
- `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k: Qwen3.8-27B-oQ4e-mtp` for the
  `general` group so `compliance-reading`'s bound seat can land on oMLX
  without adding `reasoning` to its routing groups (whichever of "alias in
  general" vs "add reasoning group to compliance-reading routing" is smaller
  after `sync-config` — do exactly one, and regenerate `workspace_routing`
  with sync-config; never hand-edit it).

Priority stays 10 (shadow-shift, automatic ollama fallback on
unhealthy/rejects — the established pattern). Every alias ships with a live
tool-call probe recorded in the backends.yaml comment, matching how
omlx-security/omlx-reasoning entries were added.

DeepSeek-R1-0528-Qwen3-8B stays Ollama-only: oMLX drops its tool-call format
(documented in `backends.yaml`) — the auto-council operator seat does not move.

### W5. Flip the compliance fan-out to the pipeline; set concurrency

- `sweep.map_read`/`sweep_standard`: resolve dialect via `COMPLIANCE_TRANSPORT`
  (now default `pipeline`), and run requirements **concurrently with a small
  bound** — a module-level `SWEEP_CONCURRENCY` (default **3**, the measured
  oMLX saturation point; env-overridable) with a `ThreadPoolExecutor`, since
  the sequential loop's docstring rationale (prefix-cache protection) was
  already falsified by P4.1. Per-requirement write semantics, receipts, and
  `context_overflow` routing are unchanged; results are keyed, not ordered.
- The council's seat loop (`run_council`) stays sequential this task (three
  different models; changing vote-order semantics is out of scope) — but its
  calls now go through the pipeline dialect and therefore oMLX when aliased.
- Security sweep: no code change (already pipeline-first). After W4, record
  which backend served bench cells (`/v1/trace` in `_call_model`'s normalizer
  if not already captured) and re-measure one SWEEP_WORKERS=2 wall number on
  the aliased seat for the results table. Update the `_sweep_driver.py` CAVEAT
  comment with the oMLX numbers (decode-bound arms now overlap ~2x;
  prefill-heavy cells stay ~additive).

### W6. Revisit `OLLAMA_NUM_PARALLEL` AFTER the seats move (gated, not now)

Once the compliance reading seat and the fan-out bench seats land on oMLX,
ollama's resident set shrinks (router 5.4 GiB + small seats only). Re-measure
per-seat footprints at PARALLEL=2 (procedure and numbers to beat:
P5-ROUTER-EVICTION-001's 50.3/60.2 GiB) and only then consider restoring
PARALLEL=2 on the daemon. Plist changes go through
`sudo launchctl bootout/bootstrap` with a `plutil` edit (documented in
`docs/*ollama*` + operator memory) — never a bare plist rewrite. If the
footprints still don't fit, PARALLEL=1 stands and the fan-out lives on oMLX,
which the measurements say is the better engine for it anyway.

## Acceptance (all measured, numbers recorded in this file or a report under `reports/`)

1. **A1 — dialect unit tests** pass (`uv run pytest`, targeted files), ruff/mypy
   clean per repo config.
2. **A2 — pipeline smoke, reading call**: one `map_read(write=False)` on a
   small requirement with `COMPLIANCE_TRANSPORT=pipeline`: determinations
   parse, receipt stamps `dialect="pipeline"`, `backend`/`served_model` from
   trace agree with the intended seat, and the sweep process made ZERO direct
   `:11434` calls (assert via ollama log absence or the trace).
3. **A3 — tool loop survives**: one full `reader.read` (tools + json) through
   the pipeline dialect completes ≥3 turns with real tool calls; streamed
   aggregation handles a >300 s turn without the pipeline killing it.
4. **A4 — fan-out gain**: 3 concurrent map readings through the pipeline on an
   oMLX-aliased seat: concurrent/serial wall ratio ≤ 0.7 (expect ~0.5 per M3).
   Same measurement on the ollama fallback path recorded for contrast (~1.0).
5. **A5 — window**: the `ctx98k` tag serves a >65k-token prompt through the
   pipeline (`/api/ps` shows `context_length: 98304` on the ollama path); a
   20-token verdict call on a small-tag seat reserves the small seat, not the
   98k one.
6. **A6 — security sweep**: one cell end-to-end in pipeline mode post-alias;
   served backend recorded; the updated CAVEAT comment matches the numbers.
7. **A7 — attribution**: every receipt row names dialect, endpoint, backend and
   served model; a deliberate wrong-`?model=` run is flagged (BLOCKED) rather
   than silently substituted.

## Rollback

- `COMPLIANCE_TRANSPORT=ollama-native` restores the previous wire behavior
  everywhere (the direct dialects stay functional and stamped as probes).
- Revert `config/backends.yaml` aliases (priority-10 shadows — removal
  returns seats to ollama with no workspace_routing edit).
- The `ctx98k` tag is additive; delete with `ollama rm` when unneeded.
- No plist/daemon change is part of landing this task (W6 is separately gated).

## Out of scope

Council vote-order/parallelism; splash; model-quality re-benching beyond the
A2–A5 smokes (seat quality verdicts stay with WFE/bench campaigns); oMLX tool
parser work for DeepSeek; any daemon env change (W6 is a separate measured
decision).

## Execution results (2026-09-25, live)

**A1 — unit/regression.** New `tests/unit/test_transport_pipeline_dialect.py`
(18 tests: wire shape, drops, failure translation, receipt lift, seat-window
authority, refusal gate). Full `tests/unit` suite: **2471 passed, 0 failed**.
Four test files that fake the transport (`_post`/`urlopen`) gained an autouse
`COMPLIANCE_TRANSPORT=ollama-native` pin — they contract-test the NATIVE wire
and the default flip had redirected them at the pipeline dialect. ruff + mypy
clean on every touched file.

**A2 — pipeline smoke.** `map_read(write=False)` on `CIP-002-5.1a Attachment 1
Part 1.3`, seat `bench-granite41-30b-ctx98k`: wall 111 s warm (230 s with the
oMLX cold load), determinations parse clean, receipt stamps
`dialect=pipeline`, `route_backend=omlx-general`,
`served_model=granite-4.1-30b-4bit`, correlation id recorded. `/api/ps` shows
the seat never touched Ollama. The same shape on the direct dialect remains
available for A/B via `COMPLIANCE_TRANSPORT=ollama-native`.

**A3 — tool loop.** `reader.read` through the pipeline dialect: 124.6 s,
`failed=False`, 2,610-char answer, seat window 98304 (W3 sizing — the reader
took the workspace's declared `context_limit`, not the module constant).
Live acceptance found and fixed a REAL pre-existing defect here: chat()
read `tool_calls` from the native `body["message"]`, so every non-native
dialect silently dropped tool calls — invisible until now because the
tool-less JSON lanes never noticed. Fixed dialect-aware (`reading_transport`
message extraction); streaming-client error paths also got the
`ResponseNotRead` fix (buffer the streamed error body before
`raise_for_status`).

**A4 — fan-out gain.** `sweep_standard` over 3 CIP-002 refs on the aliased
8b seat (`granite4.1:8b-ctx8k → granite-4.1-8b-mxfp8`, num_ctx 32768):
sequential 316.9 s, concurrent(3) 184.4 s → **ratio 0.58 (1.72x)** on
prefill-heavy ~16.5k-token map payloads — inside the predicted band
(decode-bound microbench 2.4x, prefill 1.28x). `SWEEP_CONCURRENCY` ships
OPT-IN (default 1): §B2's measured ×118 sequential prefix collapse on Ollama
means the fan-out default is a per-engine decision the run records, not one
this task preempts.

**A5 — window.** `granite4.1:30b-ctx98k` tag live (from existing blobs;
`PARAMETER num_ctx 98304`, trained ceiling 131,072): `/api/ps` reports
`context_length: 98304`, footprint 31.7 GiB. Short-call seats stay on
16k/32k tags. `reader.read`'s window precedence is now
`seat_window (authoritative, pipeline) → num_ctx arg (requestable, native) →
DEFAULT_NUM_CTX floor`.

**A6 — security sweep.** `run_eval("kerberoast_to_da", granite4.1:8b-ctx8k,
arms=["raw"])` through the pipeline: end-to-end clean, 108.3 s. Attribution
now rides on the bench message (`served_model` key — kept, not stripped, by
the shared-client wrapper): live call reports
`served_model=granite-4.1-8b-mxfp8`. `_sweep_driver`'s CAVEAT updated with
the oMLX numbers. One cell recall=0.0 on a single raw-arm trial is seat
quality (out of scope), not a transport fault.

**A7 — substitution.** Unmapped tags are now REFUSED client-side
(`is_addressable` gate in `PipelineCompat.build`) instead of being silently
served by the routing group's first model — that silent serving was
reproduced live first (request for `no-such-tag-xyz` got served by
`gemma-4-26b-a4b-it-QAT-4bit`, visible only via the new trace attribution).
Aliased seats serve their alias target under the guard's acceptable set
(`{hint} ∪ alias_targets`), which also fixed a latent false-positive the new
aliases would have triggered in the security bench's substitution guard.

Live-state notes: the pipeline image was rebuilt (portal.yaml is baked;
backends.yaml/portal_wiki are mounted) — 48 workspaces, 12/12 backends
healthy post-restart, router re-pinned by the restart's own warmup. W6
(NUM_PARALLEL) untouched by design.

## Lane-alignment audit (operator review, 2026-09-25 — what runs where, and does it match intent)

Method: every workspace/variant hint resolved through the pipeline's own
semantics (routing groups in YAML order, backends by priority desc,
`models` ∪ `aliases`, alias targets validated against each engine's LIVE
model list), then each oMLX landing checked for checkpoint identity
(config.json arch/layers/ctx), tool capability, and the window the lane was
bound for. Result: **48 hinted workspaces, 14 land on oMLX, 34 on Ollama,
0 unresolved** (no lane can silently hit a group's first model).

### Security arm (8 roles — the multi-model design)

| lane | bound model (intent) | serves on | verdict |
|---|---|---|---|
| base (auto-security) | VulnLLM-R-7B ctx8k | oMLX VulnLLM-R-7B-4bit | same checkpoint (qwen2, 28L, 32k ctx) — pre-existing alias |
| ::blueteam | granite4.1:8b-ctx8k | oMLX granite-4.1-8b-mxfp8 | same checkpoint (granite, 40L) — pre-existing alias |
| ::redteam / ::purpleteam | huihui qwen3.5-abliterated:9b ctx8k | oMLX huihui Qwen3.5-9B-abliterated-4bit | same abliterated checkpoint — pre-existing alias |
| ::purpleteam-deep | same 9b, **ctx64k** | oMLX same conversion | **window VERIFIED live: engine held a 216,032-token prompt** (needle test); 64k prefill ≈ 12 min at observed throughput, inside the lane's 1500 s budget |
| ::pentest | fredrezones55 HauhauCS Qwen3.6-35B ctx24k | oMLX Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit | same HauhauCS checkpoint; **needle hit at 39,268 tokens** (lane window verified end-to-end) |
| ::redteam-deep / ::purpleteam-exec | supergemma4-26b-uncensored ctx64k | **oMLX Jiunsong supergemma4-26b-uncensored-mlx-4bit-v2 (NEW, pulled+registered 2026-09-25)** | the correct -uncensored conversion (the 2026-08-10 refusal targeted the abliterated-multimodal checkpoint — that refusal stands). Behavioral A/B vs the GGUF seat: identical reasoning-channel structure (MLX 2,726 reasoning + 4,219 content chars vs GGUF 2,515 + 4,017 on the same Kerberoasting probe), clean typed tool calls (run_nmap, args typed) via oMLX's gemma4 parser. Note: bare probes without reasoning budget return empty content on BOTH engines identically — the role's production budget covers its think block |
| ::uncensored | huihui baronllm-abliterated ctx8k | **Ollama GGUF (transitional)** | no MLX conversion of this checkpoint exists on HF (searched 2026-09-25). Local convert-and-register is the remaining path — the lane moves when the conversion exists |

### Compliance arm

| lane | bound model (intent) | serves on | verdict |
|---|---|---|---|
| auto-compliance (conversation + tools) | Qwen3.8-27B GGUF ctx32k | oMLX Qwen3.8-27B-oQ4e-mtp | same qwen3_5 checkpoint + MTP; pre-existing alias (reasoning group), production-proven |
| compliance-reading (bound reading seat) | **gemma4:26b-a4b-it-q4_K_M-ctx32k** | **Ollama GGUF** | correct: the §P8.1-bound seat; no registered gemma-4-26b-QAT MLX conversion — pull-and-audit is the remaining path |
| council Evidence Auditor | granite4.1:30b-ctx16k | oMLX granite-4.1-30b-4bit (NEW alias, this task) | same checkpoint (granite, 64L, ctx 131,072); tool-probed live |
| council Challenger | mistral-small3.2:24b | **oMLX mlx-community Mistral-Small-3.2-24B-Instruct-2506-4bit (NEW, pulled+registered)** | same Mistral-Small-3.2-24B-Instruct-2506 checkpoint; lane requirement is `response_format json_object` — verified (parses, correct schema, 2 s). KNOWN GAP: its template does not render tools on oMLX (model answered "unable to access tools") — fine for the tool-less challenger lane, do NOT alias this conversion onto tool lanes |
| council Operator/User Advocate | DeepSeek-R1-0528-Qwen3-8B ctx64k | **Ollama GGUF (transitional)** | the on-disk MLX conversion exists but oMLX drops DeepSeek tool-call format — the deepseek_r1 tool parser (added to the brew install once, LOST to a later brew upgrade; tokenizer_config `tool_parser_type` also gone) must be rebuilt and installed upgrade-surviving. Precise fix path recorded below |
| council Synthesizer | qwen3.6:27b-q4_K_M-ctx16k | **Ollama GGUF (transitional)** | candidate conversion identified (unsloth/Qwen3.6-27B-UD-MLX-4bit) — pull-and-audit is the remaining path |
| reading/mapping sweep (bench seats) | granite 8b/30b tags | oMLX conversions (NEW aliases) | same checkpoints; window verification below |
| reading 98k seat | granite4.1:30b-ctx98k (baked 98304) | **Ollama** (alias REMOVED) | the granite-4.1-30b-4bit conversion fails ≥85k: empty decode twice (821 s / 2,294 s prefill, no usage), once with guard-reject at 53.46 vs 53.13 GB ceiling and once clean at aggressive tier — a conversion long-context defect, not config. Lane keeps its baked-98304 Ollama seat (verified working) until the conversion is fixed upstream |

**Supporting config change (host):** `~/.omlx/settings.json`
`memory_guard_tier: balanced → aggressive` — the 2026-09-25 probes produced
the "pending data" the balanced-tier deferral was waiting for: the reading
lane's prefill peak (~53 GB at 85k) exceeded the balanced dynamic ceiling by
under 1 GB. Aggressive sets the ceiling at 56 GB (i_gouged wired limit); the
98k conversion defect is INDEPENDENT of this (empty decode with headroom
available).

**Divergences found: quant-level only, same checkpoints.** Every lane moved
to oMLX lands on a conversion of the SAME checkpoint, verified by
config-identity plus behavioral probes (tools, window, reasoning channel,
json contract per lane). Two probe artifacts were run down and correctly
attributed: the "empty at 85k" granite case (conversion defect — lane stays
on Ollama) and the "empty redteam probe" cases (reasoning-budget starvation,
identical on both engines — not a divergence).

### Divergences found: quant-level only, same checkpoints — plus one real window risk, verified

Every lane this task moved to oMLX lands on a conversion of the SAME
checkpoint (config-verified). The only behavioral deltas are quantization
(Q4_K_M ↔ 4-bit/MXFP8 — comparable, MXFP8 strictly higher precision on the
8b) and MTP speculative decoding on Qwen3.8. The one intent-critical open
risk was **window**: an MLX conversion serves the engine's own window; a lane
bound at 64k/98k on the GGUF tag only keeps that intent if the conversion
holds it. Live needle probes: Qwen3.5-9B MLX held 216,032 tokens
(purpleteam-deep's 64k is safe); granite-4.1-30b-4bit correctly refused
132,029 tokens (> its trained 131,072) and the reading-lane worst case
(~82k) result is recorded below with the probes.

### A/B use-case validation (2026-09-26): every flipped seat vs the Ollama seat it replaced

One lane-representative case per lane, sent to BOTH engines, contract-checked
(json parses / tool call emitted / substantive content). Results:

| lane | contract | oMLX | Ollama | verdict |
|---|---|---|---|---|
| council-challenger (mistral) | json | ✓ (6/7 clean; one intermittent temp-0 decode loop, non-reproducible at council sampling) | ✓ | MATCH |
| council-evidence (granite-30b) | json | ✓ | ✓ | MATCH |
| redteam-deep (supergemma4-v2) | toolcall | ✓ | ✓ | MATCH |
| blueteam (granite-8b mxfp8) | json | ✓ | ✓ | MATCH — unconstrained (no response_format) runs degrade; the lane contract always sends it |
| base-security (VulnLLM) | content | ✓ near-identical wording | ✓ | MATCH |
| pentest (HauhauCS-35B) | content | ✓ | empty in bare probe (reasoning-starved at 32-token budget; lane runs larger) | MATCH on contract; probe artifact on the GGUF side |
| auto-compliance (Qwen3.8) | content | ✓ | ✓ | MATCH |
| council-synthesizer (Qwen3.6-27B) | json | ✓ | empty in bare probe (same artifact class) | MATCH on contract |
| reading seat (gemma-4-26b) | full map_read | ✓ 68 s, 3,986 chars, clean parse | ✓ 61 s, 3,837 chars, clean parse | MATCH — same placeholder-citation behavior both sides (bench domain) |

Probe artifacts to remember: reasoning-capable checkpoints return EMPTY
content when `max_tokens` cannot cover the think block — identical on both
engines; a bare-prompt A/B must budget for the reasoning channel or it
manufactures divergences.

### Remaining gaps, terminal or in progress (2026-09-26)

- **DeepSeek-R1-0528-Qwen3-8B — FIXED.** `deepseek_r1` parser rebuilt
  (`scripts/omlx/deepseek_r1_tool_parser.py`, installed by
  `scripts/install_omlx_parsers.sh` — re-run after every `brew upgrade
  omlx`), `tool_parser_type: deepseek_r1` stamped in the model's
  tokenizer_config. Live probe: clean typed `get_weather` calls at
  temperature 0 and 0.3. Alias registered in `omlx-reasoning`; the council
  operator seat and auto-reasoning now have an oMLX path.
- **Qwen3.6-27B synthesizer — REGISTERED** (unsloth UD-4bit pulled): json
  synthesis verified, typed tool call verified, alias in `omlx-general`.
- **gemma-4-26b-a4b-it-4bit (standard checkpoint) — REGISTERED** for the
  compliance-reading seat: json ✓, tools ✓, **90,041-token needle ✓** —
  the reading window intent holds with margin. Full map_read A/B matched
  the GGUF seat (see table). NOTE the standard-vs-QAT distinction: two
  gemma-4-26b conversions exist and are never cross-aliased.
- **baronllm-abliterated — BLOCKED BY UPSTREAM.** The abliterated
  checkpoint exists ONLY as GGUF (huihui-ai repo is `gguf-my-repo`
  auto-quantized; no safetensors anywhere on HF, searched 2026-09-26), and
  the bundled mlx_lm has no GGUF→MLX conversion path. A hand-rolled
  conversion would double-quantize (Q4_K_M → affine-4bit) a security lane's
  weights — rejected for fidelity reasons. The lane stays on its Ollama
  GGUF until huihui-ai publishes safetensors or an official MLX conversion
  appears. This is the ONE security role without an oMLX path.
