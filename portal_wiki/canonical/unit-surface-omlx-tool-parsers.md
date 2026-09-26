---
id: unit-surface-omlx-tool-parsers
kind: mixed
title: "oMLX tool parsers — the upgrade-surviving parser install"
sources:
- type: code
  path: scripts/omlx/deepseek_r1_tool_parser.py
- type: code
  path: scripts/install_omlx_parsers.sh
claims: []
confidence: high
tags:
- authored-v1
- surface
- omlx
created_at: 1790412800.0
updated_at: 1790412800.0
---

- **What**: `scripts/omlx/deepseek_r1_tool_parser.py` is the canonical copy of
  the `deepseek_r1` mlx_lm tool parser for DeepSeek-R1-0528-Qwen3-8B, and
  `scripts/install_omlx_parsers.sh` installs it into the running brew oMLX
  site-packages and stamps the model's `tokenizer_config.json` with
  `tool_parser_type: deepseek_r1`.

- **Why it exists**: oMLX loads text-model tool parsers from
  `mlx_lm.tool_parsers.<tool_parser_type>` (mlx_lm/tokenizer_utils.py). The
  first copy of this parser was installed directly into the brew
  site-packages and was SILENTLY LOST on a later `brew upgrade omlx` — the
  DeepSeek council-operator seat stopped emitting tool calls until the loss
  was diagnosed (2026-09-25, P5-FANOUT-001). The canonical copy now lives in
  the repo; the installer re-applies it in one command after every upgrade.

- **Format parsed**: the DeepSeek marker language, verbatim from the model's
  tokenizer — `<｜tool▁calls▁begin｜>…<｜tool▁call▁begin｜>function<｜tool▁sep｜>NAME
  ```json {…}```<｜tool▁call▁end｜>…<｜tool▁calls▁end｜>` (U+FF5C and U+2581, not
  ASCII look-alikes). Multiple calls per block are returned as a list; no call
  raises ValueError, never fabricates.

- **Verified live 2026-09-25**: after install + oMLX restart, the
  DeepSeek-R1-0528-Qwen3-8B-4bit seat emits clean typed `get_weather` calls at
  temperature 0 and 0.3 through `/v1/chat/completions` with tools.

- **Lane effect**: the council Operator/User Advocate seat
  (DeepSeek-R1-0528-Qwen3-8B) and auto-reasoning now have an oMLX path; the
  alias in `config/backends.yaml` `omlx-reasoning` supersedes that file's
  2026-08 "deliberately NOT here" note for this model.

## Why

The parser fragility was previously handled by choosing the Ollama GGUF for
the whole lane; the installer converts that from a permanent limitation into a
one-command maintenance step, and the repo copy means the parser can never be
lost without the loss being visible in git.
