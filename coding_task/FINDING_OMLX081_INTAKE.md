# FINDING — oMLX 0.8.1 intake: harness LoRA adapters + Inkling 2 Mini

Lane `lane/omlx081-intake`, 2026-11-20/21. Everything below marked **read** was read from a
source at the URL/commit named with it; everything marked **verified locally** was executed on
this host. Nothing here was proven against the live oMLX server or the live Pipeline — the
orchestrator runs that (see `## Handoff` for the exact commands).

## 1. Research (perishable — re-check at intake time)

### 1.1 `harness-hub/Qwen3.8-27B-opencode-adapted` — read 2026-11-21T02:2xZ

- Repo sha `181c2c3f3db612e7a7083c6d2ba6a3e3057ed58d`; created 2026-11-16, last commit
  `Update README.md` 2026-11-20T13:55Z. The weights have not changed since upload — every
  commit after 2026-11-16 is README/card art.
- PEFT LoRA, `base_model_name_or_path: Qwen/Qwen3.8-27B`, `r=32`, `lora_alpha=64`,
  `lora_dropout=0`, `bias=none`, `modules_to_save=null`, `use_dora=false`,
  `target_modules: gate_proj, k_proj, up_proj, v_proj, q_proj, o_proj, down_proj`,
  `init_lora_weights: true`, `task_type: CAUSAL_LM`.
- Files: `adapter_model.safetensors` 637,610,624 B (608 MiB), plus `chat_template.jinja`
  (9,004 B), `tokenizer.json` (19,989,339 B), `tokenizer_config.json` (2,486 B).
- Card sampling: **thinking off, temperature 0.8, top-p 1.0** (its training sampling), one
  attempt per task, 100-step budget, text only (vision tower not served), 131,072-token
  context, 32k output cap per model call.
- Card results (OpenCode, thinking off, paired on the same tasks): SWE-bench Pro (hard 51)
  **35.3% → 51.0%** (+15.7 ±13.9, p=0.057); Terminal-Bench 2.1 46.4% → 52.4%; the 66
  non-selected TB2.1 tasks 45.5% → 59.1% (p=0.035). Generated tokens per task 1.9k vs 6.8k
  on SWE-bench Pro — the 6–8× is against the **base at `xhigh` thinking** (31.8k vs 3.9k).
- Card on thinking: "Keep thinking off: turning it on for the adapter adds nothing
  significant" (51.0 → 54.9 on SWE-bench Pro, 53.0 → 56.6 on TB2.1, ~6× the tokens).
- Hardware behind the numbers: 2× NVIDIA B200 per harness, vLLM. **None of it is this host.**
- GGUF: `harness-hub/Qwen3.8-27B-opencode-adapted-GGUF`, `Qwen3.8-27B-opencode-lora-F16.gguf`
  318,802,400 B. Card pairs it with a **`Q8_0`** base ("the closer the base GGUF is to the
  BF16 weights, the closer you get") and states the GGUF version **has not been re-evaluated**.

### 1.2 `harness-hub/Qwen3.8-27B-pi-adapted` — read 2026-11-21T02:2xZ

- Repo sha `3cad999e2b9ec72fea8d802cc286e4502adfa082`; created 2026-11-16, last commit
  2026-11-20T13:55Z (`Update README.md`); the 2026-11-19 commit is a **score correction**
  (thinking-on SWE-bench Pro 64.7/66.7 → 74.5/74.5).
- Same adapter shape as 1.1 (PEFT, r32/a64, same 7 targets, same 608 MiB), different RL run.
- Card sampling: **identical — thinking off, temperature 0.8, top-p 1.0**; pi harness,
  131,072-token context, 32k output cap.
  *One inconsistency for the record*: the card's Llama.app example block sets `temp = 0.7`,
  `ctx-size = 32768`. That block is the app's generic example, not the evaluation; the
  evaluation sampling above (0.8/1.0) is what the numbers were produced with.
- Card results (pi, thinking off): SWE-bench Pro 39.2% → **64.7%** (+25.5 ±14.2, p=0.0023);
  Terminal-Bench 2.1 39.5% → 55.8% (+16.3 ±9.1, p=0.0013).
- pi-specific gotcha the card calls out: `~/.pi/agent/models.json` needs
  **`"api": "openai-completions"`**, otherwise pi uses the Responses API, "which this adapter
  was not trained or evaluated with".
- GGUF: `harness-hub/Qwen3.8-27B-pi-adapted-GGUF` — `Qwen3.8-27B-pi-lora-F16.gguf`
  318,802,304 B **and** `Qwen3.8-27B-pi-Q8_0.gguf` 28,595,763,840 B (a full base, not just
  the adapter).

### 1.3 Newer / sibling variants in the adapter family — read 2026-11-21

`harness-hub` publishes 11 Qwen3.8-27B entries. The relevant ones:

| Repo | What it is | Verdict for this brief |
| --- | --- | --- |
| `Qwen3.8-27B-super-adapter` | One LoRA merging pi + Hermes + opencode adapters (1,912,679,616 B) | **Not a substitute.** Its card recommends **thinking on** — with thinking off it is worse than each specialist on that specialist's harness (mean 49.0% vs specialist 51.0% on SWE-bench Pro/OpenCode, 48.2% vs 56.5% on TB2.1/pi). The card says outright: "If you use a single harness with thinking off, its specialist adapter is the better choice". |
| `Qwen3.8-27B-hermes-adapted` | Same idea for Hermes Agent | Out of scope (no Hermes seat here). |
| `netprojects/…-opencode-adapted-GGUF`, `prithivMLmods/…-opencode-adapted-GGUF` | Third-party re-quants of the same adapter | Skip — the first-party GGUF exists. |

No `v2` of either specialist exists as of 2026-11-21T02:45Z.

### 1.4 `mlx-community/Inkling-2-Mini-oQ4e-mtp` — read 2026-11-21

- Repo sha `3eea042751cd296b7266628a8342c1749242e1fe`, uploaded 2026-11-21T00:49Z, built with
  **oMLX v0.8.1 oQ**; card: "It needs oMLX 0.8.1 or later."
- Contents (15,690 MiB / 16.847 GB total): 4 shards (5,077,690,550 + 5,063,799,732 +
  5,256,611,079 + 813,590,578 B), `mtp.safetensors` 635,801,416 B (the bundled **DSpark**
  draft), `chat_template.jinja` 6,868 B, `config.json`, `generation_config.json`,
  `tokenizer.json`, `processor_config.json`.
- Mixed precision: NVFP4 g16 for layers 0–19 experts, affine-4 g64 for layers 20–23,
  affine-8 for attention/embeddings/LM head, BF16 vision tower + DSpark draft, FP32
  router/loop controllers. **4.915 bits/weight** (5.047 including the draft).
- Architecture `Inkling2LoopForConditionalGeneration`, `model_type: inkling2_loop`, 24 layers
  (middle 12 run 3×), 128 experts top-8, hidden 2304, `model_max_length: 1048576`.
- Sibling builds, same family, all newer/parallel options: `Inkling-2-Mini-oQ3e-mtp`
  (13,674,035,690 B = 12.73 GiB), `mlx-community/Inkling-2-Mini-4bit`,
  `netprojects/Inkling-2-Mini-MLX-4-8bit`, `pipenetwork/Inkling-2-Mini-MLX-8bit`,
  `nativ-community/Inkling-2-Mini-nvfp4`, `OpenUncensored/Inkling-2-Mini-Uncensored` (an
  abliterated build, published 2026-11-20T22:34Z). **oQ4e-mtp was the newest first-party MLX
  build at intake**; oQ3e is the same code path at 3 bits for ~3 GB less.

### 1.5 Inkling 2 Mini — upstream card, template, sampling, tools — read 2026-11-21

- `thinkingmachines/Inkling-2-Mini`, released **2026-11-20**, Apache 2.0. 26.4B total /
  3.4B active (5.4B effective per token due to the loop), 1M-token context, text **and
  image** in, text out.
- **Sampling: the card publishes none.** The only first-party values are in
  `generation_config.json`: `temperature 1.0`, `do_sample true` (no top_p/top_k). oMLX's
  `load_sampling_defaults` therefore keeps 1.0 and leaves top_p to the global 0.95 — that
  0.95 is **oMLX's default, not a vendor value**. Do not present it as a card row.
- **Chat template** (`chat_template.jinja`, 137 lines, byte-identical to the upstream one):
  - `reasoning_effort` kwarg maps `none→0.0, minimal→0.1, low→0.2, medium→0.7, high→0.9,
    xhigh→0.99, max→0.99`, and **defaults to `0.9` ("high") when the kwarg is absent**; a
    numeric value must be in [0.0, 0.99]. It is emitted as a system message
    `Thinking effort level: <n>`.
  - There is **no `enable_thinking` switch**. A request that sends `enable_thinking: false`
    (what the Portal pipeline injects for `think: false`) does nothing on this template.
  - Tool definitions are emitted as `<|message_system|>tool_declare<|content_xml|>` + a JSON
    array of `{name, description, parameters, type}`; assistant calls as
    `<|message_model|><fn><|content_invoke_tool_json|>{"name":…,"args":{…}}`; tool results as
    `<|message_tool|><fn>…`. Tool-call arguments **must be objects, not JSON strings** — the
    template raises otherwise ("canonicalize upstream").
  - Assistant turns end with `<|content_model_end_sampling|>` inside a `{% generation %}`
    block; that is the stop token oMLX keys on.
- **Tool calls on oMLX**: `omlx/adapter/output_parser.py` already implements the full Inkling
  channel parser (`_INKLING_MODEL_TYPES = {inkling, inkling_mm_model, inkling2,
  inkling2_loop}`, thinking/text/tool channels, `end_sampling` stop id, JSON-closer repair).
  vLLM's recipe uses `--reasoning-parser inkling` + an `inkling` tool-call parser; oMLX gets
  the same protocol natively.
- Card caveats worth carrying into a seat decision: repetitive reasoning loops (recommends
  output-token and turn limits), less reliable at following project conventions, may take
  destructive actions without confirmation, "setting reasoning effort to its minimum does not
  fully disable reasoning".
- Card also lists Ollama as a supported local runtime for quantized GGUF, and
  `unsloth/Inkling-2-Mini-GGUF` + `ggml-org/Inkling-2-Mini-GGUF` appeared 2026-11-20 — so the
  brief's "the next Ollama release supports it" is consistent with the cards but **I did not
  verify an Ollama version that loads it**, and nothing was installed for the Ollama path.

## 2. Weights (data01 only)

Layout follows the existing convention in this repo's own docs
(`coding_task/AUTO_DAILY_MODEL_RESEARCH.md`, `docs/MODEL_UNUSED_INVENTORY_20261115.md`):
weights live once in `/Volumes/data01/hf-cache/models--…/snapshots/<sha>`, and
`/Volumes/data01/omlx-models/<Name>` is a **symlink** to the snapshot. Nothing was written to
the main drive (`HF_HOME` and `HF_HUB_CACHE` forced to data01 for the run).

| Link created | Points at | Size |
| --- | --- | --- |
| `omlx-models/Qwen3.8-27B-opencode-adapted` | `hf-cache/models--harness-hub--Qwen3.8-27B-opencode-adapted/snapshots/181c2c3f…` | 629 MiB (`du -sh` of the cache repo) |
| `omlx-models/Qwen3.8-27B-pi-adapted` | `hf-cache/models--harness-hub--Qwen3.8-27B-pi-adapted/snapshots/3cad999e…` | 629 MiB |
| `omlx-models/Inkling-2-Mini-oQ4e-mtp` | `hf-cache/models--mlx-community--Inkling-2-Mini-oQ4e-mtp/snapshots/3eea0427…` | 16 GiB (`du -sh`; 15 files, matches the card's 16.847 GB / 15.690 GiB) |

Filesystem, measured: `/Volumes/data01` free went **364 GiB → 347 GiB** (−17 GiB) over the
download; `hf-cache/models--mlx-community--Inkling-2-Mini-oQ4e-mtp` is 16 G on disk.
`du -sh /Volumes/data01/omlx-models` reads **186 G before and after** — `du` does not follow
symlinks, so the new bytes are counted in `hf-cache`, not in the model dir. That is the
intended shape (one copy of the weights), not a failed download.

Only the base checkpoint was not re-fetched; it was **verified present**:
`/Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp` = 16 GiB, `model_type qwen3_5`,
`Qwen3_5ForConditionalGeneration`, 64 layers, hidden 5120.

### 2.1 Verified locally against the real oMLX 0.8.1 code (offline, no engine start)

`omlx.lora_adapters.read_adapter_info` + `compatibility_problem` from the installed
`omlx-0.8.1` package, run against the downloaded folders and the base `config.json`:

```
Qwen3.8-27B-opencode-adapted is_adapter_dir= True
  fmt peft rank 32 layers 64 targets ('down_proj','gate_proj','k_proj','o_proj','q_proj','up_proj','v_proj')
  size 637610624 resident MiB 304.0 base_model Qwen/Qwen3.8-27B
  problem None
  compat vs Qwen3.8-27B-oQ4e-mtp: None
Qwen3.8-27B-pi-adapted … (identical numbers, problem None, compat None)
```

`omlx.model_discovery.discover_models_from_dirs(['/Volumes/data01/omlx-models'], …)`:

```
MODEL Qwen3.8-27B-oQ4e-mtp | type vlm | engine vlm | size 16.6 GiB
ADAPTER Qwen3.8-27B-opencode-adapted -> /Volumes/data01/omlx-models/Qwen3.8-27B-opencode-adapted
ADAPTER Qwen3.8-27B-pi-adapted -> /Volumes/data01/omlx-models/Qwen3.8-27B-pi-adapted
```

after the Inkling build finished, the same call also returned:

```
Inkling: ('vlm', 'vlm', 16.5)
```

So: the adapter folders register as **adapters** (correct — they are not offered as models),
the base is served by the **VLM** engine (still a `BaseEngine`, so the chat path resolves
exposed profiles for it), and oMLX's own loader sees no blocker on either adapter: 64/64
decoder layers, all seven projections inside the decoder stack, 304 MiB resident each.

## 3. oMLX 0.8.1 configuration surface — read from the installed `omlx-0.8.1`

Release notes: `github.com/jundot/omlx/releases/tag/v0.8.1` (published 2026-11-21T01:17Z) —
"Turn on **Expose as model** in a profile to serve the adapter under its own id,
`<model>:<profile>`"; "DFlash, VLM MTP, ANE prefill, MoE expert offload and the Prefill
Accelerator cannot be used with an adapter yet"; "adapter folders in a model directory no
longer show up as models in `/v1/models`".

### 3.1 Where the settings actually live — **the brief's premise is off**

The brief says "write the exact `~/.omlx/model_settings.json` **profile** JSON". In 0.8.1 a
profile is **not** in `model_settings.json`:

- `~/.omlx/model_settings.json` — `{"version": 2, "models": {<model dir>: {…}}}`; this is
  where the per-model `lora_adapter` path goes (`ModelSettings.lora_adapter: Optional[str]`,
  `model_settings.py:604`).
- `~/.omlx/model_profiles.json` — `{"version": 1, "profiles": {<model dir>: {<name>: {…}}}}`
  (`PROFILES_VERSION = 1`, `model_settings.py:279`), written atomically by
  `ModelSettingsManager._save_profiles`. Each record:
  `name, display_name, api_name, description, created_at, updated_at, settings,
  source_template, expose_as_model` (`save_profile`, `model_settings.py:1549`).

On this host `~/.omlx/model_profiles.json` **does not exist yet** — no profile has ever been
saved, so the orchestrator is creating it, not editing it.

### 3.2 Consequences the handoff depends on

- `lora_adapter` is a **filesystem path**, used verbatim (`apply_adapter(model, lora_path)`,
  `adapter_info(lora_path)`) — not an adapter id, and it must be reachable by the oMLX
  process (data01 mount).
- The exposed request id is `<model dir>:<api_name>` (`_profile_model_id`), or
  `<model_alias>:<api_name>` when the base entry has a `model_alias`. `Qwen3.8-27B-oQ4e-mtp`
  has **no** `model_alias` in `model_settings.json`, so the ids are exactly
  `Qwen3.8-27B-oQ4e-mtp:opencode` and `Qwen3.8-27B-oQ4e-mtp:pi`.
- `api_name` must match `^[a-z0-9][a-z0-9_-]{0,31}$` (`validate_profile_name`).
- Profiles are applied **per request**: `get_exposed_profile_runtime_settings_for_request`
  merges base settings + profile's model-specific fields, and the engine signature includes
  `lora_adapter` (`engine_pool.py:1495`), so a profile request loads a *variant* engine while
  the base stays untouched. Base `mtp_enabled: true` survives: MTP is **not** in the
  adapter conflict list.
- Adapter conflicts (`_LORA_CONFLICTS`, `model_settings.py:52`): `dflash_enabled`,
  `vlm_mtp_enabled`, `qwen35_ane_prefill_enabled`, `moe_expert_offload_enabled`,
  `prefill_helper_node_id` ("a Prefill Accelerator"), `external_engine`. A profile carrying
  the adapter has those cleared automatically by `resolve_lora_conflicts`; a base that has
  them on is fine because the merge clears them for the variant.
- Loader refuses (so the orchestrator does not need to try): DoRA, `modules_to_save`, LoRA
  bias, `trainable_token_indices`, `target_parameters` (MoE experts), `layer_replication`,
  QA-LoRA, aLoRA, Arrow, LoftQ, PiSSA/OLoRA/CorDA residual inits, anything outside the
  decoder stack, and MoE router/expert projections. Not one of these applies to either
  harness adapter (see §2.1).
- `lora_adapters._NON_DECODER` also refuses module paths containing `mtp` — irrelevant here,
  and worth remembering if someone later adapts an MTP-head model with more targets.

## 4. Portal-side wiring (this repo)

- `config/backends.yaml` — the three candidate ids appended to the existing **`omlx-general`**
  backend (group `general`), not a new group. Reason: every `bench-*` workspace routes to
  `general`, and `tests/unit/test_variant_hints_resolve_in_routing.py` fails a hint that lives
  outside its workspace's routed groups (the same constraint that put the S8 screen
  challengers in `general`). Appending keeps `models[0]` — which the last-resort
  substitution path uses — unchanged, and nothing but the three bench workspaces names the new
  ids. No production workspace, variant, persona or alias was pointed at them.
- `config/bench_workspaces.yaml` — three `module: eval` workspaces carrying the ids as
  `model_hint`, each with the card's sampling and `expose_to_owui: false` (explicit-only).
  The pipeline's `model` field is a **workspace id**, not a model id
  (`portal/platform/inference/model_addressing.py`), which is why the model ids alone would
  not be addressable through the Pipeline.
- `config/modelfiles/` — the two Ollama GGUF LoRA recipes for the non-Apple-silicon fallback.
- Bench workspaces merge only when eval is on (`modules.eval.enabled`, or
  `PORTAL_ENABLE_EVAL=1`). The live `.env` already carries `PORTAL_ENABLE_EVAL=1`.

## 5. What is deliberately not done

- No production workspace, variant, persona, alias or `workspace_routing` group was pointed
  at any of these ids.
- Nothing seated (`bench-*` is excluded from auto-routing by name; `expose_to_owui: false`).
- No `ollama create` was run anywhere — the recipes are files only.
- No `~/.omlx` write, no engine restart, no `launch.sh` beyond `bash -n`.
- The Inkling oQ3e build was not downloaded (oQ4e chosen per the brief; 3 GB saved if the
  orchestrator prefers oQ3e — same code path, and the task is a bench screen first).
