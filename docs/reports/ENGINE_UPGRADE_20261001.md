# Engine upgrade — Ollama 0.35.0, oMLX 0.7.0 (2026-10-01)

Both engines moved to the latest **stable** release (no RCs) and were tested
through the pipeline. Gate: `scripts/engine_contract_check.py` (both pass).

## Outcome

| Engine | From → to | Verdict |
|---|---|---|
| Ollama | 0.34.4 → 0.35.0 | adopted; seat A/B identical within noise |
| oMLX | 0.6.4 → 0.7.0 | adopted; seat A/B at least as good; needs `aggressive` tier for REAP-288 only |

## What the first oMLX attempt got wrong (and why it was rolled back)

The autoupdater's contract probe rejected 0.7.0 twice over. Both were probe
fragility, not engine bugs:

- `presence_penalty`: still honoured, but 0.7.0 corrected Qwen3.5/3.6 GDN numerics, so the
  probe prompt's greedy output shifted and a 2.0 penalty no longer flips it (it needs 10.0 there;
  0.6.4 flipped at 1.0). Probe now escalates 2.0 / 5.0 / 10.0.
- `think:true`: the model needs slightly more than the old 600-token cap to finish thinking.
  A response cut off mid-thought leaks thinking into `content` on **both** versions (the
  Qwen3.5 template prefills `<think>`, so no tag is left to split on). Probe cap is now 2000.

## Real finding: pipeline tool_call deltas had no `index`

oMLX 0.7.0 returns parallel tool calls for Qwen3-Coder. The pipeline re-streamed them
(`router/streaming.py`, buffered-completion and client-tools passthrough paths) with no `index`,
so OpenAI-style clients merged them (`file_writefile_writepytest_run`). Smoke: 0.6.4 PASS 2/2,
0.7.0 FAIL 4/4 before the fix, PASS 3/3 after. Affects clients that bring their own tools
(IDE lanes, the WFE harness), not Open WebUI.

## Seat A/B (pipeline, n=3, same seats/models, only the engine differs)

oMLX (42 rows per arm): Laguna-XS-2.1 22 → 27 PASS; Qwen3-Coder-30B 17 → 21 PASS
(`code-kv` fails on both versions).

Ollama (36 rows per version): gemma4-e4b 9/9 → 9/9; Nex-N2-mini 9/9 → 9/9;
KAT-coder 8/9 → 8/9; omnicoder2 9/9 → 8/9 (one budget-exhausted row, noise at n=3).

Plans: `tests/wfe/plans/engine_ab_omlx.yaml`, `engine_ab_ollama.yaml`.

## Memory guard (oMLX 0.7.0 rebuilt it)

`ceiling = min(static, dynamic, metal_cap)`; `dynamic = oMLX resident + free + inactive − tier reserve`.
Tier reserve on this 64GB Mac: safe 12.8 GiB, balanced 5.1, aggressive 1.5.
Measured with the stack up: balanced 40.5 GiB, aggressive 48.7 GiB (Metal cap 56.1).

REAP-288 (IDE only, stack down), measured:

| Tier | Result |
|---|---|
| balanced | rejected: prefill peak ~39.97 GB vs dynamic ceiling 39.81 GB, even for a one-word prompt |
| aggressive | loads; a 15.3K-token prefill served at 29.8 tok/s |

Decision: daily operation stays `balanced` (largest regular oMLX models are far below 40 GiB);
`./launch.sh coder-reap288` sets `aggressive` (`scripts/omlx_memory_tier.py`) and
`./launch.sh up` restores `balanced`. The 56GB `wired_limit` is unchanged.

## Lightning MTP on 0.7.0

Native (`omlx.patches.mlx_lm_mtp`, 93–98% draft acceptance); no MTPLX side-car process runs.

| Model | tok/s (0.7.0) | Reference |
|---|---|---|
| Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp | 90 | 70 on 0.6.x, 53 on Ollama |
| Qwen3.8-27B-oQ4e-mtp | 42 | 6.8–9.5 on Ollama |

## Seats exercised through the pipeline

12 seats answered correctly with no leaked thinking (security redteam/purpleteam/pentest/blueteam/base,
nemotron, reasoning::deep, documents, research, data, vision, general-uncensored). `auto-compliance`
is served by `Qwen3.8-27B-oQ4e-mtp` and passed its WFE smoke.

## Follow-up verification (2026-10-01, later run)

**Memory tier, REAP-288, stack down (re-measured).** Short prompt: `balanced` loads and answers.
A 14.3K-token prefill under `balanced` is aborted mid-prefill (usage 44.8 GB vs hard watermark
44.7 GB, dynamic ceiling 47.1 GB). Under `aggressive` a 22.4K-token prefill is served (101.7 s).
Live ceilings with the stack up and nothing loaded: safe 34.1, balanced 41.7, aggressive 51.5 GiB
(Metal cap 56.1, so `aggressive` stays under it). Decision unchanged: `balanced` daily, `aggressive`
only for the REAP session. The regular oMLX models (16-18 GB) never hit a guard refusal in any
0.7.0 campaign.

**Concurrency (Nemotron-3.5-Lightning, 200-token completions, direct to oMLX).** Aggregate
tok/s at 1/2/4/8 requests in flight: 78.5 / 107.9 / 144.5 / 158.0. Nemotron's Lightning MTP is
single-request only (log: "MTP inactive for 2-row batch"), so multi-request scaling there is plain
batching. The live `max_concurrent_requests` change (`apply_max_concurrent_requests`) exists in
0.7.0 but was not exercised (admin API needs auth); production keeps `max_concurrent_requests: 8`.

**MTPLX side-car: not needed.** No MTPLX process runs; the `-oQ4e-mtp` checkpoints are served by
oMLX's native Lightning MTP. Remaining "MTPLX" mentions are historical comments and the
checkpoint format name.

**Compliance seats (through the pipeline, `auto-compliance` served by Qwen3.8-27B-oQ4e-mtp,
22 rows = 11 tasks x 2).**

| oMLX | PASS | BUDGET_EXHAUSTED | FAIL | REFUSED | HARNESS_ERROR | wall |
|---|---|---|---|---|---|---|
| 0.6.4 | 13 | 5 | 1 | 3 | 0 | 3152 s |
| 0.7.0 | 12 | 8 | 1 | 0 | 1 | 1209 s |

Equivalent within noise at n=2, and 2.6x faster wall time on 0.7.0. The one HARNESS_ERROR is the
harness's own contamination check on `comp-p6j-14` (answer key in tool output), a task issue.
`comp-reading-contract-01` exhausts its budget on both versions. Plan:
`tests/wfe/plans/engine_ab_compliance.yaml`.

`compliance-reading` (Ollama gemma4), `compliance-mapping` and `auto-compliance` each answered a
CIP-007-6 R2 control question correctly (35 calendar days, Part 2.2) with no leaked thinking.

## Open WebUI end to end

Signed in with the `.env` admin account (279 models visible) and streamed three workspaces
through Open WebUI -> pipeline -> engine: `auto-coding` (9.0 s), `compliance-reading` (16.9 s,
correct 35-day answer with quoted sources), `auto-general-uncensored` (14.0 s). No leaked thinking.

## oMLX API key (pipeline wired)

oMLX now requires a key (`auth.api_key` in `~/.omlx/settings.json`, mirrored as `OMLX_API_KEY` in
`.env`; `.env.example` documents it, empty = keyless). Unauthenticated `/v1/models` returns 401;
`/health` stays open. `portal/platform/inference/omlx_auth.py` adds the Bearer token to requests
bound for oMLX only (never Ollama or the MCP servers): the pipeline's shared client, the health
client and backend introspection, the host-side security chain, the WFE `omlx` engine mode, the
contract check, `check_model_bindings`, the watchdog, `launch.sh status` and `coder-reap288`
(including the generated opencode config). Compose passes `OMLX_API_KEY` to the pipeline container.

Verified with the key enforced: 12/12 backends healthy, `smoke_stream.sh` PASS, both contract
checks pass, Qwen3-Coder and Laguna smokes PASS through the pipeline, `auto-compliance` and
`auto-security::redteam` answer, status row healthy, watchdog probe authenticated.

**Live concurrency change (now tested).** Admin login works with the key. `POST
/admin/api/global-settings {max_concurrent_requests: 4}` applied at runtime in 0.01 s: same
process, same resident model (22.9 GB), no unload. 8 requests in flight at limit 4 vs 8 gave
77-148 tok/s with no consistent difference (the first runs after a change are the slow ones), so
production stays at 8; the setting was restored to 8 and persisted.

## Bench and UAT tooling

Direct-oMLX callers now authenticate as well: the oMLX bench scripts (v3, concurrency, daily
soak), `settings_audit`, `omlx_chat_template_patch`, the `prove_then_scale` tool probe and the UAT
monitor. Checked against the secured server: `/v1/models` and `/v1/models/status` answer 200
when authenticated and 401 when not. The UAT harness itself drives the pipeline (already keyed) and only reads oMLX `/health`, which stays open.

## Not tested

Full bench runs on the new key path (only the call sites were exercised).
