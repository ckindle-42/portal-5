# Auto-daily cold first-token plan

Date: 2026-11-20

Scope: research and proposed A/B only. No config, engine, or live state was changed in this worker lane.

## Finding

The current production hint for `auto-daily` is the Nemotron 3.5 Lightning 30B-A3B GGUF at `Q4_K_M-ctx32k`. Ordinary `auto` requests select `auto-daily`. `defaults.preferred_residents` is now empty, so the Pipeline no longer proactively loads this model at startup. However, `deploy/portal-5/docker-compose.yml` sets Ollama's global `OLLAMA_KEEP_ALIVE=24h`, and the native adapter leaves lifecycle control to Ollama. A normal request can therefore leave the GGUF resident for up to 24 hours unless the load guard unloads it. The brief's cold-first-token observation is about 40 s (2026-11-16); the reported 24.6 GiB resident caused oMLX headroom trouble, and restoring the preferred resident is not a viable fix.

Current HEAD has a registered oMLX Nemotron `oQ4e-mtp` model in `omlx-general`, but the exact `auto-daily` GGUF hint has no alias to it. The candidate checkpoint is 16.57 GiB on disk. Existing same-session warm measurements report 70.0–70.3 tok/s on oMLX versus 52.9–53.1 tok/s on the Ollama GGUF, but they do **not** measure cold load or first-token latency. The catalog's historical Nemotron alias text is stale relative to `config/backends.yaml`; use current config as the routing source of truth.

## Options

| Option | Cold time-to-first-token expectation | Resident memory | Evidence and risk |
|---|---|---|---|
| **On-demand oMLX shadow for the same Nemotron family (recommended A/B)** | Unknown until the live A/B. A bytes-only scenario scales the old 40 s by `16.57 GiB / 23.73 GiB` (the GGUF artifact's 25.48 GB), or about 28 s, if model-load time were linear in checkpoint size. That is a hypothesis, not a prediction: page-cache state, MLX initialization, prompt prefill, and MTP setup may dominate. | 16.57 GiB checkpoint plus KV/runtime while loaded; set oMLX model TTL to 300 s so it unloads after idle. Actual resident bytes must come from `/v1/models/status`. | Same registered model family and already measured warm decode advantage; smaller checkpoint than the reported 23.8–24.6 GiB GGUF resident. Risks: distinct quant/engine behavior, unmeasured cold load, different tool/parser behavior, and reduced oMLX headroom while warm. Keep the GGUF fallback. |
| Lower Nemotron GGUF quant | Directionally faster only if the new artifact is smaller and loading is byte-bound; exact TTFT is unknown. No selected lower-quant artifact or cold measurement is present in this task's evidence. | Less than the current ~23.8–24.6 GiB loaded footprint by an unknown amount; weight file remains resident until Ollama unloads it. | Changes the quant and quality. No current daily-seat tool/quality evidence for a lower quant, so it is not the first experiment. |
| Switch to the existing Gemma QAT fast variant | Unknown. Its 14.57 GiB oMLX checkpoint is smaller, but no cold-load timing is recorded. | About 14.57 GiB checkpoint plus KV/runtime while loaded; still a material resident if pinned or left without TTL. | Existing Gate C evidence exists, but the 2026-11-06 `auto-daily` real-use comparison was Nemotron 28/28 vs Gemma 26/28. This is a model-seat decision with a quality tradeoff, so do not make it the first recommendation. |
| Bake a 16k Ollama context tag / reduce context | Expected near the 40 s baseline; possibly a small load-time change from less KV allocation, with no evidence for a number. The current daily GGUF tag bakes 32k, while the workspace declares 16k. | Weights stay about 23.8–24.6 GiB; only context/KV allocation can fall, with exact savings unknown. | `OllamaNativeTransport` deliberately drops load-time `num_ctx` options to avoid reloading resident models. A derived 16k tag is required. This could help memory, but is unlikely to remove the weight-loading part of cold TTFT. |
| Ollama mmap / Flash Attention / parallelism tuning | No supported, evidence-backed TTFT reduction for this request path. | Does not reduce model weight size; Flash Attention can reduce context-cache memory on supported backends. | The current Ollama docs say Flash Attention is automatic where supported; the Pipeline transport does not forward load-time request options such as `use_mmap`. `OLLAMA_NUM_PARALLEL` is already documented with default 1 and affects concurrent capacity, not a single cold request. Avoid a global engine setting for this seat without version-specific evidence. |
| Reduce Ollama's global keep-alive from 24h to 5m | No change to the first cold request; later cold requests may happen sooner after idle. | Frees any Ollama model after 5 idle minutes rather than up to 24h, across the entire fleet. | The global is explicitly set in compose. This could reduce the fallback's memory window but affects every Ollama seat and increases repeat cold loads. It does not solve the first cold TTFT, so keep it a separate operator decision. |
| Keep a smaller resident beside oMLX | Warm TTFT, by definition; cold TTFT returns after eviction. No cold figure is available for an unqualified smaller daily model. | A 4–5 GiB-class model would cost about that much plus its KV/runtime; it would still be resident memory and current host headroom must be measured. | No small candidate in the current evidence has the daily seat's quality/tool qualification. Do not replace the selected seat on size arithmetic alone. |
| Prefetch from an OWUI typing signal | No separate pre-submit signal was found in this repository's inference path. Loading when the chat-completion request arrives is the same load the user's first token waits on. | Same loaded model footprint as the normal request. | The supported OWUI path is `POST /api/chat/completions`; adding a keystroke hook would require changing Open WebUI source, which project rules prohibit. Not a current option. |
| Restore a permanent preferred resident | Warm requests avoid model load. | Reported ~24.6 GiB GGUF resident; brief reports oMLX dynamic ceiling near 23 GiB and 20 GiB oMLX seats refused at prefill. | Rejected by the reported headroom failure and current operator decision in commit `ad7163296`; do not restore `auto-daily` in `preferred_residents`. |

Ollama lifecycle detail: the Pipeline's OpenAI-shaped `keep_alive` field is not forwarded by `OllamaNativeTransport`; Ollama applies its server keep-alive setting. The checked-in Compose value is `OLLAMA_KEEP_ALIVE=24h` (the upstream default is 5 minutes, but this deployment overrides it). oMLX model settings document `ttl_seconds: None` as no TTL, so the oMLX candidate must have a finite TTL and must not be pinned.

## Recommended A/B configuration

Trial the same Nemotron model through oMLX, leaving the existing Ollama GGUF as automatic fallback:

```yaml
# config/backends.yaml, under the existing `omlx-general` aliases:
hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp
```

For the oMLX model's existing settings in the host-owned `~/.omlx/model_settings.json`, merge the following fields and preserve its current MTP settings:

```json
{
  "max_context_window": 32768,
  "ttl_seconds": 300
}
```

The `max_context_window` matches the existing GGUF tag's baked 32k window for the A/B. The finite 300 s TTL keeps the model demand-loaded and gives it a warm-use window without making it a permanent resident. Check the actual oMLX v0.8 settings schema and existing model entry before applying; do not overwrite `mtp_enabled` or other saved fields. Keep `preferred_residents: []` unchanged. This trial changes the routing engine/quant path, so live answer/tool behavior and context fit remain acceptance checks.

No Ollama workspace `keep_alive` change is proposed: current source deliberately does not forward that lifecycle field. The checked-in 24-hour global setting means an Ollama fallback can still occupy about 24 GiB for up to 24 hours after the last request. The candidate A/B is valid only if it stays on oMLX; changing the global Ollama keep-alive would affect all seats and is a separate operator decision.

## Live A/B for the orchestrator

Run on a quiet host in two phases, current config first and the candidate alias second. Do not flush the OS page cache; “cold” here means the target model is unloaded. Use the same prompt and five unloaded-model trials per phase. Record the median client-visible first-content time, exact backend/model route, `/v1/models/status`, and the load-guard seat-fit report.

### 1. Unload only the tested model before each trial

Baseline Ollama model:

```bash
ollama stop 'hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k'
ollama ps
```

Candidate oMLX model (omit the Authorization header only if this host is configured keyless):

```bash
curl --fail-with-body --silent --show-error -X POST \
  -H "Authorization: Bearer ${OMLX_API_KEY}" \
  "${OMLX_URL:-http://localhost:8085}/admin/api/models/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp/unload"
```

Verify the target is unloaded in `ollama ps` or oMLX `/v1/models/status` before sending the request. Do not unload unrelated models or clear the host page cache.

### 2. Measure visible first content through OWUI → `auto`

Run once per trial in both phases (the Open WebUI API applies the workspace model):

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

For every trial, confirm the Pipeline log shows the intended effective route:

```bash
docker logs --since 5m portal5-pipeline 2>&1 | rg 'Stream routing: workspace=auto-daily backend=(ollama-general|omlx-general) model='
```

The baseline must show `ollama-general` and the GGUF tag. The candidate must show `omlx-general` and `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`; an oMLX failure followed by Ollama fallback is not a candidate pass.

### 3. Capture oMLX headroom with the candidate warm, then after TTL

Immediately after a candidate reply, capture the live ceiling, resident bytes, and headroom:

```bash
curl --silent --show-error \
  -H "Authorization: Bearer ${OMLX_API_KEY}" \
  "${OMLX_URL:-http://localhost:8085}/v1/models/status" |
jq --arg id 'NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp' \
  '{final_ceiling_gib:(.final_ceiling/1073741824), current_model_memory_gib:(.current_model_memory/1073741824), headroom_gib:((.final_ceiling-.current_model_memory)/1073741824), target:[.models[]|select(.id==$id)|{id,loaded,pinned,estimated_size,actual_size}]}'
```

Capture the Pipeline's seat-fit view at the same point (regular `PIPELINE_API_KEY`):

```bash
curl --silent --show-error -X POST \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  "${PIPELINE_URL:-http://localhost:9099}/admin/seat-fit" |
jq '{available_gib,budget_source,never_fit,over_budget,unserved}'
```

After 300 seconds without a request, repeat the oMLX status command and check `target[].loaded` is false and headroom has recovered. Also run `ollama ps` and confirm there was no fallback load. If the engine is still resident, the TTL is not effective; if the Ollama fallback was selected, it may remain resident under the 24-hour server setting and the candidate trial is invalid.

### Decision rule and rollback

Keep the alias only if all three observations hold together: (1) the candidate route is really `omlx-general`; (2) the candidate's median first visible content is lower than a fresh baseline run with the same prompt and model-unloaded state; and (3) while warm, oMLX still has a safe live seat-fit/headroom result for the currently required production seats, with no new prefill refusal or fallback. The 27–28 s file-size scenario is not the acceptance threshold.

If any condition fails, remove only the new alias, restore the prior oMLX model settings, restart the Pipeline through the orchestrator's normal deployment path, and verify `auto` routes back to the Ollama GGUF. Do not change the model seat based on offline timing or size estimates.

## Source notes

- Current routing/config: `config/portal.yaml` (`auto` and `auto-daily`), `config/backends.yaml` (`ollama-general`, `omlx-general`, `preferred_residents`), `portal/platform/inference/router/preinject.py`, `portal/platform/inference/router/streaming.py`.
- Engine request lifecycle: `portal/platform/inference/ollama_native.py` deliberately strips `keep_alive` and load-time options; `deploy/portal-5/docker-compose.yml` sets Ollama's 24-hour global keep-alive; `portal/platform/inference/load_guard.py` unloads idle models when needed.
- Local measurements/artifacts: `docs/engine_research/gguf_20261114.md`, `docs/MODEL_UNUSED_INVENTORY_20261115.md`, `config/MODEL_CATALOG.md`, `docs/GEMMA26B_QAT_CONSOLIDATION_20261106.md`, `coding_task/FINDING_OMLX080_SEAT_THRASH.md`.
- API shapes: [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx) (keep-alive and Flash Attention), [Ollama API](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml) (load timing fields), [oMLX model settings](https://github.com/jundot/omlx/blob/main/omlx/model_settings.py) (`ttl_seconds` and `max_context_window`), and [Open WebUI API endpoints](https://docs.openwebui.com/reference/api-endpoints/) (`POST /api/chat/completions`). Recheck the deployed engine versions at live preflight; web pages are current upstream, not proof of the host's exact runtime.

## Verified and unproven

Verified from this checkout: the current auto-daily hint, oMLX model registration, lack of the exact Nemotron alias in current `backends.yaml`, `preferred_residents: []`, `OLLAMA_KEEP_ALIVE=24h` in Compose, the native adapter's dropped lifecycle/context options, and the registered checkpoint/artifact sizes and historical warm decode figures cited above.

Unproven here: current cold first-token latency, whether the live deployment uses this Compose value unchanged, cold oMLX load time, candidate resident memory under the live prompt/context, current oMLX TTL setting, and live headroom/seat-fit while Nemotron is warm. The orchestrator owns those checks; this worker did not load either model or touch the live stack.
