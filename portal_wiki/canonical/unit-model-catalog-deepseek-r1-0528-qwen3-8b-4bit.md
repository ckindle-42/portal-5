---
id: unit-model-catalog-deepseek-r1-0528-qwen3-8b-4bit
kind: what
title: "MODEL_CATALOG \u2014 `DeepSeek-R1-0528-Qwen3-8B-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786315000.0
updated_at: 1786315000.0
---

`DeepSeek-R1-0528-Qwen3-8B-4bit` is the 4-bit MLX conversion (mlx-community) of the DeepSeek-R1-0528 distill onto Qwen3-8B, served by the oMLX evaluation backend. `config/backends.yaml` registers it in the new `omlx-reasoning` entry (group `reasoning`, `priority: 10`, TASK_OMLX_FULL_PIPELINE_COVERAGE_V1) with `supports_tools: true`. The `aliases` block maps the production GGUF hint `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` onto this oMLX name — `reasoning`-group daily workspaces (`auto-reasoning`, `auto-compliance`, `auto-research`, `auto-data`) can now be served by oMLX with automatic Ollama fallback, no `workspace_routing` change.

This model initially audited as a hard NO on tool-calling (0/N) — root-caused, not worked around, as two real defects on disk in `/Volumes/data01/omlx-models/DeepSeek-R1-0528-Qwen3-8B-4bit/`: (1) `tokenizer_config.json` mislabeled `tokenizer_class` as `LlamaTokenizerFast` for a ByteLevel-BPE `tokenizer.json`, so `AutoTokenizer.from_pretrained` loaded the slow SentencePiece-style Llama tokenizer and corrupted decode (raw `Ġ`/`Ċ` byte markers leaking into output as literal text) — fixed to `PreTrainedTokenizerFast`, which uses `tokenizer.json`'s own correct `ByteLevel` decoder; (2) the upstream `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` `chat_template.jinja` (matched verbatim on this conversion) never renders the `tools` kwarg into the prompt at all — replaced with `unsloth/DeepSeek-R1-0528-Qwen3-8B`'s canonical tool-calling template (sourced from sglang's official `tool_chat_template_deepseekr1.jinja`, verified byte-identical between that repo's embedded and standalone template files, not hand-authored); (3) no `mlx_lm` tool parser recognized DeepSeek's `<｜tool▁calls▁begin｜>` format — added `mlx_lm/tool_parsers/deepseek_r1.py` to the running oMLX install (`/opt/homebrew/Cellar/omlx/0.5.7/libexec/lib/python3.11/site-packages/mlx_lm/`, the actual process per `lsof`/`ps` — a decoy `/Volumes/data01/omlx-venv` and a second homebrew site-packages exist but are not what `omlx-server` runs) and set `tool_parser_type: deepseek_r1` explicitly in this model's `tokenizer_config.json` (same explicit per-model override pattern as the prior Laguna tool-parser fix, not a global `_infer_tool_parser` change). Post-fix re-audit: 100% (6/6) structured `tool_calls` at `temperature: 0`; roughly 50-60% at default sampling — this 8B reasoning distill sometimes talks itself out of calling the tool in its `reasoning_content` before finishing with plain prose. `supports_tools: true` reflects a genuinely functional, temperature-sensitive capability (measured, not assumed) rather than a silent-failure flag.

## Why

Records the full root-cause chain because none of it is visible from `config/backends.yaml` alone: the fix lives partly in on-disk model files (tokenizer_config.json, chat_template.jinja) and partly in the running oMLX server's vendored `mlx_lm` package, neither tracked by this git repo. Without this unit, a future session re-auditing this model would see `supports_tools: true`, find it flaky at default temperature, and either wrongly conclude the flag is a lie or re-do the same tokenizer/template/parser investigation from scratch. The temperature-sensitivity finding is kept explicit because it is the honest caveat, not a reason to downgrade the flag — same discipline as the group's cross-group memory-ceiling finding in the parent task.
