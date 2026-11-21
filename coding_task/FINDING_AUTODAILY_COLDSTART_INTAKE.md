# Auto-daily cold-start screen — intake

Date: 2026-11-20
Seat under test: `auto-daily` (incumbent `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k`)
Action if a candidate wins: repoint `auto-daily.model_hint` and run the 2–3 day real-use trial
Budget: 2 candidates × 3 cold trials + 6 real-use tasks × (2 challengers + incumbent) × 1 repeat

This lane stages the screen. It does not load a model, pull a tag, or touch the live stack.

## Candidates

| Family | Newest variant at intake | Ollama artifact | oMLX artifact | On disk |
|---|---|---|---|---|
| Qwen3.5-9B (released 2026-03-02) | post-trained 9B, thinking on by default | `qwen3.5:9b-q4_K_M` — 6.6 GB, arch `qwen35`, Q4_K_M (5.6 GB model + 922 MB BF16 vision projector) | `bambocher/Qwen3.5-9B-oQ4e-mtp` — oMLX 0.7.3, 6.529 GB (6.081 GiB), 5.411 bits/weight, MTP head kept, updated 2026-11-13 | no |
| Gemma 4 12B (released 2026-06-03) | 12B Unified, 256K context, thinking modes | `gemma4:12b-it-q4_K_M` — 8.0 GB, arch `gemma4`, Q4_K_M, 423M Q8_0 assistant/draft | `Jundot/gemma-4-12B-it-oQ4e-mtp` — oMLX 0.7.3, 8.072 GB (7.517 GiB), 5.215 bits/weight, MTP head kept, updated 2026-10-29 | no |

Gemma also ships a quantisation-aware-trained base (`gemma4:12b-it-qat`, 7.2 GB, Q4_0; MLX oQ4e of the QAT base exists as `djrsystemservices/gemma-4-12B-it-qat-oQ4e-mtp`). It is the better 4-bit Gemma build, but it is Q4_0, not the brief's `q4_K_M`. The screen therefore starts on the Q4_K_M artifact; swap the tag and the oMLX alias to the QAT pair if the orchestrator prefers quality over the stated quant. Do not run both Gemma arms in one screen.

Qwen3.5 has no QAT release; the Q4_K_M artifact is the documented 4-bit default. The oMLX oQ4e artifact is an enhanced mixed-precision 4-bit build (`oQ4e`), the level oMLX documents as the starting point.

## Checklist (feedback_seat_quant_and_template_verification)

| Check | Qwen3.5-9B | Gemma 4 12B |
|---|---|---|
| Quant is the requested class | **verified**: Ollama manifest says `Q4_K_M`; oQ4e says 5.411 bpw (4/5/6/16-bit mix) | **verified**: Ollama manifest says `Q4_K_M`; oQ4e says 5.215 bpw |
| Card sampling | **verified** from the Ollama params blob: temperature 1, top_p 0.95, top_k 20, presence_penalty 1.5 | **verified** from the Ollama params blob: temperature 1, top_p 0.95, top_k 64 |
| Thinking default | **verified** from the Qwen3.5 card: thinking on by default, disable per request | **verified** from the Ollama tag: `thinking` capability; the `gemma4` template enables thinking via the system `<\|think\|>` token |
| Template renders a chat | **Ollama tag stores `{{ .Prompt }}`** — the library manifest's template blob is `{{ .Prompt }}`, not a chat template. Ollama may still use its native `qwen35` renderer; that is unproven here. The MLX/oQ4e artifact does ship the model's chat template. | **verified at the tag level**: Ollama advertises `tools` + `thinking`; the template is Ollama-managed. The MLX/oQ4e artifact ships the model's chat template. |
| Native tool calls | **unproven on this host**. oMLX 0.8.0 documents a Qwen3.5 XML function-call parser; a direct probe is still required, and on Ollama the `{{ .Prompt }}` template is a red flag until the merged-tool probe returns typed `tool_calls`. | **unproven on this host**. The Gemma 4 card documents native function calling and oMLX documents a `<start_function_call>` parser; a direct probe is still required on both engines. |
| Context | 262,144 native; auto-daily declares 16,384 | 256,000 native; auto-daily declares 16,384 |
| GGUF fallback exists | yes: `qwen3.5:9b-q4_K_M` → `Qwen3.5-9B-oQ4e-mtp` | yes: `gemma4:12b-it-q4_K_M` → `gemma-4-12B-it-oQ4e-mtp` |

The only template finding strong enough to act on is Qwen's Ollama library template. Treat every `supports_tools` on the new entries as **false until a direct typed tool-call probe passes**; the probe is the first gate in the orchestrator run. A candidate that cannot emit native tool calls cannot hold `auto-daily`, whose seat carries web, knowledge-base, document, Python, memory and transcription tools.

## Staging shape, and why it is not final

The bench workspaces point at the **base** GGUF tags, and the registry carries both the base tag and the derived `-ctx16k` tag:

- `qwen3.5:9b-q4_K_M` / `gemma4:12b-it-q4_K_M` — acquisition tags and the oMLX alias keys.
- `qwen3.5:9b-q4_K_M-ctx16k` / `gemma4:12b-it-q4_K_M-ctx16k` — `PARAMETER num_ctx 16384` baked from `config/modelfiles/`, both registered so the real-use arms resolve.

The bench workspace keeps the base tag until the live working-context preflight is recorded. Setting `ctx_validated: true` now would claim a probe this lane did not run; omitting it on a baked `-ctxNk` hint fails check BW. The orchestrator repoints the two bench `model_hint` values to the derived tags and adds `ctx_validated: true` in the same edit that records the preflight result. This is the same shape as the Flint bench intake (2026-10-21): base tag + card sampling + a documented derived-tag prerequisite.

The cold-start phase itself can run before that edit: it resolves the base tag to the oMLX checkpoint through the alias (priority 10), and its prompt is short, so the Ollama fallback's default window is irrelevant.

## Acquisition and preflight (orchestrator only)

```bash
# 1. Pull/stage both engines' artifacts.
ollama pull qwen3.5:9b-q4_K_M
ollama pull gemma4:12b-it-q4_K_M
hf download bambocher/Qwen3.5-9B-oQ4e-mtp \
  --local-dir /Volumes/data01/omlx-models/Qwen3.5-9B-oQ4e-mtp
hf download Jundot/gemma-4-12B-it-oQ4e-mtp \
  --local-dir /Volumes/data01/omlx-models/gemma-4-12B-it-oQ4e-mtp

# 2. Bake the 16k Ollama fallbacks from the committed Modelfiles.
ollama create qwen3.5:9b-q4_K_M-ctx16k \
  -f config/modelfiles/qwen3.5-9b.Q4_K_M-ctx16k.Modelfile
ollama create gemma4:12b-it-q4_K_M-ctx16k \
  -f config/modelfiles/gemma4-12b-it.Q4_K_M-ctx16k.Modelfile

# 3. Prove the working window and the tool path on each engine/model.
ollama show qwen3.5:9b-q4_K_M-ctx16k --modelfile | rg 'num_ctx'
ollama show gemma4:12b-it-q4_K_M-ctx16k --modelfile | rg 'num_ctx'
# settings_audit --behavioral is the repo's typed tool-call probe; run it per tag.
uv run python scripts/settings_audit.py --tag qwen3.5:9b-q4_K_M-ctx16k --behavioral
uv run python scripts/settings_audit.py --tag gemma4:12b-it-q4_K_M-ctx16k --behavioral
# oMLX: one direct /v1/chat/completions call with a two-tool array per checkpoint;
# require native tool_calls with typed arguments and no text-form <tool_call>.

# 4. Set unproven flags only after step 3 passes.
#    config/backends.yaml: supports_tools: true on the proven entry.
#    config/bench_workspaces.yaml: model_hint -> the -ctx16k tag, ctx_validated: true.
```

The oMLX host settings (`~/.omlx/model_settings.json`, host-owned) need `max_context_window: 16384` on each candidate and a finite `ttl_seconds` (300 s is the prior proposal); do not pin them. The pipeline drops request-time `num_ctx`; the window must be set at the model, not the workspace.

The cold-start phase targets the two `bench-autodaily-*` seats, so the Pipeline process must have the eval/bench workspaces merged for the run (`PORTAL_ENABLE_EVAL=true` on the Pipeline service — the explicit opt-in path). With eval off, the seat id is a 404 by design; that is not a candidate failure. The real-use quality run does not depend on this: it addresses `auto-daily` with a `?model=` arm by tag.

## What the intake does not prove

- Cold first-token latency on either engine/model. No load was run.
- That Ollama's `qwen35` native renderer supplies a chat/tool template over the `{{ .Prompt }}` library template.
- Native tool calls on either candidate on either engine.
- That an oQ4e artifact loads on the host's oMLX build (0.8.0 vs the 0.7.3 builds cited) or that its MTP head activates.
- That the oMLX checkpoint and the GGUF fallback share the same tokenizer/template output byte-for-byte.

## Sources

- Qwen3.5-9B card: https://huggingface.co/Qwen/Qwen3.5-9B
- `qwen3.5:9b-q4_K_M` manifest: https://ollama.com/library/qwen3.5:9b-q4_K_M
- `bambocher/Qwen3.5-9B-oQ4e-mtp`: https://huggingface.co/bambocher/Qwen3.5-9B-oQ4e-mtp
- Gemma 4 12B card: https://huggingface.co/google/gemma-4-12B-it
- `gemma4:12b-it-q4_K_M` manifest: https://ollama.com/library/gemma4:12b-it-q4_K_M
- `gemma4:12b-it-qat` manifest: https://ollama.com/library/gemma4:12b-it-qat
- `Jundot/gemma-4-12B-it-oQ4e-mtp`: https://huggingface.co/Jundot/gemma-4-12B-it-oQ4e-mtp
- oMLX oQ levels: https://github.com/jundot/omlx/blob/main/docs/oQ_Quantization.md
