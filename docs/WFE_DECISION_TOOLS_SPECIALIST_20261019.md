# WFE decision: tools-specialist seats Qwen3.6-35B-A3B (2026-10-19)

**Decision (operator, 2026-10-19):** `tools-specialist` moves from `granite4.1:8b-ctx8k` to
`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` (served on oMLX as
`unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit`).

## Evidence

The confirm tier ran on the corrected pipeline: tool-hop reasoning carried forward (c8fe27e8),
a hop's calls run in emitted order (68bfbd9a), library renderer/parser on every tag, and
serving conformance clean. Suite `tools_specialist_production` has 36 tasks × 3 repeats.

| Arm | Campaign | Pass | Median | p90 | Notes |
|---|---|---|---|---|---|
| granite4.1:8b (incumbent) | g | 96/108 (89%) | 10.2 s | 339 s | loops to the output cap on store-recall (median 227 s) |
| Qwen3.6-35B-A3B | h (g's incumbent rows reused) | 76/87 (87%) | 9.9 s | 17.6 s | curtailed NOT_SEPARATED; one malformed tool call, graded FAIL (da218e17) |
| Qwen3.8-27B | g | 76/78 (97%) | 21.9 s | 29.3 s | curtailed NOT_SEPARATED; about 16 GB extra memory |

Neither challenger separated from the incumbent under the exact sign test. The operator chose
Qwen3.6 on the lane's intent: a small, fast tool lane. It matches the incumbent's pass rate,
removes the five-minute store-recall loops (p90 17.6 s vs 339 s), and adds no memory because
the same weights are already resident for other seats. Qwen3.8 was more accurate but is too
heavy for this lane.

## Seat settings

The Qwen3.6 card's `thinking_precise_coding` arm (temperature 0.6, top_p 0.95, top_k 20,
min_p 0, presence 0, repeat 1.0), think on. A tools seat must serve its card's coding/precise
arm (settings_audit `sampling_mode_fit`). The confirm ran on the card's `thinking_general`
arm. On the chain tasks the two arms scored 23/24 and 22/24, so the difference is within noise.

## Defects found and fixed on the way

The pass rates above are only meaningful because these were fixed first:

- **Grader strictness:** stdout grounding required the bare value (c354fd4a).
- **Incumbent reuse:** never fired for route-served or async tools (83ef6d73).
- **Missing renderers:** about 30 Ollama tags had no RENDERER/PARSER (fixed on the host; now
  gated by validate_system `serving_conformance`).
- **Lost reasoning:** the tool loop dropped reasoning and prose between hops (c8fe27e8).
- **Parallel dispatch:** dependent calls raced, so recall ran before remember (68bfbd9a).
- **Mis-graded malformed calls:** a malformed tool call was graded HARNESS_ERROR and halted
  whole arms (da218e17).
