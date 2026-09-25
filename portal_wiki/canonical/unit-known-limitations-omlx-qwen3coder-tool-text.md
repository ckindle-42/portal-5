---
id: unit-known-limitations-omlx-qwen3coder-tool-text
kind: what
title: oMLX Drops Some Qwen3-Coder Tool Calls Into Text (Open)
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
claims: []
confidence: high
tags:
- known-limitations
- omlx
- tools
- open
created_at: 1790352000
updated_at: 1790352000
---

- **ID**: P5-OMLX-QWEN3CODER-TOOLTEXT-001
- **Status**: OPEN 2026-09-25. Mitigated by sampling: `auto-coding`, `auto-bigfix` and `auto-cad` keep low temperature (0.1–0.2, `top_k` bounded) instead of the Qwen3-Coder card's 0.7/0.8/20.
- **Description**: `Qwen3-Coder-30B-A3B-Instruct-4bit` on oMLX (0.6.4, `mlx_lm` `qwen3_coder` tool parser) sometimes starts its reply with a stray word and skips the `<tool_call>` opener. For example, it writes `Paris\n<function=get_weather>…</function>\n</tool_call>`. The parser only switches to tool mode on the opener, so the call is returned as plain `content` with no `tool_calls`, and the pipeline dispatches nothing. Measured with a neutral single-tool probe: at the card's sampling, 4/6 calls were parsed; at the prior 0.2/0.9/40 block, 6/6 and 9/10; with an unbounded `top_k`, 5/6. Ollama serves the same model with a tolerant parser (3/3 at 0.7).
- **Fix owed**: salvage a Qwen3-Coder XML call from `content` when tools were offered (pipeline, streaming and non-streaming, smoke-tested with `./scripts/smoke_stream.sh`), or patch/report the oMLX parser. Then the card-sampling A/B for these seats can run. See `docs/TASK_SEAT_SAMPLING_AB_V1.md` C6.

## Why

A tool call that comes back as text looks like a normal answer: nothing errors. The seat just stops using its tools some of the time. Tool reliability outranks a vendor sampling recommendation for a coding seat whose job is tool use, so the card lost here on evidence.
