# Auto-daily model and engine research

- Date: 2026-11-20
- HEAD reviewed: `f248f58af`
- Status: research only; no model, backend, workspace, or live service configuration changed.

## Recommendation

Screen these two first, as separate candidate arms:

1. **Qwen3.5-9B, MLX 4-bit on oMLX 0.8.0.** Best size/quality/tool evidence in the shortlist; its Qwen3.5 template format is explicitly recognized by oMLX. The expected 2.8 s below is only the oMLX model-load component estimate, not cold first visible content.
2. **Gemma 4 12B-it, MLX 4-bit on oMLX 0.8.0.** Strong general-chat results and native function calling, with an explicitly recognized Gemma parser. It is a useful larger-quality counterpoint to Qwen3.5-9B.

Qwen3.8-9B Distill is the reserve challenger. It has promising community results and a compact MLX artifact, but it is an independent community distillation, not an official Qwen 9B release; its oMLX tool-format compatibility is inferred from its Qwen3.5 architecture and still needs a direct probe.

Do not restore either candidate as a preferred resident. The candidate must pass the five-trial cold screen with the largest required oMLX seat still loaded. The seat change remains an operator decision.

## Requirements and evidence boundary

- `auto` sends ordinary chat to `auto-daily`; `auto-daily.context_limit` is **16,384** in the current `config/portal.yaml`.
- `auto-daily` has the merged production tool set: web search/fetch, knowledge search/list, document readers and creators, Python, memory, and audio transcription. The workspace is text-only; image turns reroute to `auto-vision`.
- Hard cold target: **every candidate first-visible-content time must be at most 8 seconds through Open WebUI `/api/chat/completions`, model `auto`**. This is an end-to-end user-visible measure, not a model file-load estimate.
- Host requirement: M-series, 64 GB unified memory. The candidate must coexist with the largest required oMLX seat loaded; that identity and live fit must be confirmed from the orchestrator's current `/v1/models/status` and seat-fit data at screen time.
- The brief supplies the incumbent cold first-visible-content observation of about 40 seconds and the current oMLX `load_seconds_per_gb_estimate` of about 0.47 s/GB. Neither value was re-measured by this worker. The current 40-second incumbent result is not a model-load duration.
- The worker did not find an Ollama server log or candidate-specific `load_duration` records. Therefore, there are **no measured candidate Ollama load times** to report. Do not infer Ollama times by scaling the incumbent's 40-second first-visible-content result.
- The local model inventory is read-only. `ollama list` reports on-disk tag sizes, not currently loaded memory. No inference or `ollama ps`/oMLX status probe was run here.

`loaded estimate` below means model weights plus a calculated 16K KV cache where the architecture makes that calculation available. It excludes runtime, allocator, prompt buffers, and any resident shared weights. It is a planning floor, not a measured loaded size. The live `/v1/models/status` value is required for actual resident memory.

## Ranked shortlist

Sizes from vendor/Hugging Face file listings are decimal GB; the GiB conversion is shown where used. `oMLX load component` applies only to an MLX artifact served by oMLX and uses the brief-supplied 0.47 s/GB estimate. It is not a TTFT prediction. Ollama estimates stay unknown because candidate load-duration logs were unavailable.

| Rank | Candidate and engine | Artifact; 16K loaded planning size | Load estimate | Chat and tool evidence | Template / tool path | On disk in this checkout/host |
|---:|---|---|---|---|---|---|
| **1** | **Qwen3.5-9B, MLX 4-bit / oMLX** | MLX artifact **5.98 GB** (5.57 GiB). Qwen config has eight full-attention layers and four KV heads; FP16 16K KV is about 0.50 GiB, so weights+that KV are about **6.07 GiB before runtime**. | oMLX component estimate **2.81 s**; full cold TTFT unknown. | Official card reports MMLU-Pro 82.5, IFEval 91.5, BFCL-V4 66.1, Tau2 79.1, and native 262K context. A separate community small-model test reports Q4 tool-use results; framework/harness differs, so treat as corroboration only. | oMLX 0.8.0 explicitly auto-detects the Qwen3.5 XML function-call format. The official Ollama model family is available, but this exact tag's merged-tool path must still pass a direct probe before `supports_tools: true`. | Exact official MLX Q4 artifact absent. `ollama list` has only the **Huihui abliterated** Qwen3.5 9B GGUF at 6.6 GB; that is not this checkpoint. |
| **2** | **Gemma 4 12B-it, MLX 4-bit / oMLX** | MLX artifact **6.77 GB** (6.30 GiB). Based on the published layer/KV configuration, 16K FP16 KV is about 0.81 GiB; weights+KV are about **7.11 GiB before runtime**. | oMLX component estimate **3.18 s**; full cold TTFT unknown. | Official card reports MMLU-Pro 77.2 and Tau2 average 69.0; Google documents native function calling and a 256K window. Its official results are not directly comparable to Qwen's benchmark setup. | oMLX 0.8.0 explicitly recognizes Gemma's `<start_function_call>` format. Gemma's official chat template supports function calling; direct `auto-daily` merged-tool probe still required. | Exact MLX 12B artifact absent. Ollama has `gemma4:12b-it-qat-ctx8k` (7.2 GB), a different QAT artifact with an 8K baked tag. The separate 26B Gemma MLX/Ollama artifacts do not count as this model. |
| **3** | **Qwen3.8-9B Distill, MLX 4-bit / oMLX** | Community MLX artifact **5.04 GB** (4.69 GiB). It follows the Qwen3.5-9B architecture; using the base's approximate 0.50 GiB FP16 16K full-attention KV gives about **5.19 GiB before runtime**. | oMLX component estimate **2.37 s**; full cold TTFT unknown. | The distiller reports MMLU flexible-extract 0.751 vs Qwen3.5-9B base 0.546; its own card says native function calling per Qwen3.5. A community Agon Arena run reports 77.79% overall / 21.67 of 24 agent points for a Qwen3.8-9B entry. Both are non-vendor evidence; the distiller's results are self-reported and the arena model identity/quant should be rechecked before comparison. | Qwen3.5-based template plus oMLX's Qwen3.5 parser make support plausible, but this exact distillation was not probed on oMLX 0.8.0. Directly verify tool schema rendering and native `tool_calls`. | No exact Qwen3.8-9B artifact on disk. Existing `Qwen3.8-27B` MLX folders are a different, much larger model. |
| **4** | **Nemotron 3.5 Bolt E4B, Q4 GGUF / Ollama** | Local GGUF tag is **6.1 GB**. Weight floor is about 5.68 GiB; 16K loaded size is weights plus KV/runtime and has not been measured. | Ollama cold load duration **unknown**; no matching log entry. Do not apply the oMLX estimate to this Ollama path. | NVIDIA reports Q4 RelyToolBench 69.29, MultiChallenge 55.60, and strong instruction-following results. These are vendor benchmark results, not Portal real-use results. | Gemma4-derived family with a functioning Ollama tool template; repository currently declares `supports_tools: true` for the existing Bolt tag. The installed tag bakes 8K, so build and probe a 16K tag before a seat screen. | Present as `hf.co/unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL` (6.1 GB) and a separate `-ctx8k` tag. No 16K derived tag. No MLX copy located. |
| **5** | **LFM2.5-8B-A1B, GGUF / Ollama** | Local GGUF is **5.2 GB** (about 4.84 GiB weights). Loaded memory at 16K is weights plus model-specific KV/runtime; not measured. | Ollama cold load duration **unknown**; no matching log entry. | Official LiquidAI card describes an 8.3B-total / 1.5B-active, 128K text model. Community Agon Arena reports 67.18% overall / 16.67 of 24 agent points for LFM2.5-8B-A1B. The community score is a low-resource llama.cpp result, not a target-host measure. | Exact Ollama tag is already marked `supports_tools: true` in current backend config. No explicit LFM parser is listed by oMLX 0.8.0; treat oMLX tool support as unknown until direct test. | `lfm2.5:8b-ctx8k` is present at 5.2 GB. It needs a 16K derived tag. A separate local custom uncensored 8B GGUF is not equivalent. |
| **6** | **Granite 4.2-8B, Q4 GGUF / Ollama** | Ollama's 8B tag is about **5.3 GB** (about 4.94 GiB weights). Its published 40-layer/8-KV-head/128-dim configuration gives about 2.50 GiB FP16 KV at 16K; weights+KV are about **7.44 GiB before runtime**. | Ollama cold load duration **unknown**. | IBM's card reports MMLU-Pro 74.04, BFCL v4 52.39, Tau3 58.06, and 128K context. | IBM describes reasoning-augmented tool calling. oMLX does not list Granite in the named parser table; generic parsing only works if the template renders the supplied tools and emits a recognized format. Verify each engine directly. | Granite 4.2 exact tag absent. `granite4.1:8b-ctx16k` (5.3 GB) is present, but is a different generation and must not be used as proof for 4.2. |
| **7** | **GPT-OSS-20B, MXFP4 / Ollama** | Ollama artifact is about **14 GB** (13.04 GiB weights) before 16K KV/runtime. This is close enough to the 15 GiB loaded ceiling that actual residency and co-fit could disqualify it. | Ollama cold load duration **unknown**; no matching log entry. | OpenAI describes strong tool/function calling and says the 20B model can run in 16 GB memory. Ollama lists the MXFP4 model at about 14 GB and 128K context. The available general-quality claim is less directly comparable to the Qwen/Gemma cards. | Ollama tool path is documented. oMLX 0.8.0 has GPT-OSS response parsing fixes, but its tool-call compatibility for this exact quant/template is not proven by that note; test before adding an alias. | Not present in `ollama list` or the named oMLX directories. |

The official family check matters for interpreting the shortlist: the official Qwen3.8 open releases are 27B and 2.4T, while the official small Qwen family includes Qwen3.5-9B. The 9B “Qwen3.8” above is a community distillation from Qwen3.8 into Qwen3.5-9B architecture. LiquidAI's newest family at intake is LFM3; its text model is 1.7B, around 1 GB at 4-bit, below the requested 4–15 GiB loaded range and positioned for specialized/agent tasks. It has strong vendor tool results (BFCL V4 71.39, ToolSandbox 80.36), so it could be a separate speed/control test if ordinary-chat quality is acceptable. The local LFM2.5-8B is included as the in-range LFM comparison, not as the newest LFM release. The official Qwen3.8-27B 4-bit MLX folder exists locally at about 15 GB on disk; its weights alone sit at the upper loaded-size boundary, so it is not recommended for this co-residency screen.

## Exact pulls and context-tag builds

The commands below only stage artifacts/tags; they do not alter Portal config. Confirm enough free space and the current model source before running them. No BF16 download or conversion is proposed.

### Top two

```bash
# Qwen3.5-9B MLX 4-bit candidate for oMLX
hf download mlx-community/Qwen3.5-9B-MLX-4bit \
  --local-dir /Volumes/data01/omlx-models/Qwen3.5-9B-MLX-4bit

# Matching Ollama fallback and a 16K context tag
ollama pull qwen3.5:9b
cat >/tmp/qwen35-9b-ctx16k.Modelfile <<'EOF'
FROM qwen3.5:9b
PARAMETER num_ctx 16384
EOF
ollama create qwen3.5:9b-ctx16k -f /tmp/qwen35-9b-ctx16k.Modelfile

# Gemma 4 12B-it MLX 4-bit candidate for oMLX
hf download mlx-community/gemma-4-12B-it-4bit \
  --local-dir /Volumes/data01/omlx-models/gemma-4-12B-it-4bit

# Matching Ollama fallback and a 16K context tag
ollama pull gemma4:12b
cat >/tmp/gemma4-12b-ctx16k.Modelfile <<'EOF'
FROM gemma4:12b
PARAMETER num_ctx 16384
EOF
ollama create gemma4:12b-ctx16k -f /tmp/gemma4-12b-ctx16k.Modelfile
```

### Remaining shortlist candidates that are not on disk

Qwen3.8-9B Distill MLX Q4:

```bash
hf download keXjos/Qwen3.8-9B-mlx-4Bit \
  --local-dir /Volumes/data01/omlx-models/Qwen3.8-9B-mlx-4Bit
```

Granite 4.2-8B GGUF through Ollama (then create a separate 16K tag using the same `Modelfile` pattern above):

```bash
ollama pull granite4.2:8b
```

GPT-OSS-20B MXFP4 through Ollama (then create a separate 16K tag using the same pattern):

```bash
ollama pull gpt-oss:20b
```

No pull is needed for the listed Bolt E4B, LFM2.5-8B, or Granite 4.1 local comparison tags; derive new 16K Ollama tags from their existing source tags before any tool or seat test. For each new derived tag, retain its exact `FROM` source, use `PARAMETER num_ctx 16384`, and record the resulting tag in the live evidence. Do not use an existing 8K tag for this 16K seat.

## Proposed config for the two screens (not applied)

Keep `context_limit: 16384`, all current sampling/memory/tool settings, and `preferred_residents: []`. Change only the `auto-daily.model_hint` for the arm being screened. Register the 16K fallback tag under `ollama-general`, the MLX directory id under `omlx-general`, and add the GGUF-tag-to-MLX-id mapping under `omlx-general.aliases`.

Candidate A — Qwen3.5-9B:

```yaml
# config/portal.yaml, under auto-daily
model_hint: qwen3.5:9b-ctx16k
context_limit: 16384

# config/backends.yaml, under ollama-general.models
- id: qwen3.5:9b-ctx16k
  supports_tools: true  # add only after the exact tag passes a behavioral tool probe

# config/backends.yaml, under omlx-general.models
- id: Qwen3.5-9B-MLX-4bit
  supports_tools: true  # add only after the exact oMLX model passes a behavioral tool probe

# config/backends.yaml, under omlx-general.aliases
qwen3.5:9b-ctx16k: Qwen3.5-9B-MLX-4bit
```

Candidate B — Gemma 4 12B-it:

```yaml
# config/portal.yaml, under auto-daily
model_hint: gemma4:12b-ctx16k
context_limit: 16384

# config/backends.yaml, under ollama-general.models
- id: gemma4:12b-ctx16k
  supports_tools: true  # add only after the exact tag passes a behavioral tool probe

# config/backends.yaml, under omlx-general.models
- id: gemma-4-12B-it-4bit
  supports_tools: true  # add only after the exact oMLX model passes a behavioral tool probe

# config/backends.yaml, under omlx-general.aliases
gemma4:12b-ctx16k: gemma-4-12B-it-4bit
```

The snippets show the final desired registry state, but `supports_tools: true` is conditional on a direct typed tool-call probe for that exact engine/model/tag. The upstream model card or parser table is not enough. If either tool probe fails, do not advertise the tag as tool-capable or run the full merged-tool screen.

## Live screen for the orchestrator

Run only after an operator chooses an arm, the assets are present, aliases are staged, and the host is quiet. Run a five-trial baseline and five-trial candidate phase with the same prompt. Before each trial unload only the target model and verify it is unloaded; do not flush OS page cache or unload the largest required oMLX seat. Capture the live largest-seat identity, candidate actual memory, and seat-fit before and while the candidate is loaded.

Set the candidate's oMLX id for the selected arm and submit this once per trial through OWUI → `auto`:

```bash
set -o pipefail
: "${OWUI_API_KEY:?Set an Open WebUI API key}"
curl --silent --show-error --no-buffer --fail-with-body \
  -H "Authorization: Bearer ${OWUI_API_KEY}" \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"auto","messages":[{"role":"user","content":"Reply with exactly READY."}],"stream":true}' \
  "${OWUI_URL:-http://localhost:8080}/api/chat/completions" |
python3 -u -c '
import json, sys, time
t0 = time.monotonic()
seen = False
for line in sys.stdin:
    if not line.startswith("data: "):
        continue
    payload = line[6:].strip()
    if payload == "[DONE]":
        break
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        continue
    choices = event.get("choices") or []
    delta = (choices[0].get("delta") or {}) if choices else {}
    content = delta.get("content")
    if content and not seen:
        print(f"first_content_s={time.monotonic() - t0:.3f} first_content={content!r}", flush=True)
        seen = True
if not seen:
    raise SystemExit("stream ended before visible content")
'
```

For every request, preserve the returned `first_content_s` and verify routing from the Pipeline log:

```bash
docker logs --since 5m portal5-pipeline 2>&1 |
  rg 'Stream routing: workspace=auto-daily backend=(ollama-general|omlx-general) model='
```

The candidate screen passes only if all five first-visible-content observations are `<= 8.000 s`, each request logs `workspace=auto-daily backend=omlx-general` and the exact selected MLX model id, and none falls back to Ollama. Report median and maximum as well as all five raw times. A timeout, missing visible content, wrong route, or any result above 8 seconds is a fail for the hard target.

Capture oMLX residency/coexistence before the phase, with the candidate warm, and after unloading the candidate. Keep the largest required production seat loaded throughout:

```bash
curl --silent --show-error \
  -H "Authorization: Bearer ${OMLX_API_KEY}" \
  "${OMLX_URL:-http://localhost:8085}/v1/models/status" |
jq '{load_seconds_per_gb_estimate, final_ceiling_gib:(.final_ceiling/1073741824), current_model_memory_gib:(.current_model_memory/1073741824), models:[.models[]|select(.loaded)|{id,loaded,pinned,estimated_size,actual_size}]}'

curl --silent --show-error -X POST \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  "${PIPELINE_URL:-http://localhost:9099}/admin/seat-fit" |
jq '{available_gib,budget_source,never_fit,over_budget,unserved}'
```

Pass requires the largest required seat to remain loaded, no new seat-fit refusal/over-budget state, and the candidate to load without eviction, memory-guard rejection, or fallback. Record the actual status values; the formula-derived sizes above do not replace them.

### Real-use and merged-tool screen with an independent judge

Use the repository's existing `realuse_v1` auto-daily suite at one repeat per arm (seven real-use tasks), with production tools. Create one temporary plan per candidate and run the pair against the current incumbent. The judge is a third model (`mistral-small3.2:24b`), not either candidate or the incumbent. Preserve campaign outputs and blind pairwise judgments.

For Qwen3.5 (change `SCREEN_TAG` and `CAMPAIGN` to the Gemma values for the second run):

```bash
mkdir -p coding_task/scratch
SCREEN_TAG=qwen3.5:9b-ctx16k
CAMPAIGN=auto_daily_qwen35_screen_20261120
cat >"coding_task/scratch/${CAMPAIGN}.yaml" <<EOF
repeats: 1
workloads:
  auto-daily:
    tool_mode: production
    home: realuse_v1
    discovery: []
    arms:
      incumbent: hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k
      challengers:
        - ${SCREEN_TAG}
EOF
uv run python -m tests.wfe.campaign --campaign-id "${CAMPAIGN}" \
  --plan "coding_task/scratch/${CAMPAIGN}.yaml" --tier realuse
WFE_JUDGE_MODEL='mistral-small3.2:24b' uv run python -m tests.wfe.judge \
  --campaign "${CAMPAIGN}"
```

For the Gemma pass, set `SCREEN_TAG=gemma4:12b-ctx16k` and `CAMPAIGN=auto_daily_gemma12b_screen_20261120`, then repeat the same commands. The plan uses production tools and the existing objective checks; also verify the captured tool trace contains a native structured call, correct tool name/arguments, and a grounded final answer for the tool-required rows. A plain answer without the expected call, malformed arguments, failed tool execution, or fabricated tool result fails that row. The independent judge must not produce a candidate loss across the seven conversations; inspect and retain its reasons instead of treating the judge as a substitute for objective checks.

## Sources and local evidence

Primary model/runtime references:

- [oMLX 0.8.0 release](https://github.com/jundot/omlx/releases/tag/v0.8.0) and [oMLX tool-calling documentation](https://github.com/jundot/omlx/blob/main/README.md#tool-calling--structured-output): current parser families and the requirement that a model template accept `tools`.
- [Qwen3.5-9B official model card](https://huggingface.co/Qwen/Qwen3.5-9B), [Q4 MLX artifact](https://huggingface.co/mlx-community/Qwen3.5-9B-MLX-4bit), and [Unsloth small-model tool-call benchmark](https://huggingface.co/Manojb/small-llm-tool-use-bench).
- [Gemma 4 12B official model card](https://huggingface.co/google/gemma-4-12B-it) and [Q4 MLX artifact](https://huggingface.co/mlx-community/gemma-4-12B-it-4bit).
- [Official Qwen3.8 model list](https://github.com/QwenLM/Qwen3.8), [Qwen3.8-9B Distill card](https://huggingface.co/empero-ai/Qwen3.8-9B-Distill), and [4-bit MLX conversion](https://huggingface.co/keXjos/Qwen3.8-9B-mlx-4Bit).
- [NVIDIA Nemotron 3.5 Bolt card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16), [LiquidAI LFM2.5-8B-A1B card](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B), [LiquidAI LFM3 launch/results](https://www.liquid.ai/blog/lfm3), and [LFM3-1.7B card](https://huggingface.co/LiquidAI/LFM3-1.7B).
- [IBM Granite 4.2-8B card](https://huggingface.co/ibm-granite/granite-4.2-8b), [OpenAI GPT-OSS announcement](https://openai.com/index/introducing-gpt-oss/), and [Agon Arena v2 results](https://github.com/GuideboardLabs/agon-arena).
- [Ollama Gemma4 tags](https://ollama.com/library/gemma4/tags), [Qwen3.5 tags](https://ollama.com/library/qwen3.5/tags), [Granite4.2 tags](https://ollama.com/library/granite4.2/tags), and [GPT-OSS tags](https://ollama.com/library/gpt-oss/tags).

Local facts checked in this checkout: `config/portal.yaml` (`auto-daily` context and tools), `config/backends.yaml` (backend model entries, aliases, and recorded `supports_tools` flags), `coding_task/AUTO_DAILY_COLD_START_PLAN.md` (incumbent route/screen pattern), `docs/MODEL_UNUSED_INVENTORY_20261115.md`, local `/Volumes/data01/omlx-models` directory names, `ollama --version`, and read-only `ollama list`. The `ollama list` inventory includes Bolt 6.1 GB, LFM2.5-8B 5.2 GB, LFM2.5-24B 14 GB, Gemma4 12B QAT 7.2 GB, and Granite4.1 8B 5.3 GB; it does not establish resident memory or provide cold timings.

## Unproven / operator checks

- Candidate cold TTFT through OWUI `auto` on this host; the 0.47 s/GB factor is an estimate for oMLX model loading only.
- Candidate-specific Ollama `load_duration`; the expected log source/records were unavailable here.
- Current live oMLX estimate factor, host free headroom, largest seat identity, candidate actual resident size, KV allocation, and whether loading candidates coexist without eviction/refusal.
- Exact serving versions and parser/template behavior on the current oMLX and Ollama processes. Repository version/config and upstream documentation are not a substitute for the direct probes above.
- Final real-use quality, tool selection/arguments, UI-visible output, independent judge results, and whether either candidate meets the 8-second hard limit.
