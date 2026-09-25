---
id: unit-known-limitations-omlx-qwen3coder-tool-text
kind: what
title: oMLX Drops Some Qwen3-Coder Tool Calls Into Text (Resolved)
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: portal/platform/inference/router/text_tool_calls.py
claims: []
confidence: high
tags:
- known-limitations
- omlx
- tools
- resolved
created_at: 1790352000
updated_at: 1790362799
---

- **ID**: P5-OMLX-QWEN3CODER-TOOLTEXT-001
- **Status**: RESOLVED 2026-09-25. The pipeline recovers the call (`salvage_text_tool_calls` / `TextToolCallHoldback` in `portal/platform/inference/router/text_tool_calls.py`, used by the streaming and non-streaming tool loops and by the WFE harness). Each recovery increments `portal5_tool_calls_recovered_total{workspace}`.
- **Description**: `Qwen3-Coder-30B-A3B-Instruct-4bit` on oMLX (0.6.4, `mlx_lm` `qwen3_coder` tool parser) sometimes omits the `<tool_call>` opener and writes `<function=NAME>…</function>\n</tool_call>` straight into content, sometimes after a stray word (`Paris\n<function=get_weather>…`). `mlx_lm`'s parser only enters tool mode on the opener, so the call came back as plain `content` and nothing was dispatched. The vendor's own `qwen3coder_tool_parser.py`, shipped in the model directory, accepts `<function=` without the opener; Ollama's parser is tolerant too.
- **What the first measurement missed**: the loss depends on the prompt shape, not mainly on temperature. With a bare single-tool probe it was 2–4 of 6 at the card sampling and 90–100% parsed at 0.2. Through the pipeline, with the workspace prompt and tool set, some prompts lost the opener on every attempt, even at the seat's 0.2: a weather question 40/40 at 0.7–1.2 and 10/10 at seat sampling, `sandbox_status` and `remember` requests too. Others (`execute_python`, `execute_bash`, `recall`) stayed native. So the low-temperature revert never covered it.
- **Fix**: when tools were offered, content from the first `<function=` or `<tool_call>` marker on is withheld from the stream. At the end of the stream it is parsed against the offered tool names and schema types and dispatched like a native call. If it does not parse, or names a tool that was not offered, the held text is released unchanged and in order (finish frame and `[DONE]` after it). Verified live 2026-09-25 across `auto-coding`, `auto-bigfix` and `auto-cad`, streaming and non-streaming: 200/200 probe calls (card, seat and 1.2 temperature) delivered as `tool_calls` with no XML in the text, recovered workspace calls dispatched end to end, and `./scripts/smoke_stream.sh` PASS.
- **Follow-up**: the card-sampling A/B for these three seats is unblocked (`docs/TASK_SEAT_SAMPLING_AB_V1.md`). An upstream report to `mlx_lm` (accept `<function=` without the opener, as the vendor parser does) is optional.

## Why

A tool call that comes back as text looks like a normal answer: nothing errors. The seat just stops using its tools some of the time, and the user sees raw XML. Recovering it in the pipeline fixes every engine and quant that emits this shape, and it survives oMLX updates. Checking against the offered tool names keeps a quoted example in a coding answer from being executed.
