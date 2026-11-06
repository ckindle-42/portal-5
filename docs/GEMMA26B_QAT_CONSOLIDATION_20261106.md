# Gemma 4 26B QAT consolidation prep — 2026-11-06

This prep moves auto-documents to the existing QAT MLX build and leaves the other plain-4bit callers in place until their seat-specific comparisons complete. The six queued WFE jobs and plans are listed below; no WFE campaign or Ollama model creation was run in this worktree.

## QAT conversion window

The read-only QAT MLX checkpoint config at /Volumes/data01/omlx-models/gemma-4-26b-a4b-it-QAT-4bit/config.json resolves to a HF cache snapshot. Its text_config declares max_position_embeddings 262144. Full attention uses proportional RoPE with theta 1000000; sliding attention uses default RoPE with theta 10000. vision_config declares max_position_embeddings 131072. Therefore the conversion covers the planned 8k, 32k, 64k and 128k text windows and the 8k vision fallback check.

The QAT GGUF model layer is sha256:4c856523d61d77922dbc0b26753a6bf6208e5d69d80db0c04dcd776832d054c5 in the local Ollama store. Its tokenizer metadata names <eos>; its embedded chat template ends messages with <turn|>. The ctx64k and ctx128k recipes inherit the QAT GGUF template and Gemma 4 renderer/parser from the existing ctx8k tag, then set num_ctx and both stop tokens. They are recipes only; no ollama create was run.

## Seat inventory and evidence

| Caller | Current plain context | Prior evidence cited by the seat | QAT check queued |
|---|---:|---|---|
| auto-documents | 16,384 seat limit; 32k tag | docs/WFE_DECISION_AUTO_DOCUMENTS_20261017.md: Gemma beat Granite and tied Qwen3.8 at 108/108. 2026-11-06 same-engine oMLX: plain 31/32, QAT 30/32; pooled 46/48 each. | Same real-use task set, exact seat sampling, four repeats: tests/wfe/plans/realuse_v1_documents_qat_omlx.yaml |
| compliance-reading-overflow | 65,536 | config/portal.yaml documents four of 255 register nodes priced above 32k and fitting 65k; PIPELINE_ALIGNMENT_V1 §P2 binds this overflow seat. | Twelve 40k long-context needle, aggregation and quote rows plus paired real CIP-003-8 register sweeps: tests/wfe/plans/gemma26b_qat_overflow64k_20261106.yaml and config/arm_jobs/gemma26b-qat-overflow64-ab.yaml |
| auto-compliance::reading | 131,072 | config/portal.yaml DATA_TRUTH Amendment 1 records a 124,660-token real-document read, deep facts quoted exactly, with 59% memory free; config/MODEL_CATALOG.md preserves the tag decision. | All 40k/80k/112k synthetic long-context tasks plus reading_production, four repeats; real corpus acceptance is a second job step: tests/wfe/plans/gemma26b_qat_reading128k_20261106.yaml |
| compliance-mapping | 131,072 | config/portal.yaml says this tool-less machine seat catches the DATA_TRUTH reading tag and shares its 128k model; its strict-JSON sampling uses repetition penalty 1.1. | Full long-context suite at this seat's sampling: tests/wfe/plans/gemma26b_qat_mapping128k_20261106.yaml |
| Vision persona fallback lists | 8,192 workspace limit; 32k plain tag | The six persona files list plain Gemma after the two Qwen3-VL tags: ocrspecialist, chartanalyst, diagramreader, codescreenshotreader, whiteboardconverter and gemma4e4bvision. No QAT fallback promotion is assumed. | vision_production at auto-vision sampling: tests/wfe/plans/gemma26b_qat_vision_fallbacks_20261106.yaml |
| bench-gemma4-26b-optiq | Unpinned in config/bench_workspaces.yaml | Its description pairs the Ollama GGUF against auto-daily; no seat-specific WFE result or context_limit is declared. | Ten no-tool general tasks with both arms pinned to the same 32k tags and bench sampling: tests/wfe/plans/gemma26b_qat_bench_20261106.yaml |

The compliance-mapping and bench plans use production-mode empty tool allowlists because their selected suites are no-tool tasks and those workspaces expose no tools. The overflow plan selects only 40k synthetic tasks because its 64k window cannot run the 80k and 112k suite rows.

## Queue entries

Each config/arm_jobs/gemma26b-qat-*-ab.yaml file runs one seat plan through the Pipeline, serially, at confirm tier with four repeats. gemma26b-qat-reading128-ab also runs scripts/compliance_acceptance.py through the reader adapter against both 128k tags. The ctx64k and ctx128k fallback tags can be created later from the checked-in recipes; this worker did not create them.

## Retirement order

1. Auto-documents has moved to QAT in config/portal.yaml. Keep the plain build until the queued seat-sampling confirm is reviewed.
2. Retire the bench plain tag after its matched 32k comparison; the bench window itself remains an operator decision because it is not currently pinned.
3. Retire the vision fallback references after the 8k image comparison is reviewed.
4. Retire the 64k overflow plain tag after its 40k suite and four register-node coverage are confirmed.
5. Retire the 128k DATA_TRUTH plain tag last, after the 112k needle/real-document checks and actual reader acceptance confirm no truncation and preserved deep facts.

The vision persona lists, 64k and 128k seats, and bench workspace remain on plain-4bit in configuration until those comparisons are reviewed.
