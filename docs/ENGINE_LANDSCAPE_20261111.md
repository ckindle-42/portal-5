# Inference-engine landscape — 2026-11-11

Research only. No engine was installed or started in this lane. Versions and claims below are what the cited primary page said on 2026-11-11. Unknown stays unknown. Third-party numbers are copied as published, not averaged or adjusted. Nothing here predicts a bench outcome.

Target host, as stated by the operator: one Apple M4 Pro, 64 GiB unified memory, arm64 macOS. A resident router sits beside the seat. The Pipeline's contract is OpenAI-compatible HTTP, with tool calling and long context. Production engines today are oMLX (`:8085`, MLX checkpoints) and Ollama (`:11434`, GGUF). Rule 14: native means arm64. Upstream vLLM CUDA wheels are not an arm64 macOS server.

The head-to-head registry that already exists is `tests/benchmarks/engine_h2h.yaml` on `lane/engine-h2h-revive-202611` at `836ff40af` (the path in the task brief, `scripts/benchmarks/engine_h2h.yaml`, is not on that HEAD). Registered there: ollama, omlx, mlx-serve 26.11.1, rapid-mlx 1.0.1, vllm-mlx 0.6.0, mlx_lm.server, prismml-llama, brew-llama, prismml-mlx, mtplx, splash 1.5.0, mlxcel 0.8.1. This doc does not edit that file.

Seat families this ranking cares about, from `config/backends.yaml` (read, not edited): Gemma 4 26B-A4B QAT (daily), Qwen3.8-27B with an MTP sidecar and a DFlash2 drafter (coding), Qwen3.6-35B-A3B, NVIDIA Nemotron 3.5 Lightning 30B-A3B with MTP, Qwen3-Coder-30B-A3B, Granite 4.1 8B/30B, Laguna-XS.2, Gemma 4 E4B (router). Flint is operator-limited to Splash in that registry.

## Already registered

Properties are from each project's own README or release, fetched 2026-11-11, plus the registry pin where it differs from current upstream.

| Engine | Version seen | Release date | Licence | arm64 macOS | Maintenance |
|---|---|---|---|---|---|
| oMLX `jundot/omlx` | GitHub latest tag `v0.7.4.dev1`; previous `v0.7.3` | 2026-11-04; 2026-10-31 | Apache-2.0 (README badge and GitHub API) | Yes. README: macOS 15+, Apple Silicon, Python 3.11–3.13. DMG or Homebrew. Default port in the README is 8000; this host serves `:8085` | Pushed 2026-11-11 |
| Ollama `ollama/ollama` | Stable `v0.40.16`. `v0.40.17-rc0` is a prerelease | 2026-11-09; rc 2026-11-10 | MIT | Yes. Official app and Homebrew. v0.40.16 notes an Apple-silicon memory change and "Updated llama.cpp" | Pushed 2026-11-11 |
| mlx-serve `ddalcu/mlx-serve` | Registry `26.11.1`. Upstream `v26.11.2` | 2026-11-01; 2026-11-06 | MIT (README). GitHub API said `NOASSERTION` | Yes. `brew install mlx-serve` is the CLI bottle; the cask is the app. Zig binary, no Python. Also ships NVIDIA Linux builds — refuse those | Pushed 2026-11-11 |
| Rapid-MLX `raullenchai/Rapid-MLX` | Registry `1.0.1`. Upstream `v1.0.2` | 2026-11-02; 2026-11-06 | Apache-2.0 (README). GitHub API `NOASSERTION` | Yes. `curl -fsSL https://rapidmlx.com/install.sh \| bash` or Homebrew. README: Python 3.12+, not the Portal 3.10 venv | Pushed 2026-11-11 |
| vllm-mlx `waybarrios/vllm-mlx` | `v0.6.0` matches the registry. README quick start still shows `0.4.1` | 2026-10-20 | Apache-2.0 | Yes. Apple Silicon only, MLX. `uvx --from vllm-mlx==0.6.0` is the registry pin so it does not collide with Rapid-MLX's own `vllm-mlx` executable | Pushed 2026-11-07. No newer tag |
| mlx-lm `ml-explore/mlx-lm` | `v0.32.2` | 2026-10-16 | MIT | Yes. `pip`/`uv` package `mlx-lm`, command `mlx_lm.server`. Apple's MLX stack (`mlx` `v0.32.4`, 2026-10-14) | Repo pushed 2026-11-06. Open PR `#2040` "Server V2" (2026-11-06) is not a release |
| llama.cpp `ggml-org/llama.cpp` | `b12284`, GitHub-marked prerelease. That is how this repo publishes | 2026-11-11 | MIT | Yes. README: Apple silicon via ARM NEON, Accelerate, and Metal. `llama-server` is the OpenAI server. Homebrew formula is the registry's `brew-llama` | Pushed 2026-11-11 |
| PrismML llama.cpp `PrismML-Eng/llama.cpp` | No release tag retrieved (later GitHub calls were rate-limited) | unknown | MIT (repo API) | The registry builds `~/src/prismml-llama.cpp` and runs `llama-server`. This lane did not rebuild it. Ternary PTQ/PQ GGUF is the fork's point | Pushed 2026-11-06 |
| Splash `incoai/splash` | Registry `1.5.0`. Upstream `1.6.1` | registry pin 2026-10-28; `1.6.0` 2026-11-06; `1.6.1` 2026-11-11 | Apache-2.0 | Yes. `brew install incoai/tap/splash`, CLI not the `splash-app` cask. README: Apple silicon | Pushed 2026-11-11 |
| mlxcel `lablup/mlxcel` | `v0.8.1` matches the registry | 2026-11-02 | Apache-2.0 | Yes for the macOS aarch64 zip the registry names. The same repo also ships CUDA and ROCm. Refuse those zips. Rust binary, MLX C++ bindings, no Python on the request path | Pushed 2026-11-11 |
| MTPLX `youssofal/MTPLX` | Upstream `v2.12.3`. Registry comments say 2.12.0 | 2026-11-06; 2.12.0 was 2026-09-24 | Apache-2.0, with a user-visible attribution line the README requires | Yes. `brew install youssofal/mtplx/mtplx` (`depends_on arch: :arm64`) or pip. macOS 14+ | Pushed 2026-11-07. The November revive brief said MTPLX stays archived; the revive-lane YAML still registers it |

`prismml-mlx` is a harness script (`tests/benchmarks/prismml_mlx_server.py` on that lane), not an upstream product. No separate upstream version.

### Serving contract (registered)

| Engine | HTTP | Tools | Structured output | Multi-model | Prefix / KV | Batching | Memory control |
|---|---|---|---|---|---|---|---|
| oMLX | OpenAI and Anthropic, streaming. README also lists embeddings, rerank, tokenize | mlx-lm formats plus the families in the README table (Llama/Qwen/DeepSeek JSON, MiniMax, Kimi, Longcat, IFM). Template must accept `tools` | JSON schema | Yes. Directory discovery, pin, TTL, LRU | Hot RAM blocks plus SSD cold tier, survives restart. Optional Affine4/8 KV compression | Continuous batching on mlx-lm | Per-model context and a memory limit in the admin UI |
| Ollama | Native `/api/chat` plus OpenAI `/v1`. v0.40.16 notes `/v1/responses` truncation behaviour | Documented by Ollama; this lane did not re-fetch the tool-calling page | unknown here | One model resident per runner; swap is the lifecycle. Portal already depends on this | Reuses the previous request's prompt cache (Rapid-MLX README's 2026-09-26 reading of Ollama's docs, not re-verified on docs.ollama.com in this pass) | `OLLAMA_NUM_PARALLEL`. This repo's September plan records that it does not make cross-model overlap safe | `num_ctx` baked into tags. KV cache type is an Ollama setting; exact flag not re-copied here |
| mlx-serve | OpenAI, Anthropic, and Ollama, streaming, vision | README: tool calls. Parser name per family not copied from `docs/api.md` | JSON schemas | README memory table is one suggested model per RAM size. Whether two models stay loaded without a restart was an open question in `docs/MLX_SERVE_ENGINE_BENCH_V1.md` and was not re-checked | Continued-chat cache is in the 26.11.1 speed blurb (56 ms cited on an older blog). 26.11.2 notes conversation checkpoints for stateful models | Batched decode is what this host logged on v26.9.2 | `--ctx-size` in the registry argv. Disk KV flag: unknown |
| Rapid-MLX | OpenAI chat and Responses, Anthropic Messages | README: 27 parser modules plus auto-detect. Registry passes `--enable-auto-tool-choice --tool-call-parser` | unknown here | `rapid-mlx serve <alias>` is one server process per the README quick start | In-memory radix prefix cache; README says it is saved on shutdown and restored at startup. Quantized KV | Continuous batching | `--no-telemetry` is the registry fairness pin. 1.0.2 notes Desktop can unload an idle model while the API stays up |
| vllm-mlx 0.6.0 | OpenAI `/v1/*` and Anthropic `/v1/messages` | README: 19 parsers. Registry passes `--tool-call-parser` | `response_format` JSON schema via lm-format-enforcer | One `serve <model>` process in the examples | Paged KV, prefix cache, optional `--ssd-cache-dir`. Registry plain argv does not pass the SSD cache | README: continuous batching is a flag you add after the first response. Registry 0.6.0 passes `--continuous-batching` and says it is off by default | Not copied |
| mlx_lm.server | OpenAI-style chat | Tool calls when the tokenizer declares them (Rapid-MLX comparison, 2026-09-26). Open bugs below | unknown | Lists the whole HF cache (`list_models_is_cache` in the registry, measured 2026-09-23) | In-memory prompt cache. Issue `#1802`: streamed generations do not store prompt-cache entries (commented 2026-11-07) | `BatchGenerator`. Rapid-MLX's table says quantized KV is one-request-at-a-time | `--kv-bits` exists per that same table |
| llama.cpp `llama-server` | OpenAI server. Registry uses `--jinja` so the model template renders tools | Jinja tool templates. Parser is the template, not a named vLLM parser | Grammar / JSON schema exist upstream; the exact  b12284 flag set was not copied | One `-m` in the registry argv | Slot cache, `--cache-type-k/v` exist upstream; not re-copied from `llama-server --help` | Batched slots (`-np`). Registry spec cells pin `-np 1` for the draft-dspark row | `-c` context. `-ngl 99` is the registry's full-GPU pin |
| Splash | OpenAI chat, Responses, Completions; Anthropic Messages; streaming | README links a tool-call section. Parser name not copied | JSON Schema | The five families in the README table only. One model per `splash serve` | SSD cache `--max-cache-disk` (default auto, up to 32 GiB). Registry pins `0`. `--persistent-cache` is off by default; registry says do not pass it | README: batches concurrent requests. 1.0 table is the published concurrency claim | `--max-memory`, `--max-context` up to `1M`, `--kv-format` default INT8, `--language-only` |
| mlxcel | OpenAI, Anthropic, llama-server routes | Not named in the sections read. Do not assume a parser | unknown | `mlxcel-server -m` one checkpoint in the examples. Router mode is listed as a feature | Prompt-prefix cache on by default. Registry: no disk KV flag found, so none is passed | `--parallel` with `--kv-unified` so the context is not split. README: native batched decode | `--ctx-size` |
| MTPLX | OpenAI and Anthropic, streaming, optional embeddings and rerank | Registry: default tool prompt mode is `hybrid` (not the model's own template). Fairness pin is `--tool-prompt-mode native` | unknown | One pack per `mtplx serve`. Packs are Youssofal MTPLX builds, not an arbitrary mlx-community folder | SSD session cache exists. Registry pins `--ssd-session-cache off` | Not established from the pages read. Native MTP is the product, not a batch claim | `--context-window`. `--profile sustained` is the registry pin because the default resolves to Turbo for 27B/9B packs |

### Speed levers vs our seats (registered)

A cell is "supports" only when the cited page or the revive-lane registry names that family. "Unknown" means this pass did not find the sentence.

| Lever | Gemma 4 26B-A4B QAT | Qwen3.8-27B | Qwen3.6-35B-A3B | Nemotron 3.5 Lightning | Gemma 4 E4B router |
|---|---|---|---|---|---|
| MTP / native multi-token head | mlx-serve README speed table includes "Gemma 4 26B-A4B, 4-bit" with speculation on. Which head was not stated. mlxcel measured Gemma 4 **12B** plus a 4-bit assistant, not this 26B QAT | oMLX sidecar `Qwen3.8-27B-oQ4e-mtp` is seated. Registry also has MTP cells for mlx-serve, rapid-mlx, splash (DFlash2, not MTP), mlxcel. vllm-mlx registry cell is `null` | mlx-serve table lists it with speculation on. Method not stated | Registry: oMLX, mlx-serve, rapid-mlx, vllm-mlx MTP. mlxcel `null` (no separate drafter file). Splash `na` | Not a h2h model. No seat-specific MTP sentence found |
| DFlash / DFlash2 | Splash README family list does not include Gemma 4. Registry splash cell is `na` | Seated on oMLX with `incoai` DFlash2. Registry: splash, rapid-mlx, mlx-serve, mlxcel. vllm-mlx and mlx_lm.server `null` | Splash family row, DFlash2 draft selected automatically | Splash `na`. No DFlash sentence found for this MoE in the Splash README | unknown |
| DSpark | Not in the registered engines' own pages for this checkpoint | Splash is DFlash2, not DSpark. mlx-dspark (not registered) is below | unknown on registered engines | unknown on registered engines | unknown |
| Prompt-lookup, no drafter | mlx-serve plain mode must pass `--no-pld` because PLD defaults on (registry comment, carried from 26.9.2) | same | same | same | same |
| Quantisation we already store | MLX QAT 4-bit plus Ollama GGUF QAT tags | MLX 4-bit, oQ4e MTP, GGUF Q4_K_M | MLX UD 4-bit and GGUF | oQ4e MTP and GGUF Q4_K_M | GGUF Q4_K_M router tag. MLX E4B was removed from `omlx-local` per the comment in `backends.yaml` |
| Concurrent batching | mlxcel README names Gemma 4 among native batched families. Others: the engine's general batch flag, not a Gemma-specific sentence | oMLX, mlx-serve (this host logged GDN batched decode on v26.9.2), Splash, Rapid-MLX, vllm-mlx when the flag is on, mlxcel | Splash and Rapid-MLX publish 4-stream numbers. mlx-serve publishes a single-stream number only in the current README | unknown as a named batch result | unknown |

Ollama has no speculative cell in the registry (plain only). That is a harness fact, not a claim that llama.cpp inside Ollama 0.40.16 cannot do MTP. Ollama's 0.40.16 notes do not mention MTP.

Rapid-MLX's comparison table says Ollama on a Mac is "GGML/GGUF engine, plus an MLX engine for safetensors models" (README, feature facts dated 2026-09-26). Ollama's own v0.40.16 notes do not say that. This repo has already recorded the opposite for the old MLX proxy (`docs/MLX_SERVE_ENGINE_BENCH_V1.md`: Ollama on this host is GGUF via its Metal path). The Rapid sentence stays an unverified vendor sentence.

## Not registered, and plausible on this Mac

| Engine | Version | Date | Licence | Native arm64? | Contract, in one line | Why it is or is not a new registry row |
|---|---|---|---|---|---|---|
| vLLM Metal `vllm-project/vllm-metal` | Stable `v0.33.0`. Dev tags continue (`v0.33.0.dev20261111083610` on 2026-11-11) | 2026-11-04 | Apache-2.0 | Yes. macOS 15+, Apple Silicon, arm64 CPython 3.12 wheels. `brew install vllm-project/vllm-metal/vllm-metal` or the install script. Docs: `pip install vllm-metal` is not supported. Prebuilt wheels, no Metal compiler | Upstream vLLM V1/V2 scheduler and OpenAI server, MLX for the model, paged KV. Blog 2026-09-22 shows `vllm serve`, `--gpu-memory-utilization`, `--max-model-len`, `--no-async-scheduling`, `--speculative-config` MTP. Tool-parser flags are upstream vLLM; this pass did not see a Metal-specific page that lists which parsers pass | **Candidate.** See below |
| lithos-metal `lithos-ai/lithos-metal` | `v0.1.2` | 2026-10-05. Blog 2026-10-08 | Apache-2.0 | Yes. `brew install lithos-ai/tap/lithos-metal`. macOS 26+ per README. M4 Pro 20-core is a "measured profile"; M4 Pro 16-core is "unmeasured native fallback". This lane did not read the host's GPU core count | `lithos-metal serve --model …`. Chat, Responses, Anthropic, Ollama `/api/chat`, tools, SSE. Default `127.0.0.1:8000`, 32K context, `--max-context`, `--no-draft`, `--draft`. **One generation at a time** (README). DSpark on Qwen3.8-27B NVFP4 and affine 4-bit, and experimental Qwen3.6-35B-A3B NVFP4 | Candidate, lower. No host/port flag was copied. Single-flight conflicts with the concurrency question that decided Splash |
| mistral.rs `EricLBuehler/mistral.rs` | `v0.9.5` | 2026-10-19 | MIT | README: Metal, and paged attention is the default on supported Metal models in 0.9.5. Install feature flags were not copied from the quickstart | `mistralrs serve`: OpenAI `/v1` and Anthropic Messages, continuous batching, prefix cache, GGUF, Gemma 4, Qwen3.8-Flash-Next. Published speed tables in the README are GB10 / B200 / H100, not Apple | Candidate only if a non-MLX Metal stack is still an open question after the MLX servers |
| mlx-dspark `ARahim3/mlx-dspark` | No release tag fetched before rate limit. Repo pushed 2026-11-08. PyPI badge on the README; version number not copied | README measured-table date context includes 2026-08-19 and a long-context section dated 2026-09-27 | MIT | Yes. Apple Silicon only. OpenAI-compatible server is claimed; the serve argv was not copied | Lossless DSpark and DFlash. Vouched table includes Qwen3.8-27B 4-bit DFlash2, Qwen3.6-35B-A3B 4-bit, Nemotron 3.5 Lightning 4-bit, Gemma 4 **12B**. Gemma 4 26B-A4B is not in that vouched table | Not a general server candidate. A drafter A/B, and only for families the table names |
| LocalAI `mudler/LocalAI` | `v4.12.1` | 2026-10-23 | MIT | README: Apple Silicon Metal, MLX and MLX-VLM backends, unsigned DMG | Multiplexer over llama.cpp, MLX, and others. OpenAI-compatible | Not worth its own bench. The backends are the engines above |
| `mudler/vllm.cpp` | Release tag unknown (releases API rate-limited). Pushed 2026-11-11 | unknown | Apache-2.0 | LocalAI's README says this backend runs on Metal as well as CPU, CUDA, Vulkan | C++ vLLM-alike: paged KV, continuous batching, GGUF, radix cache. Tool-parser and serve flags not read | Not worth ahead of vLLM Metal. Revisit only if the Python plugin cannot load a seated checkpoint |
| exo `exo-explore/exo` | Latest GitHub release `v1.0.71` | 2026-04-23. Main pushed 2026-11-06 | Apache-2.0 | MLX backend, RDMA over Thunderbolt, clusters Macs | OpenAI, Anthropic, Responses, Ollama API. Product is a device cluster | Not worth on one M4 Pro. Last tagged release is seven months behind main |
| llamafile `mozilla-ai/llamafile` | `0.10.6` | 2026-09-15 | Apache-2.0 (README badge). GitHub API `NOASSERTION` | Cosmopolitan single file; Metal comes from the bundled llama.cpp, which lags `b12284` | One-file server | Not worth. `brew-llama` is the current llama.cpp |
| ik_llama.cpp `ikawrakow/ik_llama.cpp` | Last release tag `t0002` | 2025-07-22. Main pushed 2026-11-11 | not re-fetched | llama.cpp fork. Apple build not confirmed from a README section in this pass | Quant-specialised GGUF fork | Not worth a first bench. Our GGUF baseline is already upstream `llama-server`, and no Apple Q4_K_M claim was fetched |
| mlx-omni-server `madroidmaq/mlx-omni-server` | No GitHub releases. Last push 2026-05-09 | stale relative to 2026-11-11 | MIT | Apple Silicon MLX, OpenAI and Anthropic | Wrapper over mlx-lm | Not worth. Upstream is `mlx_lm.server`, and this repo has not moved since May |
| Nexa / GenieX `NexaAI/nexa-sdk` | `v0.10.0` stable; newer tags are prereleases | 2026-10-28 | BSD-3-Clause | README and homepage describe Qualcomm NPU/GPU/CPU, not a Mac | — | Out of scope |
| koboldcpp `LostRuins/koboldcpp` | `v1.124.2` | 2026-10-31 | not re-fetched | Metal builds exist historically; not re-read | Story API, not our tool contract | Not worth |
| Upstream vLLM without the Metal plugin | `v0.33.0rc3` is the core the Metal plugin tracks | 2026-11-02 | Apache-2.0 | No. CUDA/ROCm wheels. The Mac path is `vllm-metal` | — | Not a candidate |

Lily (`RavenXAILabs/lily-engine`, 1 star, pushed 2026-09-03) and Uzu appear as names in the vLLM Metal blog's engine table (2026-09-22). The only GitHub hits found were tiny forks. No maintained upstream release was identified. Treated as unknown, not as candidates.

Apple's 2026-10-15 MLX distributed post (`machinelearning.apple.com/research/mlx-distributed-inference`) runs `mlx_lm.server` across two or four Mac Studios with RDMA Thunderbolt. That is the same `mlx_lm.server` already registered, on hardware this host is not. The post's own warning, as quoted by a secondary write-up and not re-read on the Apple page's warning box in full: `MLX_METAL_FAST_SYNCH=1` can deadlock. Not a single-host candidate.

## Claims, as published

Conditions are only what the source stated. Blank means the source did not say.

### Vendor claims

| Source | Who | Date | Hardware | Model | Concurrency | Prompt / output | Number | Not stated |
|---|---|---|---|---|---|---|---|---|
| mlx-serve README, v26.11.1 table | vendor | page fetched 2026-11-11; release v26.11.1 is 2026-11-01 | M5 Ultra, 256 GB | Qwen3.6-35B-A3B 4-bit | one stream implied ("decode speed") | "a code prompt"; lengths absent | 421 tok/s | batch, output length, which spec method, acceptance |
| same | vendor | same | same | Qwen3.8-27B 4-bit | same | same | 243 tok/s | same |
| same | vendor | same | same | Gemma 4 26B-A4B 4-bit | same | same | 184 tok/s | same. Not our QAT checkpoint unless they used it, which they do not say |
| same | vendor | same | same | Gemma 4 E4B 4-bit | same | same | 200 tok/s | same |
| same README | vendor | same | M4 Max, models "the same" | same four | same | same | "10% to 51% faster than v26.8" | per-model split |
| mlx-serve blog `why-mlx-serve-is-fast` | vendor | 2026-09-22, release 26.9.5 | M4 Max, 128 GB | Qwen3.6-35B-A3B 4-bit with MTP | 1 | "code prompt"; median of 3 llmprobe runs | 239 tok/s | prompt and output lengths |
| same blog | vendor | same | same | Qwen3.8-27B 4-bit | 4 chats | not stated | 119 tok/s combined; one chat 70 | prompt length |
| same blog | vendor | same | same | Gemma 4 26B-A4B | continued chat | 1,431 tokens from cache | 56 ms to first token; cold 929 ms | decode tok/s |
| Rapid-MLX README, vs mlx-lm | vendor | measured 2026-10-04, Rapid-MLX 0.15.6 vs mlx-lm 0.32.0 | Mac mini M4 Pro, 48 GB (not this 64 GB host) | Qwen3.5-9B 4-bit, same HF weights, greedy, both at defaults | 1 | "whole-file code edits" for the 198.4 figure; 18 stream tasks for the median | 198.4 vs 46.4 tok/s on that edit; median decode 1.50×; 1.37× end to end over 20 tasks | output length of the median task |
| same page, as quoted on the README | vendor | 2026-10-04 | same | Qwen3.6-35B-A3B 4-bit | best task | not on the README | 3.16× vs mlx-lm | full conditions live on the compare page, not copied here |
| Rapid-MLX README vs oMLX and LM Studio | vendor | README fetched 2026-11-11; versions Rapid-MLX 0.16.1, oMLX 0.7.0 | Mac Studio M5 Max, 36 GB | Qwen3.5-9B, Qwen3.8-27B, Qwen3.6-35B, "same base 4-bit weights" | 1 and 4 streams | 2K prompt for the TTFT row only | Qwen3.8 decode 37.9 / 25.3 / 26.0 tok/s; 4-stream 82.8 / 75.3 / 69.7. Qwen3.6 decode 173.4 / 145.8 / 124.5; 4-stream 293.9 / 281.9 / 265.6; TTFT 0.55 / 1.14 / 1.49 s | sampling, output length, thinking on or off. Footnote: single run; Rapid MTP text mode; oMLX SSD cache on; LM Studio context and four slots as configured |
| Splash README, Splash 1.0 launch table | vendor | README fetched 2026-11-11; table is Splash 1.0, not 1.6.1 | M5 Pro 16-core, 48 GB; Flash-Next row is M5 Pro 20-core, 64 GB | Qwen3.6-35B-A3B, Qwen3.8-27B, Flash-Next Q2_0 GGUF | 1 and 4 | "selected SPEED-Bench coding prompts"; 32K prefill row | 35B decode 210 tok/s (1.7× the next engine); 27B 74 (2.0×); 4-concurrent 357 and 170 | the other engine's name on the 1.0 table; output length |
| Splash README, GGUF vs llama.cpp | vendor | same page | M5 Pro 20-core and M3 Max 40-core | Unsloth UD-Q4_K_M 27B and 35B-A3B | 1 | not stated. Splash used BF16 KV and `--disable-ane` | 27B: llama.cpp 16, llama.cpp+MTP 27, Splash 74 on the M5 Pro. 35B: 69 vs 74's sibling 175 | output length, llama.cpp build, MTP depth |
| Splash 1.6.0 release notes | vendor | 2026-11-06 | M5 Max 36 GB, `--max-memory 18G` | Qwen3.8-Flash-Next Q2_0 | concurrent, count not stated | "the same load" | longest stream pause 300–406 s on 1.5.0 to 0.92 s; prefill 1.27×, decode 1.25×, TTFT −26% vs 1.5.0. Single-request decode within 2% of 1.5.0 | absolute tok/s, prompt length |
| Splash 1.6.1 release notes | vendor | 2026-11-11 | "On M5 and later" | Qwen3.8-27B MLX 4-bit | not stated | not stated | "about 25% lower TTFT" | absolute TTFT, prompt length. Also: default `--activations auto` uses INT8 on some paths, so outputs can differ from 1.6.0 |
| MTPLX HISTORY / README | vendor | 2026-09-16, MTPLX 2.11.3 | M5 Max (memory not in the row copied) | Qwen 3.8 Flash Next Optimized Speed | 1 OpenCode request | 18,539-token prompt, 18,364 from cache, 1,301 generated, MTP depth 3 | 125.8 tok/s | not our seat, and not this host |
| MTPLX, 2 July 2026 log note on the how-it-works page | vendor | 2026-07-02 | M5 Max | Qwen3.6-27B Optimized Speed | 1 | 192-token bench, depth 3, thinking off, temp 0.6 / top_p 0.95 / top_k 20 | 81.74 tok/s vs 30.37 without MTP | hardware memory |
| mlxcel README | vendor | v0.6.0 exactness policy; page fetched 2026-11-11 | M5 Max | Gemma 4 12B + 4-bit assistant | 1 | a code prompt, and separately a 14-token sweep prompt | 93.2 vs 43.8 tok/s greedy (2.13×, byte-identical); 14-token prompt 70.9 vs 45.3 (1.57×, K=4, 35% acceptance) | not the 26B-A4B seat |
| mlxcel README | vendor | 0.8.1 sweep, text 2026-11-03 | GB10 (NVIDIA), not a Mac | 111 text checkpoints, pp512/tg128 | 1 | 512 prompt / 128 generated | median decode ratio 1.026 vs their 0.4.0-rc.1 | irrelevant to this host except as a warning that their headline host is not a Mac |
| lithos-metal README | vendor, and they say it is a projection | page fetched 2026-11-11; blog 2026-10-08 said "more than 200 tokens per second" on M5 Max | 40-core M5 Max, 48 GB | Qwen3.8-27B-NVFP4 | the README says one generation at a time | assumes six accepted tokens per eight-row target pass | projection 168 tok/s at 128 context, 127 at 32K | **excludes drafting, acceptance, and rewind**. Not an end-to-end rate. The 200 tok/s blog sentence is the same study's marketing line |
| mlx-dspark README | vendor | table fetched 2026-11-11; long-context section dated 2026-09-27 | M4 Pro (RAM and core count not in the header) | Qwen3.8-27B 4-bit, DFlash2 | 1, warm, median of 3 | short chat/code/math prompts | 3.17× code, 3.13× math, 2.49× chat, about 37–47 tok/s | prompt token length in the header table. They point at a separate 16k–32k section |
| same | vendor | same | same | Nemotron-3.5-Lightning 4-bit | same | same | 1.34× math, 1.27× code, 1.07× chat, about 87–112 tok/s | same |
| same | vendor | same | same | Qwen3.6-35B-A3B 4-bit | same | same | 1.67× math, 1.24× code, 1.05× chat, about 91–145 tok/s | same |
| vLLM blog 2026-09-22 | vendor | 2026-09-22, around v0.28.0 | not a tok/s table | comparison of batching style only | — | — | no tok/s in the section read | the blog contrasts packed prefill plus paged KV (vLLM Metal) with contiguous KV (oMLX, Splash, mlx-lm, llama.cpp). No Apple tok/s number was on that page section |
| mistral.rs README v0.8.2 tables | vendor | page fetched 2026-11-11 | GB10, B200, H100 | Gemma 4 E4B and 26B-A4B, Q8 and BF16 | mean across prompt lengths | decode depth 128–16384, 256 generated | e.g. 26B-A4B Q8 decode on GB10: 46.8 vs llama.cpp 46.4 | **not Apple**. Do not import these as Mac numbers |
| vllm-mlx README | vendor | page fetched 2026-11-11; the install pin in the same README is 0.4.1 while the tag is 0.6.0 | M4 Max, 128 GB, greedy, single stream | Qwen3-30B-A3B-4bit | 1 | not stated | 127.7 tok/s, ~18 GB | not our Qwen3-Coder checkpoint unless it is the same weights, which they do not say. No Qwen3.8 / Gemma 4 / Nemotron row |

### Numbers already recorded on this host

These are this repository's measurements. This lane did not re-run them.

| Source | Date | Hardware | What | Number | Conditions stated there |
|---|---|---|---|---|---|
| `docs/MLX_SERVE_ENGINE_BENCH_V1.md` | the doc does not date the run; it tests mlx-serve **v26.9.2** | this machine, M4 Pro, 64 GB, macOS 27.0 (26A428) | mlx-serve vs Ollama, Qwen3.8-27B | decode 14.89–15.34 vs 12.4–12.7 tok/s; 4-concurrent aggregate 43.19 vs 12.7; prefill 114.9 tok/s on a 284-token tool prompt | fixed ~400-word prompt, `max_tokens=400`, thinking off, temperature 0.3, 3 sequential rounds then one 4-wide round. Ollama column is cited from the Splash bench doc, not re-measured that day |
| same doc, citing `docs/SPLASH_ENGINE_BENCH_V1.md` | same | same weights | Splash | 17.8–21.1 tok/s single; 26.2 tok/s at 4 concurrent | Splash lost the keep-or-not decision on concurrency behaviour, not on the single-stream number |
| `config/backends.yaml` comment on `Qwen3.8-27B-oQ4e-mtp` | 2026-08-14 | this host, same prompt/session as the Ollama baseline | oMLX Lightning MTP | 17.5–18.6 tok/s vs Ollama GGUF 12.25; draft accept 60–65% | tool probe passed. Comment says the plain mlx-community 4-bit has no MTP tensors |
| `config/backends.yaml` comment on Nemotron oQ4e-mtp | 2026-08-14 | same | oMLX MTP | 70.0–70.3 vs Ollama 52.9–53.1 tok/s; accept 76–87% | tool probe passed |
| `docs/MIMO_V26_DISTILL_9B_BRINGUP_V1.md` | 2026-09-21 | this host, isolated, no swap pressure | Ollama MiMo 9B Q4_K_M, full 262144 ctx | about 36 tok/s decode, 11 GB resident | The head-to-head against Laguna was invalidated (two requests in flight, swap). Do not cite a winner from that doc |

Headline pattern, from those sources only: single-stream gaps on this host have been about 1.2–1.6×, while 4-wide aggregate is where batching showed up (mlx-serve 43 vs Ollama 13 vs Splash 26 on that Qwen3.8 setup). Vendor tables at 200 tok/s are M5 Ultra or M5 Max, speculative, and not this machine.

## Blockers

| Item | Why it blocks or distorts a Portal bench | Link |
|---|---|---|
| lithos-metal serves one generation at a time | Cannot answer the concurrency question. Also a 64 GB host with a resident router cannot use a second full seat if the engine will not overlap | README serving section, fetched 2026-11-11 |
| lithos headline rates are projections | README: excludes draft, accept, and rewind, and "are not measured end-to-end generation rates" | `lithos-ai/lithos-metal` README performance section |
| lithos numerical drift | Open issue: exact prompt passes are not bit-exact where attention auto-picks v3. Input-norm fusion changes BF16 rounding unless `--no-commute-norm` | https://github.com/lithos-ai/lithos-metal/issues/81 |
| vLLM Metal single-stream decode bandwidth | Open: paged single-sequence decode attention ~40 GB/s vs ~200 GB/s achievable. A single-stream loss would not by itself kill the engine; it is a known gap | https://github.com/vllm-project/vllm-metal/issues/695 |
| vLLM Metal KV residency | Open: lazily allocated KV pool is fully resident after warmup. On 64 GB beside a router this can evict the seat or the router | https://github.com/vllm-project/vllm-metal/issues/1198 |
| vLLM Metal text Qwen3.5 | Open: `qwen3_5_text` fails on the MLX backend (`No module named mlx_lm.models…`). Our Qwen seats are 3.6/3.8, so this is a watch item, not a proven block | https://github.com/vllm-project/vllm-metal/issues/1273 |
| mlx-lm server drops a bad tool-call span | Open: invalid JSON in a tool-call span is dropped, `finish_reason` still reports tool calls, content empty. oMLX uses mlx-lm parsers, so this can apply beyond `mlx_lm.server` | https://github.com/ml-explore/mlx-lm/issues/2019 |
| mlx-lm prompt cache and SSM leak | `#1802` streamed generations do not store prompt-cache entries (comments through 2026-11-07). `#1845` `ArraysCache.advance()` leaks a Metal buffer per SSM layer per token on long completions (comments through 2026-11-07). Qwen3.8 is a hybrid SSM/attention model | https://github.com/ml-explore/mlx-lm/issues/1802 and https://github.com/ml-explore/mlx-lm/issues/1845 |
| Mistral Small 3.2 tools on mlx-lm | Open `#1639`. Matches this repo: `omlx-general` marks that conversion `supports_tools: false` | https://github.com/ml-explore/mlx-lm/issues/1639 |
| Granite 4.1 8B mxfp8 on oMLX | This repo, not an upstream ticket: with tools, the nightmedia conversion inserts U+200B and splits names. Alias removed. The Ollama GGUF is the seat. An engine bench of "Granite 8B on MLX" that ignores this will look like a tool-parser win or loss when it is the checkpoint | `config/backends.yaml` comments, 2026-10-17 and 2026-11-09 |
| Splash model list | Only Qwen3.8-27B, Qwen3.6-35B-A3B, Ornith-1.5-122B, Qwen3.8-Flash-Next, Flint. No Gemma 4, no Nemotron, no Granite, no Qwen3-Coder. 1.6.1 changes INT8 activations by default on M5 and later, so a 1.5.0 vs 1.6.1 quality compare is not the same graph | Splash README and 1.6.1 notes |
| Splash 1.5.0 stalls under a memory cap | 1.6.0 notes say 1.5.0 made all cached KV resident for every GPU command and decode slowed up to 5.8× near the GPU memory limit, and records multi-minute stalls. The revive registry still pins 1.5.0 | https://github.com/incoai/splash/releases/tag/1.6.0 |
| mlx-serve PLD default | Plain runs that forget `--no-pld --no-drafter --no-mtp` are speculative. Registry already pins this | revive-lane `engine_h2h.yaml` |
| MTPLX tool prompt default and footer | Default `hybrid` tool prompt is not the model template. `--no-stats-footer` or a TPS footer is appended to replies. Attribution line is a licence condition | MTPLX README and the registry comments |
| Rapid-MLX telemetry | Registry keeps `--no-telemetry`. Do not drop it; a bench that phones home is not a local measurement | revive-lane registry |
| Ollama cross-model overlap | Two models in flight deadlocked Ollama on 2026-09-21. Any new engine still shares the 64 GB with the router. The harness lock exists for this | `docs/MIMO_V26_DISTILL_9B_BRINGUP_V1.md` |
| llama.cpp inside other apps | LM Studio's app is closed source. Its `mlx-engine` repo is MIT and pushed 2026-11-03, but it is a library, not a pinnable `serve` binary with a published fairness pin. Skipped as a registry row for that reason | https://github.com/lmstudio-ai/mlx-engine |

Closed, so not a current block: vLLM Metal `#622` (garbage token at temperature > 0, closed 2026-08-25) and `#479` (EngineCore livelock, closed 2026-07-13). They are history, not a reason to skip the engine.

## Proposed registry candidates

Not applied. Ports continue from 11243. The orchestrator checks `file` is arm64 and `--help` still contains every flag before a live run. Flags below are only ones a primary page showed, except where a line says the flag is the usual upstream CLI and was not on the Metal page.

### vllm-metal — add

```yaml
vllm-metal:
  kind: managed
  requires: mlx
  port: 11244
  version: "0.33.0"
  # brew tap vllm-project/vllm-metal https://github.com/vllm-project/vllm-metal
  # brew install vllm-project/vllm-metal/vllm-metal
  # Stable channel is the 2026-11-04 release. Dev install script tracks main; do not use it for the bench.
  # macOS 15+, arm64, the formula's Python is 3.12. Refuse an x86_64 wheel.
  # Docs say pip install vllm-metal is unsupported.
  # --host and --port are upstream vLLM CLI; the 2026-09-22 Metal blog did not print them.
  # Confirm with `vllm serve --help` before trusting them.
  # No SSD-cache flag was in the blog examples. Do not add one.
  # --gpu-memory-utilization 0.7 is the blog's 64 GB example for Qwen3.8-27B-4bit.
  # Tool parser: do not pass --tool-call-parser until --help on this install lists it.
  # Think-off: blog does not show a think flag. Preflight must show whether
  # chat_template_kwargs.enable_thinking is honoured. If it is not, mark the cell REVIEW.
  plain: [vllm, serve, "{mlx_root}/{model_dir}", --host, 127.0.0.1, --port, "{port}", --gpu-memory-utilization, "0.7", --max-model-len, "{ctx}"]
  base_spec: [vllm, serve, "{mlx_root}/{model_dir}", --host, 127.0.0.1, --port, "{port}", --gpu-memory-utilization, "0.7", --max-model-len, "{ctx}", --no-async-scheduling, --speculative-config, "{spec_json}"]
```

Spec JSON only where a page names the pair. The blog's example is Gemma 4 **E4B**, not the 26B QAT seat:

`{"method":"mtp","model":"mlx-community/gemma-4-E4B-it-assistant-bf16","num_speculative_tokens":1}`

For Qwen3.8-27B and Nemotron, MTP method name on this plugin was not copied from a model matrix. Leave those spec cells unset until `docs/supported_models.md` on the v0.33.0 tag is read at bench time. A plain cell is still worth running.

Fairness: one model, no sleep-mode flag (the October notes describe a sleep mode that returns memory; do not enable it mid-bench), no second Mac.

### lithos-metal — add only if the orchestrator wants a single-stream Qwen3.8 cell

```yaml
lithos-metal:
  kind: managed
  requires: mlx
  port: 11245
  version: "0.1.2"
  # brew install lithos-ai/tap/lithos-metal
  # Default bind is 127.0.0.1:8000. A --port flag was not in the README. If --help has no port flag, do not register it; do not move the live oMLX off 8085 to free 8000.
  # Plain must pass --no-draft. Spec is the default DSpark head.
  # --no-commute-norm keeps the BF16 rounding the README says fusion changes.
  plain: [lithos-metal, serve, --model, "{model_id}", --no-draft, --no-commute-norm, --max-context, "{ctx}"]
  base_spec: [lithos-metal, serve, --model, "{model_id}", --no-commute-norm, --max-context, "{ctx}"]
```

`{model_id}` for the documented 4-bit pair is `mlx-community/Qwen3.8-27B-4bit` (README says the automatic draft is `LithosAI/Qwen3.8-27B-DSpark-NVFP4` even for the affine 4-bit target). Gemma 4 and Nemotron are not in the automatic table. Skip them.

### mistral.rs — do not add until the install line is copied from its quickstart

`mistralrs serve` is the command the README names. The Metal feature flag, the model-id flag, and the think-off flag were not on the pages saved here. Inventing a `cargo install` line would be a guess. If it is added later: port 11246, paged attention left at the 0.9.5 default, no extra quant flag, one Apple-silicon wheel only.

### Version bumps on rows that already exist

These are not new engines. The revive lane pinned older builds. Whether to move the pin is the orchestrator's call before that bench, because 1.6.x Splash changes outputs (`--activations auto`).

| Registry pin | Current upstream | Why it matters |
|---|---|---|
| splash 1.5.0 | 1.6.1 (2026-11-11) | 1.6.0 says it fixed 1.5.0's memory-limit stalls and the "all KV resident" decode tax |
| mlx-serve 26.11.1 | 26.11.2 (2026-11-06) | GGUF-on-MLX path and conversation checkpoints. The speed table cited above is still labelled 26.11.1 |
| rapid-mlx 1.0.1 | 1.0.2 (2026-11-06) | 1.0.2 notes are video and Desktop idle-unload, not a decode claim |
| mtplx comment 2.12.0 | 2.12.3 (2026-11-06) | Already registered. The November brief said leave it archived |

## Ranked bench shortlist

Order is which live cells are worth the orchestrator's quiet-host time. It is not a predicted ranking of speed.

1. **vLLM Metal 0.33.0, plain, three seats: Gemma 4 26B-A4B QAT, Qwen3.8-27B-4bit, Nemotron oQ4e.** It is the upstream vLLM scheduler on MLX, it is not in the registry, and the open KV-residency bug (`#1198`) is exactly the 64 GB failure mode worth knowing before any longer run. Concurrency n=1 and n=4 is the useful pair, because `#695` says single-stream decode is the weak path. MTP only for a pair the v0.33.0 model matrix names. Tool preflight is the quality gate; a faster wrong tool call is not a win.
2. **Splash 1.6.1 against the 1.5.0 pin, Qwen3.8-27B and Qwen3.6-35B-A3B only, n=1 and n=4, disk cache off, `--activations bf16` on one arm and the new default on another.** 1.6.0's own notes say 1.5.0 stalled under a memory cap. That is the property that made Splash lose here in September. Gemma 4 and Nemotron are out of its family list, so they are not cells. Flint stays the operator's Splash-only arm already in the registry.
3. **The engines already pinned on the revive lane, at those pins, before any new engine.** oMLX and Ollama are the production baselines. mlx-serve, Rapid-MLX, mlxcel, and vllm-mlx already have argv. Re-measuring them is the only way the vendor M5 numbers become comparable. This lane does not reorder that harness.
4. **lithos-metal, one plain and one DSpark cell, Qwen3.8-27B-4bit, n=1 only.** Only after (1) and (3). The README already says it will not batch, and the tok/s figure is a projection. Stop if `--help` has no way to bind a non-8000 port or if the M4 Pro falls through to the unmeasured 16-core backend.
5. **mistral.rs 0.9.5, one plain cell, Qwen3.8 or Gemma 4, only if the quickstart install is an arm64 Metal wheel and does not pull CUDA.** No Apple tok/s claim was published in the README. The NVIDIA tables are not a reason to spend the slot.

Not worth bench time:

- **LM Studio.** Closed app, defaults are a GUI profile. Vendor comparisons already include it; we would not be able to pin the same fairness flags.
- **llamafile, ik_llama.cpp, LocalAI, vllm.cpp.** They are llama.cpp or a second vLLM, behind a current `llama-server` or behind vLLM Metal, and no Apple claim for our checkpoints was fetched.
- **exo.** Cluster product. Last release 2026-04-23. This host is one machine.
- **mlx-omni-server.** Last push 2026-05-09. Superseded by `mlx_lm.server`, which is already the slow reference in the registry.
- **mlx-dspark as its own server.** The vouched M4 Pro numbers are a drafter result. If DSpark on Nemotron or Qwen3.8 is the question, run it as a spec method inside an engine that already loads those weights, not as a new product.
- **Nexa/GenieX, koboldcpp, upstream CUDA vLLM, Apple's multi-Mac `mlx.launch`.** Wrong hardware, wrong contract, or wrong machine count.
- **MTPLX as a new row.** It is already in the revive YAML. The November brief said to leave it archived. This doc does not reopen that.

## Sources touched

GitHub API and raw READMEs, 2026-11-11: `jundot/omlx`, `ollama/ollama` (tag `v0.40.16`), `ddalcu/mlx-serve` (tags `v26.11.1`, `v26.11.2`), `raullenchai/Rapid-MLX` (`v1.0.2` and README), `waybarrios/vllm-mlx`, `ml-explore/mlx-lm`, `ml-explore/mlx`, `ggml-org/llama.cpp`, `incoai/splash` (`1.6.0`, `1.6.1`, README), `lablup/mlxcel`, `vllm-project/vllm-metal` (`v0.33.0`), `vllm-project/vllm`, `youssofal/MTPLX`, `EricLBuehler/mistral.rs`, `exo-explore/exo`, `mudler/LocalAI`, `mudler/vllm.cpp` (metadata only), `mozilla-ai/llamafile`, `lithos-ai/lithos-metal`, `ARahim3/mlx-dspark`, `madroidmaq/mlx-omni-server`, `lmstudio-ai/mlx-engine` (metadata), `NexaAI/nexa-sdk`, `ikawrakow/ik_llama.cpp`, `LostRuins/koboldcpp`, `PrismML-Eng/llama.cpp` (metadata).

Other primary pages: https://vllm.ai/blog/2026-09-22-vllm-metal-v0-28-0 , https://mlxserve.com/blog/why-mlx-serve-is-fast/ , https://rapidmlx.com/compare/mlx-lm (as linked from the README; the README table is what was copied), https://machinelearning.apple.com/research/mlx-distributed-inference (distributed MLX; secondary write-ups were not used as numbers).

Issue search was GitHub's search API. Releases for `mudler/vllm.cpp` and a second PrismML call returned HTTP 403 after the first burst. Those versions stay unknown.
