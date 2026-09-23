# MiMo-V2.6-Distill-Qwen-9B — Bring-up & Bench (2026-09-21)

**Status: candidate only.** Not wired into `config/portal.yaml`, `config/backends.yaml`, or any persona YAML. Promotion to a live `model_hint` is a separate operator task.

## What it is

`XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B` — Qwen3.5-9B base, SFT'd on 77.4B tokens across Code (23.2B) / Cyber (11.0B) / General (22.0B) / Visual (21.2B). Architecture: `Qwen3_5ForConditionalGeneration`, hybrid linear/full attention, 262144 native `max_position_embeddings`, no rope_scaling needed.

Model-card claims: SWE Verified 60.0→61.1, SWE Pro 32.0→44.6, AutomationBench 5.0→30.3, Terminal Bench 27.0→37.1, MiMo Cyber 5.7→31.3 (base→this SFT).

## Pull & tag

`ollama pull hf.co/bartowski/...` hit a known Ollama xet-CDN redirect bug (`blocked redirect to a different host` on HF's `us.aws.cdn.hf.co` xet-bridge URL). Worked around by downloading the GGUF directly via `hf download bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF MiMo-V2.6-Distill-Qwen-9B-Q4_K_M.gguf` (5.84GB) and importing via local `ollama create` with a Modelfile — not an Ollama-library fallback, still the bartowski Q4_K_M GGUF, just fetched by a different client.

Final tag: **`portal5/mimo-v26-distill-9b:q4_K_M-ctx256k`**

Baked `PARAMETER num_ctx 262144` (full native context) — precedent already exists in this fleet for a same-size model (`portal5/omnicoder2-9b:q4_K_M-ctx256k`), and hybrid linear/full attention keeps KV-cache growth far cheaper than a dense-attention model at this context. Confirmed empirically: resident footprint at full 262144 ctx is **11GB, 100% GPU** — cheap.

## Template/config verification (source vs. harness — not just trusted)

Per this fleet's standing rule (thinking models silently opening `<think>` by default, and the command-r tool-envelope bug, are both prior production incidents that trace back to trusting a harness's guessed default over the model's real source config), the bartowski GGUF's baked-in template was diffed against XiaomiMiMo's own source repo, not assumed:

- **Tool-call wrapper**: source `chat_template.jinja` renders `<tool_call><function=NAME><parameter=K>V</parameter></function></tool_call>` — byte-identical to what `ollama show <tag> --template` baked in. No mismatch.
- **Thinking control**: source template gates on `{%- if enable_thinking is false -%}` (README confirms `chat_template_kwargs: {"enable_thinking": true/false}`), matching the baked template exactly. Ollama's own `think:false` request param maps onto this correctly — verified live (see probes below).
- **EOS/stop**: source `tokenizer_config.json` sets `eos_token: "<|im_end|>"`, matching the baked template's turn-closing token. No mismatch.
- **Verdict: bartowski's GGUF embeds the real source template, not a generic/fallback one.** No Modelfile fix was needed.

## Live probes

**Tool-call probe** (direct `/api/chat` with a `get_weather` tool definition):
```json
{"tool_calls":[{"function":{"name":"get_weather","arguments":{"city":"Boston"}}}]}
```
Clean, correctly-typed arguments, reasoning routed to `thinking` field (not leaked into `content`). **`supports_tools:true` confirmed by probe**, not inferred from arch.

**Thinking-suppression probe** (`think:false`, `"2+2=?"`): returned bare `"4"`, no `<think>` leakage. Confirmed.

**Cold load**: 1.36s (first smoke request, clean system state).

## Bench — clean, isolated numbers only

A head-to-head coding-lane comparison against the auto-coding incumbent (Laguna-XS.2) was attempted and **invalidated by a system-level confound, not a model problem**: the box was under heavy swap pressure (~22GB swap in use, physical free memory near zero) during the Laguna run, likely compounded by an operator error mid-session (a second request was fired at a different model before the first Laguna request had actually completed, deadlocking Ollama's model-swap logic in a `Stopping...` state for ~10+ minutes until the stale client was killed). **The Laguna timing/correctness data from that run is discarded — not reported as real.** The failure was two requests in flight at once, not the models failing to fit together — see the head-to-head test plan below. (Correction 2026-09-23: Laguna-XS.2 is not the `auto-coding` incumbent. `auto-coding`'s `model_hint` is `qwen3-coder:30b-a3b-q4_K_M-ctx256k`; Laguna is the `auto-coding` `laguna` variant — the agentic/opencode default.)

What follows are clean, isolated, single-model numbers for MiMo alone (no other model resident, no swap pressure):

| Probe | Result | eval tok/s | eval tokens | prompt eval | notes |
|---|---|---|---|---|---|
| Coding: batch-processing off-by-one bug | **Correct fix** (`items[i:i+batch_size]`) | 36.0 tok/s | 51 | 0.46s / 141 tok | clean, isolated |
| Security: open-redirect classification | **Correct** — CWE-601, High/7.1-8.0 CVSS w/ sound justification, working allowlist mitigation | 35.8 tok/s | 529 | 0.35s / 80 tok | clean, isolated |

Both correctness results are qualitatively strong for a 9B model — the CWE identification, CVSS band reasoning, and mitigation code in the security probe would not look out of place from a much larger model. Decode speed (~36 tok/s) is consistent across both tasks regardless of output length, as expected for a dense-attention decode workload at this size on this hardware.

**Coding-lane and security-lane head-to-head comparisons against the seated incumbents (Laguna-XS.2 for agentic coding via the `laguna` variant; VulnLLM-R-7B for `auto-security`) are NOT validly measured yet** — only MiMo's own standalone numbers are trustworthy from this session. Don't cite this doc as "MiMo beats/loses to X" on speed or quality; it only supports "MiMo works correctly and performs reasonably in isolation."

## Footprint

- Disk: 5.84GB (Q4_K_M GGUF)
- Resident: 11GB at full 262144 ctx, 100% GPU
- Cheap enough to coexist with most of this fleet's other seated models on 64GB unified memory (compare: Laguna-XS.2 — the `laguna` variant — is ~23GB resident at its 131072 ctx tag `portal5/laguna-xs2:q4_K_M-ctx128k`)

## Recommendation

**PROMOTE_POLICY=confirm** for candidate-pool inclusion (matching the existing BENCH-GATED PROVISIONAL pattern used for kat-coder-v2.5-dev / orcarouter Qwen3.8-27B-Uncensored) — the correctness signal (clean tool-calls, correct bug fix, correct CWE/CVSS reasoning) and the cheap footprint (11GB vs 17-25GB for the current small-candidate pool) justify a place in the pool alongside the other unpromoted coding/security candidates. **Do not promote to a live model_hint or claim a win over Laguna-XS.2 / VulnLLM-R-7B** — that requires a valid head-to-head, which this session did not get. Next step: run the head-to-head test plan below.

## Head-to-head test plan (V2, 2026-09-23 — supersedes "stack quiesced, one model at a time")

**Operating condition: production-like — Docker stack UP.** Stopping the stack was the wrong precondition. A 9B that takes 11GB at full 262k ctx has to be judged under the conditions it would serve in, and the pair fits beside the stack anyway (table below). What the harness *does* clear before each measurement is other **models** — Ollama residents and whatever oMLX holds — never services, so each number describes one engine × one model rather than the other things loaded. Co-residency in production is checked separately, by the promotion gate's live-stack check.

| Resident | GB |
|---|---|
| MiMo 9B @ 262144 ctx | ~11 |
| Laguna-XS.2 @ 131072 ctx | ~23 |
| Docker stack + VM | ~9 |
| gemma-4-E4B router (keep_alive forever) | 5.5 |
| **Total** | **~49** — under the 57344 MB `iogpu.wired_limit_mb` |

Laguna is the memory risk (23GB); MiMo is not. The rules below are about Laguna and about concurrent requests, not about stopping the stack.

### Rules (all runs)

1. **One request in flight, ever.** This is what broke the 2026-09-21 run: a second request went to a different model while a Laguna request was still running, and Ollama deadlocked in `Stopping...`. The harness is strictly sequential and takes a lock (`/tmp/portal5_engine_h2h.lock`), so a second harness process fails fast. Don't send any manual or other traffic to any engine while it runs. `OLLAMA_NUM_PARALLEL=4` doesn't protect against this.
2. **Don't use `scripts/wfe_sweep_unattended.sh`.** Its precondition takes the stack down. Call `tests/wfe/campaign.py` directly, one arm per process.
3. **Swap baseline before starting.** `speed` and `security` refuse to start while swap is over 50% full. **On 2026-09-23 it was 19.5/20GB (95%) with only the router loaded**, and `doctor` reports BLOCKED. Clear it before the run: a reboot, or Ollama/oMLX restarts via their clean paths (never `kill -9`).
4. **Validity guard.** During every `speed`/`security` run the harness samples `vm.swapusage` and, for Ollama, `/api/ps` every 30s. A row is **INVALID**, gets re-run and is never reported, if either happens:
   - swap grows >2GB during it
   - the Ollama arm shows any CPU split (`size_vram < size`)
5. **Laguna runs from its real tag** `portal5/laguna-xs2:q4_K_M-ctx128k` — not `laguna-xs.2:Q4_K_M` (default ctx) or `-ctx64k`.

### Tooling — built and validated 2026-09-23 (the delegate runs it; nothing left to write)

| Piece | Path | What it does |
|---|---|---|
| Harness | `tests/benchmarks/bench_engine_h2h.py` | `doctor`, `fetch-drafters`, `build-prefill`, `commands`, `switch`, `preflight`, `speed`, `security`, `stop`, `summarize` |
| Registry | `tests/benchmarks/engine_h2h.yaml` | engines (ports, exact launch argv for plain/spec, stop signal) and models (Ollama tag, MLX dir, ctx, tool parser, spec cell per engine) |
| Security prompts | `tests/benchmarks/fixtures/engine_h2h/security_prompts.json` | the 6 fixed prompts (5 CWE + 1 clean control) |
| Prefill prompts | `tests/benchmarks/fixtures/engine_h2h/prefill_{20000,6000}.txt` | byte-identical real-repo prefill text for every engine (6000 for VulnLLM's 8k window) |
| WFE plans | `tests/wfe/plans/mimo_h2h_ollama.yaml`, `mimo_h2h_mlx.yaml` | coding-lane arms (Ollama tags / MLX served names) |
| WFE engine mode | `tests/wfe/runner.py` `ENGINE`/`CHAT_BASE`, `campaign.py`, `schema.py` | `WFE_ENGINE=<name> WFE_CHAT_BASE_URL=<base>` runs any WFE campaign against an OpenAI-compatible engine. Ollama stays the model manager, so draining it frees memory for the engine under test. Preflight runs on `/v1` only; thinking goes through `chat_template_kwargs.enable_thinking`; the engine is stamped into the fingerprint so it can't be mixed with Ollama rows. Default (unset) behaviour is byte-identical to before. |
| Tests | `tests/unit/test_bench_engine_h2h.py`, `tests/wfe/tests/test_wfe_contracts.py` (engine-mode cases) | pure-logic contracts; no network |

**Already done on this host:**
- Rapid-MLX 0.15.0 installed as a uv tool with the `[dflash]` extra; `--no-telemetry` verified to block upload.
- vllm-mlx 0.5.0 runs through `uvx --from vllm-mlx==0.5.0`, because Rapid-MLX is a vllm-mlx fork and installs its own `vllm-mlx` executables.
- MiMo MLX builds are in `/Volumes/data01/omlx-models`:
  - `MiMo-V2.6-Distill-Qwen-9B-MLX-4bit` (nativ-community, 5.6GB) is the shared plain build
  - `…-MLX-Serve-4bit-mtp` (ddalcu, 7.1GB) ships `model-mtp.safetensors`, Qwen3.5's MTP head, and is the spec build
- oMLX was restarted and lists both MiMo builds.
- Drafters are in `/Volumes/data01/engine_h2h_drafters`, outside oMLX's discovery dir:
  - `Laguna-XS.2-speculator.dflash`
  - `Qwen2.5-0.5B-Instruct-4bit`
- **Every plain launch command was smoke-tested** on `VulnLLM-R-7B-4bit`: served id, `OK` reply, clean `get_weather` tool call, clean stop. The full harness path (`switch` → `preflight` → speed → security → guard → `stop`) and one WFE engine-mode task ran end to end against mlx-serve. Those were validation runs, moved out of the results dir, not results.

**Facts found while building (these change the earlier plan text):**
- **mlx-serve runs speculative decoding by default.** Prompt-lookup decoding (PLD) is on unless disabled, and it auto-loads an MTP head or `drafter/` subdir. Plain mode passes `--no-pld --no-drafter --no-mtp`. Its spec mode for VulnLLM is just its default PLD.
- **Poolside's Laguna drafter is `speculators` format.** It has `aux_hidden_state_layer_ids` and a reduced `draft_vocab_size` of 32000. That is not the z-lab DFlash layout (`dflash_config.target_layer_ids`) that mlx-serve and Rapid-MLX auto-detect. Expect the Laguna spec cells to fail to load. Record "engine unsupported" and move on; a success is the headline.
- **oMLX supports DFlash and MTP per model** (`dflash_enabled`/`dflash_draft_model`, `mtp_enabled` in `~/.omlx/model_settings.json`; Qwen3.8-27B already uses DFlash). Its admin API needs an API key this host doesn't set, and setting one would also gate the `/v1` path the pipeline uses. So `switch --engine omlx` edits the settings file instead: it writes a timestamped `.h2hbak` backup first, touches only the spec keys for the model under test, then restarts the launchd service `homebrew.mxcl.omlx`. `switch` also restarts oMLX before every *other* engine, to release what it holds (it held 18GB on 2026-09-23).
- **vllm-mlx 0.5.0 has no `--moe-top-k` flag**, despite its README. It isn't in the CLI, so there's no MoE-tuning row. It has no DFlash either: its spec cells are MTP (MiMo) or null.
- **mlx_lm.server lists the whole HF cache on `/v1/models` and ignores SIGINT.** The harness launches it from the model root with a relative `--model`, so its id matches the other engines, and stops it with SIGTERM.
- **Spec runs for MiMo use the `-mtp` build**, so the served id in spec rows is that directory name. WFE MLX plan arms are the plain builds; spec is a speed-lane measurement only.
- **The WFE persona resolver maps `auto-security` to `adversarysimulator`.** That is the wrong framing for CWE review, so the security lane uses the workspace's own `owui_system_prompt` and sampling (temperature 0.3, top_p 0.9; top_k/min_p/repeat_penalty aren't portable across engines' /v1, so they aren't sent to any of them).
- **The clean control works.** In validation VulnLLM invented four CWEs for the clean scrypt snippet — a false positive the scoring caught.

### Run order

```bash
H="uv run python tests/benchmarks/bench_engine_h2h.py"
$H doctor                 # every line OK; swap gate not BLOCKED (rule 3)
$H commands               # the exact argv every managed engine will get

# Engine × model × mode, one cell at a time. ENGINES: ollama omlx mlx-serve rapid-mlx vllm-mlx mlx_lm.server
# MODELS: mimo laguna vulnllm. MODES: plain, then spec where the registry has a cell (ollama is plain only).
$H switch    --engine E --model M --mode plain   # stops managed engines, evicts Ollama, restarts oMLX, starts E
$H preflight --engine E --model M --mode plain   # served id, think-off "OK", tool call, template diff vs source → OK/REVIEW
$H speed     --engine E --model M --mode plain   # cold first request, 3× decode (400 tok), 3× nonce-prefixed prefill, resident GB
$H security  --engine E --model M --mode plain --repeats 3   # only for mimo + vulnllm (the security pair)
# ...repeat for --mode spec where available, then the next engine/model
$H stop --engine E        # after the last managed cell
$H summarize              # per-model markdown table from tests/benchmarks/results/engine_h2h/<model>.jsonl
```

- Order within a model: Laguna's spec cells first (the drafter question decides whether the rest matters most), then plain everywhere, then the remaining spec cells.
- Every row carries the engine version, the exact launch argv, the log path, the guard verdict and `valid`. Engine startup logs go in `results/engine_h2h/logs/`; read them for kernel path (`gdn`, fused MoE) and speculative acceptance rate, and put both in the report.
- A `preflight` REVIEW means that cell's speed numbers aren't reported until it's fixed or marked "engine unsupported".
- Restore oMLX's settings at the end: `switch --engine omlx --model <m> --mode plain` clears the spec keys it set, and the `.h2hbak` files hold every prior state.

### Coding lane — MiMo vs Laguna-XS.2 (WFE `coding` suite, agentic)

WFE resolves prompt + sampling from the workspace (`tests/wfe/runner.py` `workspace_context`), not variants. Both arms therefore run under `auto-coding`'s base config. That keeps the comparison fair between the two arms, but it is not the `laguna` variant's own sampling. Say so in the result. Each arm has 14 tasks (3 coding + 11 compliance_agentic discovery); n=3 is 42 runs per arm.

```bash
# Ollama (production engine)
C=wfe_mimo_h2h_$(date +%Y%m%d); P=tests/wfe/plans/mimo_h2h_ollama.yaml
uv run python -m tests.wfe.campaign --plan $P --campaign-id $C --preflight
uv run python -m tests.wfe.campaign --plan $P --campaign-id $C --arm portal5/laguna-xs2:q4_K_M-ctx128k --repeats 3
uv run python -m tests.wfe.campaign --plan $P --campaign-id $C --arm portal5/mimo-v26-distill-9b:q4_K_M-ctx256k --repeats 3

# Any MLX engine: after `bench_engine_h2h.py switch --engine E --model <m> --mode plain`, one campaign per engine
P=tests/wfe/plans/mimo_h2h_mlx.yaml
WFE_ENGINE=E WFE_CHAT_BASE_URL=http://127.0.0.1:<port> \
  uv run python -m tests.wfe.campaign --plan $P --campaign-id ${C}_E --arm MiMo-V2.6-Distill-Qwen-9B-MLX-4bit --repeats 3
```

- Ports: oMLX 8085, mlx-serve 11234, Rapid-MLX 11235, vllm-mlx 11236, mlx_lm.server 11237.
- The full n=3 suite on an MLX engine is only worth running on the engine that wins the speed lane for that model.
- Arms run strictly one after the other (rule 1). `campaign.py` drains Ollama per arm; that's expected and doesn't need the stack down.
- Report pass rate per task, wall time per run, turns used and decode tok/s. Include the discovery rows.

### Security lane — MiMo vs VulnLLM-R-7B (`auto-security`)

`bench_engine_h2h.py security` sends the 6 fixed prompts (all 6 on one model, n=3 each, never interleaved). Both models get the same:
- system prompt: `auto-security`'s `owui_system_prompt`
- sampling: temperature 0.3, top_p 0.9
- thinking off
- seed per repeat

Prompts:
1. open redirect → CWE-601
2. SQL injection via string-formatted query → CWE-89
3. path traversal in a download handler → CWE-22
4. hard-coded credential → CWE-798
5. `pickle.loads` on a request body → CWE-502
6. **clean** scrypt/`hmac.compare_digest` snippet → must answer `NO VULNERABILITY FOUND` with no CWE

Scoring:
- **Automatic:** `cwe_ok` (expected CWE named) and `false_positive` (any CWE, or no `NO VULNERABILITY FOUND`, on #6).
- **Operator:** `cvss_ok` and `mitigation_ok` are left null in each row for you to grade from the saved `response`.

### Engine lane — Ollama vs oMLX vs mlx-serve vs Rapid-MLX vs vllm-mlx vs mlx_lm.server, per model

Goal: for each model, find out which engine on this host is fastest. Each model runs on every engine that has a usable 4-bit build of it.

| Engine | Endpoint | Notes |
|---|---|---|
| **Ollama** | `:11434` | production chat tier (GGUF Q4_K_M); plain only |
| **oMLX** | `:8085` | already wired in `config/backends.yaml` (`omlx-local`, coding shadow group); spec via `model_settings.json` |
| **mlx-serve** 26.9.2 | `:11234` | spec = MTP head / DFlash `--drafter` / PLD |
| **Rapid-MLX** 0.15.0 | `:11235` | vllm-mlx fork; spec via `--speculative-config` (mtp / dflash / suffix); telemetry killed with `--no-telemetry` |
| **vllm-mlx** 0.5.0 | `:11236` | upstream, via uvx; spec = `--enable-mtp` only |
| **mlx_lm.server** 0.31.3 | `:11237` | reference baseline; spec = classic `--draft-model` |

**Spec cell per model** (registry `models.<m>.spec`; null = no spec path, report as such):

| | mlx-serve | Rapid-MLX | vllm-mlx | oMLX | mlx_lm.server |
|---|---|---|---|---|---|
| MiMo | MTP (`-mtp` build) | MTP | MTP | MTP | — |
| Laguna | DFlash (Poolside drafter) | DFlash (Poolside drafter) | — | DFlash (Poolside drafter) | — |
| VulnLLM | PLD | suffix | — | — | draft model (Qwen2.5-0.5B) |

**One MLX build per model, shared by every MLX engine**, from the same directory under `/Volumes/data01/omlx-models`, so the comparison is between engines, not builds. 4-bit only, to match Q4_K_M. The spec build for MiMo is the one exception, because the plain build has no MTP head.

- **Context parity:** every engine runs at the Ollama tag's context (262144 / 131072 / 8192) where the engine takes a flag (mlx-serve `--ctx-size`); the others take the model's own window, recorded in the row.
- **Arch support:** if an engine fails to load a model or produces garbage, record **"engine unsupported"** for that cell and continue. Don't patch around it.
- **Measurement notes:** the prefill prompt is prefixed with a fresh nonce every round, which defeats every engine's prefix, radix and SSD cache, so each round is a real cold prefill of identical length. "Cold" is the first short request after `switch`. On Ollama it includes the model load; managed engines load at startup, and the row's `launch_ready_s` holds that. 4-concurrent throughput is out of scope: Portal is single-user.
- **Speculative decoding and kernels are where MLX speed comes from.** Speculative decoding helps less at 4-bit than at 8-bit (mlx-dspark: 2.30× vs 3.63× on the same model), so measure it rather than assume the published multiplier. [`mlx-dspark`](https://github.com/ARahim3/mlx-dspark) supports none of the three models. Revisit it for Qwen3.8-27B (auto-compliance).
- **Quality parity check:** on the fastest engine for each model, if it isn't Ollama, run the security prompt set once (n=1) and one WFE coding task through engine mode. Correctness must match the Ollama run: a faster engine that answers differently hasn't won.

Report: `summarize` gives the per-model table (engine × mode rows; decode tok/s, prefill tok/s, prefill TTFT, cold, resident GB, tool OK, template OK, valid, CWE accuracy, clean FP). Add from the logs:
- which drafter was used and its acceptance rate
- the kernel path

Name the winning engine and mode for each model.

### Promotion gate

A win is reported only from VALID runs (rule 4).

**Coding:** if MiMo is ≥ Laguna's pass rate on the coding suite, that's the evidence for an operator task to add MiMo as a cheaper agentic option. It does **not** mean replacing Laguna automatically; promotion stays a separate operator task.

**Security:** if MiMo is ≥ VulnLLM on CWE accuracy with no false positive on #6, that supports an `auto-security` promotion task.

**Engine:** adding a new engine or replacing an existing one is on the table (operator, 2026-09-23), so a clear winner feeds a real integration task, not just a note. Before that task starts, it has to answer the history below.

**History — don't repeat the dual-engine experience.** Portal ran `mlx_lm.server` behind an MLX proxy alongside Ollama (and a separate vision path) until commit `3a0c58e` (2026-06-09). Operator's account: the dual-engine setup gave a **terrible user experience**. `KNOWN_LIMITATIONS.md` records the failure surface that was deleted:
- single-model eviction across engines
- cold-boot 503 windows
- admission-control conflicts
- deploy staleness
- the proxy/watchdog/thread-patch stack needed to hold it together

MLX engines may have matured since then — continuous batching, SSD KV cache and prompt caching all postdate that setup — but a speed win in this bench does not show the UX problem is gone. Any integration proposal must show, on the live stack, with the winning engine running beside Ollama (and oMLX if it stays):
- no cross-engine memory contention (both engines' models resident without swap growth)
- clean cold-start behaviour, with no 503 windows visible in OWUI
- one routing path in `BackendRegistry` with no proxy or watchdog
- a single-engine alternative considered: whether the winner could *replace* Ollama or oMLX, rather than become a third concurrent engine
