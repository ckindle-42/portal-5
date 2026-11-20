# oMLX 0.7.3 → 0.8.0 upgrade plan (prepared 2026-11-19, no live changes made)

Incumbent: **oMLX 0.7.3** (last verified stable; `docs/ENGINE_H2H_RESULTS_20261113.md`,
`docs/ENGINE_GRADE_20261115.md` still grade 0.7.3 as the incumbent). Target: **oMLX 0.8.0**,
released 2026-11-18 ([v0.8.0](https://github.com/jundot/omlx/releases/tag/v0.8.0), commit
`7fad36c`, `prerelease: false`), after [v0.8.0rc1](https://github.com/jundot/omlx/releases/tag/v0.8.0rc1)
(2026-11-12) and the 0.7.4.dev1 dev releases. This is the engine's next major release line
after 0.7.0 (2026-10-01 upgrade, `docs/reports/ENGINE_UPGRADE_20261001.md`).

Everything below is written from the release notes/PRs, the GitHub release asset list, and
repo code read at HEAD on this lane. Nothing here has touched the live engine — the live
ladder is §4 and is the orchestrator's.

## 0. Speed gate (operator addendum, 2026-11-19)

The upgrade is gated on **no per-seat regression**: a pre-upgrade baseline over every
oMLX-served seat, the identical run post-upgrade, and a fix-or-roll-back rule (§0.2). This
section inventories what we tuned locally, so the gate knows what it must not lose.

### 0.1 Inventory — does 0.8.0 keep, supersede or break each local speed gain

| # | Gain | Where it lives | Measured gain (receipt) | 0.8.0 verdict |
| --- | --- | --- | --- | --- |
| 1 | Lightning MTP on the `-oQ4e-mtp` side-car checkpoints | checkpoint choice on disk + `mtp_enabled: true` per model in host `~/.omlx/model_settings.json`; alias wiring `config/backends.yaml:621, 651` (omlx-coding), `:719, 773-775` (omlx-general), `:805, 845` (omlx-reasoning) | Rollout 2026-08-14: Qwen3.8 17.5–18.6 vs 12.25 tok/s Ollama (~1.45×, accept 60–65%), Nemotron 70.0–70.3 vs 52.9–53.1 (~1.33×, accept 76–87%) (`config/backends.yaml:606, 705`; `config/MODEL_CATALOG.md:1874, 1972`); 0.7.0 native MTP: Nemotron 90, Qwen3.8 42 tok/s, acceptance 93–98% (`docs/reports/ENGINE_UPGRADE_20261001.md:60-67`); 0.7.3 re-measure: Qwen3.8 MTP 27.5 vs plain 14.1, Nemotron MTP 50.0 vs plain 45.1, accept 69–76% (`docs/ENGINE_H2H_RESULTS_20261113.md:46, 67-68, 82`) | **KEPT, faster upstream**: top-p MTP verify from top 512 (#5313); DFlash drafter context kept on exact prefix hits (`22f2c43`/#5344); DFlash2 +10% (4 requests) (#5212); `~` drafter-path fix (#5154). The plain conversions carry no `mtp.*` weights, so the `-oQ4e-mtp` checkpoints stay required. Verify `mtp_enabled: true` survived the restart (autoupdate backs the file up, §2). Stale-doc note: `config/MODEL_CATALOG.md:1972` still describes a Nemotron GGUF alias that backends.yaml no longer carries — the Nemotron oQ4e-mtp checkpoint is registered seat-less (`config/backends.yaml:708`). |
| 2 | LaunchAgent `ProcessType Standard` (never Background) | `deploy/launchd/com.portal5.omlx.plist:32-34` (commit `3d17767ba`) | Background cut MoE decode ~56%: Gemma-4-26B QAT 32.5→73.7, Nemotron 42→95, Qwen3.8 13.9→15.2 tok/s, aligning with stock mlx_lm (`docs/ENGINE_GRADE_20261115.md:7-11`) | **KEPT** — our plist, not the engine's; #5179 changes console-log verbosity under brew/app supervision only. Verify the plist still points at the venv entrypoint after the restart (UNPROVEN §5). |
| 3 | DFlash2 drafter seat + `dflash_max_ctx: 65536` | host `~/.omlx/model_settings.json` on the `Qwen3.8-27B-4bit` seat; seat registration `config/backends.yaml:627-641` | Unlimited drafter ctx hangs past ~70–85K prompt tokens (67,153 tok in 742 s; 87,652 stalled >900 s; clean eviction fallback 923 s) (`config/backends.yaml:629-635`) | **KEPT + upstream speedup** (#5212 +10% at 4 requests, #5154 path fix, drafter prefix retention). Verify the key survived the upgrade restart (§3.2 item 4). |
| 4 | Per-model seat sampling defaults | `scripts/omlx_seat_defaults.py` → `~/.omlx/model_settings.json`, run by `./launch.sh sync-config` | No TPS gain claimed — pipeline traffic sends sampling explicitly; it fixes DIRECT clients (IDE harnesses at :8085) from oMLX global defaults to their seat's resolved sampling (per-model default behaviour verified 2026-09-25) | **KEPT** — the merge removes only keys it previously managed, so 0.8.0's new per-model keys survive (test-covered, this lane). Post-upgrade `--dry-run` churn check (§3.2 item 5). |
| 5 | Gemma 4 no-think post-tool template anchor | `scripts/omlx_chat_template_patch.py` patches model dirs' `chat_template.jinja`; Ollama side `portal/platform/inference/ollama_native.py` | Direct oMLX triage 18/21→21/21 (card sampling), 6/7→7/7 (greedy); Ollama 8/8 clean calls vs 0/8 (PIPELINE_ALIGNMENT_V1 §13). Wall-clock effect: stops runaway thought-channel answers to the token cap | **KEPT** — the template-render thinking-default change (`44b0525`) does not remove the patched branch; idempotent, re-run after upgrade (§3.2 item 2). |
| 6 | Memory tier + ceilings | `scripts/omlx_memory_tier.py` → `~/.omlx/settings.json` `memory.memory_guard_tier`; `./launch.sh up` writes `balanced`, `./launch.sh coder-reap288` writes `aggressive` | REAP-288: `balanced` aborts a 14.3K prefill (44.8 GB vs watermark), `aggressive` serves 22.4K (101.7 s); ceilings 41.7/51.5 GiB vs Metal cap 56.1 (`docs/reports/ENGINE_UPGRADE_20261001.md:49-58, 76-83`) | **KEPT, dynamics change** — #5165 (unloading no longer disturbs residents), #4842 (MoE expert offload under prefill pressure), #4321 (grammar cache 1 GiB) move the counters the load guard reads. Re-measure ceilings + the swap shape (§3.2 items 6–7, §4 step 2 `final_ceiling`). |
| 7 | Shadow-then-shift alias rollout + hot-seat protection | priority-10 alias blocks `config/backends.yaml` (pattern comments :599-618, :655-659); `hot_seat_protect_s: 900` `config/backends.yaml:913` | Fanout: same-model decode-bound fan-out on oMLX 2.1× (30B) / 2.4–2.8× (8B) at 3–4 concurrent vs fully serialized Ollama (`config/backends.yaml:739-741`, `docs/TASK_FANOUT_CONCURRENCY_V1.md`) | **KEPT (config-level)** — but #5164 Concurrent Request Priority + #5140 change the fanout/TTFT shape: re-run the fanout rows (§4 step 5), don't re-tune blind. |
| 8 | Prefix-cache SSD cap | host oMLX settings: SSD dir `~/.omlx/cache` capped 64 GB (auto default = half free space, grew to 189 GB) | P5-OMLX-PREFIX-CACHE-001 (`portal_wiki/canonical/unit-known-limitations-omlx-prefix-cache-accounting.md`): a store is not a hit, a second model deep-resets caches, 0.7.2 refused 166 GB of 0.7.0-era blocks | **SUPERSEDED upstream, partially** — #5324 short-prompt loops keep hits; #5202 image prefix hashing ~4× cheaper. Upgrade note: blocks from the old build are skipped after an upgrade → expect cold caches and worse first-run TTFT immediately post-upgrade; re-measure the record (§3.2 item 6). |
| 9 | `max_concurrent_requests: 8` | host oMLX global settings (admin API; production keeps 8) | Aggregate tok/s at 1/2/4/8 in flight = 78.5/107.9/144.5/158.0 (Nemotron); 4 vs 8 at the limit: no consistent difference → stays 8 (`docs/reports/ENGINE_UPGRADE_20261001.md:85-89, 131-135`) | **KEPT**; #5312 stops tg-TPS inflation for batch > Max Concurrent Requests (affects other tools' rows, not this sequential gate); interacts with #5164 — A/B in §0.3. |
| 10 | Portal-side, engine-agnostic (context, not part of this gate) | keeper warm-daily-driver (`portal/platform/inference/router/lifespan.py:267-305`), oMLX prefill zone (`portal/platform/inference/load_guard.py:116-138`) | Engine-agnostic admission/TTFT work; unchanged by any engine version | **Unaffected** — listed so the gate doesn't re-litigate them; watch their interaction with #5085/#5165 post-upgrade (§4 step 4). |

Registered but currently seat-less oMLX models (serve no production seat today: `auto-daily`
and its `::nemotron` variant pin the GGUF `ctx32k` tag, `config/portal.yaml:937, 1138`, and only
`ctx8k` is aliased to oMLX):
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`, `unsloth--Qwen3.6-27B-UD-MLX-4bit`,
`mlx-community--Mistral-Small-3.2-24B-Instruct-2506-4bit`, `Tongyi-DeepResearch-30B-A3B-abliterated-4bit`
— optional in the gate, not blocking.

### 0.2 Baseline: exact commands and the comparison rule

Instruments — the existing benches, not new ones:
- **Engine gate** `scripts/speed_bench.py --engine omlx` (direct :8085; prefill/decode split,
  TTFT, load s; per model, sizes 2000/8000/32000, decode 128 tokens; JSON via `--out`;
  `scripts/OPERATOR_TOOLS.md:203`).
- **End-to-end check** `tests/benchmarks/bench_tps.py --mode pipeline` (through the pipeline,
  category prompts, per-run cv + `avg_ttft_s`). `--workspace` filters to exact ids in
  `workspace_routing` (`tests/benchmarks/bench/runners.py:281-287`), so it covers the top-level
  workspaces only; the 24 `::variant` seats are driven by speed_bench with
  `--engine pipeline --workspace <base>::<variant>` (the Pipeline accepts `base::variant` ids,
  `portal/platform/inference/router/handlers.py:573`).

Precondition: quiet host (`uv run python scripts/host_quiet.py`), live checkout, oMLX 0.7.3
running, stack up. Every command runs from the live checkout, not this worktree.

**B1 — engine baseline, run TWICE** (the pair measures run-to-run noise), all 14 oMLX models
that serve production seats (resolved from `config/portal.yaml` × the priority-10 alias blocks,
same resolution as `scripts/omlx_seat_defaults.py`; 38 seats map onto them):

```bash
MODELS=(Qwen3.8-27B-oQ4e-mtp Qwen3-Coder-30B-A3B-Instruct-4bit Laguna-XS-2.1-4bit \
  Qwen3.8-27B-4bit Huihui-Qwen3.6-27B-abliterated-MLX-4bit gemma-4-26b-a4b-it-QAT-4bit \
  mlx-community--gemma-4-26b-a4b-it-4bit granite-4.1-30b-4bit \
  unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit DeepSeek-R1-0528-Qwen3-8B-4bit \
  VulnLLM-R-7B-4bit Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit \
  Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2 \
  huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit)
for m in "${MODELS[@]}"; do
  uv run python scripts/speed_bench.py --engine omlx --model "$m" --sizes 2000,8000,32000 \
    --out /tmp/speed_pre080_run1_"$m".json
done   # then repeat verbatim with run2 (and post-upgrade: pre080→post080)
```

**B2 — pipeline baseline, run TWICE**, the 14 top-level workspaces whose default lane is
oMLX-served: `auto auto-coding auto-compliance auto-spl auto-security auto-council
auto-documents compliance-council-deepseek-r1 compliance-council-granite41
compliance-council-qwen38 compliance-mapping compliance-reading-overflow hunt-reasoning
tools-specialist`.

```bash
uv run python tests/benchmarks/bench_tps.py --mode pipeline \
  --workspace auto --workspace auto-coding --workspace auto-compliance --workspace auto-spl \
  --workspace auto-security --workspace auto-council --workspace auto-documents \
  --workspace compliance-council-deepseek-r1 --workspace compliance-council-granite41 \
  --workspace compliance-council-qwen38 --workspace compliance-mapping \
  --workspace compliance-reading-overflow --workspace hunt-reasoning \
  --workspace tools-specialist \
  --runs 3 --order size --cooldown 10 \
  --output tests/benchmarks/results/bench_tps_pre080_run1.json
# then repeat verbatim with run2; post-upgrade identical with post080 names
```

**B3 — variant seats** (the remaining 24 oMLX seats, speed_bench through the Pipeline, twice):
`auto-coding::heavy auto-coding::laguna auto-coding::qwen38coder auto-coding::qwen38coder-dflash
auto-coding::uncensored-agentic auto-coding::bigfix auto-coding::cad auto-reasoning::deep
auto-daily::deep auto-daily::fast auto-daily::gemma-fast auto-research::data
auto-compliance::reading auto-security::pentest auto-security::purpleteam
auto-security::purpleteam-deep auto-security::purpleteam-exec auto-security::redteam
auto-security::redteam-deep auto-security::blueteam-council auto-security::blueteam-orchestrated
auto-security::bully-handoff-drafter auto-security::security-council-granite41-30b
auto-general-uncensored::creative` — same speed_bench invocation shape as B1 with
`--engine pipeline --workspace <seat>`. If the Pipeline rejects a `base::variant` id on 0.7.3
(it accepts the shape, `portal/platform/inference/router/handlers.py:573` — verify on the first
seat), run that seat's `--engine omlx --model <resolved oMLX id>` from the B1 roster instead
and note the substitution.

**Comparison rule (operator):** per seat and per metric — decode tok/s, TTFT (warm rows),
prefill tok/s — the pre band is the spread between the two baseline runs (or the run's `cv`,
whichever is larger). A post-upgrade seat **regresses** when it is worse than the worse
pre-upgrade run by more than that band. Any regressing seat ⇒ fix the known post-upgrade items
first (parser reinstall §3.2 item 1, seat defaults §3.2 item 5, template patch §3.2 item 2,
cold prefix cache from #5324-era note above) and re-measure; still regressing ⇒ roll back
(§ROLLBACK). No seat is adopted or dropped from a single pre/post pair. `load_seconds` and
first-size TTFT are load-dominated: gate them separately (they move with #5165/#5085 cache
state), and judge TTFT on warmed rows. Comparability caveat: pre-upgrade rows from OTHER tools
(h2h, oMLX's own bench) may carry the #5312 inflation — this gate's own pre/post pair never
mixes tools.

### 0.3 The three new 0.8.0 defaults — set for our workload, or A/B first?

| Setting | Default | Should we set it? | A/B against the baseline |
| --- | --- | --- | --- |
| Concurrent Request Priority (#5164, #5160, #5175) | `Balanced` — keeps running streams ≥10 tok/s, cuts new-prompt TTFT 26% | Keep the default for the gate (comparability). It matches our measured workload shape: production concurrency = `max_concurrent_requests: 8` and the fanout receipt (aggregate tok/s rising 78.5→158.0 at 1→8 in flight; 2.1–2.8× fan-out at 3–4 concurrent) is exactly the traffic it protects. | Toggle via the admin API (`POST /admin/api/global-settings` — applied at runtime in 0.01 s, no unload, verified 2026-10-01 `ENGINE_UPGRADE_20261001.md:131-135`), re-run B1+B2 on 2–3 concurrency-sensitive seats (auto-coding, compliance-council-qwen38, a fanout seat) and the fanout rows (§4 step 5). Adopt an override only if it beats the noise band on TTFT/fanout with no seat decode regression; otherwise stay `Balanced`. |
| Keep GPU Awake After Requests (#5085) | 5 min | Keep the 5-min default. Our idle-unload accounting and admission headroom read the engine's memory state; a long awake window holds GPU memory the load guard counts. | Watch `portal5_load_guard_headroom_bytes` / `portal5_load_guard_ceiling_bytes` and that idle unload still fires (§4 step 4). A/B (longer window vs default) only if post-upgrade TTFT-after-idle shows a cold-start cost beyond the noise band on the daily-driver seat; raise the window on that one seat, never globally, if so. |
| INT8 Activation Prefill (#5108) | off, per-model opt-in, own SSD cache blocks | Leave OFF. Prefill is not our binding bottleneck on the MoE seats (H2H prefill 597–785 tok/s vs decode 27–95), the numerics change (activation quantization) would need quality rows, not just speed, and its own SSD blocks add disk/memory under the memory-tier ceilings. | If the gate shows a prefill-bound seat (compliance-reading-overflow / the gemma plain 128k seat), A/B on that seat alone: enable per-model, re-run its B1 sizes + a quality row; keep it only if prefill t/s beats the band with the quality row unchanged. Re-measure ceilings after enabling (§0.1 row 6). |

## 1. What changed between 0.7.3 and 0.8.0

### 1.1 API / CLI / config surface

No endpoint, CLI verb or settings-file rename is announced in the release notes. The
behaviour changes that Portal code makes assumptions about:

| Change | Reference | Portal impact |
| --- | --- | --- |
| `reasoning_effort: "none"` / `"off"` now turn thinking **off** (previously mapped to `low`, i.e. thinking stayed on) | [#5151](https://github.com/jundot/omlx/pull/5151) | Portal never sends `reasoning_effort:none` to oMLX: `_apply_reasoning_effort` converts it to `think:False` first (`portal/platform/inference/router/validation.py:322-327`), and the oMLX adapter maps think to `chat_template_kwargs.enable_thinking` (`validation.py:526-530`). The tiers Portal does forward (`low/medium/high` → `chat_template_kwargs.reasoning_effort`, `validation.py:505-511`) are unaffected. Seats that send an explicit effort will now get the OpenAI meaning end-to-end. |
| Thinking defaults are now read by **rendering the chat template** (GLM-4.6V, GLM-OCR report thinking on) | commit `44b0525` | Our oMLX fleet has no GLM models (grep of `config/backends.yaml`: GLM tags exist only in Ollama groups). For every model where a workspace sets `think`, Portal still injects `enable_thinking` explicitly, so engine-side default detection is a no-op for us. Only matters for direct IDE clients on a template-declares-thinking model. |
| INT8 Activation Prefill stays off unless a model opts in, with its own SSD cache blocks | [#5108](https://github.com/jundot/omlx/issues/5108) | If any host `~/.omlx/model_settings.json` entry had INT8 activation prefill enabled, its effective prefill path changes. Check the host file before/after (autoupdate backs both settings files up). |
| New global setting **Concurrent Request Priority** (default `Balanced`: keeps running streams ≥10 tok/s, cuts new-prompt TTFT 26%); short request arriving during a long prefill starts after the running chunk | [#5164](https://github.com/jundot/omlx/pull/5164), [#5160](https://github.com/jundot/omlx/pull/5160), [#5175](https://github.com/jundot/omlx/pull/5175) | Production keeps `max_concurrent_requests: 8`. Fanout/concurrency behaviour (TASK_FANOUT_CONCURRENCY_V1) changes shape — re-verify, don't re-tune blind (§4 step 5). |
| New Advanced setting **Keep GPU Awake After Requests**, 5 min default | [#5085](https://github.com/jundot/omlx/pull/5085) | Idle-unload accounting and the load guard's quiet-path reads (`portal/platform/inference/load_guard.py`) see the engine one setting different. GPU warmth is not residency, but verify idle unload still fires (KNOWN_LIMITATIONS "oMLX unload accounting can over-wait"). |
| Supervised console log keeps only warnings/errors under `brew services` and the macOS app | [#5179](https://github.com/jundot/omlx/pull/5179) | Our service is the Portal LaunchAgent (`com.portal5.omlx`, `OMLX_SUPERVISED=launchd`), whose full log goes to `/opt/homebrew/var/log/omlx.log` via the plist — unchanged. Watchdog log-tail behaviour unaffected. |
| New **Prefill Accelerator** (NVIDIA CUDA helper / DGX Spark / second Mac), enabled per model after Global Settings → Advanced → Enable Distributed Inference + Cluster pairing | [#5065](https://github.com/jundot/omlx/pull/5065), [#5163](https://github.com/jundot/omlx/pull/5163), [#5195](https://github.com/jundot/omlx/pull/5195), guide `docs/experimental/prefill-accelerator.md` | Off by default; single-M4-Pro host, no CUDA helper, no second Mac — do not enable. Listed so nobody "cleans up" the new settings keys. |
| New **oQh** quantization option ("Rotated codes" in the oQe section; output names end in `h`, e.g. `Qwen3.5-9B-oQ2.5h`); oQe itself more accurate at same size; >memory Qwen3.5/3.6 quantizable | [#5317](https://github.com/jundot/omlx/pull/5317), [#5292](https://github.com/jundot/omlx/pull/5292), [@keefar in #5332](https://github.com/jundot/omlx/pull/5332) | No Portal seat names an oQh checkpoint. A re-quant is a model change with its own A/B gate (MODEL_SEAT_PROCESS), not part of this upgrade. |
| **Tool-call parsing fixes**: array parameters split across JSON fragments are merged; tool names like `read` counted only in call position; coded error for an empty `tool_calls` finish; gpt-oss keeps completed messages on a malformed last header | [#5345](https://github.com/jundot/omlx/pull/5345), [#4433](https://github.com/jundot/omlx/pull/4433)/[#5161](https://github.com/jundot/omlx/issues/5161), [#5139](https://github.com/jundot/omlx/pull/5139), [#5224](https://github.com/jundot/omlx/issues/5224) | Same class as the 0.7.0 parallel-tool-call finding (no `index` on streamed deltas; fixed in `portal/platform/inference/router/streaming.py:359-362`, `_indexed_tool_calls`, and `:1029`). Server-side parse behaviour changed → smoke_stream + tool-turn rows must re-prove it (§4). |
| **Memory/ceiling**: unloading a model no longer disturbs still-loaded models (Metal wired limit stays); compiled-grammar cache capped at 1 GiB; MoE expert offload keeps resident experts under prefill pressure | [#5165](https://github.com/jundot/omlx/issues/5165), [#4321](https://github.com/jundot/omlx/issues/4321), [#4842](https://github.com/jundot/omlx/pull/4842) | #5165 changes the counter dynamics the load guard reads (P5-LOADGUARD-SWAP-001 reads `current_model_memory` direction during swaps; KNOWN_LIMITATIONS "oMLX unload accounting can over-wait") — the swap race may now behave differently, re-test. Grammar cap: the Pipeline sends no `response_format`/schema to oMLX (grep of `validation.py`), so this lands on IDE-direct clients only. |
| **Speculative decoding**: top-p MTP verify picks from top 512 candidates; DFlash drafter context kept on exact prefix hits; DFlash2 +10% (4 requests); `~` drafter path expansion fix; DSpark drafter batches verify across requests | [#5313](https://github.com/jundot/omlx/pull/5313), commit `22f2c43`/[#5344](https://github.com/jundot/omlx/pull/5344), [#5212](https://github.com/jundot/omlx/pull/5212), [#5154](https://github.com/jundot/omlx/pull/5154) | The omlx-coding MTP side-car seat (`Qwen3.8-27B-oQ4e-mtp`) and the DFlash2 seat (`Qwen3.8-27B-4bit`, `dflash_max_ctx: 65536` in host `~/.omlx/model_settings.json`, `config/backends.yaml:627-641`) change acceptance/throughput dynamics — bench rows stale after upgrade (§4 step 5). |
| **Speed**: Qwen 8-request decode +38% (#5309), two long requests +30% (#5090), 6-req 8-bit +16% (`b5c7793`); DeepSeek V4.1 prefill +44% (#5031), cold-shader first decode +269% (#5025); Affine KV decode up to +58% at long context (#5095), attention-sink prefill ~4x (#5088/#5101); short-prompt loops keep prefix-cache hits (#5324); image prefix hashing ~4x cheaper (#5202) | as cited | Every oMLX decode/prefill number in the repo (bench rows, h2h tables, ENGINE_GRADE) is measured on 0.7.x and goes stale for these seats. The prefix-cache limitation entry (2026-10-21, measured on 0.7.2) should be re-measured, not assumed. |
| **Benchmarks**: batch wider than Max Concurrent Requests no longer inflates tg TPS; code benchmarks no longer hang; Max Tokens Override for local accuracy runs | [#5312](https://github.com/jundot/omlx/pull/5312), `bf28cd6`, [#5189](https://github.com/jundot/omlx/pull/5189) | Comparability caveat for any before/after delta: pre-upgrade rows with batch>8 may have been inflated; the fix makes post-upgrade rows more honest, so a raw delta conflates engine speed with the fix. |
| **Dependencies**: transformers up to 5.22 | [#5131](https://github.com/jundot/omlx/pull/5131) | Risk item: `Laguna-XS-2.1-4bit` ships custom `modeling_laguna.py`/`configuration_laguna.py` that oMLX loads natively (`portal_wiki/archive/unit-model-catalog-laguna-xs-2-4bit.md`). A transformers major-line bump is exactly what breaks custom-code checkpoints — Laguna is a **priority-10 live production seat** (`config/backends.yaml:598-604`), so its canary is mandatory (§4 step 4). |
| **Model lists survive bad files** (skip unreadable safetensors header / HF refs file); Qwen3-Reranker scores no longer tie at 1.0 | [#5379](https://github.com/jundot/omlx/pull/5379), [#5329](https://github.com/jundot/omlx/pull/5329), [#5207](https://github.com/jundot/omlx/pull/5207) | `/v1/models` composition could differ if a previously-listed conversion had a bad file it now skips. `portal trace` alias hops re-prove the list (`portal/platform/inference/cli/trace/engines.py:139-145,177-188`). The :8942 VL reranker is a separate host service, not an oMLX seat — #5207 does not touch it. |

### 1.2 Distribution

Release assets (GitHub API, checked 2026-11-19): `omlx-0.8.0-cp311-cp311-macosx_15_0_universal2.whl`,
`...cp312...`, `...cp313...` (~41 MB each) plus two DMGs (macOS 26/27, macOS 15 Sequoia).
The wheel names match what the venv installer expects exactly
(`scripts/omlx_venv_install.py:_release_asset`, pattern
`omlx-<ver>-<tag>-<tag>-macosx_15_0_universal2.whl`, python tags cp311/cp312/cp313) — **no
installer change needed**. The updater's stable-release pick (`scripts/engine_autoupdate.py:328-336`)
skips `0.8.0rc1`/`0.7.4.dev1` by tag regex and returns `0.8.0`; `_PRERELEASE`
(`scripts/engine_autoupdate.py:462`) does not match `0.8.0`; `_semver` ordering puts
`(0,8,0) > (0,7,3) > (0,7,4)` (`scripts/check_updates.py:94-97`).

## 2. What in Portal touches each change (file:line, HEAD `15af4cd6f`)

**Upgrade path**
- `scripts/engine_autoupdate.py` — `omlx_latest()` :328-336 (stable pick), `_PRERELEASE` :462,
  `_update_target()` :465-481 (skips rejected), `omlx_upgrade()` :371-395 (staged venv wheel →
  restart → model-count wait), `omlx_backup()`/`omlx_restore()` :353-363 (both
  `~/.omlx/settings.json` and `~/.omlx/model_settings.json`), `_omlx_restart()` :339-350
  (venv `launchctl kickstart -k` vs `brew services restart`), `_await_visible()` :238-261
  (data01 TCC popup, 30 min then rollback), `omlx_point_at()` :409-439 (rollback),
  `omlx_prune()` :398-406, weekly/security gating `main()` :650-681. State
  `~/.portal5/engine_update.json`; launchd `deploy/launchd/com.portal5.engine-update.plist`.
- `scripts/check_updates.py` — `check_omlx()` :330-366 (`_release_gap("jundot/omlx", …)` :359,
  version read from the active venv python :332-350, brew symlink fallback :353-357),
  `_semver` :94-97, `_release_gap` prerelease filter :238-244.
- `scripts/omlx_venv_install.py` — `_release_asset()` :117-127 (wheel-name match), `_python_tag()`
  :102-114, `install_release_wheel()` :145-153, `stage_venv_upgrade()` :167-173,
  `relocate_venv_entrypoints()` :175-186, `activate_venv()` :189-202; **new** `venv_service_active()`
  :24-34 and `omlx_restart_command()` :37-43 (this lane).

**Contract probes** (the gate that accepts or rejects 0.8.0)
- `scripts/engine_contract_check.py` — `_omlx_version()` :417-427 (reads `/api/status`
  `version`), `_needs_probe()` :436-440 (served ≠ installed forces a re-probe — covers a
  manual upgrade too), `check_omlx()` :443-461 (`/v1/models` discovery + delivery probes),
  `_delivery()` :112-171 (top_k/min_p/top_p/temperature/seed/repeat/presence/max_tokens/think,
  with the presence-penalty escalation 2.0→5.0→10.0 introduced because 0.7.0's numerics
  needed >2.0, :137-147), `_gemma4_tool_format()` :178-220 (raw `<|tool_call>` leak probe,
  added for the p2-wave34 OWUI leak on 2026-11-19). Probe models: `config/engine_contract.yaml`
  (omlx: `huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit`, `gemma-4-26b-a4b-it-QAT-4bit`).
- State `~/.portal5/engine_contract.json`; the daily `--if-changed` run re-proves on ANY
  version change (engine_autoupdate `main()` :661-666).

**Request building (what Portal sends 0.8.0)**
- `portal/platform/inference/router/validation.py` — `_inject_omlx_options()` :494-536:
  `repetition_penalty` naming :522-524, `stream_options.include_usage` :513-514, sampling
  setdefaults :516-520, think → `chat_template_kwargs.enable_thinking` :526-530, effort tiers →
  `chat_template_kwargs.reasoning_effort` :505-511, `thinking_budget` passthrough
  `_apply_omlx_thinking_budget` :348-350; `_apply_reasoning_effort()` :310-332 (`none` →
  `think:False`, so #5151 cannot change our wire shape). Note: `thinking_budget` is
  **unprobed** by the contract check — a 0.8.0 change there would be silent (UNPROVEN §5).

**Routing/fallback (oMLX → Ollama GGUF cascade)**
- `config/backends.yaml` — oMLX entries: `omlx-local` :581-589 (holding, no routing),
  `omlx-coding` :591-655 (priority 10; Qwen3-Coder-30B, Laguna-XS-2.1, Qwen3.8-27B-oQ4e-mtp,
  Huihui-Qwen3.6-27B, Qwen3.8-27B DFlash2 :627-641), `omlx-reasoning` :799-848 (DeepSeek-R1
  deepseek_r1 parser seat :792-818), `omlx-general` :681-778, `omlx-security` :850-892,
  `omlx-creative` :894-901. Priority-10 alias blocks translate the production GGUF
  `model_hint`s to oMLX names, so an oMLX-served workspace falls back to its Ollama GGUF tag
  automatically when oMLX is unhealthy (`get_backend_candidates` order + `_hint_fallback`).
- `portal/platform/inference/router/backend_introspect.py` — `_omlx_model_loaded()` :116,
  `free_ollama_for_omlx()` :151, `make_room_for_omlx()` :211-217 (Ollama residents freed for
  oMLX admission).

**Memory / ceiling**
- `portal/platform/inference/load_guard.py` — `_omlx_prefill_zone()` :116-138 (reads
  `memory.prefill_safe_zone_ratio`), `/api/status` + admin reads/unloads
  (`_omlx_status` :806-817, `_omlx_used` :827, `_omlx_idle_models` :916, `_omlx_loading` :980,
  `_omlx_foreign_active` :1016), unload-counter direction logic per P5-LOADGUARD-SWAP-001.
- `scripts/omlx_memory_tier.py` (tiers; `launch.sh:57` writes `balanced` on every up;
  restart now service-aware, this lane). Ceiling limitation: P5-OMLX-CEILING-001
  (`portal_wiki/canonical/unit-known-limitations-omlx-balanced-ceiling.md`) — balanced's
  ceiling moves with free memory; `LOAD_GUARD_CEILING_GB` is the fixed-budget knob.

**Seat defaults / chat-template patcher (run by `./launch.sh sync-config`)**
- `scripts/omlx_seat_defaults.py` — writes single-seat models' resolved sampling into
  `~/.omlx/model_settings.json` (`_FIELDS` :48-55, `seat_defaults()` :70-103, `apply()` :106-125
  merge semantics: only keys it previously managed are removed, unmanaged keys — including
  0.8.0's new per-model keys — survive). Restart now targets the live service (this lane,
  :149-151).
- `scripts/omlx_chat_template_patch.py` — Gemma 4 post-tool no-think anchor
  (`patch_text()` :53-61, marker :40, unload of patched loaded models :73-99). 0.8.0's
  template-render thinking-default change does not remove the patched branch; idempotent,
  re-run after upgrade. Ollama side of the same gap: `portal/platform/inference/ollama_native.py`.

**Tool parsers (the silent-loss trap)**
- `scripts/omlx/deepseek_r1_tool_parser.py` + `scripts/install_omlx_parsers.sh` (venv-aware
  target discovery :15-25) + watchdog self-check `scripts/omlx-watchdog.sh:67-92`.
  A wheel upgrade replaces site-packages wholesale and silently drops the parser — that
  already happened once on `brew upgrade` (P5-FANOUT-001, 2026-09-25). **Must re-run after
  every upgrade**, venv or brew.

**launchd / startup**
- `deploy/launchd/com.portal5.omlx.plist` — `ProgramArguments`: `__OMLX_VENV__/bin/python
  -m omlx.cli serve` (entrypoint unchanged in 0.8.0 per release notes; verify at first
  restart — UNPROVEN), `ProcessType: Standard` with the comment that Background cut MoE
  decode ~56% (2026-11-15, `docs/ENGINE_GRADE_20261115.md`), `OMLX_SUPERVISED=launchd`,
  log `/opt/homebrew/var/log/omlx.log`. `deploy/launchd/com.portal5.omlx-watchdog.plist` +
  `scripts/omlx-watchdog.sh` (probe `/v1/models`, two-failure restart of the active label).
- `scripts/lib/util.sh` launch-path restarts are already venv-aware :779-783, :795-799.

**Read-only observability**
- `portal/platform/inference/cli/trace/engines.py` — `omlx_hop()` :177-188 reads
  `/v1/models/status` `final_ceiling`; model lists :139-145. Sections wired in
  `portal/platform/inference/cli/trace/command.py` :32-50.

**WFE / bench harness**
- `tests/wfe/campaign.py` — `OMLX_BASE` :318-322 (`/health` `engine_pool`), `drain_omlx()`
  :328+ (**fixed this lane**: it restarted brew unconditionally; with the venv LaunchAgent
  holding :8085 a brew restart drains nothing — bench rows would measure a previous arm's
  resident weights — and can start a port-conflicting crash loop). `scripts/uat_engines.py`
  is the per-seat canary runner.

## 3. Code changes

### 3.1 Made BEFORE the upgrade (this lane, with unit tests)

1. `scripts/omlx_venv_install.py` — `venv_service_active()` + `omlx_restart_command()`: one
   helper that returns the restart command for whichever oMLX service is live (venv
   LaunchAgent `com.portal5.omlx` vs brew `jundot/omlx/omlx`).
2. `scripts/omlx_seat_defaults.py`, `scripts/omlx_memory_tier.py` — restarted oMLX via
   `brew services restart` unconditionally (pre-cutover stragglers; the live service is the
   venv LaunchAgent, verified `launchctl print` on this host). On the upgrade path
   sync-config runs seat defaults; a changed file would have restarted the *fallback*
   service while the live one kept stale in-memory settings. Now both restart the live
   service.
3. `tests/wfe/campaign.py` `drain_omlx()` — same fix: a brew restart while the venv agent
   holds :8085 drains no residents (WFE arms would measure paging beside a previous arm's
   weights) and can start a second oMLX that crash-loops on the busy port. This is on the
   orchestrator's post-upgrade retest path, so it had to land before the upgrade.
4. Tests: `tests/unit/test_omlx_service_restart.py` (9 tests: venv-active probe, both
   restart branches, seat-defaults/memory-tier/wfe-drain wiring, dry-run no-restart,
   empty-pool skip).

Deliberately NOT changed (and why):
- `scripts/engine_autoupdate.py` restart branch :339-350 — already venv-aware; refactoring
  it onto the new helper would be a drive-by. (Pre-existing minor duplication of the label
  constants with `omlx-watchdog.sh`, `scripts/lib/util.sh` — noted, not touched.)
- Wheel/installer/semver logic — verified against the real 0.8.0 release assets and tag
  list (§1.2); nothing to fix.
- No new contract-check probe was added for `thinking_budget`/effort tiers: a behavioural
  probe whose 0.8.0 semantics I cannot validate offline risks a false REJECT that blocks
  the whole upgrade. Listed in §4/§5 instead (stop, don't improvise).

### 3.2 Changes that can only FOLLOW the upgrade (live, orchestrator)

1. `bash scripts/install_omlx_parsers.sh` — re-applies the DeepSeek parser into the fresh
   site-packages (pointless before: it would no-op against the old install).
2. `./launch.sh sync-config` — re-runs seat defaults + the Gemma template patcher against
   0.8.0 (idempotent).
3. Contract check against 0.8.0 (§4 step 1) — the accept/reject decision itself.
4. Verify host `~/.omlx/model_settings.json` extras survived the upgrade restart:
   `dflash_max_ctx: 65536` on the DFlash2 seat, any tool-parser stamps
   (`tokenizer_config.json` on disk in `/Volumes/data01/omlx-models/` survives, but verify).
5. `uv run python scripts/omlx_seat_defaults.py --dry-run` — confirm no seat-default churn
   from resolved-sampling changes before letting sync-config write.
6. Re-measure the prefix-cache limitation record (0.8.0 claims short-prompt loops keep
   hits — the 2026-10-21 record is 0.7.2-era).
7. Re-test the load-guard swap shape (P5-LOADGUARD-SWAP-001) — #5165 changed unload vs
   wired-limit behaviour the guard's counter-direction read depends on.
8. Bench/WFE re-runs (§4 step 5).

## 4. Live retest/bench plan for the orchestrator (smallest first)

Quiet host, nothing in flight (the autoupdater defers on its own while a WFE/UAT runs).
`uv run` everywhere; commands run from the live checkout (not this worktree).

**Step 0 — preflight (no engine contact beyond reads)**
```bash
uv run python -c "from scripts.engine_autoupdate import omlx_latest; print(omlx_latest())"
cat ~/.portal5/engine_update.json | python3 -m json.tool | head -30
uv run python scripts/engine_contract_check.py --if-changed omlx   # expect [SKIP] unless version changed
```
Expected: `0.8.0` from the first command; `rejected` in state does not contain `0.8.0`;
contract shows the last 0.7.3 verification. If `0.8.0` is in `rejected`, clear it only
after understanding why it was rejected (it will not be retried otherwise).

**Step 1 — the upgrade, contract-gated, automatic rollback**
```bash
uv run python scripts/engine_autoupdate.py --now omlx
```
- **Worked**: log shows `omlx: updating 0.7.3 -> 0.8.0`, `omlx: switched=True`, then
  `[OK] omlx 0.8.0` with every probe `ok` (delivery keys, think both ways, gemma4 native
  tool call parsed), then `omlx updated 0.7.3 -> 0.8.0`; history entry
  `{"from": "0.7.3", "to": "0.8.0", "contract_rc": 0, "result": "updated"}` in
  `~/.portal5/engine_update.json`.
- **Did not work**: `[FAIL] omlx …` probe lines + Pushover + history `rolled_back` with
  `rollback_rc`, `0.8.0` appended to `rejected` (engine back on 0.7.3 — verify with
  `uv run python -c "import scripts.engine_autoupdate as ea; print(ea.omlx_running())"`).
  `result: awaiting_approval` = the data01 popup is waiting — click Allow on the Mac
  within 30 min or it rolls back. `result: install_failed`/`release_unavailable` = the
  wheel/stage step; nothing changed live.

**Step 1b — parser reinstall (mandatory, silent-loss trap)**
```bash
bash scripts/install_omlx_parsers.sh
bash scripts/omlx-watchdog.sh && bash scripts/omlx-watchdog.sh   # second pass confirms
tail -5 ~/.portal5/logs/omlx-watchdog.log
```
Expected: `installed: …/mlx_lm/tool_parsers/deepseek_r1.py` and no `PARSER CHECK FAILED`
line. Skip this and the DeepSeek council-operator seat loses tool calls with no error.

**Step 2 — read-only trace (engines, aliases, workspaces)**
```bash
uv run portal trace --section engines --section aliases --section workspaces
```
- **Worked**: `omlx status PASS … final_ceiling readable` (ceiling value may differ from
  0.7.3's — record it), alias hops follow the engine's model list, workspaces end-to-end
  PASS with oMLX-served seats actually served by oMLX.
- **Did not work**: `omlx status FAIL final_ceiling absent` (status schema change — diff
  `GET :8085/api/status` and `/v1/models/status` against 0.7.3 before proceeding); alias
  hop failures (a conversion dropped out of `/v1/models` — #5379 now skips bad files).

**Step 3 — streaming smoke (live stack)**
```bash
./scripts/smoke_stream.sh
```
Must pass: 0.8.0 changed server-side tool-call streaming/merging (#5345) and stream
preparation (#5140); this gate exercises `_inject_omlx_options` bodies through a real
0.8.0 stream. A failure here with tool-call deltas is the #5345/#4433 class — capture the
smoke output, roll back (§ROLLBACK), and take the transcript to an issue.

**Step 4 — per-seat canary on each oMLX-served workspace**
```bash
uv run python scripts/uat_engines.py --only auto-coding
uv run python scripts/uat_engines.py --only auto-reasoning
uv run python scripts/uat_engines.py --only auto-security
uv run python scripts/uat_engines.py --only auto-data
uv run python scripts/uat_engines.py --only auto-compliance
```
(plus any other workspace whose `portal trace --section workspaces` hop shows an
`omlx-*` backend served). Look for: structured `tool_calls` (no raw markup in content),
`think:false` honoured post-tool (template patch), `reasoning_content` present on
thinking seats, sane refusal behaviour on security seats. Highest-risk seats, in order:
Laguna-XS-2.1 (custom modeling code under transformers 5.22 — if it fails to load, that
alone is a rollback trigger), the DFlash2 seat (drafter path/prefix changes; confirm
`dflash_max_ctx` still honoured), Qwen3.8-27B-oQ4e-mtp (MTP verify window), DeepSeek-R1
(parser reinstall), Gemma-4-26B QAT (gemma4 parser), Huihui/VulnLLM security seats.
Also re-verify one load-guard admission during an oMLX model swap (P5-LOADGUARD-SWAP-001
shape) and read `portal5_load_guard_headroom_bytes` / `portal5_load_guard_ceiling_bytes`
on the Model Management dashboard — #5165 changed unload/wired-limit behaviour.

**Step 5 — bench/WFE rows to re-run (only seats the release could change)**
(The throughput baseline itself is §0 — this step is the behaviour/quality rows.)
Re-run, smallest first:
- **Tool-turn WFE rows for oMLX-served seats only** (text_tool_calls-graded): server-side
  parsing changed (#4433, #5345, #5139). Ollama-side rows are untouched — do not re-run.
- **Decode throughput rows for the oMLX coding seats** (Qwen3.8-27B oQ4e-mtp,
  Qwen3-Coder-30B-A3B, Huihui-Qwen3.6-27B): Qwen batched-decode changes (#5309, #5090) and
  MTP verify (#5313) shift these numbers by design — the incumbent numbers are stale.
- **Long-context rows** (compliance reading / `compliance-reading-overflow`): Affine KV
  speedups (#5095, #5088) and prefix-cache fixes (#5324, #5314) change TTFT/throughput at
  64K+.
- **Fanout/concurrency rows** (TASK_FANOUT_CONCURRENCY_V1 shape): Concurrent Request
  Priority default (#5164) + long-prompt prep no longer stalling streams (#5140).
Comparability caveat when comparing to pre-upgrade rows: #5312 stopped tg-TPS inflation
for batch > Max Concurrent Requests, so part of any delta is the measurement fix, not the
engine. Do not adopt or drop a seat on numbers that conflate the two.
What does NOT need re-running: Ollama-only seats, media/embedding rows (separate host
services), rows for seats whose config and traffic the release cannot touch.

## ROLLBACK (pin the prior version)

**Automatic (already wired):** a contract failure or failed switch on the upgrade path rolls
itself back — `omlx_restore()` puts both `~/.omlx` settings files back from their
`.autoupdate-0.8.0` copies (backed up pre-upgrade, `scripts/engine_autoupdate.py:353-363, 493`),
the engine is re-pointed at the prior install and restarted, `0.8.0` is appended to `rejected`
in `~/.portal5/engine_update.json`, and the history entry reads `result: rolled_back`.
Verify with `uv run python -c "import scripts.engine_autoupdate as ea; print(ea.omlx_running())"`
→ `0.7.3`.

**Manual (the upgrade succeeded; the speed gate §0.2 or a §4 canary fails later):**
1. Quiet host. Restore the prior engine:
   `uv run python -c "from scripts.engine_autoupdate import omlx_point_at; omlx_point_at('0.7.3')"`
   — re-stages `~/omlx-live/venv.previous` (venv install) or re-links the brew keg, then
   restarts the live service (`scripts/engine_autoupdate.py:409-439`). A missing
   `venv.previous`/keg means no rollback material exists — stop and report.
2. Restore settings if 0.8.0 changed them:
   `uv run python -c "from scripts.engine_autoupdate import omlx_restore; omlx_restore('0.8.0')"`.
3. Pin 0.8.0 out of the retry path so the weekly updater cannot re-apply it: add `"0.8.0"` to
   the `rejected` list in `~/.portal5/engine_update.json` (the updater skips rejected targets,
   §2 `_update_target()` :465-481; the CLI has no reject flag — it is the same state record the
   updater writes on a failed contract).
4. Post-rollback hygiene: `bash scripts/install_omlx_parsers.sh` (the restored install's
   site-packages), `./launch.sh sync-config`, then `uv run portal trace --section engines`
   PASS on 0.7.3 before traffic resumes.

## 5. UNPROVEN (what this lane could not verify)

- 0.8.0 keeps the shapes Portal reads: `/health` `engine_pool.model_count`,
  `/api/status` `version`, `/v1/models/status` `final_ceiling`, `/admin/api/login`,
  the unload endpoints, and the `-m omlx.cli serve` entrypoint — reasoned from the
  release notes (no API/CLI renames announced) and the unchanged wheel-based install;
  proven live by steps 1-2 (the updater's model-count wait and the trace both read them).
- `think:false` / `enable_thinking`, `reasoning_effort` tiers, gemma4 native tool-call
  parsing, presence-penalty escalation on 0.8.0 numerics — the contract check decides;
  not runnable from this lane.
- Laguna-XS-2.1 loads under transformers 5.22 (custom-code checkpoint) — flagged risk;
  canary in step 4.
- `thinking_budget` delivery is unprobed by the contract check on ANY version — if 0.8.0
  changed it, nothing gates it; adding a probe needs its 0.8.0 semantics validated live
  first.
- All speed numbers quoted from the release notes are upstream's hardware (M3/M5
  Ultra/Max), not this M4 Pro — nothing here predicts local deltas.
- The §0 rosters (38 seats → 14 models, 14 top-level workspaces, 24 variant seats) were
  resolved offline from `config/portal.yaml` × `config/backends.yaml` at HEAD; the live
  stack's config can differ — reconcile against `portal trace --section workspaces` output
  before running B1–B3.
- speed_bench driving `base::variant` pipeline ids is reasoned from
  `portal/platform/inference/router/handlers.py:573`, not run — verify on the first seat
  (fallback named in §0.2 B3).
- No §0 command was run by this lane (no live runs, per the worker contract); the two-run
  baseline, the noise band, and every 0.8.0 keep/supersede verdict in §0.1 rows 1, 6, 8 are
  pending the orchestrator's live measurements.
