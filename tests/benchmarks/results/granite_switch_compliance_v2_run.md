# Granite Switch v2 — corrected adapter/prompt vs seated Ollama compliance model

## Granite Switch (checkpoint templates, no truncation)

- Checkpoint: `/Users/chris/.portal5/granite-switch/granite-switch-4.1-3b-preview` on `mps`
- Edges run: 183, wall time: 1062.0s (5.8s/edge combined; ~2.9s/edge per adapter)

### factuality-detection (checkpoint's own instruction, full text) — real result
- Defect catch (gold UNSUPPORTED/WRONG_RELATION correctly flagged): 11/42 (26.2%)
- SUPPORTED false positives: 54/141 (38.3%)

### requirement-check — NOT a usable result, reported for the record only
- Defect catch: 42/42 (100.0%)
- SUPPORTED false positives: 141/141 (100.0%)

Checked the raw replies: every single one of the 183 requirement-check calls
returned `{"score": "no"}` — zero variance across the whole corpus,
including on strong SUPPORTED edges with clear, on-topic citations. This
adapter, given only the cited sentences (no full document context) as the
"generation" to check, produces a constant output rather than a real
judgment. The apparent "100% defect catch" is an artifact of that constant
output, not evidence the correct-adapter framing worked — it did not.
requirement-check needs either the full section_text as context (not just
the citation) or a different prompt structure closer to its native
"did the assistant's answer meet the stated constraints" framing before it's
worth measuring again.

## Seated Ollama compliance model (same corpus, same judgment question)

- Model: `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`
- Edges run: 183, wall time: 374.4s (2045.6ms/edge)
- Defect catch: 100.0%
- SUPPORTED false positives: 75.2%

Unlike requirement-check, this is a real, discriminating result (148
unsupported / 35 supported replies, not constant) — it's just biased toward
"unsupported" given only the bare citation as evidence, same thin-context
issue as above but less extreme.

## What's actually comparable

- **Accuracy:** factuality-detection's false-positive rate (38.3%) is
  meaningfully lower than Ollama's (75.2%) on the same thin-context
  question — Granite is more conservative about crying wolf. But
  factuality-detection's defect catch (26.2%) is far below Ollama's
  (100%) — Ollama catches far more real problems, at the cost of many
  more false alarms. Neither is a clean win; it depends whether a
  compliance guard should optimize for few false alarms or few misses.
- **Speed, which was the operator's actual ask:** Ollama is *faster per
  edge* (2.05s) than Granite Switch (~2.9s per adapter), despite Qwen3.8
  being an 8x larger model. Ollama runs through an optimized llama.cpp
  Metal backend; Granite Switch runs through raw HuggingFace
  `transformers` on MPS, which is known to be slow. On this hardware,
  right now, Granite Switch is not a speed win even setting accuracy
  aside.

## Operator gate (P3.G1, corrected)

This task does not wire either into the compliance module. Given the
speed result and the unresolved requirement-check framing, this does not
look ready to promote as-is. A follow-up would need either a faster
Granite Switch inference path (MLX port, not raw transformers/MPS) or a
reworked requirement-check prompt with full document context before
re-measuring.

Operator decision: PENDING
