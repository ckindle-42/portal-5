---
id: unit-wfe-loop-attribution-protocol
kind: mixed
title: "WFE / bench loop attribution protocol (Rule 5)"
sources:
- type: doc
  path: docs/SALUKI_27B_SPIKE_CLOSEOUT.md
- type: code
  path: scripts/saluki_rule5_reverify.py
- type: code
  path: tests/wfe/prompt_surface.py
claims: []
confidence: high
tags:
- authored-v1
- tests
- evaluation
- attribution
created_at: 1791000000
updated_at: 1791000000
---

## Why

A turn-cap loop, a tool-call loop or a format failure is NOT attributed to a model
until these controls have run on the same instrument. The Saluki spike's original
"2-bit model collapse" claim skipped most of them and was withdrawn on 2026-10-12
(record: docs/SALUKI_27B_SPIKE_CLOSEOUT.md, Rule-5 paragraph).

Required before naming the model:

1. **Incumbent control on the same instrument.** The same prompt, tools and
   settings on the seat the operator already trusts. If the incumbent loops too,
   the instrument is at fault.
2. **Think-on arm.** Run the model at its card's think setting as well as the
   lane's forced think-off. A reasoning card measured only think-off is a lane-fit
   result, not a capability result.
3. **No-format-clause control, on the production engine.** Same loop with the
   output-format instruction removed. Use the production engine (Ollama), not only
   a second engine.
4. **Rendered-prompt capture.** Record what the engine actually feeds the model on
   the post-tool turn. Compare the prompt token count with the official template
   render (the GGUF's embedded jinja, with enable_thinking set to match the arm).
   Note the known trailing-newline artifact on Ollama's chat path.
5. **Prompt/tool-surface check.** `tests/wfe/prompt_surface.py` must report no
   WARN for the workspace. A prompt that names tools the harness does not offer
   sends the model hunting; that is a harness fault.
6. **Tool-argument logging.** Record tool arguments as well as tool names
   (`tool_args` in `scripts/saluki_rule5_reverify.py`).
7. **Seeded n of at least 3.** Report the counts, not one run.

Engine cross-checks clear the ENGINE only. A repro that shares one embedded
template across two engines does not clear the template or the settings.

Reference script: `scripts/saluki_rule5_reverify.py`. Decision thresholds for
any future run go in the receipt BEFORE the run.
